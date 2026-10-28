"""
Étape 1 : explorer les pages de téléchargement de l'open data de l'Assurance Maladie
(open-data-assurance-maladie.ameli.fr) et tester les vrais fichiers.
Lancement : python -m src.decouverte
"""
import json
import re
import zlib
from pathlib import Path
from urllib.parse import urljoin

import requests

SORTIE = Path("data/decouverte")
NAV = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
PAGES = {
    "damir_2025": "https://open-data-assurance-maladie.ameli.fr/depenses/download.php?Dir_Rep=Open_DAMIR&Annee=2025",
    "medic_2025": "https://open-data-assurance-maladie.ameli.fr/medicaments/download.php?Dir_Rep=Open_MEDIC_Base_Complete&Annee=2025",
    "lpp_2025": "https://open-data-assurance-maladie.ameli.fr/LPP/download.php?Dir_Rep=Open_LPP_Base_Complete&Annee=2025",
    "bio_2025": "https://open-data-assurance-maladie.ameli.fr/biologie/download.php?Dir_Rep=Open_BIO_Base_Complete&Annee=2025",
    "soins_ville_2025": "https://open-data-assurance-maladie.ameli.fr/depenses/download.php?Dir_Rep=Tables_N&Annee=2025",
}


def premieres_lignes(url, n=30):
    with requests.get(url, headers=NAV, stream=True, timeout=120) as r:
        r.raise_for_status()
        brut = b""
        for bloc in r.iter_content(1 << 16):
            brut += bloc
            if len(brut) > 4 << 20:
                break
    info = {"url_finale": r.url, "type": r.headers.get("content-type"), "taille": r.headers.get("content-length"),
            "debut_brut": brut[:8].hex()}
    if brut[:2] == b"\x1f\x8b":
        brut = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(brut)
        info["format"] = "gzip"
    elif brut[:2] == b"PK":
        info["format"] = "zip"
        return info
    texte = brut.decode("latin-1", errors="replace")
    info["lignes"] = texte.splitlines()[:n]
    return info


def main():
    SORTIE.mkdir(parents=True, exist_ok=True)
    resultat = {}
    for nom, url in PAGES.items():
        try:
            r = requests.get(url, headers=NAV, timeout=60)
            liens = sorted({urljoin(r.url, h) for h in re.findall(r'href=["\']([^"\']+)["\']', r.text)
                            if re.search(r"\.(csv|gz|zip|txt|xls|xlsx)(\?|$)", h, re.I)})
            res = {"code": r.status_code, "verification": "rification de s" in r.text, "liens": liens,
                   "texte": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))[:800]}
            if liens:
                try:
                    res["test_premier_fichier"] = premieres_lignes(liens[0])
                except Exception as e:
                    res["test_premier_fichier"] = {"erreur": repr(e)}
            resultat[nom] = res
            print(f"[decouverte] {nom} : {len(liens)} fichiers", flush=True)
        except Exception as e:
            resultat[nom] = {"erreur": repr(e)}
    (SORTIE / "pages_telechargement.json").write_text(json.dumps(resultat, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
