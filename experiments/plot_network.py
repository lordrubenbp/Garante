#!/usr/bin/env python3
"""
Static, legended rendering of the copublication network of the synthetic Demo
institute (paper Fig. 5). Same encoding as the dashboard view (pages/lab_red.py):
node colour = research area, node size = excellence score E_i, edge width =
cohesion K_ij. Positions come from a seeded force-directed layout and carry no
metric meaning, so the plot has no axes.

No database, no API key:
    pip install matplotlib   # figure dep, not in runtime requirements.txt
    python experiments/plot_network.py
Output: experiments/network_demo.pdf and .png
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "optimizer"))

import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from demo_data import generate_demo_docs
from mip_garantes import compute_E, compute_K

PALETTE = [  # same as pages/lab_red.py
    "#4caf7d", "#5c8fff", "#ffa040", "#e57373", "#ab72e8",
    "#26c6da", "#f06292", "#8bc34a", "#ff8a65", "#4db6ac",
    "#7986cb", "#a1887f", "#90a4ae", "#ffb74d", "#4dd0e1",
]
EDGE = "#b0b8c4"
node_size = lambda e: 20 + 220 * e      # E_i in [0, 1]
edge_width = lambda k: 0.4 + 3.6 * k    # K_ij in [0, 1]


def main():
    docs = generate_demo_docs()
    E, raw = compute_E(docs)
    K = compute_K(raw, docs)
    areas = sorted({r["area"] for r in raw})
    col = {a: PALETTE[i % len(PALETTE)] for i, a in enumerate(areas)}

    G = nx.Graph()
    G.add_nodes_from(range(len(raw)))
    G.add_edges_from((i, j, {"k": float(K[i][j])})
                     for i in range(len(raw)) for j in range(i + 1, len(raw)) if K[i][j] > 0)
    pos = nx.spring_layout(G, seed=7, k=0.35)

    fig, ax = plt.subplots(figsize=(10, 6.2))
    nx.draw_networkx_edges(G, pos, ax=ax, edge_color=EDGE,
                           width=[edge_width(d["k"]) for *_, d in G.edges(data=True)])
    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=[col[r["area"]] for r in raw],
                           node_size=[node_size(E[i]) for i in G.nodes()], linewidths=0)
    ax.set_axis_off()

    area_leg = ax.legend(
        handles=[Line2D([], [], marker="o", ls="", color=col[a], markersize=7, label=a) for a in areas],
        title="Research area (node colour)", loc="upper left", bbox_to_anchor=(1.0, 1.0),
        fontsize=8, title_fontsize=9, frameon=False)
    ax.add_artist(area_leg)
    size_leg = ax.legend(
        handles=[Line2D([], [], marker="o", ls="", color="#90a4ae",
                        markersize=node_size(e) ** 0.5, label=f"{e:.1f}") for e in (0.2, 0.4, 0.7)],
        title="Excellence $E_i$ (node size)", loc="upper left", bbox_to_anchor=(1.0, 0.42),
        fontsize=8, title_fontsize=9, frameon=False, labelspacing=1.1)
    ax.add_artist(size_leg)
    edge_leg = ax.legend(
        handles=[Line2D([], [], color=EDGE, lw=edge_width(k), label=f"{k:.2f}") for k in (0.1, 0.5, 1.0)],
        title="Cohesion $K_{ij}$ (edge width)", loc="upper left", bbox_to_anchor=(1.0, 0.17),
        fontsize=8, title_fontsize=9, frameon=False)

    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(ROOT / "experiments" / f"network_demo.{ext}", dpi=200, bbox_inches="tight",
                    bbox_extra_artists=(area_leg, size_leg, edge_leg))
    print(f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(areas)} areas")


if __name__ == "__main__":
    main()
