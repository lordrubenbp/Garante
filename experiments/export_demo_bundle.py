#!/usr/bin/env python3
"""
Export a SAFE, de-identified replication bundle from the anonymised DEMO_claude DB
so the ablation reproduces offline, without MongoDB and without shipping any
personal or re-identifiable data.

We export only aggregate, name-stripped fields (a strict whitelist) plus the
precomputed excellence scores E_i and the cohesion matrix K. No internal IDs, no
ORCID, no publication titles, no subfield labels, no collaborator names ever leave
the database — K is exported as a plain numeric matrix, not as collaboration lists.

Run once (needs DB access):
    cd Garante && python experiments/export_demo_bundle.py
Produces: experiments/demo_bundle.json
"""
import sys, os, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "optimizer"))
for line in (ROOT / ".env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import numpy as np
from pymongo import MongoClient
import config as cfg
from mip_garantes import compute_E, compute_K

# strict whitelist: only the aggregate fields the ablation consumes
RAW_KEYS = ["nombre_completo", "area", "genero", "h_index", "proyectos_eu",
            "tendencia", "produccion_cvn", "proyectos_ip", "tesis_dir", "impacto_art"]
MODALITIES = ["SO", "MdM", "UEI"]
DB = "DEMO_claude"


def main():
    docs = list(MongoClient(cfg.MONGO_URI, serverSelectionTimeoutMS=8000)[DB]["investigadores"].find())
    bundle = {"db": DB, "n": len(docs), "raw_keys": RAW_KEYS, "modalities": {}}
    for modalidad in MODALITIES:
        E, raw = compute_E(docs, modalidad=modalidad)
        K = compute_K(raw, docs)
        safe_raw = [{k: r.get(k) for k in RAW_KEYS} for r in raw]
        bundle["modalities"][modalidad] = {
            "raw": safe_raw,
            "E": [float(x) for x in E],
            "K": [[round(float(v), 6) for v in row] for row in K],
        }
        print(f"{modalidad}: {len(safe_raw)} records exported")
    out = ROOT / "experiments" / "demo_bundle.json"
    out.write_text(json.dumps(bundle, ensure_ascii=False))
    kb = out.stat().st_size / 1024
    print(f"Wrote {out} ({kb:.0f} KB) — de-identified, offline-reproducible")


if __name__ == "__main__":
    main()
