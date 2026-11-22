"""What an agent receives each cycle. Views hold observed state, messages and summaries only:
never `RealState`, `GridState` or true digital health (checked by a test)."""

from __future__ import annotations

from dataclasses import dataclass

from cascadasen.domain.theater.config import Mission, Policy
from cascadasen.domain.theater.decisions import ActionFeedback, FieldReport, Intent, ISRReport
from cascadasen.domain.theater.state import ObservedState


@dataclass(frozen=True)
class AgentView:
    role: str
    cycle: int
    observed: ObservedState
    history: tuple[ObservedState, ...]
    mission: Mission
    policy: Policy
    isr: ISRReport | None = None
    intent: Intent | None = None
    resources: tuple[tuple[str, float], ...] = ()
    field_reports: tuple[FieldReport, ...] = ()
    feedback: tuple[ActionFeedback, ...] = ()
    active: tuple[str, ...] = ()
    crew_eta: tuple[tuple[str, int], ...] = ()  # (area, cycles until the nearest free crew is there)
    containment: bool = False  # the run is a propagating-intrusion drill: contain what looks compromised

    def available(self, pool: str) -> float:
        return dict(self.resources).get(pool, 0.0)

    def outages(self) -> list[str]:
        """Areas where supervision shows lost load (only where values are visible)."""
        out = []
        for a in self.observed.areas:
            if a.energized is False or (a.served_mw is not None and a.served_mw < 0.95 * a.load_mw - 1.0):
                out.append(a.area)
        return out


@dataclass(frozen=True)
class AdversaryView:
    """What the adversary can see: the defence's visible posture, its own effects, public impact."""

    cycle: int
    budget_left: float
    posture: tuple[tuple[str, str], ...]  # (area, "normal" | "manual" | "segmented")
    my_effects: tuple[
        tuple[str, str, str, bool, int, int | None], ...
    ]  # (id, event, area, established, start, cleared)
    public_served_share: float
    public_dark_areas: tuple[str, ...]
