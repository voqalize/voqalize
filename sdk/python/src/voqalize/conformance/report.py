"""Run the scenario catalog against a brain and collect a report.

This is the top-level entry the pytest suite and the CLI both call. Each scenario
runs against its own :class:`~voqalize.conformance.scenarios.ScenarioContext`
(fresh sessions, torn down after), so one failing scenario never leaks state into
the next. A scenario passes iff it returns without raising; the raised
:class:`~voqalize.conformance.checks.ConformanceError` (or any exception)
message is captured verbatim as the failure reason.

**A scenario that could not apply is skipped, and the skip is in the report.**
Two-thirds of the catalog needs the reference *command grammar* — a brain that
answers ``say banana`` by speaking "banana" (see :mod:`.reference`). Pointed at an
ordinary brain those scenarios used to fail, so a perfectly conformant brain was
told it was NON-CONFORMANT for not knowing a vocabulary it was never supposed to
know; running with ``--no-reference`` instead dropped them from the report
entirely and printed a bare CONFORMANT over a quarter of the catalog. Both
answers were wrong in the same way — the verdict didn't say what it had tested.
The suite now *probes* for the grammar and skips what cannot apply, with the
reason attached, and the verdict states its own coverage.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field

from .scenarios import CATALOG, Scenario, ScenarioContext

# The probe: a brain that speaks the reference grammar answers `say <text>` by
# speaking exactly `<text>`. Unambiguous, one short session, and it tests the
# thing the deep-semantics scenarios actually depend on.
_PROBE_WORD = "conformance-probe"

_NO_GRAMMAR = (
    "needs the reference command grammar — this brain answered the probe with "
    "its own words, which is what any real brain does"
)
_GRAMMAR_OFF = "needs the reference command grammar (--no-reference)"
_AUTH_OFF = "needs token verification (--no-auth)"


@dataclass
class ScenarioResult:
    name: str
    description: str
    passed: bool
    duration_s: float
    error: str | None = None
    traceback: str | None = None
    # A scenario that never ran because it could not apply. Neither a pass nor a
    # failure — and recorded rather than dropped, because a catalog that quietly
    # shrinks is how a partial run comes to read as a full one.
    skipped: bool = False
    skip_reason: str | None = None


@dataclass
class Report:
    results: list[ScenarioResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """No scenario failed. Skips do not make a run unconformant — but they do
        bound what it proved, which is what :meth:`summary` says out loud."""
        return self.failed == 0

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed and not r.skipped)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed and not r.skipped)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.skipped)

    def summary(self) -> str:
        lines = []
        for r in self.results:
            mark = "SKIP" if r.skipped else ("PASS" if r.passed else "FAIL")
            suffix = "" if r.skipped else f" ({r.duration_s * 1000:.0f} ms)"
            lines.append(f"  [{mark}] {r.name:<28}{suffix}".rstrip())
            if not r.skipped and not r.passed and r.error:
                lines.append(f"         → {r.error}")

        # Skip reasons are shared by whole tiers, so they go in a footer: printed
        # per row, one reason repeated a dozen times buries the failures above it.
        reasons: dict[str, int] = {}
        for r in self.results:
            if r.skipped and r.skip_reason:
                reasons[r.skip_reason] = reasons.get(r.skip_reason, 0) + 1
        if reasons:
            lines.append("")
            for reason, count in reasons.items():
                lines.append(f"  {count} skipped: {reason}")

        lines.append("")
        counts = f"{self.passed} passed, {self.failed} failed"
        if self.skipped:
            counts += f", {self.skipped} skipped"
        if not self.ok:
            lines.append(f"  {counts} — NON-CONFORMANT")
        elif self.skipped:
            total = len(self.results)
            # Never a bare CONFORMANT over a partial catalog: the developer quotes
            # this line, and it has to carry its own caveat when it has one.
            lines.append(
                f"  {counts} — CONFORMANT on what ran "
                f"({self.passed} of {total} scenarios; see the skips above)"
            )
        else:
            lines.append(f"  {counts} — CONFORMANT")
        return "\n".join(lines)


def _skipped(scenario: Scenario, reason: str) -> ScenarioResult:
    return ScenarioResult(
        name=scenario.name,
        description=scenario.description,
        passed=False,
        duration_s=0.0,
        skipped=True,
        skip_reason=reason,
    )


async def run_scenario(scenario: Scenario, ctx: ScenarioContext) -> ScenarioResult:
    start = time.perf_counter()
    try:
        await scenario.run(ctx)
    except Exception as exc:
        return ScenarioResult(
            name=scenario.name,
            description=scenario.description,
            passed=False,
            duration_s=time.perf_counter() - start,
            error=f"{type(exc).__name__}: {exc}",
            traceback=traceback.format_exc(),
        )
    finally:
        await ctx.aclose()
    return ScenarioResult(
        name=scenario.name,
        description=scenario.description,
        passed=True,
        duration_s=time.perf_counter() - start,
    )


async def speaks_reference_grammar(ctx: ScenarioContext, *, timeout: float = 5.0) -> bool:
    """Does this brain speak the reference command grammar?

    One session: greet, then ``say <probe>``. The reference brain speaks the probe
    word back verbatim; every other brain answers in its own words, or not at all.
    Any failure at all reads as "no" — the probe exists to *avoid* accusing a brain
    of anything, so it never turns a connection problem into a verdict (the wire
    scenarios run either way, and they will report it properly).
    """
    from .reference import SAY_PREFIX

    try:
        driver = await ctx.connect()
        await driver.start_session()
        turn = await driver.user_says(f"{SAY_PREFIX}{_PROBE_WORD}", timeout=timeout)
    except Exception:
        return False
    return turn.text.strip() == _PROBE_WORD


async def run_suite(
    brain_url: str,
    *,
    private_key_pem: bytes | None,
    include_reference: bool | None = None,
    include_auth: bool = True,
    only: list[str] | None = None,
    default_timeout: float = 5.0,
    agent_id: str = "agent_conformance",
    tenant_id: str = "tenant_conformance",
) -> Report:
    """Run the catalog against ``brain_url`` and return a :class:`Report`.

    ``private_key_pem`` signs the pygato token the driver presents (``None`` ⇒ no
    auth header, for a brain running ``allow_unverified``).

    ``include_reference`` decides the deep-semantics tier: ``None`` (the default)
    **probes** the brain for the reference command grammar and skips that tier if
    it doesn't speak it; ``True`` forces it on, ``False`` forces it off. Auto is
    the default because getting it wrong was never the developer's mistake to
    make — leaving the tier on produced a page of failures a conformant brain
    could not fix, and turning it off produced a green run that had tested a
    quarter of the catalog without saying so.

    ``include_auth`` keeps the auth-rejection scenarios (skip them when the brain
    runs unverified — they can't pass without token enforcement); ``only``
    restricts to named scenarios.
    """

    def _ctx() -> ScenarioContext:
        return ScenarioContext(
            brain_url,
            private_key_pem=private_key_pem,
            agent_id=agent_id,
            tenant_id=tenant_id,
            default_timeout=default_timeout,
        )

    selected = [s for s in CATALOG if only is None or s.name in only]
    reference_reason = _GRAMMAR_OFF

    if include_reference is None:
        if any(s.requires_reference for s in selected):
            probe = _ctx()
            try:
                include_reference = await speaks_reference_grammar(probe, timeout=default_timeout)
            finally:
                await probe.aclose()
            if not include_reference:
                reference_reason = _NO_GRAMMAR
        else:
            include_reference = False

    report = Report()
    for scenario in selected:
        if scenario.requires_reference and not include_reference:
            report.results.append(_skipped(scenario, reference_reason))
            continue
        if "auth" in scenario.tags and not include_auth:
            report.results.append(_skipped(scenario, _AUTH_OFF))
            continue
        report.results.append(await run_scenario(scenario, _ctx()))
    return report
