# Ablation: exact optimiser vs. a naive LLM selector (AI-vs-AI)

**Honest design note.** This is an AI-vs-AI experiment. No human experts are involved
or simulated, and no result here is presented as a human-expert evaluation. The goal
is to characterise what is lost if the structured scoring + exact-optimisation layers
are replaced by "just ask an LLM to pick the team".

Reproduces **offline** from a de-identified bundle (`demo_bundle.json`: only aggregate,
name-stripped fields plus the precomputed E_i scores and cohesion matrix — no internal
IDs, ORCID, publication titles or collaborator names). Regenerate the bundle from the
anonymised DB with `export_demo_bundle.py`; the experiment falls back to MongoDB only if
the bundle is absent.

```bash
cd Garante && python experiments/naive_llm_baseline.py   # uses demo_bundle.json
python experiments/plot_ablation.py                                 # renders the figure
```

Model: `claude-opus-4-5`, temperature 0.7, K = 10 runs per cell, team size N = 6.
The MIP optimum is the reference; the LLM is measured against it. Excellence is the
institution's own DORA-aligned E_i score (sum over the team). "Opt-gap" is
`(ΣE_i^MIP − ΣE_i^LLM) / ΣE_i^MIP` (positive = LLM team is lower on this metric).

## Two conditions

- **scores_provided** — the LLM receives the same E_i scores the MIP uses, plus the
  constraint attributes, and is asked to optimise the selection. Tests the LLM as a
  *combinatorial optimiser* when the objective is handed to it.
- **raw_indicators** — the LLM receives raw CV indicators (publications, PI projects,
  theses, recent trend, article impact, h-index, area, gender, EU flag) but **no E_i**,
  and must both judge merit and select. This is the realistic "external LLM" scenario:
  a model without the scoring pipeline, asked to pick guarantors.

## Results (30 runs per condition: 3 modalities × K = 10)

| Condition | Feasible (all hard constraints) | Mean opt-gap vs MIP (mean ± sd) | Mean Jaccard vs MIP team |
|---|---|---|---|
| scores_provided | 30/30 (100%) | SO +0.3±0.6% · MdM 0.0±0.0% · UEI −0.5±0.0% | 0.94 / 1.00 / 0.71 |
| raw_indicators  | 25/30 (83%)  | SO +11.9±2.9% · MdM +16.7±1.5% · UEI +21.5±4.1% | 0.21 / 0.20 / 0.05 |

In `scores_provided` every run honoured every hard constraint (≥3 areas, EU-project
minimum, gender band, h-index floor). In `raw_indicators` the model also honoured them
for SO and MdM, but in the tightest call (UEI) it **violated the gender-parity band in
5 of 10 runs** — the only constraint failures observed.

## What this shows (and does not)

1. **Constraint handling is mostly, but not entirely, robust.** Given the rules in
   plain language the model honoured every hard constraint in 55 of 60 runs; the only
   failures were gender-parity violations in the tightest call (UEI, raw indicators),
   5 of 10 runs. So the blunt intuition "an LLM will break the rules" is largely **not**
   supported — but constraint satisfaction is empirical and stochastic, never
   guaranteed, whereas the MIP guarantees it by construction.

2. **When the LLM is handed the calibrated scores, it is a competent selector at this
   scale** — feasible and within ~0.5% of the MIP objective. The occasional negative
   gap (UEI −0.5%) is expected and honest: the MIP maximises excellence **plus**
   cohesion and area-diversity, not pure ΣE_i, so a pure-excellence picker can edge it
   out on that one axis while ignoring the structural terms.

3. **The real divergence is in the excellence *judgement*, not the optimisation.**
   Without the E_i pipeline, the LLM's ad-hoc weighting of raw indicators selects teams
   that are 12–22% below the institution's own excellence metric and overlap only
   5–21% with the optimal team. We do **not** claim those teams are objectively worse
   (there is no ground truth); we claim the choice of scoring methodology materially
   changes the outcome. The tool's contribution is making that methodology explicit,
   transparent and reproducible, and solving the constrained selection exactly — rather
   than leaving excellence to an opaque, non-deterministic model judgement (note the
   sub-1.0 Jaccard even in `scores_provided`: the LLM returns different teams across
   runs, whereas the MIP is deterministic and auditable).

## Limitations

Single anonymised institution, one model, K = 10, N = 6, small candidate pools. AI-vs-AI
only — this is **not** a validation against a real evaluation panel, which remains
future work. Results characterise the architecture, not the real-world quality of any
selection.
