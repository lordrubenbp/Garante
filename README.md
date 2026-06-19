# Garante

**A hybrid MIP–LLM decision-support system for assembling scientific guarantor teams in research-excellence calls.**

Garante helps a research institution choose the small team of *scientific guarantors*
required by excellence-accreditation programmes (in Spain, the Severo Ochoa and María de
Maeztu calls of the State Research Agency, and the regional *Unidades de Excelencia*
scheme). It selects an optimal subset of investigators by maximising a DORA-aligned,
eleven-dimensional excellence score together with a copublication-cohesion term, subject
to the call's hard eligibility constraints (area coverage, h-index thresholds, minimum
European-project participation, gender-parity band). A large-language-model module
additionally emulates a call-specific evaluation rubric to add a qualitative layer that
is kept strictly separate from the exact optimisation.

This repository accompanies the SoftwareX article *"Garante: A hybrid MIP–LLM
decision-support system for assembling scientific guarantor teams in research excellence
calls."*

## What it does

- **Scoring** — `compute_E()` maps each investigator to an excellence score
  `E_i ∈ [0,1]` over eleven normalised, article-level dimensions (production, project
  leadership, theses, recent trend, EU projects, international collaboration,
  recognition, i10, article-level citation impact, *sexenios*, field percentile). No
  journal-based metric enters the score.
- **Cohesion** — `compute_K()` builds a pairwise matrix from real copublications.
- **Optimisation** — `run_mip()` solves a mixed-integer program (Google OR-Tools / SCIP)
  to proven optimality, with hard constraints, a parity band, an h-index soft gate, and
  an optional stability analysis.
- **LLM panel** — `llm_evaluador.py` scores candidates and the overall proposal with
  call-specific prompts (Anthropic Claude API). Prompts are versioned; the model id is
  pinned; MIP results never depend on the LLM.
- **Dashboard** — a Streamlit wizard for configuration, optimisation, diagnostics,
  network analytics and PDF reporting.

## Installation

```bash
git clone https://github.com/lordrubenbp/garante
cd garante
pip install -r requirements.txt
```

Python ≥ 3.10.

## Quick start

**Offline command-line demo (no database, no API key).** Runs the full
scoring → optimisation → diagnostics pipeline on mock data:

```bash
cd optimizer && python test_mip.py
```

**Interactive dashboard, fully offline.** No database needed — pick the **"Demo
(offline)"** institute in the first dropdown to run the complete wizard (scoring,
optimisation, diagnostics, network) on synthetic data:

```bash
streamlit run streamlit_app.py
```

The LLM panel additionally needs an Anthropic API key. For a live deployment on your
own data, set `MONGO_URI` (and `ANTHROPIC_API_KEY`) in `.env`:

```bash
cp .env.example .env
streamlit run streamlit_app.py
```

## Reproducing the AI-vs-AI ablation

The `experiments/` directory contains an honest ablation (exact optimiser vs. a naive
LLM selector) that reproduces **offline** from a de-identified bundle:

```bash
python experiments/naive_llm_baseline.py   # needs ANTHROPIC_API_KEY for the LLM half
python experiments/plot_ablation.py        # renders the figure
```

`experiments/demo_bundle.json` ships only de-identified aggregate fields plus the
precomputed scores and cohesion matrix; `experiments/results_naive_llm.json` lets you
inspect the numbers without re-running. See `experiments/README.md` for the design and
findings.

## Repository structure

```
optimizer/        core: scoring, cohesion, MIP, diagnostics, LLM modules, CLI tests
pages/            Streamlit dashboard pages
ui/               shared dashboard components
experiments/      AI-vs-AI ablation harness, de-identified bundle, results, figure
streamlit_app.py  dashboard entry point
```

## Data and privacy

The repository ships **de-identified demonstration data only** — name-stripped aggregate
records and precomputed scores, with no names, internal identifiers, ORCIDs or
publication titles. The full institutional database contains personal data and is not
included.

## Tests

```bash
cd optimizer && python test_mip.py
```

The test suite runs without MongoDB.

## License

MIT — see [LICENSE](LICENSE).

## Citation

If you use Garante, please cite the SoftwareX article (reference to be added on
publication).
