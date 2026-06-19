#!/usr/bin/env python3
"""Lab: Red de copublicaciones del instituto."""
import sys
import os
import tempfile

import numpy as np
import streamlit as st
import streamlit_antd_components as sac
import streamlit.components.v1 as components
import networkx as nx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "optimizer"))
import config as cfg
from mip_garantes import load_investigators, compute_E, compute_K

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ui.wizard_common import render_tool_instituto_selector, _pretty_institute

# ── Institutional color palette (Material Design 700 shades) ──
_BRAND_PALETTE = [
    "#4caf7d", "#5c8fff", "#ffa040", "#e57373", "#ab72e8",
    "#26c6da", "#f06292", "#8bc34a", "#ff8a65", "#4db6ac",
    "#7986cb", "#a1887f", "#90a4ae", "#ffb74d", "#4dd0e1",
]
_BRAND_PRIMARY = '#002045'
_BRAND_FG = '#181c1e'
_BRAND_BG = '#ffffff'
_EDGE_COLOR = "#b0b8c4"
_EDGE_HIGHLIGHT = "#6e7178"

# ── Data loading ──
@st.cache_data(ttl=300)
def _load_data(db_name: str, modalidad: str = "MdM"):
    docs = load_investigators(db_name)
    E, raw = compute_E(docs, modalidad=modalidad)
    return docs, E, raw


# ── Page header ──
st.title("Red de copublicaciones")
st.caption(
    "Visualizacion de la red de colaboracion del instituto basada en "
    "copublicaciones reales. Cada enlace conecta investigadores que han "
    "publicado juntos."
)

# ── Instituto / modalidad selector (independiente del wizard) ──
instituto, modalidad_code = render_tool_instituto_selector()

docs, E, raw = _load_data(instituto, modalidad_code)
st.caption(f"{len(raw)} investigadores disponibles · {_pretty_institute(instituto)}")

# ── Compute K_full (keyed by instituto to avoid stale data on institute switch) ──
_k_key = f"K_full_{instituto}"
if st.session_state.get(_k_key) is None:
    with st.spinner(
        f"Calculando conexiones para los {len(raw)} investigadores del instituto..."
    ):
        st.session_state[_k_key] = compute_K(raw, docs)
K_full_lab = st.session_state[_k_key]

if len(raw) == 0:
    st.warning("No hay investigadores disponibles.")
    st.stop()

# ── Vista selector ──
_vista_red = st.radio(
    "Vista",
    ["Investigadores", "Areas"],
    horizontal=True,
)

# =============================================================================
# VISTA: Investigadores
# =============================================================================
if _vista_red == "Investigadores":
    st.subheader("Red de copublicaciones del instituto")
    st.caption("Cada linea conecta investigadores que han copublicado.")

    K_src = K_full_lab
    data_src = raw
    indices_all = list(range(len(raw)))

    areas_en_red = sorted(
        set(data_src[i]["area"] for i in indices_all if data_src[i]["area"])
    )
    area_filtro_red = sac.chip(
        items=[sac.ChipItem(label=a) for a in areas_en_red],
        size="sm", multiple=True, return_index=False,
    ) or []

    filtro_inv = st.multiselect(
        "Filtrar por investigador -- muestra sus conexiones directas",
        options=sorted(data_src[i]["nombre_completo"] for i in range(len(data_src))),
        placeholder="Sin filtro -- mostrar todos...",
        help="Selecciona uno o mas investigadores para ver unicamente sus "
             "conexiones directas en el grafo.",
    )

    G = nx.Graph()
    indices = indices_all
    if area_filtro_red:
        indices = [i for i in indices if data_src[i]["area"] in area_filtro_red]

    if filtro_inv:
        _pivot_set = {
            i for i in range(len(data_src))
            if data_src[i]["nombre_completo"] in set(filtro_inv)
        }
        _neighbors = {
            j for i in _pivot_set
            for j in range(len(data_src))
            if j != i and K_src[i][j] > 0
        }
        indices = sorted(_pivot_set | _neighbors)

    # Copublicaciones crudas para hover
    id_to_idx_src = {
        r.get("id_investigador"): i
        for i, r in enumerate(data_src)
        if r.get("id_investigador") is not None
    }
    copubs_raw = {}
    for i, doc in enumerate(docs):
        colabs = (doc.get("colaboraciones") or {}).get("colaboradores", [])
        for colab in colabs:
            colab_id = colab.get("id_investigador")
            if colab_id and colab_id in id_to_idx_src:
                j = id_to_idx_src[colab_id]
                if j != i:
                    pubs = colab.get("publicaciones_conjuntas", 0) or 0
                    key = (min(i, j), max(i, j))
                    copubs_raw[key] = max(copubs_raw.get(key, 0), pubs)

    for i in indices:
        G.add_node(i)
    for idx_i, i in enumerate(indices):
        for j in indices[idx_i + 1:]:
            if K_src[i][j] > 0:
                key = (min(i, j), max(i, j))
                G.add_edge(i, j, weight=float(K_src[i][j]), copubs=copubs_raw.get(key, 0))

    st.caption(f"{len(indices)} investigadores · {G.number_of_edges()} conexiones")

    if len(G.nodes) == 0:
        st.warning("No hay nodos para mostrar.")
    else:
        from pyvis.network import Network as PyVisNetwork

        areas_list = sorted(
            set(data_src[i]["area"] for i in G.nodes() if data_src[i]["area"])
        )

        net = PyVisNetwork(
            height="650px", width="100%",
            bgcolor=_BRAND_BG, font_color=_BRAND_FG,
        )
        net.barnes_hut(
            gravity=-4000, central_gravity=0.3,
            spring_length=180, spring_strength=0.04,
        )
        net.show_buttons(filter_=["physics"])

        for n in G.nodes():
            r = data_src[n]
            parts = r["nombre_completo"].split()
            short = parts[0] + " " + parts[1] if len(parts) >= 2 else parts[0]
            area = r["area"]
            area_idx = areas_list.index(area) if area in areas_list else 0
            color = _BRAND_PALETTE[area_idx % len(_BRAND_PALETTE)]
            title = (
                f"{r['nombre_completo']}\nArea: {area}\n"
                f"h-index: {r['h_index']}  |  E_i: {r['E_i']:.3f}"
            )
            net.add_node(
                n, label=short, title=title,
                size=12 + 15 * r["E_i"],
                color={
                    "background": color, "border": color,
                    "highlight": {"background": color, "border": _BRAND_PRIMARY},
                },
                borderWidth=1,
                font={"size": 12, "face": "Inter, Arial, sans-serif"},
            )

        for u, v, d in G.edges(data=True):
            w = d["weight"]
            cpubs = d.get("copubs", 0)
            title = (
                f"{data_src[u]['nombre_completo']} - "
                f"{data_src[v]['nombre_completo']}\n"
                f"K = {w:.3f}\nCopublicaciones: {cpubs}"
            )
            net.add_edge(
                u, v, value=1 + 6 * w, title=title,
                color={
                    "color": _EDGE_COLOR,
                    "highlight": _EDGE_HIGHLIGHT,
                    "opacity": 0.4 + 0.5 * w,
                },
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w") as f:
            net.save_graph(f.name)
            tmp_path = f.name
        try:
            with open(tmp_path, "r") as f:
                html_content = f.read()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        html_content = html_content.replace(
            "</body>",
            '<script>network.on("stabilizationIterationsDone", '
            'function(){network.setOptions({physics:false});});</script></body>',
        )
        components.html(html_content, height=1080, scrolling=True)

# =============================================================================
# VISTA: Areas
# =============================================================================
else:
    st.subheader("Red de copublicaciones entre areas")
    st.caption(
        "Cada linea conecta areas cuyos investigadores han copublicado. "
        "Grosor proporcional al volumen de copublicaciones inter-area."
    )

    from collections import defaultdict
    area_members = defaultdict(list)
    for i in range(len(raw)):
        a = raw[i]["area"]
        if a:
            area_members[a].append(i)

    todas_las_areas = sorted(area_members.keys())
    area_filtro_areas = sac.chip(
        items=[sac.ChipItem(label=a) for a in todas_las_areas],
        size="sm", multiple=True, return_index=False,
    ) or []
    areas_sorted = (
        [a for a in todas_las_areas if a in area_filtro_areas]
        if area_filtro_areas else list(todas_las_areas)
    )

    # K agregado entre pares de areas
    area_k = {}
    area_pairs_count = {}
    for idx_a, a1 in enumerate(areas_sorted):
        for a2 in areas_sorted[idx_a + 1:]:
            k_sum = 0.0
            n_pairs = 0
            for i in area_members[a1]:
                for j in area_members[a2]:
                    k_val = K_full_lab[i][j]
                    if k_val > 0:
                        k_sum += k_val
                        n_pairs += 1
            if k_sum > 0:
                area_k[(a1, a2)] = k_sum
                area_pairs_count[(a1, a2)] = n_pairs

    if area_k:
        max_k_val = max(area_k.values())
        min_k_val = min(area_k.values())
        if max_k_val > min_k_val:
            min_k_filter = st.slider(
                "K agregado minimo entre areas",
                min_value=0.0,
                max_value=float(round(max_k_val, 2)),
                value=0.0, step=0.01, format="%.2f",
                help="Solo muestra conexiones entre areas cuyo K agregado >= este valor.",
                key="min_k_areas",
            )
            area_k = {k: v for k, v in area_k.items() if v >= min_k_filter}
            area_pairs_count = {k: v for k, v in area_pairs_count.items() if k in area_k}

    if not areas_sorted:
        st.warning("No hay areas para mostrar.")
    else:
        G_areas = nx.Graph()
        for a in areas_sorted:
            G_areas.add_node(a)
        for (a1, a2), k_sum in area_k.items():
            G_areas.add_edge(a1, a2, weight=k_sum, pairs=area_pairs_count[(a1, a2)])

        st.caption(
            f"{len(areas_sorted)} areas · "
            f"{G_areas.number_of_edges()} conexiones inter-area"
        )

        from pyvis.network import Network as PyVisNetwork

        max_k = max(area_k.values()) if area_k else 1.0

        net = PyVisNetwork(
            height="650px", width="100%",
            bgcolor=_BRAND_BG, font_color=_BRAND_FG,
        )
        net.barnes_hut(
            gravity=-3000, central_gravity=0.3,
            spring_length=200, spring_strength=0.04,
        )
        net.show_buttons(filter_=["physics"])

        for idx, a in enumerate(areas_sorted):
            members = area_members[a]
            names_str = "\n".join(
                raw[i]["nombre_completo"] for i in members[:15]
            )
            if len(members) > 15:
                names_str += f"\n... y {len(members) - 15} mas"
            net.add_node(
                a, label=a,
                title=f"{a}\n{len(members)} investigadores\n\n{names_str}",
                size=15 + 5 * len(members),
                color=_BRAND_PALETTE[idx % len(_BRAND_PALETTE)],
                font={"size": 16, "face": "Manrope, Inter, Arial, sans-serif"},
            )

        for (a1, a2), k_sum in area_k.items():
            w_norm = k_sum / max_k
            n_pairs = area_pairs_count[(a1, a2)]
            net.add_edge(
                a1, a2, value=2 + 8 * w_norm,
                title=(
                    f"{a1} - {a2}\nK agregado: {k_sum:.3f}\n"
                    f"{n_pairs} pares con copublicaciones"
                ),
                color={
                    "color": _EDGE_COLOR,
                    "highlight": _EDGE_HIGHLIGHT,
                    "opacity": 0.3 + 0.6 * w_norm,
                },
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w") as f:
            net.save_graph(f.name)
            tmp_path = f.name
        try:
            with open(tmp_path, "r") as f:
                html_content = f.read()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        html_content = html_content.replace(
            "</body>",
            '<script>network.on("stabilizationIterationsDone", '
            'function(){network.setOptions({physics:false});});</script></body>',
        )
        components.html(html_content, height=1080, scrolling=True)

        with st.expander("Detalle por area"):
            area_rows = []
            for a in areas_sorted:
                members = area_members[a]
                e_mean = np.mean([raw[i]["E_i"] for i in members])
                h_mean = np.mean([raw[i]["h_index"] for i in members])
                conexiones = sum(1 for (a1, a2) in area_k if a in (a1, a2))
                area_rows.append({
                    "Area": a,
                    "Investigadores": len(members),
                    "h-index medio": round(h_mean, 1),
                    "E_i medio": round(e_mean, 3),
                    "Areas conectadas": conexiones,
                })
            st.dataframe(area_rows, use_container_width=True, hide_index=True)
