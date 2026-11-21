"""Seeded random streams for the theatre (docs/strategy.md section 7).

Every source of chance draws from its own named stream, derived from the run seed. Changing the
defensive policy therefore leaves the dice of the world (physics, field, digital, adversary)
untouched, so policies are compared under the same luck. A run without a seed gets a fresh random
one, recorded in its recipe, so every run differs and any run can still be replayed.
"""

from __future__ import annotations

import hashlib
import random
import secrets


def rng_for(seed: int, name: str) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{name}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def new_seed() -> int:
    return secrets.randbits(53)  # fits a JSON number without loss
