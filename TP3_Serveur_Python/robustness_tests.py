
import os
import tempfile

import csv_manager
from data_processing import executer_cas, traiter_cycle

NORMALE = {"Led_1": False, "temperature": 25.0, "humidity": 50.0}


def _cycle(donnees):
    """Lance un cycle complet sur `donnees` et résume le résultat en une phrase."""
    with tempfile.TemporaryDirectory() as dossier:
        r = traiter_cycle(lambda: donnees, os.path.join(dossier, "m.csv"))
        return f"ok={r['ok']} etape={r['etape']}"


def _csv(contenu):
    """Importe un CSV créé à partir de `contenu` (texte) et résume le résultat."""
    with tempfile.TemporaryDirectory() as dossier:
        chemin = os.path.join(dossier, "test.csv")
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(contenu)
        r = csv_manager.import_csv(chemin)
        if not r["ok"]:
            return f"ok=False erreur={r['erreur']}"
        return f"ok=True valides={r['valides']} invalides={r['invalides']}"


def _interruption():
    """Firebase coupé puis rétabli : deux cycles successifs."""
    etat = {"n": 0}
    def source():
        etat["n"] += 1
        if etat["n"] == 1:
            raise ConnectionError("coupure simulée")
        return NORMALE
    with tempfile.TemporaryDirectory() as dossier:
        chemin = os.path.join(dossier, "m.csv")
        r1 = traiter_cycle(source, chemin)
        r2 = traiter_cycle(source, chemin)
    return f"cycle1 ok={r1['ok']} ; cycle2 ok={r2['ok']}"


def _csv_inexistant():
    """Import d'un fichier qui n'existe pas."""
    r = csv_manager.import_csv(os.path.join(tempfile.gettempdir(), "fichier_inexistant_tp3.csv"))
    return f"ok={r['ok']} erreur={r['erreur']}"


def run_robustness_tests():
    """Lance tous les cas de robustesse (chaque cas est protégé par try/except)."""
    cas = [
        ("Température manquante", "champ temperature absent", "ok=False etape=champs",
         lambda: _cycle({"humidity": 50.0})),
        ("Valeur None", "temperature = None", "ok=False etape=champs",
         lambda: _cycle({"temperature": None, "humidity": 50.0})),
        ("Température non numérique", "temperature = 'abc'", "ok=False etape=validation",
         lambda: _cycle({"temperature": "abc", "humidity": 50.0})),
        ("Humidité négative", "humidity = -5", "ok=False etape=validation",
         lambda: _cycle({"temperature": 25.0, "humidity": -5})),
        ("Humidité supérieure à 100", "humidity = 105", "ok=False etape=validation",
         lambda: _cycle({"temperature": 25.0, "humidity": 105})),
        ("Réponse Firebase vide ({})", "réponse {}", "ok=False etape=firebase", lambda: _cycle({})),
        ("Réponse Firebase vide (None)", "réponse None", "ok=False etape=firebase", lambda: _cycle(None)),
        ("Réponse de mauvais format", "réponse = liste", "ok=False etape=firebase", lambda: _cycle([1, 2])),
        ("Interruption Firebase simulée", "1er accès en erreur puis rétabli",
         "cycle1 ok=False ; cycle2 ok=True", _interruption),
        ("CSV inexistant", "fichier absent", "ok=False erreur=Fichier CSV introuvable", _csv_inexistant),
        ("CSV avec colonne manquante", "colonne humidity absente", "ok=False erreur=Colonnes manquantes : humidity",
         lambda: _csv("timestamp,temperature\n2026-11-08 09:00:00,25.0\n")),
        ("CSV avec lignes incomplètes", "ligne sans humidity et ligne sans température",
         "ok=True valides=1 invalides=2",
         lambda: _csv("timestamp,temperature,humidity\n2026-11-08 09:00:00,25.0,50\n"
                      "2026-11-08 09:00:05,26.0\n2026-11-08 09:00:10\n")),
        ("CSV vide", "fichier de 0 octet", "ok=False erreur=Fichier CSV vide", lambda: _csv("")),
        ("CSV avec NaN écrit en texte", "temperature = nan", "ok=True valides=0 invalides=1",
         lambda: _csv("timestamp,temperature,humidity\n2026-11-08 09:00:00,nan,50\n")),
    ]
    return [executer_cas(nom, donnees, attendu, fonction) for nom, donnees, attendu, fonction in cas]
