
import os
import re

# Dossier qui contient ce fichier (= dossier du projet)
DOSSIER_PROJET = os.path.dirname(os.path.abspath(__file__))

# --- Firebase ---------------------------------------------------------
# Chemin du fichier de clé du compte de service (à modifier si besoin)
CHEMIN_CLE = os.path.join(DOSSIER_PROJET, "serviceAccountKey.json")
# URL de la base Realtime Database de l'étudiant
DATABASE_URL = "https://esp32-iot-tp-default-rtdb.europe-west1.firebasedatabase.app"

# --- Fichiers ---------------------------------------------------------
CHEMIN_CSV = os.path.join(DOSSIER_PROJET, "data", "mesures.csv")
DOSSIER_RAPPORTS = os.path.join(DOSSIER_PROJET, "reports")

# --- Temps (en secondes) ----------------------------------------------
INTERVALLE_ENVOI = 5          # l'ESP32 envoie une mesure toutes les 5 s
DELAI_MAX_WATCHDOG = 30       # au-delà : "délai dépassé"
INTERVALLE_SUPERVISION = 3    # le serveur interroge Firebase toutes les 3 s

# --- Plage de validation ----------------------------------------------
# Capteur DHT22 : température de -40 à 80 °C, humidité de 0 à 100 %
TEMP_MIN, TEMP_MAX = -40.0, 80.0
HUM_MIN, HUM_MAX = 0.0, 100.0

# --- Seuils de classification -----------------------------------------
SEUIL_TEMP_MOYEN, SEUIL_HUM_MOYEN = 40, 70   # au-dessus : MEDIUM
SEUIL_TEMP_ELEVE, SEUIL_HUM_ELEVE = 60, 80   # au-dessus : HIGH


def nettoyer_message(message):
    """Retire d'un message tout ce qui ressemble à un secret ou à un chemin.

    On l'utilise avant d'afficher une erreur dans l'interface, la console
    ou les rapports, pour ne jamais divulguer la clé.
    """
    texte = str(message)
    # Bloc de clé privée complet ou coupé
    texte = re.sub(r"-----BEGIN[\s\S]*?(-----END[^-]*-----|$)", "[clé masquée]", texte)
    # Champ "private_key": "...."
    texte = re.sub(r'"?private_key(_id)?"?\s*[:=]\s*"?[^",}\s]*"?', "[clé masquée]", texte)
    # Adresse e-mail du compte de service
    texte = re.sub(r"[\w.\-]+@[\w.\-]*gserviceaccount\.com", "[compte masqué]", texte)
    # Clé d'API de type AIza...
    texte = re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "[clé masquée]", texte)
    # Chemins Windows (C:\...) et chemins vers un .json
    texte = re.sub(r"[A-Za-z]:\\[^\s'\"]*", "[chemin masqué]", texte)
    texte = re.sub(r"/[^\s'\"]*\.json", "[chemin masqué]", texte)
    return texte
