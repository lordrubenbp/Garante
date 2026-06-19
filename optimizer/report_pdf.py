"""Generador de PDF para informe de garantes."""
import numpy as np
from fpdf import FPDF
from datetime import datetime

import os as _os
_FONT_MACOS       = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
_FONT_LINUX       = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_LINUX_BOLD  = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_WIN         = "C:/Windows/Fonts/arial.ttf"
FONT_PATH = next(
    (p for p in [_FONT_MACOS, _FONT_LINUX, _FONT_WIN] if _os.path.exists(p)),
    _FONT_MACOS  # fallback — will raise FileNotFoundError with a clear path
)
FONT_BOLD_PATH = _FONT_LINUX_BOLD if _os.path.exists(_FONT_LINUX_BOLD) else FONT_PATH


def generate_report_pdf(seleccionados, raw, K, z_total, params, diagnostico=None):
    """
    Genera un PDF con la propuesta de garantes y diagnostico.
    Si diagnostico es None, lo calcula internamente.
    Retorna bytes del PDF.
    """
    if diagnostico is None:
        from mip_garantes import compute_diagnostico
        diagnostico = compute_diagnostico(
            seleccionados, raw, K, params.get("N", len(seleccionados)),
            modalidad=params.get("modalidad", "MdM"),
            db_name=params.get("db_name")
        )

    N = params.get("N", len(seleccionados))
    m = diagnostico.get("metricas", {})

    pdf = FPDF()
    pdf.add_font("au", "", FONT_PATH)
    pdf.add_font("au", "B", FONT_BOLD_PATH)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Title
    pdf.set_font("au", "B", 18)
    pdf.set_text_color(0, 32, 69)
    pdf.cell(0, 12, "Propuesta de Garantes", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("au", "", 11)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 7, f"Convocatoria Severo Ochoa / Maria de Maeztu 2026", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # Parameters
    pdf.set_font("au", "B", 12)
    pdf.set_text_color(0, 32, 69)
    pdf.cell(0, 8, "Parametros de optimizacion", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("au", "", 10)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 6, f"N = {N} garantes | Excelencia: {params.get('alpha', 1.0)*100:.0f}% | Cohesion: {params.get('beta', 0.0)*100:.0f}% (desempate) | min-areas = {params.get('min_areas', '?')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Summary metrics
    pdf.set_font("au", "B", 12)
    pdf.set_text_color(0, 32, 69)
    pdf.cell(0, 8, "Metricas del subgrafo optimo", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("au", "", 10)
    pdf.set_text_color(30, 30, 30)
    _z_str = f"{z_total:.4f}" if z_total is not None else "N/A (solucion ajustada manualmente)"
    pdf.cell(0, 6, f"Z optimo: {_z_str}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"h-index medio: {m['h_mean']}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Cohesion media (K): {m['k_mean']} (informativo — no es criterio determinante)", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Mujeres: {m['mujeres']}/{N} ({m['mujeres_pct']:.0f}%) — paridad como criterio de desempate", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Areas distintas: {m['areas']} ({', '.join(m['areas_list'])})", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # Table of garantes
    pdf.set_font("au", "B", 12)
    pdf.set_text_color(0, 32, 69)
    pdf.cell(0, 8, "Garantes seleccionados", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    widths = [8, 52, 18, 45, 15, 15, 15]
    headers = ["#", "Nombre", "Genero", "Area", "h", "E_i", "EU"]
    pdf.set_font("au", "B", 9)
    pdf.set_fill_color(238, 241, 247)
    for h, w in zip(headers, widths):
        pdf.cell(w, 6, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("au", "", 9)
    pdf.set_text_color(30, 30, 30)
    for rank, i in enumerate(seleccionados, 1):
        r = raw[i]
        row = [
            str(rank),
            r["nombre_completo"][:30],
            r["genero"][:1],
            r["area"][:25],
            str(r["h_index"]),
            f"{r['E_i']:.3f}",
            str(r.get("proyectos_eu", 0)),
        ]
        for val, w in zip(row, widths):
            pdf.cell(w, 5.5, val, border=1)
        pdf.ln()

    pdf.ln(6)

    # Diagnostico from dict
    pdf.set_font("au", "B", 12)
    pdf.set_text_color(0, 32, 69)
    pdf.cell(0, 8, "Diagnostico y recomendaciones", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_text_color(30, 30, 30)

    pdf.set_font("au", "B", 10)
    pdf.cell(0, 6, "Fortalezas:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("au", "", 10)
    for f in diagnostico["fortalezas"]:
        pdf.cell(6)
        pdf.cell(0, 5.5, f"+ {f}", new_x="LMARGIN", new_y="NEXT")
    if not diagnostico["fortalezas"]:
        pdf.cell(6)
        pdf.cell(0, 5.5, "Ninguna destacable", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.set_font("au", "B", 10)
    pdf.cell(0, 6, "Debilidades:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("au", "", 10)
    for d in diagnostico["debilidades"]:
        pdf.cell(6)
        pdf.cell(0, 5.5, f"- {d}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.set_font("au", "B", 10)
    pdf.cell(0, 6, "Recomendaciones:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("au", "", 10)
    for rec in diagnostico["recomendaciones"]:
        pdf.cell(6)
        pdf.multi_cell(0, 5.5, f"- [{rec['prioridad']}] {rec['texto']}")
        pdf.ln(1)

    # Valoracion
    pdf.ln(4)
    pdf.set_font("au", "B", 11)
    pdf.cell(0, 7, f"VALORACION: {diagnostico['valoracion']}", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
