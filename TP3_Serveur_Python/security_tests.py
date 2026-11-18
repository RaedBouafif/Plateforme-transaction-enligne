
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from unittest import mock

import data_processing
import firebase_config as cfg
from data_processing import creer_resultat, executer_cas

MARQUEUR = "FAUX-SECRET-A-NE-JAMAIS-AFFICHER"


def requete_http_get(url):
    """Fait un GET sans authentification et retourne le code HTTP (None si pas de réseau)."""
    try:
        with urllib.request.urlopen(url, timeout=5) as reponse:
            return reponse.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def _cle_utilisee():
    """Vérifie que connect_firebase() ouvre bien le fichier configuré dans firebase_config."""
    with tempfile.TemporaryDirectory() as dossier:
        faux = os.path.join(dossier, "serviceAccountKey.json")
        with open(faux, "w", encoding="utf-8") as f:
            f.write("{}")
        chemins_lus = []
        def espion(chemin):
            chemins_lus.append(chemin)
            raise ValueError("arrêt volontaire du test")
        with mock.patch.object(cfg, "CHEMIN_CLE", faux), \
                mock.patch.object(data_processing, "_charger_certificat", espion):
            data_processing.connect_firebase()
        return "oui" if chemins_lus == [faux] else "non"


def _gitignore_ok():
    """Vérifie que serviceAccountKey.json est listé dans .gitignore."""
    chemin = os.path.join(cfg.DOSSIER_PROJET, ".gitignore")
    if not os.path.isfile(chemin):
        return "pas de .gitignore"
    with open(chemin, encoding="utf-8") as f:
        lignes = [l.strip() for l in f]
    return "ignoré" if "serviceAccountKey.json" in lignes else "NON ignoré"


def _mauvais_identifiants():
    """Une fausse clé doit donner une erreur propre, sans afficher son contenu."""
    with tempfile.TemporaryDirectory() as dossier:
        faux = os.path.join(dossier, "faux.json")
        with open(faux, "w", encoding="utf-8") as f:
            json.dump({"type": "service_account", "private_key": MARQUEUR,
                       "client_email": "test@faux.iam.gserviceaccount.com"}, f)
        r = data_processing.connect_firebase(faux)
        propre = MARQUEUR not in r["message"] and dossier not in r["message"]
        return f"ok={r['ok']} message_propre={propre}"


def _clef_absente():
    """Fichier de clé inexistant : message clair sans chemin complet."""
    chemin = os.path.join(tempfile.gettempdir(), "dossier_secret", "absent.json")
    r = data_processing.connect_firebase(chemin)
    return f"ok={r['ok']} chemin_masque={'dossier_secret' not in r['message']}"


def _nettoyage():
    """nettoyer_message retire clé privée, e-mail du compte et chemins."""
    sale = ('Erreur C:\\Users\\Eleve\\TP3\\serviceAccountKey.json "private_key": "abc123" '
            "x@projet.iam.gserviceaccount.com -----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----")
    propre = cfg.nettoyer_message(sale)
    interdits = ["abc123", "AAAA", "Eleve", "x@projet", "BEGIN PRIVATE"]
    return "propre" if not any(m in propre for m in interdits) else "secret restant : " + propre


def _scan_code():
    """Cherche une vraie clé privée ou une clé d'API dans les fichiers .py / .md, et un accès à la clé dans la GUI."""
    motif_pem = re.compile("-----BEGIN [A-Z ]*PRIVATE KEY-----\\s*[A-Za-z0-9+/]{20,}")
    motif_api = re.compile("AIza[0-9A-Za-z_\\-]{30,}")
    problemes = []
    for nom in sorted(os.listdir(cfg.DOSSIER_PROJET)):
        if nom.endswith((".py", ".md", ".txt", ".json")) and nom != "serviceAccountKey.json":
            with open(os.path.join(cfg.DOSSIER_PROJET, nom), encoding="utf-8") as f:
                texte = f.read()
            if motif_pem.search(texte) or motif_api.search(texte):
                problemes.append(nom)
            if nom in ("interface.py", "main.py") and "private" + "_key" in texte:
                problemes.append(nom + " (accès à la clé)")
    return "aucun secret" if not problemes else "à vérifier : " + ", ".join(problemes)


PROTECTIONS = ("1) règles Firebase : '.read'/'.write' = 'auth != null' (ou règles par chemin) ; "
               "2) ne jamais commiter la clé ; 3) clé révocable : en cas de fuite, la supprimer dans la console Google Cloud "
               "et en générer une nouvelle ; 4) limiter les droits du compte de service ; "
               "5) valider toutes les données reçues ; 6) ne pas afficher d'erreurs brutes.")


def run_security_tests(requete=requete_http_get):
    """Lance les tests de sécurité. `requete` est injectable pour les tests hors ligne."""
    resultats = []

    # 1) Le fichier de clé configuré existe et porte le bon nom
    debut = time.perf_counter()
    present = os.path.isfile(cfg.CHEMIN_CLE)
    bon_nom = os.path.basename(cfg.CHEMIN_CLE) == "serviceAccountKey.json"
    resultats.append(creer_resultat(
        "Fichier de clé présent", "chemin de firebase_config.CHEMIN_CLE", "présent, nommé serviceAccountKey.json",
        f"présent={present} nom_correct={bon_nom}", present and bon_nom,
        (time.perf_counter() - debut) * 1000,
        "" if present else "placez serviceAccountKey.json dans le dossier du projet"))

    resultats.append(executer_cas("La clé configurée est celle utilisée", "connect_firebase() sans argument", "oui", _cle_utilisee))
    resultats.append(executer_cas("Clé listée dans .gitignore", ".gitignore", "ignoré", _gitignore_ok))

    # 2) Règles Firebase (information, non bloquant) : GET sans authentification
    debut = time.perf_counter()
    code = requete(cfg.DATABASE_URL + "/.json")
    if code == 200:
        obtenu, erreur = "base PUBLIQUE (lecture sans authentification)", "à protéger avant toute mise en production"
    elif code in (401, 403):
        obtenu, erreur = "base protégée (accès refusé sans authentification)", ""
    else:
        obtenu, erreur = "non vérifiable (réseau ou réponse inattendue)", ""
    resultats.append(creer_resultat("Règles Firebase (GET sans authentification)", "ma propre base uniquement",
                                    "information", obtenu, True, (time.perf_counter() - debut) * 1000, erreur))

    # 3) Mauvais identifiants et messages propres
    resultats.append(executer_cas("Mauvais identifiants : erreur propre", "fausse clé JSON",
                                  "ok=False message_propre=True", _mauvais_identifiants))
    resultats.append(executer_cas("Clé absente : message sans chemin", "fichier inexistant",
                                  "ok=False chemin_masque=True", _clef_absente))
    resultats.append(executer_cas("Nettoyage des messages d'erreur", "texte contenant des secrets", "propre", _nettoyage))
    resultats.append(executer_cas("Aucun secret dans le code", "fichiers du projet", "aucun secret", _scan_code))

    # 4) Protections proposées
    resultats.append(creer_resultat("Protections proposées", "bonnes pratiques", "information", PROTECTIONS, True, 0))
    return resultats
