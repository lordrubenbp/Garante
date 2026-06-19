"""Generador de argumentario con Claude API para solicitudes SO/MdM."""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

SYSTEM_PROMPT = """Eres un experto en convocatorias de excelencia investigadora del Ministerio de Ciencia de España (Severo Ochoa y María de Maeztu). Tu tarea es redactar un argumentario convincente para la solicitud, justificando la composición del panel de garantes propuesto.

Criterios de evaluación SO/MdM que debes tener en cuenta:
- Excelencia científica: producción de alto impacto, h-index competitivo internacionalmente
- Cohesión y trabajo en equipo: evidencia de colaboración real (copublicaciones)
- Interdisciplinariedad: diversidad de áreas que enriquece la investigación
- Paridad de género: composición equilibrada
- Proyección futura: tendencia ascendente, capacidad de liderazgo
- Impacto social y transferencia: especialmente relevante en CCSS

Escribe en español formal académico. El texto debe ser directo, con datos concretos, y listo para incluir en la memoria de solicitud. No uses bullet points — redacta párrafos argumentativos fluidos. Extensión: 400-600 palabras."""


def generar_argumentario(diagnostico, sel_raw, params):
    """
    Genera un argumentario narrativo usando Claude API.

    Args:
        diagnostico: dict de compute_diagnostico()
        sel_raw: lista de dicts con datos de garantes seleccionados
        params: dict con parametros de optimizacion

    Returns:
        str con el texto generado, o None si falla
    """
    if not ANTHROPIC_API_KEY:
        return None

    import anthropic

    m = diagnostico["metricas"]

    # Construir perfil de cada garante
    perfiles = []
    for r in sel_raw:
        perfiles.append(
            f"- {r['nombre_completo']}: {r['area']}, h-index={r['h_index']}, "
            f"E_i={r['E_i']:.3f}, genero={r['genero']}"
        )

    user_prompt = f"""Genera un argumentario para la siguiente propuesta de panel de garantes:

## Metricas del grupo
- h-index medio: {m['h_mean']} (rango {m['h_min']}-{m['h_max']})
- Cohesion media (K): {m['k_mean']} ({m['k_nonzero_pct']:.0f}% de pares con copublicaciones)
- Areas distintas: {m['areas']} ({', '.join(m['areas_list'])})
- Paridad: {m['mujeres_pct']:.0f}% mujeres ({m['mujeres']}/{params['N']})
- Valoracion del modelo: {diagnostico['valoracion']}

## Garantes seleccionados
{chr(10).join(perfiles)}

## Fortalezas detectadas
{chr(10).join('- ' + f for f in diagnostico['fortalezas'])}

## Debilidades detectadas
{chr(10).join('- ' + d for d in diagnostico['debilidades'])}

Redacta el argumentario justificando por qué este grupo es adecuado para una solicitud SO/MdM. Argumenta las fortalezas, mitiga las debilidades con razonamientos sólidos, y destaca la complementariedad del equipo."""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, base_url="https://api.anthropic.com")

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return message.content[0].text


def generar_argumentario_stream(diagnostico, sel_raw, params):
    """
    Igual que generar_argumentario pero con streaming.
    Yields chunks de texto para st.write_stream.
    """
    if not ANTHROPIC_API_KEY:
        yield "Error: ANTHROPIC_API_KEY no configurada en .env"
        return

    import anthropic

    m = diagnostico["metricas"]

    perfiles = []
    for r in sel_raw:
        perfiles.append(
            f"- {r['nombre_completo']}: {r['area']}, h-index={r['h_index']}, "
            f"E_i={r['E_i']:.3f}, genero={r['genero']}"
        )

    user_prompt = f"""Genera un argumentario para la siguiente propuesta de panel de garantes:

## Metricas del grupo
- h-index medio: {m['h_mean']} (rango {m['h_min']}-{m['h_max']})
- Cohesion media (K): {m['k_mean']} ({m['k_nonzero_pct']:.0f}% de pares con copublicaciones)
- Areas distintas: {m['areas']} ({', '.join(m['areas_list'])})
- Paridad: {m['mujeres_pct']:.0f}% mujeres ({m['mujeres']}/{params['N']})
- Valoracion del modelo: {diagnostico['valoracion']}

## Garantes seleccionados
{chr(10).join(perfiles)}

## Fortalezas detectadas
{chr(10).join('- ' + f for f in diagnostico['fortalezas'])}

## Debilidades detectadas
{chr(10).join('- ' + d for d in diagnostico['debilidades'])}

Redacta el argumentario justificando por qué este grupo es adecuado para una solicitud SO/MdM. Argumenta las fortalezas, mitiga las debilidades con razonamientos sólidos, y destaca la complementariedad del equipo."""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, base_url="https://api.anthropic.com")

    with client.messages.stream(
        model="claude-opus-4-5",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text
