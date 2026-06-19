#!/usr/bin/env python3
"""Lab -- standalone tool page for collaborative exploration.

Not part of the wizard flow. Provides:
1. Copublication network (investigators and areas views)
2. Nucleus detection via Louvain community detection
3. LLM nucleus suggestions and comparison radar
"""
import sys
import os
import math
import tempfile

import numpy as np
import pandas as pd
import networkx as nx
import plotly.graph_objects as go
import streamlit as st
import streamlit_antd_components as sac
import streamlit.components.v1 as components

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "optimizer"))
import config as cfg
from mip_garantes import (
    load_investigators, discover_institutes, compute_E, compute_K,
    run_mip, compute_diagnostico,
)
from utils import (
    k_medio_individual, short_name, detect_and_score_nucleos,
)

# ── Institutional color palette (Material Design 700 shades) ──
_BRAND_PALETTE = [
    "#4caf7d", "#5c8fff", "#ffa040", "#e57373", "#ab72e8",
    "#26c6da", "#f06292", "#8bc34a", "#ff8a65", "#4db6ac",
    "#7986cb", "#a1887f", "#90a4ae", "#ffb74d", "#4dd0e1",
]
_BRAND_PRIMARY = '#002045'
_BRAND_FG = '#181c1e'
_EDGE_COLOR = "#b0b8c4"
_EDGE_HIGHLIGHT = "#6e7178"
_BRAND_BG = '#ffffff'

# ── Constants ──
DIM_LABELS = [
    "Produccion", "IP", "Tesis", "Tendencia", "EU", "Intl.",
    "Reconoc.", "i10", "Impacto art.", "Sexenios", "Top mundial",
]
DIM_KEYS = [
    "produccion", "ip", "tesis", "tendencia", "eu", "intl",
    "reconocimiento", "i10", "impacto_art", "sexenios", "top_mundial",
]


# ── Styling helpers ──
def _color_tendencia(val):
    if not isinstance(val, (int, float)):
        return ""
    if val >= 0.7:
        return "background-color: rgba(76,175,125,0.55); color: #181c1e"
    if val >= 0.4:
        return "background-color: rgba(139,195,74,0.55); color: #181c1e"
    if val >= 0.1:
        return "background-color: rgba(205,220,57,0.55); color: #181c1e"
    if val >= 0:
        return "background-color: rgba(255,235,59,0.55); color: #181c1e"
    if val >= -0.1:
        return "background-color: rgba(255,193,7,0.55); color: #181c1e"
    if val >= -0.3:
        return "background-color: rgba(255,112,67,0.55); color: #181c1e"
    return "background-color: rgba(229,115,115,0.55); color: #181c1e"


def _color_nucleo(val):
    if isinstance(val, str) and "Nucleo" in val:
        return "background-color: rgba(255,193,7,0.55); color: #181c1e"
    return ""


# ── Data loading ──
@st.cache_data(ttl=300)
def _load_data(db_name: str, modalidad: str = "MdM"):
    docs = load_investigators(db_name)
    E, raw = compute_E(docs, modalidad=modalidad)
    return docs, E, raw


@st.cache_data(ttl=60)
def _get_institutes() -> list[str]:
    return discover_institutes()


# ── Page header ──
st.header("Lab -- exploracion colaborativa del instituto")
st.caption(
    "Espacio de exploracion NO ligado a ninguna convocatoria. Aqui el factor "
    "determinante son las copublicaciones: red de colaboracion y grupos de "
    "investigacion a futuro."
)

# ── Resolve instituto / modalidad ──
_institutes = _get_institutes()
instituto = st.session_state.get(
    "instituto", _institutes[0] if _institutes else "research_db"
)
modalidad = st.session_state.get("modalidad", "MdM")
modalidad_code = (
    "SO" if modalidad and "Severo" in modalidad
    else "UEI" if modalidad and "UEI" in modalidad
    else "MdM"
)

docs, E, raw = _load_data(instituto, modalidad_code)
st.caption(
    f"{len(raw)} investigadores disponibles  --  instituto: {instituto}"
)

# ── Compute K_full (shared across both sections) ──
if st.session_state.get("K_full") is None:
    with st.spinner(
        f"Calculando conexiones para los {len(raw)} investigadores del instituto..."
    ):
        st.session_state.K_full = compute_K(raw, docs)
K_full_lab = st.session_state.K_full


# =============================================================================
# SECTION 1: Red de copublicaciones
# =============================================================================
sac.divider(label="Red de copublicaciones", icon="diagram-3", color="dark")

if len(raw) > 0:
    _vista_red = st.radio(
        "vista_red_radio",
        ["Investigadores", "Areas"],
        horizontal=True,
        label_visibility="collapsed",
    )

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

        # Filtro por investigador: ego-network
        _names_src = sorted(
            data_src[i]["nombre_completo"] for i in range(len(data_src))
        )
        filtro_inv = st.multiselect(
            "Filtrar por investigador -- muestra sus conexiones directas",
            options=_names_src,
            placeholder="Sin filtro -- mostrar todos...",
            help="Selecciona uno o mas investigadores para ver unicamente sus "
                 "conexiones directas en el grafo.",
        )

        G = nx.Graph()
        indices = indices_all
        if area_filtro_red:
            indices = [i for i in indices if data_src[i]["area"] in area_filtro_red]

        # Si hay filtro de investigador: mostrar pivot(s) + todos sus vecinos con K > 0
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

        # Calcular copublicaciones crudas para hover
        docs_src = docs
        id_to_idx_src = {}
        for i, r in enumerate(data_src):
            inv_id = r.get("id_investigador")
            if inv_id is not None:
                id_to_idx_src[inv_id] = i
        copubs_raw = {}
        for i, doc in enumerate(docs_src):
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
                    G.add_edge(
                        i, j, weight=float(K_src[i][j]),
                        copubs=copubs_raw.get(key, 0),
                    )

        st.caption(f"{len(indices)} investigadores  --  {G.number_of_edges()} conexiones")

        if len(G.nodes) == 0:
            st.warning("No hay nodos para mostrar.")
        else:
            from pyvis.network import Network as PyVisNetwork

            areas_list = sorted(
                set(data_src[i]["area"] for i in G.nodes() if data_src[i]["area"])
            )
            palette = _BRAND_PALETTE

            net = PyVisNetwork(
                height="650px", width="100%",
                bgcolor=_BRAND_BG, font_color=_BRAND_FG,
            )
            net.barnes_hut(
                gravity=-4000, central_gravity=0.3,
                spring_length=180, spring_strength=0.04,
            )
            net.show_buttons(filter_=["physics"])

            # Nodos
            for n in G.nodes():
                r = data_src[n]
                parts = r["nombre_completo"].split()
                short = parts[0] + " " + parts[1] if len(parts) >= 2 else parts[0]
                area = r["area"]
                area_idx = areas_list.index(area) if area in areas_list else 0
                color = palette[area_idx % len(palette)]
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

            # Aristas
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

            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".html", mode="w"
            ) as f:
                net.save_graph(f.name)
                tmp_path = f.name
            try:
                with open(tmp_path, "r") as f:
                    html_content = f.read()
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            # Desactivar fisica tras estabilizacion
            html_content = html_content.replace(
                "</body>",
                '<script>network.on("stabilizationIterationsDone", '
                'function(){network.setOptions({physics:false});});</script></body>',
            )
            components.html(html_content, height=1080, scrolling=True)

    else:  # Vista de Areas
        st.subheader("Red de copublicaciones entre areas")
        st.caption(
            "Cada linea conecta areas cuyos investigadores han copublicado. "
            "Grosor proporcional al volumen de copublicaciones inter-area."
        )

        K_areas = K_full_lab
        data_areas = raw
        indices_areas = list(range(len(raw)))

        # Agrupar investigadores por area
        from collections import defaultdict
        area_members = defaultdict(list)
        for i in indices_areas:
            a = data_areas[i]["area"]
            if a:
                area_members[a].append(i)

        # Filtro de areas
        todas_las_areas = sorted(area_members.keys())
        area_filtro_areas = sac.chip(
            items=[sac.ChipItem(label=a) for a in todas_las_areas],
            size="sm", multiple=True, return_index=False,
        ) or []
        if area_filtro_areas:
            areas_sorted = [a for a in todas_las_areas if a in area_filtro_areas]
        else:
            areas_sorted = list(todas_las_areas)

        # Calcular K agregado entre pares de areas
        area_k = {}
        area_pairs_count = {}
        for idx_a, a1 in enumerate(areas_sorted):
            for a2 in areas_sorted[idx_a + 1:]:
                k_sum = 0.0
                n_pairs = 0
                for i in area_members[a1]:
                    for j in area_members[a2]:
                        k_val = K_areas[i][j]
                        if k_val > 0:
                            k_sum += k_val
                            n_pairs += 1
                if k_sum > 0:
                    area_k[(a1, a2)] = k_sum
                    area_pairs_count[(a1, a2)] = n_pairs

        # Filtro por K agregado minimo entre areas
        if area_k:
            max_k_val = max(area_k.values())
            min_k_val = min(area_k.values())
            if max_k_val > min_k_val:
                min_k_filter = st.slider(
                    "K agregado minimo entre areas",
                    min_value=0.0,
                    max_value=float(round(max_k_val, 2)),
                    value=0.0,
                    step=0.01, format="%.2f",
                    help="Solo muestra conexiones entre areas cuyo K agregado "
                         "(suma de copublicaciones ponderadas) sea >= este valor.",
                    key="min_k_areas",
                )
                area_k = {k: v for k, v in area_k.items() if v >= min_k_filter}
                area_pairs_count = {
                    k: v for k, v in area_pairs_count.items() if k in area_k
                }

        if not areas_sorted:
            st.warning("No hay areas para mostrar.")
        else:
            G_areas = nx.Graph()
            for a in areas_sorted:
                G_areas.add_node(a)
            for (a1, a2), k_sum in area_k.items():
                G_areas.add_edge(
                    a1, a2, weight=k_sum, pairs=area_pairs_count[(a1, a2)]
                )

            st.caption(
                f"{len(areas_sorted)} areas  --  "
                f"{G_areas.number_of_edges()} conexiones inter-area"
            )

            from pyvis.network import Network as PyVisNetwork

            max_k = max(area_k.values()) if area_k else 1.0
            palette = _BRAND_PALETTE

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
                names = [data_areas[i]["nombre_completo"] for i in members]
                names_str = "\n".join(names[:15])
                if len(names) > 15:
                    names_str += f"\n... y {len(names) - 15} mas"
                title = f"{a}\n{len(members)} investigadores\n\n{names_str}"
                net.add_node(
                    a, label=a, title=title,
                    size=15 + 5 * len(members),
                    color=palette[idx % len(palette)],
                    font={"size": 16, "face": "Manrope, Inter, Arial, sans-serif"},
                )

            for (a1, a2), k_sum in area_k.items():
                w_norm = k_sum / max_k
                n_pairs = area_pairs_count[(a1, a2)]
                title = (
                    f"{a1} - {a2}\nK agregado: {k_sum:.3f}\n"
                    f"{n_pairs} pares con copublicaciones"
                )
                net.add_edge(
                    a1, a2, value=2 + 8 * w_norm, title=title,
                    color={
                        "color": _EDGE_COLOR,
                        "highlight": _EDGE_HIGHLIGHT,
                        "opacity": 0.3 + 0.6 * w_norm,
                    },
                )

            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".html", mode="w"
            ) as f:
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

            # Tabla resumen de areas
            with st.expander(
                "Detalle por area", icon=":material/table_chart:"
            ):
                area_rows = []
                for a in areas_sorted:
                    members = area_members[a]
                    e_mean = np.mean([data_areas[i]["E_i"] for i in members])
                    h_mean = np.mean([data_areas[i]["h_index"] for i in members])
                    conexiones = sum(
                        1 for (a1, a2) in area_k if a in (a1, a2)
                    )
                    area_rows.append({
                        "Area": a,
                        "Investigadores": len(members),
                        "h-index medio": round(h_mean, 1),
                        "E_i medio": round(e_mean, 3),
                        "Areas conectadas": conexiones,
                    })
                st.dataframe(area_rows, use_container_width=True, hide_index=True)


# =============================================================================
# SECTION 2: Grupos de investigacion a futuro
# =============================================================================
sac.divider(
    label="Grupos de investigacion a futuro", icon="people", color="dark"
)
st.caption(
    "Deteccion de nucleos colaborativos con potencial. Exploracion "
    "modalidad-agnostica: investigadores que si empiezan a colaborar podrian "
    "formar un equipo competitivo a futuro. El scoring multidimensional "
    "identifica combinaciones estrategicas y la IA propone refuerzos para "
    "completar cada grupo."
)

if "clusters" not in st.session_state:
    st.session_state.clusters = None
    st.session_state.llm_nucleos = None
    st.session_state.clusters_K = None

# ── MIP parameters for nucleus optimization ──
# Use sensible defaults; override from session state if the wizard has run.
n_garantes_default = 10 if modalidad_code == "SO" else 5 if modalidad_code == "UEI" else 6
n_garantes = st.session_state.get("n_garantes", n_garantes_default)
min_areas = st.session_state.get("min_areas", 3)
paridad_pct = st.session_state.get("paridad_pct", 40)
h_min_default = (
    cfg.H_MIN_SO if modalidad_code == "SO"
    else cfg.H_MIN_UEI if modalidad_code == "UEI"
    else cfg.H_MIN_MDM
)
h_min = st.session_state.get("h_min", h_min_default)
eu_min_default = 4 if modalidad_code == "SO" else 1 if modalidad_code == "UEI" else 2
eu_min = st.session_state.get("eu_min", eu_min_default)
top_pct_max = st.session_state.get("top_pct_max", 100.0)
top_pct_source = st.session_state.get("top_pct_source", "field")

cluster_btn = st.button(
    "Detectar nucleos", type="primary",
    use_container_width=True, icon=":material/hub:",
)

if cluster_btn:
    with st.spinner(
        "Detectando y valorando nucleos (scoring multidimensional + IA)..."
    ):
        K_full = compute_K(raw, docs)
        all_nucleos, llm_result = detect_and_score_nucleos(
            raw, E, K_full,
            max_clusters=5, max_total=7,
            modalidad="MdM",  # base; los pesos los fija el override neutro
            n_garantes=cfg.NUCLEO_SIZE_LAB * 2,
            pesos_override=cfg.PESOS_NUCLEO_LAB,
            size_override=cfg.NUCLEO_SIZE_LAB,
        )

    # Ejecutar MIP para cada nucleo
    with st.spinner("Optimizando grupos completos para cada nucleo..."):
        clusters = []
        for nucleo in all_nucleos:
            # Solo el nucleo Louvain es hard-fixed
            fixed = list(nucleo["indices"])
            if len(fixed) > n_garantes:
                fixed = sorted(fixed, key=lambda i: -E[i])[:n_garantes]

            # Resolver refuerzos IA a indices
            refuerzos_indices = []
            for ref in nucleo.get("refuerzos_ia", []):
                nombre = ref.get("nombre", "")
                matches = [
                    i for i, r in enumerate(raw)
                    if r["nombre_completo"] == nombre
                ]
                if matches and matches[0] not in fixed:
                    refuerzos_indices.append(matches[0])

            # Intentar con nucleo + refuerzos como fixed
            all_fixed = fixed + refuerzos_indices
            if len(all_fixed) > n_garantes:
                all_fixed = fixed + sorted(
                    refuerzos_indices, key=lambda i: -E[i]
                )[:n_garantes - len(fixed)]

            sel, z = run_mip(
                raw, E, K_full, n_garantes,
                min_areas=min_areas,
                min_paridad=paridad_pct / 100.0,
                fixed_indices=all_fixed,
                modalidad=modalidad_code,
                h_min=h_min, eu_min=eu_min,
                top_pct_max=top_pct_max,
                top_pct_source=top_pct_source,
            )

            if sel is None:
                # Refuerzos violan restricciones -> solo nucleo como fixed
                sel, z = run_mip(
                    raw, E, K_full, n_garantes,
                    min_areas=min_areas,
                    min_paridad=paridad_pct / 100.0,
                    fixed_indices=fixed,
                    modalidad=modalidad_code,
                    h_min=h_min, eu_min=eu_min,
                    top_pct_max=top_pct_max,
                    top_pct_source=top_pct_source,
                )

            if sel is None:
                # Nucleo completo inviable -> intentar con subconjunto
                if len(fixed) > 2:
                    fixed_sub = sorted(
                        fixed, key=lambda i: -E[i]
                    )[:max(2, len(fixed) // 2)]
                    sel, z = run_mip(
                        raw, E, K_full, n_garantes,
                        min_areas=min_areas,
                        min_paridad=paridad_pct / 100.0,
                        fixed_indices=fixed_sub,
                        modalidad=modalidad_code,
                        h_min=h_min, eu_min=eu_min,
                        top_pct_max=top_pct_max,
                        top_pct_source=top_pct_source,
                    )

            if sel is None:
                continue

            diag = compute_diagnostico(
                sel, raw, K_full, n_garantes,
                modalidad=modalidad_code,
                db_name=st.session_state.get("instituto"),
            )
            clusters.append({
                "nucleo": nucleo,
                "refuerzos_indices": refuerzos_indices,
                "seleccionados": sel,
                "z_total": z,
                "diagnostico": diag,
            })

    st.session_state.clusters = clusters
    st.session_state.clusters_K = K_full
    st.session_state.llm_nucleos = llm_result

if st.session_state.clusters is not None:
    clusters = st.session_state.clusters
    _llm_res = st.session_state.get("llm_nucleos") or {}
    if _llm_res.get("error"):
        st.warning(
            f"Analisis IA no disponible: {_llm_res['error']}. "
            "Se muestran solo los grupos algoritmicos.",
            icon=":material/warning:",
        )
    if not clusters:
        st.warning("No se encontraron nucleos viables.")
    else:
        st.success(f"{len(clusters)} grupos con potencial detectados.")
        for idx, cl in enumerate(clusters):
            nuc = cl["nucleo"]
            diag = cl["diagnostico"]
            m = diag["metricas"]
            v = diag["valoracion"]

            color = (
                ":green" if v == "COMPETITIVO"
                else ":orange" if v == "MEJORABLE"
                else ":red"
            )
            validado = nuc.get("validado", True)
            val_icon = "[OK]" if validado else "[!]"
            # Header shows top members of final group
            sel_names = [
                short_name(raw[i]["nombre_completo"])
                for i in cl["seleccionados"][:4]
            ]
            header = f"Grupo {idx+1} {val_icon}: {', '.join(sel_names)}"
            if len(cl["seleccionados"]) > 4:
                header += f" (+{len(cl['seleccionados'])-4})"

            with st.expander(
                f"{header} -- {color}[{v}]", expanded=(idx == 0)
            ):
                # Validacion IA
                justif = nuc.get("justificacion_ia", "")
                if justif:
                    if validado:
                        st.success(
                            f"**IA:** {justif}",
                            icon=":material/check_circle:",
                        )
                    else:
                        st.warning(
                            f"**IA:** {justif}",
                            icon=":material/warning:",
                        )

                # Scoring multidimensional
                scoring = nuc.get("scoring", {})
                if scoring:
                    st.caption("**Scoring multidimensional del nucleo**")
                    sc_cols = st.columns(6)
                    labels = [
                        ("Cohesion", "cohesion"),
                        ("Top mundial", "top_mundial"),
                        ("Diversidad", "diversidad_areas"),
                        ("Equilibrio", "equilibrio_senior_junior"),
                        ("Tendencia", "tendencia"),
                        ("Intl/EU", "internacionalizacion"),
                    ]
                    for col, (lbl, key) in zip(sc_cols, labels):
                        with col:
                            val_sc = scoring.get(key, 0)
                            st.metric(lbl, f"{val_sc:.2f}")

                # Refuerzos propuestos por IA
                refuerzos = nuc.get("refuerzos_ia", [])
                if refuerzos:
                    st.caption("**Refuerzos propuestos por IA**")
                    has_discarded = False
                    for ref in refuerzos:
                        nombre = ref.get("nombre", "")
                        razon = ref.get("razon", "")
                        matches = [
                            i for i, r in enumerate(raw)
                            if r["nombre_completo"] == nombre
                        ]
                        in_sel = (
                            matches[0] in cl["seleccionados"] if matches else False
                        )
                        if not in_sel:
                            has_discarded = True
                        icon = "[OK]" if in_sel else "[X]"
                        st.markdown(f"- {icon} **{nombre}** -- {razon}")
                    if has_discarded:
                        st.caption(
                            "[OK] = incluido en grupo final por MIP | "
                            "[X] = descartado por restricciones"
                        )

                st.divider()

                # Metricas del nucleo
                col_n1, col_n2, col_n3 = st.columns(3)
                with col_n1, st.container(border=True):
                    st.metric(
                        "K medio nucleo", f"{nuc['k_mean']:.3f}",
                        help="Cohesion media entre los miembros del nucleo. "
                             ">0.1 indica colaboracion real",
                    )
                with col_n2, st.container(border=True):
                    st.metric(
                        "E_i medio nucleo", f"{nuc['e_mean']:.3f}",
                        help="Excelencia media de los miembros del nucleo (0-1)",
                    )
                with col_n3, st.container(border=True):
                    st.metric(
                        "Areas nucleo", f"{len(nuc['areas'])}",
                        help="N de areas tematicas del nucleo. "
                             "Mas areas = mayor interdisciplinariedad",
                    )
                st.caption(f"Areas: {', '.join(nuc['areas'])}")

                st.divider()

                # Metricas del grupo completo
                col_g1, col_g2, col_g3, col_g4 = st.columns(4)
                with col_g1, st.container(border=True):
                    st.metric(
                        "Valoracion", v,
                        help="COMPETITIVO: buenas opciones. MEJORABLE: "
                             "trabajar debilidades. DIFICIL: mejoras "
                             "sustanciales necesarias",
                    )
                    if v == "COMPETITIVO":
                        st.badge(
                            "COMPETITIVO",
                            icon=":material/check:", color="green",
                        )
                    elif v == "MEJORABLE":
                        st.badge(
                            "MEJORABLE",
                            icon=":material/warning:", color="orange",
                        )
                    else:
                        st.badge(
                            "DIFICIL",
                            icon=":material/close:", color="red",
                        )
                with col_g2, st.container(border=True):
                    st.metric(
                        "h-index medio", f"{m['h_mean']}",
                        help="Promedio del h-index del grupo completo",
                    )
                with col_g3, st.container(border=True):
                    st.metric(
                        "Cohesion media", f"{m['k_mean']}",
                        help="Promedio de copublicaciones entre garantes "
                             "del grupo",
                    )
                with col_g4, st.container(border=True):
                    st.metric(
                        "Paridad", f"{m['mujeres_pct']:.0f}%",
                        help="No obligatorio, pero criterio de desempate "
                             "entre candidaturas similares",
                    )

                # Tabla del grupo propuesto
                K_cl = st.session_state.clusters_K
                tabla_cl = []
                refuerzos_in_sel = (
                    set(cl.get("refuerzos_indices", []))
                    & set(cl["seleccionados"])
                )
                for rank, i in enumerate(cl["seleccionados"], 1):
                    r = raw[i]
                    if i in nuc["indices"]:
                        rol = "* Nucleo"
                    elif i in refuerzos_in_sel:
                        rol = "+ Refuerzo IA"
                    else:
                        rol = "- MIP"
                    k_med = k_medio_individual(K_cl, i, cl["seleccionados"])
                    tabla_cl.append({
                        "Rol": rol,
                        "Nombre": r["nombre_completo"],
                        "Area": r["area"],
                        "Genero": r["genero"],
                        "h": r["h_index"],
                        "E_i": round(r["E_i"], 3),
                        "K med": round(k_med, 3),
                        "Tendencia": round(r.get("tendencia", 0), 3),
                    })
                df_cl = pd.DataFrame(tabla_cl)
                df_cl_styled = df_cl.style.map(
                    _color_nucleo, subset=["Rol"]
                ).map(
                    _color_tendencia, subset=["Tendencia"]
                )
                st.dataframe(
                    df_cl_styled,
                    use_container_width=True, hide_index=True,
                    column_config={
                        "Rol": st.column_config.TextColumn(
                            "Rol",
                            help="* = nucleo detectado | + = refuerzo "
                                 "propuesto por IA | - = completado por MIP",
                            width="small",
                        ),
                        "E_i": st.column_config.ProgressColumn(
                            "E_i",
                            help="Excelencia individual (0-1)",
                            format="%.3f", min_value=0, max_value=1,
                        ),
                        "K med": st.column_config.ProgressColumn(
                            "K med",
                            help="Cohesion media con el resto del grupo",
                            format="%.3f", min_value=0, max_value=1,
                        ),
                        "h": st.column_config.NumberColumn(
                            "h", help="Indice h combinado",
                        ),
                        "Tendencia": st.column_config.NumberColumn(
                            "Tendencia",
                            help="Tendencia de produccion. >0 = creciendo",
                            format="%.3f",
                        ),
                    },
                )

                # Boton usar este grupo
                if st.button(
                    "Usar este grupo", key=f"use_cluster_{idx}"
                ):
                    st.session_state.seleccionados = cl["seleccionados"]
                    st.session_state.K = K_cl
                    st.session_state.raw_f = raw
                    st.session_state.E_f = E
                    st.session_state.docs_f = docs
                    st.session_state.z_total = cl["z_total"]
                    st.session_state.params = {
                        "N": n_garantes, "alpha": 1.0, "beta": 0.0,
                        "min_areas": min_areas, "paridad_pct": paridad_pct,
                        "modalidad": modalidad_code, "h_min": h_min,
                        "eu_min": eu_min,
                        "db_name": st.session_state.get("instituto"),
                        "pesos": {},
                        "top_pct_max": top_pct_max,
                        "top_pct_source": top_pct_source,
                        "director_idx": None,
                        "fixed_indices": [],
                    }
                    st.session_state.diagnostico = cl.get("diagnostico")
                    st.toast(
                        "Grupo cargado. Ve a la pagina Resultado para "
                        "ver el detalle.",
                        icon=":material/check_circle:",
                    )

        # ── Comparacion radar entre grupos ──
        if len(clusters) >= 2:
            sac.divider(
                label="Comparar grupos", icon="radar", color="dark"
            )
            col_cmp1, col_cmp2 = st.columns(2)
            group_names = [
                f"Grupo {i+1}" for i in range(len(clusters))
            ]
            with col_cmp1:
                g1_sel = st.selectbox(
                    "Grupo A", group_names, index=0, key="radar_g1"
                )
            with col_cmp2:
                g2_sel = st.selectbox(
                    "Grupo B", group_names, index=1, key="radar_g2"
                )
            g1_idx = group_names.index(g1_sel)
            g2_idx = group_names.index(g2_sel)

            def _group_dims_mean(cl_idx):
                cl_sel = clusters[cl_idx]["seleccionados"]
                return [
                    np.mean([
                        raw[i].get("dims_norm", {}).get(k, 0)
                        for i in cl_sel
                    ])
                    for k in DIM_KEYS
                ]

            vals_g1 = _group_dims_mean(g1_idx)
            vals_g2 = _group_dims_mean(g2_idx)
            fig_cmp = go.Figure()
            fig_cmp.add_trace(go.Scatterpolar(
                r=vals_g1 + [vals_g1[0]],
                theta=DIM_LABELS + [DIM_LABELS[0]],
                name=g1_sel, fill='toself', line_color=_BRAND_PRIMARY,
            ))
            fig_cmp.add_trace(go.Scatterpolar(
                r=vals_g2 + [vals_g2[0]],
                theta=DIM_LABELS + [DIM_LABELS[0]],
                name=g2_sel, fill='toself', line_color='#2E7D32',
            ))
            fig_cmp.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
                showlegend=True, height=400,
                margin=dict(t=30, b=30),
            )
            st.plotly_chart(fig_cmp, use_container_width=True)
