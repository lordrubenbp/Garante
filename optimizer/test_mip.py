#!/usr/bin/env python3
"""
Tests del optimizador MIP con datos mock (sin MongoDB).
Ejecutar: python -m pytest test_mip.py -v   o   python test_mip.py
"""
import sys
import math
import os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

# Evitar que config.py falle por MONGO_URI ausente durante tests
os.environ.setdefault("MONGO_URI", "mongodb://test:test@localhost:27017/")

import config as cfg
from mip_garantes import compute_E, compute_K, run_mip, compute_diagnostico, find_clusters, compute_stability, diagnosticar_casi_garantes


# ─── Mock docs (simulan documentos MongoDB) ─────────────────────────────────
# Cada doc necesita: nombre_completo, figura, genero, area.nombre,
# grupo_investigacion.nombre, financiaciones, tesis, openalex (con h_index y
# counts_by_year), publicaciones, colaboraciones (con colaboradores[].id_investigador
# y publicaciones_conjuntas).

def _make_doc(idx, nombre, figura, genero, area, grupo, h_index, ip, tesis,
              citas_by_year, copubs=None, eu_financiador=None, intl_institutions=None,
              patentes=0, distinciones=0, membresias=0,
              gs_h_index=None, gs_i10=None, gs_citas_por_anio=None,
              ss_h_index=None, ss_encontrado=False,
              citas_crossref=0,
              journal_cuartiles=None, art_citas=None,
              sexenios=0, fecha_ultimo_sexenio=""):
    """Helper para crear un doc mock."""
    # Google Scholar data
    google_scholar = None
    if gs_h_index is not None:
        google_scholar = {
            "h_index": gs_h_index,
            "i10_index": gs_i10 or 0,
            "citas_por_anio": gs_citas_por_anio or {},
        }

    # Semantic Scholar data
    semantic_scholar = {"encontrado": ss_encontrado}
    if ss_encontrado and ss_h_index is not None:
        semantic_scholar["h_index"] = ss_h_index

    # Metricas unificadas
    metricas_unificadas = {
        "citas_totales": {
            "openalex": sum(y.get("cited_by_count", 0) for y in citas_by_year),
            "crossref": citas_crossref,
        },
    }
    if ss_encontrado and ss_h_index is not None:
        metricas_unificadas["citas_totales"]["semantic_scholar"] = 0

    # Build financiaciones items (anualidad dentro del período de referencia)
    fin_items = [{"responsable": True, "nombre": "", "financiador": "", "convocatoria": "", "programa": "", "anualidad": 2022}] * ip + \
                [{"responsable": False, "nombre": "", "financiador": "", "convocatoria": "", "programa": "", "anualidad": 2022}]
    if eu_financiador:
        for ef in eu_financiador:
            fin_items.append({"responsable": ef.get("responsable", False),
                              "nombre": ef.get("nombre", ""),
                              "financiador": ef.get("financiador", "UNIÓN EUROPEA"),
                              "convocatoria": "", "programa": "",
                              "anualidad": ef.get("anualidad", 2023)})

    # Build instituciones
    inst_list = []
    if intl_institutions:
        for inst in intl_institutions:
            inst_list.append({"nombre": inst, "pais": "International"})

    # Publicaciones con journal/cuartil y citas Crossref (anualidad 2022)
    pub_items = []
    if journal_cuartiles:
        for idx_q, q in enumerate(journal_cuartiles):
            item = {"tipo": "articulo", "anualidad": 2022, "journal": {"cuartil": q}}
            if art_citas and idx_q < len(art_citas):
                item["crossref"] = {"citas_crossref": art_citas[idx_q], "encontrado": True}
            pub_items.append(item)
    elif art_citas:
        for c in art_citas:
            pub_items.append({"tipo": "articulo", "anualidad": 2022,
                              "crossref": {"citas_crossref": c, "encontrado": True}})

    doc = {
        "nombre_completo": nombre,
        "figura": figura,
        "genero": genero,
        "id_investigador": f"mock_id_{idx}",
        "area": {"nombre": area},
        "grupo_investigacion": {"nombre": grupo},
        "financiaciones": {
            "total": len(fin_items),
            "items": fin_items,
        },
        "tesis": {
            "doctoral": {"titulo": f"Tesis {idx}", "anualidad": 2000},
            "dirigidas": [{"anualidad": 2022}] * tesis,
        },
        "openalex": {
            "h_index": h_index,
            "counts_by_year": citas_by_year,
        },
        "dialnet_metricas": {},
        "publicaciones": {"items": pub_items},
        "colaboraciones": {
            "colaboradores": copubs or [],
            "instituciones": inst_list,
        },
        "patentes": {"total": patentes, "items": []},
        "orcid_record": {"distinciones": distinciones, "membresias": membresias},
        "google_scholar": google_scholar,
        "semantic_scholar": semantic_scholar,
        "metricas_unificadas": metricas_unificadas,
        "sexenios": sexenios,
        "fecha_ultimo_sexenio": fecha_ultimo_sexenio,
    }
    return doc


# id_investigador values for cross-referencing copublications
MOCK_IDS = [f"mock_id_{i}" for i in range(12)]

MOCK_DOCS = [
    # 0: Ana, Catedratica, Medicina, copubs con 1 y 2
    _make_doc(0, "Ana Martinez Lopez", "Catedratica de Universidad", "Mujer",
              "Medicina", "CTS-001", 22, 3, 4,
              [{"year": 2023, "cited_by_count": 300, "works_count": 6},
               {"year": 2022, "cited_by_count": 250, "works_count": 5}],
              copubs=[
                  {"id_investigador": MOCK_IDS[1], "publicaciones_conjuntas": 5},
                  {"id_investigador": MOCK_IDS[2], "publicaciones_conjuntas": 3},
              ],
              eu_financiador=[{"responsable": True, "nombre": "H2020 project", "financiador": "UNIÓN EUROPEA"}],
              intl_institutions=["MIT", "Oxford", "ETH Zurich"],
              patentes=1,
              gs_h_index=24, gs_i10=38, gs_citas_por_anio={"2021": 200, "2022": 250, "2023": 300, "2024": 280, "2025": 320},
              ss_h_index=20, ss_encontrado=True, citas_crossref=1500,
              journal_cuartiles=["Q1","Q1","Q1","Q2","Q2","Q1"],
              art_citas=[25, 18, 30, 12, 8, 22],
              sexenios=4, fecha_ultimo_sexenio="01/01/2024"),
    # 1: Carlos, Titular, Medicina, copubs con 0
    _make_doc(1, "Carlos Ruiz Perez", "Profesor Titular de Universidad", "Hombre",
              "Medicina", "CTS-001", 14, 2, 2,
              [{"year": 2023, "cited_by_count": 120, "works_count": 4}],
              copubs=[
                  {"id_investigador": MOCK_IDS[0], "publicaciones_conjuntas": 5},
              ],
              gs_h_index=16, gs_i10=12, gs_citas_por_anio={"2021": 80, "2022": 90, "2023": 120, "2024": 110, "2025": 130},
              ss_h_index=12, ss_encontrado=True, citas_crossref=600),
    # 2: Laura, Titular, Medicina, copubs con 0
    _make_doc(2, "Laura Sanchez Gil", "Profesora Titular de Universidad", "Mujer",
              "Medicina", "CTS-001", 10, 1, 1,
              [{"year": 2024, "cited_by_count": 80, "works_count": 3}],
              copubs=[
                  {"id_investigador": MOCK_IDS[0], "publicaciones_conjuntas": 3},
              ]),
    # 3: Pedro, Catedratico, Enfermeria, copubs con 4
    _make_doc(3, "Pedro Gomez Vera", "Catedratico de Universidad", "Hombre",
              "Enfermeria", "CTS-002", 18, 2, 3,
              [{"year": 2023, "cited_by_count": 200, "works_count": 5}],
              copubs=[
                  {"id_investigador": MOCK_IDS[4], "publicaciones_conjuntas": 8},
              ],
              eu_financiador=[{"responsable": False, "nombre": "Erasmus+ project", "financiador": "UNIÓN EUROPEA"}],
              intl_institutions=["Sorbonne"],
              gs_h_index=20, gs_i10=25, gs_citas_por_anio={"2021": 150, "2022": 170, "2023": 200, "2024": 190, "2025": 210},
              ss_h_index=16, ss_encontrado=True, citas_crossref=900,
              sexenios=3, fecha_ultimo_sexenio="01/06/2022"),
    # 4: Maria, Contratada Doctora, Enfermeria, copubs con 3
    _make_doc(4, "Maria Torres Blanco", "Profesora Contratada Doctora", "Mujer",
              "Enfermeria", "CTS-002", 7, 1, 0,
              [{"year": 2023, "cited_by_count": 60, "works_count": 3}],
              copubs=[
                  {"id_investigador": MOCK_IDS[3], "publicaciones_conjuntas": 8},
              ]),
    # 5: Jorge, Titular, Fisioterapia, copubs con 6
    _make_doc(5, "Jorge Fernandez Cruz", "Profesor Titular de Universidad", "Hombre",
              "Fisioterapia", "CTS-003", 12, 2, 2,
              [{"year": 2023, "cited_by_count": 90, "works_count": 4}],
              copubs=[
                  {"id_investigador": MOCK_IDS[6], "publicaciones_conjuntas": 4},
              ]),
    # 6: Isabel, Titular, Fisioterapia, copubs con 5
    _make_doc(6, "Isabel Navarro Reyes", "Profesora Titular de Universidad", "Mujer",
              "Fisioterapia", "CTS-003", 9, 1, 1,
              [{"year": 2023, "cited_by_count": 50, "works_count": 2}],
              copubs=[
                  {"id_investigador": MOCK_IDS[5], "publicaciones_conjuntas": 4},
              ]),
    # 7: Sofia, Ramon y Cajal, Medicina, sin copubs
    _make_doc(7, "Sofia Delgado Mora", "Investigadora Posdoctoral Ramon y Cajal", "Mujer",
              "Medicina", "CTS-001", 6, 1, 0,
              [{"year": 2024, "cited_by_count": 120, "works_count": 5},
               {"year": 2020, "cited_by_count": 10, "works_count": 2}],
              gs_h_index=8, gs_i10=3, gs_citas_por_anio={"2021": 5, "2022": 15, "2023": 40, "2024": 80, "2025": 120},
              ss_h_index=5, ss_encontrado=True, citas_crossref=200),
    # 8: Manuel, Catedratico, Farmacia, copubs con 9
    _make_doc(8, "Manuel Ortega Prieto", "Catedratico de Universidad", "Hombre",
              "Farmacia", "CTS-004", 25, 3, 5,
              [{"year": 2023, "cited_by_count": 400, "works_count": 8}],
              copubs=[
                  {"id_investigador": MOCK_IDS[9], "publicaciones_conjuntas": 10},
              ],
              eu_financiador=[
                  {"responsable": True, "nombre": "ERC Consolidator", "financiador": "UNIÓN EUROPEA"},
                  {"responsable": False, "nombre": "COST Action", "financiador": "UNIÓN EUROPEA"},
              ],
              intl_institutions=["Harvard", "Max Planck", "Cambridge", "CNRS"],
              distinciones=2, membresias=1,
              gs_h_index=28, gs_i10=45, gs_citas_por_anio={"2021": 300, "2022": 350, "2023": 400, "2024": 380, "2025": 420},
              ss_h_index=23, ss_encontrado=True, citas_crossref=2500,
              journal_cuartiles=["Q1","Q1","Q1","Q1","Q2","Q1","Q1","Q2"],
              art_citas=[40, 35, 50, 28, 15, 45, 32, 20],
              sexenios=5, fecha_ultimo_sexenio="15/03/2025"),
    # 9: Elena, Titular, Farmacia, copubs con 8
    _make_doc(9, "Elena Romero Diaz", "Profesora Titular de Universidad", "Mujer",
              "Farmacia", "CTS-004", 8, 0, 1,
              [{"year": 2023, "cited_by_count": 40, "works_count": 2}],
              copubs=[
                  {"id_investigador": MOCK_IDS[8], "publicaciones_conjuntas": 10},
              ]),
    # 10: David, Ayudante Doctor, Psicologia, sin copubs
    _make_doc(10, "David Herrera Campos", "Profesor Ayudante Doctor", "Hombre",
              "Psicologia", "CTS-005", 2, 0, 0,
              [{"year": 2023, "cited_by_count": 5, "works_count": 1},
               {"year": 2021, "cited_by_count": 8, "works_count": 1},
               {"year": 2020, "cited_by_count": 6, "works_count": 1}]),
    # 11: Carmen, Titular, Psicologia, sin copubs
    _make_doc(11, "Carmen Iglesias Fuentes", "Profesora Titular de Universidad", "Mujer",
              "Psicologia", "CTS-005", 11, 1, 2,
              [{"year": 2023, "cited_by_count": 70, "works_count": 3}],
              gs_h_index=13, gs_i10=8, gs_citas_por_anio={"2021": 50, "2022": 55, "2023": 70, "2024": 65, "2025": 75},
              citas_crossref=400,
              sexenios=2, fecha_ultimo_sexenio="01/01/2018"),
]


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_compute_E():
    """E_i se calcula y normaliza correctamente."""
    E, raw = compute_E(MOCK_DOCS)
    assert len(E) == len(MOCK_DOCS)
    assert all(e >= 0.0 for e in E), f"E_i negativo: {E}"
    # i=8 (Manuel, h=25, IP=3, tesis=5) debe ser el mas alto
    assert np.argmax(E) == 8, f"Max E_i esperado en i=8, es i={np.argmax(E)}"
    # i=10 (David, h=2, IP=0, tesis=0) debe ser el mas bajo
    assert np.argmin(E) == 10, f"Min E_i esperado en i=10, es i={np.argmin(E)}"
    print("test_compute_E ... OK")
    return E, raw


def test_compute_K(raw):
    """K se construye con copublicaciones reales."""
    K = compute_K(raw, MOCK_DOCS)
    n = len(MOCK_DOCS)
    assert K.shape == (n, n)
    assert np.all(K == K.T), "K no es simetrica"
    assert np.all(np.diag(K) == 0), "Diagonal no es 0"
    assert np.all((K >= 0) & (K <= 1)), "K fuera de [0,1]"

    # Pares con copubs deben tener K > 0
    assert K[0][1] > 0, f"K[0,1] deberia ser >0 (5 copubs), es {K[0][1]}"
    assert K[3][4] > 0, f"K[3,4] deberia ser >0 (8 copubs), es {K[3][4]}"
    assert K[8][9] > 0, f"K[8,9] deberia ser >0 (10 copubs), es {K[8][9]}"

    # Pares sin copubs deben ser 0
    assert K[0][10] == 0, f"K[0,10] deberia ser 0, es {K[0][10]}"
    assert K[7][10] == 0, f"K[7,10] deberia ser 0, es {K[7][10]}"

    # K[8,9] debe ser >= K[0,1] (10 copubs >= 5 copubs)
    assert K[8][9] >= K[0][1], "K[8,9] deberia ser >= K[0,1]"

    nonzero = int(np.sum(K > 0)) // 2
    print(f"test_compute_K ... OK ({nonzero} pares con K>0)")
    return K


def test_run_mip_n6(raw, E, K):
    """MIP selecciona N=6 con paridad >= 40%."""
    sel, z = run_mip(raw, E, K, N=6)
    assert len(sel) == 6
    mujeres = sum(1 for i in sel if raw[i]["genero"] == "Mujer")
    assert mujeres >= math.ceil(0.4 * 6), f"Necesitan >={math.ceil(0.4*6)} mujeres, hay {mujeres}"
    assert z > 0
    print(f"test_run_mip_n6 ... OK (Z={z:.4f}, mujeres={mujeres}/6)")
    return sel


def test_run_mip_director(raw, E, K):
    """Director fijado debe aparecer en la solucion."""
    sel, z = run_mip(raw, E, K, N=6, director_idx=8)
    assert 8 in sel, f"Director (i=8) no esta en la seleccion: {sel}"
    print("test_run_mip_director ... OK")


def test_run_mip_paridad(raw, E, K):
    """Paridad personalizada funciona."""
    sel, z = run_mip(raw, E, K, N=6, min_paridad=0.5)
    mujeres = sum(1 for i in sel if raw[i]["genero"] == "Mujer")
    assert mujeres >= math.ceil(0.5 * 6), f"Necesitan >={math.ceil(0.5*6)} mujeres, hay {mujeres}"
    print(f"test_run_mip_paridad ... OK ({mujeres}/6 mujeres con 50%)")


def test_compute_diagnostico(sel, raw, K):
    """compute_diagnostico devuelve estructura correcta."""
    diag = compute_diagnostico(sel, raw, K, 6)
    assert "fortalezas" in diag
    assert "debilidades" in diag
    assert "recomendaciones" in diag
    assert "valoracion" in diag
    assert diag["valoracion"] in ("COMPETITIVO", "MEJORABLE", "DIFICIL")
    assert "metricas" in diag
    m = diag["metricas"]
    assert "h_mean" in m and "k_mean" in m and "mujeres" in m and "areas" in m
    print(f"test_compute_diagnostico ... OK (valoracion: {diag['valoracion']})")


def test_gender_constraint_ceil():
    """math.ceil se usa correctamente para paridad."""
    assert math.ceil(0.4 * 8) == 4
    assert math.ceil(0.4 * 6) == 3
    assert math.ceil(0.4 * 10) == 4
    print("test_gender_constraint_ceil ... OK")


def test_run_mip_fixed_indices(raw, E, K):
    """fixed_indices fija multiples miembros en la solucion."""
    fixed = [0, 1]  # Ana y Carlos
    sel, z = run_mip(raw, E, K, N=6, fixed_indices=fixed)
    assert 0 in sel, f"Fixed i=0 no esta en la seleccion: {sel}"
    assert 1 in sel, f"Fixed i=1 no esta en la seleccion: {sel}"
    assert len(sel) == 6
    print("test_run_mip_fixed_indices ... OK")


def test_find_clusters(raw, E, K):
    """find_clusters detecta nucleos y ejecuta MIP."""
    resultados = find_clusters(raw, MOCK_DOCS, E, K, N=6, min_areas=2, max_clusters=3)
    assert isinstance(resultados, list)
    # Deberia encontrar al menos 1 nucleo (hay copubs en los datos)
    assert len(resultados) >= 1, f"Se esperaba al menos 1 nucleo, hay {len(resultados)}"
    for r in resultados:
        assert "nucleo" in r
        assert "seleccionados" in r
        assert "diagnostico" in r
        assert len(r["seleccionados"]) == 6
        assert len(r["nucleo"]["indices"]) >= 2
    print(f"test_find_clusters ... OK ({len(resultados)} nucleos encontrados)")


def test_compute_E_modalidad():
    """E_i scores differ between SO and MdM modalidades."""
    E_mdm, raw_mdm = compute_E(MOCK_DOCS, modalidad="MdM")
    E_so, raw_so = compute_E(MOCK_DOCS, modalidad="SO")

    assert len(E_mdm) == len(MOCK_DOCS)
    assert len(E_so) == len(MOCK_DOCS)
    assert all(e >= 0.0 for e in E_mdm)
    assert all(e >= 0.0 for e in E_so)

    # Scores should differ (different weights)
    assert not np.allclose(E_mdm, E_so), "SO and MdM scores should differ"

    # New raw fields should be present
    assert "proyectos_eu" in raw_mdm[0]
    assert "instituciones_intl" in raw_mdm[0]
    assert "reconocimiento" in raw_mdm[0]
    assert raw_mdm[0]["proyectos_eu"] >= 1  # Ana has 1 EU project
    assert raw_mdm[8]["proyectos_eu"] >= 2  # Manuel has 2 EU projects

    print("test_compute_E_modalidad ... OK")


def test_compute_E_modalidad_uei():
    """UEI E_i scores use PESOS_UEI weights and differ from MdM."""
    E_uei, raw_uei = compute_E(MOCK_DOCS, modalidad="UEI")
    E_mdm, raw_mdm = compute_E(MOCK_DOCS, modalidad="MdM")
    assert len(E_uei) == len(E_mdm)
    assert any(abs(e1 - e2) > 1e-6 for e1, e2 in zip(E_uei, E_mdm)), \
        "UEI and MdM should produce different E_i scores"
    assert all(e >= 0 for e in E_uei), "E_i no debe ser negativo"
    print("test_compute_E_modalidad_uei ... OK")


def test_run_mip_uei(raw, E, K):
    """MIP solver works with UEI modalidad and its lower thresholds."""
    sel, z = run_mip(raw, E, K, N=5, modalidad="UEI")
    assert len(sel) == 5, f"Expected 5 selected, got {len(sel)}"
    print(f"test_run_mip_uei ... OK (selected {len(sel)})")


def test_compute_diagnostico_uei(sel, raw, K):
    """Diagnostico works with UEI modalidad and uses UEI thresholds."""
    diag = compute_diagnostico(sel, raw, K, len(sel), modalidad="UEI")
    assert diag["metricas"]["modalidad"] == "UEI"
    assert diag["valoracion"] in ("COMPETITIVO", "MEJORABLE", "DIFICIL")
    assert any("Excelencia" in f or "Unidades" in f or "h-index" in f
               for f in diag["fortalezas"] + diag["debilidades"]), \
        "Diagnostico should mention h-index quality"
    print(f"test_compute_diagnostico_uei ... OK (valoracion: {diag['valoracion']})")


def test_pesos_uei_sum():
    """PESOS_UEI and PESOS_NUCLEO_UEI must sum to 1.0."""
    import config as cfg
    assert abs(sum(cfg.PESOS_UEI.values()) - 1.0) < 1e-9, \
        f"PESOS_UEI sums to {sum(cfg.PESOS_UEI.values())}"
    assert abs(sum(cfg.PESOS_NUCLEO_UEI.values()) - 1.0) < 1e-9, \
        f"PESOS_NUCLEO_UEI sums to {sum(cfg.PESOS_NUCLEO_UEI.values())}"
    print("test_pesos_uei_sum ... OK")


def test_h_consolidado():
    """H-index usa OpenAlex como fuente canónica."""
    E, raw = compute_E(MOCK_DOCS)
    # Ana (doc 0): OA=22, GS=24 → usa OA
    ana = raw[0]
    assert ana["h_index"] == 22, f"Ana h should be 22 (OA), got {ana['h_index']}"

    # David (doc 10): sin GS → OA (h=2)
    david = raw[10]
    assert david["h_google_scholar"] is None
    assert david["h_index"] == 2, f"David h should be 2 (OA), got {david['h_index']}"

    print("test_h_consolidado ... OK")


def test_tendencia_regresion():
    """Tendencia usa regresión GS cuando disponible, fallback OA."""
    E, raw = compute_E(MOCK_DOCS)
    # Sofia (doc 7): GS citas crecientes 5→15→40→80→120 — tendencia alta
    sofia = raw[7]
    assert sofia["tendencia_metodo"] == "gs_regresion"
    assert sofia["tendencia"] > 0, f"Sofia should have positive trend, got {sofia['tendencia']}"

    # David (doc 10): sin GS → fallback oa_ratio
    david = raw[10]
    assert david["tendencia_metodo"] == "oa_ratio"

    print("test_tendencia_regresion ... OK")


def test_i10_y_citas_cruzadas():
    """i10_index y citas_cruzadas se extraen correctamente."""
    E, raw = compute_E(MOCK_DOCS)
    # Manuel (doc 8): GS i10=45, OpenAlex citas en periodo = 400 (year 2023)
    manuel = raw[8]
    assert manuel["i10_index"] == 45
    assert manuel["citas_cruzadas"] >= 400  # citas del período de referencia (OpenAlex)

    # David (doc 10): sin GS → i10=0
    david = raw[10]
    assert david["i10_index"] == 0

    print("test_i10_y_citas_cruzadas ... OK")


def test_impacto_articulo():
    """impacto_art se calcula como media de citas Crossref por artículo."""
    E, raw = compute_E(MOCK_DOCS)
    # Manuel (doc 8): 8 artículos con citas [40,35,50,28,15,45,32,20] → media 33.125
    manuel = raw[8]
    assert round(manuel["impacto_art"], 3) == 33.125, f"Expected 33.125, got {manuel['impacto_art']}"
    # Ana (doc 0): 6 artículos con citas [25,18,30,12,8,22] → media 19.167
    ana = raw[0]
    assert round(ana["impacto_art"], 3) == 19.167, f"Expected 19.167, got {ana['impacto_art']}"
    # David (doc 10): sin publicaciones con crossref → 0
    david = raw[10]
    assert david["impacto_art"] == 0.0
    print("test_impacto_articulo ... OK")


def test_run_mip_h_min_filter(raw, E, K):
    """Candidates below h_min are excluded (except fixed)."""
    sel, z = run_mip(raw, E, K, N=6, h_min=5)
    assert 10 not in sel, f"David (h=2) should be excluded with h_min=5, but is in {sel}"

    # But if fixed, should still be included
    sel2, z2 = run_mip(raw, E, K, N=6, h_min=5, fixed_indices=[10])
    assert 10 in sel2, f"David should be included when fixed, but {sel2}"

    print("test_run_mip_h_min_filter ... OK")


def test_run_mip_eu_min(raw, E, K):
    """Solution must have at least eu_min garantes with EU projects."""
    sel, z = run_mip(raw, E, K, N=6, eu_min=2)
    eu_count = sum(1 for i in sel if raw[i].get("proyectos_eu", 0) > 0)
    assert eu_count >= 2, f"Need >= 2 garantes with EU projects, got {eu_count}"
    print(f"test_run_mip_eu_min ... OK ({eu_count} garantes with EU)")


def test_compute_diagnostico_modalidad(sel, raw, K):
    """compute_diagnostico adapts thresholds to modality."""
    diag_mdm = compute_diagnostico(sel, raw, K, 6, modalidad="MdM")
    diag_so = compute_diagnostico(sel, raw, K, 6, modalidad="SO")

    assert diag_mdm["metricas"]["modalidad"] == "MdM"
    assert diag_so["metricas"]["modalidad"] == "SO"

    assert diag_so["valoracion"] in ("COMPETITIVO", "MEJORABLE", "DIFICIL")
    assert diag_mdm["valoracion"] in ("COMPETITIVO", "MEJORABLE", "DIFICIL")

    # New metrics should be present
    assert "garantes_eu" in diag_mdm["metricas"]
    assert "intl_mean" in diag_mdm["metricas"]

    print(f"test_compute_diagnostico_modalidad ... OK (MdM: {diag_mdm['valoracion']}, SO: {diag_so['valoracion']})")


def test_sexenios_vivo_bonus():
    """Sexenio vivo (within 6 years) gives higher E_i than same count without."""
    doc_vivo = _make_doc(
        90, "Test Vivo", "Catedratico de Universidad", "Hombre",
        "Medicina", "CTS-001", 15, 2, 2,
        [{"year": 2023, "cited_by_count": 100, "works_count": 4}],
        sexenios=3, fecha_ultimo_sexenio="01/01/2024",
    )
    doc_no_vivo = _make_doc(
        91, "Test No Vivo", "Catedratico de Universidad", "Hombre",
        "Medicina", "CTS-001", 15, 2, 2,
        [{"year": 2023, "cited_by_count": 100, "works_count": 4}],
        sexenios=3, fecha_ultimo_sexenio="01/01/2018",
    )
    E, raw = compute_E([doc_vivo, doc_no_vivo], modalidad="SO")
    # Vivo has raw=4 (3+1), no vivo has raw=3 (3+0)
    assert raw[0]["sexenios_raw"] == 4.0
    assert raw[1]["sexenios_raw"] == 3.0
    # With normalization, vivo should score higher
    assert E[0] > E[1], f"Vivo E_i {E[0]} should exceed no-vivo {E[1]}"
    print("  test_sexenios_vivo_bonus ... OK")


def test_sexenios_missing_fields():
    """Candidates without sexenios fields don't break compute_E."""
    doc_with = _make_doc(
        92, "Has Sexenios", "Catedratico de Universidad", "Hombre",
        "Medicina", "CTS-001", 15, 2, 2,
        [{"year": 2023, "cited_by_count": 100, "works_count": 4}],
        sexenios=2, fecha_ultimo_sexenio="01/01/2023",
    )
    doc_without = _make_doc(
        93, "No Sexenios", "Profesora Titular de Universidad", "Mujer",
        "Medicina", "CTS-001", 15, 2, 2,
        [{"year": 2023, "cited_by_count": 100, "works_count": 4}],
    )
    # Remove fields entirely to simulate old DB docs
    del doc_without["sexenios"]
    del doc_without["fecha_ultimo_sexenio"]

    E, raw = compute_E([doc_with, doc_without], modalidad="MdM")
    assert raw[1]["sexenios_raw"] == 0.0
    assert raw[1]["sexenios"] == 0
    assert E[0] > E[1], "Researcher with sexenios should score higher"
    print("  test_sexenios_missing_fields ... OK")


# ─── Tests de mejoras de selección ────────────────────────────────────────────

def test_norm_winsor_outlier():
    """(1a) La normalización winsor evita que un outlier comprima al resto."""
    import mip_garantes as mg
    docs = [d for d in MOCK_DOCS]  # pool real
    # winsor (default) vs minmax: comparar dispersión de E entre no-outliers.
    # Desactivamos log1p para aislar el efecto winsor puro.
    old_method = cfg.E_NORM_METHOD
    old_log = cfg.LOG_TRANSFORM_COLS.copy()
    try:
        cfg.LOG_TRANSFORM_COLS = set()
        cfg.E_NORM_METHOD = "minmax"
        E_mm, _ = compute_E(docs)
        cfg.E_NORM_METHOD = "winsor"
        E_w, _ = compute_E(docs)
    finally:
        cfg.E_NORM_METHOD = old_method
        cfg.LOG_TRANSFORM_COLS = old_log
    # Ambos en [0,1]
    assert all(e >= 0 for e in E_mm)
    assert all(e >= 0 for e in E_w)
    # Winsor debe dar más "aire" a los del medio: mayor desviación estándar
    # entre los no-máximos (menos compresión por el outlier).
    assert np.std(E_w) >= np.std(E_mm) - 1e-9, \
        f"winsor std {np.std(E_w):.4f} < minmax std {np.std(E_mm):.4f}"
    print("test_norm_winsor_outlier ... OK")


def test_log_transform_compresses_outlier():
    """Log transform reduces the score gap between a heavy outlier and the median."""
    import copy

    # Build a pool with an extreme outlier in citas_cruzadas at index 8
    docs_with_outlier = copy.deepcopy(MOCK_DOCS)
    # Inject extreme outlier into openalex counts_by_year — this is what compute_E reads for citas_cruzadas
    docs_with_outlier[8]["openalex"]["counts_by_year"] = [
        {"year": 2023, "cited_by_count": 5000, "works_count": 8}
    ]

    old_log = cfg.LOG_TRANSFORM_COLS.copy()
    try:
        # Without log transform
        cfg.LOG_TRANSFORM_COLS = set()
        E_no_log, _ = compute_E(docs_with_outlier)
        # With log transform — use real config value
        cfg.LOG_TRANSFORM_COLS = old_log
        E_log, _ = compute_E(docs_with_outlier)
    finally:
        cfg.LOG_TRANSFORM_COLS = old_log

    # Gap between outlier (index 8) and Ana (index 0) should be smaller with log
    gap_no_log = E_no_log[8] - E_no_log[0]
    gap_log    = E_log[8]    - E_log[0]
    assert gap_log < gap_no_log, (
        f"Log transform should compress outlier gap: "
        f"gap_no_log={gap_no_log:.4f}, gap_log={gap_log:.4f}"
    )
    assert all(e >= 0 for e in E_log)
    print("test_log_transform_compresses_outlier ... OK")


def test_balance_penalty():
    """(1b) Un perfil equilibrado supera a uno picudo con la misma suma lineal."""
    import mip_garantes as mg
    E, raw = compute_E(MOCK_DOCS)
    # Todos deben tener balance_factor en (0, 1]
    assert all(0 < r["balance_factor"] <= 1.0 for r in raw)
    # El factor penaliza: al menos un investigador "picudo" debe tener factor < 1
    assert any(r["balance_factor"] < 1.0 for r in raw), \
        "Ningún perfil fue penalizado por desequilibrio"
    print("test_balance_penalty ... OK")


def test_balance_entropy_vs_cv():
    """Entropy balance_factor does not penalise a low-mean-but-uniform profile more than a high-mean-but-spiked one."""
    import math

    def entropy_balance(vals, lam=0.10):
        n = len(vals)
        total = sum(vals)
        if total <= 0 or n < 2:
            return 1.0
        probs = [v / total for v in vals]
        H = -sum(p * math.log(p) for p in probs if p > 0)
        H_max = math.log(n)
        H_norm = H / H_max if H_max > 0 else 1.0
        return 1.0 - lam * (1.0 - H_norm)

    uniform = [0.2, 0.2, 0.2, 0.2, 0.2]
    spiked  = [0.9, 0.025, 0.025, 0.025, 0.025]

    f_uniform = entropy_balance(uniform)
    f_spiked  = entropy_balance(spiked)

    assert f_uniform > f_spiked, (
        f"Uniform profile should have higher balance_factor than spiked: "
        f"f_uniform={f_uniform:.4f}, f_spiked={f_spiked:.4f}"
    )
    assert abs(f_uniform - 1.0) < 1e-9, f"Perfectly uniform should give factor=1.0, got {f_uniform}"
    assert f_spiked < 1.0, f"Spiked profile should be penalised, got {f_spiked:.4f}"
    assert 0 < f_spiked <= 1.0
    assert 0 < f_uniform <= 1.0

    print("test_balance_entropy_vs_cv ... OK")


def test_soft_h_gate():
    """(2) El gate blando: una tendencia ascendente recompra un h-index bajo el
    umbral duro, y eso decide QUÉ candidato entra en la selección.

    Diseño: 3 candidatos, h_min=10 (buyback=2 → suelo blando=8), N=2.
      A (h=15, área A1) y B (h=15, área A2): superan el umbral duro → siempre
        elegibles (2 == N, así nunca se dispara la ampliación del pool).
      C (h=9, área A3, tendencia ASCENDENTE y E_i ALTO): solo elegible vía gate
        blando, pero con la mejor Excelencia Individual del pool.
    Sin restricciones de área/paridad, el optimizador maximiza ΣE_i:
      - gate ON  → C es elegible y, por su E_i alto, ENTRA (desplaza a A o B).
      - gate OFF → C no es elegible; quedan {A,B} (=N) y C NO entra.
    """
    asc_citas = [{"year": 2025, "cited_by_count": 400, "works_count": 5},
                 {"year": 2024, "cited_by_count": 350, "works_count": 5},
                 {"year": 2022, "cited_by_count": 20, "works_count": 2}]
    modest_citas = [{"year": 2024, "cited_by_count": 40, "works_count": 2},
                    {"year": 2022, "cited_by_count": 40, "works_count": 2}]
    docs = [
        _make_doc(0, "A Fuerte", "Catedratico de Universidad", "Mujer",
                  "A1", "G1", 15, 1, 0, modest_citas, journal_cuartiles=["Q3"]),
        _make_doc(1, "B Fuerte", "Catedratico de Universidad", "Hombre",
                  "A2", "G2", 15, 1, 0, modest_citas, journal_cuartiles=["Q3"]),
        _make_doc(2, "C Ascendente", "Profesor Titular", "Mujer",
                  "A3", "G3", 9, 3, 3, asc_citas, journal_cuartiles=["Q1", "Q1"],
                  distinciones=3, membresias=2),
    ]
    E, raw = compute_E(docs)
    K = compute_K(raw, docs)
    assert raw[2]["tendencia"] >= cfg.H_SOFT_GATE_TREND_MIN, \
        f"C debería ser ascendente (tend={raw[2]['tendencia']})"
    assert E[2] > E[0] and E[2] > E[1], \
        f"C debería tener el mayor E_i (E={[round(float(x),3) for x in E]})"

    _orig = cfg.H_SOFT_GATE_ENABLED
    try:
        cfg.H_SOFT_GATE_ENABLED = True
        sel_on, _ = run_mip(raw, E, K, N=2, min_areas=1, min_paridad=0.0,
                            h_min=10, eu_min=0)
        cfg.H_SOFT_GATE_ENABLED = False
        sel_off, _ = run_mip(raw, E, K, N=2, min_areas=1, min_paridad=0.0,
                             h_min=10, eu_min=0)
    finally:
        cfg.H_SOFT_GATE_ENABLED = _orig

    assert sel_on is not None and sel_off is not None, "Ambas corridas factibles"
    assert 2 in sel_on, "C (ascendente, E_i alto) debería entrar vía buyback (gate ON)"
    assert 2 not in sel_off, "C no es elegible con el gate OFF y no debería entrar"
    print("test_soft_h_gate ... OK (buyback decide selección: C dentro con gate ON, fuera con OFF)")


def test_paridad_banda():
    """(5a) La banda de paridad evita grupos monogénero."""
    E, raw = compute_E(MOCK_DOCS)
    K = compute_K(raw, MOCK_DOCS)
    sel, z = run_mip(raw, E, K, N=6, min_paridad=0.4)
    mujeres = sum(1 for i in sel if raw[i]["genero"] == "Mujer")
    hombres = len(sel) - mujeres
    assert mujeres >= math.ceil(0.4 * 6), f"muy pocas mujeres: {mujeres}"
    if cfg.PARIDAD_BANDA:
        assert hombres >= math.ceil(0.4 * 6), f"banda violada: solo {hombres} hombres"
    print(f"test_paridad_banda ... OK ({mujeres}M/{hombres}H)")


def test_compute_stability():
    """(4) compute_stability devuelve frecuencias en [0,1] y un núcleo robusto."""
    E, raw = compute_E(MOCK_DOCS)
    K = compute_K(raw, MOCK_DOCS)
    freq, valid = compute_stability(raw, E, K, N=6, n_runs=20, sigma=0.05)
    assert valid > 0, "Ninguna corrida produjo solución factible"
    assert all(0.0 <= f <= 1.0 for f in freq.values())
    # Debe existir un núcleo robusto: al menos un investigador casi siempre elegido
    assert any(f >= 0.9 for f in freq.values()), \
        "No se detectó ningún garante robusto (freq >= 0.9)"
    # La suma de frecuencias debe rondar N (cada corrida elige N)
    assert abs(sum(freq.values()) - 6) < 1.0, \
        f"suma de frecuencias {sum(freq.values()):.2f} lejos de N=6"
    print(f"test_compute_stability ... OK ({valid} corridas válidas)")


def test_produccion_sin_h_lifetime():
    """(A) 'produccion' no debe depender del h-index lifetime.

    Dos perfiles idénticos en las métricas del periodo de referencia
    (citas y producción CVN) pero con distinto h global deben recibir
    la misma puntuación en la dimensión 'produccion'.
    """
    citas = [{"year": 2023, "cited_by_count": 100, "works_count": 5}]
    base = dict(figura="Catedratico de Universidad", genero="Hombre",
                area="Area X", grupo="G", ip=1, tesis=1,
                citas_by_year=citas, journal_cuartiles=["Q1", "Q2"])
    docs = [
        _make_doc(0, "Alta H", h_index=40, **base),
        _make_doc(1, "Baja H", h_index=5, **base),
        # Tercero distinto para que la normalización tenga rango
        _make_doc(2, "Otro", figura="Catedratico de Universidad", genero="Mujer",
                  area="Area Y", grupo="G2", h_index=10, ip=0, tesis=0,
                  citas_by_year=[{"year": 2023, "cited_by_count": 10, "works_count": 1}],
                  journal_cuartiles=["Q4"]),
    ]
    E, raw = compute_E(docs)
    p0 = raw[0]["dims_norm"]["produccion"]
    p1 = raw[1]["dims_norm"]["produccion"]
    assert abs(p0 - p1) < 1e-9, \
        f"'produccion' depende del h lifetime: {p0:.4f} (h=40) vs {p1:.4f} (h=5)"
    # h-index sigue existiendo como dato (gate/contexto), solo que fuera del E_i
    assert raw[0]["h_index"] == 40 and raw[1]["h_index"] == 5
    print("test_produccion_sin_h_lifetime ... OK")


def test_casi_garantes_devuelve_m_no_seleccionados():
    """Devuelve hasta 2*M candidatos (M por género), ninguno seleccionado."""
    E, raw = compute_E(MOCK_DOCS, modalidad="MdM")
    K = compute_K(raw, MOCK_DOCS)
    sel, _ = run_mip(raw, E, K, N=3, modalidad="MdM", h_min=5, eu_min=0)
    params = {"modalidad": "MdM", "h_min": 5, "eu_min": 0,
              "top_pct_max": None, "top_pct_source": "any"}
    res = diagnosticar_casi_garantes(raw, E, sel, params, m=2)
    assert 1 <= len(res) <= 4, f"Expected 1-4 casi-garantes (m=2 per gender), got {len(res)}"
    for c in res:
        assert c["idx"] not in sel
        assert "debilidades" in c and isinstance(c["debilidades"], list)
        assert "accion" in c
    print("test_casi_garantes_devuelve_m_no_seleccionados ... OK")


def test_casi_garantes_ordenados_por_Ei_descendente():
    E, raw = compute_E(MOCK_DOCS, modalidad="MdM")
    K = compute_K(raw, MOCK_DOCS)
    sel, _ = run_mip(raw, E, K, N=3, modalidad="MdM", h_min=5, eu_min=0)
    params = {"modalidad": "MdM", "h_min": 5, "eu_min": 0,
              "top_pct_max": None, "top_pct_source": "any"}
    res = diagnosticar_casi_garantes(raw, E, sel, params, m=4)
    eis = [c["E_i"] for c in res]
    assert eis == sorted(eis, reverse=True)
    print("test_casi_garantes_ordenados_por_Ei_descendente ... OK")


def test_casi_garantes_detecta_h_bajo():
    """Un candidato con h por debajo del umbral debe tener la debilidad de h."""
    E, raw = compute_E(MOCK_DOCS, modalidad="SO")
    K = compute_K(raw, MOCK_DOCS)
    sel, _ = run_mip(raw, E, K, N=2, modalidad="SO", h_min=8, eu_min=0)
    params = {"modalidad": "SO", "h_min": 20, "eu_min": 0,
              "top_pct_max": None, "top_pct_source": "any"}
    res = diagnosticar_casi_garantes(raw, E, sel, params, m=5)
    # Con h_min=20 (muy alto), al menos un casi-garante debe señalar h bajo
    assert any(any("h-index" in d for d in c["debilidades"]) for c in res)
    print("test_casi_garantes_detecta_h_bajo ... OK")


def test_lifetime_metrics_ignore_period():
    """IP, tesis, EU counts are lifetime — unaffected by periodo_ref narrowing."""
    doc = _make_doc(
        idx=99, nombre="Test Lifetime", figura="Titular", genero="Hombre",
        area="TestArea", grupo="TestGrupo", h_index=10, ip=0, tesis=0,
        citas_by_year=[{"year": 2022, "cited_by_count": 50},
                       {"year": 2023, "cited_by_count": 60}],
    )
    # Override items to dates outside any recent period
    doc["financiaciones"]["items"] = [
        {"responsable": True,  "nombre": "", "financiador": "",             "convocatoria": "", "programa": "", "anualidad": 2015},
        {"responsable": True,  "nombre": "", "financiador": "",             "convocatoria": "", "programa": "", "anualidad": 2015},
        {"responsable": True,  "nombre": "", "financiador": "",             "convocatoria": "", "programa": "", "anualidad": 2015},
        {"responsable": False, "nombre": "", "financiador": "",             "convocatoria": "", "programa": "", "anualidad": 2015},
        {"responsable": True,  "nombre": "", "financiador": "UNIÓN EUROPEA","convocatoria": "", "programa": "", "anualidad": 2015},
        {"responsable": False, "nombre": "", "financiador": "UNIÓN EUROPEA","convocatoria": "", "programa": "", "anualidad": 2018},
    ]
    doc["tesis"]["dirigidas"] = [{"anualidad": 2015}, {"anualidad": 2016}]

    E, raw = compute_E([doc], modalidad="MdM", periodo_ref=(2021, 2025))

    assert raw[0]["proyectos_ip"] >= 3, \
        f"proyectos_ip must be >= 3 (lifetime), got {raw[0]['proyectos_ip']}"
    assert raw[0]["tesis_dir"] == 2, \
        f"tesis_dir must be 2 (lifetime), got {raw[0]['tesis_dir']}"
    assert raw[0]["proyectos_eu"] >= 2, \
        f"proyectos_eu must be >= 2 (lifetime), got {raw[0]['proyectos_eu']}"

    print("test_lifetime_metrics_ignore_period ... OK")


# ─── Ejecutar ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  TEST SUITE — Optimizador MIP de Garantes")
    print("=" * 60)

    test_gender_constraint_ceil()
    E, raw = test_compute_E()
    test_compute_E_modalidad()
    test_pesos_uei_sum()
    test_compute_E_modalidad_uei()
    test_h_consolidado()
    test_tendencia_regresion()
    test_i10_y_citas_cruzadas()
    test_impacto_articulo()
    K = test_compute_K(raw)
    sel = test_run_mip_n6(raw, E, K)
    test_run_mip_director(raw, E, K)
    test_run_mip_paridad(raw, E, K)
    test_compute_diagnostico(sel, raw, K)
    test_compute_diagnostico_modalidad(sel, raw, K)
    test_run_mip_fixed_indices(raw, E, K)
    test_run_mip_h_min_filter(raw, E, K)
    test_run_mip_eu_min(raw, E, K)
    test_find_clusters(raw, E, K)
    test_run_mip_uei(raw, E, K)
    test_compute_diagnostico_uei(sel, raw, K)
    test_sexenios_vivo_bonus()
    test_sexenios_missing_fields()
    test_norm_winsor_outlier()
    test_log_transform_compresses_outlier()
    test_balance_penalty()
    test_balance_entropy_vs_cv()
    test_soft_h_gate()
    test_paridad_banda()
    test_compute_stability()
    test_produccion_sin_h_lifetime()
    test_casi_garantes_devuelve_m_no_seleccionados()
    test_casi_garantes_ordenados_por_Ei_descendente()
    test_casi_garantes_detecta_h_bajo()
    test_lifetime_metrics_ignore_period()

    print()
    print("-" * 60)
    print("  Todos los tests pasaron.")
    print("-" * 60)
