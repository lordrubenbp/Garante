"""Configuración centralizada del optimizador MIP de garantes."""
import os
from dataclasses import dataclass, field
from typing import Literal
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

# Type for modalidad
Modalidad = Literal["SO", "MdM", "UEI"]

# ── MongoDB ───────────────────────────────────────────────────────────────────
# MONGO_URI es opcional: si no se define (p. ej. en una instalación sin
# credenciales), la aplicación arranca en modo demo offline sobre datos
# sintéticos. Las funciones que requieren MongoDB se degradan con elegancia.
MONGO_URI  = os.getenv("MONGO_URI")
DB_NAME    = os.getenv("MONGO_DB", "research_db")
DEMO_INSTITUTE = "Demo (offline)"   # instituto sintético: dashboard sin MongoDB
COLLECTION = "investigadores"
MONGO_SYSTEM_DBS = {"admin", "local", "config"}

# ── Registro de institutos ────────────────────────────────────────────────────
# Cada BD MongoDB puede tener una entrada aquí con nombre legible y descripción
# para los prompts LLM. Si una BD no tiene entrada, se usan valores genéricos.
# Vacío por defecto: cualquier BD sin entrada usa los valores genéricos de
# get_instituto_info(). Para personalizar el contexto de los prompts LLM de un
# instituto concreto, añade aquí una entrada con clave igual al nombre de la BD.
INSTITUTOS: dict = {}

def get_instituto_info(db_name: str) -> dict:
    """Devuelve la info del instituto para db_name, con fallback genérico."""
    if db_name in INSTITUTOS:
        return INSTITUTOS[db_name]
    # Fallback genérico: deriva el nombre de la BD
    nombre = db_name.replace("_claude", "").upper()
    return {
        "nombre": nombre,
        "nombre_largo": nombre,
        "universidad": "",
        "perfil": "investigación científica multidisciplinar",
    }

# ── Elegibilidad ──────────────────────────────────────────────────────────────
FIGURAS_ELEGIBLES = [
    "Catedrático de Universidad",
    "Catedrática de Universidad",
    "Profesor Titular de Universidad",
    "Profesora Titular de Universidad",
    "Profesor Contratado Doctor",
    "Profesora Contratada Doctora",
    "Profesor Ayudante Doctor",
    "Profesora Ayudante Doctora",
    "Profesor Permanente Laboral",
    "Profesora Permanente Laboral",
    "Investigadora Posdoctoral Ramón y Cajal",
    "Investigadora Doctora Tipo 1",
]

# ── Función objetivo  Z = ALPHA·ΣE_i·x_i + BETA·ΣK_ij·y_ij ─────────────────
ALPHA = 0.95   # peso excelencia individual (Fase 1 convocatoria: evaluación individual)
BETA  = 0.05   # peso cohesión estructural (desempate entre candidatos con E_i similar)

# ── Score E_i fallback (si no hay modalidad SO/MdM) ──────────────────────────
PESOS_5D = dict(calidad=0.30, ip=0.25, tesis=0.15, produccion=0.15, tendencia=0.15)
PESOS_4D = dict(ip=0.34, produccion=0.22, tesis=0.22, tendencia=0.22)

# ── Pesos E_i por modalidad SO/MdM (suman 1.0) ─────────────────────────────
# Severo Ochoa: prioriza liderazgo europeo e internacionalizacion
# Alineado con criterios Fase 1 convocatoria AEI 2026 (Anexo II)
# 'impacto_art' = media de citas por artículo (Crossref), DORA-compatible.
# Mide el impacto real del trabajo publicado, no el prestigio de la revista.
# 'top_mundial' = field-percentile OpenAlex (1−pct), testimonial.
# Señal de posicionamiento global en el subcampo; peso bajo para no duplicar métricas de output.
PESOS_SO = {
    "produccion": 0.11, "ip": 0.07, "tesis": 0.04, "tendencia": 0.07,
    "eu": 0.22, "intl": 0.16, "reconocimiento": 0.08, "i10": 0.03, "impacto_art": 0.11,
    "sexenios": 0.06, "top_mundial": 0.05,
}
# Maria de Maeztu: mas equilibrado, valora formacion y transferencia
# Alineado con criterios Fase 1 convocatoria AEI 2026 (Anexo II)
PESOS_MDM = {
    "produccion": 0.14, "ip": 0.09, "tesis": 0.05, "tendencia": 0.08,
    "eu": 0.16, "intl": 0.13, "reconocimiento": 0.08, "i10": 0.04, "impacto_art": 0.11,
    "sexenios": 0.07, "top_mundial": 0.05,
}
# UEI (Unidades de Excelencia en Investigación, Junta de Andalucía): trampolín hacia MdM/SO
# Umbrales más bajos; pesos MdM-alineados con más peso en EU e internacionalización
PESOS_UEI = {
    "produccion": 0.13, "ip": 0.09, "tesis": 0.06, "tendencia": 0.09,
    "eu": 0.14, "intl": 0.12, "reconocimiento": 0.08, "i10": 0.04, "impacto_art": 0.11,
    "sexenios": 0.09, "top_mundial": 0.05,
}

# ── Pesos scoring de NUCLEOS por modalidad (suman 1.0) ────────────────────────
# Severo Ochoa: prioriza internacionalización y masa crítica senior
PESOS_NUCLEO_SO = {
    "cohesion": 0.20, "top_mundial": 0.20, "diversidad_areas": 0.10,
    "equilibrio_senior_junior": 0.12, "tendencia": 0.13, "internacionalizacion": 0.25,
}
# María de Maeztu: prioriza colaboración interna, formación y sostenibilidad
PESOS_NUCLEO_MDM = {
    "cohesion": 0.25, "top_mundial": 0.20, "diversidad_areas": 0.15,
    "equilibrio_senior_junior": 0.18, "tendencia": 0.12, "internacionalizacion": 0.10,
}
# UEI: similar a MdM, algo más de énfasis en excelencia individual y tendencia
PESOS_NUCLEO_UEI = {
    "cohesion": 0.25, "top_mundial": 0.18, "diversidad_areas": 0.15,
    "equilibrio_senior_junior": 0.18, "tendencia": 0.14, "internacionalizacion": 0.10,
}
# Configuración NEUTRA para la pestaña Lab (exploración sin convocatoria).
# Media equilibrada: cohesión y excelencia altas, resto repartido.
PESOS_NUCLEO_LAB = {
    "cohesion": 0.30,
    "top_mundial": 0.25,
    "diversidad_areas": 0.15,
    "equilibrio_senior_junior": 0.10,
    "tendencia": 0.15,
    "internacionalizacion": 0.05,
}
NUCLEO_SIZE_LAB = 5

# ── Tamaño del nucleo algorítmico vs refuerzos IA ────────────────────────────
NUCLEO_SIZE_SO = 5    # Severo Ochoa: 5 nucleo + 5 IA
NUCLEO_SIZE_MDM = 3   # María de Maeztu: 3 nucleo + 3 IA
NUCLEO_SIZE_UEI = 5   # UEI: 5 nucleo + 5 IA (similar a SO, equipo más amplio)

# ── Año de referencia (para cálculos de tendencia) ────────────────────────
CURRENT_YEAR = 2026

# ── Período de referencia por modalidad (año_inicio inclusive, año_fin inclusive) ──
# SO/MdM: últimos 5 años completos de actividad investigadora
# UEI: 1 enero 2022 – 30 junio 2025 (3.5 años, BOJA Art. 2.d)
PERIODO_REF_SO:  tuple[int, int] = (2021, 2025)
PERIODO_REF_MDM: tuple[int, int] = (2021, 2025)
PERIODO_REF_UEI: tuple[int, int] = (2022, 2025)

# ── Umbrales por modalidad ──────────────────────────────────────────────────
H_MIN_SO  = 8
H_MIN_MDM = 5
H_MIN_UEI = 4
H_TARGET_SO  = 25   # h-index medio objetivo para fichajes/scoring
H_TARGET_MDM = 15
H_TARGET_UEI = 12

# ── Producción ponderada por tipo (CVN / publicaciones.items) ────────────────
# (El filtro temporal se aplica via PERIODO_REF_* por modalidad en compute_E)
PRODUCCION_TYPE_WEIGHTS: dict[str, float] = {
    "articulo":            3.0,
    "libro":               2.0,
    "capitulo":            1.5,
    "aportación congreso": 1.0,
    "_default":            0.5,   # resto de tipos reconocidos
}
EU_MIN_SO  = 4
EU_MIN_MDM = 2
EU_MIN_UEI = 1

# ── Penalizaciones blandas en funcion objetivo ──────────────────────────────
PENALTY_ISOLATED  = 0.05
PENALTY_DECLINING = 0.03

# ── Keywords para detectar proyectos europeos ───────────────────────────────

# ── Cohesión K_ij (copublicaciones reales) ───────────────────────────────────
C_MAX_PERCENTILE = 95   # percentil para normalizar copublicaciones

# ── Diversidad de áreas ──────────────────────────────────────────────────────
MIN_AREAS_DEFAULT = 3   # mínimo de áreas distintas en el subgrafo (para N≤10)
MIN_AREAS_LARGE   = 4   # para N>10

# ── Mejoras de selección ─────────────────────────────────────────────────────
# (1a) Normalización robusta de E_i: "winsor" recorta outliers al percentil
#      E_NORM_PERCENTILE antes de escalar min-max, evitando que un único
#      superstar comprima al resto del pool. "minmax" = comportamiento clásico.
E_NORM_METHOD = "winsor"        # "winsor" | "minmax"
E_NORM_PERCENTILE = 95          # percentil de recorte superior (igual que K)

# Columnas con distribución muy sesgada a la derecha — aplica log1p antes de
# normalizar para suavizar la cola sin recorte brusco.
# log1p(x) = log(x+1): mapea 0→0, suaviza outliers.
LOG_TRANSFORM_COLS: set[str] = {
    "citas_cruzadas",   # citas totales: cola muy larga
    "eu_score_raw",     # proyectos EU + 2×IP_EU: lifetime, cola larga
    "proyectos_ip",     # IPs en carrera: concentrado en 0–3, cola larga
    "impacto_art",      # media citas por artículo: cola larga
    "i10_index",        # artículos con ≥10 citas: cola larga
}


# (1b) Recompensa al equilibrio multidimensional: penaliza perfiles "picudos"
#      (fuertes en una dimensión, nulos en otras) multiplicando E_i por
#      (1 - BALANCE_LAMBDA · dispersión), donde la dispersión es el coeficiente
#      de variación de las dimensiones con peso > 0. 0.0 = sin penalización.
BALANCE_LAMBDA = 0.10           # penalización máxima ~10 % para perfiles desequilibrados

# (5c) Shrinkage de tendencia: amortigua la tendencia hacia 0 para investigadores
#      con pocas publicaciones en el período (donde slope/mean es ruidoso).
TENDENCIA_SHRINKAGE = True
TENDENCIA_MIN_PUBS = 5          # nº de works en período para confiar plenamente en la tendencia

# (2) Gate blando de h-index: una tendencia fuertemente ascendente permite
#     "recomprar" hasta H_SOFT_GATE_BUYBACK puntos por debajo del h_min duro.
#     Pensado para no excluir jóvenes en ascenso (alineado con filosofía UEI).
H_SOFT_GATE_ENABLED = True
H_SOFT_GATE_TREND_MIN = 0.5     # tendencia (slope/mean) considerada "ascendente"
H_SOFT_GATE_BUYBACK = 2         # puntos de h-index que la tendencia puede compensar

# (5a) Banda de paridad: además del suelo (≥ min_paridad mujeres) impone un techo
#      simétrico (≥ min_paridad hombres), evitando grupos monogénero.
PARIDAD_BANDA = True

# (5b) Bonus de diversidad de áreas en la función objetivo: premia cubrir más
#      áreas distintas, más allá del mínimo duro (min_areas). Pequeño para no
#      dominar la excelencia individual.
AREA_DIVERSITY_BONUS = 0.01

# (4) Análisis de estabilidad de la selección: re-ejecuta el MIP con E_i
#     perturbado para medir qué garantes son robustos vs marginales.
STABILITY_N_RUNS = 50           # nº de corridas perturbadas
STABILITY_SIGMA = 0.05          # desviación relativa del ruido gaussiano sobre E_i

# ── Pesos para h-index consolidado (promedio ponderado) ─────────────────────
H_WEIGHTS = {
    "google_scholar": 0.45,
    "openalex": 0.30,
    "dialnet": 0.15,
    "semantic_scholar": 0.10,
}

# ── API Key (centralizada) ────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENALEX_MAILTO = os.getenv("OPENALEX_MAILTO", "research@example.org")  # Polite pool OpenAlex API
ANTHROPIC_BASE_URL = "https://api.anthropic.com"  # Forzar servidor real (evitar proxy local de Claude Code)
LLM_MODEL = "claude-opus-4-5"


# ── MIPConfig dataclass ──────────────────────────────────────────────────
@dataclass
class MIPConfig:
    """Encapsula los parámetros del solver MIP."""
    N: int
    modalidad: Modalidad = "MdM"
    alpha: float = ALPHA
    beta: float = BETA
    min_areas: int | None = None
    min_paridad: float = 0.4
    h_min: int | None = None
    eu_min: int | None = None
    fixed_indices: list[int] = field(default_factory=list)
    director_idx: int | None = None

    @classmethod
    def from_modalidad(cls, modalidad: Modalidad, N: int, **kwargs) -> "MIPConfig":
        """Factory con defaults por modalidad."""
        if modalidad == "SO":
            h_min_def, eu_min_def = H_MIN_SO, EU_MIN_SO
        elif modalidad == "UEI":
            h_min_def, eu_min_def = H_MIN_UEI, EU_MIN_UEI
        else:
            h_min_def, eu_min_def = H_MIN_MDM, EU_MIN_MDM
        defaults = {
            "h_min": h_min_def,
            "eu_min": eu_min_def,
            "min_areas": MIN_AREAS_DEFAULT if N <= 10 else MIN_AREAS_LARGE,
        }
        defaults.update(kwargs)
        return cls(N=N, modalidad=modalidad, **defaults)

