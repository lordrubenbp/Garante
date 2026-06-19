"""Búsqueda de fichajes estratégicos en OpenAlex para mejorar métricas del grupo."""
import os
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))
import config as cfg

OPENALEX_BASE = "https://api.openalex.org"
MAILTO = cfg.OPENALEX_MAILTO
MAX_WORKERS = 5


def _api_get(endpoint, params, timeout=15):
    """GET request to OpenAlex with polite pool."""
    params["mailto"] = MAILTO
    try:
        resp = requests.get(f"{OPENALEX_BASE}/{endpoint}", params=params, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def _search_author(nombre):
    """Busca un autor en OpenAlex por nombre."""
    data = _api_get("authors", {"search": nombre})
    if data and data.get("results"):
        return data["results"][0]
    return None


def _get_author_works(author_id, per_page=50):
    """Obtiene obras recientes de un autor."""
    data = _api_get("works", {
        "filter": f"author.id:{author_id}",
        "sort": "publication_year:desc",
        "per_page": per_page,
    })
    return data.get("results", []) if data else []


def analizar_debilidades(sel_raw, diagnostico, modalidad="MdM"):
    """
    Analiza el grupo actual y detecta debilidades a cubrir con fichajes.

    Returns:
        dict con:
            - h_deficit: True si h medio bajo
            - eu_deficit: True si pocos proyectos EU
            - areas_faltantes: áreas del instituto no cubiertas
            - paridad_deficit: género minoritario si desequilibrio
            - h_umbral: h-index mínimo deseado para fichajes
            - topics_grupo: topics principales del grupo actual
    """
    metricas = diagnostico.get("metricas", {})

    h_mean = metricas.get("h_mean", 0)
    h_umbral = (cfg.H_TARGET_SO if modalidad == "SO"
                else cfg.H_TARGET_UEI if modalidad == "UEI"
                else cfg.H_TARGET_MDM)

    # EU deficit
    eu_count = sum(1 for r in sel_raw if r.get("proyectos_eu", 0) > 0)
    eu_min = (cfg.EU_MIN_SO if modalidad == "SO"
              else cfg.EU_MIN_UEI if modalidad == "UEI"
              else cfg.EU_MIN_MDM)
    eu_deficit = eu_count < eu_min

    # Areas cubiertas vs posibles
    areas_cubiertas = set(r.get("area", "") for r in sel_raw if r.get("area"))
    areas_faltantes = set()  # sin pool completo no podemos saber qué áreas faltan

    # Paridad
    mujeres = sum(1 for r in sel_raw if r.get("genero") == "Mujer")
    hombres = len(sel_raw) - mujeres
    n = len(sel_raw)
    paridad_deficit = None
    if n == 0:
        return {"h_deficit": True, "h_umbral": h_umbral, "h_mean_actual": 0, "eu_deficit": True,
                "eu_count": 0, "eu_min": eu_min, "areas_faltantes": [],
                "areas_cubiertas": [], "paridad_deficit": None, "topics_grupo": []}
    if mujeres / n < 0.4:
        paridad_deficit = "Mujer"
    elif hombres / n < 0.4:
        paridad_deficit = "Hombre"

    # Topics del grupo (para buscar por afinidad)
    topics_grupo = set()
    for r in sel_raw:
        area = r.get("area", "")
        if area:
            topics_grupo.add(area)

    return {
        "h_deficit": h_mean < h_umbral,
        "h_umbral": h_umbral,
        "h_mean_actual": h_mean,
        "eu_deficit": eu_deficit,
        "eu_count": eu_count,
        "eu_min": eu_min,
        "areas_faltantes": sorted(areas_faltantes),
        "areas_cubiertas": sorted(areas_cubiertas),
        "paridad_deficit": paridad_deficit,
        "topics_grupo": sorted(topics_grupo),
    }


def buscar_fichajes_estrategicos(sel_raw, diagnostico, modalidad="MdM", max_fichajes=8):
    """
    Busca investigadores en OpenAlex que cubrirían las debilidades del grupo.

    Pipeline:
    1. Analiza debilidades del grupo actual
    2. Busca por topics afines en OpenAlex (filtrando por h alto, España/Europa)
    3. Busca coautores de garantes actuales (afinidad)
    4. Puntúa cada candidato por cuántas debilidades cubre
    5. Devuelve top fichajes ordenados por impacto potencial

    Returns:
        (debilidades, fichajes)
        - debilidades: dict con análisis de debilidades
        - fichajes: lista de dicts con candidatos externos
    """
    debilidades = analizar_debilidades(sel_raw, diagnostico, modalidad)

    # Nombres del grupo actual (para excluirlos)
    nombres_grupo = set(r.get("nombre_completo", "").lower() for r in sel_raw)

    candidatos = {}  # openalex_id -> candidato dict

    # --- Estrategia 1: Buscar coautores de garantes (afinidad) ---
    garante_ids = {}

    def _lookup_garante(r):
        author = _search_author(r["nombre_completo"])
        return (r["nombre_completo"], author["id"] if author else None)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        lookups = list(executor.map(_lookup_garante, sel_raw[:10]))
    garante_ids = {name: aid for name, aid in lookups if aid}

    def _get_coauthors_of(gid_gname):
        gid, gname = gid_gname
        works = _get_author_works(gid, per_page=20)
        coauthors = []
        for work in works:
            for authorship in work.get("authorships", []):
                aid = authorship.get("author", {}).get("id", "")
                aname = authorship.get("author", {}).get("display_name", "")
                if aid and aid != gid and aname.lower() not in nombres_grupo:
                    # Check country/institution
                    institutions = authorship.get("institutions", [])
                    country = ""
                    inst_name = ""
                    if institutions:
                        country = institutions[0].get("country_code", "")
                        inst_name = institutions[0].get("display_name", "")
                    coauthors.append({
                        "id": aid, "nombre": aname, "garante": gname,
                        "country": country, "institucion": inst_name,
                    })
        return coauthors

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        all_coauthor_lists = list(executor.map(_get_coauthors_of, garante_ids.items()))

    for coauthor_list in all_coauthor_lists:
        for ca in coauthor_list:
            aid = ca["id"]
            if aid not in candidatos:
                candidatos[aid] = {
                    "openalex_id": aid,
                    "nombre": ca["nombre"],
                    "conectados_con": set(),
                    "country": ca["country"],
                    "institucion": ca["institucion"],
                }
            candidatos[aid]["conectados_con"].add(ca["garante"])

    # --- Estrategia 2: Buscar por topics del grupo con h alto ---
    topics_search = debilidades["topics_grupo"][:5]  # top 5 áreas
    for topic in topics_search:
        # Buscar autores con alto h-index en este topic
        h_filter = max(5, debilidades["h_umbral"] - 5)  # slightly lower threshold to get more candidates
        data = _api_get("authors", {
            "search": topic,
            "filter": f"summary_stats.h_index:>{h_filter}",
            "sort": "summary_stats.h_index:desc",
            "per_page": 15,
        })
        if data and data.get("results"):
            for author in data["results"]:
                aid = author.get("id", "")
                aname = author.get("display_name", "")
                if not aid or aname.lower() in nombres_grupo:
                    continue
                if aid not in candidatos:
                    inst_name = ""
                    country = ""
                    affils = author.get("affiliations", [])
                    if affils:
                        inst_name = affils[0].get("institution", {}).get("display_name", "")
                        country = affils[0].get("institution", {}).get("country_code", "")
                    candidatos[aid] = {
                        "openalex_id": aid,
                        "nombre": aname,
                        "conectados_con": set(),
                        "country": country,
                        "institucion": inst_name,
                        "h_index": author.get("summary_stats", {}).get("h_index", 0),
                        "works_count": author.get("works_count", 0),
                        "cited_by_count": author.get("cited_by_count", 0),
                        "i10_index": author.get("summary_stats", {}).get("i10_index", 0),
                        "topics": [t.get("display_name", "") for t in (author.get("topics") or [])[:5]],
                        "_from_topic_search": True,
                    }
        time.sleep(0.2)

    # --- Enriquecer candidatos con métricas (solo los que no tienen datos ya) ---
    def _enrich(c):
        if c.get("_from_topic_search"):
            # Already has data from search results
            c["conectados_con"] = sorted(c["conectados_con"])
            c["n_conexiones"] = len(c["conectados_con"])
            return c
        oa_id = c["openalex_id"].split("/")[-1] if "/" in c["openalex_id"] else c["openalex_id"]
        data = _api_get(f"authors/{oa_id}", {})
        if data:
            c["h_index"] = data.get("summary_stats", {}).get("h_index", 0)
            c["works_count"] = data.get("works_count", 0)
            c["cited_by_count"] = data.get("cited_by_count", 0)
            c["i10_index"] = data.get("summary_stats", {}).get("i10_index", 0)
            topics = data.get("topics", [])
            c["topics"] = [t.get("display_name", "") for t in topics[:5]]
            if not c.get("institucion"):
                affils = data.get("affiliations", [])
                if affils:
                    c["institucion"] = affils[0].get("institution", {}).get("display_name", "")
                    c["country"] = affils[0].get("institution", {}).get("country_code", "")
        else:
            c.setdefault("h_index", 0)
            c.setdefault("works_count", 0)
            c.setdefault("cited_by_count", 0)
            c.setdefault("i10_index", 0)
            c.setdefault("topics", [])
        c["conectados_con"] = sorted(c["conectados_con"])
        c["n_conexiones"] = len(c["conectados_con"])
        return c

    # Limit to top candidates before enriching (save API calls)
    # Pre-sort by connections
    cands_list = sorted(candidatos.values(), key=lambda x: -len(x["conectados_con"]))
    cands_list = cands_list[:max_fichajes * 3]  # enrich 3x candidates, then filter

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        cands_list = list(executor.map(_enrich, cands_list))

    # --- Scoring: cuántas debilidades cubre cada candidato ---
    for c in cands_list:
        score = 0.0
        razones = []

        # h-index alto
        if debilidades["h_deficit"] and c["h_index"] >= debilidades["h_umbral"]:
            score += 3.0
            razones.append(f"h={c['h_index']} sube media del grupo")
        elif c["h_index"] >= debilidades["h_umbral"] * 0.8:
            score += 1.5
            razones.append(f"h={c['h_index']} refuerza excelencia")

        # Conexión con garantes (afinidad)
        if c["n_conexiones"] >= 3:
            score += 3.0
            razones.append(f"copublica con {c['n_conexiones']} garantes")
        elif c["n_conexiones"] >= 2:
            score += 2.0
            razones.append(f"copublica con {c['n_conexiones']} garantes")
        elif c["n_conexiones"] >= 1:
            score += 1.0
            razones.append(f"copublica con {c['conectados_con'][0]}")

        # Áreas faltantes (max 1 match to avoid inflation)
        areas_matched = set()
        if c.get("topics"):
            for topic in c["topics"]:
                topic_lower = topic.lower()
                for area in debilidades["areas_faltantes"]:
                    if area not in areas_matched and (area.lower() in topic_lower or topic_lower in area.lower()):
                        score += 2.0
                        razones.append(f"cubre area faltante: {area}")
                        areas_matched.add(area)
                        break

        # Internacionalización
        if c.get("country") and c["country"] not in ("ES", ""):
            score += 1.5
            razones.append(f"internacionalización ({c['country']})")

        # Works count alto (productividad)
        if c.get("works_count", 0) > 100:
            score += 0.5

        c["score"] = round(score, 2)
        c["razones"] = razones

    # Filtrar: al menos 1 razón y h > 0
    cands_list = [c for c in cands_list if c["score"] > 0 and c["h_index"] > 0]

    # Ordenar por score
    cands_list.sort(key=lambda x: -x["score"])

    return debilidades, cands_list[:max_fichajes]

