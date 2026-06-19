# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MIP optimizer for selecting "garantes" (scientific guarantors) for Spanish Severo Ochoa / María de Maeztu research excellence grants (AEI convocatoria 2026). The system selects optimal subsets of investigators by primarily maximizing individual excellence (95%) with a minor cohesion tiebreaker (5%), subject to constraints on area diversity, h-index thresholds, and European project participation. Gender parity is not mandatory but acts as a tiebreaker between similar candidatures.

## Commands

```bash
# Run tests (no MongoDB needed — uses mock data)
cd optimizer && python test_mip.py

# Run Streamlit dashboard
streamlit run streamlit_app.py

# Install dependencies
pip install -r requirements.txt
```

## Architecture

### Core Pipeline

```
MongoDB (investigadores) → compute_E(docs, modalidad) → E[] scores + raw[]
                         → compute_K(raw, docs)       → K[][] cohesion matrix
                         → run_mip(raw, E, K, N, ...)  → seleccionados[]
                         → compute_diagnostico(sel, raw, K, N, modalidad) → diagnostico dict
```

**All four functions live in `optimizer/mip_garantes.py`** — this is the core file.

### Key Design Decisions

- **Modality-aware**: SO and MdM use different weight vectors (`PESOS_SO`/`PESOS_MDM` in `config.py`), different h-index thresholds, different EU project minimums, and different diagnostic thresholds
- **E_i scoring** uses 11 normalized dimensions: produccion, IP, tesis, tendencia, EU projects, international collaborations, reconocimiento, i10, impacto_art (article-level citations, DORA-compatible), sexenios, top_mundial (field percentile, testimonial weight)
- **K_ij cohesion** is built from real copublications in MongoDB, normalized to the 95th percentile
- **MIP solver** (OR-Tools/SCIP) maximizes `α·ΣE_i + β·ΣK_ij` (default α=0.95, β=0.05) with hard constraints (size, areas, EU minimum) and soft penalty (declining trends). Parity is a constraint but not mandatory per the convocatoria — it serves as tiebreaker
- **Prefiltration**: candidates below h_min are excluded before entering the solver (except fixed members)
- **`compute_diagnostico()`** is the single source of truth for diagnostics — consumed by dashboard, PDF report, and CLI

### LLM Integration (Claude API)

Three LLM modules in `optimizer/`, all using model `claude-opus-4-5` (set via `LLM_MODEL` in `config.py`):

- **`llm_evaluador.py`** — Simulates real evaluation panel with separate system prompts per modality (SO / MdM / UEI), each with its own reference period and exigency level. Two phases: individual garante scoring (0-10, threshold 9) and proposal evaluation (0-100, threshold 95)
- **`llm_nucleos.py`** — Values Louvain-detected collaboration clusters and proposes strategic alternatives
- **`llm_narrativa.py`** — Deprecated (kept for reference but not imported in dashboard)

### Dashboard (`streamlit_app.py`)

6 tabs: Resultado | Red | Candidatos | Sugerencias | Evaluacion | Exportar

Session state persists optimization results across tab switches. The modality selector in the sidebar drives defaults for all parameters.

### External Data

- **MongoDB** (`research_db.investigadores`) — investigators with publications, financiaciones, colaboraciones, ORCID records, OpenAlex data
- **OpenAlex API** — used by `openalex_enrich.py` to suggest external researchers

## Configuration

Copy `.env.example` to `.env`. All variables are optional: with no `MONGO_URI` the app boots in **offline demo mode** on synthetic investigator data (no database or credentials needed). Set `MONGO_URI` to use a real dataset, and `ANTHROPIC_API_KEY` to enable the LLM features.

Weights and thresholds are centralized in `optimizer/config.py`. Default α=0.95 (excellence), β=0.05 (cohesion tiebreaker). E_i weights are aligned with AEI 2026 convocatoria Phase 1 criteria; all dimensions are DORA-compatible (article-level impact instead of journal quartiles). The UI allows custom E_i weights via the "Pesos E_i" expander.

## Testing

Tests use mock MongoDB documents (no database connection needed). Run `cd optimizer && python test_mip.py`. Mock docs include EU projects on indices 0, 3, 8 for testing EU constraints.
