"""
Evaluador critico que simula el panel de evaluacion SO/MdM 2026.

Replica fielmente los criterios del Anexo II de la convocatoria 2026:
- Fase 1: Calidad cientifico-tecnica de cada garante (0-10, umbral 9)
- Fase 2: Memoria de actividades (0-50, umbral 40) + Plan estrategico (0-50, umbral 40)
  Total segunda fase: 0-100, umbral 95 para acreditacion.
"""
import os
import json
import sys

sys.path.insert(0, os.path.dirname(__file__))
import config as cfg

SYSTEM_PROMPT_SO = """Eres un evaluador internacional del programa de Centros de Excelencia Severo Ochoa de la Agencia Estatal de Investigacion (AEI) de España. Convocatoria 2026.

## CONTEXTO SEVERO OCHOA

La acreditacion Severo Ochoa se otorga a CENTROS DE INVESTIGACION completos que demuestran excelencia de primer nivel mundial. Ejemplos de centros acreditados: ICFO (fotonica), CNIO (oncologia), ICN2 (nanociencia), BIST, IRB Barcelona.

Caracteristicas diferenciales de SO frente a MdM:
- Se acredita un CENTRO completo con identidad propia, no una unidad dentro de otra estructura
- Se requiere director/a + 10 garantes que superen umbral 9 (mas masa critica)
- Se espera infraestructura propia y financiacion diversificada (no solo publica)
- Financiacion: ~1M€/ano durante 4 anos
- El nivel de exigencia es MAXIMO: el centro debe ser referencia internacional indiscutible en su area
- Se valora especialmente: ERC grants (Starting, Consolidator, Advanced), liderazgo de consorcios europeos, h-index en el cuartil superior mundial del area

{CRITERIOS_COMUNES}

## INSTRUCCIONES DE EVALUACION (SEVERO OCHOA)

Se MUY EXIGENTE. Los centros SO son la elite absoluta de la investigacion en España y compiten con los mejores del mundo (Max Planck, CNRS, ETH...).

Para la PRIMERA FASE: un garante SO debe ser indiscutiblemente top 10% mundial. En ciencias sociales/humanidades, h-index bajo puede compensarse con impacto social excepcional, premios nacionales/internacionales y liderazgo de grandes proyectos europeos, pero el liston es alto.

Para la SEGUNDA FASE: un centro SO debe demostrar liderazgo internacional claro, capacidad de atraer talento mundial, infraestructura competitiva, y una estrategia ambiciosa y viable. Evalua con baremo de centros como ICFO o CNIO.

Responde SIEMPRE en JSON valido con la estructura indicada."""

SYSTEM_PROMPT_MDM = """Eres un evaluador internacional del programa de Unidades de Excelencia Maria de Maeztu de la Agencia Estatal de Investigacion (AEI) de España. Convocatoria 2026.

## CONTEXTO MARIA DE MAEZTU

La acreditacion Maria de Maeztu se otorga a UNIDADES DE INVESTIGACION (departamentos, institutos universitarios, grupos estructurados) que demuestran excelencia destacada a nivel internacional. Ejemplos de unidades acreditadas: BCAM (matematicas), IFISC (fisica interdisciplinar), IRI (robotica), departamentos de universidades punteras.

Caracteristicas diferenciales de MdM frente a SO:
- Se acredita una UNIDAD dentro de una universidad u organismo, no un centro independiente
- Se requiere director/a + 6 garantes que superen umbral 9 (menor masa critica que SO)
- La unidad puede compartir infraestructura con su institucion matriz
- Financiacion: ~500K€/ano durante 4 anos
- El nivel de exigencia es ALTO pero algo menor que SO: se valora la excelencia en contexto universitario
- Se valora especialmente: coherencia tematica de la unidad, potencial de crecimiento, impacto en su entorno institucional, capacidad formativa (doctorados, postdocs)

{CRITERIOS_COMUNES}

## INSTRUCCIONES DE EVALUACION (MARIA DE MAEZTU)

Se EXIGENTE pero contextualizado. Las unidades MdM son excelentes pero operan dentro de estructuras universitarias con sus limitaciones.

Para la PRIMERA FASE: un garante MdM debe ser top 10% mundial en su area, pero se acepta mayor diversidad de perfiles (incluyendo perfiles con fuerte componente de transferencia, formacion o impacto social). En ciencias sociales, h-index de 8-15 con impacto social demostrado puede ser competitivo.

Para la SEGUNDA FASE: una unidad MdM debe demostrar excelencia clara, buena organizacion, y un plan estrategico realista que aproveche el marco institucional. No se espera la infraestructura de un centro SO, pero si liderazgo en su area y proyeccion internacional creciente.

Responde SIEMPRE en JSON valido con la estructura indicada."""

SYSTEM_PROMPT_UEI = """Eres un evaluador del programa de Unidades de Excelencia en Investigacion de la Junta de Andalucia. Convocatoria 2025 (Orden BOJA 10 nov 2025).

## CONTEXTO UNIDADES DE EXCELENCIA (JUNTA ANDALUCIA)

La acreditacion UEI se otorga a UNIDADES DE INVESTIGACION del Sistema Andaluz del Conocimiento que destacan por su impacto y relevancia internacional. Es un programa AUTONOMICO, disenado como trampolin para que los grupos andaluces refuercen sus estructuras y compitan con garantias para las acreditaciones estatales Maria de Maeztu o Severo Ochoa.

Dos categorias segun puntuacion:
- Unidad de Excelencia en Investigacion (>=90 puntos): hasta 1.500.000 EUR
- Unidad de Investigacion Competitiva (80-89 puntos): hasta 1.200.000 EUR

Caracteristicas diferenciales de UEI frente a MdM/SO:
- Se acredita una UNIDAD del sistema andaluz, no necesariamente universitaria
- Se requiere persona directora cientifica + 5 garantes que superen umbral 9/10 individual
- Periodo de referencia: 1 enero 2022 - 30 junio 2025 (3.5 anos)
- Vigencia: 4 anos, con subvencion para programa estrategico (max 3 anos)
- Incompatible con acreditaciones SO/MdM vigentes
- Objetivo: preparar al grupo para competir en convocatorias estatales (MdM o SO)
- Se valora especialmente: trayectoria ascendente, potencial de crecimiento, construccion de equipo

{CRITERIOS_COMUNES}

## INSTRUCCIONES DE EVALUACION (UEI — JUNTA DE ANDALUCIA)

Se EXIGENTE pero con perspectiva de POTENCIAL. Las UEI buscan grupos en ascenso, no necesariamente consolidados al nivel MdM.

Para la PRIMERA FASE: un garante UEI debe demostrar calidad investigadora destacada (top 20% en su area), con potencial claro de crecimiento. En ciencias sociales/humanidades, se acepta mayor peso de transferencia, impacto social y liderazgo regional/nacional. h-index de 6-12 con proyeccion ascendente puede ser competitivo.

Para la SEGUNDA FASE: una unidad UEI debe demostrar trayectoria de investigacion compartida, coherencia tematica, y un plan estrategico realista orientado a crecer hacia MdM. Se valora especialmente la tendencia ascendente de productividad e impacto, la capacidad formativa, y la emergente internacionalizacion.

Responde SIEMPRE en JSON valido con la estructura indicada."""

CRITERIOS_COMUNES = """
## PRIMERA FASE — Evaluacion individual de investigadores/as

Criterio 1: Calidad cientifico-tecnica del/de la investigador/a (0-10, umbral 9).

Se valora:
- Calidad cientifico-tecnica, impacto y capacidad de liderazgo
- Reconocimiento nacional e internacional: premios, reconocimientos de instituciones de ambito nacional/internacional
- Excelencia e impacto de aportaciones cientificas: publicaciones, conferencias internacionales de prestigio, patentes en explotacion, software, contratos de alto impacto
- Liderazgo en proyectos europeos del Programa Marco (H2020, Horizonte Europa), ayudas ERC en todas sus modalidades, coordinacion de proyectos europeos, grandes colaboraciones internacionales
- Participacion en comites de evaluacion ERC, pertenencia a comites editoriales de revistas cientificas internacionales de prestigio
- Pertenencia a organizaciones cientificas internacionales de acceso por meritos
- EN GENERAL: se espera que el/la investigador/a garante se encuentre dentro del 10% de investigadores/as mas destacados en su area de especializacion a nivel global

## SEGUNDA FASE — Evaluacion de la propuesta como conjunto

1. Memoria de actividades cientificas (0-50, umbral 40):
   1.1 Modelo de organizacion, equipo humano, medios materiales y capacidades (0-20):
       - Organizacion cientifica y coherencia de lineas de investigacion
       - Sinergias y complementariedad hacia un objetivo cientifico-tecnologico conjunto
       - Experiencia y liderazgo del equipo humano
       - Masa critica del centro/unidad
       - Mecanismos de atraccion y retencion de talento
       - Igualdad de genero
       - Financiacion del centro/unidad
   1.2 Resultados de investigacion (0-20):
       - Contribuciones al estado del arte y liderazgo internacional
       - Publicaciones, proyectos, contratos (regional, nacional, europeo, internacional)
       - Patentes y propiedad industrial/intelectual
       - Transferencia de conocimiento, desarrollo tecnologico, innovacion
       - Difusion y divulgacion
   1.3 Liderazgo internacional (0-10):
       - Posicionamiento respecto a centros de excelencia internacionales
       - Premios y reconocimientos internacionales, ayudas ERC/EIC
       - Organizacion de congresos internacionales relevantes
       - Liderazgo de proyectos internacionales

2. Plan estrategico (0-50, umbral 40):
   2.1 Objetivos estrategicos, actividades de investigacion, viabilidad (0-30, umbral 25):
       - Claridad, novedad y justificacion de objetivos
       - Fortalecimiento de capacidades y coordinacion de lineas
       - Liderazgo cientifico-tecnologico internacional
       - Impacto cientifico-tecnico, social y economico
       - Organizacion interna y gestion
       - Etica e integridad cientifica
       - Viabilidad, hitos e indicadores de seguimiento
   2.2 Actividades transversales (0-20):
       - Formacion e incorporacion de recursos humanos
       - Internacionalizacion
       - Explotacion y difusion de resultados
       - Efecto tractor sobre el entorno

UMBRAL TOTAL segunda fase: 95/100 para obtener acreditacion.
Por debajo de 85: no pueden presentarse en la siguiente convocatoria."""

# Build final prompts with criteria injected
SYSTEM_PROMPT_SO = SYSTEM_PROMPT_SO.replace("{CRITERIOS_COMUNES}", CRITERIOS_COMUNES)
SYSTEM_PROMPT_MDM = SYSTEM_PROMPT_MDM.replace("{CRITERIOS_COMUNES}", CRITERIOS_COMUNES)
SYSTEM_PROMPT_UEI = SYSTEM_PROMPT_UEI.replace("{CRITERIOS_COMUNES}", CRITERIOS_COMUNES)


def _call_evaluator(system_prompt, user_prompt, max_tokens=8000):
    """Call Claude API and parse JSON response. Returns dict or {"error": ...}."""
    if not cfg.ANTHROPIC_API_KEY:
        return None

    import anthropic
    client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY, base_url=cfg.ANTHROPIC_BASE_URL, timeout=90.0)

    try:
        message = client.messages.create(
            model=cfg.LLM_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = message.content[0].text.strip() if message.content else ""
        if not text:
            return {"error": "Empty LLM response"}
        if text.startswith("```"):
            lines = text.split("\n", 1)
            text = lines[1] if len(lines) > 1 else ""
            text = text.rstrip()
            if text.endswith("```"):
                text = text[:-3].rstrip()
        return json.loads(text)
    except Exception as e:
        return {"error": str(e)}


def evaluar_propuesta_fase1(diagnostico, sel_raw, params, modalidad="MdM", db_name=None):
    """
    Fase 1: Evalua individualmente a cada garante (0-10).
    modalidad: "SO" para Severo Ochoa, "MdM" para Maria de Maeztu.
    Returns dict con evaluaciones individuales.
    """
    if not cfg.ANTHROPIC_API_KEY:
        return None

    if modalidad == "SO":
        system_prompt, modalidad_full, garantes_necesarios = SYSTEM_PROMPT_SO, "Severo Ochoa", 10
    elif modalidad == "UEI":
        system_prompt, modalidad_full, garantes_necesarios = SYSTEM_PROMPT_UEI, "Unidades de Excelencia (Junta Andalucia)", 5
    else:
        system_prompt, modalidad_full, garantes_necesarios = SYSTEM_PROMPT_MDM, "Maria de Maeztu", 6
    inst = cfg.get_instituto_info(db_name or cfg.DB_NAME)

    perfiles = []
    for r in sel_raw:
        perfiles.append(
            f"- {r['nombre_completo']}: area={r['area']}, h-index={r['h_index']}, "
            f"E_i={r['E_i']:.3f}, genero={r['genero']}, "
            f"proyectos_IP={r.get('proyectos_ip', 0)}, tesis_dirigidas={r.get('tesis_dir', 0)}, "
            f"tendencia={'ascendente' if r.get('tendencia', 0) >= 0.7 else 'estable' if r.get('tendencia', 0) >= 0 else 'descendente'}, "
            f"h_openalex={r.get('h_openalex', '?')}, h_dialnet={r.get('h_dialnet', '?')}, "
            f"stanford_top2pct={'SI (top ' + str(r['stanford_percentil']) + '% en ' + str(r['stanford_subfield']) + ')' if r.get('stanford_percentil') is not None else 'no en top 2%'}"
        )

    m = diagnostico.get("metricas")
    if not m:
        return {"error": "diagnostico missing metricas key"}

    user_prompt = f"""Evalua la PRIMERA FASE de esta solicitud {modalidad_full} del {inst['nombre_largo']}, {inst['universidad']}. Perfil: {inst['perfil']}.

## Investigadores/as propuestos/as ({len(sel_raw)} garantes)
{chr(10).join(perfiles)}

## Contexto del grupo
- h-index medio: {m['h_mean']} (rango {m['h_min']}-{m['h_max']})
- Areas: {', '.join(m['areas_list'])}
- Paridad: {m['mujeres_pct']:.0f}% mujeres

Para {modalidad_full} se necesitan al menos {garantes_necesarios} garantes + director/a que superen el umbral 9/10.

Responde en JSON con esta estructura exacta:
{{
  "modalidad": "{modalidad_full}",
  "garantes_necesarios": {garantes_necesarios},
  "evaluaciones_individuales": [
    {{
      "nombre": "Nombre completo",
      "puntuacion": 7,
      "supera_umbral": false,
      "justificacion": "Explicacion concisa de por que esta puntuacion",
      "factores_positivos": ["factor1", "factor2"],
      "factores_negativos": ["factor1"]
    }}
  ],
  "garantes_que_superan_umbral": 3,
  "superada_fase1": false,
  "veredicto_fase1": "Explicacion de si se supera la fase 1 y por que"
}}"""

    return _call_evaluator(system_prompt, user_prompt)


def evaluar_propuesta_fase2(diagnostico, sel_raw, params, modalidad="MdM", db_name=None):
    """
    Fase 2: Evalua la propuesta como conjunto (0-100).
    modalidad: "SO" para Severo Ochoa, "MdM" para Maria de Maeztu.
    Returns dict con puntuaciones por subcriterio.
    """
    if not cfg.ANTHROPIC_API_KEY:
        return None

    if modalidad == "SO":
        system_prompt, modalidad_full = SYSTEM_PROMPT_SO, "Severo Ochoa"
    elif modalidad == "UEI":
        system_prompt, modalidad_full = SYSTEM_PROMPT_UEI, "Unidades de Excelencia (Junta Andalucia)"
    else:
        system_prompt, modalidad_full = SYSTEM_PROMPT_MDM, "Maria de Maeztu"
    inst = cfg.get_instituto_info(db_name or cfg.DB_NAME)

    m = diagnostico.get("metricas")
    if not m:
        return {"error": "diagnostico missing metricas key"}

    perfiles_resumen = []
    for r in sel_raw:
        perfiles_resumen.append(f"{r['nombre_completo']} ({r['area']}, h={r['h_index']})")

    user_prompt = f"""Evalua la SEGUNDA FASE de esta solicitud {modalidad_full} del {inst['nombre_largo']} ({inst['universidad']}).

## Garantes seleccionados
{', '.join(perfiles_resumen)}

## Metricas del grupo
- h-index medio: {m['h_mean']} (rango {m['h_min']}-{m['h_max']})
- Cohesion (copublicaciones): K medio = {m['k_mean']}, {m['k_nonzero_pct']:.0f}% pares con copubs (informativo — no es criterio determinante en la convocatoria)
- Areas: {m['areas']} distintas ({', '.join(m['areas_list'])})
- Paridad: {m['mujeres_pct']:.0f}% mujeres ({m['mujeres']}/{params.get('N', len(sel_raw))}) — no obligatoria, criterio de desempate
- Internacionalizacion media: {m.get('intl_mean', 'N/A')} instituciones extranjeras
- Tendencia media: {m.get('tendencia_mean', 'N/A')}

## Diagnostico automatico
Fortalezas: {', '.join(diagnostico.get('fortalezas', [])) or 'Ninguna'}
Debilidades: {', '.join(diagnostico.get('debilidades', [])) or 'Ninguna'}

NOTA: Solo tienes datos bibliometricos y de copublicaciones. No tienes la memoria completa ni el plan estrategico. Evalua lo que puedas inferir y señala que informacion te falta.

Responde en JSON con esta estructura exacta:
{{
  "memoria_actividades": {{
    "c11_organizacion_equipo": {{
      "puntuacion": 12,
      "max": 20,
      "justificacion": "..."
    }},
    "c12_resultados_investigacion": {{
      "puntuacion": 10,
      "max": 20,
      "justificacion": "..."
    }},
    "c13_liderazgo_internacional": {{
      "puntuacion": 4,
      "max": 10,
      "justificacion": "..."
    }},
    "subtotal_memoria": 26,
    "umbral_memoria": 40,
    "supera_umbral_memoria": false
  }},
  "plan_estrategico": {{
    "c21_objetivos_viabilidad": {{
      "puntuacion": 18,
      "max": 30,
      "umbral": 25,
      "justificacion": "..."
    }},
    "c22_transversales": {{
      "puntuacion": 12,
      "max": 20,
      "justificacion": "..."
    }},
    "subtotal_plan": 30,
    "umbral_plan": 40,
    "supera_umbral_plan": false
  }},
  "puntuacion_total": 56,
  "umbral_acreditacion": 95,
  "umbral_exclusion": 85,
  "acreditable": false,
  "excluido_proxima": true,
  "veredicto_fase2": "Explicacion global del resultado",
  "recomendaciones_criticas": [
    "Recomendacion 1 concreta",
    "Recomendacion 2 concreta"
  ],
  "informacion_faltante": [
    "Que datos necesitarias para una evaluacion mas precisa"
  ]
}}"""

    return _call_evaluator(system_prompt, user_prompt)


# ─────────────────────────────────────────────────────────────────────────────
# FASE EXPERTA DORA: revisión profunda de perfiles completos
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_FASE1_MDM = """Eres un comite de evaluacion internacional de la Agencia Estatal de Investigacion (AEI) de España evaluando candidatos a investigadores/as garantes para la convocatoria de Unidades de Excelencia «Maria de Maeztu» 2026.

## CONVOCATORIA Y CONTEXTO

Modalidad: Unidades de Excelencia Maria de Maeztu (unidades de investigacion en universidades u organismos publicos).
Convocatoria: AEI 2026. Firmada 07/04/2026.
Financiacion: hasta 2.250.000 EUR por unidad. Acreditacion vigente 6 anos.
Para superar Fase 1: director/a + 6 garantes deben alcanzar umbral 9/10 individualmente.

**PERIODO DE REFERENCIA: 1 de enero de 2021 – 31 de diciembre de 2025.**
Evalua PRIORITARIAMENTE los meritos y actividad dentro de este periodo. Meritos anteriores pueden considerarse como contexto de trayectoria, pero el peso principal recae en lo producido entre 2021 y 2025.

## CRITERIOS OFICIALES (ANEXO II, FASE 1)

Criterio unico: Calidad cientifico-tecnica del/de la investigador/a (0-10, umbral 9).

Se valora (por orden de importancia):
1. Calidad cientifico-tecnica, impacto y capacidad de liderazgo en el periodo de referencia. **El rol del/de la investigador/a en cada contribucion es determinante**: primer/a autor/a, autor/a de correspondencia, IP de proyecto, coordinador/a de consorcio. Se distingue a quien lidera de quien participa.
2. Excelencia e impacto de aportaciones: publicaciones citadas (con rol de autoria), conferencias internacionales de prestigio, patentes en explotacion, software, contratos de alto impacto.
3. Liderazgo en proyectos europeos del Programa Marco (H2020, Horizonte Europa), ayudas ERC (Starting, Consolidator, Advanced, Synergy, Proof of Concept), coordinacion de proyectos europeos, grandes colaboraciones internacionales. Se valora especialmente ser IP o coordinador/a, no solo participante.
4. Reconocimiento nacional e internacional: premios, distinciones de instituciones de ambito nacional/internacional.
5. Participacion en comites de evaluacion ERC, comites editoriales de revistas internacionales de prestigio, organizaciones cientificas internacionales de acceso por meritos.

**Expectativa oficial AEI**: el/la garante debe encontrarse dentro del **top 10% de investigadores/as mas destacados/as en su area a nivel global**.

## PRINCIPIO DORA (OBLIGATORIO)

No se tienen en cuenta factores de impacto de revistas (JCR, SJR), cuartiles, listas de mas citados ni indicadores bibliometricos de journal. Evalua el IMPACTO REAL del trabajo: citas de articulos concretos, proyectos liderados, tesis dirigidas, transferencia de conocimiento.

## NIVEL DE EXIGENCIA (MdM)

Se EXIGENTE pero contextualizado en el entorno universitario. Las unidades MdM son excelentes pero operan con las limitaciones estructurales de la universidad española.
- Un garante MdM debe ser top 10% mundial en su area, con posibilidad de mayor diversidad de perfiles (transferencia, formacion, impacto social).
- En ciencias sociales y humanidades: h-index de 8-15 con impacto social demostrado y liderazgo de proyectos competitivos puede ser competitivo.
- Penaliza la inactividad en el periodo de referencia (sin publicaciones, sin proyectos entre 2021-2025).

## ESCALA DE PUNTUACION

- 9-10: Garante excepcional. Trayectoria de excelencia internacional indiscutible en el periodo. Top 10% mundial. ERC o equivalente, publicaciones de alto impacto, liderazgo claro.
- 7-8: Garante solido. Perfil competitivo con hitos relevantes en el periodo. Buena proyeccion internacional.
- 5-6: Garante aceptable. Fortalezas claras pero lagunas significativas (poca actividad europea, bajo liderazgo, produccion irregular).
- 3-4: Garante debil. Pocos hitos de impacto internacional real en el periodo.
- 0-2: No apto. Sin evidencia de excelencia o inactivo en el periodo de referencia.

Se riguroso pero justo. No penalices a investigadores jovenes por tener menos anos de carrera — evalua la densidad y calidad de sus hitos relativos a su etapa y al periodo 2021-2025."""

SYSTEM_PROMPT_FASE1_SO = """Eres un comite de evaluacion internacional de la Agencia Estatal de Investigacion (AEI) de España evaluando candidatos a investigadores/as garantes para la convocatoria de Centros de Excelencia «Severo Ochoa» 2026.

## CONVOCATORIA Y CONTEXTO

Modalidad: Centros de Excelencia Severo Ochoa (centros de investigacion independientes).
Convocatoria: AEI 2026. Firmada 07/04/2026.
Financiacion: hasta 4.500.000 EUR por centro. Acreditacion vigente 6 anos.
Para superar Fase 1: director/a + 10 garantes deben alcanzar umbral 9/10 individualmente.
Referencia de excelencia: centros como ICFO, CNIO, ICN2, IRB Barcelona, BIST.

**PERIODO DE REFERENCIA: 1 de enero de 2021 – 31 de diciembre de 2025.**
Evalua PRIORITARIAMENTE los meritos y actividad dentro de este periodo. Meritos anteriores pueden considerarse como contexto de trayectoria, pero el peso principal recae en lo producido entre 2021 y 2025.

## CRITERIOS OFICIALES (ANEXO II, FASE 1)

Criterio unico: Calidad cientifico-tecnica del/de la investigador/a (0-10, umbral 9).

Se valora (por orden de importancia):
1. Calidad cientifico-tecnica, impacto y capacidad de liderazgo en el periodo de referencia. **El rol del/de la investigador/a en cada contribucion es determinante**: primer/a autor/a, autor/a de correspondencia, IP de proyecto, coordinador/a de consorcio. Se distingue a quien lidera de quien participa.
2. Excelencia e impacto de aportaciones: publicaciones citadas (con rol de autoria), conferencias internacionales de prestigio, patentes en explotacion, software, contratos de alto impacto.
3. Liderazgo en proyectos europeos del Programa Marco (H2020, Horizonte Europa), ayudas ERC (Starting, Consolidator, Advanced, Synergy, Proof of Concept), coordinacion de proyectos europeos, grandes colaboraciones internacionales. Se valora especialmente ser IP o coordinador/a, no solo participante.
4. Reconocimiento nacional e internacional: premios, distinciones de instituciones de ambito nacional/internacional.
5. Participacion en comites de evaluacion ERC, comites editoriales de revistas internacionales de prestigio, organizaciones cientificas internacionales de acceso por meritos.

**Expectativa oficial AEI**: el/la garante debe encontrarse dentro del **top 10% de investigadores/as mas destacados/as en su area a nivel global**.

## PRINCIPIO DORA (OBLIGATORIO)

No se tienen en cuenta factores de impacto de revistas (JCR, SJR), cuartiles, listas de mas citados ni indicadores bibliometricos de journal. Evalua el IMPACTO REAL del trabajo: citas de articulos concretos, proyectos liderados, tesis dirigidas, transferencia de conocimiento.

## NIVEL DE EXIGENCIA (SO — MAXIMO)

Se MUY EXIGENTE. Los centros SO son la elite absoluta de la investigacion en España y compiten con los mejores centros del mundo (Max Planck, CNRS, ETH, Cambridge...).
- Un garante SO debe ser INDISCUTIBLEMENTE top 10% mundial. El liston es muy alto.
- Se espera presencia de ERC grants, liderazgo de consorcios europeos, h-index en el cuartil superior mundial del area.
- En ciencias sociales y humanidades: h-index bajo solo puede compensarse con impacto social excepcional, premios nacionales/internacionales de primer nivel y liderazgo de grandes proyectos europeos.
- Penaliza duramente la inactividad o baja produccion en el periodo de referencia (2021-2025).

## ESCALA DE PUNTUACION

- 9-10: Garante excepcional. Trayectoria de excelencia internacional indiscutible en el periodo. Top 10% mundial indiscutible. ERC o equivalente, publicaciones con gran impacto real, liderazgo internacional consolidado.
- 7-8: Garante solido. Perfil competitivo pero que no alcanza el nivel SO. Puede ser garante MdM.
- 5-6: Garante aceptable para convocatorias menores. No apto SO.
- 3-4: Garante debil. Pocos hitos de impacto internacional real.
- 0-2: No apto. Sin evidencia de excelencia o inactivo en el periodo de referencia.

Se riguroso pero justo. No penalices a investigadores jovenes por tener menos anos de carrera — evalua la densidad y calidad de sus hitos relativos a su etapa y al periodo 2021-2025."""

SYSTEM_PROMPT_FASE1_UEI = """Eres un comite de evaluacion del programa de Unidades de Excelencia en Investigacion (UEI) de la Junta de Andalucia evaluando candidatos a investigadores/as garantes. Convocatoria 2025 (Orden BOJA 10 nov 2025).

## CONVOCATORIA Y CONTEXTO

Modalidad: Unidades de Excelencia en Investigacion — Junta de Andalucia (programa autonomico andaluz).
Financiacion: hasta 1.500.000 EUR (Unidad de Excelencia, >=90 pts) o hasta 1.200.000 EUR (Unidad Competitiva, 80-89 pts).
Para superar Fase 1: directora/director + 5 garantes deben alcanzar umbral 9/10 individualmente.
Objetivo del programa: preparar grupos andaluces para competir en convocatorias estatales (MdM o SO).

**PERIODO DE REFERENCIA: 1 de enero de 2022 – 30 de junio de 2025 (3,5 anos).**
Evalua PRIORITARIAMENTE los meritos y actividad dentro de este periodo. Meritos anteriores pueden considerarse como contexto de trayectoria, pero el peso principal recae en lo producido entre 2022 y junio de 2025.

## CRITERIOS OFICIALES (FASE 1)

Criterio unico: Calidad cientifico-tecnica del/de la investigador/a (0-10, umbral 9).

Se valora (por orden de importancia):
1. Calidad cientifico-tecnica, impacto y capacidad de liderazgo en el periodo de referencia. **El rol del/de la investigador/a en cada contribucion es determinante**: primer/a autor/a, autor/a de correspondencia, IP de proyecto, coordinador/a de consorcio. Se distingue a quien lidera de quien participa.
2. Excelencia e impacto de aportaciones: publicaciones citadas (con rol de autoria), conferencias internacionales, patentes, software, contratos.
3. Liderazgo en proyectos europeos (H2020, Horizonte Europa, ERC), coordinacion de proyectos, colaboraciones internacionales. Se valora especialmente ser IP o coordinador/a, no solo participante.
4. Reconocimiento nacional e internacional: premios, distinciones.
5. Participacion en comites editoriales, comites ERC, organizaciones cientificas internacionales.

**Expectativa**: calidad investigadora destacada con potencial claro de crecimiento hacia el top 20% en su area.

## PRINCIPIO DORA (OBLIGATORIO)

No se tienen en cuenta factores de impacto de revistas (JCR, SJR), cuartiles ni indicadores bibliometricos de journal. Evalua el IMPACTO REAL del trabajo: citas de articulos concretos, proyectos liderados, tesis dirigidas.

## NIVEL DE EXIGENCIA (UEI — POTENCIAL + TRAYECTORIA ASCENDENTE)

Se EXIGENTE pero con perspectiva de POTENCIAL. Las UEI buscan grupos en ascenso, no necesariamente consolidados al nivel MdM.
- Un garante UEI debe demostrar calidad investigadora destacada (top 20%) con potencial claro de crecimiento.
- Se valora especialmente la TENDENCIA ASCENDENTE: produccion creciente, incorporacion a redes internacionales, primeros proyectos europeos.
- En ciencias sociales y humanidades: mayor peso de transferencia, impacto social y liderazgo regional/nacional. h-index de 6-12 con proyeccion ascendente puede ser competitivo.
- Penaliza la inactividad en el periodo de referencia (2022-2025), especialmente en grupos jovenes.

## ESCALA DE PUNTUACION

- 9-10: Garante excepcional. Excelencia clara en el periodo y potencial de crecimiento destacado. Perfil que podria competir en MdM.
- 7-8: Garante solido. Perfil competitivo para UEI con buena proyeccion. Trayectoria ascendente visible.
- 5-6: Garante aceptable. Fortalezas pero lagunas en internacionalizacion o liderazgo.
- 3-4: Garante debil. Produccion escasa o sin proyeccion internacional en el periodo.
- 0-2: No apto. Sin evidencia de actividad o impacto en el periodo de referencia.

Se riguroso pero justo. Valora el potencial y la trayectoria ascendente, no solo el nivel absoluto."""

# Lookup por codigo de modalidad
_SYSTEM_PROMPTS_FASE1 = {
    "SO": SYSTEM_PROMPT_FASE1_SO,
    "MdM": SYSTEM_PROMPT_FASE1_MDM,
    "UEI": SYSTEM_PROMPT_FASE1_UEI,
}


def _build_perfil_completo(doc, raw_entry):
    """Construye un perfil textual completo del investigador para el LLM."""
    lines = []
    nombre = doc.get("nombre_completo", "?")
    lines.append(f"### {nombre}")
    lines.append(f"- Figura: {doc.get('figura', '?')}")
    lines.append(f"- Area: {(doc.get('area') or {}).get('nombre', '?')}")
    lines.append(f"- Grupo: {(doc.get('grupo_investigacion') or {}).get('nombre', '?')}")
    lines.append(f"- h-index (OpenAlex): {raw_entry.get('h_index', '?')}")
    lines.append(f"- E_i (score optimizador): {raw_entry.get('E_i', '?')}")
    lines.append(f"- Tendencia: {raw_entry.get('tendencia', '?')} ({raw_entry.get('tendencia_metodo', '?')})")
    lines.append(f"- Sexenios: {doc.get('sexenios', 0)} (ultimo: {doc.get('fecha_ultimo_sexenio', '?')})")

    # Top mundial
    pct = raw_entry.get("openalex_pct")
    subf = raw_entry.get("openalex_pct_subfield")
    if pct is not None:
        lines.append(f"- Top mundial: {pct:.1f}% en {subf or '?'}")

    # Publicaciones más citadas (top 10 por citas Crossref)
    pubs = (doc.get("publicaciones") or {}).get("items", [])
    pubs_con_citas = []
    for p in pubs:
        cr = (p.get("crossref") or {})
        citas = cr.get("citas_crossref", 0) or 0
        pubs_con_citas.append((citas, p))
    pubs_con_citas.sort(key=lambda x: -x[0])
    top_pubs = pubs_con_citas[:10]

    if top_pubs:
        lines.append("\n**Publicaciones mas citadas:**")
        for citas, p in top_pubs:
            titulo = (p.get("titulo") or "?")[:120]
            año = p.get("anualidad", "?")
            jrnl = (p.get("journal") or {}).get("nombre_scimago") or (p.get("localizacion") or "")[:50]
            lines.append(f"  - [{año}] {titulo} ({jrnl}) -- {citas} citas")
    else:
        lines.append("\n**Publicaciones:** Sin datos de citas disponibles")

    # Proyectos como IP
    fin_items = (doc.get("financiaciones") or {}).get("items", [])
    ips = [f for f in fin_items if f.get("responsable") is True]
    eu_projs = [f for f in fin_items
                if "unión europea" in (f.get("financiador") or "").lower()
                or "european research council" in (f.get("financiador") or "").lower()]
    if ips:
        lines.append(f"\n**Proyectos como IP ({len(ips)}):**")
        for p in sorted(ips, key=lambda x: -(x.get("anualidad") or 0))[:8]:
            nombre_p = (p.get("nombre") or "?")[:80]
            fin = p.get("financiador", "?")
            año_p = p.get("anualidad", "?")
            lines.append(f"  - [{año_p}] {nombre_p} ({fin})")
    if eu_projs:
        lines.append(f"\n**Proyectos europeos ({len(eu_projs)}):**")
        for p in sorted(eu_projs, key=lambda x: -(x.get("anualidad") or 0))[:6]:
            nombre_p = (p.get("nombre") or "?")[:80]
            resp = "IP" if p.get("responsable") else "miembro"
            año_p = p.get("anualidad", "?")
            lines.append(f"  - [{año_p}] {nombre_p} ({resp})")

    # Tesis dirigidas
    tesis = (doc.get("tesis") or {}).get("dirigidas", [])
    if tesis:
        lines.append(f"\n**Tesis doctorales dirigidas: {len(tesis)}**")

    # Colaboraciones internacionales
    insts = (doc.get("colaboraciones") or {}).get("instituciones", [])
    intl = [i for i in insts if isinstance(i, dict)
            and (i.get("pais") or "").lower() not in ("españa", "spain", "")]
    if intl:
        lines.append(f"\n**Colaboraciones internacionales ({len(intl)}):**")
        for inst in intl[:6]:
            lines.append(f"  - {inst.get('nombre', '?')} ({inst.get('pais', '?')})")

    # Reconocimiento
    patentes = (doc.get("patentes") or {}).get("total", 0)
    orcid = doc.get("orcid_record") or {}
    distinciones = orcid.get("distinciones", 0)
    membresias = orcid.get("membresias", 0)
    reconocimiento = []
    if patentes:
        reconocimiento.append(f"{patentes} patentes")
    if distinciones:
        reconocimiento.append(f"{distinciones} distinciones")
    if membresias:
        reconocimiento.append(f"{membresias} membresías en comités")
    if reconocimiento:
        lines.append(f"\n**Reconocimiento:** {', '.join(reconocimiento)}")

    return "\n".join(lines)


def _evaluar_candidato_fase1(perfil_text, modalidad_full, inst, modalidad_code="MdM"):
    """Evalúa un solo candidato (Fase 1). Llamada rápida (~4K tokens output)."""
    system_prompt = _SYSTEM_PROMPTS_FASE1.get(modalidad_code, SYSTEM_PROMPT_FASE1_MDM)
    periodo = "2022-2025" if modalidad_code == "UEI" else "2021-2025"
    user_prompt = f"""Evalua como comite experto este candidato a garante de la solicitud {modalidad_full} del {inst['nombre_largo']} ({inst['universidad']}).

Recuerda: el periodo de referencia de esta convocatoria es {periodo}. Pon el foco en los meritos y la actividad dentro de ese periodo.

{perfil_text}

---

Responde en JSON con esta estructura exacta:
{{
  "nombre": "Nombre completo",
  "hitos": [
    "Hito 1: descripcion concisa del logro — incluye ROL (primer autor / IP / coordinador / miembro), ano y impacto real (citas, financiacion, etc.)",
    "Hito 2: ...",
    "...(hasta 10 hitos, priorizando los del periodo de referencia)"
  ],
  "narrativa": "Parrafo evaluando si los hitos cuentan una historia coherente de excelencia internacional, con especial atencion al periodo {periodo}.",
  "fortalezas": ["fortaleza 1", "fortaleza 2"],
  "debilidades": ["debilidad 1"],
  "puntuacion": 8.0,
  "supera_umbral": true,
  "veredicto": "Garante solido"
}}

Veredictos posibles: Garante excepcional (9-10) / Garante solido (7-8) / Garante aceptable (5-6) / Garante debil (3-4) / No apto (0-2).
La puntuacion es sobre 10. Umbral para garante: 9.
Evalua el IMPACTO REAL del trabajo (citas de articulos, proyectos liderados), NO el prestigio de la revista. Los hitos deben ser especificos y datados."""

    return _call_evaluator(system_prompt, user_prompt, max_tokens=4000)


def evaluar_fase1_experta(sel_raw, docs_sel, casi_raw, casi_docs,
                          modalidad="MdM", db_name=None,
                          progress_callback=None):
    """
    Fase 1 experta: evalúa seleccionados + casi-garantes EN PARALELO,
    los ordena por puntuación y detecta si algún excluido supera a un seleccionado.

    Args:
        sel_raw: lista de raw entries de los seleccionados
        docs_sel: lista de docs MongoDB originales de los seleccionados
        casi_raw: lista de raw entries de los casi-garantes (mejores excluidos)
        casi_docs: lista de docs MongoDB de los casi-garantes
        modalidad: "SO", "MdM" o "UEI"
        db_name: nombre de la BD del instituto
        progress_callback: función(i, total, nombre) para reportar progreso

    Returns: dict con evaluaciones, ranking y swaps recomendados
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not cfg.ANTHROPIC_API_KEY:
        return None

    inst = cfg.get_instituto_info(db_name or cfg.DB_NAME)
    modalidad_full = {"SO": "Severo Ochoa", "UEI": "UEI (Junta Andalucia)",
                      "MdM": "Maria de Maeztu"}.get(modalidad, modalidad)

    n_sel = len(sel_raw)
    n_casi = len(casi_raw)
    total = n_sel + n_casi
    all_raw = list(sel_raw) + list(casi_raw)
    all_docs = list(docs_sel) + list(casi_docs)

    def evaluar_uno(idx, doc, raw_e):
        nombre = raw_e.get("nombre_completo", "?")
        es_seleccionado = idx < n_sel
        perfil = _build_perfil_completo(doc, raw_e)
        result = _evaluar_candidato_fase1(perfil, modalidad_full, inst, modalidad_code=modalidad)
        return idx, nombre, es_seleccionado, result

    # Evaluar todos en paralelo — max 8 workers (limitado por rate limits de la API)
    max_workers = min(8, total)
    evaluaciones_por_idx = {}
    errores = []
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(evaluar_uno, idx, doc, raw_e): idx
            for idx, (doc, raw_e) in enumerate(zip(all_docs, all_raw))
        }
        for future in as_completed(futures):
            idx, nombre, es_seleccionado, result = future.result()
            completed += 1
            # progress_callback se llama en el hilo principal (requerido por Streamlit)
            if progress_callback:
                tag = "garante" if es_seleccionado else "excluido"
                progress_callback(completed - 1, total, f"{nombre} ({tag})")
            if result and "error" not in result:
                result["nombre"] = nombre  # forzar nombre real, no el que redacta el LLM
                result["es_seleccionado"] = es_seleccionado
                evaluaciones_por_idx[idx] = result
            else:
                err_msg = (result or {}).get("error", "sin respuesta")
                errores.append(f"{nombre}: {err_msg}")
                evaluaciones_por_idx[idx] = {
                    "nombre": nombre, "hitos": [],
                    "narrativa": f"Error en la evaluacion: {err_msg}",
                    "fortalezas": [], "debilidades": [],
                    "puntuacion": 0, "supera_umbral": False,
                    "veredicto": "Error", "es_seleccionado": es_seleccionado,
                }

    # Restaurar orden original
    evaluaciones = [evaluaciones_por_idx[i] for i in range(total)]

    # Ranking unificado (seleccionados + excluidos)
    ranking = sorted(evaluaciones, key=lambda e: -(e.get("puntuacion", 0)))
    ranking_final = []
    for i, e in enumerate(ranking):
        ranking_final.append({
            "posicion": i + 1,
            "nombre": e.get("nombre", "?"),
            "puntuacion": e.get("puntuacion", 0),
            "es_seleccionado": e.get("es_seleccionado", True),
            "supera_umbral": e.get("supera_umbral", False),
            "veredicto": e.get("veredicto", "?"),
        })

    # Detectar swaps: excluidos que superan a seleccionados
    sel_evals = [e for e in evaluaciones if e.get("es_seleccionado")]
    casi_evals = [e for e in evaluaciones if not e.get("es_seleccionado")]
    min_sel_pts = min((e.get("puntuacion", 0) for e in sel_evals), default=0)

    swaps = []
    for exc in casi_evals:
        exc_pts = exc.get("puntuacion", 0)
        if exc_pts <= min_sel_pts:
            continue
        peores_sel = [s for s in sel_evals if s.get("puntuacion", 0) < exc_pts]
        if peores_sel:
            peor = min(peores_sel, key=lambda s: s.get("puntuacion", 0))
            swaps.append({
                "excluido": exc.get("nombre", "?"),
                "excluido_pts": exc_pts,
                "seleccionado": peor.get("nombre", "?"),
                "seleccionado_pts": peor.get("puntuacion", 0),
            })

    # Valoración del conjunto (secuencial, tras tener todos los resultados)
    resumen = "\n".join(
        f"- {e.get('nombre','?')}: {e.get('puntuacion',0)}/10 — {e.get('veredicto','?')}"
        f" {'[SELECCIONADO]' if e.get('es_seleccionado') else '[EXCLUIDO]'}"
        for e in ranking
    )
    val_prompt = f"""Estos son los candidatos evaluados para la solicitud {modalidad_full} del {inst['nombre_largo']}, ordenados por puntuacion (garantes seleccionados por MIP + mejores excluidos):

{resumen}

Escribe un parrafo de valoracion del CONJUNTO y, si algun excluido supera a un seleccionado, recomienda el intercambio. Responde en JSON:
{{"valoracion_conjunto": "Parrafo valorando masa critica, swaps recomendados y viabilidad."}}"""

    val_result = _call_evaluator(_SYSTEM_PROMPTS_FASE1.get(modalidad, SYSTEM_PROMPT_FASE1_MDM), val_prompt, max_tokens=1500)
    valoracion = ""
    if val_result and "error" not in val_result:
        valoracion = val_result.get("valoracion_conjunto", "")

    superan_umbral = sum(1 for e in sel_evals if e.get("supera_umbral"))
    necesarios = {"SO": 10, "UEI": 5, "MdM": 6}.get(modalidad, 6)

    return {
        "evaluaciones": evaluaciones,
        "ranking_final": ranking_final,
        "swaps_recomendados": swaps,
        "valoracion_conjunto": valoracion,
        "superan_umbral": superan_umbral,
        "necesarios": necesarios,
        "superada_fase1": superan_umbral >= necesarios,
        "errores": errores,
    }
