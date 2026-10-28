"""
Étape 1 : repérer les fichiers open data de l'Assurance Maladie sur data.gouv.fr
et tester s'ils sont téléchargeables automatiquement (certains sites demandent une vérification humaine).
Lancement : python -m src.decouverte
"""
import json
from pathlib import Path

import requests

SORTIE = Path("data/decouverte")
API = "https://www.data.gouv.fr/api/1/datasets/"
JEUX = [
    "open-damir-base-complete-sur-les-depenses-dassurance-maladie-interregimes",
    "open-medic-base-complete-sur-les-depenses-de-medicaments-interregimes",
    "open-bio-base-complete-sur-les-depenses-de-biologie-medicale-interregimes",
    "open-lpp-base-complete-sur-les-depenses-de-dispositifs-medicaux-inscrits-a-la-liste-de-produits-et-prestations-lpp-interregimes",
    "open-phmev-bases-sur-les-prescriptions-hospitalieres-de-medicaments-delivrees-en-ville",
    "donnees-nationales-sur-les-depenses-dassurance-maladie-relatives-aux-soins-de-ville",
    "donnees-nationales-sur-les-depenses-dassurance-maladie-relatives-aux-etablissements-de-sante-prives",
    "open-ccam-national",
]
NAV = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def tester(url):
    """Télécharge les premiers octets : fichier réel, ou page de vérification ?"""
    try:
        with requests.get(url, headers=NAV, stream=True, timeout=60, allow_redirects=True) as r:
            debut = next(r.iter_content(2048), b"")
            html = b"<html" in debut[:600].lower() or b"<!doctype" in debut[:600].lower()
            verif = b"rification de s" in debut or b"challenge" in debut.lower()
            return {"code": r.status_code, "url_finale": r.url, "type": r.headers.get("content-type"),
                    "taille": r.headers.get("content-length"),
                    "statut": "bloqué (vérification humaine)" if verif else "page web" if html else "fichier OK",
                    "debut": debut[:300].decode("latin-1", errors="replace")}
    except Exception as e:
        return {"statut": f"erreur {e!r}"}


def main():
    SORTIE.mkdir(parents=True, exist_ok=True)
    catalogue = {}
    for slug in JEUX:
        try:
            d = requests.get(API + slug + "/", timeout=60).json()
        except Exception as e:
            catalogue[slug] = {"erreur": repr(e)}
            continue
        res = []
        for i, x in enumerate(d.get("resources", [])):
            r = {"titre": x.get("title"), "url": x.get("url"), "format": x.get("format"), "taille": x.get("filesize")}
            if i < 3 or (x.get("format") or "").lower() in ("xls", "xlsx"):
                r["test"] = tester(x["url"])
            res.append(r)
        catalogue[slug] = {"titre": d.get("title"), "licence": d.get("license"), "ressources": res}
        print(f"[decouverte] {d.get('title')} : {len(res)} fichiers", flush=True)
    (SORTIE / "catalogue.json").write_text(json.dumps(catalogue, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
