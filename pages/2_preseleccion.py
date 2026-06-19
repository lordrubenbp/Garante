"""
Paso 2 del wizard: Preseleccion — tabla de garantes, swap, diagnostico.
Clean card-based layout with minimal headers.
"""
import sys
import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "optimizer"))
import config as cfg
from mip_garantes import compute_diagnostico, diagnosticar_casi_garantes
from utils import k_medio_individual

from ui.wizard_common import (
    require_step,
    render_progress_bar,
    wizard_nav,
    get_instituto_label,
    get_modalidad_label,
    color_tendencia,
    color_nivel,
    color_anos_sin,
    color_stanford,
)

# ── Gate ──
require_step(2)

render_progress_bar(current_step=2)
st.title("Preseleccion de garantes")
st.caption(f"{get_instituto_label()} · {get_modalidad_label(st.session_state.get('params', {}).get('modalidad', 'MdM'))}")

# ── Load state ──
sel = st.session_state.seleccionados
r_f = st.session_state.raw_f
E_f = st.session_state.E_f
K = st.session_state.K
docs_f = st.session_state.get("docs_f")
stored_params = st.session_state.get("params", {})

# Guard: optimization must have run before this page is useful
if sel is None or r_f is None:
    st.warning("Ejecuta la optimizacion en el paso 1 primero.")
    st.stop()

diag = st.session_state.get("diagnostico") or compute_diagnostico(
    sel, r_f, K, stored_params.get("N", len(sel)),
    modalidad=stored_params.get("modalidad", "MdM"),
    db_name=stored_params.get("db_name"),
)
st.session_state["diagnostico"] = diag
m = diag["metricas"]

# ── Unlock step 3 ──
st.session_state["wizard_step"] = max(st.session_state.get("wizard_step", 2), 3)

# ── Valoracion alert (subtle) ──
v = diag["valoracion"]
_val_map = {
    "COMPETITIVO": (st.success, ":material/check_circle:", "Buenas probabilidades en la convocatoria SO/MdM"),
    "MEJORABLE":   (st.warning, ":material/construction:",  "Posibilidades si se trabajan las debilidades detectadas"),
    "DIFICIL":     (st.error,   ":material/dangerous:",     "Requiere mejoras sustanciales antes de presentar"),
}
_alert_fn, _alert_icon, _val_desc = _val_map.get(v, (st.info, ":material/info:", ""))
_alert_fn(f"**{v}** — {_val_desc}", icon=_alert_icon)

# ── KPIs — single row of 6 ──
_stored_modalidad = stored_params.get("modalidad", "MdM")
_h_ref = 25.0 if _stored_modalidad == "SO" else 12.0 if _stored_modalidad == "UEI" else 15.0

st.markdown(
    """<style>
    [data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stMetric"]) {
        min-height: 108px;
    }
    </style>""",
    unsafe_allow_html=True,
)

st.markdown(
    """<style>
    [data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stMetric"]) > div {
        min-height: 108px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    [data-testid="stMetricDelta"] {
        display: inline-flex;
        align-items: center;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 500;
    }
    [data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Up"]) {
        background-color: #4caf7d;
        color: #ffffff !important;
    }
    [data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Down"]) {
        background-color: #e57373;
        color: #ffffff !important;
    }
    [data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Up"]) svg,
    [data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Down"]) svg {
        fill: #ffffff !important;
    }
    </style>""",
    unsafe_allow_html=True,
)

c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1, st.container(border=True):
    st.metric(
        "Puntuacion media",
        f"{m['e_mean'] * 10:.2f} / 10",
        help="Promedio del indice de excelencia individual del grupo (E_i × 10)",
    )
with c2, st.container(border=True):
    st.metric(
        "H-index medio",
        f"{m['h_mean']:.1f}",
        delta=f"{m['h_mean'] - _h_ref:+.1f} vs umbral",
        delta_color="normal",
        help="Promedio del indice h del grupo. SO exige ~25, MdM ~15, UEI ~12",
    )
with c3, st.container(border=True):
    st.metric(
        "Diversidad",
        f"{m['areas']} areas",
        delta=f"{m['areas'] - stored_params.get('min_areas', 3):+d} vs minimo",
        delta_color="normal",
        help="Numero de areas tematicas distintas",
    )
with c4, st.container(border=True):
    st.metric(
        "Garantes con EU",
        m.get("garantes_eu", sum(1 for i in sel if r_f[i].get("proyectos_eu", 0) > 0)),
        help="Numero de garantes con al menos un proyecto europeo",
    )
with c5, st.container(border=True):
    st.metric(
        "Paridad",
        f"{m['mujeres_pct']:.0f}% mujeres",
        delta=f"{m['mujeres_pct'] - 40:+.0f}% vs 40%",
        delta_color="normal",
        help="No obligatorio, pero la paridad es criterio de desempate",
    )
with c6, st.container(border=True):
    _tend_mean = np.mean([r_f[i].get("tendencia", 0) for i in sel])
    st.metric(
        "Tendencia media",
        f"{_tend_mean:.3f}",
        help="Promedio de tendencia del grupo. >0.7 ascendente, <0.4 descendente",
    )

# ── Area chips ──
_AREA_PALETTE = [
    "#4caf7d", "#5c8fff", "#ffa040", "#e57373", "#ab72e8",
    "#26c6da", "#f06292", "#8bc34a", "#ff8a65", "#4db6ac",
    "#7986cb", "#a1887f", "#90a4ae", "#ffb74d", "#4dd0e1",
]
_areas_en_sel = sorted(set(r_f[i]["area"] for i in sel if r_f[i].get("area")))
_area_color = {area: _AREA_PALETTE[idx % len(_AREA_PALETTE)] for idx, area in enumerate(_areas_en_sel)}

_chips_html = " ".join(
    f"<span style='"
    f"background:{_area_color[area]};color:#fff;"
    f"padding:3px 12px;border-radius:16px;font-size:0.78rem;font-weight:600;"
    f"margin:2px;display:inline-block;letter-spacing:0.01em'"
    f">{area}</span>"
    for area in _areas_en_sel
)
st.markdown(f"<div style='margin:6px 0 4px'>{_chips_html}</div>", unsafe_allow_html=True)


# ── Helper: escalar E_i (0-1) a escala 0-10 ──
def _ei_to_10(e_i: float) -> float:
    return round(e_i * 10, 2)


def _barra_puntuacion(val):
    return f"{val:.1f}"


def _color_puntuacion(val):
    if val >= 8.5:
        return "background-color: rgba(76,175,125,0.55); color: #181c1e; font-family: monospace"
    if val >= 7.5:
        return "background-color: rgba(139,195,74,0.55); color: #181c1e; font-family: monospace"
    if val >= 6.5:
        return "background-color: rgba(205,220,57,0.55); color: #181c1e; font-family: monospace"
    if val >= 5.5:
        return "background-color: rgba(255,235,59,0.55); color: #181c1e; font-family: monospace"
    if val >= 4.5:
        return "background-color: rgba(255,193,7,0.55); color: #181c1e; font-family: monospace"
    if val >= 4.0:
        return "background-color: rgba(255,160,64,0.55); color: #181c1e; font-family: monospace"
    if val >= 3.0:
        return "background-color: rgba(255,112,67,0.55); color: #181c1e; font-family: monospace"
    if val >= 2.5:
        return "background-color: rgba(229,115,115,0.55); color: #181c1e; font-family: monospace"
    return "background-color: rgba(198,40,40,0.65); color: #181c1e; font-family: monospace"


# ── Helper: classify E_i into a level ──
def _nivel_ei(e_i: float) -> str:
    if e_i >= 0.75:
        return "Excepcional"
    if e_i >= 0.55:
        return "Solido"
    if e_i >= 0.40:
        return "Aceptable"
    if e_i >= 0.25:
        return "Debil"
    return "No apto"


# ── Perfil individual: radar + métricas ──
_DIM_LABELS = [
    "Produccion", "IP", "Tesis", "Tendencia", "EU", "Intl.",
    "Reconoc.", "i10", "Impacto art.", "Sexenios", "Top mundial",
]
_DIM_KEYS = [
    "produccion", "ip", "tesis", "tendencia", "eu", "intl",
    "reconocimiento", "i10", "impacto_art", "sexenios", "top_mundial",
]


@st.dialog("Desglose de excelencia", width="large")
def _show_perfil(idx: int, r: dict):
    dims = r.get("dims_norm", {})

    # ── Cabecera ──
    st.title(r["nombre_completo"])
    st.caption(f"{r.get('area', '')} · {r.get('figura', '')}")

    # ── Métricas fila 1 ──
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1, st.container(border=True):
        st.metric("h-index", r.get("h_index", "—"), help="Índice h combinado (máximo entre Google Scholar, OpenAlex). Mide impacto acumulado: más alto = más publicaciones de alto impacto")
    with c2, st.container(border=True):
        st.metric("Proyectos IP", r.get("proyectos_ip", 0), help="Proyectos donde ha sido Investigador/a Principal a lo largo de toda su carrera investigadora.")
    with c3, st.container(border=True):
        st.metric("Tesis", r.get("tesis_dir", 0), help="Tesis doctorales dirigidas a lo largo de toda su carrera investigadora.")
    with c4, st.container(border=True):
        st.metric("Tendencia", f"{r.get('tendencia', 0):.3f}", help="Evolución reciente de citas. >0 = producción en crecimiento, <0 = en declive. Se penaliza si es negativa")
    with c5, st.container(border=True):
        st.metric("Puntuación", f"{_ei_to_10(r['E_i']):.2f} / 10", help="Puntuación de excelencia en base 10 (E_i normalizado). Más alto = mejor.")

    # ── Métricas fila 2 ──
    c6, c7, c8, c9, c10 = st.columns(5)
    with c6, st.container(border=True):
        st.metric("Proyectos EU", r.get("proyectos_eu", 0), help="Proyectos europeos (H2020, ERC, MSCA…) a lo largo de toda la carrera investigadora. La convocatoria exige un mínimo en el grupo.")
    with c7, st.container(border=True):
        st.metric("Intl.", r.get("instituciones_intl", 0), help="Instituciones internacionales con las que ha colaborado. Más = mayor internacionalización")
    with c8, st.container(border=True):
        st.metric("Reconoc.", r.get("reconocimiento", 0), help="Patentes + distinciones + membresías en comités editoriales o sociedades científicas")
    with c9, st.container(border=True):
        st.metric("i10", r.get("i10_index", 0), help="Publicaciones con 10+ citas (Google Scholar). Complementa al h-index midiendo productividad de impacto")
    with c10, st.container(border=True):
        _calidad_val = r.get("calidad") or r.get("calidad_q")
        _calidad_str = f"{_calidad_val:.2f}" if _calidad_val else "—"
        st.metric("Calidad Q", _calidad_str, help="Media ponderada de cuartiles de revistas: Q1=4, Q2=3, Q3=2, Q4=1. Más alto = publica en mejores revistas")

    # ── Radar con media del grupo ──
    if dims:
        vals_garante = [dims.get(k, 0.0) for k in _DIM_KEYS]
        vals_media = [np.mean([r_f[j].get("dims_norm", {}).get(k, 0) for j in sel]) for k in _DIM_KEYS]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=vals_garante + [vals_garante[0]],
            theta=_DIM_LABELS + [_DIM_LABELS[0]],
            name=r["nombre_completo"],
            fill="toself",
            line_color="#1e3a8a",
        ))
        fig_radar.add_trace(go.Scatterpolar(
            r=vals_media + [vals_media[0]],
            theta=_DIM_LABELS + [_DIM_LABELS[0]],
            name="Media grupo",
            fill="toself",
            opacity=0.3,
            line_color="#16a34a",
        ))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
            showlegend=True, height=350,
            margin=dict(t=30, b=30),
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    # ── Stanford/Elsevier ──
    stan = r.get("stanford_percentil")
    if stan is not None:
        _s_color = "#16a34a" if stan <= 2 else ("#d97706" if stan <= 10 else "#6b7280")
        _s_label = "TOP 2% MUNDIAL" if stan <= 2 else ("TOP 10% MUNDIAL" if stan <= 10 else f"TOP {stan:.1f}%")
        st.markdown(
            f"**Stanford/Elsevier Top Scientists** &nbsp; "
            f'<span style="background:{_s_color};color:white;padding:2px 8px;'
            f'border-radius:4px;font-size:0.85em;font-weight:600;">{_s_label}</span>',
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Percentil mundial", f"{stan:.1f}%", help="Posición en el ranking mundial Stanford/Elsevier. Menor = mejor")
        c2.metric("Subcampo", r.get("stanford_subfield", "—"), help="Subcampo científico según clasificación Stanford/Elsevier")
        c3.metric("Criterio AEI top 10%", "Cumple" if stan <= 10 else "No cumple", help="La convocatoria AEI valora positivamente estar en el top 10% mundial del subcampo")
        st.caption("Fuente: Stanford/Elsevier Top Scientists, single-year 2024 (dataset v8, agosto 2025)")

    # ── OpenAlex c-score (Ioannidis) ──
    oa = r.get("openalex_pct")
    if oa is not None:
        _o_color = "#16a34a" if oa <= 2 else ("#d97706" if oa <= 10 else "#6b7280")
        _o_label = "TOP 2% MUNDIAL" if oa <= 2 else ("TOP 10% MUNDIAL" if oa <= 10 else f"TOP {oa:.1f}%")
        _metric   = r.get("openalex_pct_metric", "")
        _is_cscore = _metric == "cscore_approx"
        _c_approx  = r.get("openalex_pct_capprox")
        oa_valores = r.get("openalex_pct_valores") or {}
        _incompleto = r.get("openalex_pct_incompleto", False)

        _titulo = "c-score Ioannidis (OpenAlex works)" if _is_cscore else "Indicador compuesto OpenAlex"
        _gs_tag = (
            ' <span style="background:#7c3aed;color:white;padding:1px 6px;'
            'border-radius:3px;font-size:0.75em">GS</span>'
            if r.get("openalex_pct_h_source") == "gs" else ""
        )
        st.markdown(
            f"**{_titulo}** &nbsp; "
            f'<span style="background:{_o_color};color:white;padding:2px 8px;'
            f'border-radius:4px;font-size:0.85em;font-weight:600;">{_o_label}</span>'
            f"{_gs_tag}",
            unsafe_allow_html=True,
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("Percentil mundial", f"{oa:.1f}%",
                  help="Posición en el ranking mundial dentro del subfield. Menor = mejor. "
                       "Basado en c-score aproximado de Ioannidis (h, citas, hm, fl, 2yr).")
        c2.metric("Subfield", r.get("openalex_pct_subfield", "—"),
                  help="Subcampo científico OpenAlex (primer topic del investigador)")
        c3.metric("Criterio AEI ≤10%", "Cumple ✓" if oa <= 10 else "No cumple",
                  help="La convocatoria AEI valora positivamente estar en el top 10% mundial del subcampo")

        if _is_cscore and oa_valores:
            # Fila de métricas del c-score
            _h   = oa_valores.get("h_index", 0)
            _nc  = oa_valores.get("cited_by_count", 0)
            _hm  = oa_valores.get("hm", 0)
            _fl  = oa_valores.get("fl_ratio", 0)
            _2yr = oa_valores.get("2yr_mean_citedness", 0)
            _nw  = oa_valores.get("works_descargados")

            mc1, mc2, mc3, mc4, mc5 = st.columns(5)
            mc1.metric("h-index", f"{_h:.0f}",
                       help="H-index OpenAlex (o Google Scholar si perfil OA incompleto)")
            mc2.metric("Citas", f"{_nc:,.0f}",
                       help="Citas totales (cited_by_count OpenAlex)")
            mc3.metric("hm (Schreiber)", f"{_hm:.1f}",
                       help="H-index ajustado por multiautoria: citas/nº_autores por paper → h sobre eso. "
                            "Penaliza investigadores que publican siempre con muchos coautores.")
            mc4.metric("fl ratio", f"{_fl:.0%}",
                       help="Fracción de papers como primer o último autor. "
                            "Proxy de liderazgo investigador (ncsfl en Stanford).")
            mc5.metric("2yr mean", f"{_2yr:.2f}",
                       help="Media de citas en los últimos 2 años (OpenAlex). Mide actividad reciente.")

            if _c_approx is not None:
                _nw_str = f" · {_nw} works descargados" if _nw else ""
                st.caption(
                    f"c-score = {_c_approx:.4f} · fórmula: (nc/500)^0.3 × (h/10)^0.3 × "
                    f"(hm/5)^0.1 × (fl/0.15)^0.1 × (2yr/2)^0.1{_nw_str}"
                )

        if _incompleto:
            st.caption("⚠️ Perfil OpenAlex incompleto — h-index tomado de Google Scholar.")

        st.caption("Fuente: OpenAlex API. hm y fl_ratio calculados desde works reales (author_position).")


# ── Tabla de garantes seleccionados ──
st.subheader(":material/verified_user: Garantes seleccionados")

_alpha_used = stored_params.get("alpha", cfg.ALPHA)
_beta_used = stored_params.get("beta", cfg.BETA)

_scores_final = {}
for i in sel:
    k_med = k_medio_individual(K, i, sel)
    _scores_final[i] = _alpha_used * r_f[i]["E_i"] + _beta_used * k_med

sel_sorted = sorted(sel, key=lambda i: _scores_final[i], reverse=True)

import datetime as _dt
_current_year = cfg.CURRENT_YEAR

tabla = []
for rank, i in enumerate(sel_sorted, 1):
    r = r_f[i]
    ultima = r.get("ultima_publicacion", 0)
    anos_sin = (_current_year - int(ultima)) if ultima and ultima > 0 else None
    tabla.append({
        "N": rank,
        "Nombre": r["nombre_completo"],
        "Genero": r["genero"],
        "Area": r["area"],
        "Figura": r.get("figura", ""),
        "Puntuacion": _ei_to_10(r["E_i"]),
        "h-index": r["h_index"],
        "Tendencia": r["tendencia"],
        "IPs": r.get("proyectos_ip", 0),
        "EU": r.get("proyectos_eu", 0),
        "Intl": r.get("instituciones_intl", 0),
        "i10": r.get("i10_index", 0),
        "Impacto art.": round(r.get("impacto_art", 0), 1),
        "Sexenios": r.get("sexenios", 0),
        "Fecha ult. sexenio": r.get("fecha_ultimo_sexenio", ""),
        "Top%(Stanford)": r.get("stanford_percentil"),
        "Top%(OA)": r.get("openalex_pct"),
        "Anos s/pub": anos_sin,
        "h (GS)": r.get("h_google_scholar") or "---",
        "h (OA)": r.get("h_openalex", 0),
        "h (Dial)": r.get("h_dialnet", 0),
        "Citas": r.get("citas_cruzadas") or r.get("citas_2020", 0),
        "Citas cruzadas": r.get("citas_cruzadas", 0),
        "Tesis": r.get("tesis_dir", 0),
        "EU IP": r.get("proyectos_eu_ip", 0),
        "Ultima pub.": ultima if ultima and ultima > 0 else None,
        "Nivel": _nivel_ei(r["E_i"]),
    })

df_tabla = pd.DataFrame(tabla)
df_tabla["Barra"] = df_tabla["Puntuacion"].apply(_barra_puntuacion)

_big_pool_nombres = {
    r_f[i]["nombre_completo"] for i in sel
    if (r_f[i].get("openalex_pct_total") or 0) > 5_000_000
}

def _color_barra(row):
    styles = [""] * len(row)
    barra_idx = row.index.get_loc("Barra")
    styles[barra_idx] = _color_puntuacion(row["Puntuacion"])
    return styles

def _color_oa_row(row):
    val = row.get("Top%(OA)")
    if row.get("Nombre") in _big_pool_nombres:
        return ["background-color: rgba(92,143,255,0.55); color: #181c1e" if col == "Top%(OA)" else "" for col in row.index]
    return [color_stanford(val) if col == "Top%(OA)" else "" for col in row.index]

df_styled = df_tabla.style.apply(
    _color_barra, axis=1
).map(
    color_tendencia, subset=["Tendencia"]
).map(
    color_nivel, subset=["Nivel"]
).map(
    color_anos_sin, subset=["Anos s/pub"]
).map(
    color_stanford, subset=["Top%(Stanford)"]
).apply(
    _color_oa_row, axis=1, subset=list(df_tabla.columns)
).format(
    {"Tendencia": "{:.3f}", "Impacto art.": "{:.1f}"}
)

_mostrar_todo = st.toggle(
    "Mostrar todos los campos",
    value=False,
    key="sel_mostrar_todo",
    on_change=lambda: st.session_state.pop("perfil_investigador_sel", None),
)

# ── Selector de perfil ──
_sel_name_list = [r_f[i]["nombre_completo"] for i in sel_sorted]
_perfil_sel = st.selectbox(
    "Ver perfil de investigador",
    options=["— selecciona —"] + _sel_name_list,
    index=0,
    key="perfil_investigador_sel",
    label_visibility="collapsed",
    help="Selecciona un investigador para ver su radar de dimensiones y métricas detalladas",
)
if _perfil_sel != "— selecciona —":
    _perfil_idx = next((i for i in sel_sorted if r_f[i]["nombre_completo"] == _perfil_sel), None)
    if _perfil_idx is not None:
        _show_perfil(_perfil_idx, r_f[_perfil_idx])

_col_order_base = ["N", "Nombre", "Genero", "Area", "Barra", "h-index", "Tendencia", "IPs", "Intl"]
_col_order_full = [
    "N", "Nombre", "Genero", "Area", "Figura", "Barra", "h-index", "Tendencia",
    "IPs", "EU", "EU IP", "Intl", "Tesis",
    "i10", "Citas", "Citas cruzadas", "Impacto art.", "Sexenios", "Fecha ult. sexenio",
    "Top%(Stanford)", "Top%(OA)", "Anos s/pub", "Ultima pub.",
    "h (GS)", "h (OA)", "h (Dial)",
    "Nivel",
]
_col_order = _col_order_full if _mostrar_todo else _col_order_base

_ROW_HEIGHT = 35
_HEADER_HEIGHT = 38

st.dataframe(
    df_styled,
    use_container_width=True,
    hide_index=True,
    height=_HEADER_HEIGHT + _ROW_HEIGHT * len(df_tabla),
    column_order=_col_order,
    column_config={
        "N": st.column_config.NumberColumn("N", width="small"),
        "Puntuacion": None,
        "Barra": st.column_config.TextColumn(
            "Puntuacion (0-10)",
            help="Excelencia individual (E_i × 10). Verde ≥7.5 · Azul ≥5.5 · Naranja ≥4 · Rojo <4",
            width="medium",
        ),
        "Nivel": st.column_config.TextColumn(
            "Nivel",
            help="Excepcional (≥7.5), Sólido (≥5.5), Aceptable (≥4.0), Débil (≥2.5), No apto (<2.5)",
        ),
        "h-index": st.column_config.NumberColumn("h-index", help="Índice h consolidado"),
        "Tendencia": st.column_config.NumberColumn("Tendencia", help=">0.7 ascendente, <0.4 descendente", format="%.3f"),
        "EU": st.column_config.NumberColumn("EU", help="Proyectos europeos (H2020, Horizon, ERC, MSCA…)"),
        "IPs": st.column_config.NumberColumn("IPs", help="Proyectos como Investigador Principal a lo largo de toda la carrera investigadora."),
        "Intl": st.column_config.NumberColumn("Intl", help="Instituciones internacionales colaboradoras"),
        "i10": st.column_config.NumberColumn("i10", help="Artículos con ≥10 citas"),
        "Impacto art.": st.column_config.NumberColumn("Impacto art.", help="Media de citas por artículo", format="%.1f"),
        "Sexenios": st.column_config.NumberColumn("Sexenios", help="Tramos de investigación reconocidos"),
        "Top%(Stanford)": st.column_config.NumberColumn("Top%(Stanford)", help="Percentil Stanford/Elsevier 2024. Verde ≤2%, naranja ≤10%", format="%.1f%%"),
        "Top%(OA)": st.column_config.NumberColumn("Top%(OA)", help="Percentil c-score Ioannidis vía OpenAlex. Verde ≤2%, naranja ≤10%", format="%.1f%%"),
        "Anos s/pub": st.column_config.NumberColumn("Anos s/pub", help="Años desde la última publicación. Rojo si ≥5", format="%d"),
        "Fecha ult. sexenio": st.column_config.TextColumn("Fecha ult. sexenio"),
        "Citas": st.column_config.NumberColumn("Citas", help="Citas Google Scholar / Crossref"),
        "Citas cruzadas": st.column_config.NumberColumn("Citas cruzadas", help="Citas Crossref"),
        "Tesis": st.column_config.NumberColumn("Tesis", help="Tesis doctorales dirigidas a lo largo de toda la carrera investigadora."),
        "EU IP": st.column_config.NumberColumn("EU IP", help="Proyectos europeos como IP"),
        "Ultima pub.": st.column_config.NumberColumn("Ultima pub.", help="Año de la última publicación", format="%d"),
        "h (GS)": st.column_config.TextColumn("h (GS)", help="h-index Google Scholar"),
        "h (OA)": st.column_config.NumberColumn("h (OA)", help="h-index OpenAlex"),
        "h (Dial)": st.column_config.NumberColumn("h (Dial)", help="h-index Dialnet"),
    },
)

# ── Casi-garantes ──
_casi = diagnosticar_casi_garantes(r_f, E_f, sel, stored_params, m=5)
if _casi:
    with st.expander("Mejores excluidos", icon=":material/person_remove:"):
        st.caption(
            "Top 5 hombres y top 5 mujeres no seleccionados por E_i: "
            "posibles sustitutos, con la debilidad concreta y la accion recomendada."
        )
        tabla_exc = []
        for c in _casi:
            r = r_f[c["idx"]]
            ultima = r.get("ultima_publicacion", 0)
            anos_sin = (_current_year - int(ultima)) if ultima and ultima > 0 else None
            tabla_exc.append({
                "Nombre": c["nombre"],
                "Genero": r["genero"],
                "Area": c["area"],
                "Figura": r.get("figura", ""),
                "Puntuacion": _ei_to_10(c["E_i"]),
                "h-index": c["h_index"],
                "Tendencia": c["tendencia"],
                "IPs": r.get("proyectos_ip", 0),
                "EU": c["proyectos_eu"],
                "Intl": r.get("instituciones_intl", 0),
                "i10": r.get("i10_index", 0),
                "Impacto art.": round(r.get("impacto_art", 0), 1),
                "Sexenios": r.get("sexenios", 0),
                "Fecha ult. sexenio": r.get("fecha_ultimo_sexenio", ""),
                "Top%(Stanford)": r.get("stanford_percentil"),
                "Top%(OA)": r.get("openalex_pct"),
                "Anos s/pub": anos_sin,
                "h (GS)": r.get("h_google_scholar") or "---",
                "h (OA)": r.get("h_openalex", 0),
                "h (Dial)": r.get("h_dialnet", 0),
                "Citas": r.get("citas_cruzadas") or r.get("citas_2020", 0),
                "Citas cruzadas": r.get("citas_cruzadas", 0),
                "Tesis": r.get("tesis_dir", 0),
                "EU IP": r.get("proyectos_eu_ip", 0),
                "Ultima pub.": ultima if ultima and ultima > 0 else None,
                "Nivel": _nivel_ei(c["E_i"]),
                "Debilidades": " / ".join(c["debilidades"]),
                "Accion": c["accion"],
            })
        df_exc = pd.DataFrame(tabla_exc)
        df_exc["Barra"] = df_exc["Puntuacion"].apply(_barra_puntuacion)

        def _color_barra_exc(row):
            styles = [""] * len(row)
            barra_idx = row.index.get_loc("Barra")
            styles[barra_idx] = _color_puntuacion(row["Puntuacion"])
            return styles

        df_exc_styled = df_exc.style.apply(
            _color_barra_exc, axis=1
        ).map(
            color_tendencia, subset=["Tendencia"]
        ).map(
            color_nivel, subset=["Nivel"]
        ).map(
            color_anos_sin, subset=["Anos s/pub"]
        ).map(
            color_stanford, subset=["Top%(Stanford)"]
        ).apply(
            lambda row: ["background-color: rgba(92,143,255,0.55); color: #181c1e" if col == "Top%(OA)" else "" for col in row.index],
            axis=1, subset=list(df_exc.columns)
        ).format(
            {"Tendencia": "{:.3f}", "Impacto art.": "{:.1f}"}
        )

        _mostrar_todo_exc = st.toggle("Mostrar todos los campos", value=False, key="exc_mostrar_todo")
        _exc_col_base = ["Nombre", "Genero", "Area", "Barra", "h-index", "Tendencia", "IPs", "Intl", "Debilidades", "Accion"]
        _exc_col_full = [
            "Nombre", "Genero", "Area", "Figura", "Barra", "h-index", "Tendencia",
            "IPs", "EU", "EU IP", "Intl", "Tesis",
            "i10", "Citas", "Citas cruzadas", "Impacto art.", "Sexenios", "Fecha ult. sexenio",
            "Top%(Stanford)", "Top%(OA)", "Anos s/pub", "Ultima pub.",
            "h (GS)", "h (OA)", "h (Dial)",
            "Nivel", "Debilidades", "Accion",
        ]
        _exc_col_order = _exc_col_full if _mostrar_todo_exc else _exc_col_base

        st.dataframe(
            df_exc_styled,
            use_container_width=True,
            hide_index=True,
            height=_HEADER_HEIGHT + _ROW_HEIGHT * len(df_exc),
            column_order=_exc_col_order,
            column_config={
                "Puntuacion": None,
                "Barra": st.column_config.TextColumn("Puntuacion (0-10)", help="Excelencia individual (E_i × 10).", width="medium"),
                "Nivel": st.column_config.TextColumn("Nivel"),
                "Tendencia": st.column_config.NumberColumn("Tendencia", help=">0 = crecimiento, <0 = declive", format="%.3f"),
                "Debilidades": st.column_config.TextColumn("Debilidades", help="Que le impide hoy entrar como garante"),
                "Accion": st.column_config.TextColumn("Accion", help="Dimension a desarrollar para ser garante a futuro"),
                "IPs": st.column_config.NumberColumn("IPs", help="Proyectos como Investigador Principal a lo largo de toda la carrera investigadora."),
                "Intl": st.column_config.NumberColumn("Intl", help="Instituciones internacionales colaboradoras"),
                "EU": st.column_config.NumberColumn("EU", help="Proyectos europeos (H2020, Horizon, ERC, MSCA…)"),
                "EU IP": st.column_config.NumberColumn("EU IP", help="Proyectos europeos como IP"),
                "i10": st.column_config.NumberColumn("i10", help="Artículos con ≥10 citas"),
                "Impacto art.": st.column_config.NumberColumn("Impacto art.", help="Media de citas por artículo", format="%.1f"),
                "Sexenios": st.column_config.NumberColumn("Sexenios", help="Tramos de investigación reconocidos"),
                "Fecha ult. sexenio": st.column_config.TextColumn("Fecha ult. sexenio"),
                "Top%(Stanford)": st.column_config.NumberColumn("Top%(Stanford)", help="Percentil Stanford/Elsevier 2024", format="%.1f%%"),
                "Top%(OA)": st.column_config.NumberColumn("Top%(OA)", help="Percentil c-score Ioannidis vía OpenAlex", format="%.1f%%"),
                "Anos s/pub": st.column_config.NumberColumn("Anos s/pub", help="Años desde la última publicación. Rojo si ≥5", format="%d"),
                "Ultima pub.": st.column_config.NumberColumn("Ultima pub.", help="Año de la última publicación", format="%d"),
                "Citas": st.column_config.NumberColumn("Citas", help="Citas Google Scholar / Crossref"),
                "Citas cruzadas": st.column_config.NumberColumn("Citas cruzadas", help="Citas Crossref"),
                "Tesis": st.column_config.NumberColumn("Tesis", help="Tesis doctorales dirigidas a lo largo de toda la carrera investigadora."),
                "h (GS)": st.column_config.TextColumn("h (GS)", help="h-index Google Scholar"),
                "h (OA)": st.column_config.NumberColumn("h (OA)", help="h-index OpenAlex"),
                "h (Dial)": st.column_config.NumberColumn("h (Dial)", help="h-index Dialnet"),
            },
        )

# ── Swap UI ──
st.subheader(":material/swap_horiz: Cambiar un garante")

# Initialize pending swaps in session state
if "_pending_swaps" not in st.session_state:
    st.session_state["_pending_swaps"] = []

# Build names for selectboxes
_sel_names = {i: r_f[i]["nombre_completo"] for i in sel}
_pool_indices = [
    i for i in range(len(r_f))
    if i not in set(sel)
    and i not in {s["add"] for s in st.session_state["_pending_swaps"]}
]
# Sort pool by E_i descending
_pool_indices.sort(key=lambda i: r_f[i]["E_i"], reverse=True)
_pool_names = {
    i: f"{r_f[i]['nombre_completo']}  ({_ei_to_10(r_f[i]['E_i']):.2f}/10, h={r_f[i]['h_index']})"
    for i in _pool_indices
}

_already_removed = {s["remove"] for s in st.session_state["_pending_swaps"]}
_removable = [i for i in sel if i not in _already_removed]

if not _pool_indices:
    st.caption("No quedan candidatos disponibles para incorporar.")
elif not _removable:
    st.caption("Todos los garantes ya tienen un cambio pendiente.")
else:
    col_rm, col_add, col_metric = st.columns([2, 3, 2])
    with col_rm:
        _remove_idx = st.selectbox(
            "Retirar",
            options=_removable,
            format_func=lambda i: _sel_names.get(i, str(i)),
            key="swap_remove",
        )
    with col_add:
        _add_idx = st.selectbox(
            "Incorporar",
            options=_pool_indices,
            format_func=lambda i: _pool_names.get(i, str(i)),
            key="swap_add",
        )

    # E_i delta preview inline
    with col_metric:
        if _remove_idx is not None and _add_idx is not None:
            _current_ei = np.mean([_ei_to_10(r_f[i]["E_i"]) for i in sel])
            _proposed_sel = [_add_idx if i == _remove_idx else i for i in sel]
            _proposed_ei = np.mean([_ei_to_10(r_f[i]["E_i"]) for i in _proposed_sel])
            _delta_ei = _proposed_ei - _current_ei
            st.metric(
                "Puntuacion media si se aplica",
                f"{_proposed_ei:.2f}",
                delta=f"{_delta_ei:+.2f} vs actual",
                delta_color="normal" if _delta_ei >= 0 else "inverse",
            )

    if st.button("Apilar cambio", icon=":material/swap_horiz:", use_container_width=True):
        if _remove_idx is not None and _add_idx is not None:
            st.session_state["_pending_swaps"].append({
                "remove": _remove_idx,
                "remove_name": r_f[_remove_idx]["nombre_completo"],
                "add": _add_idx,
                "add_name": r_f[_add_idx]["nombre_completo"],
            })
            st.session_state.pop("swap_remove", None)
            st.session_state.pop("swap_add", None)
            st.rerun()

# Show pending swaps
if st.session_state["_pending_swaps"]:
    with st.container(border=True):
        st.caption("Cambios pendientes:")
        for idx_s, swap in enumerate(st.session_state["_pending_swaps"], 1):
            st.markdown(
                f"{idx_s}. Retirar **{swap['remove_name']}** → "
                f"Incorporar **{swap['add_name']}**"
            )

    col_apply, col_clear = st.columns(2)
    with col_apply:
        if st.button("Recalcular con cambios", type="primary", use_container_width=True):
            # Apply swaps
            new_sel = list(sel)
            for swap in st.session_state["_pending_swaps"]:
                if swap["remove"] in new_sel:
                    new_sel.remove(swap["remove"])
                if swap["add"] not in new_sel:
                    new_sel.append(swap["add"])

            st.session_state["seleccionados"] = new_sel
            st.session_state["z_total"] = None

            # Recompute diagnostico
            new_diag = compute_diagnostico(
                new_sel,
                r_f,
                K,
                stored_params.get("N", len(new_sel)),
                modalidad=stored_params.get("modalidad", "MdM"),
                db_name=stored_params.get("db_name"),
            )
            st.session_state["diagnostico"] = new_diag

            # Invalidate later steps
            st.session_state.pop("evaluacion_fase1", None)
            st.session_state.pop("evaluacion_fase2", None)

            # Clear pending swaps
            st.session_state["_pending_swaps"] = []
            st.session_state.pop("swap_remove", None)
            st.session_state.pop("swap_add", None)
            st.rerun()
    with col_clear:
        if st.button("Limpiar cambios", use_container_width=True):
            st.session_state["_pending_swaps"] = []
            st.session_state.pop("swap_remove", None)
            st.session_state.pop("swap_add", None)
            st.rerun()

# ── Diagnostico: fortalezas y debilidades ──
st.space("small")
st.subheader(":material/insights: Diagnostico")

col_d1, col_d2 = st.columns(2)
with col_d1:
    with st.container(border=True):
        st.markdown("**:material/thumb_up: Fortalezas**")
        for f in diag["fortalezas"]:
            st.markdown(f":material/check_circle: {f}")
        if not diag["fortalezas"]:
            st.caption("Ninguna fortaleza destacable")
with col_d2:
    with st.container(border=True):
        st.markdown("**:material/warning: Debilidades**")
        for d in diag["debilidades"]:
            st.markdown(f":material/cancel: {d}")
        if not diag["debilidades"]:
            st.caption("Ninguna debilidad destacable")

# ── Recomendaciones (collapsible) ──
if diag["recomendaciones"]:
    with st.expander("Recomendaciones", icon=":material/lightbulb:"):
        for rec in diag["recomendaciones"]:
            if rec["prioridad"] == "ALTA":
                st.warning(f"**[ALTA]** {rec['texto']}", icon=":material/priority_high:")
            else:
                st.info(f"**[{rec['prioridad']}]** {rec['texto']}", icon=":material/lightbulb:")

# ── Navigation ──
wizard_nav(current_step=2, can_advance=True)
