"""Shared UI components for the wizard multi-page flow."""
import streamlit as st
import streamlit.components.v2 as _stv2
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "optimizer"))
import config as cfg


STEP_NAMES = [
    "Configuracion",
    "Preseleccion",
    "Fase 1",
    "Fase 2",
    "Resultado",
]

_PAGE_FILES = {
    1: "pages/1_configuracion.py",
    2: "pages/2_preseleccion.py",
    3: "pages/3_fase1.py",
    4: "pages/4_fase2.py",
    5: "pages/5_resultado.py",
}

_INVALIDATION_KEYS = {
    2: ["seleccionados", "K", "raw_f", "E_f", "docs_f", "z_total", "params", "diagnostico", "saved_runs", "_pending_swaps"],
    3: ["evaluacion_fase1", "_pending_swaps"],
    4: ["evaluacion_fase2"],
    5: [],
}

# ── Wizard stepper — CCv2 inline component ─────────────────────────────────────
_STEPPER_CSS = """
/* Load Manrope — institutional display font */
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@600;700;800&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body { overflow: hidden; }

.stepper {
  display: flex;
  align-items: flex-start;
  width: 100%;
  padding: 10px 4px 12px;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

/* Each step: circle + label stacked */
.step-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  min-width: 72px;
}

/* Horizontal connector line between steps */
.connector {
  flex: 1;
  height: 2px;
  margin-top: 18px;   /* vertically centres line with the 36px circle */
  min-width: 16px;
  border-radius: 2px;
  transition: background 0.35s ease;
}

/* ── Step circle ── */
.circle {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Manrope', 'Inter', system-ui, sans-serif;
  font-size: 14px;
  font-weight: 800;
  border: 2.5px solid;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  user-select: none;
  cursor: default;
  position: relative;
}

.circle.active-step {
  width: 38px;
  height: 38px;
  font-size: 15px;
  border-width: 3px;
}

.circle.clickable {
  cursor: pointer;
}
.circle.clickable:hover {
  transform: scale(1.12);
}

/* ── Step label ── */
.label {
  font-family: 'Manrope', 'Inter', system-ui, sans-serif;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.3;
  text-align: center;
  white-space: nowrap;
  margin-top: 7px;
  letter-spacing: 0.02em;
  transition: color 0.2s;
}

.label.active {
  font-weight: 800;
  font-size: 11.5px;
  letter-spacing: 0.01em;
}

.label.active::after {
  content: '';
  display: block;
  width: 20px;
  height: 3px;
  border-radius: 2px;
  margin: 4px auto 0;
  background: currentColor;
  opacity: 0.55;
}
"""

_STEPPER_JS = r"""
export default function(component) {
  const { data, parentElement, setTriggerValue } = component;
  if (!data) return;

  const { steps, currentStep, maxStep } = data;
  const root = parentElement.querySelector('#root');
  if (!root) return;

  /* ── Theme detection ────────────────────────────────────────────────────── */
  function isDark() {
    // Walk candidates; stAppViewContainer is transparent so we skip it and
    // use document.body which always carries the real background color.
    const candidates = [
      document.querySelector('[data-testid="stAppViewContainer"]'),
      document.querySelector('.stApp'),
      document.body,
    ].filter(Boolean);

    for (const el of candidates) {
      const bg = window.getComputedStyle(el).backgroundColor;
      const m = bg.match(/[\d.]+/g);
      if (!m || m.length < 3) continue;
      const alpha = m.length >= 4 ? parseFloat(m[3]) : 1;
      if (alpha < 0.1) continue;   // skip fully-transparent elements
      const lum = (0.299 * +m[0] + 0.587 * +m[1] + 0.114 * +m[2]) / 255;
      return lum < 0.4;
    }
    return false;   // default: light
  }

  const dark = isDark();

  /* ── Color tokens ───────────────────────────────────────────────────────── */
  // ── institutional palette ────────────────────────────────────────
  // Institutional palette
  //   primary: #002045 (deep navy)  action: #2962ff (vivid blue)
  const T = dark ? {
    // ● done: deep navy fill — completed, authoritative
    done_bg:      '#003762',
    done_border:  '#003762',
    done_fg:      '#ffffff',
    done_label:   '#80aaff',
    // ● active: vivid action-blue ring + glow
    active_bg:    'rgba(41,98,255,0.10)',
    active_border:'#2962ff',
    active_fg:    '#80aaff',
    active_label: '#ccd9ff',
    active_shadow:'0 0 0 5px rgba(41,98,255,0.22), 0 2px 8px rgba(41,98,255,0.14)',
    // ● available — muted blue, clickable
    avail_bg:     'transparent',
    avail_border: '#1a365d',
    avail_fg:     '#80aaff',
    avail_label:  '#80aaff',
    avail_shadow: 'none',
    // ● locked — dark, clearly inactive
    locked_bg:    'transparent',
    locked_border:'#21262d',
    locked_fg:    '#484f58',
    locked_label: '#484f58',
    // ── connectors
    conn_done:    '#003762',
    conn_todo:    '#21262d',
    conn_avail:   '#1a365d',
  } : {
    // ● done — deep institutional navy, solid institutional authority
    done_bg:      '#002045',
    done_border:  '#002045',
    done_fg:      '#ffffff',
    done_label:   '#002045',
    // ● active — white fill, vivid action-blue ring, near-black label
    active_bg:    '#ffffff',
    active_border:'#2962ff',
    active_fg:    '#2962ff',
    active_label: '#181c1e',
    active_shadow:'0 0 0 5px rgba(41,98,255,0.16), 0 2px 8px rgba(41,98,255,0.10)',
    // ● available — medium blue, clearly clickable
    avail_bg:     '#ffffff',
    avail_border: '#80aaff',
    avail_fg:     '#2962ff',
    avail_label:  '#2962ff',
    avail_shadow: 'none',
    // ● locked — neutral gray, readable but clearly inactive
    locked_bg:    '#f4f6fa',
    locked_border:'#d8dde8',
    locked_fg:    '#9ea6b4',
    locked_label: '#9ea6b4',
    // ── connectors
    conn_done:    '#002045',
    conn_todo:    '#eef1f7',
    conn_avail:   '#c8d8ff',
  };

  /* ── Build DOM ──────────────────────────────────────────────────────────── */
  root.innerHTML = '';
  const stepper = document.createElement('div');
  stepper.className = 'stepper';

  steps.forEach((step, idx) => {
    const num       = idx + 1;
    const isDone    = num < currentStep;
    const isActive  = num === currentStep;
    const isAvail   = num > currentStep && num <= maxStep;
    // else: locked

    /* Circle */
    const circle = document.createElement('div');
    const isClickable = isDone || isAvail;
    circle.className = 'circle' + (isClickable ? ' clickable' : '');

    if (isDone) {
      circle.style.background   = T.done_bg;
      circle.style.borderColor  = T.done_border;
      circle.style.color        = T.done_fg;
      circle.innerHTML          = '&#10003;';  // ✓ checkmark
      circle.title              = 'Ir a ' + step;
      circle.onclick            = () => setTriggerValue('clicked', idx);
    } else if (isActive) {
      circle.className += ' active-step';
      circle.style.background   = T.active_bg;
      circle.style.borderColor  = T.active_border;
      circle.style.color        = T.active_fg;
      circle.style.boxShadow    = T.active_shadow;
      circle.textContent        = num;
    } else if (isAvail) {
      circle.style.background   = T.avail_bg;
      circle.style.borderColor  = T.avail_border;
      circle.style.color        = T.avail_fg;
      circle.textContent        = num;
      circle.title              = 'Ir a ' + step;
      circle.onclick            = () => setTriggerValue('clicked', idx);
    } else {
      circle.style.background   = T.locked_bg;
      circle.style.borderColor  = T.locked_border;
      circle.style.color        = T.locked_fg;
      circle.textContent        = num;
    }

    /* Label */
    const label = document.createElement('div');
    label.className = 'label ' + (isActive ? 'active' : '');
    label.style.color = isDone  ? T.done_label
                      : isActive ? T.active_label
                      : isAvail  ? T.avail_label
                      : T.locked_label;
    label.textContent = step;

    /* Column */
    const col = document.createElement('div');
    col.className = 'step-col';
    col.appendChild(circle);
    col.appendChild(label);
    stepper.appendChild(col);

    /* Connector (not after the last step) */
    if (idx < steps.length - 1) {
      const conn = document.createElement('div');
      conn.className = 'connector';
      conn.style.background = isDone  ? T.conn_done
                            : isAvail ? T.conn_avail
                            : T.conn_todo;
      stepper.appendChild(conn);
    }
  });

  root.appendChild(stepper);
}
"""

_STEPPER_HTML = f"<style>{_STEPPER_CSS}</style><div id='root'></div>"

# Registered once at module import — name must be unique across the app
_wizard_stepper = _stv2.component(
    "wizard_stepper_v1",
    html=_STEPPER_HTML,
    js=_STEPPER_JS,
)


def render_progress_bar(current_step: int):
    """Render the wizard step indicator at the top of the page.

    Completed steps show a ✓ and are clickable (navigate back).
    Available steps (unlocked but ahead) are clickable too.
    Locked steps are gray and inactive.
    """
    max_step = st.session_state.get("wizard_step", 1)

    result = _wizard_stepper(
        key=f"wizard_steps_{current_step}",
        data={
            "steps": STEP_NAMES,
            "currentStep": current_step,
            "maxStep": max_step,
        },
        on_clicked_change=lambda: None,
        height=84,
    )

    # Navigate on click
    if result is not None and result.clicked is not None:
        target = int(result.clicked) + 1  # 0-based index → 1-based step number
        if 1 <= target <= max_step and target != current_step:
            st.switch_page(_PAGE_FILES[target])


def invalidate_from(step: int):
    """Clear session_state keys for step and all subsequent steps."""
    for s in range(step, 6):
        for key in _INVALIDATION_KEYS.get(s, []):
            st.session_state.pop(key, None)
    st.session_state["wizard_step"] = step - 1


def wizard_nav(current_step: int, can_advance: bool = True):
    """Render Previous / Next navigation buttons at the bottom."""
    st.space("medium")
    has_prev = current_step > 1
    has_next = current_step < 5

    if has_prev and has_next:
        col_prev, _, col_next = st.columns([1, 3, 1])
        with col_prev:
            if st.button("Anterior", icon=":material/arrow_back:", use_container_width=True):
                invalidate_from(current_step)
                st.switch_page(_PAGE_FILES[current_step - 1])
        with col_next:
            clicked = st.button(
                "Siguiente →",
                type="primary",
                use_container_width=True,
                disabled=not can_advance,
                help=None if can_advance else "Completa este paso para continuar",
            )
            if clicked and can_advance:
                st.switch_page(_PAGE_FILES[current_step + 1])
    elif has_prev:
        col_prev, _ = st.columns([1, 4])
        with col_prev:
            if st.button("Anterior", icon=":material/arrow_back:", use_container_width=True):
                invalidate_from(current_step)
                st.switch_page(_PAGE_FILES[current_step - 1])
    elif has_next:
        _, col_next = st.columns([4, 1])
        with col_next:
            clicked = st.button(
                "Siguiente →",
                type="primary",
                use_container_width=True,
                disabled=not can_advance,
                help=None if can_advance else "Completa este paso para continuar",
            )
            if clicked and can_advance:
                st.switch_page(_PAGE_FILES[current_step + 1])


def require_step(minimum_step: int):
    """Block access if the wizard hasn't reached this step yet."""
    if st.session_state.get("wizard_step", 1) < minimum_step:
        st.warning("Completa el paso anterior primero.")
        st.stop()


def get_instituto_label() -> str:
    """Return the human-readable name of the current institute."""
    return cfg.get_instituto_info(
        st.session_state.get("instituto", cfg.DB_NAME)
    )["nombre"]


def get_modalidad_label(code: str) -> str:
    """Return the human-readable name of the modality."""
    return {"SO": "Severo Ochoa", "MdM": "Maria de Maeztu", "UEI": "UEI (Junta Andalucia)"}.get(code, code)


# ── Styling helpers (used across pages) ──

def color_tendencia(val):
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


def color_umbral(val):
    if val == "Si":
        return "background-color: rgba(76,175,125,0.55); color: #181c1e"
    elif val == "No":
        return "background-color: rgba(229,115,115,0.55); color: #181c1e"
    return ""


def color_nivel(val):
    colores = {
        "Excepcional": "background-color: rgba(76,175,125,0.55); color: #181c1e",
        "Solido":      "background-color: rgba(139,195,74,0.55); color: #181c1e",
        "Aceptable":   "background-color: rgba(255,193,7,0.55); color: #181c1e",
        "Debil":       "background-color: rgba(255,112,67,0.55); color: #181c1e",
        "No apto":     "background-color: rgba(198,40,40,0.65); color: #181c1e",
    }
    return colores.get(val, "")


def color_estado(val):
    if val == "Excluido":
        return "background-color: rgba(198,40,40,0.65); color: #181c1e"
    return ""


def color_estado(val):
    if val == "Excluido":
        return "color: #c62828; font-weight: bold"
    return ""


def _pretty_institute(db_name: str) -> str:
    """Return a display-friendly institute name (strips '_claude' suffix)."""
    return db_name.replace("_claude", "")


def render_tool_instituto_selector() -> tuple[str, str]:
    """Render a standalone instituto selector for tool pages.

    Uses session keys prefixed with '_tools_' so they are independent from
    the wizard flow. Returns (instituto_db_name, modalidad_code).
    The modalidad is inherited from the wizard session if available,
    otherwise defaults to 'MdM' — it is not shown in the UI.
    """
    from mip_garantes import discover_institutes

    @st.cache_data(ttl=60)
    def _institutes():
        return discover_institutes()

    institutes = _institutes()
    if not institutes:
        institutes = [cfg.DB_NAME]

    # Default to wizard value if set, otherwise first institute
    _default_inst = st.session_state.get(
        "_tools_instituto",
        st.session_state.get("instituto", institutes[0] if institutes else ""),
    )
    _default_inst_idx = (
        institutes.index(_default_inst)
        if _default_inst in institutes else 0
    )

    with st.container(border=True):
        instituto = st.selectbox(
            "Instituto",
            options=institutes,
            index=_default_inst_idx,
            format_func=_pretty_institute,
            key="_tools_instituto",
        )

    # Use wizard modalidad if available, otherwise MdM
    modalidad_code = st.session_state.get(
        "modalidad",
        st.session_state.get("_tools_modalidad", "MdM"),
    )
    return instituto, modalidad_code


def color_sel(val):
    if val == "Si":
        return "background-color: rgba(76,175,125,0.55); color: #181c1e"
    return ""


def color_anos_sin(val):
    if isinstance(val, (int, float)) and val >= 5:
        return "background-color: rgba(229,115,115,0.55); color: #181c1e"
    return ""


def color_stanford(val):
    if val is None or (isinstance(val, float) and val != val):
        return "color: #6e7178"
    if val <= 2:
        return "background-color: rgba(76,175,125,0.55); color: #181c1e"
    if val <= 5:
        return "background-color: rgba(139,195,74,0.55); color: #181c1e"
    if val <= 10:
        return "background-color: rgba(205,220,57,0.55); color: #181c1e"
    if val <= 20:
        return "background-color: rgba(255,235,59,0.55); color: #181c1e"
    if val <= 35:
        return "background-color: rgba(255,193,7,0.55); color: #181c1e"
    if val <= 50:
        return "background-color: rgba(255,112,67,0.55); color: #181c1e"
    return "background-color: rgba(229,115,115,0.55); color: #181c1e"
