#!/usr/bin/env python3
"""
Baseline comparison: exact MIP vs. simpler, deterministic selection strategies
a committee could use without Garante. No LLM, no API key, no MongoDB: runs
offline on the de-identified demo_bundle.json used by the LLM ablation.

Strategies (all on the same h_min-eligible pool, N = 6):
  top_E        rank by E_i, take the top N, ignore constraints (score-only ranking)
  top_h        rank by h-index, take the top N (traditional bibliometric shortlist)
  greedy_E     add candidates in E_i order, skipping any that would make the
               remaining slots unable to meet the parity / EU / area minima
  random       uniform random feasible teams (rejection sampling), uninformed floor
  mip          Garante's exact optimiser (alpha=0.95, beta=0.05 as in the paper)

Usage:  python experiments/heuristic_baselines.py
Output: experiments/results_heuristic_baselines.json (+ printed table)
"""
import sys, json, math, random, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "optimizer"))

import numpy as np
import config as cfg
from mip_garantes import run_mip

BUNDLE = ROOT / "experiments" / "demo_bundle.json"
N = 6
MIN_PARIDAD = 0.4
MIN_AREAS = cfg.MIN_AREAS_DEFAULT
MIN_W = math.ceil(MIN_PARIDAD * N)
MAX_W = N - MIN_W
ALPHA, BETA = 0.95, 0.05  # paper defaults (config may differ)
RANDOM_SAMPLES = 1000
SEED = 42
MODALITIES = [  # (bundle key, run_mip modality, h_min, eu_min)
    ("SO",  "SO",  cfg.H_MIN_SO,  cfg.EU_MIN_SO),
    ("MdM", "MdM", cfg.H_MIN_MDM, cfg.EU_MIN_MDM),
    ("UEI", "UEI", cfg.H_MIN_UEI, cfg.EU_MIN_UEI),
]


def load_pool(key, h_min):
    b = json.loads(BUNDLE.read_text())["modalities"][key]
    raw_all, E_all, K_all = b["raw"], np.array(b["E"]), np.array(b["K"])
    pool = [i for i in range(len(raw_all)) if raw_all[i]["h_index"] >= h_min]
    return [raw_all[i] for i in pool], E_all[pool], K_all[np.ix_(pool, pool)]


def is_w(r):
    return r["genero"] == "Mujer"


def has_eu(r):
    return (r.get("proyectos_eu") or 0) > 0


def check(team, raw, eu_min, n=N, min_areas=MIN_AREAS):
    min_w = math.ceil(MIN_PARIDAD * n)
    w = sum(is_w(raw[i]) for i in team)
    c = {"parity": min_w <= w <= n - min_w,
         "eu": sum(has_eu(raw[i]) for i in team) >= eu_min,
         "areas": len({raw[i]["area"] for i in team if raw[i]["area"]}) >= min_areas}
    c["feasible"] = len(set(team)) == n and all(c.values())
    return c


def greedy(raw, E, eu_min, n=N, min_areas=MIN_AREAS):
    min_w = math.ceil(MIN_PARIDAD * n)
    team = []
    for i in sorted(range(len(raw)), key=lambda i: -E[i]):
        t = team + [i]
        left = n - len(t)
        w = sum(is_w(raw[j]) for j in t)
        m = len(t) - w
        need_w, need_m = max(0, min_w - w), max(0, min_w - m)
        need_eu = max(0, eu_min - sum(has_eu(raw[j]) for j in t))
        need_a = max(0, min_areas - len({raw[j]["area"] for j in t if raw[j]["area"]}))
        # ponytail: necessary-condition look-ahead, not exact; final team is re-checked
        if need_w + need_m <= left and need_eu <= left and need_a <= left:
            team = t
        if len(team) == n:
            break
    return team


def stress(key, mod, h_min, raw, E, Kmat):
    """Greedy vs. MIP on pure excellence (alpha=1, beta=0, penalties and area bonus
    zeroed) over a grid of call settings."""
    saved = {k: getattr(cfg, k) for k in ("PENALTY_ISOLATED", "PENALTY_DECLINING",
                                          "AREA_DIVERSITY_BONUS") if hasattr(cfg, k)}
    for k in saved:
        setattr(cfg, k, 0.0)
    rows = []
    for n in (4, 6, 8, 10):
        for min_areas in range(2, 6):
            for eu_min in range(0, n // 2 + 2):
                sel, _ = run_mip(raw, E, Kmat, n, min_areas=min_areas, min_paridad=MIN_PARIDAD,
                                 modalidad=mod, h_min=h_min, eu_min=eu_min, alpha=1.0, beta=0.0)
                if sel is None or not check(sel, raw, eu_min, n, min_areas)["feasible"]:
                    continue  # infeasible instance (or constraint relaxed by run_mip): skip
                g = greedy(raw, E, eu_min, n, min_areas)
                ok = len(g) == n and check(g, raw, eu_min, n, min_areas)["feasible"]
                mip_exc = float(sum(E[i] for i in sel))
                gap = (mip_exc - float(sum(E[i] for i in g))) / mip_exc if ok else None
                rows.append({"N": n, "min_areas": min_areas, "eu_min": eu_min,
                             "greedy_feasible": ok, "greedy_gap": gap})
    for k, v in saved.items():
        setattr(cfg, k, v)
    return rows


def random_feasible(raw, eu_min, rng):
    teams, idx = [], list(range(len(raw)))
    for _ in range(RANDOM_SAMPLES * 200):
        t = rng.sample(idx, N)
        if check(t, raw, eu_min)["feasible"]:
            teams.append(t)
            if len(teams) == RANDOM_SAMPLES:
                break
    return teams


def score(team, sel, raw, E, Kmat, eu_min, mip_exc):
    exc = float(sum(E[i] for i in team))
    coh = float(sum(Kmat[i][j] for a, i in enumerate(team) for j in team[a + 1:]))
    return {"team": [int(i) for i in team], "excellence": exc, "cohesion": coh,
            "opt_gap": (mip_exc - exc) / mip_exc,
            "jaccard": len(set(team) & set(sel)) / len(set(team) | set(sel)),
            "checks": check(team, raw, eu_min)}


def main():
    rng = random.Random(SEED)
    out = {"N": N, "alpha": ALPHA, "beta": BETA, "random_samples": RANDOM_SAMPLES,
           "seed": SEED, "modalities": {}}
    print(f"{'call':4} {'strategy':9} {'gap%':>7} {'Jacc':>5} {'cohes':>6}  feasible / violated")
    for key, mod, h_min, eu_min in MODALITIES:
        raw, E, Kmat = load_pool(key, h_min)
        sel, _ = run_mip(raw, E, Kmat, N, min_areas=MIN_AREAS, min_paridad=MIN_PARIDAD,
                         modalidad=mod, h_min=h_min, eu_min=eu_min, alpha=ALPHA, beta=BETA)
        mip_exc = float(sum(E[i] for i in sel))
        res = {
            "mip": score(sel, sel, raw, E, Kmat, eu_min, mip_exc),
            "top_E": score(sorted(range(len(raw)), key=lambda i: -E[i])[:N],
                           sel, raw, E, Kmat, eu_min, mip_exc),
            "top_h": score(sorted(range(len(raw)), key=lambda i: (-raw[i]["h_index"], -E[i]))[:N],
                           sel, raw, E, Kmat, eu_min, mip_exc),
            "greedy_E": score(greedy(raw, E, eu_min), sel, raw, E, Kmat, eu_min, mip_exc),
        }
        rs = [score(t, sel, raw, E, Kmat, eu_min, mip_exc) for t in random_feasible(raw, eu_min, rng)]
        res["random"] = {
            "samples": len(rs),
            **{k: {"mean": statistics.mean(r[k] for r in rs), "std": statistics.pstdev(r[k] for r in rs)}
               for k in ("opt_gap", "jaccard", "cohesion")},
            "share_reaching_mip": sum(r["opt_gap"] <= 1e-9 for r in rs) / len(rs),
        }
        st = stress(key, mod, h_min, raw, E, Kmat)
        out["modalities"][key] = {"pool_size": len(raw), "h_min": h_min, "eu_min": eu_min,
                                  "mip_excellence": mip_exc, "strategies": res, "stress": st}
        for name in ("mip", "top_E", "top_h", "greedy_E"):
            r = res[name]
            bad = [c for c in ("parity", "eu", "areas") if not r["checks"][c]]
            print(f"{key:4} {name:9} {r['opt_gap']*100:+7.1f} {r['jaccard']:5.2f} {r['cohesion']:6.2f}  "
                  f"{'yes' if r['checks']['feasible'] else 'NO':3} {','.join(bad)}")
        r = res["random"]
        print(f"{key:4} {'random':9} {r['opt_gap']['mean']*100:+7.1f} {r['jaccard']['mean']:5.2f} "
              f"{r['cohesion']['mean']:6.2f}  yes (by construction, n={r['samples']})")

    print("\nStress grid (greedy_E vs MIP, pure excellence; feasible instances only)")
    for key, m in out["modalities"].items():
        st = m["stress"]
        inf = sum(not r["greedy_feasible"] for r in st)
        g = [r["greedy_gap"] for r in st if r["greedy_feasible"]]
        sub = [x for x in g if x > 1e-9]
        print(f"{key:4} instances {len(st):3} | greedy infeasible {inf:3} | suboptimal {len(sub):3}"
              f" | equal {sum(abs(x) <= 1e-9 for x in g):3} | above MIP {sum(x < -1e-9 for x in g):3}"
              + (f" (max gap {max(sub)*100:.1f}%)" if sub else ""))

    path = ROOT / "experiments" / "results_heuristic_baselines.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
