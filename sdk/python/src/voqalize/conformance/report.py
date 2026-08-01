"""Run the scenario catalog against a brain and collect a pass/fail report.

This is the top-level entry the pytest suite and the CLI both call. Each scenario
runs against its own :class:`~voqalize.conformance.scenarios.ScenarioContext`
(fresh sessions, torn down after), so one failing scenario never leaks state into
the next. A scenario passes iff it returns without raising; the raised
:class:`~voqalize.conformance.checks.ConformanceError` (or any exception)
message is captured verbatim as the failure reason.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field

from .scenarios import CATALOG, Scenario, ScenarioContext


@dataclass
class ScenarioResult:
    name: str
    description: str
    passed: bool
    duration_s: float
    error: str | None = None
    traceback: str | None = None


@dataclass
class Report:
    results: list[ScenarioResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def summary(self) -> str:
        lines = []
        for r in self.results:
            mark = "PASS" if r.passed else "FAIL"
            lines.append(f"  [{mark}] {r.name:<28} ({r.duration_s * 1000:.0f} ms)")
            if not r.passed and r.error:
                lines.append(f"         → {r.error}")
        verdict = "CONFORMANT" if self.ok else "NON-CONFORMANT"
        lines.append("")
        lines.append(f"  {self.passed} passed, {self.failed} failed — {verdict}")
        return "\n".join(lines)


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


async def run_suite(
    brain_url: str,
    *,
    private_key_pem: bytes | None,
    include_reference: bool = True,
    include_auth: bool = True,
    only: list[str] | None = None,
    default_timeout: float = 5.0,
    agent_id: str = "agent_conformance",
    tenant_id: str = "tenant_conformance",
) -> Report:
    """Run the catalog against ``brain_url`` and return a :class:`Report`.

    ``private_key_pem`` signs the pygato token the driver presents (``None`` ⇒ no
    auth header, for a brain running ``allow_unverified``). ``include_reference``
    keeps the deep-semantics scenarios that need a cooperating brain;
    ``include_auth`` keeps the auth-rejection scenarios (skip them when the brain
    runs unverified — they can't pass without token enforcement); ``only``
    restricts to named scenarios."""
    report = Report()
    for scenario in CATALOG:
        if only is not None and scenario.name not in only:
            continue
        if scenario.requires_reference and not include_reference:
            continue
        if "auth" in scenario.tags and not include_auth:
            continue
        ctx = ScenarioContext(
            brain_url,
            private_key_pem=private_key_pem,
            agent_id=agent_id,
            tenant_id=tenant_id,
            default_timeout=default_timeout,
        )
        report.results.append(await run_scenario(scenario, ctx))
    return report
