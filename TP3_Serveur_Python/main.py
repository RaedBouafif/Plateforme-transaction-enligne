"""Point d'entrée du TP3.

    python main.py          -> lance l'interface graphique
"""
import argparse
import sys

import data_processing
import firebase_config as cfg
from data_processing import connect_firebase, creer_source_firebase, generate_report
from integration_tests import run_integration_tests
from performance_tests import run_performance_tests
from robustness_tests import run_robustness_tests
from security_tests import run_security_tests
from tmr_test import run_tmr_test
from unit_tests import run_unit_tests
from watchdog_test import run_watchdog_test


def construire_familles():
    """Retourne {nom de la famille: fonction(source) -> liste de résultats}.

    `source` (Firebase réel ou None) n'est utilisée que par l'intégration et la performance.
    """
    return {
        "Tests unitaires": lambda source: run_unit_tests(),
        "Tests d'intégration": lambda source: run_integration_tests(source),
        "Tests de performance": lambda source: run_performance_tests(source),
        "Tests de robustesse": lambda source: run_robustness_tests(),
        "Tests de sécurité": lambda source: run_security_tests(),
        "Test TMR": lambda source: run_tmr_test(),
        "Test Watchdog": lambda source: run_watchdog_test(),
    }


def lancer_tests_console():
    """Lance toutes les familles de tests, affiche le détail et écrit le rapport. Retourne 0 si tout réussit."""
    connexion = connect_firebase()
    source = creer_source_firebase(connexion["reference"]) if connexion["ok"] else None
    print("Firebase :", connexion["message"])
    if source is None:
        print("(mode hors ligne : les tests réels Firebase sont ignorés)")

    resultats = {}
    for nom, fonction in construire_familles().items():
        resultats[nom] = fonction(source)
        print(f"\n=== {nom} ===")
        for r in resultats[nom]:
            ligne = f"[{r['statut']:6}] {r['test']} | attendu: {r['attendu']} | obtenu: {r['obtenu']} | {r['duree_ms']} ms"
            if r["erreur"]:
                ligne += f" | erreur: {r['erreur']}"
            print(ligne)

    rapport = generate_report(resultats)
    print(f"\nTotal : {rapport['total']}  réussis : {rapport['reussis']}  échoués : {rapport['echoues']}")
    print("Rapports :", rapport["json"], "et", rapport["txt"])
    return 0 if rapport["echoues"] == 0 else 1


def main():
    """Lit les arguments puis lance la console ou l'interface."""
    parser = argparse.ArgumentParser(description="TP3 - Serveur Python de test et validation")
    parser.add_argument("--tests", action="store_true", help="lancer tous les tests en console (sans interface)")
    arguments = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # accents corrects dans la console Windows
    if arguments.tests:
        sys.exit(lancer_tests_console())
    import interface   # importé ici : tkinter n'est pas nécessaire en mode console
    interface.lancer_interface(construire_familles())


if __name__ == "__main__":
    main()
