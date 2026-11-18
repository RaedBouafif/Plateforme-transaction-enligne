import csv
import os

import pandas as pd

import firebase_config as cfg
from data_processing import validate_data

COLONNES = ["timestamp", "temperature", "humidity"]
FORMAT_DATE = "%Y-%m-%d %H:%M:%S"


def save_measure(chemin, timestamp, temperature, humidity):
    """Ajoute une mesure à la fin du CSV (crée le fichier avec l'en-tête si besoin).

    Retourne True si la ligne est écrite, False si ce timestamp existe déjà (pas de doublon).
    """
    os.makedirs(os.path.dirname(os.path.abspath(chemin)), exist_ok=True)
    existe = os.path.isfile(chemin) and os.path.getsize(chemin) > 0
    if existe:
        with open(chemin, newline="", encoding="utf-8") as f:
            deja_vus = {ligne[0] for ligne in csv.reader(f) if ligne}
        if str(timestamp) in deja_vus:
            return False
    with open(chemin, "a", newline="", encoding="utf-8") as f:
        ecrivain = csv.writer(f)
        if not existe:
            ecrivain.writerow(COLONNES)
        ecrivain.writerow([timestamp, temperature, humidity])
    return True


def compter_lignes(chemin):
    """Compte les lignes de mesures d'un CSV (sans l'en-tête). 0 si le fichier n'existe pas."""
    if not os.path.isfile(chemin):
        return 0
    with open(chemin, newline="", encoding="utf-8") as f:
        return max(0, sum(1 for ligne in csv.reader(f) if ligne) - 1)


def _resultat_erreur(message):
    """Résultat d'import en cas d'erreur de fichier (aucune ligne traitée)."""
    return {"ok": False, "erreur": message, "total": 0, "valides": 0, "invalides": 0,
            "doublons": 0, "lignes_invalides": [], "df_original": None, "df_valide": None}


def import_csv(chemin):
    """Importe un CSV avec pandas et contrôle chaque ligne SANS jamais corriger les données.

    Contrôles : colonnes, valeur manquante, non numérique, hors plage,
    date invalide, timestamp en double, date antérieure à la ligne précédente.
    Retourne un dictionnaire : ok, erreur, total, valides, invalides, doublons,
    lignes_invalides (liste avec numéro de ligne et raison), df_original
    (données lues, intactes) et df_valide (lignes acceptées).
    """
    if not os.path.isfile(chemin):
        return _resultat_erreur("Fichier CSV introuvable")
    try:
        # dtype=str : on garde le texte exact du fichier (rien n'est converti à la lecture)
        df = pd.read_csv(chemin, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return _resultat_erreur("Fichier CSV vide")
    except pd.errors.ParserError as e:
        return _resultat_erreur("CSV illisible (ligne avec trop de colonnes) : " + cfg.nettoyer_message(e)[:100])
    except Exception as e:
        return _resultat_erreur("Erreur de lecture du CSV : " + cfg.nettoyer_message(e)[:100])

    colonnes_absentes = [c for c in COLONNES if c not in df.columns]
    if colonnes_absentes:
        return _resultat_erreur("Colonnes manquantes : " + ", ".join(colonnes_absentes))

    df = df.fillna("")            # une ligne incomplète donne des cases vides
    df_original = df.copy()       # copie gardée telle quelle

    # Conversions (les valeurs non convertibles deviennent NaN / NaT, on les repère ensuite)
    temperatures = pd.to_numeric(df["temperature"].str.strip(), errors="coerce")
    humidites = pd.to_numeric(df["humidity"].str.strip(), errors="coerce")
    dates = pd.to_datetime(df["timestamp"].str.strip(), format=FORMAT_DATE, errors="coerce")

    lignes_invalides = []
    indices_valides = []
    timestamps_vus = set()
    derniere_date = None
    doublons = 0
    for i in range(len(df)):
        raisons = []
        brut = df.iloc[i]
        # --- date ---
        if dates.iloc[i] is pd.NaT:
            raisons.append("date manquante ou invalide")
        else:
            if brut["timestamp"].strip() in timestamps_vus:
                raisons.append("timestamp en double")
                doublons += 1
            elif derniere_date is not None and dates.iloc[i] < derniere_date:
                raisons.append("date antérieure à la ligne précédente")
        # --- température et humidité ---
        for nom, serie in (("température", temperatures), ("humidité", humidites)):
            colonne = "temperature" if nom == "température" else "humidity"
            if brut[colonne].strip() == "":
                raisons.append(f"{nom} manquante")
            elif pd.isna(serie.iloc[i]):
                raisons.append(f"{nom} non numérique")
        if not raisons:
            valide, message = validate_data({"temperature": float(temperatures.iloc[i]),
                                             "humidity": float(humidites.iloc[i])})
            if not valide:
                raisons.append(message)
        # --- bilan de la ligne ---
        if raisons:
            lignes_invalides.append({"ligne": i + 2, "timestamp": brut["timestamp"],
                                     "temperature": brut["temperature"], "humidity": brut["humidity"],
                                     "raison": " ; ".join(raisons)})
        else:
            indices_valides.append(i)
            timestamps_vus.add(brut["timestamp"].strip())
            derniere_date = dates.iloc[i]

    return {"ok": True, "erreur": "", "total": len(df), "valides": len(indices_valides),
            "invalides": len(lignes_invalides), "doublons": doublons,
            "lignes_invalides": lignes_invalides, "df_original": df_original,
            "df_valide": df_original.iloc[indices_valides].copy()}


def exporter_resultats(resultat, dossier):
    """Enregistre deux NOUVEAUX fichiers : mesures_valides.csv et mesures_rejetees.csv.

    Aucune correction automatique : les lignes invalides sont seulement mises à part,
    avec la colonne "raison". Le fichier d'origine n'est jamais modifié.
    """
    os.makedirs(dossier, exist_ok=True)
    chemin_valides = os.path.join(dossier, "mesures_valides.csv")
    chemin_rejetees = os.path.join(dossier, "mesures_rejetees.csv")
    resultat["df_valide"].to_csv(chemin_valides, index=False, encoding="utf-8")
    colonnes = ["ligne"] + COLONNES + ["raison"]
    pd.DataFrame(resultat["lignes_invalides"], columns=colonnes).to_csv(
        chemin_rejetees, index=False, encoding="utf-8")
    return chemin_valides, chemin_rejetees
