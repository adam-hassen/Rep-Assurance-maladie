"""
Étape 1 : repérer les fichiers open data de l'Assurance Maladie sur data.gouv.fr
et en garder un aperçu (liste des fichiers, documentation, premières lignes).
Lancement : python -m src.decouverte
"""
import gzip
import io
import json
import zlib
from pathlib import Path

import requests

SORTIE = Path("data/decouverte")
API = "https://www.data.gouv.fr/api/1/datasets/"
JEUX = {
    "open_damir": "open-damir-base-complete-sur-les-depenses-dassurance-maladie-interregimes",
    "soins_de_ville": "donnees-nationales-sur-les-depenses-dassurance-maladie-relatives-aux-soins-de-ville",
}
RECHERCHES = ["open medic", "open lpp", "open bio assurance maladie", "open ccam", "depenses assurance maladie"]


def log(m):
    print(f"[decouverte] {m}", flush=True)


def ressources(slug):
    r = requests.get(API + slug + "/", timeout=60)
    r.raise_for_status()
    d = r.json()
    res = [{"titre": x.get("title"), "url": x.get("url"), "format": x.get("format"), "taille": x.get("filesize"),
            "maj": x.get("last_modified"), "type": x.get("type")} for x in d.get("resources", [])]
    return {"titre": d.get("title"), "slug": slug, "producteur": (d.get("organization") or {}).get("name"),
            "licence": d.get("license"), "ressources": res}


def apercu_gz(url, nom, lignes=20000):
    """Lit seulement le début d'un gros fichier compressé (sans tout télécharger)."""
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        texte, lu = b"", 0
        for bloc in r.iter_content(1 << 20):
            lu += len(bloc)
            texte += d.decompress(bloc)
            if texte.count(b"\n") > lignes or lu > 200 << 20:
                break
    debut = b"\n".join(texte.split(b"\n")[:lignes])
    (SORTIE / f"{nom}_apercu.csv").write_bytes(debut)
    log(f"{nom} : aperçu de {debut.count(b'\n')} lignes")


def main():
    SORTIE.mkdir(parents=True, exist_ok=True)
    catalogue = {}
    for nom, slug in JEUX.items():
        try:
            catalogue[nom] = ressources(slug)
            log(f"{nom} : {len(catalogue[nom]['ressources'])} fichiers")
        except Exception as e:
            catalogue[nom] = {"erreur": repr(e)}
    for q in RECHERCHES:
        try:
            r = requests.get(API, params={"q": q, "organization": None, "page_size": 8}, timeout=60).json()
            catalogue[f"recherche:{q}"] = [{"titre": d["title"], "slug": d["slug"],
                                            "producteur": (d.get("organization") or {}).get("name"),
                                            "nb_fichiers": len(d.get("resources", []))} for d in r.get("data", [])]
        except Exception as e:
            catalogue[f"recherche:{q}"] = {"erreur": repr(e)}
    (SORTIE / "catalogue.json").write_text(json.dumps(catalogue, indent=2, ensure_ascii=False), encoding="utf-8")

    damir = catalogue.get("open_damir", {}).get("ressources", [])
    for x in damir:   # documentation (xls)
        if x["format"] and x["format"].lower() in ("xls", "xlsx") or "lexique" in (x["titre"] or "").lower():
            try:
                c = requests.get(x["url"], timeout=120).content
                (SORTIE / ("damir_documentation" + Path(x["url"]).suffix if Path(x["url"]).suffix else "damir_documentation.xls")).write_bytes(c)
                log(f"documentation : {x['titre']}")
            except Exception as e:
                log(f"documentation : erreur {e!r}")
    mensuels = sorted([x for x in damir if (x["titre"] or "").upper().startswith("A")], key=lambda x: x["titre"])
    if mensuels:
        dernier = mensuels[-1]
        log(f"dernier fichier mensuel : {dernier['titre']} ({dernier['taille']} octets)")
        try:
            apercu_gz(dernier["url"], "damir")
        except Exception as e:
            log(f"aperçu : erreur {e!r}")


if __name__ == "__main__":
    main()
