"""Utilidades compartidas para el optimizador de garantes CASPER-3."""
from __future__ import annotations

import numpy as np
from typing import TYPE_CHECKING

import optimizer.config as cfg

if TYPE_CHECKING:
    from typing import List, Set


def k_medio_individual(K: np.ndarray, i: int, sel: list[int]) -> float:
    """Cohesión media de un candidato con el resto del grupo seleccionado."""
    others = [K[i][j] for j in sel if j != i]
    return float(np.mean(others)) if others else 0.0


def k_medio_subgrafo(K: np.ndarray, sel: list[int]) -> float:
    """Cohesión media de todos los pares en el subgrafo seleccionado."""
    pairs = [(i, j) for idx_i, i in enumerate(sel) for j in sel[idx_i + 1:]]
    return float(np.mean([K[i][j] for i, j in pairs])) if pairs else 0.0


def compute_nucleo_potencial(indices: list[int], E: np.ndarray, K: np.ndarray) -> float:
    """Calcula el potencial de un nucleo: ALPHA*E_mean + BETA*K_mean (default 0.95/0.05)."""
    if not indices:
        return 0.0
    e_mean = float(np.mean([E[i] for i in indices]))
    return cfg.ALPHA * e_mean + cfg.BETA * k_medio_subgrafo(K, indices)


# ── Narrativa de justificación del E_i ───────────────────────────────────────

# Descripción legible de cada dimensión (para la frase principal)
_DIM_DESC = {
    "produccion":     "su producción científica de alto impacto",
    "ip":             "su liderazgo de proyectos como investigador/a principal",
    "tesis":          "su labor formativa en dirección de tesis doctorales",
    "tendencia":      "la evolución ascendente de su impacto reciente",
    "eu":             "su participación en proyectos europeos",
    "intl":           "su colaboración internacional",
    "reconocimiento": "su reconocimiento (patentes, distinciones y comités científicos)",
    "i10":            "su volumen de publicaciones de alto impacto (índice i10)",
    "impacto_art":    "el impacto real de sus publicaciones (citas por artículo)",
    "sexenios":       "los sexenios de investigación reconocidos",
    "top_mundial":    "su posición en el top mundial de su subcampo (percentil OpenAlex)",
}

# Etiqueta corta de cada dimensión (para enumeraciones secundarias)
_DIM_CORTA = {
    "produccion": "producción", "ip": "liderazgo (IP)", "tesis": "dirección de tesis",
    "tendencia": "tendencia", "eu": "proyectos europeos", "intl": "internacionalización",
    "reconocimiento": "reconocimiento", "i10": "i10", "impacto_art": "impacto artículos",
    "sexenios": "sexenios", "top_mundial": "top mundial",
}

_MODALIDAD_LABEL = {"SO": "Severo Ochoa", "MdM": "María de Maeztu", "UEI": "Unidad de Excelencia"}


def _pesos_por_modalidad(modalidad: str) -> dict:
    """Devuelve el vector de pesos E_i de la modalidad (mismo que usa compute_E)."""
    if modalidad == "SO":
        return cfg.PESOS_SO
    if modalidad == "UEI":
        return cfg.PESOS_UEI
    return cfg.PESOS_MDM


def _cualitativo(v: float) -> str:
    """Lectura cualitativa de un valor normalizado [0,1] respecto al pool."""
    if v >= 0.8:
        return "situándose entre los mejores del instituto"
    if v >= 0.5:
        return "con un valor destacado"
    if v >= 0.3:
        return "con un valor intermedio"
    return "de forma más discreta"


def narrativa_garante(rg: dict, modalidad: str = "MdM", pesos: dict | None = None) -> str:
    """
    Construye una narrativa en español que explica el cálculo del E_i de un
    garante, descomponiéndolo en las dimensiones que más aportan a su puntuación.

    El objetivo es que quien lea entienda *por qué* ese perfil se propone como
    garante: qué méritos concretos elevan su Excelencia Individual.

    Args:
        rg: dict de un investigador (debe incluir "dims_norm" y "E_i").
        modalidad: "SO", "MdM" o "UEI" — determina los pesos por defecto.
        pesos: vector de pesos efectivo (p. ej. pesos personalizados de la UI).
            Si es None, se usan los pesos por defecto de la modalidad. Debe ser
            el MISMO vector con el que se calculó el E_i del investigador para
            que la descomposición sea coherente.

    Returns:
        str con uno o varios párrafos; cadena vacía si faltan datos.
    """
    dims = rg.get("dims_norm") or {}
    if not dims:
        return ""

    if pesos is None:
        pesos = _pesos_por_modalidad(modalidad)
    e_i = float(rg.get("E_i", 0.0))
    nombre = rg.get("nombre_completo", "Este investigador")
    figura = (rg.get("figura") or "").strip()
    area = (rg.get("area") or "").strip()
    mod_label = _MODALIDAD_LABEL.get(modalidad, modalidad)

    # Contribución de cada dimensión con peso > 0
    contribs = []
    for k, w in pesos.items():
        if w <= 0:
            continue
        v = float(dims.get(k, 0.0))
        contribs.append((k, w, v, w * v))
    if not contribs:
        return ""
    raw_total = sum(c[3] for c in contribs)
    total = raw_total or 1.0
    contribs.sort(key=lambda c: -c[3])

    # Perfil sin méritos computables: narrativa neutra (caso límite, no debería
    # darse en un garante seleccionado).
    if raw_total < 0.02:
        rol = f", {figura}," if figura else ""
        en_area = f" en el área de {area}" if area else ""
        return (
            f"El índice de Excelencia Individual (E_i) de {nombre}{rol} es "
            f"{e_i:.3f} sobre 1{en_area}. Las diez dimensiones ponderadas del "
            f"modelo apenas registran méritos para este perfil, por lo que su "
            f"E_i es muy bajo respecto al conjunto de candidatos."
        )

    # ── Apertura ──
    rol = f", {figura}," if figura else ""
    en_area = f" en el área de {area}" if area else ""
    frases = [
        f"El índice de Excelencia Individual (E_i) de {nombre}{rol} alcanza "
        f"{e_i:.3f} sobre 1, valor que resume su mérito agregado{en_area} según "
        f"los pesos de la modalidad {mod_label}. El E_i es la suma ponderada de "
        f"diez dimensiones, cada una normalizada respecto al conjunto de candidatos."
    ]

    # ── Dimensiones que más aportan ──
    top = contribs[:3]
    share_top = sum(c[3] for c in top) / total
    descs = [_DIM_DESC.get(k, k) for k, *_ in top]
    if len(descs) >= 3:
        enum = f"{descs[0]}, {descs[1]} y {descs[2]}"
    elif len(descs) == 2:
        enum = f"{descs[0]} y {descs[1]}"
    else:
        enum = descs[0]
    frases.append(
        f"Su puntuación se sustenta principalmente en {enum}, dimensiones que "
        f"concentran el {share_top * 100:.0f} % de su E_i."
    )

    # Detalle cuantitativo de las 2 principales.
    # La aportación real al E_i incluye el factor de equilibrio (balance_factor),
    # igual que en compute_E: E_i = Σ(peso·valor) · balance_factor.
    _bf = float(rg.get("balance_factor", 1.0) or 1.0)
    for k, w, v, contrib in top[:2]:
        frases.append(
            f"En {_DIM_CORTA.get(k, k)}, su valor normalizado es {v:.2f}, "
            f"{_cualitativo(v)}; con un peso del {w * 100:.0f} % en la "
            f"modalidad, aporta {contrib * _bf:.3f} puntos al E_i."
        )

    # ── Áreas de menor aportación (solo si son claramente bajas) ──
    bajas = [c for c in contribs if c[2] < 0.3]
    if bajas:
        nombres_bajas = [_DIM_CORTA.get(k, k) for k, *_ in bajas[-2:]]
        if len(nombres_bajas) == 2:
            frases.append(
                f"Sus dimensiones con menor aportación son {nombres_bajas[0]} y "
                f"{nombres_bajas[1]}, que apenas elevan la puntuación."
            )
        else:
            frases.append(
                f"Su dimensión con menor aportación es {nombres_bajas[0]}, "
                f"que apenas eleva la puntuación."
            )

    # ── Equilibrio del perfil ──
    bf = rg.get("balance_factor")
    if bf is not None:
        if bf >= 0.97:
            frases.append(
                "El perfil es equilibrado entre dimensiones, lo que el modelo "
                "premia frente a perfiles muy especializados."
            )
        elif bf < 0.93:
            frases.append(
                "El perfil está marcadamente especializado en pocas dimensiones, "
                "lo que el modelo penaliza ligeramente frente a candidaturas más "
                "equilibradas."
            )

    # ── Cierre alineado con la convocatoria ──
    dim_top = top[0][0]
    frases.append(
        f"En conjunto, {_DIM_DESC.get(dim_top, dim_top)} es el factor que más "
        f"lo posiciona como garante, en línea con los criterios de excelencia de "
        f"la convocatoria {mod_label}."
    )

    return " ".join(frases)


def score_nucleo_multidim(indices: list[int], raw: list, E: np.ndarray, K: np.ndarray,
                          modalidad: str = "MdM", pesos_override: dict | None = None) -> dict:
    """
    Scoring multidimensional de un núcleo (6 factores).

    Returns:
        dict con score total + desglose de cada factor.
    """
    pesos = pesos_override if pesos_override is not None else (
        cfg.PESOS_NUCLEO_SO if modalidad == "SO"
        else cfg.PESOS_NUCLEO_UEI if modalidad == "UEI"
        else cfg.PESOS_NUCLEO_MDM)

    # 1. Cohesión interna
    k_mean = k_medio_subgrafo(K, indices)

    # 2. Excelencia media
    e_mean = float(np.mean([E[i] for i in indices]))

    # 3. Diversidad de áreas (normalizado 0-1)
    areas = set(raw[i]["area"] for i in indices if raw[i].get("area"))
    # Max razonable = 6 áreas distintas en un núcleo pequeño
    diversidad = min(len(areas) / 6.0, 1.0)

    # 4. Equilibrio senior/junior
    # Senior: h >= H_TARGET (25 SO / 15 MdM); Junior con potencial: tendencia > 0
    _h_senior = (cfg.H_TARGET_SO if modalidad == "SO"
                 else cfg.H_TARGET_UEI if modalidad == "UEI"
                 else cfg.H_TARGET_MDM)
    h_vals = [raw[i].get("h_index", 0) for i in indices]
    tend_vals = [raw[i].get("tendencia", 0) for i in indices]
    n_senior = sum(1 for h in h_vals if h >= _h_senior)
    n_rising = sum(1 for t in tend_vals if t > 0)
    n = len(indices)
    # Ideal: mix ~50/50 senior vs rising
    ratio_senior = n_senior / n if n > 0 else 0
    ratio_rising = n_rising / n if n > 0 else 0
    # Score is higher when both are present (not all one type)
    equilibrio = min(ratio_senior, ratio_rising) * 2  # max 1.0 when 50/50
    equilibrio = min(equilibrio + 0.3 * ratio_senior, 1.0)  # bonus for having seniors

    # 5. Tendencia del grupo
    tend_mean = float(np.mean(tend_vals)) if tend_vals else 0.0
    # Normalize: tendencia typically in [-0.5, 0.5], map to [0, 1]
    tendencia_norm = max(0.0, min(1.0, (tend_mean + 1.0) / 5.0))  # rango real tendencia: [-1, 4]

    # 6. Internacionalización (EU projects + intl institutions)
    eu_scores = [raw[i].get("proyectos_eu", 0) + raw[i].get("proyectos_eu_ip", 0) * 2 for i in indices]
    intl_scores = [raw[i].get("instituciones_intl", 0) for i in indices]
    eu_mean = float(np.mean(eu_scores)) if eu_scores else 0.0
    intl_mean = float(np.mean(intl_scores)) if intl_scores else 0.0
    # Normalize: EU ~ [0, 10], intl ~ [0, 20]
    intl_norm = min(1.0, (eu_mean / 6.0) * 0.6 + (intl_mean / 10.0) * 0.4)

    # Compute total score
    score = (pesos["cohesion"] * k_mean +
             pesos["top_mundial"] * e_mean +
             pesos["diversidad_areas"] * diversidad +
             pesos["equilibrio_senior_junior"] * equilibrio +
             pesos["tendencia"] * tendencia_norm +
             pesos["internacionalizacion"] * intl_norm)

    return {
        "score": round(score, 4),
        "cohesion": round(k_mean, 4),
        "top_mundial": round(e_mean, 4),
        "diversidad_areas": round(diversidad, 4),
        "equilibrio_senior_junior": round(equilibrio, 4),
        "tendencia": round(tendencia_norm, 4),
        "internacionalizacion": round(intl_norm, 4),
        "n_areas": len(areas),
        "areas": sorted(areas),
    }


def short_name(nombre: str) -> str:
    """Acorta un nombre completo a nombre + primer apellido."""
    parts = nombre.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    return nombre


def _louvain_communities(raw: list, E: np.ndarray, K: np.ndarray, max_clusters: int = 5,
                          modalidad: str = "MdM", pesos_override: dict | None = None,
                          size_override: int | None = None) -> list[dict]:
    """Detecta núcleos de colaboración via Louvain, limitados al tamaño configurado."""
    import networkx as nx
    from networkx.algorithms.community import louvain_communities

    nucleo_size = size_override if size_override is not None else (
        cfg.NUCLEO_SIZE_SO if modalidad == "SO"
        else cfg.NUCLEO_SIZE_UEI if modalidad == "UEI"
        else cfg.NUCLEO_SIZE_MDM)

    n = len(raw)
    G = nx.Graph()
    for i in range(n):
        G.add_node(i)
    for i in range(n):
        for j in range(i + 1, n):
            if K[i][j] > 0:
                G.add_edge(i, j, weight=float(K[i][j]))

    try:
        communities = louvain_communities(G, weight='weight', seed=42)
    except Exception:
        communities = []

    nucleos = []
    for comm in communities:
        members = sorted(comm)
        connected = [i for i in members if any(K[i][j] > 0 for j in members if j != i)]
        if len(connected) < 2:
            continue

        # Limitar al tamaño configurado: seleccionar los mejores por E_i
        if len(connected) > nucleo_size:
            connected = sorted(connected, key=lambda i: -E[i])[:nucleo_size]

        scoring = score_nucleo_multidim(connected, raw, E, K, modalidad,
                                        pesos_override=pesos_override)

        nucleos.append({
            "indices": connected,
            "nombres": [raw[i]["nombre_completo"] for i in connected],
            "e_mean": scoring["top_mundial"],
            "k_mean": scoring["cohesion"],
            "potencial": scoring["score"],
            "scoring": scoring,
            "areas": scoring["areas"],
        })

    nucleos.sort(key=lambda x: -x["potencial"])
    return nucleos[:max_clusters]


def detect_nucleos(raw: list, E: np.ndarray, K: np.ndarray, max_clusters: int = 5,
                   modalidad: str = "MdM") -> list[dict]:
    """Wrapper de compatibilidad — solo Louvain, sin LLM."""
    return _louvain_communities(raw, E, K, max_clusters, modalidad=modalidad)


def detect_and_score_nucleos(
    raw: list,
    E: np.ndarray,
    K: np.ndarray,
    max_clusters: int = 5,
    max_total: int = 7,
    modalidad: str = "MdM",
    n_garantes: int = 10,
    pesos_override: dict | None = None,
    size_override: int | None = None,
) -> tuple[list[dict], dict | None]:
    """
    Pipeline unificado:
    1. Louvain → nucleos candidatos con scoring multidimensional
    2. LLM valida/rechaza nucleos + propone refuerzos para cada uno
    3. Merge, sort, return

    Returns:
        (nucleos, llm_result)
        - nucleos: lista ordenada por potencial, con 'refuerzos_ia' si disponible
        - llm_result: respuesta cruda del LLM (o None)
    """
    # Paso 1: Louvain + scoring multidimensional
    nucleos_louvain = _louvain_communities(raw, E, K, max_clusters, modalidad,
                                           pesos_override=pesos_override,
                                           size_override=size_override)

    # Paso 2: LLM valida y propone refuerzos
    llm_result = None
    try:
        from optimizer.llm_nucleos import validar_nucleos_y_proponer_refuerzos
        import optimizer.config as cfg
        if cfg.ANTHROPIC_API_KEY:
            raw_for_llm = [
                {
                    "nombre_completo": r["nombre_completo"],
                    "area": r["area"],
                    "h_index": r["h_index"],
                    "E_i": r["E_i"],
                    "genero": r["genero"],
                    "tendencia": r.get("tendencia", 0),
                    "proyectos_eu": r.get("proyectos_eu", 0),
                    "instituciones_intl": r.get("instituciones_intl", 0),
                    "proyectos_ip": r.get("proyectos_ip", 0),
                }
                for r in raw
            ]
            llm_result = validar_nucleos_y_proponer_refuerzos(
                raw_for_llm, nucleos_louvain, modalidad, n_garantes
            )
    except Exception as _llm_exc:
        import logging as _logging
        _logging.getLogger(__name__).warning(f"LLM nucleos call failed: {_llm_exc}")
        llm_result = {"error": str(_llm_exc), "nucleos": []}

    # Paso 3: Integrar resultados LLM
    # Si el LLM falló (excepción → {"error":..., "nucleos":[]}), tratar como None
    # para que el path de fallback Louvain sea limpio (con sus campos originales).
    _llm_ok = llm_result and "nucleos" in llm_result and not llm_result.get("error")
    all_nucleos = []
    if _llm_ok:
        for idx, nuc_llm in enumerate(llm_result.get("nucleos", [])):
            if idx >= len(nucleos_louvain):
                break
            nucleo = nucleos_louvain[idx].copy()
            nucleo["validado"] = nuc_llm.get("aprobado", True)
            nucleo["justificacion_ia"] = nuc_llm.get("justificacion", "")
            nucleo["refuerzos_ia"] = nuc_llm.get("refuerzos", [])
            # Boost/penalty from LLM validation
            if not nuc_llm.get("aprobado", True):
                nucleo["potencial"] *= 0.5  # penalizar rechazados
            all_nucleos.append(nucleo)
    else:
        # Sin LLM: usar todos los nucleos Louvain tal cual
        all_nucleos = list(nucleos_louvain)

    # Añadir nucleos Louvain que no fueron evaluados por LLM
    if _llm_ok and len(all_nucleos) < len(nucleos_louvain):
        for idx in range(len(all_nucleos), len(nucleos_louvain)):
            all_nucleos.append(nucleos_louvain[idx])

    # Paso 4: Ordenar y limitar
    all_nucleos.sort(key=lambda x: -x["potencial"])
    return all_nucleos[:max_total], llm_result


def prefilter_candidates(raw, E, docs, n_garantes, director_name=None,
                         fixed_names=None, exclude_names=None):
    """
    Prefiltra candidatos: top por E_i, asegurando director y fijados.

    Returns:
        top_idx: indices en raw/E/docs del pool filtrado
    """
    MAX_CANDIDATES = min(len(raw), max(5 * n_garantes, 50))
    # Excluir primero (antes de truncar)
    if exclude_names:
        excluir_ids = {i for i, r in enumerate(raw) if r["nombre_completo"] in exclude_names}
    else:
        excluir_ids = set()

    all_idx = np.argsort(E)[::-1].tolist()
    all_idx = [i for i in all_idx if i not in excluir_ids]
    top_idx = all_idx[:MAX_CANDIDATES]

    # Asegurar director
    if director_name:
        dir_matches = [i for i, r in enumerate(raw) if r["nombre_completo"] == director_name]
        if dir_matches and dir_matches[0] not in top_idx:
            top_idx.append(dir_matches[0])

    # Asegurar fijados
    if fixed_names:
        for nombre in fixed_names:
            matches = [i for i, r in enumerate(raw) if r["nombre_completo"] == nombre]
            if matches and matches[0] not in top_idx:
                top_idx.append(matches[0])

    return top_idx
