"""Resource ledger: field crews, backup comms kits, fast reserve, battery MW, and the attention pools
that refill every cycle (analysts, operators). Attention models saturation."""

from __future__ import annotations

from dataclasses import dataclass, field

PER_CYCLE = frozenset({"analyst_attention", "operator_attention"})


@dataclass
class Reservation:
    action_key: str
    pool: str
    amount: float
    release: int | None  # cycle at which it is released; None = held until released explicitly


@dataclass
class Ledger:
    capacity: dict[str, float]
    reservations: list[Reservation] = field(default_factory=list)
    used_this_cycle: dict[str, float] = field(default_factory=dict)

    def available(self, pool: str) -> float:
        held = sum(r.amount for r in self.reservations if r.pool == pool)
        return self.capacity.get(pool, 0.0) - held - self.used_this_cycle.get(pool, 0.0)

    def can_afford(self, costs: dict[str, float], keep: float = 0.0) -> bool:
        """True when every cost fits, leaving `keep` (share of capacity) untouched for the
        durable pools."""
        for pool, amount in costs.items():
            reserve = 0.0 if pool in PER_CYCLE else keep * self.capacity.get(pool, 0.0)
            if amount > self.available(pool) - reserve + 1e-9:
                return False
        return True

    def spend(self, costs: dict[str, float], action_key: str, release: int | None) -> None:
        for pool, amount in costs.items():
            if amount <= 0:
                continue
            if pool in PER_CYCLE:
                self.used_this_cycle[pool] = self.used_this_cycle.get(pool, 0.0) + amount
            else:
                self.reservations.append(Reservation(action_key, pool, amount, release))

    def release(self, action_key: str) -> None:
        self.reservations = [r for r in self.reservations if r.action_key != action_key]

    def new_cycle(self, cycle: int) -> None:
        self.used_this_cycle = {}
        self.reservations = [r for r in self.reservations if r.release is None or r.release > cycle]

    def remaining_fraction(self) -> float:
        pools = [p for p in self.capacity if p not in PER_CYCLE and self.capacity[p] > 0]
        if not pools:
            return 1.0
        return sum(max(0.0, self.available(p)) / self.capacity[p] for p in pools) / len(pools)

    def snapshot(self) -> dict[str, dict[str, float]]:
        return {
            p: {"capacity": c, "available": round(self.available(p), 2)} for p, c in self.capacity.items()
        }
