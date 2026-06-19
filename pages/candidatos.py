#!/usr/bin/env python3
"""Miembros -- listado completo de investigadores del instituto."""
import sys
import os
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "optimizer"))
import config as cfg
from mip_garantes import load_investigators, compute_E

from ui.wizard_common import (
    color_tendencia, color_anos_sin, color_stanford,
    render_tool_instituto_selector, _pretty_institute,
)

# ── Page header ──
st.title("Miembros")
st.caption("Listado completo de investigadores del instituto.")


@st.cache_data(ttl=300)
def _load_data(db_name: str, modalidad: str = "MdM"):
    docs = load_investigators(db_name)
    E, raw = compute_E(docs, modalidad=modalidad)
    return docs, E, raw


# ── Instituto selector ──
instituto, modalidad = render_tool_instituto_selector()

docs, E, raw = _load_data(instituto, modalidad)
st.caption(f"{len(raw)} miembros · {_pretty_institute(instituto)}")

# ─────────────────────────────────────────────────────────────────────────────
# KPIs de cobertura de fuentes
# ─────────────────────────────────────────────────────────────────────────────
_total = len(raw)
_n_gs  = sum(1 for r in raw if r.get("h_google_scholar") is not None)
_n_ss  = sum(1 for r in raw if r.get("h_semantic_scholar") is not None)
_n_oa  = sum(1 for r in raw if r.get("h_openalex", 0) > 0)
_n_sx  = sum(1 for r in raw if (r.get("sexenios") or 0) > 0)

_kc1, _kc2, _kc3, _kc4 = st.columns(4)
with _kc1, st.container(border=True):
    st.metric("Google Scholar", f"{_n_gs}/{_total}",
              help="Investigadores con perfil Google Scholar indexado")
with _kc2, st.container(border=True):
    st.metric("Semantic Scholar", f"{_n_ss}/{_total}",
              help="Investigadores con perfil Semantic Scholar indexado")
with _kc3, st.container(border=True):
    st.metric("OpenAlex", f"{_n_oa}/{_total}",
              help="Investigadores con datos OpenAlex (h-index)")
with _kc4, st.container(border=True):
    st.metric("Sexenios", f"{_n_sx}/{_total}",
              help="Investigadores con al menos un sexenio de investigacion")

# ─────────────────────────────────────────────────────────────────────────────
# Filters
# ─────────────────────────────────────────────────────────────────────────────
all_areas = sorted(set(r["area"] for r in raw if r["area"]))
all_figuras = sorted(set(r["figura"] for r in raw if r.get("figura")))
max_h = max((r["h_index"] for r in raw), default=50)

_col_search, _col_pop = st.columns([3, 1])
with _col_search:
    busqueda = st.text_input(
        "Buscar por nombre",
        placeholder="Escribe para filtrar...",
        key="cand_busq",
        label_visibility="collapsed",
    )
with _col_pop:
    with st.popover("Filtros", icon=":material/filter_list:", use_container_width=True):
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            area_filter = st.multiselect("Area", all_areas, key="cand_area")
        with col_f2:
            figura_filter = st.multiselect("Figura", all_figuras, key="cand_figura")

        col_f3, col_f4 = st.columns(2)
        with col_f3:
            genero_filter = st.selectbox("Genero", ["Todos", "Mujer", "Hombre"], key="cand_genero")
        with col_f4:
            tend_filter = st.selectbox("Tendencia", ["Todas", "Positiva", "Negativa"], key="cand_tend")

        h_range = st.slider("Rango h-index", 0, int(max_h), (0, int(max_h)), key="cand_h")

        col_f5, col_f6 = st.columns(2)
        with col_f5:
            solo_eu = st.checkbox("Con proyectos EU", value=False, key="cand_solo_eu")
        with col_f6:
            vista_completa = st.checkbox("Todas las metricas", value=False, key="cand_vista")

# ─────────────────────────────────────────────────────────────────────────────
# Build table
# ─────────────────────────────────────────────────────────────────────────────
current_year = cfg.CURRENT_YEAR
tabla_full = []
for r in sorted(raw, key=lambda x: x["nombre_completo"]):
    if area_filter and r["area"] not in area_filter:
        continue
    if genero_filter != "Todos" and r["genero"] != genero_filter:
        continue
    if figura_filter and r.get("figura") not in figura_filter:
        continue
    if not (h_range[0] <= r["h_index"] <= h_range[1]):
        continue
    if solo_eu and r.get("proyectos_eu", 0) == 0:
        continue
    if tend_filter == "Positiva" and r["tendencia"] <= 0:
        continue
    if tend_filter == "Negativa" and r["tendencia"] >= 0:
        continue
    if busqueda and busqueda.lower() not in r["nombre_completo"].lower():
        continue
    ultima = r.get("ultima_publicacion", 0)
    anos_sin = (current_year - int(ultima)) if ultima and ultima > 0 else None
    row = {
        "Nombre": r["nombre_completo"],
        "Area": r["area"],
        "Figura": r.get("figura", ""),
        "Genero": r["genero"],
        "h": r["h_index"],
        "Tend.": r["tendencia"],
        "Impacto art.": round(r.get("impacto_art", 0), 1),
        "EU": r.get("proyectos_eu", 0),
        "Top%(Stanford)": r.get("stanford_percentil"),
        "Top%(OA)": r.get("openalex_pct"),
        "Anos s/pub": anos_sin,
        "Sexenios": r.get("sexenios", 0),
        "Fecha ult. sexenio": r.get("fecha_ultimo_sexenio", ""),
    }
    if vista_completa:
        row.update({
            "h (GS)": r.get("h_google_scholar") or "---",
            "h (OA)": r.get("h_openalex", 0),
            "h (Dial)": r.get("h_dialnet", 0),
            "i10": r.get("i10_index", 0),
            "Citas": r.get("citas_cruzadas", r["citas_2020"]),
            "Citas cruzadas": r.get("citas_cruzadas", 0),
            "IPs": r["proyectos_ip"],
            "Tesis": r["tesis_dir"],
            "EU IP": r.get("proyectos_eu_ip", 0),
            "Intl": r.get("instituciones_intl", 0),
            "Ultima pub.": r.get("ultima_publicacion", 0),
        })
    tabla_full.append(row)

df_cand = pd.DataFrame(tabla_full)

# ── Identify researchers with very large OpenAlex subfield pools ──
_big_pool_nombres = {
    r["nombre_completo"] for r in raw
    if (r.get("openalex_pct_total") or 0) > 5_000_000
}


def _color_oa_row(row):
    val = row.get("Top%(OA)")
    if row.get("Nombre") in _big_pool_nombres:
        return [
            "background-color: rgba(92,143,255,0.55); color: #181c1e" if col == "Top%(OA)" else ""
            for col in row.index
        ]
    return [color_stanford(val) if col == "Top%(OA)" else "" for col in row.index]


if not df_cand.empty:
    style = (
        df_cand.style
        .map(color_tendencia, subset=["Tend."])
        .map(color_anos_sin, subset=["Anos s/pub"])
        .map(color_stanford, subset=["Top%(Stanford)"])
        .apply(_color_oa_row, axis=1, subset=list(df_cand.columns))
        .format({"Tend.": "{:.3f}", "Impacto art.": "{:.1f}"})
    )
    st.dataframe(
        style, use_container_width=True, hide_index=True, height=620,
        column_config={
            "Tend.": st.column_config.NumberColumn(
                "Tend.", help="Evolucion reciente de citas. >0 = crecimiento, <0 = declive",
                format="%.3f"),
            "Impacto art.": st.column_config.NumberColumn(
                "Impacto art.",
                help="Media de citas Crossref por articulo en el periodo de referencia",
                format="%.1f"),
            "Anos s/pub": st.column_config.NumberColumn(
                "Anos s/pub", help="Anos desde la ultima publicacion conocida. Rojo si >= 5 anos",
                format="%d"),
            "h": st.column_config.NumberColumn(
                "h", help="Indice h combinado (maximo entre Google Scholar, OpenAlex)"),
            "EU": st.column_config.NumberColumn(
                "EU",
                help="Proyectos europeos (H2020, Horizon Europe, ERC, MSCA, COST, Interreg) a lo largo de toda la carrera investigadora."),
            "Top%(Stanford)": st.column_config.NumberColumn(
                "Top%(Stanford)",
                help="Percentil en su subcampo segun Stanford/Elsevier Top Scientists (single-year 2024). "
                     "Verde: top 2%, amarillo: top 10%, gris: sin datos.",
                format="%.1f%%"),
            "Top%(OA)": st.column_config.NumberColumn(
                "Top%(OA)",
                help="Percentil basado en c-score aproximado de Ioannidis. "
                     "Verde: top 2%, amarillo: top 10%, rojo: >10%.",
                format="%.1f%%"),
            "Tesis": st.column_config.NumberColumn(
                "Tesis",
                help="Tesis doctorales dirigidas a lo largo de toda la carrera investigadora."),
        },
    )
    st.caption(f"Mostrando {len(tabla_full)} de {len(raw)} miembros")
else:
    st.info("No hay miembros que cumplan los filtros seleccionados.", icon=":material/filter_list_off:")
    st.caption("Prueba ampliar el rango h-index, cambiar el área o quitar algún filtro.")

# ── Warning: large OpenAlex pools ──
_big_pool = [
    r for r in raw
    if (r.get("openalex_pct_total") or 0) > 5_000_000 and r.get("openalex_pct") is not None
]
if _big_pool:
    with st.expander(
        f"{len(_big_pool)} miembros con pool muy grande en OpenAlex (fiabilidad reducida)",
        expanded=False,
    ):
        st.warning(
            "Para los siguientes miembros el pool de su subfield en OpenAlex supera los "
            "5 millones de autores. En ciencias sociales y humanidades OpenAlex indexa ~400x mas "
            "autores que Scopus/Stanford, por lo que el percentil calculado no es directamente "
            "comparable con el ranking Stanford/Ioannidis.",
        )
        _bp_rows = []
        for r in sorted(_big_pool, key=lambda x: x.get("openalex_pct", 99)):
            _bp_rows.append({
                "Nombre": r["nombre_completo"],
                "Subfield": r.get("openalex_pct_subfield", "--"),
                "Pool (M)": round((r.get("openalex_pct_total") or 0) / 1_000_000, 1),
                "Top%(OA)": r.get("openalex_pct"),
                "h-index": r["h_index"],
                "Citas": r.get("citas_cruzadas", r.get("citas_2020", 0)),
            })
        st.dataframe(
            pd.DataFrame(_bp_rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Pool (M)": st.column_config.NumberColumn("Pool (M autores)", format="%.1fM"),
                "Top%(OA)": st.column_config.NumberColumn("Top%(OA)", format="%.1f%%"),
            },
        )
