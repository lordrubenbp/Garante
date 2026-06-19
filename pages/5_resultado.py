#!/usr/bin/env python3
"""Paso 5: Resultado final — resumen, calificacion global, exportar PDF/CSV/Excel."""
import sys
import os
import json as _json
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "optimizer"))
import config as cfg
from utils import k_medio_individual

from ui.wizard_common import (
    render_progress_bar, wizard_nav, require_step,
    get_instituto_label, get_modalidad_label,
)

# ── Gate ──
require_step(5)

if any(st.session_state.get(k) is None for k in ("seleccionados", "raw_f", "K", "params")):
    st.warning("Sesion expirada o datos no disponibles. Vuelve al Paso 1 y ejecuta la optimizacion.")
    st.stop()

# ── Load state ──
sel = st.session_state.seleccionados
r_f = st.session_state.raw_f
K = st.session_state.K
z = st.session_state.z_total
stored_params = st.session_state.params
modalidad_code = stored_params.get("modalidad", "MdM")
diag = st.session_state.get("diagnostico", {})
fase1 = st.session_state.get("evaluacion_fase1")
fase2 = st.session_state.get("evaluacion_fase2")

# ── Header ──
render_progress_bar(5)
st.title("Resultado de la evaluacion")
st.caption(f"{get_instituto_label()} · {get_modalidad_label(modalidad_code)}")

# ── Summary ──
st.subheader(":material/scoreboard: Resumen ejecutivo")
col1, col2, col3 = st.columns(3)

with col1, st.container(border=True):
    if fase1:
        superan = fase1.get("superan_umbral", 0)
        necesarios = fase1.get("necesarios", 6)
        f1_ok = fase1.get("superada_fase1", False)
        st.metric("Fase 1", f"{superan}/{necesarios}",
                  delta="SUPERADA" if f1_ok else "NO SUPERADA",
                  delta_color="normal" if f1_ok else "inverse")
    else:
        st.metric("Fase 1", "No evaluada")

with col2, st.container(border=True):
    if fase2:
        total = fase2.get("puntuacion_total", 0)
        f2_ok = fase2.get("acreditable", False)
        st.metric("Fase 2", f"{total}/100",
                  delta="SUPERADA" if f2_ok else "NO SUPERADA",
                  delta_color="normal" if f2_ok else "inverse")
    else:
        st.metric("Fase 2", "No evaluada")

with col3, st.container(border=True):
    if fase1 and fase2:
        acreditacion = fase1.get("superada_fase1", False) and fase2.get("acreditable", False)
        st.metric("Veredicto", "ACREDITACION" if acreditacion else "NO ACREDITACION")
    else:
        st.metric("Veredicto", "Pendiente", help="Completa ambas fases para ver el veredicto")

# ── Equipo definitivo ──
st.subheader(":material/groups: Equipo definitivo de garantes")
equipo_data = []
for rank, i in enumerate(sel, 1):
    r = r_f[i]
    k_med = k_medio_individual(K, i, sel)
    pts_f1 = ""
    if fase1:
        for ev in fase1.get("evaluaciones", []):
            if ev.get("nombre", "") == r["nombre_completo"]:
                pts_f1 = f"{ev.get('puntuacion', '?')}/10"
                break
    equipo_data.append({
        "#": rank,
        "Nombre": r["nombre_completo"],
        "Area": r["area"],
        "E_i": round(r["E_i"], 4),
        "h-index": r["h_index"],
        "EU": r.get("proyectos_eu", 0),
        "Fase 1": pts_f1,
    })
st.dataframe(
    pd.DataFrame(equipo_data),
    use_container_width=True, hide_index=True,
    column_config={
        "#": st.column_config.NumberColumn("#", width="small"),
        "E_i": st.column_config.ProgressColumn(
            "E_i",
            help="Excelencia individual (0-1). Suma ponderada de 11 dimensiones normalizadas.",
            format="%.4f",
            min_value=0,
            max_value=1,
        ),
        "h-index": st.column_config.NumberColumn("h-index", help="Indice h consolidado"),
        "EU": st.column_config.NumberColumn("EU", help="Proyectos europeos"),
    },
)

# ── Diagnostico ──
if diag:
    st.subheader(":material/insights: Diagnostico consolidado")
    v = diag.get("valoracion", "")
    if v:
        _v_colors = {"COMPETITIVO": "green", "MEJORABLE": "orange", "DIFICIL": "red"}
        _vc = _v_colors.get(v, "blue")
        st.markdown(f":{_vc}-badge[**{v}**]")
    col_f, col_d = st.columns(2)
    with col_f:
        st.markdown("**:material/thumb_up: Fortalezas**")
        for f in diag.get("fortalezas", []):
            st.markdown(f"- {f}")
        if not diag.get("fortalezas"):
            st.caption("Sin fortalezas destacables")
    with col_d:
        st.markdown("**:material/warning: Debilidades**")
        for d in diag.get("debilidades", []):
            st.markdown(f"- {d}")
        if not diag.get("debilidades"):
            st.caption("Sin debilidades destacables")

# ── Export ──
st.space("small")
st.subheader(":material/download: Exportar resultados")

@st.cache_data(show_spinner=False)
def _build_pdf(sel_tuple, raw_list, K_list, z_val, params_frozen, diag_frozen):
    from optimizer.report_pdf import generate_report_pdf
    diag_local = _json.loads(diag_frozen) if diag_frozen else None
    return generate_report_pdf(
        list(sel_tuple), raw_list, K_list, z_val, dict(params_frozen),
        diagnostico=diag_local,
    )

_inst_name = cfg.get_instituto_info(st.session_state.get("instituto", cfg.DB_NAME))["nombre"]
_diag_frozen = _json.dumps(diag, default=str) if diag else None

try:
    _pdf_bytes = _build_pdf(
        tuple(sel), r_f, K, z, tuple(sorted(stored_params.items())), _diag_frozen
    )
    st.download_button(
        label="Descargar informe PDF",
        data=_pdf_bytes,
        file_name=f"propuesta_garantes_{_inst_name}.pdf",
        mime="application/pdf",
        type="primary",
        icon=":material/picture_as_pdf:",
        use_container_width=True,
    )
except FileNotFoundError as _fe:
    st.error(f"No se encontro la fuente necesaria para el PDF: {_fe}")
except Exception as _pe:
    st.error(f"Error generando PDF: {_pe}")

st.caption("Datos del equipo en formato tabular:")
st.space("small")


export_data = []
for rank, i in enumerate(sel, 1):
    r = r_f[i]
    k_med = k_medio_individual(K, i, sel)
    export_data.append({
        "Rank": rank,
        "Nombre": r["nombre_completo"],
        "Genero": r["genero"],
        "Area": r["area"],
        "Figura": r["figura"],
        "Grupo": r.get("grupo", ""),
        "h-index": r["h_index"],
        "h (OA)": r.get("h_openalex", 0),
        "i10": r.get("i10_index", 0),
        "E_i": round(r["E_i"], 4),
        "K medio": round(k_med, 4),
        "Tendencia": r["tendencia"],
        "Impacto art.": r.get("impacto_art", 0),
        "Proyectos EU": r.get("proyectos_eu", 0),
        "IPs": r["proyectos_ip"],
        "Tesis dirigidas": r["tesis_dir"],
        "Instituciones intl": r.get("instituciones_intl", 0),
    })
df_export = pd.DataFrame(export_data)

from io import BytesIO as _BytesIO
_excel_buffer = _BytesIO()
df_export.to_excel(_excel_buffer, index=False, sheet_name="Garantes")
_csv_data = df_export.to_csv(index=False).encode("utf-8")

with st.container(horizontal=True):
    st.download_button(
        label="Descargar CSV",
        data=_csv_data,
        file_name=f"garantes_{_inst_name}.csv",
        mime="text/csv",
        icon=":material/table:",
        use_container_width=True,
    )
    st.download_button(
        label="Descargar Excel",
        data=_excel_buffer.getvalue(),
        file_name=f"garantes_{_inst_name}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        icon=":material/grid_on:",
        use_container_width=True,
    )

st.dataframe(df_export, use_container_width=True, hide_index=True)

# ── Navigation (only back) ──
wizard_nav(5, can_advance=False)
