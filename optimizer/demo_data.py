"""
Synthetic, fully offline demo dataset for the Garante dashboard.

Generates a cohort of fictitious investigators with the same document schema the
production MongoDB uses, so the complete dashboard (scoring, optimisation,
diagnostics, network) runs without any database. No real person is represented:
all names are "Researcher NNN" and every value is randomly generated from a fixed
seed, so the demo is deterministic and reproducible.

Used by `mip_garantes.load_investigators()` when the selected institute is the
offline demo. The LLM panel still requires an Anthropic API key.
"""
import random

AREAS = [
    "Applied Mathematics", "Administrative Law", "Audiovisual Communication",
    "Operations Research", "Basic Psychology", "Organic Chemistry",
    "Cell Biology", "Economic History", "Computer Languages and Systems",
    "Social Anthropology", "Marine Sciences", "Condensed Matter Physics",
]
FIGURAS = [
    "Catedrático de Universidad", "Catedrática de Universidad",
    "Profesor Titular de Universidad", "Profesora Titular de Universidad",
    "Profesor Contratado Doctor", "Profesora Contratada Doctora",
    "Profesor Ayudante Doctor", "Profesora Ayudante Doctor",
]
INTL = ["MIT", "Oxford", "ETH Zurich", "Sorbonne", "Max Planck", "Kyoto Univ.",
        "Stanford", "TU Delft", "KU Leuven", "Univ. São Paulo"]


def _make_doc(idx, genero, figura, area, h_index, ip, tesis, eu, intl_n,
              sexenios, base_cites, copubs):
    fem = genero == "Mujer"
    fin_items = [{"responsable": True, "financiador": "", "anualidad": 2022}] * ip + \
                [{"responsable": False, "financiador": "", "anualidad": 2022}]
    for k in range(eu):
        fin_items.append({"responsable": k == 0, "nombre": "EU project",
                          "financiador": "UNIÓN EUROPEA", "anualidad": 2023})
    pub_items = [{"tipo": "articulo", "anualidad": 2022 + (j % 2),
                  "crossref": {"citas_crossref": c, "encontrado": True}}
                 for j, c in enumerate(base_cites)]
    return {
        "nombre_completo": f"Researcher {idx:03d}",
        "figura": figura,
        "genero": genero,
        "id_investigador": f"demo_{idx}",
        "area": {"nombre": area},
        "grupo_investigacion": {"nombre": f"GRP-{idx % 20:02d}"},
        "financiaciones": {"total": len(fin_items), "items": fin_items},
        "tesis": {"doctoral": {"titulo": f"Doctoral thesis {idx}", "anualidad": 2005},
                  "dirigidas": [{"anualidad": 2022}] * tesis},
        "openalex": {"h_index": h_index,
                     "counts_by_year": [{"year": 2023, "cited_by_count": sum(base_cites), "works_count": len(base_cites)},
                                        {"year": 2022, "cited_by_count": sum(base_cites) // 2, "works_count": max(1, len(base_cites) // 2)}]},
        "dialnet_metricas": {},
        "publicaciones": {"items": pub_items},
        "colaboraciones": {"colaboradores": copubs,
                           "instituciones": [{"nombre": n, "pais": "International"} for n in INTL[:intl_n]]},
        "patentes": {"total": 0, "items": []},
        "orcid_record": {"distinciones": 1 if h_index > 20 else 0, "membresias": 0},
        "google_scholar": {"h_index": h_index + 2, "i10_index": h_index, "citas_por_anio": {}},
        "semantic_scholar": {"encontrado": True, "h_index": max(1, h_index - 3)},
        "metricas_unificadas": {"citas_totales": {"openalex": sum(base_cites) * 3, "crossref": sum(base_cites)}},
        "sexenios": sexenios,
        "fecha_ultimo_sexenio": "01/01/2023" if sexenios else "",
    }


def generate_demo_docs(n=80, seed=42):
    """Return a deterministic list of n synthetic investigator documents."""
    rnd = random.Random(seed)
    # first decide each researcher's headline figures
    specs = []
    for i in range(n):
        genero = "Mujer" if rnd.random() < 0.46 else "Hombre"
        # gender-consistent job title
        fem_titles = [f for f in FIGURAS if f.endswith("a") or "Doctora" in f]
        figura = rnd.choice(fem_titles if genero == "Mujer" else
                            [f for f in FIGURAS if f not in fem_titles])
        h = max(2, int(rnd.gauss(13, 6)))
        specs.append({
            "genero": genero, "figura": figura, "area": rnd.choice(AREAS),
            "h": h, "ip": rnd.randint(0, 4), "tesis": rnd.randint(0, 5),
            "eu": (rnd.randint(1, 3) if rnd.random() < 0.32 else 0),
            "intl": rnd.randint(0, 6), "sex": min(6, max(0, h // 5)),
            "cites": [rnd.randint(0, 40) for _ in range(rnd.randint(3, 12))],
        })
    # build a sparse copublication graph
    copub = {i: [] for i in range(n)}
    for i in range(n):
        for _ in range(rnd.randint(0, 3)):
            j = rnd.randint(0, n - 1)
            if j != i:
                w = rnd.randint(1, 6)
                copub[i].append({"id_investigador": f"demo_{j}", "publicaciones_conjuntas": w})
                copub[j].append({"id_investigador": f"demo_{i}", "publicaciones_conjuntas": w})
    return [
        _make_doc(i, s["genero"], s["figura"], s["area"], s["h"], s["ip"],
                  s["tesis"], s["eu"], s["intl"], s["sex"], s["cites"], copub[i])
        for i, s in enumerate(specs)
    ]
