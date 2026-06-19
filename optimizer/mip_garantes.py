#!/usr/bin/env python3
"""
Optimizador MIP de Garantes — multi-instituto v2
Severo Ochoa / María de Maeztu 2026

Mejoras v2:
  - K_ij basado en copublicaciones reales (no estructura)
  - E_i híbrido OpenAlex + Dialnet
  - Restricción de diversidad de áreas

Uso:
  python mip_garantes.py --n 10
  python mip_garantes.py --n 6 --director "Ana García López"
  python mip_garantes.py --n 10 --min-areas 4 --out resultado.json
"""
import argparse
import json
import math
import sys
import os
from datetime import datetime

import numpy as np
from scipy.stats import linregress
from ortools.linear_solver import pywraplp
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(__file__))
import config as cfg


# ─────────────────────────────────────────────────────────────────────────────
# 1. CARGA DE DATOS
# ─────────────────────────────────────────────────────────────────────────────

def discover_institutes() -> list[str]:
    """Descubre institutos disponibles: BDs MongoDB que contienen la colección
    'investigadores'. El instituto demo (offline, datos sintéticos) se ofrece
    siempre, también cuando MongoDB no está accesible."""
    if not cfg.MONGO_URI:
        return [cfg.DEMO_INSTITUTE]  # sin credenciales: solo el demo offline
    try:
        client = MongoClient(cfg.MONGO_URI, serverSelectionTimeoutMS=5000)
        with client:
            all_dbs = client.list_database_names()
            institutes = [
                db for db in all_dbs
                if db not in cfg.MONGO_SYSTEM_DBS
                and db.endswith("_claude")
                and "investigadores" in client[db].list_collection_names()
            ]
        return sorted(institutes) + [cfg.DEMO_INSTITUTE]
    except Exception:
        return [cfg.DEMO_INSTITUTE]  # sin Mongo: solo el demo offline


def load_investigators(db_name: str = cfg.DB_NAME):
    """Lee investigadores elegibles de MongoDB y devuelve lista de dicts.
    Para el instituto demo (cfg.DEMO_INSTITUTE) devuelve datos sintéticos
    generados en memoria, sin tocar MongoDB."""
    if db_name == cfg.DEMO_INSTITUTE or not cfg.MONGO_URI:
        from demo_data import generate_demo_docs
        return generate_demo_docs()
    print(f"[1/4] Conectando a MongoDB ({db_name}.{cfg.COLLECTION})...", end=" ", flush=True)
    try:
        with MongoClient(cfg.MONGO_URI, serverSelectionTimeoutMS=8000) as client:
            client.admin.command("ping")
            db = client[db_name]
            docs = list(db[cfg.COLLECTION].find(
                {
                    "figura": {"$in": cfg.FIGURAS_ELEGIBLES},
                    "tesis.doctoral.titulo": {"$exists": True, "$ne": ""},
                    "openalex.h_index": {"$exists": True},
                },
                {
                    "_id": 0,
                    "id_investigador": 1,
                    "nombre_completo": 1,
                    "figura": 1,
                    "genero": 1,
                    "area": 1,
                    "grupo_investigacion": 1,
                    "financiaciones": 1,
                    "tesis": 1,
                    "openalex": 1,
                    "dialnet_metricas": 1,
                    "colaboraciones": 1,
                    "publicaciones": 1,
                    "google_scholar": 1,
                    "semantic_scholar": 1,
                    "metricas_unificadas": 1,
                    "patentes": 1,
                    "orcid_record": 1,
                    "sexenios": 1,
                    "fecha_ultimo_sexenio": 1,
                    "stanford_ranking": 1,
                    # openalex_percentil: eliminado (sustituido por openalex_percentil_stanford)
                    "openalex_percentil_stanford": 1,
                    # openalex_percentil_hibrido: eliminado
                }
            ))
        print(f"{len(docs)} investigadores elegibles.")
        return docs
    except Exception as exc:
        raise ConnectionError(f"Error de conexión a MongoDB ({db_name}): {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# 2. SCORE E_i  (híbrido OpenAlex + Dialnet)
# ─────────────────────────────────────────────────────────────────────────────

def _str_field(doc, key):
    """Extrae un campo que puede ser string u objeto {nombre: ...}."""
    v = doc.get(key, "")
    if isinstance(v, dict):
        return v.get("nombre", "")
    return str(v) if v else ""


def _infer_genero(doc):
    """Infiere género desde el campo 'figura' si 'genero' no está disponible."""
    genero = doc.get("genero")
    if genero:
        return genero
    figura = doc.get("figura", "")
    if any(tok in figura for tok in ["Profesora", "Catedrática", "Investigadora"]):
        return "Mujer"
    return "Hombre"


def _count_eu_projects(doc, periodo_ref=None):
    """Count European projects and EU projects as IP from financiaciones.

    Criterion: financiador contiene "UNIÓN EUROPEA" o "EUROPEAN RESEARCH COUNCIL".
    """
    _EU_MARKERS = ("unión europea", "union europea", "european research council")
    items = (doc.get("financiaciones") or {}).get("items", [])
    eu_total = 0
    eu_ip = 0
    for item in items:
        if periodo_ref:
            anualidad = item.get("anualidad") or 0
            if not (periodo_ref[0] <= anualidad <= periodo_ref[1]):
                continue
        financiador = (item.get("financiador") or "").strip().lower()
        if any(m in financiador for m in _EU_MARKERS):
            eu_total += 1
            if item.get("responsable") is True:
                eu_ip += 1
    return eu_total, eu_ip


def _count_intl_institutions(doc):
    """Count international collaborating institutions (pais != España)."""
    institutions = (doc.get("colaboraciones") or {}).get("instituciones", [])
    count = 0
    for inst in institutions:
        if not isinstance(inst, dict):
            continue
        pais = (inst.get("pais") or "").strip()
        if pais and pais.lower() not in ("españa", "spain", ""):
            count += 1
    return count


def _tendencia_oa_ratio(counts, periodo_ref=None):
    """Calcula tendencia por ratio de citas recientes vs anteriores (OpenAlex)."""
    if periodo_ref:
        mid = (periodo_ref[0] + periodo_ref[1]) // 2 + 1
        año_fin = periodo_ref[1]
    else:
        mid = 2023
        año_fin = cfg.CURRENT_YEAR - 1
    citas_rec = sum(y.get("cited_by_count", 0) for y in counts if mid <= y.get("year", 0) <= año_fin)
    citas_ant = sum(y.get("cited_by_count", 0) for y in counts
                    if (periodo_ref[0] if periodo_ref else 2020) <= y.get("year", 0) < mid)
    n_ant_years = max(mid - (periodo_ref[0] if periodo_ref else 2020), 1)
    n_rec_years = max(año_fin - mid + 1, 1)
    ant_py = citas_ant / n_ant_years
    rec_py = citas_rec / n_rec_years
    tendencia = min(rec_py / ant_py if ant_py > 0 else (4.0 if rec_py > 0 else 0.0), 4.0)
    return tendencia, "oa_ratio"


def _count_reconocimiento(doc):
    """Count patents + distinctions + memberships."""
    patentes = (doc.get("patentes") or {}).get("total", 0) or 0
    orcid = doc.get("orcid_record") or {}
    distinciones = int(orcid.get("distinciones", 0)) if isinstance(orcid.get("distinciones"), (int, float)) else 0
    membresias = int(orcid.get("membresias", 0)) if isinstance(orcid.get("membresias"), (int, float)) else 0
    return patentes, distinciones, membresias


def _score_sexenios(doc):
    """Score sexenios: count + 1.0 bonus if last sexenio is 'vivo' (within 6 years)."""
    count = doc.get("sexenios", 0) or 0
    fecha_str = doc.get("fecha_ultimo_sexenio", "")
    vivo_bonus = 0.0
    if fecha_str:
        try:
            import re as _re
            m = _re.search(r'\b(19|20)\d{2}\b', fecha_str)
            if m and int(m.group()) > cfg.CURRENT_YEAR - 6:
                vivo_bonus = 1.0
        except (ValueError, AttributeError):
            pass
    return count + vivo_bonus


def compute_E(docs, sjr_map=None, modalidad="MdM", periodo_ref=None):
    """
    Devuelve:
      E  : np.array shape (n,) con scores normalizados en [0, 1]
      raw: lista de dicts con métricas brutas (para el informe)

    periodo_ref: tuple (año_inicio, año_fin) inclusive.
      Si None, se usa el período por defecto de la modalidad (config).
      Filtra producción, proyectos IP, tesis, proyectos EU e impacto_art.
    """
    if periodo_ref is None:
        if modalidad == "SO":
            periodo_ref = cfg.PERIODO_REF_SO
        elif modalidad == "UEI":
            periodo_ref = cfg.PERIODO_REF_UEI
        else:
            periodo_ref = cfg.PERIODO_REF_MDM
    _año_ini, _año_fin = periodo_ref

    Q_WEIGHTS = {1: 4, 2: 3, 3: 2, 4: 1}
    raw = []

    for j in docs:
        oalex   = j.get("openalex", {}) or {}
        dialnet = j.get("dialnet_metricas", {}) or {}
        gs      = j.get("google_scholar", {}) or {}
        ss      = j.get("semantic_scholar", {}) or {}
        mu      = j.get("metricas_unificadas", {}) or {}

        counts  = oalex.get("counts_by_year", [])
        h_oalex = oalex.get("h_index", 0) or 0
        h_dial  = dialnet.get("h_index_dialnet", 0) or 0
        h_gs    = gs.get("h_index", 0) or 0
        h_ss    = (ss.get("h_index", 0) or 0) if ss.get("encontrado") else 0

        # H-index: OpenAlex como fuente canónica (más conservador y auditable que GS)
        h_index = h_oalex

        recent  = [y for y in counts if _año_ini <= y.get("year", 0) <= _año_fin]
        citas_2020 = sum(y.get("cited_by_count", 0) for y in recent)
        works_2020 = sum(y.get("works_count", 0)    for y in recent)

        # Producción ponderada por tipo desde publicaciones.items (CVN)
        _pubs_items = (j.get("publicaciones") or {}).get("items", [])
        produccion_cvn = sum(
            cfg.PRODUCCION_TYPE_WEIGHTS.get(
                p.get("tipo", ""), cfg.PRODUCCION_TYPE_WEIGHTS["_default"]
            )
            for p in _pubs_items
            if _año_ini <= (p.get("anualidad") or 0) <= _año_fin
        )

        # Tendencia: regresión lineal sobre citas/año (GS primario, OA fallback)
        gs_citas = gs.get("citas_por_anio", {})
        if gs_citas and len(gs_citas) >= 3:
            years_all = sorted(gs_citas.keys(), key=int)
            years_5 = [y for y in years_all if _año_ini <= int(y) <= _año_fin]
            if len(years_5) >= 3:
                xs = np.array([int(y) for y in years_5], dtype=float)
                ys = np.array([gs_citas[y] for y in years_5], dtype=float)
                slope = linregress(xs, ys).slope
                mean_c = ys.mean()
                tendencia = slope / mean_c if mean_c > 0 else 0.0
                tendencia = min(max(tendencia, -1.0), 4.0)
                tendencia_metodo = "gs_regresion"
            else:
                tendencia, tendencia_metodo = _tendencia_oa_ratio(counts, periodo_ref=periodo_ref)
        else:
            tendencia, tendencia_metodo = _tendencia_oa_ratio(counts, periodo_ref=periodo_ref)

        # (5c) Shrinkage de tendencia: amortigua hacia 0 si hay pocas publicaciones
        # en el período (slope/mean es ruidoso con muestras pequeñas).
        tendencia_shrink = 1.0
        if cfg.TENDENCIA_SHRINKAGE and cfg.TENDENCIA_MIN_PUBS > 0:
            tendencia_shrink = min(1.0, works_2020 / cfg.TENDENCIA_MIN_PUBS)
            tendencia *= tendencia_shrink

        # Liderazgo IP (carrera completa — méritos de trayectoria, no ventaneados)
        items_fin    = (j.get("financiaciones") or {}).get("items", [])
        proyectos_ip = sum(1 for p in items_fin
                          if p.get("responsable") is True)

        # Tesis dirigidas (carrera completa — méritos de trayectoria, no ventaneados)
        tesis_dir = len((j.get("tesis") or {}).get("dirigidas", []))

        # Proyectos europeos (carrera completa — méritos de trayectoria, no ventaneados)
        eu_total, eu_ip = _count_eu_projects(j, periodo_ref=None)
        # Colaboraciones internacionales
        instituciones_intl = _count_intl_institutions(j)
        # Reconocimiento (patentes + distinciones + membresias)
        patentes, distinciones, membresias = _count_reconocimiento(j)
        reconocimiento = patentes + distinciones + membresias

        # Sexenios (count + vivo bonus)
        sexenios_raw = _score_sexenios(j)

        # Citas en período de referencia: usamos OpenAlex counts_by_year (ya filtrado)
        # metricas_unificadas.citas_totales es lifetime y no se puede filtrar por período
        citas_cruzadas = citas_2020  # ya filtrado por _año_ini/_año_fin arriba

        # i10-index: GS primario
        i10_index = gs.get("i10_index", 0) or 0

        # Impacto a nivel de artículo: media de citas Crossref por publicación (DORA-compatible)
        pubs = (j.get("publicaciones") or {}).get("items", [])
        art_citas = []
        for p in pubs:
            if not (_año_ini <= (p.get("anualidad") or 0) <= _año_fin):
                continue
            cr = p.get("crossref", {}) or {}
            citas_cr = cr.get("citas_crossref")
            if citas_cr is not None:
                art_citas.append(float(citas_cr))
        impacto_art = sum(art_citas) / len(art_citas) if art_citas else 0.0

        # Calidad SJR legacy (opcional)
        calidad = 0.0
        if sjr_map:
            arts = [
                p for p in (j.get("publicaciones") or {}).get("items", [])
                if p.get("tipo") == "articulo"
                and p.get("crossref", {}).get("encontrado") is True
                and _año_ini <= (p.get("anualidad") or 0) <= _año_fin
            ]
            qs = []
            for p in arts:
                anio = str(p.get("anualidad") or "")
                for issn in p.get("crossref", {}).get("issn", []):
                    if issn not in sjr_map:
                        continue
                    entry = sjr_map[issn]
                    # Buscar el año exacto o el más cercano disponible
                    año_data = entry.get(anio) or entry.get(str(int(anio)-1) if anio else "") or (list(entry.values())[-1] if entry else None)
                    if not año_data:
                        continue
                    cuartil_str = año_data.get("cuartil", "")
                    # Convertir 'Q1'→1, 'Q2'→2, etc.
                    if cuartil_str and cuartil_str[0] == "Q" and cuartil_str[1:].isdigit():
                        qs.append(int(cuartil_str[1:]))
                    break  # un cuartil por artículo
            if qs:
                calidad = sum(Q_WEIGHTS.get(q, 0) for q in qs) / len(qs)

        # Última publicación (año más reciente) — fuente CVN (publicaciones.items)
        anualidades = [p.get("anualidad") or 0 for p in pubs if p.get("anualidad")]
        ultima_pub = max(anualidades) if anualidades else 0

        raw.append({
            "nombre_completo": j.get("nombre_completo", ""),
            "id_investigador": j.get("id_investigador"),
            "figura":          j.get("figura", ""),
            "genero":          _infer_genero(j),
            "area":            _str_field(j, "area"),
            "grupo":           _str_field(j, "grupo_investigacion"),
            "h_index":         h_index,
            "h_consolidado":   round(h_index, 2),
            "h_openalex":      h_oalex,
            "h_dialnet":       h_dial,
            "h_google_scholar": h_gs if h_gs > 0 else None,
            "h_semantic_scholar": h_ss if h_ss > 0 else None,
            "citas_2020":      citas_2020,
            "citas_cruzadas":  citas_cruzadas,
            "works_2020":      works_2020,        # OpenAlex (informativo)
            "produccion_cvn":  produccion_cvn,    # CVN ponderado por tipo (scoring)
            "proyectos_ip":    proyectos_ip,
            "tesis_dir":       tesis_dir,
            "tendencia":       round(tendencia, 3),
            "tendencia_metodo": tendencia_metodo,
            "tendencia_shrink": round(tendencia_shrink, 3),
            "calidad":         round(calidad, 3),
            "impacto_art":     round(impacto_art, 3),
            "i10_index":       i10_index,
            "proyectos_eu":      eu_total,
            "proyectos_eu_ip":   eu_ip,
            "eu_score_raw":      eu_total + 2 * eu_ip,
            "instituciones_intl": instituciones_intl,
            "patentes":          patentes,
            "distinciones":      distinciones,
            "membresias":        membresias,
            "reconocimiento":    reconocimiento,
            "sexenios":              j.get("sexenios", 0) or 0,
            "fecha_ultimo_sexenio":  j.get("fecha_ultimo_sexenio", ""),
            "sexenios_raw":          sexenios_raw,
            "ultima_publicacion": ultima_pub,
            "stanford_percentil":    (j.get("stanford_ranking") or {}).get("percentil"),
            "stanford_subfield":     (j.get("stanford_ranking") or {}).get("subfield"),
            # Percentil compuesto Stanford (3 metricas ponderadas + fallback GS)
            "openalex_pct":          (j.get("openalex_percentil_stanford") or {}).get("percentil"),
            "openalex_pct_subfield": (j.get("openalex_percentil_stanford") or {}).get("subfield"),
            "openalex_pct_detail":   (j.get("openalex_percentil_stanford") or {}).get("percentiles"),
            "openalex_pct_valores":  (j.get("openalex_percentil_stanford") or {}).get("valores"),
            "openalex_pct_capprox":  (j.get("openalex_percentil_stanford") or {}).get("c_approx"),
            "openalex_pct_metric":   (j.get("openalex_percentil_stanford") or {}).get("metric"),
            "openalex_pct_h_source": (j.get("openalex_percentil_stanford") or {}).get("h_source"),
            "openalex_pct_incompleto": (j.get("openalex_percentil_stanford") or {}).get("perfil_incompleto", False),
            "openalex_pct_total":    (j.get("openalex_percentil_stanford") or {}).get("total_subfield"),
            # Indicador hibrido (composite_5 + metricas locales)
        })

    # ── Dimensión 'top_mundial' = field-percentile mundial OpenAlex ─────────
    # Peso testimonial: señal de posicionamiento global, no duplicar métricas
    # de output. El percentil almacenado es "top X%" (menor = más élite).
    # Lo invertimos: oa_exc_raw = 100 − pct. Perfiles sin dato se imputan
    # con la MEDIANA de la cohorte (neutral).
    _exc_present = [100.0 - r["openalex_pct"] for r in raw
                    if r.get("openalex_pct") is not None
                    and not r.get("openalex_pct_incompleto", False)]
    _exc_median = float(np.median(_exc_present)) if _exc_present else 0.0
    for r in raw:
        pct = r.get("openalex_pct")
        if pct is None or r.get("openalex_pct_incompleto", False):
            r["oa_exc_raw"] = _exc_median
            r["oa_exc_imputado"] = True
        else:
            r["oa_exc_raw"] = 100.0 - float(pct)
            r["oa_exc_imputado"] = False

    # Normalización por dimensión.
    # (1a) "winsor": recorta al percentil cfg.E_NORM_PERCENTILE antes de escalar,
    # evitando que un outlier comprima al resto del pool (igual que compute_K).
    def norm_col(key):
        vals = [r[key] for r in raw]
        if not vals:
            return []
        arr = np.array(vals, dtype=float)
        # Transformación logarítmica para columnas con cola muy larga.
        # log1p(x) = log(x+1): mapea 0→0, suaviza outliers sin recorte brusco.
        if key in cfg.LOG_TRANSFORM_COLS:
            arr = np.log1p(arr)
        mn = float(arr.min())
        if cfg.E_NORM_METHOD == "winsor":
            hi = float(np.percentile(arr, cfg.E_NORM_PERCENTILE))
            if hi <= mn:
                return [0.0 for _ in arr]
            clipped = np.minimum(arr, hi)
            return [float(v) for v in (clipped - mn) / (hi - mn)]
        # "minmax" clásico
        mx = float(arr.max())
        return [0.0 if mx == mn else (v - mn) / (mx - mn) for v in vals]

    # Nota: el h-index es lifetime (no descomponible por periodo) y se usa como
    # gate de elegibilidad (h_min) y como indicador de trayectoria/contexto, NO
    # dentro del E_i. La dimensión 'produccion' se calcula solo con métricas
    # ventaneadas al periodo de referencia de la convocatoria (citas + CVN).
    c_n   = norm_col("citas_cruzadas")
    w_n   = norm_col("produccion_cvn")
    ip_n  = norm_col("proyectos_ip")
    t_n   = norm_col("tesis_dir")
    tr_n  = norm_col("tendencia")
    cal_n = norm_col("calidad")
    eu_n  = norm_col("eu_score_raw")
    intl_n = norm_col("instituciones_intl")
    reco_n = norm_col("reconocimiento")
    i10_n  = norm_col("i10_index")
    iart_n = norm_col("impacto_art")
    sex_n  = norm_col("sexenios_raw")
    exc_n  = norm_col("oa_exc_raw")

    # Select weights based on modality
    if modalidad == "SO":
        pesos = cfg.PESOS_SO
    elif modalidad == "MdM":
        pesos = cfg.PESOS_MDM
    elif modalidad == "UEI":
        pesos = cfg.PESOS_UEI
    elif sjr_map:
        pesos = cfg.PESOS_5D
    else:
        pesos = cfg.PESOS_4D

    scores = []
    for i in range(len(raw)):
        prod = (c_n[i] + w_n[i]) / 2

        # Valores normalizados por dimensión (nombres alineados con los pesos)
        dim_vals = {
            "produccion": prod, "ip": ip_n[i], "tesis": t_n[i],
            "tendencia": tr_n[i], "eu": eu_n[i], "intl": intl_n[i],
            "reconocimiento": reco_n[i], "i10": i10_n[i],
            "impacto_art": iart_n[i], "sexenios": sex_n[i], "calidad": cal_n[i],
            "top_mundial": exc_n[i],
        }

        if "eu" in pesos:
            s = (pesos["produccion"]     * prod +
                 pesos["ip"]             * ip_n[i] +
                 pesos["tesis"]          * t_n[i] +
                 pesos["tendencia"]      * tr_n[i] +
                 pesos["eu"]             * eu_n[i] +
                 pesos["intl"]           * intl_n[i] +
                 pesos["reconocimiento"] * reco_n[i] +
                 pesos["i10"]            * i10_n[i] +
                 pesos["impacto_art"]    * iart_n[i] +
                 pesos.get("sexenios", 0)    * sex_n[i] +
                 pesos.get("top_mundial", 0) * exc_n[i])
        elif sjr_map:
            s = (pesos["calidad"]    * cal_n[i] +
                 pesos["ip"]         * ip_n[i] +
                 pesos["tesis"]      * t_n[i] +
                 pesos["produccion"] * prod +
                 pesos["tendencia"]  * tr_n[i])
        else:
            s = (pesos["ip"]         * ip_n[i] +
                 pesos["tesis"]      * t_n[i] +
                 pesos["produccion"] * prod +
                 pesos["tendencia"]  * tr_n[i])

        # (1b) Recompensa al equilibrio: penaliza perfiles "incompletos" usando
        # entropía de Shannon normalizada sobre TODAS las dimensiones con peso>0
        # (n_active = 11 fijo para MdM/SO), incluyendo las que valen 0.
        # DISEÑO INTENCIONAL: un garante de excelencia debe ser fuerte en múltiples
        # frentes. Tener pocas dimensiones cubiertas penaliza aunque las cubiertas
        # estén bien repartidas — eso es un perfil incompleto, no equilibrado.
        # La cobertura de dimensiones es parte de la excelencia buscada.
        # H_norm=1 (fuerte en todo) → sin penalización; ceros reducen H_norm.
        # balance_factor = 1 − BALANCE_LAMBDA × (1 − H_norm)
        balance_factor = 1.0
        if cfg.BALANCE_LAMBDA > 0:
            relevant = [dim_vals[d] for d, wgt in pesos.items()
                        if wgt > 0 and d in dim_vals]
            n_active = len(relevant)
            if n_active >= 2:
                total_r = sum(relevant)
                if total_r > 0:
                    probs = [v / total_r for v in relevant]
                    H = -sum(p * math.log(p) for p in probs if p > 0)
                    H_max = math.log(n_active)
                    H_norm = H / H_max if H_max > 0 else 1.0
                    balance_factor = max(0.0, 1.0 - cfg.BALANCE_LAMBDA * (1.0 - H_norm))
        s = s * balance_factor

        scores.append(s)
        raw[i]["E_i"] = round(s, 4)
        raw[i]["balance_factor"] = round(balance_factor, 4)
        raw[i]["dims_norm"] = {
            "produccion": round(prod, 4),
            "ip": round(ip_n[i], 4),
            "tesis": round(t_n[i], 4),
            "tendencia": round(tr_n[i], 4),
            "eu": round(eu_n[i], 4),
            "intl": round(intl_n[i], 4),
            "reconocimiento": round(reco_n[i], 4),
            "i10": round(i10_n[i], 4),
            "impacto_art": round(iart_n[i], 4),
            "sexenios": round(sex_n[i], 4),
            "top_mundial": round(exc_n[i], 4),
        }

    return np.array(scores), raw


# ─────────────────────────────────────────────────────────────────────────────
# 3. COHESIÓN K_ij  (copublicaciones reales)
# ─────────────────────────────────────────────────────────────────────────────

def compute_K(raw, docs):
    """
    Construye la matriz de cohesión K (n×n) basada en copublicaciones reales.

    Usa colaboraciones.colaboradores[].id_investigador y publicaciones_conjuntas.
    Normaliza al percentil C_MAX_PERCENTILE de los pares con copubs > 0.

    Retorna: np.array shape (n, n), simétrica con diagonal 0.
    """
    n = len(raw)
    K = np.zeros((n, n))

    # Mapear id_investigador → índice en el pool
    id_to_idx = {}
    for i, r in enumerate(raw):
        inv_id = r.get("id_investigador")
        if inv_id is not None:
            id_to_idx[inv_id] = i

    # Construir matriz de copublicaciones
    copubs_raw = np.zeros((n, n))
    for i, doc in enumerate(docs):
        colabs = (doc.get("colaboraciones") or {}).get("colaboradores", [])
        for colab in colabs:
            colab_id = colab.get("id_investigador")
            if colab_id and colab_id in id_to_idx:
                j = id_to_idx[colab_id]
                if j != i:
                    pubs = colab.get("publicaciones_conjuntas", 0) or 0
                    copubs_raw[i][j] = max(copubs_raw[i][j], pubs)

    # Simetrizar (tomar el máximo de ambas direcciones)
    copubs_sym = np.maximum(copubs_raw, copubs_raw.T)

    # Normalizar al percentil configurado
    nonzero_vals = copubs_sym[copubs_sym > 0]
    if len(nonzero_vals) > 0:
        c_max = np.percentile(nonzero_vals, cfg.C_MAX_PERCENTILE)
        if c_max > 0:
            K = np.minimum(copubs_sym / c_max, 1.0)

    np.fill_diagonal(K, 0.0)
    return K


# ─────────────────────────────────────────────────────────────────────────────
# 4. SOLVER MIP  (Google OR-Tools / SCIP)
# ─────────────────────────────────────────────────────────────────────────────

def run_mip(raw, E, K, N, director_idx=None, min_areas=None, min_paridad=0.4,
            fixed_indices=None, modalidad="MdM", h_min=None, eu_min=None,
            alpha=None, beta=None,
            top_pct_max=None, top_pct_source="any"):
    """
    Resuelve:
      max Z = ALPHA * Σ E_i·x_i  +  BETA * Σ K_ij·y_ij

    Sujeto a:
      Σ x_i == N                              (tamano exacto)
      x[i] == 1 para i en fixed_indices       (miembros fijados)
      Σ x_i·(genero_i=='Mujer') >= ceil(p·N)  (paridad de genero)
      Σ z_a >= min_areas                      (diversidad de areas)
      y_ij <= x_i, y_ij <= x_j, y_ij >= x_i+x_j-1  (linealizacion)
      x_i, y_ij, z_a in {0, 1}
    """
    n = len(raw)

    # Prefiltrado por h-index minimo
    if h_min is None:
        h_min = cfg.H_MIN_SO if modalidad == "SO" else cfg.H_MIN_UEI if modalidad == "UEI" else cfg.H_MIN_MDM

    all_fixed = list(fixed_indices or [])
    if director_idx is not None and director_idx not in all_fixed:
        all_fixed.append(director_idx)

    def _meets_top_pct(r):
        """True si el investigador cumple el umbral de Top% elegido (o si no hay umbral)."""
        if top_pct_max is None:
            return True
        st_pct = r.get("stanford_percentil")
        oa_pct = r.get("openalex_pct")
        if top_pct_source == "stanford":
            return st_pct is not None and st_pct <= top_pct_max
        if top_pct_source == "oa":
            return oa_pct is not None and oa_pct <= top_pct_max
        # "any": basta con que cualquiera de los dos cumpla
        return (st_pct is not None and st_pct <= top_pct_max) or \
               (oa_pct is not None and oa_pct <= top_pct_max)

    def _meets_h(r):
        """h-index >= umbral, con gate blando: una tendencia ascendente puede
        recomprar hasta H_SOFT_GATE_BUYBACK puntos por debajo de h_min (item 2)."""
        if r["h_index"] >= h_min:
            return True
        if (cfg.H_SOFT_GATE_ENABLED
                and r.get("tendencia", 0) >= cfg.H_SOFT_GATE_TREND_MIN
                and r["h_index"] >= h_min - cfg.H_SOFT_GATE_BUYBACK):
            return True
        return False

    eligible = [i for i in range(n) if (_meets_h(raw[i]) and _meets_top_pct(raw[i])) or i in all_fixed]
    if len(eligible) < N:
        print(f"  [AVISO] Solo {len(eligible)} candidatos cumplen los filtros (h_min={h_min}, top_pct_max={top_pct_max}), "
              f"se necesitan {N}. Se amplía el pool a todos los {n} investigadores.")
        eligible = list(range(n))

    solver = pywraplp.Solver.CreateSolver("SCIP")
    if not solver:
        print("  OR-Tools SCIP no disponible.")
        return None, 0.0

    # Variables
    x = {i: solver.IntVar(0, 1, f"x_{i}") for i in eligible}
    # Sparse y-variables: only create for pairs with K > 0
    y = {}
    for idx_a, i in enumerate(eligible):
        for j in eligible[idx_a + 1:]:
            if K[i][j] > 0:
                y[i, j] = solver.IntVar(0, 1, f"y_{i}_{j}")

    for (i, j) in y:
        solver.Add(y[i, j] <= x[i])
        solver.Add(y[i, j] <= x[j])
        solver.Add(y[i, j] >= x[i] + x[j] - 1)

    # Restricciones
    solver.Add(solver.Sum([x[i] for i in eligible]) == N)

    for idx in all_fixed:
        if idx in x:
            solver.Add(x[idx] == 1)

    min_mujeres = math.ceil(min_paridad * N)
    es_mujer = {i: 1 if raw[i]["genero"] == "Mujer" else 0 for i in eligible}
    suma_mujeres = solver.Sum([x[i] * es_mujer[i] for i in eligible])
    solver.Add(suma_mujeres >= min_mujeres)
    # (5a) Banda de paridad: techo simétrico (≥ min_paridad hombres) para evitar
    # grupos monogénero. Solo si hay suficientes hombres elegibles para no forzar
    # infactibilidad cuando el pool está sesgado.
    if cfg.PARIDAD_BANDA:
        max_mujeres = N - math.ceil(min_paridad * N)
        n_hombres_elegibles = sum(1 - es_mujer[i] for i in eligible)
        # Las mujeres fijadas se seleccionan obligatoriamente; si superan el techo
        # de la banda, imponer el techo haría infactible el problema.
        fixed_women = sum(es_mujer.get(i, 0) for i in all_fixed)
        if (max_mujeres >= min_mujeres and max_mujeres >= fixed_women
                and n_hombres_elegibles >= (N - max_mujeres)):
            solver.Add(suma_mujeres <= max_mujeres)

    z_areas = {}
    if (min_areas and min_areas > 0) or cfg.AREA_DIVERSITY_BONUS > 0:
        areas = list(set(raw[i]["area"] for i in eligible if raw[i]["area"]))
        z_areas = {a: solver.IntVar(0, 1, f"z_{idx_a}") for idx_a, a in enumerate(areas)}
        for a in areas:
            indices_a = [i for i in eligible if raw[i]["area"] == a]
            if indices_a:
                solver.Add(z_areas[a] <= solver.Sum([x[i] for i in indices_a]))
        if min_areas and min_areas > 0:
            solver.Add(solver.Sum([z_areas[a] for a in areas]) >= min_areas)

    # NEW: minimum EU constraint
    if eu_min is None:
        eu_min = cfg.EU_MIN_SO if modalidad == "SO" else cfg.EU_MIN_UEI if modalidad == "UEI" else cfg.EU_MIN_MDM
    tiene_eu = {i: 1 if raw[i].get("proyectos_eu", 0) > 0 else 0 for i in eligible}
    n_eu_available = sum(tiene_eu[i] for i in eligible)
    if n_eu_available >= eu_min:
        solver.Add(solver.Sum([x[i] * tiene_eu[i] for i in eligible]) >= eu_min)

    # Función objetivo
    alpha = alpha if alpha is not None else cfg.ALPHA
    beta = beta if beta is not None else cfg.BETA
    total_ab = alpha + beta
    if total_ab > 0:
        alpha, beta = alpha / total_ab, beta / total_ab
    else:
        alpha, beta = 0.5, 0.5

    obj = solver.Objective()
    for i in eligible:
        coeff = alpha * float(E[i])
        if raw[i]["tendencia"] < 0:
            coeff -= cfg.PENALTY_DECLINING
        has_any_copub = any(K[i][j] > 0 for j in eligible if j != i)
        if not has_any_copub:
            coeff -= cfg.PENALTY_ISOLATED
        obj.SetCoefficient(x[i], coeff)

    for (i, j) in y:
        obj.SetCoefficient(y[i, j], beta * float(K[i][j]))

    # (5b) Bonus por diversidad de áreas: premia cubrir más áreas distintas.
    if cfg.AREA_DIVERSITY_BONUS > 0 and z_areas:
        for a, z in z_areas.items():
            obj.SetCoefficient(z, cfg.AREA_DIVERSITY_BONUS)

    obj.SetMaximization()

    status = solver.Solve()

    if status != pywraplp.Solver.OPTIMAL:
        if fixed_indices:
            return None, 0.0  # infeasible con nucleo fijado
        print("  El solver no encontro solucion optima. Verifica las restricciones.")
        return None, 0.0

    seleccionados = [i for i in eligible if x[i].solution_value() > 0.5]
    z_total       = solver.Objective().Value()
    return seleccionados, z_total


def compute_stability(raw, E, K, N, modalidad="MdM", n_runs=None, sigma=None,
                      director_idx=None, min_areas=None, min_paridad=0.4,
                      fixed_indices=None, h_min=None, eu_min=None,
                      alpha=None, beta=None, top_pct_max=None, top_pct_source="any",
                      seed=42):
    """
    (4) Análisis de estabilidad de la selección.

    Re-ejecuta el MIP n_runs veces con E_i perturbado por ruido gaussiano
    relativo (sigma) y mide con qué frecuencia se selecciona cada investigador.
    Distingue el núcleo robusto (aparece casi siempre) de los marginales
    (sensibles al peso exacto de las métricas).

    Retorna:
      freq        : dict idx -> frecuencia de selección en [0, 1]
      valid_runs  : nº de corridas que produjeron solución factible
    """
    import os
    import contextlib

    n_runs = n_runs if n_runs is not None else cfg.STABILITY_N_RUNS
    sigma = sigma if sigma is not None else cfg.STABILITY_SIGMA
    rng = np.random.default_rng(seed)
    E_arr = np.asarray(E, dtype=float)
    counts = {i: 0 for i in range(len(raw))}
    valid_runs = 0

    with open(os.devnull, "w") as _devnull, contextlib.redirect_stdout(_devnull):
        for _ in range(n_runs):
            noise = rng.normal(1.0, sigma, size=len(E_arr))
            E_pert = np.clip(E_arr * noise, 0.0, None)
            sel, _z = run_mip(
                raw, E_pert, K, N, director_idx=director_idx, min_areas=min_areas,
                min_paridad=min_paridad, fixed_indices=fixed_indices,
                modalidad=modalidad, h_min=h_min, eu_min=eu_min,
                alpha=alpha, beta=beta,
                top_pct_max=top_pct_max, top_pct_source=top_pct_source,
            )
            if sel:
                valid_runs += 1
                for i in sel:
                    counts[i] += 1

    freq = {i: counts[i] / valid_runs for i in counts} if valid_runs else {}
    return freq, valid_runs


# ─────────────────────────────────────────────────────────────────────────────
# 4b. DETECCION DE NUCLEOS DE COLABORACION
# ─────────────────────────────────────────────────────────────────────────────

def find_clusters(raw, docs, E, K, N, min_areas=None, min_paridad=0.4, max_clusters=5, modalidad="MdM", db_name=None):
    """
    Detecta nucleos de colaboracion y ejecuta el MIP para cada uno.

    1. Construye grafo de copublicaciones.
    2. Detecta comunidades con Louvain.
    3. Para cada comunidad (>=2 miembros), calcula potencial.
    4. Top max_clusters nucleos → ejecuta run_mip fijando el nucleo.
    5. Retorna lista de dicts con nucleo, seleccionados, z, diagnostico.
    """
    import networkx as nx
    from networkx.algorithms.community import louvain_communities

    n = len(raw)

    # Construir grafo
    G = nx.Graph()
    for i in range(n):
        G.add_node(i)
    for i in range(n):
        for j in range(i + 1, n):
            if K[i][j] > 0:
                G.add_edge(i, j, weight=float(K[i][j]))

    # Detectar comunidades
    try:
        communities = louvain_communities(G, weight='weight', seed=42)
    except Exception:
        communities = [set(G.nodes())]

    # Filtrar comunidades con >= 2 miembros conectados
    nucleos = []
    for comm in communities:
        members = sorted(comm)
        if len(members) < 2:
            continue
        # Solo miembros con al menos una conexion dentro de la comunidad
        connected = [i for i in members
                     if any(K[i][j] > 0 for j in members if j != i)]
        if len(connected) < 2:
            continue

        # Calcular potencial del nucleo (same formula as utils.compute_nucleo_potencial)
        e_mean = np.mean([E[i] for i in connected])
        k_pairs = [(i, j) for idx_i, i in enumerate(connected)
                   for j in connected[idx_i + 1:]]
        k_mean = np.mean([K[i][j] for i, j in k_pairs]) if k_pairs else 0.0
        potencial = cfg.ALPHA * e_mean + cfg.BETA * k_mean

        nucleos.append({
            "indices": connected,
            "nombres": [raw[i]["nombre_completo"] for i in connected],
            "e_mean": round(e_mean, 3),
            "k_mean": round(k_mean, 3),
            "potencial": round(potencial, 3),
            "areas": sorted(set(raw[i]["area"] for i in connected if raw[i]["area"])),
        })

    # Ordenar por potencial y limitar
    nucleos.sort(key=lambda x: -x["potencial"])
    nucleos = nucleos[:max_clusters]

    # Ejecutar MIP para cada nucleo
    resultados = []
    for nucleo in nucleos:
        fixed = nucleo["indices"]
        # Si el nucleo tiene mas miembros que N, recortar a los mejores
        if len(fixed) > N:
            fixed = sorted(fixed, key=lambda i: -E[i])[:N]

        sel, z = run_mip(raw, E, K, N, min_areas=min_areas,
                         min_paridad=min_paridad, fixed_indices=fixed,
                         modalidad=modalidad)
        if sel is None:
            continue  # infeasible con este nucleo

        diag = compute_diagnostico(sel, raw, K, N, modalidad=modalidad, db_name=db_name)
        resultados.append({
            "nucleo": nucleo,
            "seleccionados": sel,
            "z_total": z,
            "diagnostico": diag,
        })

    return resultados


# ─────────────────────────────────────────────────────────────────────────────
# 5. INFORME
# ─────────────────────────────────────────────────────────────────────────────

def print_report(seleccionados, raw, K, z_total, N, alpha, beta):
    """Imprime el informe en consola."""
    print("\n" + "=" * 72)
    print(f"  SUBGRAFO ÓPTIMO  (N={N}, α={alpha}, β={beta})   Z = {z_total:.4f}")
    print("=" * 72)

    mujeres = sum(1 for i in seleccionados if raw[i]["genero"] == "Mujer")
    areas   = set(raw[i]["area"] for i in seleccionados if raw[i]["area"])
    print(f"  Investigadores seleccionados : {len(seleccionados)}")
    print(f"  Mujeres                       : {mujeres} ({100*mujeres/len(seleccionados):.0f}%)")
    print(f"  Áreas distintas               : {len(areas)}")

    # Cohesión media del subgrafo
    pairs  = [(i, j) for idx_i, i in enumerate(seleccionados)
              for j in seleccionados[idx_i + 1:]]
    k_mean = np.mean([K[i][j] for i, j in pairs]) if pairs else 0.0
    print(f"  Cohesión media K_ij          : {k_mean:.3f}")
    print()
    print(f"  {'#':<3} {'Nombre':<35} {'Género':<8} {'Área':<25} {'E_i':>5} {'K_med':>5}")
    print(f"  {'-'*3} {'-'*35} {'-'*8} {'-'*25} {'-'*5} {'-'*5}")

    for rank, i in enumerate(seleccionados, 1):
        r = raw[i]
        k_med = np.mean([K[i][j] for j in seleccionados if j != i]) if len(seleccionados) > 1 else 0.0
        print(f"  {rank:<3} {r['nombre_completo'][:35]:<35} {r['genero'][:7]:<8} "
              f"{r['area'][:24]:<25} {r['E_i']:>5.3f} {k_med:>5.3f}")

    print("=" * 72)


def compute_diagnostico(seleccionados, raw, K, N, modalidad="MdM", db_name=None):
    """
    Calcula el diagnostico del subgrafo optimo.
    Retorna dict con fortalezas, debilidades, recomendaciones, valoracion, metricas.
    """
    sel_raw = [raw[i] for i in seleccionados]
    h_indices = [r["h_index"] for r in sel_raw]
    h_mean = np.mean(h_indices) if h_indices else 0
    h_max = max(h_indices) if h_indices else 0
    h_min = min(h_indices) if h_indices else 0

    pairs = [(i, j) for idx_i, i in enumerate(seleccionados)
             for j in seleccionados[idx_i + 1:]]
    k_values = [K[i][j] for i, j in pairs]
    k_mean = np.mean(k_values) if k_values else 0.0
    k_nonzero_pct = 100 * sum(1 for k in k_values if k > 0) / len(k_values) if k_values else 0

    areas = set(r["area"] for r in sel_raw if r["area"])
    mujeres = sum(1 for r in sel_raw if r["genero"] == "Mujer")
    mujeres_pct = 100 * mujeres / len(seleccionados) if seleccionados else 0
    e_mean = np.mean([r["E_i"] for r in sel_raw]) if sel_raw else 0
    tendencia_mean = np.mean([r["tendencia"] for r in sel_raw]) if sel_raw else 0
    # tendencia < 0 = declive real (independiente del método de cálculo)
    declinantes = [r["nombre_completo"] for r in sel_raw if r["tendencia"] < 0]
    _h_min_ref = cfg.H_MIN_SO if modalidad == "SO" else cfg.H_MIN_UEI if modalidad == "UEI" else cfg.H_MIN_MDM
    h_bajos = [(r["nombre_completo"], r["h_index"]) for r in sel_raw if r["h_index"] < _h_min_ref]

    aislados = []
    for i in seleccionados:
        k_con_grupo = [K[i][j] for j in seleccionados if j != i]
        if all(k == 0 for k in k_con_grupo):
            aislados.append(raw[i]["nombre_completo"])

    fortalezas = []
    debilidades = []
    recomendaciones = []

    # Excelencia (umbrales adaptados a modalidad)
    if modalidad == "SO":
        h_excelente, h_moderado = 25, 15
        label = "Severo Ochoa"
    elif modalidad == "UEI":
        h_excelente, h_moderado = 12, 6
        label = "Unidades de Excelencia (Junta Andalucia)"
    else:
        h_excelente, h_moderado = 15, 8
        label = "Maria de Maeztu"

    if h_mean >= h_excelente:
        fortalezas.append(f"h-index medio competitivo para {label}")
    elif h_mean >= h_moderado:
        debilidades.append(f"h-index medio ({h_mean:.0f}) moderado para {label}")
    else:
        debilidades.append(f"h-index medio ({h_mean:.0f}) bajo para {label} (referencia: >{h_excelente})")

    if declinantes:
        debilidades.append(f"{len(declinantes)} garantes con tendencia descendente")
    if h_bajos:
        debilidades.append(f"{len(h_bajos)} garantes con h-index < {_h_min_ref}")

    # Cohesion (informativo — no es criterio determinante en la convocatoria)
    if k_mean >= 0.3:
        fortalezas.append("Cohesion alta — el grupo tiene colaboraciones reales solidas")


    # Diversidad
    if len(areas) >= 5:
        fortalezas.append(f"Buena diversidad de areas ({len(areas)} distintas)")
    elif len(areas) >= 3:
        debilidades.append(f"Diversidad aceptable ({len(areas)} areas) pero mejorable")

    # Genero (no obligatorio, pero criterio de desempate entre candidaturas similares)
    if mujeres_pct >= 50:
        fortalezas.append("Excelente paridad de genero (criterio de desempate favorable)")
    elif mujeres_pct >= 40:
        fortalezas.append("Buena paridad de genero (criterio de desempate favorable)")

    # Proyectos europeos
    garantes_eu = sum(1 for r in sel_raw if r.get("proyectos_eu", 0) > 0)
    garantes_eu_ip = sum(1 for r in sel_raw if r.get("proyectos_eu_ip", 0) > 0)
    eu_min_ref = cfg.EU_MIN_SO if modalidad == "SO" else cfg.EU_MIN_UEI if modalidad == "UEI" else cfg.EU_MIN_MDM

    if garantes_eu >= eu_min_ref:
        fortalezas.append(f"{garantes_eu} garantes con proyectos europeos (ref: {eu_min_ref})")
    else:
        debilidades.append(f"Solo {garantes_eu} garantes con proyectos europeos (ref: {eu_min_ref})")

    if garantes_eu_ip >= 2:
        fortalezas.append(f"{garantes_eu_ip} garantes IP de proyectos europeos")

    # Internacionalizacion
    intl_mean = np.mean([r.get("instituciones_intl", 0) for r in sel_raw])
    if intl_mean >= 5:
        fortalezas.append(f"Buena internacionalizacion ({intl_mean:.0f} instituciones intl. de media)")
    elif intl_mean < 2:
        debilidades.append(f"Internacionalizacion limitada ({intl_mean:.0f} instituciones intl. de media)")

    # Recomendaciones
    if k_mean < 0.15 and k_mean > 0:
        recomendaciones.append({"prioridad": "BAJA", "texto": "Considerar publicar articulos conjuntos entre garantes (mejora cohesion pero no es criterio determinante)"})
    if h_mean < h_excelente:
        recomendaciones.append({"prioridad": "ALTA", "texto": f"Incorporar investigadores de alto impacto internacional (h>{h_excelente}) al instituto"})
    if h_bajos:
        recomendaciones.append({"prioridad": "MEDIA", "texto": f"Sustituir garantes con h<{_h_min_ref} por perfiles mas competitivos"})
    if declinantes:
        recomendaciones.append({"prioridad": "MEDIA", "texto": "Valorar sustituir garantes en declive por perfiles emergentes"})
    if garantes_eu < eu_min_ref:
        recomendaciones.append({"prioridad": "ALTA", "texto": f"Necesarios al menos {eu_min_ref} garantes con proyectos europeos para {label}"})
    if garantes_eu_ip == 0:
        if modalidad == "UEI":
            recomendaciones.append({"prioridad": "MEDIA", "texto": "Ningun garante es IP de proyecto europeo — importante para futuras candidaturas MdM/SO"})
        else:
            recomendaciones.append({"prioridad": "ALTA", "texto": "Ningun garante es IP de proyecto europeo — critico para SO/MdM"})

    # Recomendación de impacto basada en el perfil temático del instituto
    inst_info = cfg.get_instituto_info(db_name or cfg.DB_NAME)
    perfil = inst_info.get("perfil", "").lower()
    if "social" in perfil or "derecho" in perfil or "economía" in perfil or "psicología" in perfil:
        recomendaciones.append({"prioridad": "ALTA", "texto": "Argumentar impacto social y transferencia ademas de bibliometria"})
    elif "marina" in perfil or "océano" in perfil or "marino" in perfil:
        recomendaciones.append({"prioridad": "ALTA", "texto": "Argumentar impacto en economia azul, sostenibilidad y politicas oceanicas ademas de bibliometria"})
    if modalidad == "SO" and h_mean < 20:
        recomendaciones.append({"prioridad": "MEDIA", "texto": "Considerar Maria de Maeztu en lugar de Severo Ochoa"})

    # Valoracion (basada en criterios Fase 1 convocatoria: excelencia individual,
    # internacionalizacion y proyectos EU — cohesion no es criterio determinante)
    if modalidad == "SO":
        if h_mean >= 25 and len(areas) >= 4 and garantes_eu >= 4 and intl_mean >= 3:
            valoracion = "COMPETITIVO"
        elif h_mean >= 15 and garantes_eu >= 2:
            valoracion = "MEJORABLE"
        else:
            valoracion = "DIFICIL"
    elif modalidad == "UEI":
        if h_mean >= 12 and len(areas) >= 3 and garantes_eu >= 1 and intl_mean >= 2:
            valoracion = "COMPETITIVO"
        elif h_mean >= 6 and garantes_eu >= 1:
            valoracion = "MEJORABLE"
        else:
            valoracion = "DIFICIL"
    else:
        if h_mean >= 15 and len(areas) >= 3 and garantes_eu >= 2 and intl_mean >= 2:
            valoracion = "COMPETITIVO"
        elif h_mean >= 8 and garantes_eu >= 1:
            valoracion = "MEJORABLE"
        else:
            valoracion = "DIFICIL"

    if modalidad == "UEI":
        if valoracion == "COMPETITIVO":
            recomendaciones.append({"prioridad": "MEDIA", "texto": "Grupo competitivo para UEI — considerar preparar candidatura Maria de Maeztu a medio plazo"})
        if h_mean >= 15 and garantes_eu >= 2:
            recomendaciones.append({"prioridad": "ALTA", "texto": "Metricas compatibles con Maria de Maeztu — valorar solicitar MdM directamente"})

    return {
        "fortalezas": fortalezas,
        "debilidades": debilidades,
        "recomendaciones": recomendaciones,
        "valoracion": valoracion,
        "metricas": {
            "h_mean": round(h_mean, 1), "h_min": h_min, "h_max": h_max,
            "k_mean": round(k_mean, 3), "k_nonzero_pct": round(k_nonzero_pct, 0),
            "mujeres": mujeres, "mujeres_pct": round(mujeres_pct, 0),
            "areas": len(areas), "areas_list": sorted(areas),
            "e_mean": round(e_mean, 3), "tendencia_mean": round(tendencia_mean, 2),
            "declinantes": declinantes, "aislados": aislados,
            "garantes_eu": garantes_eu,
            "garantes_eu_ip": garantes_eu_ip,
            "intl_mean": round(intl_mean, 1),
            "modalidad": modalidad,
        }
    }


def print_diagnostico(seleccionados, raw, E, K, N, modalidad="MdM"):
    """Imprime el diagnostico en consola usando compute_diagnostico()."""
    diag = compute_diagnostico(seleccionados, raw, K, N, modalidad=modalidad)
    m = diag["metricas"]

    print("\n" + "=" * 72)
    print("  DIAGNOSTICO Y RECOMENDACIONES DE MEJORA")
    print("=" * 72)

    print(f"\n  EXCELENCIA: h-index medio {m['h_mean']} (rango {m['h_min']}-{m['h_max']}), E_i medio {m['e_mean']}")
    print(f"  COHESION: K medio {m['k_mean']}, pares con copubs {m['k_nonzero_pct']:.0f}%")
    print(f"  DIVERSIDAD: {m['areas']} areas ({', '.join(m['areas_list'])})")
    print(f"  GENERO: {m['mujeres_pct']:.0f}% mujeres")

    print(f"\n  Fortalezas:")
    for f in diag["fortalezas"]:
        print(f"     [+] {f}")

    print(f"\n  Debilidades:")
    for d in diag["debilidades"]:
        print(f"     [-] {d}")

    print(f"\n  Recomendaciones:")
    for i, rec in enumerate(diag["recomendaciones"], 1):
        print(f"     {i}. [{rec['prioridad']}] {rec['texto']}")

    print(f"\n  VALORACION: {diag['valoracion']}")
    print("=" * 72)

    return diag


def save_json(seleccionados, raw, K, z_total, N, out_path, diagnostico=None):
    """Guarda el resultado completo en JSON."""
    areas = list(set(raw[i]["area"] for i in seleccionados if raw[i]["area"]))
    resultado = {
        "fecha":        datetime.now().isoformat(timespec="seconds"),
        "convocatoria": "Severo Ochoa / María de Maeztu 2026",
        "N_solicitado": N,
        "Z_optimo":     round(z_total, 6),
        "alpha":        cfg.ALPHA,
        "beta":         cfg.BETA,
        "areas_representadas": sorted(areas),
        "garantes": [
            {
                **{k: raw[i][k] for k in
                   ["nombre_completo", "figura", "genero", "area", "grupo",
                    "h_index", "h_openalex", "h_dialnet", "citas_cruzadas",
                    "produccion_cvn", "proyectos_ip", "tesis_dir", "tendencia",
                    "calidad", "E_i"]},
                "K_medio_subgrafo": round(
                    float(np.mean([K[i][j] for j in seleccionados if j != i])), 4
                ) if len(seleccionados) > 1 else 0.0,
            }
            for i in seleccionados
        ],
    }
    if diagnostico:
        resultado["diagnostico"] = diagnostico
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f"\n  -> Resultado guardado en: {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# 6. MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="CASPER-3 — Optimizador MIP de garantes SO/MdM 2026 (v2)"
    )
    parser.add_argument("--n",         type=int,   required=True,
                        help="Número de garantes a seleccionar")
    parser.add_argument("--director",  type=str,   default=None,
                        help="Nombre completo del/la director/a científico/a")
    parser.add_argument("--sjr",       type=str,   default=None,
                        help="Ruta al fichero sjr_map.json (opcional)")
    parser.add_argument("--out",       type=str,   default="resultado_mip.json",
                        help="Ruta del JSON de salida")
    parser.add_argument("--alpha",     type=float, default=cfg.ALPHA,
                        help=f"Peso excelencia individual (default: {cfg.ALPHA})")
    parser.add_argument("--beta",      type=float, default=cfg.BETA,
                        help=f"Peso cohesión estructural (default: {cfg.BETA})")
    parser.add_argument("--min-areas", type=int,   default=None,
                        help="Mínimo de áreas distintas (default: 3 para N<=10, 4 para N>10)")
    parser.add_argument("--modalidad", type=str,   default="MdM", choices=["SO", "MdM", "UEI"],
                        help="Modalidad: SO (Severo Ochoa), MdM (María de Maeztu) o UEI (Unidades Excelencia Junta Andalucia)")
    args = parser.parse_args()

    cfg.ALPHA = args.alpha
    cfg.BETA  = args.beta

    min_areas = args.min_areas
    if min_areas is None:
        min_areas = cfg.MIN_AREAS_DEFAULT if args.n <= 10 else cfg.MIN_AREAS_LARGE

    # Cargar SJR map (opcional)
    sjr_map = None
    if args.sjr:
        print(f"[0/4] Cargando SJR map desde {args.sjr}...", end=" ", flush=True)
        with open(args.sjr, encoding="utf-8") as f:
            sjr_map = json.load(f)
        print(f"{len(sjr_map)} revistas.")

    # Pipeline
    docs = load_investigators()

    if len(docs) < args.n:
        print(f"  Solo hay {len(docs)} investigadores elegibles; no se puede seleccionar {args.n}.")
        sys.exit(1)

    print(f"[2/4] Calculando scores E_i (OpenAlex + Dialnet, modalidad={args.modalidad})...", end=" ", flush=True)
    E, raw = compute_E(docs, sjr_map, modalidad=args.modalidad)
    print("OK")

    # Prefiltrado: limitar a top candidatos por E_i para que el solver sea tratable
    MAX_CANDIDATES = min(len(raw), max(5 * args.n, 50))
    if len(raw) > MAX_CANDIDATES:
        top_idx = np.argsort(E)[::-1][:MAX_CANDIDATES].tolist()
        # Si hay director, asegurar que esté incluido
        if args.director:
            nombres = [r["nombre_completo"] for r in raw]
            dir_matches = [i for i, nm in enumerate(nombres)
                          if args.director.lower() in nm.lower()]
            if dir_matches and dir_matches[0] not in top_idx:
                top_idx[-1] = dir_matches[0]
        # Filtrar docs también para compute_K
        docs_filtered = [docs[i] for i in top_idx]
        raw = [raw[i] for i in top_idx]
        E = np.array([E[i] for i in top_idx])
        print(f"     Prefiltrado: {MAX_CANDIDATES} mejores candidatos.")
    else:
        docs_filtered = docs

    print(f"[3/4] Construyendo matriz de cohesión K ({len(raw)}x{len(raw)}, copublicaciones)...", end=" ", flush=True)
    K = compute_K(raw, docs_filtered)
    k_nonzero = int(np.sum(K > 0)) // 2
    print(f"OK  ({k_nonzero} pares con K>0)")

    # Resolver índice del director
    director_idx = None
    if args.director:
        nombres = [r["nombre_completo"] for r in raw]
        matches = [i for i, nm in enumerate(nombres)
                   if args.director.lower() in nm.lower()]
        if not matches:
            print(f"  Director/a '{args.director}' no encontrado.")
            sys.exit(1)
        director_idx = matches[0]
        print(f"     Director/a fijado: {raw[director_idx]['nombre_completo']}")

    print(f"[4/4] Ejecutando solver MIP (N={args.n}, α={cfg.ALPHA}, β={cfg.BETA}, min_areas={min_areas})...", end=" ", flush=True)
    seleccionados, z_total = run_mip(raw, E, K, args.n, director_idx, min_areas,
                                     modalidad=args.modalidad)
    if seleccionados is None:
        print("INFACTIBLE — no se encontró solución con estos parámetros.")
        sys.exit(1)
    print(f"ÓPTIMO  (Z={z_total:.4f})")

    print_report(seleccionados, raw, K, z_total, args.n, cfg.ALPHA, cfg.BETA)
    diagnostico = print_diagnostico(seleccionados, raw, E, K, args.n, modalidad=args.modalidad)
    save_json(seleccionados, raw, K, z_total, args.n, args.out, diagnostico)


def diagnosticar_casi_garantes(raw, E, seleccionados, stored_params, m=6):
    """
    Diagnóstico de los M mejores candidatos NO seleccionados ("casi-garantes").

    Para cada uno determina por qué no entró en la selección de garantes,
    usando los umbrales de la modalidad activa (stored_params). Función pura:
    no depende de Streamlit ni de la red.

    Args:
        raw: lista de candidatos (con E_i, dims_norm, h_index, tendencia, etc.)
        E: np.ndarray de E_i (mismo orden que raw)
        seleccionados: lista de índices seleccionados por el MIP
        stored_params: dict con modalidad, h_min, eu_min, top_pct_max, top_pct_source
        m: número de casi-garantes a devolver

    Returns:
        lista de dicts ordenada por E_i desc:
        {idx, nombre, area, E_i, h_index, tendencia, proyectos_eu,
         debilidades: [str], accion: str}
    """
    sel_set = set(seleccionados)
    h_min = stored_params.get("h_min", cfg.H_MIN_MDM)
    eu_min = stored_params.get("eu_min", 0)
    top_pct_max = stored_params.get("top_pct_max")
    top_pct_source = stored_params.get("top_pct_source", "any")

    # Áreas ya cubiertas por seleccionados (con su E_i para comparar)
    areas_cubiertas = set(raw[i].get("area", "") for i in seleccionados if raw[i].get("area"))

    # Ranking de no seleccionados por E_i desc, top m por género
    no_sel = [i for i in range(len(raw)) if i not in sel_set]
    no_sel.sort(key=lambda i: -E[i])
    hombres = [i for i in no_sel if raw[i].get("genero", "").lower() not in ("mujer", "f", "female")]
    mujeres = [i for i in no_sel if raw[i].get("genero", "").lower() in ("mujer", "f", "female")]
    casi = sorted(set(hombres[:m] + mujeres[:m]), key=lambda i: -E[i])

    # Etiquetas legibles por dimensión E_i floja
    _dim_label = {
        "produccion": "producción científica", "ip": "liderazgo de proyectos (IP)",
        "tesis": "dirección de tesis", "tendencia": "tendencia de producción",
        "eu": "proyectos europeos", "intl": "colaboración internacional",
        "reconocimiento": "reconocimiento (premios/membresías)", "i10": "índice i10",
        "impacto_art": "impacto de artículos", "sexenios": "sexenios",
    }

    def _meets_h(r):
        h = r.get("h_index", 0)
        if h >= h_min:
            return True
        if (cfg.H_SOFT_GATE_ENABLED and h >= h_min - cfg.H_SOFT_GATE_BUYBACK
                and r.get("tendencia", 0) >= cfg.H_SOFT_GATE_TREND_MIN):
            return True
        return False

    def _pct_val(r):
        if top_pct_source == "stanford":
            return r.get("stanford_percentil")
        if top_pct_source == "oa":
            return r.get("openalex_pct")
        # any
        vals = [v for v in (r.get("stanford_percentil"), r.get("openalex_pct")) if v is not None]
        return min(vals) if vals else None

    out = []
    for i in casi:
        r = raw[i]
        debilidades = []

        # 1. h por debajo del mínimo (soft-gate fallido)
        if not _meets_h(r):
            debilidades.append(f"h-index = {r.get('h_index', 0):.0f} (mínimo {h_min:.0f})")

        # 2. sin proyecto europeo cuando hay cuota EU
        if eu_min > 0 and r.get("proyectos_eu", 0) == 0:
            debilidades.append("sin proyecto europeo")

        # 3. tendencia decreciente
        if r.get("tendencia", 0) < 0:
            debilidades.append("producción en descenso")

        # 4. fuera del top-percentil (si hay filtro activo)
        if top_pct_max is not None:
            pv = _pct_val(r)
            if pv is None or pv > top_pct_max:
                debilidades.append(f"fuera del top {top_pct_max:.0f}% mundial")

        # 5. área ya cubierta por seleccionados de mayor E_i
        area = r.get("area", "")
        if area and area in areas_cubiertas:
            debilidades.append(f"área «{area}» ya cubierta")

        # 6. si pasa los gates y no hay otra debilidad: desplazado por ranking →
        #    señalar dimensión E_i más floja
        if not debilidades:
            dims = r.get("dims_norm", {})
            if dims:
                dmin = min(dims, key=lambda k: dims[k])
                debilidades.append(f"competitivo; reforzar {_dim_label.get(dmin, dmin)}")
            else:
                debilidades.append("desplazado por ranking (E_i por debajo del corte)")

        # Acción accionable (basada en la dimensión más floja)
        dims = r.get("dims_norm", {})
        if dims:
            dmin = min(dims, key=lambda k: dims[k])
            accion = f"Desarrollar: {_dim_label.get(dmin, dmin)}"
        else:
            accion = "Reforzar perfil de excelencia individual"

        out.append({
            "idx": i,
            "nombre": r.get("nombre_completo", ""),
            "area": area,
            "E_i": float(E[i]),
            "h_index": r.get("h_index", 0),
            "tendencia": r.get("tendencia", 0),
            "proyectos_eu": r.get("proyectos_eu", 0),
            "debilidades": debilidades,
            "accion": accion,
        })
    return out


if __name__ == "__main__":
    main()
