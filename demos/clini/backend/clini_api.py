"""Clini's own public lookups, read server side: prices and open hours.

Two of Clini's hosts answer plain GETs with JSON, without a login or a cookie:

- the price quote, ``cotizador-web.clini.cl/Cotizar?handler=Buscar&q=…``: up to
  twelve exams by name, each with its Fonasa copago and its particular price,
  whether it needs contrast, and its preparation;
- the booking, ``agenda-web.clini.cl/?handler=Disponibilidad`` (which days have
  hours) and ``?handler=HorariosDia`` (a day's hours, by centre).

A page on www.clini.cl cannot read them (another origin, no CORS headers), so
the brain does, while the visitor waits for the answer: every call has a short
timeout and a small cache, and a failure is an exception the tool turns into a
plain sentence (the price falls back to the catalogue the crawl saved).

Only reads. The booking's ``AgendarCitaMedica`` (which books) and
``PacientePorDocumento`` (which looks a patient up by RUT) are never called from
here: a booking is the visitor's to press, and their RUT is theirs to type.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

import httpx
from loguru import logger

COTIZADOR = "https://cotizador-web.clini.cl/Cotizar"
AGENDA = "https://agenda-web.clini.cl/"
TIMEZONE = ZoneInfo("America/Santiago")

#: Seconds each host gets before the tool says it could not reach it: a visitor
#: is waiting, with only his nod in the air.
PRICE_TIMEOUT_S = 3.0
AGENDA_TIMEOUT_S = 4.0
#: Prices move rarely; open hours move as people book.
PRICE_TTL_S = 600.0
AGENDA_TTL_S = 60.0
_CACHE_MAX = 256

#: The servicio whose Región Metropolitana search also takes a sector
#: (laboratorio, ``#sector62Select``); the booking sends TODOS by default.
_SECTOR_SERVICIO = 62
_RM = 13

Period = Literal["AM", "PM"]


class LookupFailed(Exception):
    """A lookup that did not answer in time, or answered with an error."""


# ─── The wire ──────────────────────────────────────────────────────────────────

_cache: dict[str, tuple[float, Any]] = {}


def _cache_key(url: str, params: dict[str, str]) -> str:
    return url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))


async def _get_json(url: str, params: dict[str, str], timeout: float) -> Any:
    """One GET, its JSON decoded; :class:`LookupFailed` on anything else."""
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers={"Accept": "application/json"})
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as e:
        raise LookupFailed(f"{type(e).__name__}: {e}") from e


async def _cached(url: str, params: dict[str, str], timeout: float, ttl: float) -> Any:
    key = _cache_key(url, params)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    data = await _get_json(url, params, timeout)
    if len(_cache) >= _CACHE_MAX:
        for stale in [k for k, (until, _) in _cache.items() if until <= now] or list(_cache)[:32]:
            _cache.pop(stale, None)
    _cache[key] = (now + ttl, data)
    return data


def clear_cache() -> None:
    _cache.clear()


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
    data = await _cached(
        COTIZADOR, {"handler": "Buscar", "q": query.strip()}, PRICE_TIMEOUT_S, PRICE_TTL_S
    )
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


async def open_days(
    servicio: int, prestacion: int, region: int | None, *, since: str | None = None
) -> list[str]:
    """The days with at least one free hour, soonest first (about a month)."""
    params = _params(servicio, prestacion, region) | {"buscarPrimera": "true"}
    if since:
        params["desde"] = since
    body = _answer(
        await _cached(
            AGENDA, {"handler": "Disponibilidad", **params}, AGENDA_TIMEOUT_S, AGENDA_TTL_S
        ),
        "availability",
    )
    return [
        str(d["fecha"])[:10]
        for d in _days_of(body)
        if d.get("tieneDisponibilidad") and d.get("fecha")
    ]


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
        await _cached(AGENDA, {"handler": "HorariosDia", **params}, AGENDA_TIMEOUT_S, AGENDA_TTL_S),
        "hours",
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


async def availability(
    servicio: int, prestacion: int, region: int | None, day: str | None = None
) -> Availability:
    """The first open days, and the hours of ``day`` (else the first open day)
    by centre, morning and afternoon together."""
    days = await open_days(servicio, prestacion, region, since=day)
    if not days:
        return Availability(days=())
    # A day with no hours left gives the next one that has some.
    chosen = day if day in days else days[0]
    centres: dict[str, Centre] = {}
    # The morning and the afternoon are two requests of their own: asked
    # together, the slower one is the wait, not the sum (on 2026-10-22 they
    # took 2.3 s and 3.4 s, one after the other).
    periods = ("AM", "PM")
    halves = await asyncio.gather(
        *(day_hours(servicio, prestacion, region, chosen, p) for p in periods),
        return_exceptions=True,
    )
    for period, half in zip(periods, halves, strict=True):
        if isinstance(half, BaseException):
            if not isinstance(half, LookupFailed):
                raise half
            logger.warning("clini: {} hours for {} failed: {}", period, chosen, half)
            continue
        for c in half:
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


__all__ = [
    "AGENDA",
    "COTIZADOR",
    "TIMEZONE",
    "Availability",
    "Centre",
    "LookupFailed",
    "Price",
    "availability",
    "clear_cache",
    "day_es",
    "day_hours",
    "open_days",
    "pesos",
    "price_from",
    "price_line",
    "search_prices",
    "today",
]
