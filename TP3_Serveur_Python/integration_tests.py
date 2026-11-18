"""Tests d'intégration : lecture -> champs -> validation -> classification -> GUI -> CSV.

La source de données est injectable : données de test par défaut,
ou la vraie source Firebase si on la fournit (run_integration_tests(source)).
"""
import os
import tempfile

import csv_manager
import tmr_test
from data_processing import classify_alert, creer_resultat, executer_cas, traiter_cycle

HORLOGE_FIXE = lambda: 1794470400   # heure simulée constante


def source_de_test(donnees):
    """Fabrique une source de test qui renvoie toujours `donnees`."""
    return lambda: donnees


def source_en_panne():
    """Source de test qui simule Firebase injoignable."""
    raise ConnectionError("Firebase injoignable (simulation)")


def run_integration_tests(source=None):
    """Lance les tests d'intégration. Si `source` est donnée (Firebase réel), un test réel est ajouté."""
    resultats = []
    normale = {"Led_1": True, "temperature": 25.0, "humidity": 50.0}

    def flux_complet():
        """Mesure valide : GUI appelée, ligne écrite dans le CSV."""
        with tempfile.TemporaryDirectory() as dossier:
            chemin = os.path.join(dossier, "m.csv")
            appels = []
            r = traiter_cycle(source_de_test(normale), chemin, callback=appels.append)
            return f"ok={r['ok']} niveau={r['niveau']} callback={len(appels)} lignes_csv={csv_manager.compter_lignes(chemin)}"

    def champ_manquant():
        """Champ humidity absent : rejeté à l'étape 'champs', rien écrit."""
        with tempfile.TemporaryDirectory() as dossier:
            chemin = os.path.join(dossier, "m.csv")
            r = traiter_cycle(source_de_test({"temperature": 25.0}), chemin)
            return f"ok={r['ok']} etape={r['etape']} lignes_csv={csv_manager.compter_lignes(chemin)}"

    def firebase_injoignable():
        """Source en panne : erreur propre, pas de plantage, GUI informée."""
        with tempfile.TemporaryDirectory() as dossier:
            appels = []
            r = traiter_cycle(source_en_panne, os.path.join(dossier, "m.csv"), callback=appels.append)
            return f"ok={r['ok']} etape={r['etape']} callback={len(appels)}"

    def pas_de_doublon():
        """La même mesure lue deux fois n'est écrite qu'une fois."""
        with tempfile.TemporaryDirectory() as dossier:
            chemin = os.path.join(dossier, "m.csv")
            r1 = traiter_cycle(source_de_test(normale), chemin, horloge=HORLOGE_FIXE)
            r2 = traiter_cycle(source_de_test(normale), chemin, precedente=r1, horloge=HORLOGE_FIXE)
            return f"nouvelle2={r2['nouvelle']} lignes_csv={csv_manager.compter_lignes(chemin)}"

    def doublon_meme_timestamp():
        """save_measure refuse un timestamp déjà présent."""
        with tempfile.TemporaryDirectory() as dossier:
            chemin = os.path.join(dossier, "m.csv")
            a = csv_manager.save_measure(chemin, "2026-11-08 09:00:00", 25.0, 50.0)
            b = csv_manager.save_measure(chemin, "2026-11-08 09:00:00", 25.0, 50.0)
            return f"1re={a} 2e={b} lignes_csv={csv_manager.compter_lignes(chemin)}"

    def nouvelle_valeur_enregistree():
        """Une mesure différente est bien ajoutée."""
        with tempfile.TemporaryDirectory() as dossier:
            chemin = os.path.join(dossier, "m.csv")
            r1 = traiter_cycle(source_de_test(normale), chemin, horloge=lambda: 1794470400)
            autre = dict(normale, temperature=45.0)
            r2 = traiter_cycle(source_de_test(autre), chemin, precedente=r1, horloge=lambda: 1794470405)
            return f"niveau2={r2['niveau']} lignes_csv={csv_manager.compter_lignes(chemin)}"

    def timestamp_firebase():
        """Un champ timestamp optionnel venant de Firebase est utilisé tel quel."""
        with tempfile.TemporaryDirectory() as dossier:
            chemin = os.path.join(dossier, "m.csv")
            r = traiter_cycle(source_de_test(dict(normale, timestamp="2026-11-08 10:00:00")), chemin)
            return f"timestamp={r['timestamp']}"

    def valeur_invalide():
        """Humidité 105 : rejetée à la validation, rien écrit."""
        with tempfile.TemporaryDirectory() as dossier:
            chemin = os.path.join(dossier, "m.csv")
            r = traiter_cycle(source_de_test(dict(normale, humidity=105.0)), chemin)
            return f"ok={r['ok']} etape={r['etape']} lignes_csv={csv_manager.compter_lignes(chemin)}"

    cas = [
        ("Flux complet valide", "25/50, source de test", "ok=True niveau=LOW callback=1 lignes_csv=1", flux_complet),
        ("Champ manquant", "humidity absent", "ok=False etape=champs lignes_csv=0", champ_manquant),
        ("Firebase injoignable", "source en panne", "ok=False etape=firebase callback=1", firebase_injoignable),
        ("Pas de doublon CSV (même mesure)", "même mesure lue 2 fois", "nouvelle2=False lignes_csv=1", pas_de_doublon),
        ("Pas de doublon CSV (même timestamp)", "même timestamp écrit 2 fois", "1re=True 2e=False lignes_csv=1", doublon_meme_timestamp),
        ("Nouvelle valeur enregistrée", "25/50 puis 45/50", "niveau2=MEDIUM lignes_csv=2", nouvelle_valeur_enregistree),
        ("Timestamp Firebase optionnel", "champ timestamp présent", "timestamp=2026-11-08 10:00:00", timestamp_firebase),
        ("Valeur invalide rejetée", "humidity=105", "ok=False etape=validation lignes_csv=0", valeur_invalide),
    ]
    for nom, donnees, attendu, fonction in cas:
        resultats.append(executer_cas(nom, donnees, attendu, fonction))

    if source is not None:   # test avec la vraie source Firebase (CSV temporaire)
        def reel():
            with tempfile.TemporaryDirectory() as dossier:
                r = traiter_cycle(source, os.path.join(dossier, "m.csv"))
                return f"ok={r['ok']}" + ("" if r["ok"] else f" ({r['etape']})")
        resultats.append(executer_cas("Lecture Firebase réelle", "source Firebase", "ok=True", reel))
    return resultats


def run_tests_sur_import(resultat_import):
    """Teste les données d'un CSV importé (résultat de import_csv) : classification et accord TMR."""
    resultats = []
    if not resultat_import or not resultat_import.get("ok"):
        return [creer_resultat("Tests sur CSV importé", "aucun import valide", "import réussi",
                               "import impossible", False, 0,
                               (resultat_import or {}).get("erreur", "aucun import"))]
    df = resultat_import["df_valide"]
    comptes = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    desaccords = 0

    def classer():
        nonlocal desaccords
        for t, h in zip(df["temperature"], df["humidity"]):
            t, h = float(t), float(h)
            comptes[classify_alert(t, h)] += 1
            if tmr_test.tmr_classifier(t, h)[0] != classify_alert(t, h):
                desaccords += 1
        return len(df)

    resultats.append(executer_cas("CSV importé : classification des lignes valides",
                                   f"{len(df)} lignes valides", len(df), classer))
    resultats.append(creer_resultat("CSV importé : répartition des niveaux", f"{len(df)} lignes valides",
                                     "information", f"LOW={comptes['LOW']} MEDIUM={comptes['MEDIUM']} HIGH={comptes['HIGH']}",
                                     True, 0))
    resultats.append(creer_resultat("CSV importé : accord des 3 classifieurs TMR", f"{len(df)} lignes valides",
                                     "0 désaccord", f"{desaccords} désaccord(s)", desaccords == 0, 0))
    resultats.append(creer_resultat("CSV importé : lignes invalides détectées", f"{resultat_import['total']} lignes",
                                     "information", f"{resultat_import['valides']} valides / {resultat_import['invalides']} invalides",
                                     True, 0))
    return resultats
