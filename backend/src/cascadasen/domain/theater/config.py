"""Typed access to `theater/params/*.yaml`: clock, resources, digital engine, effects, actions,
restoration, ISR, policies, adversary, missions and experiment templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from cascadasen.domain.simulation.params import Provenance, collect_provenance, load_params, value

THEATER_DIR = Path(__file__).parent / "params"


class UnknownTemplateError(KeyError):
    pass


@dataclass(frozen=True)
class Policy:
    id: str
    label_key: str
    light: float
    medium: float
    heavy: float
    preventive: bool
    reserve_keep: float
    prefer_reversible: bool
    verify_first: bool

    def threshold(self, weight: str) -> float:
        return {"light": self.light, "medium": self.medium, "heavy": self.heavy}.get(weight, 0.0)


@dataclass(frozen=True)
class Mission:
    id: str
    label_key: str
    priority_areas: tuple[str, ...]
    continuity_threshold: float
    priority_threshold: float
    observability_threshold: float
    worst_acceptable_level: str


@dataclass(frozen=True)
class Template:
    id: str
    label_key: str
    question_key: str
    operating_point: str
    mission: str
    horizon: int
    adversary: dict[str, Any]
    scenario_events: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class TheaterConfig:
    clock: dict[str, int]
    resources: dict[str, float]
    digital: dict[str, float]
    effects: dict[str, dict[str, Any]]
    actions: dict[str, dict[str, Any]]
    restoration: dict[str, float]
    isr: dict[str, float]
    policies: dict[str, Policy]
    adversary: dict[str, Any]
    missions: dict[str, Mission]
    templates: dict[str, Template]
    stochastic: dict[str, Any] = field(default_factory=dict)
    crews: dict[str, Any] = field(default_factory=dict)
    physics_alarms: dict[str, float] = field(default_factory=dict)
    provenance: tuple[Provenance, ...] = field(default=())

    def template(self, template_id: str) -> Template:
        if template_id not in self.templates:
            raise UnknownTemplateError(template_id)
        return self.templates[template_id]


@cache
def theater_config() -> TheaterConfig:
    p = load_params("theater", THEATER_DIR)
    t = load_params("templates", THEATER_DIR)
    v = {k: value(p[k], k) for k in p if k != "version"}
    policies = {pid: Policy(id=pid, **spec) for pid, spec in v["policies"].items()}
    missions = {
        mid: Mission(
            id=mid,
            label_key=m["label_key"],
            priority_areas=tuple(m["priority_areas"]),
            continuity_threshold=float(m["continuity_threshold"]),
            priority_threshold=float(m["priority_threshold"]),
            observability_threshold=float(m["observability_threshold"]),
            worst_acceptable_level=m["worst_acceptable_level"],
        )
        for mid, m in v["missions"].items()
    }
    templates = {
        tid: Template(
            id=tid,
            label_key=spec["label_key"],
            question_key=spec["question_key"],
            operating_point=spec["operating_point"],
            mission=spec["mission"],
            horizon=int(spec["horizon"]),
            adversary=dict(spec.get("adversary") or {}),
            scenario_events=tuple(spec.get("scenario_events") or ()),
        )
        for tid, spec in value(t["templates"]).items()
    }
    return TheaterConfig(
        clock={k: int(x) for k, x in v["clock"].items()},
        resources={k: float(x) for k, x in v["resources"].items()},
        # the digital engine also reads the physical alarm thresholds (docs/agents.md 1.2)
        digital={k: float(x) for k, x in {**v["digital"], **v.get("physics_alarms", {})}.items()},
        effects=v["effects"],
        actions=v["actions"],
        restoration={k: float(x) for k, x in v["restoration"].items()},
        isr={k: float(x) for k, x in v["isr"].items()},
        policies=policies,
        adversary=v["adversary"],
        missions=missions,
        templates=templates,
        stochastic=v.get("stochastic", {}),
        crews=v.get("crews", {}),
        physics_alarms={k: float(x) for k, x in v.get("physics_alarms", {}).items()},
        provenance=tuple(collect_provenance(p, "theater") + collect_provenance(t, "templates")),
    )
