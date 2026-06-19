#!/usr/bin/env python3
"""Paso 4: Evaluacion Fase 2 — subida de PDF y evaluacion LLM de memoria/plan."""
import sys
import os
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "optimizer"))
import config as cfg

from ui.wizard_common import (
    render_progress_bar, wizard_nav, require_step,
    get_instituto_label, get_modalidad_label,
)

# ── Gate ──
require_step(4)

if st.session_state.get("params") is None:
    st.warning("Sesion expirada o datos no disponibles. Vuelve al Paso 1 y ejecuta la optimizacion.")
    st.stop()

# ── Load state ──
stored_params = st.session_state.params
modalidad_code = stored_params.get("modalidad", "MdM")

# ── Header ──
render_progress_bar(4)
st.title("Evaluacion Fase 2")
st.caption(f"{get_instituto_label()} · {get_modalidad_label(modalidad_code)}")
with st.expander("Como funciona esta evaluacion", icon=":material/info:"):
    st.markdown("""
La Fase 2 evalua la **propuesta como conjunto** (0-100, umbral 95):

- **Memoria de actividades** (0-50, umbral 40): organizacion, resultados, liderazgo internacional
- **Plan estrategico** (0-50, umbral 40): objetivos, viabilidad, actividades transversales

Sube la propuesta en PDF para que el comite de IA la evalue.
""")

# ── PDF Upload ──
uploaded_pdf = st.file_uploader("Sube la propuesta (PDF)", type=["pdf"])

result = st.session_state.get("evaluacion_fase2")

if uploaded_pdf is not None:
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(uploaded_pdf)
        pdf_text = ""
        for page in reader.pages:
            pdf_text += page.extract_text() or ""
    except Exception as e:
        st.error(f"Error leyendo el PDF: {e}")
        st.stop()

    if len(pdf_text.strip()) < 100:
        st.warning("El PDF parece estar vacio o contener muy poco texto. Asegurate de que es un PDF con texto seleccionable (no escaneado).")

    st.success(f"PDF cargado: {len(reader.pages)} páginas, {len(pdf_text):,} caracteres.", icon=":material/picture_as_pdf:")

    btn_evaluar = st.button(
        "Re-evaluar propuesta" if result else "Evaluar propuesta",
        type="primary", use_container_width=True,
        icon=":material/rate_review:",
    )

    if btn_evaluar:
        if not cfg.ANTHROPIC_API_KEY:
            st.error("Configura ANTHROPIC_API_KEY en .env")
            st.stop()

        from llm_evaluador import evaluar_propuesta_fase2

        sel = st.session_state.seleccionados
        r_f = st.session_state.raw_f
        K = st.session_state.K
        diag = st.session_state.get("diagnostico")

        if not diag:
            st.error("Diagnostico no disponible. Vuelve al paso 2 y ejecuta la preseleccion.")
            st.stop()

        diag_with_pdf = dict(diag)
        diag_with_pdf["texto_propuesta"] = pdf_text[:50000]

        sel_raw = [r_f[i] for i in sel]

        with st.spinner("Evaluando propuesta (Fase 2)..."):
            result = evaluar_propuesta_fase2(
                diag_with_pdf, sel_raw, stored_params,
                modalidad=modalidad_code,
                db_name=st.session_state.get("instituto"),
            )

        if result and "error" not in result:
            st.session_state.evaluacion_fase2 = result
        else:
            st.error(f"Error en evaluacion Fase 2: {(result or {}).get('error', 'sin respuesta del modelo')}")
            st.stop()

if result is not None:
    st.subheader(":material/fact_check: Resultado Fase 2")

    mem = result.get("memoria_actividades", {})
    plan = result.get("plan_estrategico", {})

    col1, col2, col3 = st.columns(3)
    with col1, st.container(border=True):
        sub_mem = mem.get("subtotal_memoria", 0)
        st.metric("Memoria de actividades", f"{sub_mem}/50",
                  delta="Supera umbral 40" if mem.get("supera_umbral_memoria") else "No supera umbral 40",
                  delta_color="normal" if mem.get("supera_umbral_memoria") else "inverse")
    with col2, st.container(border=True):
        sub_plan = plan.get("subtotal_plan", 0)
        st.metric("Plan estrategico", f"{sub_plan}/50",
                  delta="Supera umbral 40" if plan.get("supera_umbral_plan") else "No supera umbral 40",
                  delta_color="normal" if plan.get("supera_umbral_plan") else "inverse")
    with col3, st.container(border=True):
        total = result.get("puntuacion_total", 0)
        acreditable = result.get("acreditable", False)
        st.metric("Total", f"{total}/100",
                  delta="ACREDITABLE" if acreditable else "NO ACREDITABLE",
                  delta_color="normal" if acreditable else "inverse")

    with st.expander("Detalle por subcriterio", expanded=False, icon=":material/list_alt:"):
        for label, section in [("Memoria de actividades", mem), ("Plan estrategico", plan)]:
            st.markdown(f"**{label}**")
            for key, val in section.items():
                if isinstance(val, dict) and "puntuacion" in val:
                    st.markdown(f"- {key}: {val['puntuacion']}/{val.get('max', '?')} — {val.get('justificacion', '')}")

    veredicto = result.get("veredicto_fase2", "")
    if veredicto:
        _verd_fn = st.success if acreditable else st.error
        _verd_fn(f"**Veredicto:** {veredicto}", icon=":material/gavel:")

    recs = result.get("recomendaciones_criticas", [])
    if recs:
        st.subheader(":material/priority_high: Recomendaciones criticas")
        for r in recs:
            st.markdown(f"- {r}")

    faltante = result.get("informacion_faltante", [])
    if faltante:
        with st.expander("Informacion faltante para una evaluacion mas precisa", icon=":material/info:"):
            for f in faltante:
                st.markdown(f"- {f}")

can_advance = result is not None
if can_advance:
    st.session_state.wizard_step = max(st.session_state.get("wizard_step", 4), 5)
wizard_nav(4, can_advance=can_advance)
