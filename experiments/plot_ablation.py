#!/usr/bin/env python3
"""
Render the ablation figure from results_naive_llm.json.
Two panels: (a) excellence opt-gap vs the MIP optimum, (b) team overlap (Jaccard)
with the MIP team, grouped by call modality, for the two LLM conditions.
Colourblind-safe palette, vector PDF + PNG for the manuscript.
"""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
RES = json.loads((ROOT / "experiments" / "results_naive_llm.json").read_text())
OUT_DIR = Path("/Users/rubarez/Documents/Claude/Projects/SX-Garantes/figures")

mods = list(RES["modalities"].keys())
conds = [("scores_provided", "LLM with calibrated scores", "#0072B2"),
         ("raw_indicators", "LLM with raw indicators only", "#E69F00")]
x = np.arange(len(mods)); w = 0.36

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.4, 3.4))

for j, (cond, label, color) in enumerate(conds):
    gaps = [RES["modalities"][m]["conditions"][cond]["summary"]["opt_gap"]["mean"] * 100 for m in mods]
    gerr = [RES["modalities"][m]["conditions"][cond]["summary"]["opt_gap"]["std"] * 100 for m in mods]
    jac = [RES["modalities"][m]["conditions"][cond]["summary"]["jaccard"]["mean"] for m in mods]
    jerr = [RES["modalities"][m]["conditions"][cond]["summary"]["jaccard"]["std"] for m in mods]
    ax1.bar(x + (j - 0.5) * w, gaps, w, yerr=gerr, capsize=3, label=label, color=color, edgecolor="black", linewidth=0.4)
    ax2.bar(x + (j - 0.5) * w, jac, w, yerr=jerr, capsize=3, label=label, color=color, edgecolor="black", linewidth=0.4)

ax1.axhline(0, color="black", linewidth=0.8)
ax1.set_ylabel("Excellence gap vs MIP optimum (%)")
ax1.set_title("(a) Lost excellence", fontsize=10)
ax2.set_ylabel("Team overlap with MIP (Jaccard)")
ax2.set_title("(b) Selection agreement", fontsize=10)
ax2.set_ylim(0, 1)
for ax in (ax1, ax2):
    ax.set_xticks(x); ax.set_xticklabels(mods)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linewidth=0.3, alpha=0.5)
ax1.legend(fontsize=7.5, frameon=False, loc="upper left")

fig.tight_layout()
for ext in ("pdf", "png"):
    fig.savefig(OUT_DIR / f"ablation.{ext}", dpi=200, bbox_inches="tight")
print("wrote ablation.pdf / ablation.png to", OUT_DIR)
