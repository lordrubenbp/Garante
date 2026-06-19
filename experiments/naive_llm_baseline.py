#!/usr/bin/env python3
"""
Ablation: exact MIP optimiser vs. a naive LLM asked to select the guarantor team
directly. Honest AI-vs-AI design — NO human experts are involved or simulated.

Question: if you replaced the exact-optimisation layer with an LLM (i.e. "just ask
the model to pick the team"), would it honour the call's hard eligibility
constraints and reach the optimal excellence? We hand the LLM the SAME excellence
scores E_i the MIP uses plus the constraint-relevant attributes, and ask it to
optimise the selection. The MIP satisfies every constraint by construction and is
provably optimal; the LLM is run K times per modality and measured against it.

Runs on the anonymised DEMO_claude database (pseudonymised mirror; identical
structure to production), so the experiment ships and reproduces without exposing
personal data.

Usage:
    cd Garante && python experiments/naive_llm_baseline.py
Outputs: experiments/results_naive_llm.json  (+ a printed summary table)
"""
import sys, os, json, re, math, time, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "optimizer"))

# minimal .env loader (key=value)
for line in (ROOT / ".env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import numpy as np
from pymongo import MongoClient
import anthropic
import config as cfg
from mip_garantes import compute_E, compute_K, run_mip

DB = os.environ.get("EXPERIMENT_DB", "DEMO_claude")
BUNDLE = ROOT / "experiments" / "demo_bundle.json"
N = 6
K_RUNS = 10
TEMPERATURE = 0.7
MIN_PARIDAD = 0.4
MIN_AREAS = cfg.MIN_AREAS_DEFAULT
MIN_W = math.ceil(MIN_PARIDAD * N)
MAX_W = N - MIN_W
MODALITIES = [
    ("SO",  cfg.H_MIN_SO,  cfg.EU_MIN_SO),
    ("MdM", cfg.H_MIN_MDM, cfg.EU_MIN_MDM),
    ("UEI", cfg.H_MIN_UEI, cfg.EU_MIN_UEI),
]


def load_pool(modalidad, h_min):
    """Return (raw, E, Kmat) for the h_min-eligible pool.
    Prefers the offline de-identified bundle; falls back to MongoDB."""
    if BUNDLE.exists():
        b = json.loads(BUNDLE.read_text())["modalities"][modalidad]
        raw_all, E_all, K_all = b["raw"], np.array(b["E"]), np.array(b["K"])
    else:
        docs = list(MongoClient(cfg.MONGO_URI, serverSelectionTimeoutMS=8000)[DB]["investigadores"].find())
        E_all, raw_all = compute_E(docs, modalidad=modalidad)
        K_all = compute_K(raw_all, docs)
    pool = [i for i in range(len(raw_all)) if raw_all[i]["h_index"] >= h_min]
    raw = [raw_all[i] for i in pool]
    E = np.array([E_all[i] for i in pool])
    Kmat = K_all[np.ix_(pool, pool)]
    return raw, E, Kmat


def check(team, raw, h_min, eu_min):
    areas = len({raw[i]["area"] for i in team if raw[i]["area"]})
    eu = sum(1 for i in team if (raw[i].get("proyectos_eu") or 0) > 0)
    women = sum(1 for i in team if raw[i]["genero"] == "Mujer")
    hmin_ok = all(raw[i]["h_index"] >= h_min for i in team)
    return {
        "size_ok": len(set(team)) == N,
        "areas": areas, "areas_ok": areas >= MIN_AREAS,
        "eu": eu, "eu_ok": eu >= eu_min,
        "women": women, "parity_ok": MIN_W <= women <= MAX_W,
        "hmin_ok": hmin_ok,
    }


def all_ok(c):
    return all(c[k] for k in ("size_ok", "areas_ok", "eu_ok", "parity_ok", "hmin_ok"))


def build_prompt(raw, E, modalidad, h_min, eu_min, provide_scores=True):
    if provide_scores:
        header = "id\tarea\th_index\tgender\teu_project\texcellence"
        objective = ("Objective: among all teams satisfying the rules, choose the one "
                     "that MAXIMISES the sum of the 'excellence' column.")
    else:
        header = ("id\tarea\th_index\tgender\teu_project\tpublications\t"
                  "pi_projects\tphd_theses\trecent_trend\tarticle_impact")
        objective = ("Objective: among all teams satisfying the rules, choose the one "
                     "you judge to have the strongest overall research excellence, "
                     "weighing the indicator columns as you see fit.")
    lines = [header]
    for i in range(len(raw)):
        r = raw[i]
        base = (f"{i}\t{r['area']}\t{r['h_index']}\t"
                f"{'F' if r['genero']=='Mujer' else 'M'}\t"
                f"{'yes' if (r.get('proyectos_eu') or 0) > 0 else 'no'}")
        if provide_scores:
            lines.append(f"{base}\t{E[i]:.3f}")
        else:
            lines.append(f"{base}\t{r.get('produccion_cvn',0)}\t{r.get('proyectos_ip',0)}\t"
                         f"{r.get('tesis_dir',0)}\t{r.get('tendencia',0):.3f}\t{r.get('impacto_art',0):.1f}")
    table = "\n".join(lines)
    return (
        f"You are assembling a team of exactly {N} scientific guarantors for the "
        f"Spanish {modalidad} research-excellence call.\n"
        "Hard rules the team MUST satisfy:\n"
        f"- Exactly {N} members.\n"
        f"- At least {MIN_AREAS} distinct research areas.\n"
        f"- At least {eu_min} members with a European project (eu_project = yes).\n"
        f"- Gender balance: between {MIN_W} and {MAX_W} women.\n"
        f"- All listed candidates already satisfy h_index >= {h_min}.\n"
        f"{objective}\n"
        f"Return ONLY a JSON object: {{\"team\": [id, ...]}} with exactly {N} integer "
        "ids from the table, no other text.\n\n"
        "Candidates (tab-separated):\n" + table
    )


def parse_team(text):
    m = re.findall(r'\{[^{}]*"team"\s*:\s*\[[^\]]*\][^{}]*\}', text, re.S)
    if not m:
        return None
    try:
        return [int(x) for x in json.loads(m[-1])["team"]]
    except Exception:
        nums = re.findall(r"-?\d+", m[-1])
        return [int(x) for x in nums] if nums else None


def stats(xs):
    if not xs:
        return {"mean": None, "std": None, "min": None, "max": None}
    return {"mean": statistics.mean(xs), "std": statistics.pstdev(xs),
            "min": min(xs), "max": max(xs)}


def main():
    client = anthropic.Anthropic(
        api_key=cfg.ANTHROPIC_API_KEY, base_url=cfg.ANTHROPIC_BASE_URL, timeout=120.0
    )
    src = "offline bundle" if BUNDLE.exists() else "MongoDB"
    print(f"Data source: {src} | model {cfg.LLM_MODEL} | K={K_RUNS} | temp={TEMPERATURE}")
    results = {"db": DB, "data_source": src, "model": cfg.LLM_MODEL, "N": N,
               "K_runs": K_RUNS, "temperature": TEMPERATURE, "modalities": {}}

    for modalidad, h_min, eu_min in MODALITIES:
        raw, E, Kmat = load_pool(modalidad, h_min)

        sel, z = run_mip(raw, E, Kmat, N, min_areas=MIN_AREAS,
                         min_paridad=MIN_PARIDAD, modalidad=modalidad,
                         h_min=h_min, eu_min=eu_min)
        if sel is None:
            print(f"[{modalidad}] MIP infeasible — skipping"); continue
        mip_exc = float(sum(E[i] for i in sel))
        mip_chk = check(sel, raw, h_min, eu_min)

        print(f"\n=== {modalidad} (pool {len(raw)}, MIP ΣE={mip_exc:.2f}) ===")
        conditions = {}
        for cond, provide in (("scores_provided", True), ("raw_indicators", False)):
            prompt = build_prompt(raw, E, modalidad, h_min, eu_min, provide_scores=provide)
            runs = []
            for k in range(K_RUNS):
                txt = ""
                try:
                    msg = client.messages.create(
                        model=cfg.LLM_MODEL, max_tokens=1500, temperature=TEMPERATURE,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    txt = msg.content[0].text
                    team = parse_team(txt)
                except Exception as e:
                    print(f"  [{cond}] run {k}: API error {e}"); team = None
                if not team or len(set(team)) != N or any(t < 0 or t >= len(raw) for t in team):
                    runs.append({"valid": False, "team": team, "raw": txt[-300:]}); continue
                chk = check(team, raw, h_min, eu_min)
                exc = float(sum(E[i] for i in team))
                inter = len(set(team) & set(sel)); union = len(set(team) | set(sel))
                runs.append({"valid": True, "team": team, "checks": chk,
                             "feasible": all_ok(chk), "excellence": exc,
                             "opt_gap": (mip_exc - exc) / mip_exc,
                             "jaccard_vs_mip": inter / union})
                time.sleep(0.4)
            valid = [r for r in runs if r["valid"]]
            feas = [r for r in valid if r["feasible"]]
            gaps = [r["opt_gap"] for r in valid]
            jacs = [r["jaccard_vs_mip"] for r in valid]
            summ = {
                "valid_runs": len(valid), "feasible_runs": len(feas),
                "feasible_rate": len(feas) / len(valid) if valid else 0.0,
                "opt_gap": stats(gaps), "jaccard": stats(jacs),
                "constraint_violation_rate": {
                    c: (sum(0 if r["checks"][f"{c}_ok"] else 1 for r in valid) / len(valid)) if valid else None
                    for c in ("areas", "eu", "parity", "hmin")},
            }
            conditions[cond] = {"runs": runs, "summary": summ}
            g = summ["opt_gap"]; j = summ["jaccard"]
            gap = f"{g['mean']*100:+.1f}±{g['std']*100:.1f}%" if g["mean"] is not None else "n/a"
            jac = f"{j['mean']:.2f}" if j["mean"] is not None else "n/a"
            print(f"  [{cond:15}] feasible {summ['feasible_runs']}/{summ['valid_runs'] or '-'} "
                  f"({summ['feasible_rate']*100:3.0f}%) | opt-gap {gap:>12} | Jaccard {jac} | "
                  f"viol {summ['constraint_violation_rate']}")

        results["modalities"][modalidad] = {
            "pool_size": len(raw), "h_min": h_min, "eu_min": eu_min,
            "mip": {"excellence": mip_exc, "checks": mip_chk, "feasible": all_ok(mip_chk)},
            "conditions": conditions,
        }

    out = ROOT / "experiments" / "results_naive_llm.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
