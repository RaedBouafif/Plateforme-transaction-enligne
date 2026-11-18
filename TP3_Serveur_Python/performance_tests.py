
import os
import tempfile
import time

import csv_manager
from data_processing import classify_alert, creer_resultat, get_data, validate_data


def mesurer(fonction):
    """Retourne le temps (en secondes) mis par fonction() à s'exécuter."""
    debut = time.perf_counter()
    fonction()
    return time.perf_counter() - debut


def formater(secondes):
    """Met une durée en texte lisible (notation scientifique si très petite)."""
    return f"{secondes:.6f} s" if secondes >= 0.001 else f"{secondes:.2e} s"


def traiter_lot(n):
    """Valide et classe n mesures fabriquées automatiquement."""
    for i in range(n):
        mesure = {"temperature": (i % 100) - 10, "humidity": i % 101}
        if validate_data(mesure)[0]:
            classify_alert(mesure["temperature"], mesure["humidity"])


def fabriquer_csv(chemin, n):
    """Écrit un CSV de n lignes valides (un timestamp différent par ligne) pour tester l'import."""
    debut = 1767225600   # 2026-01-01 00:00:00 UTC
    with open(chemin, "w", encoding="utf-8") as f:
        f.write("timestamp,temperature,humidity\n")
        for i in range(n):
            date = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(debut + 5 * i))
            f.write(f"{date},25.0,50.0\n")


def run_performance_tests(source=None):
    """Lance les mesures de performance et retourne la liste des résultats."""
    mesures = {}   # nom de l'opération -> durée en secondes (opérations locales)
    resultats = []

    def ajouter(nom, donnees, limite_s, duree_s, detail=""):
        """Enregistre une mesure et la compare à sa limite."""
        mesures[nom] = duree_s
        resultats.append(creer_resultat(nom, donnees, f"< {limite_s} s", f"{formater(duree_s)} {detail}".strip(),
                                        duree_s < limite_s, duree_s * 1000))

    # Une seule mesure : moyenne sur 1000 appels
    d = mesurer(lambda: [validate_data({"temperature": 25.0, "humidity": 50.0}) for _ in range(1000)])
    ajouter("Validation (moyenne)", "1000 appels", 0.1, d / 1000, "par appel")
    d = mesurer(lambda: [classify_alert(25.0, 50.0) for _ in range(1000)])
    ajouter("Classification (moyenne)", "1000 appels", 0.1, d / 1000, "par appel")
    # Lots
    for n, limite in ((100, 0.5), (1000, 1), (10000, 5)):
        ajouter(f"Lot de {n} mesures", "validation + classification", limite, mesurer(lambda n=n: traiter_lot(n)))
    # Import CSV
    with tempfile.TemporaryDirectory() as dossier:
        for n, limite in ((1000, 5), (10000, 30)):
            chemin = os.path.join(dossier, f"perf_{n}.csv")
            fabriquer_csv(chemin, n)
            ajouter(f"Import CSV de {n} lignes", "pandas + contrôle ligne par ligne", limite,
                    mesurer(lambda c=chemin: csv_manager.import_csv(c)))

    # Réseau Firebase (si connecté)
    reseau_s = None
    if source is not None:
        reseau_s = get_data(source)["duree_ms"] / 1000
        resultats.append(creer_resultat("Lecture Firebase (réseau)", "1 lecture réelle", "< 5 s",
                                        f"{reseau_s:.6f} s", reseau_s < 5, reseau_s * 1000))
    else:
        resultats.append(creer_resultat("Lecture Firebase (réseau)", "Firebase non connecté", "information",
                                        "non mesuré", True, 0))

    # Comparaison : opération locale la plus lente (par appel unitaire exclu : on compare les mêmes unités)
    comparables = {k: v for k, v in mesures.items() if "moyenne" not in k}
    plus_lente = max(comparables, key=comparables.get)
    resultats.append(creer_resultat("Opération locale la plus lente", f"{len(comparables)} opérations comparées",
                                    "information", f"{plus_lente} ({comparables[plus_lente]:.4f} s)", True, 0))
    traitement_une_mesure = mesures["Validation (moyenne)"] + mesures["Classification (moyenne)"]
    if reseau_s is not None:
        rapport = reseau_s / traitement_une_mesure
        obtenu = f"réseau = {rapport:.0f} x le traitement local d'une mesure"
    else:
        obtenu = "traitement local d'une mesure = %.2e s (réseau non mesuré)" % traitement_une_mesure
    resultats.append(creer_resultat("Comparaison local / réseau", "1 mesure", "information", obtenu, True, 0))
    return resultats
