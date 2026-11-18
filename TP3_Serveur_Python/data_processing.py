
import json
import math
import os
import time

import firebase_config as cfg


# ----------------------------------------------------------------------
# Outils communs pour les résultats de tests
# ----------------------------------------------------------------------
def creer_resultat(test, donnees, attendu, obtenu, ok, duree_ms, erreur=""):
    """Construit un résultat de test (dictionnaire) utilisable par la console et la GUI."""
    return {
        "test": test,
        "donnees": str(donnees),
        "attendu": str(attendu),
        "obtenu": str(obtenu),
        "statut": "réussi" if ok else "échoué",
        "duree_ms": round(duree_ms, 3),
        "erreur": erreur,
    }


def executer_cas(test, donnees, attendu, fonction):
    """Exécute fonction() dans un try/except, mesure le temps et compare à attendu.

    Si la fonction plante, le test est marqué "échoué" sans arrêter le programme.
    """
    debut = time.perf_counter()
    erreur = ""
    try:
        obtenu = fonction()
    except Exception as e:  # on attrape tout pour ne jamais planter
        obtenu = "EXCEPTION"
        erreur = cfg.nettoyer_message(f"{type(e).__name__}: {e}")
    duree_ms = (time.perf_counter() - debut) * 1000
    return creer_resultat(test, donnees, attendu, obtenu, obtenu == attendu, duree_ms, erreur)


# ----------------------------------------------------------------------
# Connexion et lecture Firebase
# ----------------------------------------------------------------------
def _charger_certificat(chemin):
    """Charge le certificat du compte de service depuis le fichier JSON."""
    from firebase_admin import credentials
    return credentials.Certificate(chemin)


def connect_firebase(chemin_cle=None, url=None):
    """Se connecte à Firebase avec le fichier serviceAccountKey.json.

    Retourne un dictionnaire : {"ok": bool, "reference": ..., "message": str}.
    Les erreurs sont toujours renvoyées dans "message", nettoyées de tout secret.
    """
    chemin_cle = chemin_cle or cfg.CHEMIN_CLE
    url = url or cfg.DATABASE_URL
    if not os.path.isfile(chemin_cle):
        return {"ok": False, "reference": None,
                "message": "Fichier de clé introuvable : placez serviceAccountKey.json dans le dossier du projet."}
    try:
        certificat = _charger_certificat(chemin_cle)
        import firebase_admin
        from firebase_admin import db
        try:
            app = firebase_admin.get_app()          # déjà initialisée ?
        except ValueError:
            app = firebase_admin.initialize_app(certificat, {"databaseURL": url})
        reference = db.reference("/", app=app)
        reference.get()                              # lecture d'essai
        return {"ok": True, "reference": reference, "message": "Connecté à Firebase"}
    except ImportError:
        return {"ok": False, "reference": None,
                "message": "Bibliothèque firebase-admin absente : pip install -r requirements.txt"}
    except ValueError:
        # Certificat illisible : le texte de l'erreur pourrait contenir un morceau de la clé, on ne l'affiche pas
        return {"ok": False, "reference": None,
                "message": "Clé de service invalide ou refusée (vérifiez serviceAccountKey.json)"}
    except Exception as e:
        texte = cfg.nettoyer_message(str(e))[:150]
        return {"ok": False, "reference": None,
                "message": f"Échec de connexion Firebase ({type(e).__name__}) : {texte}"}


def creer_source_firebase(reference):
    """Retourne une fonction sans argument qui lit toute la base (source de données réelle)."""
    def source():
        return reference.get()
    return source


def get_data(source):
    """Lit les données via `source` (une fonction sans argument).

    La source peut être Firebase (creer_source_firebase) ou des données de test.
    Retourne {"ok", "donnees", "erreur", "duree_ms"} ; duree_ms = temps de lecture
    (réseau si source Firebase). Ne plante jamais.
    """
    debut = time.perf_counter()
    try:
        donnees = source()
    except Exception as e:
        duree = (time.perf_counter() - debut) * 1000
        return {"ok": False, "donnees": None, "duree_ms": duree,
                "erreur": "Firebase injoignable : " + cfg.nettoyer_message(f"{type(e).__name__}: {e}")}
    duree = (time.perf_counter() - debut) * 1000
    if not donnees:
        return {"ok": False, "donnees": None, "erreur": "Réponse Firebase vide", "duree_ms": duree}
    if not isinstance(donnees, dict):
        return {"ok": False, "donnees": None, "erreur": "Format de réponse inattendu", "duree_ms": duree}
    return {"ok": True, "donnees": donnees, "erreur": "", "duree_ms": duree}


# ----------------------------------------------------------------------
# Validation et classification
# ----------------------------------------------------------------------
def _est_nombre(valeur):
    """Vrai si valeur est un nombre réel fini (int ou float, pas bool, pas NaN, pas inf)."""
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        return False
    return math.isfinite(valeur)


def champs_manquants(donnees):
    """Liste les champs obligatoires absents (ou égaux à None)."""
    return [c for c in ("temperature", "humidity") if donnees.get(c) is None]


def validate_data(donnees):
    """Valide une mesure {"temperature": ..., "humidity": ...}.

    Retourne (True, "OK") ou (False, "raison du rejet").
    Règles : nombres finis, température -40..80, humidité 0..100.
    """
    if not isinstance(donnees, dict):
        return False, "données absentes ou format invalide"
    manquants = champs_manquants(donnees)
    if manquants:
        return False, "champ manquant : " + ", ".join(manquants)
    t, h = donnees["temperature"], donnees["humidity"]
    if not _est_nombre(t):
        return False, "température non numérique (ou NaN/inf)"
    if not _est_nombre(h):
        return False, "humidité non numérique (ou NaN/inf)"
    if not cfg.TEMP_MIN <= t <= cfg.TEMP_MAX:
        return False, f"température hors plage ({cfg.TEMP_MIN} à {cfg.TEMP_MAX})"
    if not cfg.HUM_MIN <= h <= cfg.HUM_MAX:
        return False, f"humidité hors plage ({cfg.HUM_MIN} à {cfg.HUM_MAX})"
    return True, "OK"


def classify_alert(temperature, humidity):
    """Classe une mesure : "HIGH", "MEDIUM" ou "LOW".

    HIGH est prioritaire sur tout ; sinon MEDIUM ; sinon LOW.
    Lève ValueError si une valeur n'est pas un nombre fini.
    """
    if not _est_nombre(temperature) or not _est_nombre(humidity):
        raise ValueError("classification impossible : valeur non numérique")
    if temperature > cfg.SEUIL_TEMP_ELEVE or humidity > cfg.SEUIL_HUM_ELEVE:
        return "HIGH"
    elif temperature > cfg.SEUIL_TEMP_MOYEN or humidity > cfg.SEUIL_HUM_MOYEN:
        return "MEDIUM"
    else:
        return "LOW"


# ----------------------------------------------------------------------
# Cycle complet : lecture -> champs -> validation -> classification -> GUI -> CSV
# ----------------------------------------------------------------------
def est_nouvelle_mesure(precedente, courante):
    """Décide si `courante` est une NOUVELLE mesure par rapport à `precedente`.

    - si les deux ont un "timestamp" venant de Firebase : nouvelle si le timestamp change ;
    - sinon (cas de l'ESP32 actuel) : nouvelle si temperature ou humidity change.
    Sert à ne pas écrire deux fois la même mesure dans le CSV.
    """
    if precedente is None:
        return True
    if precedente.get("timestamp_source") and courante.get("timestamp_source"):
        return precedente["timestamp_source"] != courante["timestamp_source"]
    return (precedente["temperature"], precedente["humidity"]) != (courante["temperature"], courante["humidity"])


def traiter_cycle(source, chemin_csv, callback=None, precedente=None, horloge=time.time):
    """Un cycle complet de supervision. Retourne un dictionnaire de résultat.

    - source : fonction sans argument (Firebase ou données de test)
    - callback : fonction appelée avec le résultat (la GUI s'en sert pour s'afficher)
    - precedente : résultat du cycle précédent (pour éviter les doublons)
    - horloge : fonction donnant l'heure (injectable pour les tests)
    Choix : chaque lecture réussie et valide compte comme "réception" pour le watchdog ;
    l'écriture CSV n'a lieu que pour une nouvelle mesure.
    """
    import csv_manager  # import ici pour éviter une importation circulaire

    resultat = {"ok": False, "etape": "firebase", "erreur": "", "temperature": None,
                "humidity": None, "niveau": None, "timestamp": None,
                "timestamp_source": None, "nouvelle": False, "enregistree": False,
                "duree_reseau_ms": 0.0, "duree_locale_ms": 0.0}
    lecture = get_data(source)
    resultat["duree_reseau_ms"] = lecture["duree_ms"]
    debut_local = time.perf_counter()
    if not lecture["ok"]:
        resultat["erreur"] = lecture["erreur"]
    else:
        donnees = lecture["donnees"]
        resultat["etape"] = "champs"
        manquants = champs_manquants(donnees)
        if manquants:
            resultat["erreur"] = "champ manquant : " + ", ".join(manquants)
        else:
            resultat["etape"] = "validation"
            valide, message = validate_data(donnees)
            if not valide:
                resultat["erreur"] = message
                resultat["temperature"] = donnees.get("temperature")
                resultat["humidity"] = donnees.get("humidity")
            else:
                resultat["temperature"] = donnees["temperature"]
                resultat["humidity"] = donnees["humidity"]
                resultat["niveau"] = classify_alert(donnees["temperature"], donnees["humidity"])
                # Horodatage : celui de Firebase s'il existe, sinon l'heure de réception du serveur
                if donnees.get("timestamp"):
                    resultat["timestamp_source"] = str(donnees["timestamp"])
                    resultat["timestamp"] = str(donnees["timestamp"])
                else:
                    resultat["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(horloge()))
                resultat["etape"] = "ok"
                resultat["ok"] = True
                resultat["nouvelle"] = est_nouvelle_mesure(precedente, resultat)
                if resultat["nouvelle"]:
                    resultat["enregistree"] = csv_manager.save_measure(
                        chemin_csv, resultat["timestamp"], resultat["temperature"], resultat["humidity"])
    resultat["duree_locale_ms"] = (time.perf_counter() - debut_local) * 1000
    if callback is not None:
        callback(resultat)
    return resultat


# ----------------------------------------------------------------------
# Rapport
# ----------------------------------------------------------------------
def generate_report(resultats_par_famille, dossier=None):
    """Écrit un rapport JSON et un rapport texte horodatés dans reports/.

    resultats_par_famille : {"nom de la famille": [liste de résultats]}.
    Retourne {"json": chemin, "txt": chemin, "total": n, "reussis": n, "echoues": n}.
    """
    dossier = dossier or cfg.DOSSIER_RAPPORTS
    os.makedirs(dossier, exist_ok=True)
    horodatage = time.strftime("%Y%m%d_%H%M%S")
    tous = [r for liste in resultats_par_famille.values() for r in liste]
    reussis = sum(1 for r in tous if r["statut"] == "réussi")
    resume = {"date": time.strftime("%Y-%m-%d %H:%M:%S"), "total": len(tous),
              "reussis": reussis, "echoues": len(tous) - reussis}

    chemin_json = os.path.join(dossier, f"rapport_{horodatage}.json")
    with open(chemin_json, "w", encoding="utf-8") as f:
        json.dump({"resume": resume, "familles": resultats_par_famille}, f,
                  ensure_ascii=False, indent=2)

    chemin_txt = os.path.join(dossier, f"rapport_{horodatage}.txt")
    with open(chemin_txt, "w", encoding="utf-8") as f:
        f.write(f"Rapport de tests TP3 - {resume['date']}\n")
        f.write(f"Total : {resume['total']}  réussis : {reussis}  échoués : {resume['echoues']}\n")
        for famille, liste in resultats_par_famille.items():
            f.write(f"\n== {famille} ==\n")
            for r in liste:
                f.write(f"[{r['statut']}] {r['test']} | données: {r['donnees']} | attendu: {r['attendu']} "
                        f"| obtenu: {r['obtenu']} | {r['duree_ms']} ms {r['erreur']}\n")
    return {"json": chemin_json, "txt": chemin_txt, "total": len(tous),
            "reussis": reussis, "echoues": len(tous) - reussis}
