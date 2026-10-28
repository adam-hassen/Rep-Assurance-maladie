"""
Collecte automatique des données ouvertes de l'Assurance Maladie (open-data-assurance-maladie.ameli.fr).

Bases collectées :
  - Open DAMIR : toutes les dépenses remboursées par l'Assurance Maladie, un fichier par mois (~1 Go compressé).
  - Open Medic : médicaments remboursés (par an).
  - Open LPP   : dispositifs médicaux remboursés (lunettes, audioprothèses, pansements…) (par an).
  - Open Bio   : analyses de biologie remboursées (par an).

Les fichiers bruts sont trop gros pour GitHub (limite 100 Mo) : on les résume (totaux par mois, âge, sexe,
région, type de soin) et on garde un échantillon de vraies lignes. Un fichier n'est traité qu'une fois
(data/manifest.json) ; chaque lancement traite les nouveaux fichiers.

Lancement :  python -m src.collecte
"""
from __future__ import annotations

import gzip
import io
import json
import os
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests

DATA = Path("data")
TMP = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "ameli"
MANIFEST = DATA / "manifest.json"
NAV = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
SITE = "https://open-data-assurance-maladie.ameli.fr"
ANNEES = [int(a) for a in os.environ.get("ANNEES", "2025").split(",")]
MAX_FICHIERS = int(os.environ.get("MAX_FICHIERS", "14"))      # fichiers lourds traités par lancement
TAILLE_MAX_SORTIE = 90 * 1024 * 1024

PAGES = {
    "damir": "/depenses/download.php?Dir_Rep=Open_DAMIR&Annee={a}",
    "medic": "/medicaments/download.php?Dir_Rep=Open_MEDIC_Base_Complete&Annee={a}",
    "lpp": "/LPP/download.php?Dir_Rep=Open_LPP_Base_Complete&Annee={a}",
    "bio": "/biologie/download.php?Dir_Rep=Open_BIO_Base_Complete&Annee={a}",
}

# Open DAMIR : colonnes gardées et leur sens
DAMIR_AXES = {
    "FLX_ANN_MOI": "mois_remboursement", "AGE_BEN_SNDS": "tranche_age", "BEN_SEX_COD": "sexe",
    "BEN_RES_REG": "region", "PRS_NAT": "code_prestation", "PSE_SPE_SNDS": "specialite_executant",
    "ASU_NAT": "nature_assurance",
}
DAMIR_MONTANTS = {
    "PRS_PAI_MNT": "depense_eur", "PRS_REM_BSE": "base_remboursement_eur", "PRS_REM_MNT": "rembourse_eur",
    "PRS_DEP_MNT": "depassement_eur", "PRS_ACT_QTE": "quantite", "PRS_ACT_NBR": "nombre_actes",
}
AGES = {0: "0-19 ans", 20: "20-29 ans", 30: "30-39 ans", 40: "40-49 ans", 50: "50-59 ans", 60: "60-69 ans",
        70: "70-79 ans", 80: "80 ans et +", 99: "inconnu"}
SEXES = {1: "homme", 2: "femme", 9: "inconnu"}
REGIONS = {5: "Régions et Départements d'outre-mer", 11: "Île-de-France", 24: "Centre-Val de Loire",
           27: "Bourgogne-Franche-Comté", 28: "Normandie", 32: "Hauts-de-France", 44: "Grand Est",
           52: "Pays de la Loire", 53: "Bretagne", 75: "Nouvelle-Aquitaine", 76: "Occitanie",
           84: "Auvergne-Rhône-Alpes", 93: "Provence-Alpes-Côte d'Azur", 94: "Corse", 99: "inconnue", 0: "inconnue"}


def log(msg: str) -> None:
    print(f"[collecte] {datetime.now(timezone.utc):%H:%M:%S} {msg}", flush=True)


# ------------------------------------------------------------------ téléchargement
def liens(base: str, annee: int) -> list[str]:
    r = requests.get(SITE + PAGES[base].format(a=annee), headers=NAV, timeout=60)
    r.raise_for_status()
    return sorted({urljoin(r.url, h) for h in re.findall(r'href=["\']([^"\']+)["\']', r.text) if "download_file" in h})


def nom_fichier(url: str) -> str:
    return url.split("file=")[-1].split("/")[-1]


def telecharger(url: str, chemin: Path, essais: int = 6) -> None:
    """Le site n'accepte qu'un téléchargement à la fois : on attend et on réessaie si besoin."""
    for i in range(essais):
        with requests.get(url, headers=NAV, stream=True, timeout=300) as r:
            r.raise_for_status()
            if "text/html" in r.headers.get("content-type", ""):
                log(f"  refusé par le site (limite de téléchargement), nouvel essai dans {60 * (i + 1)} s")
                time.sleep(60 * (i + 1))
                continue
            with open(chemin, "wb") as f:
                for bloc in r.iter_content(8 << 20):
                    f.write(bloc)
        log(f"  téléchargé : {chemin.name} ({chemin.stat().st_size / 1e6:,.0f} Mo)")
        return
    raise RuntimeError("téléchargement refusé après plusieurs essais")


# ------------------------------------------------------------------ Open DAMIR
def traiter_damir(chemin: Path, nom: str) -> dict:
    """Résume un mois d'Open DAMIR : totaux par mois x prestation x âge x sexe x région, et par spécialité."""
    import pyarrow as pa
    import pyarrow.csv as pcsv
    colonnes = list(DAMIR_AXES) + list(DAMIR_MONTANTS)
    types = {**{c: pa.float64() for c in DAMIR_MONTANTS}, **{c: pa.string() for c in DAMIR_AXES}}
    lecteur = pcsv.open_csv(pa.input_stream(str(chemin), compression="gzip"),
                            read_options=pcsv.ReadOptions(block_size=256 << 20),
                            parse_options=pcsv.ParseOptions(delimiter=";"),
                            convert_options=pcsv.ConvertOptions(include_columns=colonnes, column_types=types))
    morceaux_p, morceaux_s, lignes, echantillon = [], [], 0, []
    for lot in lecteur:
        bloc = lot.to_pandas()
        lignes += len(bloc)
        for c in DAMIR_AXES:
            bloc[c] = pd.to_numeric(bloc[c], errors="coerce").fillna(-1).astype("int32")
        if len(echantillon) < 1:
            echantillon.append(bloc.sample(min(len(bloc), 20_000), random_state=0))
        p = bloc.groupby(["FLX_ANN_MOI", "PRS_NAT", "AGE_BEN_SNDS", "BEN_SEX_COD", "BEN_RES_REG"],
                         observed=True)[list(DAMIR_MONTANTS)].sum()
        s = bloc.groupby(["FLX_ANN_MOI", "PSE_SPE_SNDS", "PRS_NAT", "AGE_BEN_SNDS"],
                         observed=True)[list(DAMIR_MONTANTS)].sum()
        morceaux_p.append(p)
        morceaux_s.append(s)
        if lignes // 10_000_000 != (lignes - len(bloc)) // 10_000_000:
            log(f"  {lignes:,} lignes lues")
    prest = pd.concat(morceaux_p).groupby(level=[0, 1, 2, 3, 4]).sum().reset_index()
    spec = pd.concat(morceaux_s).groupby(level=[0, 1, 2, 3]).sum().reset_index()
    ech = pd.concat(echantillon)
    return {"prestations": prest, "specialites": spec, "echantillon": ech, "lignes": lignes}


def lisible_damir(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={**DAMIR_AXES, **DAMIR_MONTANTS})
    if "tranche_age" in df:
        df["tranche_age"] = df["tranche_age"].map(AGES).fillna("inconnu")
    if "sexe" in df:
        df["sexe"] = df["sexe"].map(SEXES).fillna("inconnu")
    if "region" in df:
        df["region"] = df["region"].map(REGIONS).fillna(df["region"].astype(str))
    for c in DAMIR_MONTANTS.values():
        if c in df:
            df[c] = df[c].round(2)
    return df


def ajouter(chemin: Path, nouveau: pd.DataFrame, cle: str) -> None:
    """Ajoute les lignes d'un mois à un fichier annuel (en remplaçant ce mois s'il existait déjà)."""
    if chemin.exists():
        ancien = pd.read_parquet(chemin)
        ancien = ancien[~ancien[cle].isin(nouveau[cle].unique())]
        nouveau = pd.concat([ancien, nouveau], ignore_index=True)
    nouveau.sort_values(list(nouveau.columns[:3])).to_parquet(chemin, index=False, compression="zstd")


# ------------------------------------------------------------------ Open Medic, LPP, Bio
def lire_tableau(chemin: Path) -> pd.DataFrame:
    if zipfile.is_zipfile(chemin):
        with zipfile.ZipFile(chemin) as z:
            interne = max(z.namelist(), key=lambda n: z.getinfo(n).file_size)
            with z.open(interne) as f:
                brut = f.read()
    else:
        with open(chemin, "rb") as f:
            brut = f.read()
        if brut[:2] == b"\x1f\x8b":
            brut = gzip.decompress(brut)
    texte = brut.decode("latin-1")
    sep = ";" if texte[:2000].count(";") > texte[:2000].count(",") else ","
    df = pd.read_csv(io.StringIO(texte), sep=sep, low_memory=False, dtype=str)
    for c in df.columns:      # montants : virgule ou point décimal
        if re.search(r"(REM|BSE|BOITES|QTE|DEP|MNT|NBR|DEN|MONTANT)", c, re.I):
            df[c] = pd.to_numeric(df[c].str.replace(" ", "").str.replace(",", "."), errors="coerce")
    return df


def resumer_tableau(df: pd.DataFrame) -> pd.DataFrame:
    """Garde le fichier entier s'il tient ; sinon additionne les montants en retirant
    les colonnes les plus détaillées (code produit…) jusqu'à tenir sous la limite de GitHub."""
    montants = [c for c in df.columns if re.search(r"(REM|BSE|BOITES|QTE|DEP|MNT|NBR|DEN|MONTANT)", c, re.I)
                and pd.api.types.is_numeric_dtype(df[c])]
    axes = [c for c in df.columns if c not in montants]
    while True:
        test = df if axes == [c for c in df.columns if c not in montants] else \
            df.groupby(axes, dropna=False, observed=True)[montants].sum().reset_index()
        buf = io.BytesIO()
        test.to_parquet(buf, index=False, compression="zstd")
        if buf.tell() <= TAILLE_MAX_SORTIE or len(axes) <= 3:
            return test
        plus_detaille = max(axes, key=lambda c: df[c].nunique())
        log(f"  trop gros ({buf.tell() / 1e6:,.0f} Mo) : on retire la colonne {plus_detaille}")
        axes.remove(plus_detaille)


def enregistrer(message: str) -> None:
    """Sur GitHub : enregistre dans le dépôt après chaque fichier, pour ne rien perdre si le passage s'arrête."""
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    import subprocess
    ecrire_readme(json.loads(MANIFEST.read_text()))
    cmd = 'git add data/ README.md && (git diff --cached --quiet || (git commit -qm "{m}" && git pull -q --rebase && git push -q))'
    subprocess.run(cmd.format(m=message), shell=True, check=False)


# ------------------------------------------------------------------ programme principal
def main() -> int:
    DATA.mkdir(exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    traites = 0
    for annee in ANNEES:
        for base in PAGES:
            try:
                urls = liens(base, annee)
            except Exception as e:
                log(f"{base} {annee} : page inaccessible ({e!r})")
                continue
            log(f"{base} {annee} : {len(urls)} fichier(s)")
            for url in urls:
                nom = nom_fichier(url)
                if nom in manifest or traites >= MAX_FICHIERS:
                    continue
                chemin = TMP / nom
                try:
                    frais = [u for u in liens(base, annee) if nom_fichier(u) == nom]   # le jeton du lien expire
                    telecharger(frais[0] if frais else url, chemin)
                    if base == "damir":
                        r = traiter_damir(chemin, nom)
                        dossier = DATA / "damir"
                        dossier.mkdir(exist_ok=True)
                        ajouter(dossier / f"prestations_{annee}.parquet", lisible_damir(r["prestations"]), "mois_remboursement")
                        ajouter(dossier / f"specialites_{annee}.parquet", lisible_damir(r["specialites"]), "mois_remboursement")
                        lisible_damir(r["echantillon"]).to_csv(dossier / "echantillon_dernier_mois.csv", index=False, sep=";")
                        info = {"lignes": r["lignes"]}
                    else:
                        df = lire_tableau(chemin)
                        dossier = DATA / {"medic": "medicaments", "lpp": "dispositifs_medicaux", "bio": "biologie"}[base]
                        dossier.mkdir(exist_ok=True)
                        resume = resumer_tableau(df)
                        resume.to_parquet(dossier / f"open_{base}_{annee}.parquet", index=False, compression="zstd")
                        df.head(20_000).to_csv(dossier / f"echantillon_{annee}.csv", index=False, sep=";")
                        info = {"lignes": len(df), "colonnes": list(map(str, df.columns)),
                                "lignes_resume": len(resume), "colonnes_resume": list(map(str, resume.columns))}
                    manifest[nom] = {"base": base, "annee": annee, "url": url.split("token=")[0] + "…",
                                     "taille_mo": round(chemin.stat().st_size / 1e6, 1),
                                     "traite_le": datetime.now(timezone.utc).isoformat(timespec="seconds"), **info}
                    traites += 1
                    log(f"  {nom} : traité")
                except Exception as e:
                    log(f"  {nom} : ERREUR {e!r}")
                finally:
                    chemin.unlink(missing_ok=True)
                    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True))
                    enregistrer(f"Données : {nom}")
    ecrire_readme(manifest)
    log(f"Terminé : {traites} fichier(s) traité(s) ; {len(manifest)} au total")
    return 0


# ------------------------------------------------------------------ README
def ecrire_readme(manifest: dict) -> None:
    n = lambda x: f"{x:,.0f}".replace(",", " ")
    l = ["# Données de l'Assurance Maladie (France)", "",
         "Données **réelles et ouvertes** de l'Assurance Maladie, collectées automatiquement depuis "
         "[open-data-assurance-maladie.ameli.fr](https://open-data-assurance-maladie.ameli.fr) "
         "(licence ouverte Etalab). Projet AssurIA, ENSIM.", "",
         f"- **Mis à jour le** : {datetime.now(timezone.utc):%d/%m/%Y}",
         f"- **Fichiers traités** : {len(manifest)}", "",
         "## Le principe de l'assurance maladie", "",
         "Pour chaque soin, trois payeurs : la **Sécurité sociale** rembourse une partie de la *base de remboursement* "
         "(tarif officiel), la **mutuelle** (complémentaire santé) rembourse tout ou partie du reste selon son contrat, "
         "et l'assuré paie ce qui reste (**reste à charge**). Les dépassements d'honoraires (au-dessus de la base) "
         "ne sont pas remboursés par la Sécurité sociale.", "",
         "Ces données donnent la partie **Sécurité sociale** : dépense totale, base de remboursement, montant remboursé, "
         "dépassement. La partie mutuelle se calcule avec le tableau de garanties de chaque contrat.", "",
         "## Contenu", "", "| Dossier | Base | Contenu |", "| --- | --- | --- |",
         "| `damir/` | Open DAMIR | `prestations_<année>.parquet` : totaux par mois, type de soin, âge, sexe, région. "
         "`specialites_<année>.parquet` : totaux par mois, spécialité du professionnel, type de soin, âge. "
         "`echantillon_dernier_mois.csv` : 20 000 vraies lignes |",
         "| `medicaments/` | Open Medic | Médicaments remboursés, par classe, âge, sexe, région |",
         "| `dispositifs_medicaux/` | Open LPP | Lunettes, audioprothèses et autres dispositifs remboursés |",
         "| `biologie/` | Open Bio | Analyses de biologie remboursées |", "",
         "## Colonnes d'Open DAMIR", "", "| Colonne | Sens |", "| --- | --- |",
         "| `mois_remboursement` | Mois du remboursement (AAAAMM) |",
         "| `code_prestation` | Type de soin (code PRS_NAT : consultation, pharmacie, optique…) |",
         "| `tranche_age`, `sexe`, `region` | Le bénéficiaire des soins |",
         "| `specialite_executant` | Spécialité du professionnel qui a réalisé le soin |",
         "| `depense_eur` | Montant total payé au professionnel |",
         "| `base_remboursement_eur` | Tarif officiel servant au calcul du remboursement |",
         "| `rembourse_eur` | Montant remboursé par l'Assurance Maladie |",
         "| `depassement_eur` | Dépassement d'honoraires |",
         "| `quantite`, `nombre_actes` | Volume de soins |", "",
         "Les montants négatifs sont des régularisations (annulations de remboursements déjà versés).", ""]
    if manifest:
        l += ["## Fichiers traités", "", "| Fichier | Base | Lignes d'origine | Taille téléchargée |", "| --- | --- | --- | --- |"]
        for k, v in sorted(manifest.items()):
            l.append(f"| `{k}` | {v['base']} | {n(v.get('lignes', 0))} | {v['taille_mo']} Mo |")
    l += ["", "## Mise à jour", "",
          "Le workflow `.github/workflows/collecte.yml` tourne chaque semaine et traite les nouveaux fichiers publiés. "
          "Lancement à la main : onglet **Actions** → **Collecte** → **Run workflow**.", "",
          "Les libellés des codes (types de soin, spécialités) sont dans le *descriptif des variables* publié par "
          "l'Assurance Maladie sur [data.gouv.fr](https://www.data.gouv.fr/datasets/open-damir-base-complete-sur-les-depenses-dassurance-maladie-interregimes).", ""]
    Path("README.md").write_text("\n".join(l), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
