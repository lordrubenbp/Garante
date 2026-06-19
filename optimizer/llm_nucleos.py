"""Validación de nucleos y propuesta de refuerzos con LLM (Claude)."""
import os
import json
import sys

sys.path.insert(0, os.path.dirname(__file__))
import config as cfg

SYSTEM_PROMPT_VALIDACION = """Eres un experto en estrategia investigadora para convocatorias de excelencia (Severo Ochoa / María de Maeztu) del Ministerio de Ciencia de España.

Tu tarea es analizar nucleos de investigadores detectados algoritmicamente y:
1. VALIDAR si tienen potencial estrategico a futuro (no para presentar ahora, sino como semilla de un grupo que podria ser competitivo si empiezan a colaborar)
2. PROPONER refuerzos concretos del pool para completar cada nucleo

El objetivo es identificar GRUPOS CON POTENCIAL FUTURO: investigadores que si empiezan a trabajar juntos, publicar en comun, y desarrollar lineas compartidas, podrian convertirse en un equipo competitivo para SO/MdM en 3-5 anos.

Criterios de validacion de un nucleo:
- Coherencia tematica (las areas se complementan, cuentan una historia investigadora)
- Masa critica (hay al menos 1-2 perfiles senior con h alto)
- Potencial de crecimiento (tendencia positiva, investigadores en ascenso)
- Complementariedad (no son redundantes, cada uno aporta algo distinto)
- Viabilidad de colaboracion (areas compatibles para copublicar)

Criterios para proponer refuerzos:
- Complementariedad tematica (cubrir huecos que el nucleo no tiene)
- Mejorar paridad de genero si el nucleo es desequilibrado
- Aportar internacionalizacion (EU, instituciones internacionales)
- Equilibrar perfiles senior/junior (sostenibilidad a largo plazo)
- Diversificar areas sin perder coherencia

IMPORTANTE: Usa SIEMPRE los nombres EXACTOS del pool. No inventes nombres.
Responde SIEMPRE en JSON valido con la estructura indicada. Sin texto adicional fuera del JSON."""


def validar_nucleos_y_proponer_refuerzos(raw, nucleos, modalidad="MdM", n_garantes=10):
    """
    Pipeline LLM unificado: valida nucleos + propone refuerzos.

    Args:
        raw: lista de candidatos (dicts con nombre_completo, area, h_index, E_i, genero, tendencia, etc)
        nucleos: nucleos detectados por Louvain con scoring multidimensional
        modalidad: "SO" o "MdM"
        n_garantes: tamaño objetivo del grupo final

    Returns:
        dict con:
            - nucleos: lista de {aprobado, justificacion, refuerzos: [{nombre, razon}]}
    """
    if not cfg.ANTHROPIC_API_KEY:
        return None

    import anthropic

    # Construir resumen del pool
    pool_summary = []
    for i, r in enumerate(raw):
        pool_summary.append(
            f"{i}. {r['nombre_completo']} | {r['area']} | h={r['h_index']} | "
            f"E_i={r['E_i']:.3f} | genero={r['genero']} | "
            f"tend={r.get('tendencia', 0):.2f} | EU={r.get('proyectos_eu', 0)} | "
            f"intl={r.get('instituciones_intl', 0)} | IP={r.get('proyectos_ip', 0)}"
        )

    # Resumen de nucleos con scoring
    nucleos_text = []
    for idx, n in enumerate(nucleos):
        scoring = n.get("scoring", {})
        nucleos_text.append(
            f"Nucleo {idx}: {', '.join(n['nombres'][:6])}\n"
            f"  Areas: {', '.join(n.get('areas', []))}\n"
            f"  Score total: {n['potencial']:.3f} | "
            f"Cohesion={scoring.get('cohesion', 0):.3f} | "
            f"Excelencia={scoring.get('excelencia', 0):.3f} | "
            f"Diversidad={scoring.get('diversidad_areas', 0):.3f} | "
            f"Equilibrio={scoring.get('equilibrio_senior_junior', 0):.3f} | "
            f"Tendencia={scoring.get('tendencia', 0):.3f} | "
            f"Intl={scoring.get('internacionalizacion', 0):.3f}"
        )

    if modalidad == "SO":
        modalidad_desc = "Severo Ochoa (maxima excelencia, liderazgo europeo, impacto global)"
    elif modalidad == "UEI":
        modalidad_desc = "Unidades de Excelencia en Investigacion de la Junta de Andalucia (trampolin hacia MdM/SO: grupos en ascenso con potencial, tendencia ascendente, internacionalizacion emergente)"
    else:
        modalidad_desc = "Maria de Maeztu (excelencia sostenida, formacion, transferencia, colaboracion)"

    nucleo_size = (cfg.NUCLEO_SIZE_SO if modalidad == "SO"
                   else cfg.NUCLEO_SIZE_UEI if modalidad == "UEI"
                   else cfg.NUCLEO_SIZE_MDM)
    n_refuerzos = max(1, n_garantes - nucleo_size)  # IA propone los restantes hasta completar el grupo

    # Calcular genero del nucleo para informar al LLM
    nucleos_genero_info = []
    for idx, n in enumerate(nucleos):
        mujeres = sum(1 for i in n["indices"] if raw[i]["genero"] == "Mujer")
        hombres = len(n["indices"]) - mujeres
        nucleos_genero_info.append(f"Nucleo {idx}: {mujeres}M/{hombres}H")

    user_prompt = f"""Convocatoria: {modalidad_desc}
Tamano objetivo del grupo: {n_garantes} garantes
PARIDAD (criterio de desempate, no obligatorio): Se recomienda 40-60% mujeres ({int(n_garantes * 0.4)} de {n_garantes}). La paridad no es obligatoria en la convocatoria pero favorece la candidatura como criterio de desempate entre propuestas similares.
Genero actual nucleos: {', '.join(nucleos_genero_info)}

## Pool de candidatos ({len(raw)} investigadores)
{chr(10).join(sorted(pool_summary, key=lambda x: float(x.split("E_i=")[1].split(" ")[0]), reverse=True)[:60])}
{"..." if len(pool_summary) > 60 else ""}

## Nucleos detectados algoritmicamente ({len(nucleos)} nucleos)
{chr(10).join(nucleos_text)}

## Tarea
Para cada nucleo:
1. VALIDA: ¿tiene sentido estrategico para {modalidad}? (aprobado: true/false)
2. JUSTIFICA: por que es bueno o malo (1-2 frases)
3. PROPONE REFUERZOS: sugiere {n_refuerzos} investigadores del pool (que NO estan ya en el nucleo) para completar el grupo de {n_garantes}. Para cada refuerzo explica QUE APORTA.

Responde en JSON con esta estructura exacta:
{{
  "nucleos": [
    {{
      "indice": 0,
      "aprobado": true,
      "justificacion": "Nucleo solido con coherencia en X y liderazgo europeo",
      "refuerzos": [
        {{"nombre": "Nombre Exacto Del Pool", "razon": "Aporta internacionalizacion en Y"}},
        ...
      ]
    }},
    ...
  ]
}}

REGLAS:
- Usa SOLO nombres exactos del pool
- Los refuerzos NO deben incluir miembros que ya estan en el nucleo
- PARIDAD RECOMENDADA (desempate): intenta que nucleo + refuerzos tenga entre 40-60% mujeres. No es obligatorio pero favorece la candidatura
- Prioriza refuerzos que cubran debilidades del nucleo (baja internacionalizacion → proponer alguien con EU; poca diversidad → proponer otra area; desequilibrio genero → proponer del genero minoritario)
- Si rechazas un nucleo, aun asi propone refuerzos que PODRIAN mejorarlo"""

    client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY, base_url=cfg.ANTHROPIC_BASE_URL, timeout=90.0)

    try:
        message = client.messages.create(
            model=cfg.LLM_MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT_VALIDACION,
            messages=[{"role": "user", "content": user_prompt}],
        )

        response_text = message.content[0].text.strip() if message.content else ""
        if not response_text:
            return {"error": "Empty LLM response", "nucleos": []}
        # Limpiar posible markdown code fence
        if response_text.startswith("```"):
            lines = response_text.split("\n", 1)
            response_text = lines[1] if len(lines) > 1 else ""
            # Strip trailing fence (handle ```json and ``` variants)
            response_text = response_text.rstrip()
            if response_text.endswith("```"):
                response_text = response_text[:-3].rstrip()

        return json.loads(response_text)

    except (json.JSONDecodeError, Exception) as e:
        return {"error": str(e), "nucleos": []}


