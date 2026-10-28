# Données de l'Assurance Maladie (France)

Données **réelles et ouvertes** de l'Assurance Maladie, collectées automatiquement depuis [open-data-assurance-maladie.ameli.fr](https://open-data-assurance-maladie.ameli.fr) (licence ouverte Etalab). Projet AssurIA, ENSIM.

- **Mis à jour le** : 28/10/2026
- **Fichiers traités** : 15

## Le principe de l'assurance maladie

Pour chaque soin, trois payeurs : la **Sécurité sociale** rembourse une partie de la *base de remboursement* (tarif officiel), la **mutuelle** (complémentaire santé) rembourse tout ou partie du reste selon son contrat, et l'assuré paie ce qui reste (**reste à charge**). Les dépassements d'honoraires (au-dessus de la base) ne sont pas remboursés par la Sécurité sociale.

Ces données donnent la partie **Sécurité sociale** : dépense totale, base de remboursement, montant remboursé, dépassement. La partie mutuelle se calcule avec le tableau de garanties de chaque contrat.

## Contenu

| Dossier | Base | Contenu |
| --- | --- | --- |
| `damir/` | Open DAMIR | `prestations_<année>.parquet` : totaux par mois, type de soin, âge, sexe, région. `specialites_<année>.parquet` : totaux par mois, spécialité du professionnel, type de soin, âge. `echantillon_dernier_mois.csv` : 20 000 vraies lignes |
| `medicaments/` | Open Medic | Médicaments remboursés, par classe, âge, sexe, région |
| `dispositifs_medicaux/` | Open LPP | Lunettes, audioprothèses et autres dispositifs remboursés |
| `biologie/` | Open Bio | Analyses de biologie remboursées |

## Colonnes d'Open DAMIR

| Colonne | Sens |
| --- | --- |
| `mois_remboursement` | Mois du remboursement (AAAAMM) |
| `code_prestation` | Type de soin (code PRS_NAT : consultation, pharmacie, optique…) |
| `tranche_age`, `sexe`, `region` | Le bénéficiaire des soins |
| `specialite_executant` | Spécialité du professionnel qui a réalisé le soin |
| `depense_eur` | Montant total payé au professionnel |
| `base_remboursement_eur` | Tarif officiel servant au calcul du remboursement |
| `rembourse_eur` | Montant remboursé par l'Assurance Maladie |
| `depassement_eur` | Dépassement d'honoraires |
| `quantite`, `nombre_actes` | Volume de soins |

Les montants négatifs sont des régularisations (annulations de remboursements déjà versés).

## Fichiers traités

| Fichier | Base | Lignes d'origine | Taille téléchargée |
| --- | --- | --- | --- |
| `A202501.csv.gz` | damir | 36 640 259 | 973.6 Mo |
| `A202502.csv.gz` | damir | 34 710 236 | 923.4 Mo |
| `A202503.csv.gz` | damir | 35 881 985 | 952.7 Mo |
| `A202504.csv.gz` | damir | 32 781 300 | 871.7 Mo |
| `A202505.csv.gz` | damir | 34 167 564 | 916.1 Mo |
| `A202506.csv.gz` | damir | 34 412 402 | 924.3 Mo |
| `A202507.csv.gz` | damir | 35 467 887 | 950.4 Mo |
| `A202508.csv.gz` | damir | 30 731 153 | 815.0 Mo |
| `A202509.csv.gz` | damir | 34 321 259 | 918.5 Mo |
| `A202510.csv.gz` | damir | 35 185 026 | 942.2 Mo |
| `A202511.csv.gz` | damir | 32 399 786 | 868.4 Mo |
| `A202512.csv.gz` | damir | 35 667 937 | 955.8 Mo |
| `OPEN_BIO_2025.zip` | bio | 316 799 | 3.9 Mo |
| `OPEN_LPP_2025.CSV.gz` | lpp | 812 459 | 10.8 Mo |
| `OPEN_MEDIC_2025.zip` | medic | 1 873 062 | 26.7 Mo |

## Mise à jour

Le workflow `.github/workflows/collecte.yml` tourne chaque semaine et traite les nouveaux fichiers publiés. Lancement à la main : onglet **Actions** → **Collecte** → **Run workflow**.

Les libellés des codes (types de soin, spécialités) sont dans le *descriptif des variables* publié par l'Assurance Maladie sur [data.gouv.fr](https://www.data.gouv.fr/datasets/open-damir-base-complete-sur-les-depenses-dassurance-maladie-interregimes).
