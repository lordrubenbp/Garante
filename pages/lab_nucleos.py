#!/usr/bin/env python3
"""Lab: Nucleos colaborativos -- deteccion de grupos con potencial."""
import sys
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "optimizer"))
import config as cfg
from mip_garantes import (
    load_investigators, compute_E, compute_K,
    run_mip, compute_diagnostico,
)
from utils import k_medio_individual, short_name, detect_and_score_nucleos

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ui.wizard_common import render_tool_instituto_selector, _pretty_institute

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


# ── Page header ──
st.title("Nucleos colaborativos")
st.caption(
    "Deteccion de nucleos con potencial colaborativo. Exploracion "
    "modalidad-agnostica: investigadores que si empiezan a colaborar podrian "
    "formar un equipo competitivo a futuro. El scoring multidimensional "
    "identifica combinaciones estrategicas y la IA propone refuerzos para "
    "completar cada grupo."
)

# ── Instituto / modalidad selector (independiente del wizard) ──
instituto, modalidad_code = render_tool_instituto_selector()

docs, E, raw = _load_data(instituto, modalidad_code)
st.caption(f"{len(raw)} investigadores disponibles · {_pretty_institute(instituto)}")

# ── State init — invalida si cambia el instituto ──
if st.session_state.get("_clusters_instituto") != instituto:
    st.session_state.clusters = None
    st.session_state.clusters_K = None
    st.session_state.llm_nucleos = None
    st.session_state["_clusters_instituto"] = instituto

# ── MIP parameters (defaults / from wizard session state) ──
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
top_pct_source = st.session_state.get("top_pct_source", "any")

# ── Detect button ──
cluster_btn = st.button(
    "Detectar nucleos",
    type="primary",
    use_container_width=True,
    icon=":material/hub:",
)

if cluster_btn:
    with st.spinner("Detectando y valorando nucleos (scoring multidimensional + IA)..."):
        K_full = compute_K(raw, docs)
        all_nucleos, llm_result = detect_and_score_nucleos(
            raw, E, K_full,
            max_clusters=5, max_total=7,
            modalidad="MdM",
            n_garantes=cfg.NUCLEO_SIZE_LAB * 2,
            pesos_override=cfg.PESOS_NUCLEO_LAB,
            size_override=cfg.NUCLEO_SIZE_LAB,
        )

    with st.spinner("Optimizando grupos completos para cada nucleo..."):
        clusters = []
        for nucleo in all_nucleos:
            fixed = list(nucleo["indices"])
            if len(fixed) > n_garantes:
                fixed = sorted(fixed, key=lambda i: -E[i])[:n_garantes]

            refuerzos_indices = []
            for ref in nucleo.get("refuerzos_ia", []):
                nombre = ref.get("nombre", "")
                matches = [i for i, r in enumerate(raw) if r["nombre_completo"] == nombre]
                if matches and matches[0] not in fixed:
                    refuerzos_indices.append(matches[0])

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

            if sel is None and len(fixed) > 2:
                fixed_sub = sorted(fixed, key=lambda i: -E[i])[:max(2, len(fixed) // 2)]
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
                db_name=instituto,
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

# ── Show results ──
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
        st.stop()

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
        val_icon = "✓" if validado else "⚠"
        sel_names = [short_name(raw[i]["nombre_completo"]) for i in cl["seleccionados"][:4]]
        header = f"Grupo {idx+1} {val_icon}: {', '.join(sel_names)}"
        if len(cl["seleccionados"]) > 4:
            header += f" (+{len(cl['seleccionados'])-4})"

        with st.expander(f"{header} · {color}[{v}]", expanded=(idx == 0)):
            # Validacion IA
            justif = nuc.get("justificacion_ia", "")
            if justif:
                if validado:
                    st.success(f"**IA:** {justif}", icon=":material/check_circle:")
                else:
                    st.warning(f"**IA:** {justif}", icon=":material/warning:")

            # Scoring multidimensional
            scoring = nuc.get("scoring", {})
            if scoring:
                st.markdown("**Scoring multidimensional del nucleo**")
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
                        st.metric(lbl, f"{scoring.get(key, 0):.2f}")

            # Refuerzos IA
            refuerzos = nuc.get("refuerzos_ia", [])
            if refuerzos:
                st.markdown("**Refuerzos propuestos por IA**")
                has_discarded = False
                for ref in refuerzos:
                    nombre = ref.get("nombre", "")
                    razon = ref.get("razon", "")
                    matches = [i for i, r in enumerate(raw) if r["nombre_completo"] == nombre]
                    in_sel = matches[0] in cl["seleccionados"] if matches else False
                    if not in_sel:
                        has_discarded = True
                    icon = "✓" if in_sel else "✗"
                    st.markdown(f"- {icon} **{nombre}** — {razon}")
                if has_discarded:
                    st.caption(
                        "✓ = incluido en grupo final por MIP | "
                        "✗ = descartado por restricciones"
                    )

            # Metricas del nucleo
            col_n1, col_n2, col_n3 = st.columns(3)
            with col_n1, st.container(border=True):
                st.metric("K medio nucleo", f"{nuc['k_mean']:.3f}",
                          help="Cohesion media entre los miembros del nucleo. >0.1 = colaboracion real")
            with col_n2, st.container(border=True):
                st.metric("E_i medio nucleo", f"{nuc['e_mean']:.3f}",
                          help="Excelencia media de los miembros del nucleo (0-1)")
            with col_n3, st.container(border=True):
                st.metric("Areas nucleo", f"{len(nuc['areas'])}",
                          help="N de areas tematicas del nucleo")
            st.caption(f"Areas: {', '.join(nuc['areas'])}")

            # Metricas del grupo completo
            col_g1, col_g2, col_g3, col_g4 = st.columns(4)
            with col_g1, st.container(border=True):
                st.metric("Valoracion", v)
                if v == "COMPETITIVO":
                    st.badge("COMPETITIVO", icon=":material/check:", color="green")
                elif v == "MEJORABLE":
                    st.badge("MEJORABLE", icon=":material/warning:", color="orange")
                else:
                    st.badge("DIFICIL", icon=":material/close:", color="red")
            with col_g2, st.container(border=True):
                st.metric("h-index medio", f"{m['h_mean']}")
            with col_g3, st.container(border=True):
                st.metric("Cohesion media", f"{m['k_mean']}")
            with col_g4, st.container(border=True):
                st.metric("Paridad", f"{m['mujeres_pct']:.0f}%")

            # Tabla del grupo
            K_cl = st.session_state.clusters_K
            tabla_cl = []
            refuerzos_in_sel = (
                set(cl.get("refuerzos_indices", [])) & set(cl["seleccionados"])
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
            df_cl_styled = (
                df_cl.style
                .map(_color_nucleo, subset=["Rol"])
                .map(_color_tendencia, subset=["Tendencia"])
            )
            st.dataframe(
                df_cl_styled,
                use_container_width=True, hide_index=True,
                column_config={
                    "Rol": st.column_config.TextColumn(
                        "Rol",
                        help="* = nucleo detectado | + = refuerzo IA | - = completado por MIP",
                        width="small",
                    ),
                    "E_i": st.column_config.ProgressColumn(
                        "E_i", format="%.3f", min_value=0, max_value=1,
                    ),
                    "K med": st.column_config.ProgressColumn(
                        "K med", format="%.3f", min_value=0, max_value=1,
                    ),
                    "h": st.column_config.NumberColumn("h"),
                    "Tendencia": st.column_config.NumberColumn("Tendencia", format="%.3f"),
                },
            )

            # Usar este grupo en el wizard
            if st.button("Usar este grupo", key=f"use_cluster_{idx}"):
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
                    "db_name": instituto,
                    "pesos": {},
                    "top_pct_max": top_pct_max,
                    "top_pct_source": top_pct_source,
                    "director_idx": None,
                    "fixed_indices": [],
                }
                st.session_state.diagnostico = cl.get("diagnostico")
                st.session_state["modalidad"] = modalidad_code
                st.session_state["instituto"] = instituto
                # Limpiar evaluaciones de runs anteriores
                st.session_state.pop("evaluacion_fase1", None)
                st.session_state.pop("evaluacion_fase2", None)
                st.session_state.wizard_step = max(
                    st.session_state.get("wizard_step", 1), 3
                )
                st.switch_page("pages/2_preseleccion.py")

    # ── Comparacion radar entre grupos ──
    if len(clusters) >= 2:
        st.subheader(":material/radar: Comparar grupos", divider="blue")
        col_cmp1, col_cmp2 = st.columns(2)
        group_names = [f"Grupo {i+1}" for i in range(len(clusters))]
        with col_cmp1:
            g1_sel = st.selectbox("Grupo A", group_names, index=0, key="radar_g1")
        with col_cmp2:
            g2_sel = st.selectbox("Grupo B", group_names, index=1, key="radar_g2")
        g1_idx = group_names.index(g1_sel)
        g2_idx = group_names.index(g2_sel)

        def _group_dims_mean(cl_idx):
            cl_sel = clusters[cl_idx]["seleccionados"]
            return [
                np.mean([raw[i].get("dims_norm", {}).get(k, 0) for i in cl_sel])
                for k in DIM_KEYS
            ]

        vals_g1 = _group_dims_mean(g1_idx)
        vals_g2 = _group_dims_mean(g2_idx)
        fig_cmp = go.Figure()
        fig_cmp.add_trace(go.Scatterpolar(
            r=vals_g1 + [vals_g1[0]], theta=DIM_LABELS + [DIM_LABELS[0]],
            name=g1_sel, fill='toself', line_color='#002045',
        ))
        fig_cmp.add_trace(go.Scatterpolar(
            r=vals_g2 + [vals_g2[0]], theta=DIM_LABELS + [DIM_LABELS[0]],
            name=g2_sel, fill='toself', line_color='#2E7D32',
        ))
        fig_cmp.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
            showlegend=True, height=400, margin=dict(t=30, b=30),
        )
        st.plotly_chart(fig_cmp, use_container_width=True)
