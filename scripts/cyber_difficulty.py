"""Win rate of each defender on each Ciberataque difficulty preset (docs/attack-sim.md 3.2).

Why: the presets in theater.yaml (cyber_attack_presets) quote measured outcomes; this script measures them again.
Usage: cd backend && uv run python ../scripts/cyber_difficulty.py [- | PRESETS_JSON] [N=100] [POLICIES=ABC] [FIRST_SEED=1]
"-" uses the presets of theater.yaml; a JSON object {name: params} tries other values. Needs data/processed.
"""

import json
import statistics
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from cascadasen.application.theater_world import default_world
from cascadasen.domain.theater.config import theater_config
from cascadasen.domain.theater.cycle import AdversaryConfig, RunConfig, Simulation
from cascadasen.infrastructure.settings import Settings

_W = None


def one(args):
    global _W
    params, pol, seed = args
    if _W is None:
        _W = default_world(str(Settings().processed_dir))
    adv = AdversaryConfig(enabled=True, mode="propagation", adaptive=False, budget=0, propagation=params)
    s = Simulation(_W, RunConfig(template="ciberataque", seed=seed, policy=pol, adversary=adv), light=True)
    s.run_to_end()
    r = s.report()["cyber_attack"]
    return r["outcome"], s.cycle


if __name__ == "__main__":
    presets = (
        json.loads(sys.argv[1])
        if len(sys.argv) > 1 and sys.argv[1] != "-"
        else {k: v["params"] for k, v in theater_config().cyber_attack_presets.items()}
    )
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    pols = sys.argv[3] if len(sys.argv) > 3 else "ABC"
    first = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    jobs = [(presets[k], pol, seed) for k in presets for pol in pols for seed in range(first, first + n)]
    with ProcessPoolExecutor() as ex:
        res = list(ex.map(one, jobs, chunksize=4))
    i = 0
    for k in presets:
        for pol in pols:
            rows = res[i : i + n]
            i += n
            c = Counter(o for o, _ in rows)
            win = [cy for o, cy in rows if o == "defense"]
            pc = {k: round(100 * c[k] / n) for k in ("defense", "attack", "undecided")}
            print(
                f"{k:8} {pol}  defensa {pc['defense']:3}%  ataque {pc['attack']:3}%  sin definir {pc['undecided']:3}%  ciclos a ganar {statistics.median(win) if win else '-'}"
            )
