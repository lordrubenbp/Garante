#!/usr/bin/env python3
"""
Dashboard web — Optimizador de Garantes (multi-instituto)
Wizard multi-pagina con st.navigation().
"""
import streamlit as st

st.set_page_config(
    page_title="Garante — Selector de garantes",
    page_icon=":material/science:",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "**Garante** — Hybrid MIP-LLM guarantor selection for research-excellence calls",
    },
)

# ── Global CSS: shadows + expander white bg ──
st.markdown(
    """<style>
    /* Bordered containers: soft shadow */
    [data-testid="stVerticalBlockBorderWrapper"] {
        box-shadow: 0 1px 4px rgba(0,0,0,0.07);
    }
    /* Dataframes: soft shadow card */
    [data-testid="stDataFrame"] {
        box-shadow: 0 1px 4px rgba(0,0,0,0.07);
        border-radius: 10px;
        overflow: hidden;
    }
    /* Expander content: white background */
    [data-testid="stExpanderDetails"] {
        background-color: #ffffff;
    }
    </style>""",
    unsafe_allow_html=True,
)

# ── Sidebar branding ──
with st.sidebar:
    st.markdown(
        '<div style="padding:0.2rem 0 0.8rem;border-bottom:2px solid rgba(255,255,255,0.12);margin-bottom:0.5rem">'
        '<span style="font-family:Manrope,Inter,sans-serif;font-size:1.15rem;font-weight:800;letter-spacing:-0.02em;color:rgba(255,255,255,0.92)">Garante</span>'
        '<span style="display:block;font-size:0.62rem;font-weight:500;letter-spacing:0.1px;color:rgba(255,255,255,0.5);line-height:1.3;margin-top:2px">'
        'MIP + LLM guarantor selection</span>'
        '<span style="display:block;font-size:0.58rem;color:rgba(255,255,255,0.35);margin-top:3px;letter-spacing:0.3px">open-source toolkit</span>'
        '</div>',
        unsafe_allow_html=True,
    )

# ── Initialize wizard state ──
if "wizard_step" not in st.session_state:
    st.session_state.wizard_step = 1
if "seleccionados" not in st.session_state:
    st.session_state.seleccionados = None

# ── Define pages ──
wizard_pages = [
    st.Page("pages/1_configuracion.py", title="Configuracion", icon=":material/settings:"),
    st.Page("pages/2_preseleccion.py", title="Preseleccion", icon=":material/group:"),
    st.Page("pages/3_fase1.py", title="Fase 1 — Perfiles", icon=":material/rate_review:"),
    st.Page("pages/4_fase2.py", title="Fase 2 — Propuesta", icon=":material/upload_file:"),
    st.Page("pages/5_resultado.py", title="Resultado final", icon=":material/assessment:"),
]

tool_pages = [
    st.Page("pages/candidatos.py", title="Miembros", icon=":material/people:"),
    st.Page("pages/lab_red.py", title="Red de copublicaciones", icon=":material/hub:"),
    st.Page("pages/lab_nucleos.py", title="Nucleos colaborativos", icon=":material/group_work:"),
]

nav = st.navigation(
    {"Wizard": wizard_pages, "Herramientas": tool_pages},
    position="sidebar",
)

nav.run()
