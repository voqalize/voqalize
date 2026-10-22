"""Clini's own public lookups, read server side: prices and open hours.

Two of Clini's hosts answer plain GETs with JSON, without a login or a cookie:

- the price quote, ``cotizador-web.clini.cl/Cotizar?handler=Buscar&q=…``: up to
  twelve exams by name, each with its Fonasa copago and its particular price,
  whether it needs contrast, and its preparation;
- the booking, ``agenda-web.clini.cl/?handler=Disponibilidad`` (which days have
  hours) and ``?handler=HorariosDia`` (a day's hours, by centre).

A page on www.clini.cl cannot read them (another origin, no CORS headers), so
the brain does, while the visitor waits for the answer: on one kept-alive
client, with a deadline per lookup and a small cache, and a failure is an
exception the tool turns into a plain sentence (the price falls back to the
catalogue the crawl saved). A booking tab that shows an exam starts the lookup
for it in the background (:func:`prefetch`), so the question usually finds the
answer waiting.

Only reads. The booking's ``AgendarCitaMedica`` (which books) and
``PacientePorDocumento`` (which looks a patient up by RUT) are never called from
here: a booking is the visitor's to press, and their RUT is theirs to type.
"""

from __future__ import annotations

import asyncio
import importlib.util
import math
import os
import time
from collections.abc import Coroutine
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

import httpx
from loguru import logger

COTIZADOR = "https://cotizador-web.clini.cl/Cotizar"
AGENDA = "https://agenda-web.clini.cl/"
TIMEZONE = ZoneInfo("America/Santiago")

#: How long one tool waits for its lookup, all of its requests together: a
#: visitor is waiting, with only his nod in the air. A per-request timeout is
#: not that: one 4 s per phase let a lookup run past 8 s (dev call 2fd742d5).
PRICE_DEADLINE_S = 4.0
AGENDA_DEADLINE_S = 6.0
#: One request's own ceiling, longer than either deadline: a lookup the tool
#: stopped waiting for still finishes, and lands in the cache for the next ask.
REQUEST_TIMEOUT_S = 15.0
CONNECT_TIMEOUT_S = 5.0
#: Prices move rarely; open hours move as people book.
PRICE_TTL_S = 600.0
AGENDA_TTL_S = 90.0
_CACHE_MAX = 256

#: The servicio whose Región Metropolitana search also takes a sector
#: (laboratorio, ``#sector62Select``); the booking sends TODOS by default.
_SECTOR_SERVICIO = 62
_RM = 13

Period = Literal["AM", "PM"]


class LookupFailed(Exception):
    """A lookup that did not answer in time, or answered with an error."""


class LookupSlow(LookupFailed):
    """A lookup that missed its deadline and is still running: asked again, or
    awaited with a longer one, it is answered by the same requests."""


# ─── The wire ──────────────────────────────────────────────────────────────────
#
# The brains run far from Chile: a new connection to either host costs 1.1 s
# from India, 1.8 s on the brains node (its resolver takes 0.7 s a lookup), and
# a lookup used to pay it twice, once per stage. So there is one client, kept
# alive: both hosts are IIS, which keeps an idle connection for 120 s, and the
# session's start opens them before the first question (:func:`warm`).

#: HTTP/2 only when its package is installed: one connection then carries the
#: morning and the afternoon together.
_HTTP2 = importlib.util.find_spec("h2") is not None
#: Under IIS's 120 s, so a connection is never reused as the server drops it.
_KEEPALIVE_S = 110.0
#: A host used this recently is warm already.
_WARM_AGAIN_S = 60.0

_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None
#: A test's fake transport; ``None`` is the network.
_transport: httpx.AsyncBaseTransport | None = None
_cache: dict[str, tuple[float, Any]] = {}
#: The requests under way, by cache key: a second ask for the same thing waits
#: on the first rather than sending it again, and a request the asker stopped
#: waiting for runs on into the cache.
_inflight: dict[str, asyncio.Task[Any]] = {}
#: Work started and awaited by nobody, kept alive until it ends.
_background: set[asyncio.Future[Any]] = set()
#: When each host was last asked, for :func:`warm`.
_touched: dict[str, float] = {}


def _cache_key(url: str, params: dict[str, str]) -> str:
    return url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))


def _http() -> httpx.AsyncClient:
    """The one client, made on first use in this event loop."""
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(REQUEST_TIMEOUT_S, connect=CONNECT_TIMEOUT_S),
            limits=httpx.Limits(
                max_connections=8, max_keepalive_connections=4, keepalive_expiry=_KEEPALIVE_S
            ),
            http2=_HTTP2,
            follow_redirects=True,
            transport=_transport,
        )
        _client_loop = loop
    return _client


def _offline() -> bool:
    """A test run with no fake transport: nothing reaches Clini's hosts, even
    from a session another demo's test opened (the voice-contract sweep)."""
    return "PYTEST_CURRENT_TEST" in os.environ and _transport is None


async def _get_json(url: str, params: dict[str, str], timeout: float) -> Any:
    """One GET on the shared client, its JSON decoded; :class:`LookupFailed`
    on anything else. A kept-alive connection the server closed as it was
    reused is tried once more, on a fresh one."""
    _touched[httpx.URL(url).host] = time.monotonic()
    for attempt in (1, 2):
        try:
            response = await _http().get(
                url, params=params, headers={"Accept": "application/json"}, timeout=timeout
            )
            response.raise_for_status()
            return response.json()
        except httpx.RemoteProtocolError as e:
            if attempt == 2:
                raise LookupFailed(f"{type(e).__name__}: {e}") from e
        except (httpx.HTTPError, ValueError) as e:
            raise LookupFailed(f"{type(e).__name__}: {e}") from e
    raise AssertionError("unreachable")


def _spawn[T](work: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
    """``work`` as a task nobody awaits, kept alive until it ends, its error
    read so it is never reported as lost."""
    task = asyncio.get_running_loop().create_task(work)
    _background.add(task)

    def ended(t: asyncio.Task[T]) -> None:
        _background.discard(t)
        if not t.cancelled() and (e := t.exception()) is not None:
            logger.debug("clini: background lookup failed: {}", e)

    task.add_done_callback(ended)
    return task


async def _fetch(key: str, url: str, params: dict[str, str], timeout: float, ttl: float) -> Any:
    data = await _get_json(url, params, timeout)
    now = time.monotonic()
    if len(_cache) >= _CACHE_MAX:
        for stale in [k for k, (until, _) in _cache.items() if until <= now] or list(_cache)[:32]:
            _cache.pop(stale, None)
    _cache[key] = (now + ttl, data)
    return data


async def _cached(url: str, params: dict[str, str], ttl: float) -> Any:
    """The answer to one GET: from the cache, from the same request already
    under way, or from a new one. A caller that stops waiting (a deadline, a
    barge-in) leaves the request running, so its answer is cached all the same."""
    key = _cache_key(url, params)
    hit = _cache.get(key)
    if hit is not None and hit[0] > time.monotonic():
        return hit[1]
    task = _inflight.get(key)
    if task is None:
        task = _spawn(_fetch(key, url, params, REQUEST_TIMEOUT_S, ttl))
        _inflight[key] = task
        task.add_done_callback(
            lambda t: _inflight.pop(key, None) if _inflight.get(key) is t else None
        )
    return await asyncio.shield(task)


def warm() -> None:
    """Open the connections the first question will use: two to the booking
    (its morning and afternoon are asked together), one to the price list.
    Fire and forget; a host used in the last minute is left alone."""
    if _offline():
        return
    now = time.monotonic()
    for url, connections in ((AGENDA, 2), (COTIZADOR, 1)):
        host = httpx.URL(url).host
        if now - _touched.get(host, -math.inf) < _WARM_AGAIN_S:
            continue
        _touched[host] = now
        for _ in range(connections):
            _spawn(_touch(url))


async def _touch(url: str) -> None:
    try:
        await _http().head(url)
    except httpx.HTTPError as e:
        logger.debug("clini: warming {} failed: {}", url, e)


def clear_cache() -> None:
    """Forget every answer and stop every lookup under way (the tests' reset)."""
    _cache.clear()
    _days.clear()
    _touched.clear()
    for task in [*_inflight.values(), *_background]:
        task.cancel()
    _inflight.clear()
    _background.clear()
    _prefetching.clear()


# ─── Prices ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Price:
    """One exam as the cotizador lists it. Prices are Chilean pesos."""

    nombre: str
    servicio: str = ""
    categoria: str = ""
    fonasa: int | None = None
    """The Fonasa Nivel 1 copago (tramos B, C and D)."""
    particular: int | None = None
    contraste: bool = False
    preparacion: str = ""


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        digits = "".join(c for c in value if c.isdigit())
        return int(digits) if digits else None
    return None


def price_from(raw: Any) -> Price | None:
    """A cotizador item (the API's or the saved catalogue's), or ``None``."""
    if not isinstance(raw, dict):
        return None
    item = cast(dict[str, Any], raw)
    nombre = str(item.get("nombre") or item.get("name") or "").strip()
    if not nombre:
        return None
    return Price(
        nombre=nombre,
        servicio=str(item.get("servicio") or ""),
        categoria=str(item.get("categoria") or ""),
        fonasa=_int(item.get("precioFonasa", item.get("fonasa"))),
        particular=_int(item.get("precioParticular", item.get("particular"))),
        contraste=bool(item.get("requiereContraste", item.get("contraste", False))),
        preparacion=str(item.get("preparacion") or "").strip(),
    )


async def search_prices(query: str) -> list[Price]:
    """The cotizador's own search for ``query`` (at most twelve exams)."""
    try:
        async with asyncio.timeout(PRICE_DEADLINE_S):
            data = await _cached(COTIZADOR, {"handler": "Buscar", "q": query.strip()}, PRICE_TTL_S)
    except TimeoutError as e:
        raise LookupSlow(f"the price list took longer than {PRICE_DEADLINE_S:g} s") from e
    if not isinstance(data, list):
        raise LookupFailed("the price search did not answer with a list")
    return [p for raw in cast(list[Any], data) if (p := price_from(raw)) is not None]


def pesos(amount: int | None) -> str:
    """``88280`` as the site writes it, ``$88.280``."""
    return "sin precio publicado" if amount is None else "$" + f"{amount:,}".replace(",", ".")


def _short(text: str, most: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= most else text[: most - 1].rsplit(" ", 1)[0] + "…"


def price_line(p: Price) -> str:
    """One exam, compactly, for the model to say in words."""
    parts = [f"{p.nombre} — Fonasa {pesos(p.fonasa)} / particular {pesos(p.particular)}"]
    if p.servicio:
        parts.append(p.servicio)
    if p.contraste:
        parts.append("con contraste")
    if p.preparacion:
        parts.append(f"preparación: {_short(p.preparacion, 140)}")
    return "; ".join(parts)


# ─── Open hours ────────────────────────────────────────────────────────────────

_DAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def today() -> date:
    """Today in Santiago, where Clini's days are counted."""
    return datetime.now(TIMEZONE).date()


def day_es(day: date | str, *, now: date | None = None) -> str:
    """``2026-10-23`` as a Chilean says it: "viernes 23 de octubre", with
    "hoy" or "mañana" when it is."""
    d = date.fromisoformat(day) if isinstance(day, str) else day
    said = f"{_DAYS_ES[d.weekday()]} {d.day} de {_MONTHS_ES[d.month - 1]}"
    now = now or today()
    if d == now:
        return f"hoy, {said}"
    if (d - now).days == 1:
        return f"mañana, {said}"
    return said


@dataclass(frozen=True)
class Centre:
    """One centre's hours on one day, as the booking lists it."""

    nombre: str
    codigo: str = ""
    direccion: str = ""
    times: tuple[str, ...] = ()


@dataclass(frozen=True)
class Availability:
    days: tuple[str, ...]
    """The first days with hours, YYYY-MM-DD."""
    day: str | None = None
    """The day whose hours are in ``centres``."""
    centres: tuple[Centre, ...] = field(default_factory=tuple[Centre, ...])


def _params(servicio: int, prestacion: int, region: int | None) -> dict[str, str]:
    params = {"servicio": str(servicio), "prestacion": str(prestacion)}
    if region is not None:
        params["region"] = str(region)
        if servicio == _SECTOR_SERVICIO and region == _RM:
            params["sector"] = "TODOS"
    return params


def _answer(data: Any, what: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise LookupFailed(f"the booking's {what} did not answer with an object")
    body = cast(dict[str, Any], data)
    if body.get("exito") is False:
        raise LookupFailed(str(body.get("mensaje") or f"the booking refused the {what}"))
    return body


def _days_of(body: dict[str, Any]) -> list[dict[str, Any]]:
    raw = body.get("dias")
    if not isinstance(raw, list):
        return []
    return [cast(dict[str, Any], d) for d in cast(list[Any], raw) if isinstance(d, dict)]


@dataclass(frozen=True)
class _Window:
    """The days one availability answer covered, and which of them had hours."""

    until: float
    start: str
    end: str
    open: tuple[str, ...]


#: Each search's open days, by the search and not by the day it was asked
#: from: "is there one tomorrow?" after "when is the first one?" is the same
#: answer, read from the days already listed (dev call 2fd742d5, T25).
_days: dict[str, list[_Window]] = {}


def _known_days(key: str, since: str) -> list[str] | None:
    now = time.monotonic()
    windows = [w for w in _days.get(key, ()) if w.until > now]
    _days[key] = windows
    for w in windows:
        if w.start <= since <= w.end:
            return [d for d in w.open if d >= since]
    return None


def cached_days(
    servicio: int, prestacion: int, region: int | None, *, since: str | None = None
) -> list[str] | None:
    """The open days from ``since`` (else today) if an answer already covers
    them; ``None`` when only a lookup can say."""
    key = _cache_key("days", _params(servicio, prestacion, region))
    return _known_days(key, since or today().isoformat())


async def open_days(
    servicio: int, prestacion: int, region: int | None, *, since: str | None = None
) -> list[str]:
    """The days with at least one free hour, soonest first (about a month)."""
    base = _params(servicio, prestacion, region)
    key = _cache_key("days", base)
    now_day = today().isoformat()
    start = since if since and since > now_day else now_day
    if (known := _known_days(key, start)) is not None:
        return known
    params = base | {"buscarPrimera": "true"}
    if start != now_day:
        params["desde"] = start
    body = _answer(
        await _cached(AGENDA, {"handler": "Disponibilidad", **params}, AGENDA_TTL_S),
        "availability",
    )
    listed = [
        (str(d["fecha"])[:10], bool(d.get("tieneDisponibilidad")))
        for d in _days_of(body)
        if d.get("fecha")
    ]
    open_ = tuple(sorted(day for day, has in listed if has))
    end = max((day for day, _ in listed), default=start)
    _days.setdefault(key, []).append(_Window(time.monotonic() + AGENDA_TTL_S, start, end, open_))
    return [d for d in open_ if d >= start]


async def day_hours(
    servicio: int, prestacion: int, region: int | None, day: str, period: Period
) -> list[Centre]:
    """One half of ``day``'s free hours, by centre, in the booking's own order
    (``fase=prioritarios``: the centres it puts first)."""
    params = _params(servicio, prestacion, region) | {
        "fecha": day,
        "fase": "prioritarios",
        "periodo": period,
    }
    body = _answer(
        await _cached(AGENDA, {"handler": "HorariosDia", **params}, AGENDA_TTL_S), "hours"
    )
    out: list[Centre] = []
    for d in _days_of(body):
        for raw in cast(list[Any], d.get("centros") or []):
            if not isinstance(raw, dict):
                continue
            c = cast(dict[str, Any], raw)
            times = tuple(
                str(cast(dict[str, Any], h).get("hora") or "")[:5]
                for h in cast(list[Any], c.get("horarios") or [])
                if isinstance(h, dict) and cast(dict[str, Any], h).get("hora")
            )
            out.append(
                Centre(
                    nombre=str(c.get("nombre") or "").strip(),
                    codigo=str(c.get("codigo") or ""),
                    direccion=" ".join(str(c.get("direccion") or "").split()),
                    times=times,
                )
            )
    return [c for c in out if c.nombre]


_PERIODS: tuple[Period, Period] = ("AM", "PM")


def _both_halves(
    servicio: int, prestacion: int, region: int | None, day: str
) -> list[asyncio.Task[list[Centre]]]:
    """``day``'s morning and afternoon, asked together: the slower one is the
    wait, not the sum (on 2026-10-22 they took 2.3 s and 3.4 s, one after the
    other). Tasks, so one nobody waits for still finishes into the cache."""
    return [_spawn(day_hours(servicio, prestacion, region, day, p)) for p in _PERIODS]


async def availability(
    servicio: int,
    prestacion: int,
    region: int | None,
    day: str | None = None,
    *,
    deadline: float | None = None,
) -> Availability:
    """The first open days, and the hours of ``day`` (else the first open day)
    by centre, morning and afternoon together, within ``deadline`` seconds
    (:data:`AGENDA_DEADLINE_S` unless given).

    With nothing cached, the hours of the day it would choose (``day``, else
    today) are asked at the same time as the open days, so a laboratorio
    search that takes the booking 4 s is not waited for twice. Hours that miss
    the deadline are left out (``centres`` empty), not failed: the open days
    are the answer, and the hours land in the cache for the next ask. Open days
    that miss it are :class:`LookupFailed`."""
    deadline = AGENDA_DEADLINE_S if deadline is None else deadline
    loop = asyncio.get_running_loop()
    until = loop.time() + deadline
    guess = day or today().isoformat()
    known = cached_days(servicio, prestacion, region, since=day)
    early = _both_halves(servicio, prestacion, region, guess) if known is None else None
    try:
        async with asyncio.timeout_at(until):
            days = (
                known
                if known is not None
                else await open_days(servicio, prestacion, region, since=day)
            )
    except TimeoutError as e:
        raise LookupSlow(f"the booking took longer than {deadline:g} s") from e
    if not days:
        return Availability(days=())
    # A day with no hours left gives the next one that has some.
    chosen = day if day in days else days[0]
    halves = (
        early
        if early is not None and chosen == guess
        else _both_halves(servicio, prestacion, region, chosen)
    )
    done, late = await asyncio.wait(halves, timeout=max(0.0, until - loop.time()))
    if late:
        logger.warning(
            "clini: the hours of {} missed the {:g} s deadline; the open days answer",
            chosen,
            deadline,
        )
    centres: dict[str, Centre] = {}
    for period, half in zip(_PERIODS, halves, strict=True):
        if half not in done or half.cancelled():
            continue
        if (error := half.exception()) is not None:
            if not isinstance(error, LookupFailed):
                raise error
            logger.warning("clini: {} hours for {} failed: {}", period, chosen, error)
            continue
        for c in half.result():
            had = centres.get(c.nombre)
            centres[c.nombre] = (
                c
                if had is None
                else Centre(had.nombre, had.codigo, had.direccion, had.times + c.times)
            )
    ordered = tuple(
        Centre(c.nombre, c.codigo, c.direccion, tuple(sorted(set(c.times))))
        for c in centres.values()
    )
    return Availability(days=tuple(days), day=chosen, centres=ordered)


#: The searches being prefetched now, so a burst of reports starts one each.
_prefetching: set[str] = set()


def prefetch(servicio: int, prestacion: int, region: int | None) -> None:
    """Start, in the background, the lookup ``check_availability`` would make
    for this search: its open days and the hours of its first two. Never
    waits, never raises; what it finds is cached, and a question asked while it
    runs waits on the same requests rather than sending its own."""
    key = _cache_key("prefetch", _params(servicio, prestacion, region))
    if key in _prefetching:
        return
    _prefetching.add(key)

    async def run() -> None:
        try:
            found = await availability(servicio, prestacion, region, deadline=REQUEST_TIMEOUT_S)
            if len(found.days) > 1:
                await asyncio.wait(_both_halves(servicio, prestacion, region, found.days[1]))
        except LookupFailed as e:
            logger.info("clini: prefetch of servicio {} failed: {}", servicio, e)
        finally:
            _prefetching.discard(key)

    _spawn(run())


def prefetch_day(servicio: int, prestacion: int, region: int | None, day: str) -> None:
    """Start, in the background, ``day``'s hours for this search: the next
    open day after one just said, which is what the visitor asks for next."""
    _both_halves(servicio, prestacion, region, day)


__all__ = [
    "AGENDA",
    "COTIZADOR",
    "TIMEZONE",
    "Availability",
    "Centre",
    "LookupFailed",
    "LookupSlow",
    "Price",
    "availability",
    "cached_days",
    "clear_cache",
    "day_es",
    "day_hours",
    "open_days",
    "pesos",
    "prefetch",
    "prefetch_day",
    "price_from",
    "price_line",
    "search_prices",
    "today",
    "warm",
]
