"""
Paso 1 del wizard: Configuracion del instituto, modalidad, equipo y restricciones.
"""
import sys
import os
import json
import math
import numpy as np
import streamlit as st
from pathlib import Path
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "optimizer"))
import config as cfg
from mip_garantes import (
    load_investigators, discover_institutes, compute_E, compute_K, run_mip,
    compute_diagnostico,
)
from utils import prefilter_candidates

from ui.wizard_common import render_progress_bar

DIM_KEYS = [
    "produccion", "ip", "tesis", "tendencia", "eu", "intl",
    "reconocimiento", "i10", "impacto_art", "sexenios", "top_mundial",
]

_SJR_PATH = Path(__file__).parent.parent / "optimizer" / "scimago_data.json"


@st.cache_resource
def _load_sjr_map() -> dict:
    if not _SJR_PATH.exists():
        return {}
    with open(_SJR_PATH, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=300)
def load_data(db_name: str, modalidad: str = "MdM"):
    sjr_map = _load_sjr_map()
    docs = load_investigators(db_name)
    E, raw = compute_E(docs, sjr_map=sjr_map or None, modalidad=modalidad)
    return docs, E, raw


@st.cache_data(ttl=300)
def load_data_custom(db_name: str, modalidad: str, año_ini: int, año_fin: int):
    """Like load_data but with an explicit periodo_ref override."""
    sjr_map = _load_sjr_map()
    docs = load_investigators(db_name)
    E, raw = compute_E(docs, sjr_map=sjr_map or None, modalidad=modalidad,
                       periodo_ref=(año_ini, año_fin))
    return docs, E, raw


@st.cache_data(ttl=60)
def get_institutes() -> list[str]:
    return discover_institutes()


# ─────────────────────────────────────────────────────────────────────────────
render_progress_bar(1)
st.title("Configuracion")
st.caption("Selecciona el instituto, la convocatoria y define las restricciones del optimizador.")

# ── Delta badge pill styles (same as preseleccion) ──
st.markdown(
    """<style>
    [data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stMetric"]) {
        min-height: 108px;
    }
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
    /* Segmented control: selected option → navy background + white text */
    button[kind='segmented_controlActive']:not(:disabled) {
        background-color: #002045 !important;
        color: #ffffff !important;
        border-color: #002045 !important;
    }
    </style>""",
    unsafe_allow_html=True,
)

# ── Instituto + Convocatoria ──────────────────────────────────────────────────
with st.container(border=True):
    col_inst, col_mod = st.columns([1, 2])

    with col_inst:
        raw_institutes = get_institutes()
        discovery_failed = len(raw_institutes) == 0
        institutes = raw_institutes if raw_institutes else [cfg.DB_NAME]
        label_map = {db: db.replace("_claude", "") for db in institutes}

        if "instituto" not in st.session_state:
            st.session_state["instituto"] = institutes[0]
        if st.session_state.get("instituto") not in institutes:
            st.session_state["instituto"] = institutes[0]

        selected_db = st.selectbox(
            "Instituto",
            options=institutes,
            index=(
                institutes.index(st.session_state["instituto"])
                if st.session_state["instituto"] in institutes else 0
            ),
            format_func=lambda x: label_map[x],
            help="Base de datos MongoDB del instituto a optimizar",
        )
        if selected_db != st.session_state.get("instituto"):
            _keys_to_clear = [
                "seleccionados", "K", "raw_f", "E_f", "docs_f", "z_total",
                "params", "diagnostico", "saved_runs", "_pending_swaps",
                "evaluacion_fase1", "evaluacion_fase2", "_last_modalidad",
                "clusters", "clusters_K", "llm_nucleos", "K_full", "modalidad",
                "wizard_step",
            ]
            for _k in _keys_to_clear:
                st.session_state.pop(_k, None)
            st.session_state["instituto"] = selected_db
            st.rerun()
        if discovery_failed:
            st.warning("No se pudo conectar a MongoDB. Usando instituto por defecto.")

    with col_mod:
        _mod_labels = {
            "MdM": "Maria de Maeztu",
            "SO":  "Severo Ochoa",
            "UEI": "UEI Junta",
        }
        modalidad_code = st.segmented_control(
            "Convocatoria",
            options=["MdM", "SO", "UEI"],
            format_func=lambda x: _mod_labels[x],
            default="MdM",
            key="convocatoria_seg",
        ) or "MdM"
        _desc = {
            "SO":  f"Centro completo, maxima exigencia · **10+1 garantes** · h-min {cfg.H_MIN_SO}",
            "UEI": f"Unidades de Excelencia (Junta de Andalucia) · **5+1 garantes** · h-min {cfg.H_MIN_UEI}",
            "MdM": f"Unidad universitaria · **6+1 garantes** · h-min {cfg.H_MIN_MDM}",
        }
        st.caption(_desc[modalidad_code])

# Reset on modalidad change
if st.session_state.get("_last_modalidad") != modalidad_code:
    st.session_state["_pesos_version"] = st.session_state.get("_pesos_version", 0) + 1
    st.session_state["_last_modalidad"] = modalidad_code
    for _k in ("clusters", "clusters_K", "llm_nucleos", "K_full"):
        st.session_state[_k] = None

# Invalidate results when period changes
_periodo_state_key = f"periodo_{modalidad_code}"
_current_periodo = st.session_state.get(_periodo_state_key, None)
_ui_ini = st.session_state.get(f"periodo_ini_{modalidad_code}")
_ui_fin = st.session_state.get(f"periodo_fin_{modalidad_code}")
if _ui_ini is not None and _ui_fin is not None:
    _new_periodo = (_ui_ini, _ui_fin)
    if _current_periodo is not None and _new_periodo != _current_periodo:
        for _k in ("seleccionados", "K", "raw_f", "E_f", "docs_f",
                   "z_total", "params", "diagnostico", "saved_runs", "_pending_swaps",
                   "evaluacion_fase1", "evaluacion_fase2"):
            st.session_state.pop(_k, None)
        st.session_state["wizard_step"] = 1
    st.session_state[_periodo_state_key] = _new_periodo

# Load data
with st.spinner("Cargando datos del instituto..."):
    try:
        _def_ini, _def_fin = (
            cfg.PERIODO_REF_SO  if modalidad_code == "SO"
            else cfg.PERIODO_REF_UEI if modalidad_code == "UEI"
            else cfg.PERIODO_REF_MDM
        )
        _pr = st.session_state.get(f"periodo_{modalidad_code}", (_def_ini, _def_fin))
        if _pr != (_def_ini, _def_fin):
            docs, E, raw = load_data_custom(
                st.session_state["instituto"], modalidad_code, _pr[0], _pr[1]
            )
        else:
            docs, E, raw = load_data(st.session_state["instituto"], modalidad_code)
    except ConnectionError as _e:
        st.error(f"Error de conexion a MongoDB: {_e}")
        st.stop()

nombres = ["--"] + sorted(set(r["nombre_completo"] for r in raw))
# Safe fallback; will be overridden by the period selector UI block below
_def_ini_fb, _def_fin_fb = (
    cfg.PERIODO_REF_SO if modalidad_code == "SO"
    else cfg.PERIODO_REF_UEI if modalidad_code == "UEI"
    else cfg.PERIODO_REF_MDM
)
periodo_ref = (_def_ini_fb, _def_fin_fb)
nombres_pool = [n for n in nombres if n != "--"]
n_default = 10 if modalidad_code == "SO" else 5 if modalidad_code == "UEI" else 6
h_min_default = (
    cfg.H_MIN_SO if modalidad_code == "SO"
    else cfg.H_MIN_UEI if modalidad_code == "UEI"
    else cfg.H_MIN_MDM
)
eu_min_default = 4 if modalidad_code == "SO" else 1 if modalidad_code == "UEI" else 2

# ── Main layout: left (config) + right (live stats) ──────────────────────────
col_left, col_right = st.columns([3, 2], gap="large")

with col_left:

    # ── Equipo ──
    with st.container(border=True):
        st.subheader(":material/group: Composicion del equipo")

        director_sel = st.selectbox(
            "Director/a cientifico/a",
            nombres,
            help="Lider de la propuesta. Se incluye automaticamente en la solucion.",
        )
        n_garantes = st.slider(
            "Numero de garantes",
            4, 15, n_default,
            key=f"n_garantes_{modalidad_code}",
            help="Garantes a seleccionar (sin contar al director/a)",
        )
        _total_equipo = n_garantes + (1 if director_sel != "--" else 0)
        st.caption(f"Equipo total: **{_total_equipo}** personas ({n_garantes} garantes{' + 1 director/a' if director_sel != '--' else ''})")

        col_fij, col_exc = st.columns(2)
        with col_fij:
            fijar_sel = st.multiselect(
                "Incluir siempre",
                nombres_pool,
                help="Se incluiran en la solucion sin importar su puntuacion",
                placeholder="Ninguno...",
            )
        with col_exc:
            excluir_sel = st.multiselect(
                "Excluir",
                [n for n in nombres_pool if n not in fijar_sel and n != director_sel],
                help="Se eliminaran del pool",
                placeholder="Ninguno...",
            )

    # ── Restricciones ──
    with st.container(border=True):
        st.subheader(":material/tune: Restricciones del optimizador")

        _row1_c1, _row1_c2 = st.columns(2)
        with _row1_c1:
            h_min = st.number_input(
                "h-index minimo",
                0, 20, h_min_default,
                key=f"h_min_{modalidad_code}",
                help="Excluye candidatos por debajo de este umbral (excepto fijados)",
            )
        with _row1_c2:
            eu_min = st.number_input(
                "Min. con EU",
                0, 8, eu_min_default,
                key=f"eu_min_{modalidad_code}",
                help="Numero minimo de garantes con proyecto europeo",
            )
        _row2_c1, _row2_c2 = st.columns(2)
        with _row2_c1:
            min_areas = st.number_input(
                "Min. areas",
                1, 8, 3,
                key=f"min_areas_{modalidad_code}",
                help="Diversidad tematica minima requerida",
            )
        with _row2_c2:
            paridad_pct = st.number_input(
                "Paridad (%)",
                0, 50, 40, 5,
                key=f"paridad_pct_{modalidad_code}",
                help="% minimo de mujeres (criterio de desempate entre candidaturas similares)",
            )
            _min_mujeres_real = math.ceil(paridad_pct / 100.0 * n_garantes)
            if _min_mujeres_real > 0:
                st.caption(
                    f"= {_min_mujeres_real} mujeres de {n_garantes} "
                    f"({100 * _min_mujeres_real / n_garantes:.0f}%)"
                )

        # Top mundial filter (optional, collapsible)
        with st.expander(":material/public: Filtro Top% mundial (opcional)", expanded=False):
            top_pct_enable = st.toggle(
                "Activar filtro por percentil mundial",
                value=False,
                help="Excluye candidatos que no esten en el top X% de su subfield (Stanford o OpenAlex).",
            )
            if top_pct_enable:
                col_tp1, col_tp2 = st.columns(2)
                with col_tp1:
                    top_pct_max = st.slider(
                        "Umbral maximo (%)", 1, 25, 10, 1,
                        help="Solo candidatos en el top X% mundial. Menor = mas estricto.",
                        format="%d%%",
                    )
                with col_tp2:
                    top_pct_source = st.radio(
                        "Ranking",
                        options=["any", "oa", "stanford"],
                        format_func=lambda x: {
                            "any": "OA o Stanford",
                            "oa": "OpenAlex",
                            "stanford": "Stanford/Ioannidis",
                        }[x],
                        horizontal=True,
                    )

                def _pct_val(r, src):
                    st_p = r.get("stanford_percentil")
                    oa_p = r.get("openalex_pct")
                    if src == "stanford":
                        return st_p
                    if src == "oa":
                        return oa_p
                    return (
                        min(v for v in [st_p, oa_p] if v is not None)
                        if any(v is not None for v in [st_p, oa_p])
                        else None
                    )

                _n_pass = sum(
                    1 for r in raw
                    if (v := _pct_val(r, top_pct_source)) is not None and v <= top_pct_max
                )
                _n_data = sum(1 for r in raw if _pct_val(r, top_pct_source) is not None)
                _color = "green" if _n_pass >= 10 else ("orange" if _n_pass >= 5 else "red")
                _color_md = "green" if _color == "green" else ("orange" if _color == "orange" else "red")
                st.markdown(f":{_color_md}[**{_n_pass}**] de {_n_data} con datos cumplen este criterio")
            else:
                top_pct_max = None
                top_pct_source = "any"

    # ── Periodo de referencia ──
    with st.container(border=True):
        st.subheader(":material/date_range: Periodo de evaluacion")

        _default_ini, _default_fin = (
            cfg.PERIODO_REF_SO  if modalidad_code == "SO"
            else cfg.PERIODO_REF_UEI if modalidad_code == "UEI"
            else cfg.PERIODO_REF_MDM
        )
        _periodo_key = f"periodo_{modalidad_code}"
        if _periodo_key not in st.session_state:
            st.session_state[_periodo_key] = (_default_ini, _default_fin)

        _col_ini, _col_fin = st.columns(2)
        with _col_ini:
            año_ini = st.number_input(
                "Año inicio",
                min_value=2000, max_value=cfg.CURRENT_YEAR - 1,
                value=st.session_state[_periodo_key][0],
                step=1,
                key=f"periodo_ini_{modalidad_code}",
                help=f"Inicio del periodo de referencia (por defecto {_default_ini})",
            )
        with _col_fin:
            año_fin = st.number_input(
                "Año fin",
                min_value=2000, max_value=cfg.CURRENT_YEAR - 1,
                value=st.session_state[_periodo_key][1],
                step=1,
                key=f"periodo_fin_{modalidad_code}",
                help=f"Fin del periodo de referencia (por defecto {_default_fin})",
            )

        if año_ini > año_fin:
            st.warning("El año de inicio no puede ser posterior al año de fin.", icon=":material/warning:")
            año_ini, año_fin = _default_ini, _default_fin
            st.session_state[_periodo_key] = (_default_ini, _default_fin)

        st.session_state[_periodo_key] = (int(año_ini), int(año_fin))

        _periodo_changed = (año_ini, año_fin) != (_default_ini, _default_fin)
        if _periodo_changed:
            st.caption(
                f":orange[Periodo personalizado: {año_ini}–{año_fin}] "
                f"(por defecto: {_default_ini}–{_default_fin})"
            )
        else:
            st.caption(f"Periodo por defecto para {modalidad_code}: {_default_ini}–{_default_fin}")

        periodo_ref = (año_ini, año_fin)

    # ── Pesos E_i ──
    with st.expander(":material/bar_chart: Personalizar pesos E_i", expanded=False):
        _default_pesos = (
            cfg.PESOS_SO if modalidad_code == "SO"
            else cfg.PESOS_UEI if modalidad_code == "UEI"
            else cfg.PESOS_MDM
        )
        if "_pesos_version" not in st.session_state:
            st.session_state["_pesos_version"] = 0
        _pv = st.session_state["_pesos_version"]

        st.caption("Peso de cada dimension en la puntuacion de excelencia individual. Deben sumar 100%.")
        _dim_ui = {
            "produccion":   ("Produccion",         "Citas y produccion CVN del periodo de referencia"),
            "ip":           ("Liderazgo IP",        "Proyectos como investigador/a principal"),
            "tesis":        ("Tesis dirigidas",     "Tesis doctorales dirigidas y codirigidas"),
            "tendencia":    ("Tendencia",           "Evolucion reciente de citas (ultimos 3 anos vs anteriores)"),
            "eu":           ("Proyectos EU",        "Participacion en proyectos financiados por la UE"),
            "intl":         ("Internacionalizacion","Colaboraciones con instituciones extranjeras"),
            "reconocimiento":("Reconocimiento",     "Patentes, distinciones y membresias en comites"),
            "i10":          ("Indice i10",          "Publicaciones con 10+ citas"),
            "impacto_art":  ("Impacto articulos",   "Media de citas Crossref por articulo. DORA-compatible."),
            "sexenios":     ("Sexenios",            "Acreditaciones CNEAI + bonus si sexenio vivo"),
            "top_mundial":  ("Top mundial",         "Percentil del top mundial en el subcampo (OpenAlex). Peso testimonial."),
        }
        custom_pesos = {}
        _cols_p = st.columns(2)
        for idx_p, (k, (label, desc)) in enumerate(_dim_ui.items()):
            with _cols_p[idx_p % 2]:
                _def_val = int(round(_default_pesos.get(k, 0) * 100))
                custom_pesos[k] = (
                    st.slider(
                        label, 0, 50, _def_val,
                        step=1, key=f"peso_{k}_v{_pv}", help=desc,
                        format="%d%%",
                    ) / 100.0
                )
        _pesos_sum = sum(custom_pesos.values())
        _pesos_pct = int(round(_pesos_sum * 100))
        _sum_color = "normal" if abs(_pesos_sum - 1.0) <= 0.05 else "inverse"
        st.metric("Total pesos", f"{_pesos_pct}%", delta=f"{_pesos_pct - 100:+d}pp",
                  delta_color=_sum_color,
                  help="Deben sumar ~100%. Se normalizan automaticamente al calcular.")
        if abs(_pesos_sum - 1.0) > 0.05:
            st.warning(f"Los pesos suman {_pesos_pct}% — se normalizaran automaticamente.", icon=":material/warning:")
        if st.button("Restablecer pesos", key="reset_pesos", icon=":material/refresh:", use_container_width=True):
            st.session_state["_pesos_version"] = _pv + 1
            st.rerun()


with col_right:

    # ── Live pool stats ──
    with st.container(border=True):
        st.subheader(":material/analytics: Pool de candidatos")

        _total = len(raw)
        _pasan_h = sum(1 for r in raw if r["h_index"] >= h_min)
        _con_eu = sum(1 for r in raw if r.get("proyectos_eu", 0) > 0)
        _mujeres = sum(1 for r in raw if r.get("genero") == "Mujer")
        _pct_mujeres = 100 * _mujeres / _total if _total else 0
        _fijados = len(fijar_sel)
        _excluidos = len(excluir_sel)

        with st.container(horizontal=True):
            st.metric("Total", _total, border=True)
            st.metric("Pasan h-index", _pasan_h,
                      delta=f"{_pasan_h - n_garantes:+d} vs necesarios",
                      delta_color="normal",
                      border=True,
                      help=f"Investigadores con h-index >= {h_min}")
            st.metric("Con EU", _con_eu,
                      delta=f"{_con_eu - eu_min_default:+d} vs minimo",
                      delta_color="normal",
                      border=True)
        with st.container(horizontal=True):
            st.metric("Mujeres", f"{_mujeres} ({_pct_mujeres:.0f}%)",
                      delta=f"{_pct_mujeres - 40:+.0f}% vs 40%",
                      delta_color="normal",
                      border=True)
            st.metric("Fijados", _fijados, border=True,
                      help="Se incluiran siempre en la solucion" if _fijados else "Ninguno fijado")
            st.metric("Excluidos", _excluidos, border=True,
                      help="Eliminados del pool" if _excluidos else "Ninguno excluido")

        # Area breakdown
        _area_counts = Counter(r["area"] for r in raw if r["area"])
        _top_areas = _area_counts.most_common(5)
        _max_cnt = _top_areas[0][1] if _top_areas else 1
        st.caption("Top 5 areas")
        for _area, _cnt in _top_areas:
            _short = _area[:28] + "…" if len(_area) > 28 else _area
            cols_a = st.columns([3, 1])
            with cols_a[0]:
                st.progress(_cnt / _max_cnt, text=_short)
            with cols_a[1]:
                st.caption(str(_cnt))

    # ── Config summary ──
    with st.container(border=True):
        st.subheader(":material/summarize: Resumen")

        # Convocatoria badge
        _badge_color = {"SO": "red", "MdM": "blue", "UEI": "orange"}[modalidad_code]
        _conv_label = {"SO": "Severo Ochoa", "MdM": "Maria de Maeztu", "UEI": "UEI"}[modalidad_code]
        st.badge(_conv_label, color=_badge_color, icon=":material/workspace_premium:")

        # Equipo
        _total_equipo = n_garantes + (1 if director_sel != "--" else 0)
        st.markdown(
            f":material/group: **{_total_equipo}** personas — "
            f"{n_garantes} garantes"
            + (f" + director/a" if director_sel != "--" else "")
        )
        if director_sel != "--":
            st.caption(f"Director/a: {director_sel}")
        if fijar_sel:
            st.caption(f":material/lock: Fijados: {', '.join(fijar_sel)}")
        if excluir_sel:
            st.caption(f":material/block: Excluidos: {', '.join(excluir_sel)}")

        st.divider()

        # ── Feasibility check por restriccion ──
        st.caption("Viabilidad de las restricciones")

        def _check_row(label, ok, detail):
            icon  = ":material/check_circle:" if ok else ":material/cancel:"
            color = "green" if ok else "red"
            cols  = st.columns([0.08, 0.92])
            with cols[0]:
                st.markdown(f":{color}[{icon}]")
            with cols[1]:
                st.markdown(f"**{label}** · :{'green' if ok else 'red'}[{detail}]")

        # h-index
        _h_ok = _pasan_h >= n_garantes
        _check_row(
            f"h-index ≥ {h_min}",
            _h_ok,
            f"{_pasan_h} pasan ({_pasan_h - n_garantes:+d} sobre el minimo)" if _h_ok
            else f"solo {_pasan_h} pasan, se necesitan {n_garantes}",
        )

        # EU
        _eu_ok = _con_eu >= eu_min
        _check_row(
            f"Min. EU: {eu_min}",
            _eu_ok,
            f"{_con_eu} con EU ({_con_eu - eu_min:+d})" if _eu_ok
            else f"solo {_con_eu} con EU, se necesitan {eu_min}",
        )

        # Areas
        _n_areas_pool = len(set(r["area"] for r in raw if r["area"] and r["h_index"] >= h_min))
        _areas_ok = _n_areas_pool >= min_areas
        _check_row(
            f"Min. areas: {min_areas}",
            _areas_ok,
            f"{_n_areas_pool} areas disponibles" if _areas_ok
            else f"solo {_n_areas_pool} areas en pool filtrado",
        )

        # Paridad
        _min_muj_req = math.ceil(paridad_pct / 100.0 * n_garantes)
        _par_ok = _mujeres >= _min_muj_req
        _check_row(
            f"Paridad {paridad_pct}%",
            _par_ok,
            f"{_mujeres} mujeres disponibles, {_min_muj_req} requeridas" if _par_ok
            else f"solo {_mujeres} mujeres, se necesitan {_min_muj_req}",
        )

        # Resolucion global
        _all_ok = _h_ok and _eu_ok and _areas_ok and _par_ok
        st.space("small")
        if _all_ok:
            st.success("Configuracion factible — lista para optimizar.", icon=":material/rocket_launch:")
        else:
            st.warning("Ajusta las restricciones marcadas en rojo antes de optimizar.", icon=":material/build:")

        # Period in use
        _pr_label = f"{año_ini}–{año_fin}"
        if _periodo_changed:
            st.caption(f":material/date_range: Periodo: :orange[**{_pr_label}**] (personalizado)")
        else:
            st.caption(f":material/date_range: Periodo: **{_pr_label}**")

# ─────────────────────────────────────────────────────────────────────────────
# RECOMPUTE E_i
# ─────────────────────────────────────────────────────────────────────────────
if "custom_pesos" not in locals() or not custom_pesos:
    custom_pesos = dict(
        cfg.PESOS_SO if modalidad_code == "SO"
        else cfg.PESOS_UEI if modalidad_code == "UEI"
        else cfg.PESOS_MDM
    )
if "_default_pesos" not in locals():
    _default_pesos = (
        cfg.PESOS_SO if modalidad_code == "SO"
        else cfg.PESOS_UEI if modalidad_code == "UEI"
        else cfg.PESOS_MDM
    )

_pesos_changed = any(
    abs(custom_pesos.get(k, 0) - _default_pesos.get(k, 0)) > 0.005
    for k in _default_pesos
)
if _pesos_changed:
    _pesos_sum_rc = sum(custom_pesos.values())
    _norm = _pesos_sum_rc if _pesos_sum_rc > 0 else 1.0
    _effective_pesos = {k: custom_pesos.get(k, 0) / _norm for k in custom_pesos}
    E = np.array([
        sum(_effective_pesos.get(k, 0) * r["dims_norm"].get(k, 0) for k in _effective_pesos)
        * r.get("balance_factor", 1.0)
        for r in raw
    ])
    for i, r in enumerate(raw):
        r["E_i"] = round(float(E[i]), 4)
else:
    _effective_pesos = dict(_default_pesos)

# ─────────────────────────────────────────────────────────────────────────────
# PREFILTRADO
# ─────────────────────────────────────────────────────────────────────────────
top_idx = prefilter_candidates(
    raw, E, docs, n_garantes,
    director_name=director_sel if director_sel != "--" else None,
    fixed_names=fijar_sel or None,
    exclude_names=excluir_sel or None,
)
raw_f = [raw[i] for i in top_idx]
E_f = np.array([E[i] for i in top_idx])
docs_f = [docs[i] for i in top_idx]

director_idx = None
if director_sel != "--":
    director_idx = next(
        (i for i, r in enumerate(raw_f) if r["nombre_completo"] == director_sel), None
    )

fixed_indices = []
if fijar_sel:
    fixed_indices = [i for i, r in enumerate(raw_f) if r["nombre_completo"] in fijar_sel]

# ─────────────────────────────────────────────────────────────────────────────
# STATE INIT & OPTIMIZE BUTTON
# ─────────────────────────────────────────────────────────────────────────────
if "seleccionados" not in st.session_state:
    st.session_state.seleccionados = None
    st.session_state.K = None
    st.session_state.raw_f = None
    st.session_state.E_f = None
    st.session_state.docs_f = None
    st.session_state.z_total = None
    st.session_state.params = None
if "saved_runs" not in st.session_state:
    st.session_state.saved_runs = []

st.space("small")
run_btn = st.button(
    "Comenzar optimizacion",
    type="primary",
    use_container_width=True,
    icon=":material/play_arrow:",
)

alpha = 1.0
beta = 0.0

if run_btn:
    for _k in ("clusters", "clusters_K", "llm_nucleos", "K_full"):
        st.session_state[_k] = None
    st.session_state.pop("evaluacion_fase1", None)
    st.session_state.pop("evaluacion_fase2", None)
    with st.spinner("Calculando solucion optima..."):
        K = compute_K(raw_f, docs_f)
        seleccionados, z_total = run_mip(
            raw_f, E_f, K, n_garantes, director_idx, min_areas,
            paridad_pct / 100.0,
            modalidad=modalidad_code,
            h_min=h_min, eu_min=eu_min,
            fixed_indices=fixed_indices,
            alpha=alpha, beta=beta,
            top_pct_max=top_pct_max,
            top_pct_source=top_pct_source,
        )
    if top_pct_max is not None:
        _fixed_set = set(fixed_indices)
        _n_eligible_pct = sum(
            1 for i, r in enumerate(raw_f)
            if i in _fixed_set or (
                r["h_index"] >= h_min and (
                    (top_pct_source == "stanford" and r.get("stanford_percentil") is not None and r["stanford_percentil"] <= top_pct_max)
                    or (top_pct_source == "oa" and r.get("openalex_pct") is not None and r["openalex_pct"] <= top_pct_max)
                    or (top_pct_source == "any" and (
                        (r.get("stanford_percentil") is not None and r["stanford_percentil"] <= top_pct_max)
                        or (r.get("openalex_pct") is not None and r["openalex_pct"] <= top_pct_max)
                    ))
                )
            )
        )
        if _n_eligible_pct < n_garantes:
            st.warning(
                f"Solo {_n_eligible_pct} candidatos cumplen el filtro Top% (menos que los {n_garantes} solicitados). "
                f"El filtro fue ignorado y el optimizador uso el pool completo.",
            )
    if seleccionados is None:
        st.error(
            "No se encontro una solucion factible. "
            "Intenta reducir el minimo de areas, bajar el umbral de h-index o ajustar la paridad."
        )
        st.stop()

    st.session_state.K = K
    st.session_state.seleccionados = seleccionados
    st.session_state.raw_f = raw_f
    st.session_state.E_f = E_f
    st.session_state.docs_f = docs_f
    st.session_state.z_total = z_total
    st.session_state.params = {
        "N": n_garantes, "alpha": alpha, "beta": beta,
        "min_areas": min_areas, "paridad_pct": paridad_pct,
        "modalidad": modalidad_code, "h_min": h_min, "eu_min": eu_min,
        "director_idx": director_idx, "fixed_indices": fixed_indices,
        "top_pct_max": top_pct_max, "top_pct_source": top_pct_source,
        "pesos": dict(_effective_pesos),
        "db_name": st.session_state.get("instituto"),
        "periodo_ref": periodo_ref,
    }
    st.session_state.diagnostico = compute_diagnostico(
        seleccionados, raw_f, K, n_garantes,
        modalidad=modalidad_code,
        db_name=st.session_state.get("instituto"),
    )
    st.session_state["modalidad"] = modalidad_code
    st.session_state.wizard_step = max(st.session_state.get("wizard_step", 1), 2)
    st.switch_page("pages/2_preseleccion.py")
