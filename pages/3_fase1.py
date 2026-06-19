#!/usr/bin/env python3
"""Paso 3: Evaluacion Fase 1 — evaluacion cualitativa LLM de garantes + casi-garantes."""
import sys
import os
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "optimizer"))
import config as cfg
from mip_garantes import compute_diagnostico, diagnosticar_casi_garantes

from ui.wizard_common import (
    render_progress_bar, wizard_nav, require_step,
    get_instituto_label, get_modalidad_label,
    color_nivel, color_estado,
    color_tendencia, color_anos_sin, color_stanford,
)
import datetime as _dt


# ── Helpers de formato (igual que preseleccion) ──
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


def _color_pts_ia(val):
    """Colorea la puntuacion IA (escala 0-10, umbral 9)."""
    if val is None:
        return ""
    if val >= 9.0:
        return "background-color: rgba(76,175,125,0.65); color: #181c1e; font-family: monospace; font-weight:600"
    if val >= 7.0:
        return "background-color: rgba(139,195,74,0.55); color: #181c1e; font-family: monospace"
    if val >= 5.0:
        return "background-color: rgba(255,193,7,0.55); color: #181c1e; font-family: monospace"
    if val >= 3.0:
        return "background-color: rgba(255,112,67,0.55); color: #181c1e; font-family: monospace"
    return "background-color: rgba(198,40,40,0.65); color: #181c1e; font-family: monospace"


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


_ROW_HEIGHT = 35
_HEADER_HEIGHT = 38
_current_year = cfg.CURRENT_YEAR

# ── Gate ──
require_step(3)

if any(st.session_state.get(k) is None for k in ("seleccionados", "raw_f", "E_f", "docs_f", "params")):
    st.warning("Sesion expirada o datos no disponibles. Vuelve al Paso 1 y ejecuta la optimizacion.")
    st.stop()

# ── Load state ──
sel = st.session_state.seleccionados
r_f = st.session_state.raw_f
E_f = st.session_state.E_f
K = st.session_state.K
docs_f = st.session_state.docs_f
stored_params = st.session_state.params
modalidad_code = stored_params.get("modalidad", "MdM")

# ── Header ──
render_progress_bar(3)
st.title("Evaluacion Fase 1")
st.caption(f"{get_instituto_label()} · {get_modalidad_label(modalidad_code)}")
with st.expander("Como funciona esta evaluacion", icon=":material/info:"):
    st.markdown("""
Un comite de IA (Claude Opus) revisa los **perfiles completos** de los garantes seleccionados
y de los **mejores excluidos** (casi-garantes). Para cada candidato redacta sus **10 hitos principales**
y evalua si cuentan una **narrativa coherente de excelencia internacional** (0-10, umbral 9).
DORA-compatible: se valora el impacto real del trabajo, no el prestigio de las revistas.
Si algun excluido supera a un seleccionado, se recomienda el intercambio.
""")

# ── Check for existing results ──
result = st.session_state.get("evaluacion_fase1")

# ── Evaluate button ──
btn_fase1 = st.button(
    "Re-evaluar Fase 1" if result else "Evaluar Fase 1",
    type="primary", use_container_width=True,
    icon=":material/rate_review:",
)

if btn_fase1:
    from llm_evaluador import evaluar_fase1_experta

    if not cfg.ANTHROPIC_API_KEY:
        st.error("Configura ANTHROPIC_API_KEY en .env")
        st.stop()

    sel_raw = [r_f[i] for i in sel]
    docs_sel = [docs_f[i] for i in sel]

    _casi = diagnosticar_casi_garantes(r_f, E_f, sel, stored_params, m=5)
    casi_indices = [c["idx"] for c in _casi] if _casi else []
    casi_raw = [r_f[i] for i in casi_indices]
    casi_docs = [docs_f[i] for i in casi_indices]

    progress_bar = st.progress(0, text="Iniciando evaluacion Fase 1...")

    def _fase1_progress(i, total, nombre):
        if total > 0:
            progress_bar.progress(i / total, text=f"Evaluando {nombre} ({i+1}/{total})...")

    result = evaluar_fase1_experta(
        sel_raw, docs_sel, casi_raw, casi_docs,
        modalidad=modalidad_code,
        db_name=st.session_state.get("instituto"),
        progress_callback=_fase1_progress,
    )
    progress_bar.progress(1.0, text="Evaluacion completada")

    if result and "error" not in result:
        st.session_state.evaluacion_fase1 = result
    else:
        st.error(f"Error en evaluacion Fase 1: {(result or {}).get('error', 'sin respuesta del modelo')}")
        st.stop()

# ── Display results ──
if result:
    superan = result.get("superan_umbral", 0)
    necesarios = result.get("necesarios", 6)
    superada = result.get("superada_fase1", False)

    if superada:
        st.success(f"FASE 1 SUPERADA: {superan}/{necesarios} garantes seleccionados superan el umbral 9/10")
    else:
        st.error(f"FASE 1 NO SUPERADA: solo {superan}/{necesarios} garantes seleccionados superan el umbral 9/10")

    # ── Construir lookup IA por índice posicional (robusto, no depende del nombre) ──
    evaluaciones = result.get("evaluaciones", [])
    sel_evals = [ev for ev in evaluaciones if ev.get("es_seleccionado")]
    casi_evals = [ev for ev in evaluaciones if not ev.get("es_seleccionado")]

    # Mapeo índice r_f → evaluación IA para seleccionados MIP
    _ia_by_sel_idx = {
        sel[j]: sel_evals[j]
        for j in range(min(len(sel), len(sel_evals)))
    }
    # Mapeo índice r_f → evaluación IA para casi-garantes
    _casi_diag = diagnosticar_casi_garantes(r_f, E_f, sel, stored_params, m=5)
    _casi_indices = [c["idx"] for c in _casi_diag] if _casi_diag else []
    _ia_by_casi_idx = {
        _casi_indices[j]: casi_evals[j]
        for j in range(min(len(_casi_indices), len(casi_evals)))
    }
    # Lookup unificado: índice r_f → evaluación IA
    _ia_by_idx = {**_ia_by_sel_idx, **_ia_by_casi_idx}

    # ── Ranking unificado por nota IA → los top N son "seleccionados IA" ──
    todos_indices = list(set(list(sel) + _casi_indices))
    todos_con_pts = sorted(
        todos_indices,
        key=lambda i: _ia_by_idx.get(i, {}).get("puntuacion") or -1,
        reverse=True,
    )
    top_n = todos_con_pts[:necesarios]
    resto = todos_con_pts[necesarios:]

    # ── Helper para construir fila de tabla ──
    def _fila(i, rank=None):
        r = r_f[i]
        ultima = r.get("ultima_publicacion", 0)
        anos_sin = (_current_year - int(ultima)) if ultima and ultima > 0 else None
        ev = _ia_by_idx.get(i, {})
        pts_ia = ev.get("puntuacion")
        row = {
            "Nombre": r["nombre_completo"],
            "Genero": r["genero"],
            "Area": r["area"],
            "Figura": r.get("figura", ""),
            "Preseleccion": _ei_to_10(r["E_i"]),
            "IA (0-10)": pts_ia,
            "Umbral": "Si" if (pts_ia is not None and pts_ia >= 9) else ("No" if pts_ia is not None else "—"),
            "Veredicto IA": ev.get("veredicto", ""),
            "En MIP": "Si" if i in set(sel) else "No",
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
            "Nivel": _nivel_ei(r["E_i"]),
        }
        if rank is not None:
            row = {"N": rank, **row}
        return row

    def _make_styled_df(filas, include_n=True):
        df = pd.DataFrame(filas)
        df["Barra"] = df["Preseleccion"].apply(_barra_puntuacion)

        def _style_row(row):
            styles = [""] * len(row)
            if "Barra" in row.index:
                styles[row.index.get_loc("Barra")] = _color_puntuacion(row["Preseleccion"])
            if "IA (0-10)" in row.index:
                styles[row.index.get_loc("IA (0-10)")] = _color_pts_ia(row["IA (0-10)"])
            return styles

        styled = (
            df.style
            .apply(_style_row, axis=1)
            .map(color_tendencia, subset=["Tendencia"])
            .map(color_nivel, subset=["Nivel"])
            .map(color_anos_sin, subset=["Anos s/pub"])
            .map(color_stanford, subset=["Top%(Stanford)"])
            .format({"Tendencia": "{:.3f}", "Impacto art.": "{:.1f}", "IA (0-10)": "{:.1f}"}, na_rep="—")
        )
        return df, styled

    # ── Tabla seleccionados IA ──
    st.subheader(f":material/verified_user: Top {necesarios} según evaluacion IA")
    st.caption(f"Los {necesarios} candidatos con mayor puntuacion IA de entre seleccionados MIP + mejores excluidos.")

    filas_top = [_fila(i, rank=rank) for rank, i in enumerate(top_n, 1)]
    df_top, df_top_styled = _make_styled_df(filas_top)

    _mostrar_todo_sel = st.toggle("Mostrar todos los campos", value=False, key="fase1_sel_todo")
    _col_base_sel = ["N", "Nombre", "Genero", "Area", "Barra", "IA (0-10)", "Umbral", "Veredicto IA", "En MIP", "h-index", "Tendencia", "IPs", "Intl"]
    _col_full_sel = [
        "N", "Nombre", "Genero", "Area", "Figura", "Barra", "IA (0-10)", "Umbral", "Veredicto IA", "En MIP",
        "h-index", "Tendencia", "IPs", "EU", "Intl",
        "i10", "Impacto art.", "Sexenios", "Fecha ult. sexenio",
        "Top%(Stanford)", "Top%(OA)", "Anos s/pub", "Nivel",
    ]
    _cc_comun = {
        "Preseleccion": None,
        "N": st.column_config.NumberColumn("N", width="small"),
        "Barra": st.column_config.TextColumn("Preseleccion (0-10)", help="Score MIP (E_i × 10)", width="medium"),
        "IA (0-10)": st.column_config.NumberColumn("Evaluacion IA (0-10)", help="Nota del panel IA. Umbral: 9/10", format="%.1f", width="medium"),
        "Umbral": st.column_config.TextColumn("Umbral ≥9", width="small"),
        "Veredicto IA": st.column_config.TextColumn("Veredicto IA", width="large"),
        "En MIP": st.column_config.TextColumn("En MIP", help="Estaba en la seleccion del optimizador", width="small"),
        "Nivel": st.column_config.TextColumn("Nivel"),
        "h-index": st.column_config.NumberColumn("h-index"),
        "Tendencia": st.column_config.NumberColumn("Tendencia", format="%.3f"),
        "EU": st.column_config.NumberColumn("EU"),
        "IPs": st.column_config.NumberColumn("IPs"),
        "Intl": st.column_config.NumberColumn("Intl"),
        "i10": st.column_config.NumberColumn("i10"),
        "Impacto art.": st.column_config.NumberColumn("Impacto art.", format="%.1f"),
        "Sexenios": st.column_config.NumberColumn("Sexenios"),
        "Fecha ult. sexenio": st.column_config.TextColumn("Fecha ult. sexenio"),
        "Top%(Stanford)": st.column_config.NumberColumn("Top%(Stanford)", format="%.1f%%"),
        "Top%(OA)": st.column_config.NumberColumn("Top%(OA)", format="%.1f%%"),
        "Anos s/pub": st.column_config.NumberColumn("Anos s/pub", format="%d"),
    }

    st.dataframe(
        df_top_styled,
        use_container_width=True,
        hide_index=True,
        height=_HEADER_HEIGHT + _ROW_HEIGHT * len(df_top),
        column_order=_col_full_sel if _mostrar_todo_sel else _col_base_sel,
        column_config=_cc_comun,
    )

    # ── Cambiar un garante (justo tras los seleccionados IA) ──
    with st.expander("Cambiar un garante tras la evaluacion", expanded=False, icon=":material/swap_horiz:"):
        sel_set = set(sel)
        pool_no_sel_indices = sorted(
            [i for i in range(len(r_f)) if i not in sel_set],
            key=lambda i: -r_f[i]["E_i"],
        )

        _swap_col_out, _swap_col_in = st.columns(2)
        with _swap_col_out:
            garante_out_idx = st.selectbox(
                "Garante a sustituir",
                options=list(sel),
                format_func=lambda i: r_f[i]["nombre_completo"],
                key="fase1_swap_out",
            )
        with _swap_col_in:
            garante_in_idx = st.selectbox(
                "Reemplazo del pool",
                options=[None] + pool_no_sel_indices,
                format_func=lambda i: "--" if i is None else (
                    f"{r_f[i]['nombre_completo']} ({r_f[i]['area']}, E_i={r_f[i]['E_i']:.4f})"
                ),
                key="fase1_swap_in",
            )
        if garante_in_idx is not None and garante_out_idx is not None:
            if st.button("Aplicar cambio y re-evaluar", type="primary"):
                new_sel = list(sel)
                if garante_out_idx in new_sel:
                    pos = new_sel.index(garante_out_idx)
                    new_sel[pos] = garante_in_idx
                    st.session_state.seleccionados = new_sel
                    st.session_state["z_total"] = None
                    st.session_state.diagnostico = compute_diagnostico(
                        new_sel, r_f, K, stored_params.get("N", len(new_sel)),
                        modalidad=modalidad_code,
                        db_name=stored_params.get("db_name"),
                    )
                    st.session_state.pop("evaluacion_fase1", None)
                    st.session_state.pop("evaluacion_fase2", None)
                    st.session_state["wizard_step"] = min(
                        st.session_state.get("wizard_step", 3), 3
                    )
                    st.rerun()

    # ── Tabla excluidos IA ──
    if resto:
        with st.expander(":material/person_remove: Excluidos por evaluacion IA", expanded=True):
            st.caption("Candidatos que no entran en el top según la IA, ordenados por nota IA descendente.")

            filas_exc = [_fila(i) for i in resto]
            df_exc, df_exc_styled = _make_styled_df(filas_exc, include_n=False)

            _mostrar_todo_exc = st.toggle("Mostrar todos los campos", value=False, key="fase1_exc_todo")
            _col_base_exc = ["Nombre", "Genero", "Area", "Barra", "IA (0-10)", "Umbral", "Veredicto IA", "En MIP", "h-index", "Tendencia", "IPs", "Intl"]
            _col_full_exc = [
                "Nombre", "Genero", "Area", "Figura", "Barra", "IA (0-10)", "Umbral", "Veredicto IA", "En MIP",
                "h-index", "Tendencia", "IPs", "EU", "Intl",
                "i10", "Impacto art.", "Sexenios",
                "Top%(Stanford)", "Top%(OA)", "Anos s/pub", "Nivel",
            ]
            _cc_exc = {k: v for k, v in _cc_comun.items() if k != "N"}

            st.dataframe(
                df_exc_styled,
                use_container_width=True,
                hide_index=True,
                height=_HEADER_HEIGHT + _ROW_HEIGHT * len(df_exc),
                column_order=_col_full_exc if _mostrar_todo_exc else _col_base_exc,
                column_config=_cc_exc,
            )

    # ── Intercambios recomendados ──
    swaps = result.get("swaps_recomendados", [])
    if swaps:
        st.subheader(":material/compare_arrows: Intercambios recomendados")
        st.info(f"Se detectaron {len(swaps)} excluido(s) con puntuacion IA superior a algún seleccionado.", icon=":material/swap_horiz:")
        swap_data = []
        for sw in swaps:
            swap_data.append({
                "Excluido (entra)": sw.get("excluido", "?"),
                "Pts excluido": sw.get("excluido_pts", 0),
                "Seleccionado (sale)": sw.get("seleccionado", "?"),
                "Pts seleccionado": sw.get("seleccionado_pts", 0),
                "Diferencia": round(sw.get("excluido_pts", 0) - sw.get("seleccionado_pts", 0), 1),
            })
        st.dataframe(pd.DataFrame(swap_data), use_container_width=True, hide_index=True)

    val_conj = result.get("valoracion_conjunto", "")
    if val_conj:
        st.subheader(":material/forum: Valoracion del conjunto")
        st.markdown(f"> {val_conj}")

    # ── Detalle expandible por candidato ──
    if evaluaciones:
        st.subheader(":material/person_search: Detalle por candidato")
        for ev in evaluaciones:
            nombre = ev.get("nombre", "?")
            pts = ev.get("puntuacion", "?")
            veredicto = ev.get("veredicto", "")
            es_sel = ev.get("es_seleccionado", True)
            tag = "SEL" if es_sel else "EXC"
            with st.expander(f"[{tag}] {nombre} · {pts}/10 — {veredicto}"):
                hitos = ev.get("hitos", [])
                if hitos:
                    st.markdown("**Hitos principales:**")
                    for i, h in enumerate(hitos, 1):
                        st.markdown(f"{i}. {h}")
                narrativa = ev.get("narrativa", "")
                if narrativa:
                    st.markdown("**Narrativa de excelencia:**")
                    st.markdown(f"_{narrativa}_")
                col_f, col_d = st.columns(2)
                with col_f:
                    fortalezas = ev.get("fortalezas", [])
                    if fortalezas:
                        st.markdown("**Fortalezas:**")
                        for f in fortalezas:
                            st.markdown(f"- {f}")
                with col_d:
                    debilidades = ev.get("debilidades", [])
                    if debilidades:
                        st.markdown("**Debilidades:**")
                        for d in debilidades:
                            st.markdown(f"- {d}")

    errores = result.get("errores", [])
    if errores:
        st.warning(f"Errores en {len(errores)} evaluacion(es): " + "; ".join(errores))

# ── Navigation ──
can_advance = result is not None
if can_advance:
    st.session_state.wizard_step = max(st.session_state.get("wizard_step", 3), 4)
wizard_nav(3, can_advance=can_advance)
