"""Watchdog : surveille que les mesures arrivent régulièrement.

Principe : on mémorise l'heure de la dernière mesure reçue. Si le temps écoulé
dépasse delai_max (30 s par défaut, alors que l'ESP32 envoie toutes les 5 s),
la communication est déclarée perdue. Un petit retard (ex. 8 s) ne déclenche rien.
"""
import time

import firebase_config as cfg
from data_processing import creer_resultat, executer_cas

ATTENTE = "aucune mesure reçue"
ACTIVE = "communication active"
DEPASSE = "délai dépassé"
RETABLIE = "communication rétablie"


class Watchdog:
    """Chien de garde : l'horloge est injectable (horloge=time.time par défaut)."""

    def __init__(self, delai_max=cfg.DELAI_MAX_WATCHDOG, horloge=time.time):
        """Initialise le watchdog sans aucune mesure reçue."""
        self.delai_max = delai_max
        self.horloge = horloge
        self.derniere_mesure = None   # heure de la dernière mesure
        self.en_defaut = False        # vrai si le délai a été dépassé
        self.etat_courant = ATTENTE

    def enregistrer_mesure(self):
        """Appelée à chaque réception : mémorise l'heure et met à jour l'état."""
        self.derniere_mesure = self.horloge()
        if self.en_defaut:
            self.etat_courant = RETABLIE   # on revient après une coupure
            self.en_defaut = False
        else:
            self.etat_courant = ACTIVE

    def temps_ecoule(self):
        """Retourne les secondes écoulées depuis la dernière mesure (None si aucune)."""
        if self.derniere_mesure is None:
            return None
        return self.horloge() - self.derniere_mesure

    def etat(self):
        """Retourne l'état actuel (le délai doit être STRICTEMENT dépassé pour alerter)."""
        ecoule = self.temps_ecoule()
        if ecoule is not None and ecoule > self.delai_max:
            self.en_defaut = True
            self.etat_courant = DEPASSE
        return self.etat_courant


def run_watchdog_test():
    """Teste les états du watchdog avec une horloge simulée (aucune vraie attente)."""
    temps = [1000.0]                       # horloge simulée : on la fait avancer à la main
    wd = Watchdog(delai_max=30, horloge=lambda: temps[0])
    resultats = []

    def cas(nom, donnees, attendu, fonction):
        resultats.append(executer_cas(nom, donnees, attendu, fonction))

    cas("Avant toute mesure", "aucune mesure", ATTENTE, wd.etat)
    wd.enregistrer_mesure()
    cas("Mesure reçue", "t = 0 s", ACTIVE, wd.etat)
    temps[0] += 8
    cas("Mesure un peu en retard (pas d'alerte)", "t = 8 s (envoi normal : 5 s)", ACTIVE, wd.etat)
    cas("Temps écoulé calculé", "t = 8 s", 8.0, wd.temps_ecoule)
    temps[0] += 22
    cas("Limite exacte du délai", "t = 30 s (délai max = 30 s)", ACTIVE, wd.etat)
    temps[0] += 1
    cas("Délai dépassé", "t = 31 s", DEPASSE, wd.etat)
    wd.enregistrer_mesure()
    cas("Communication rétablie", "nouvelle mesure après coupure", RETABLIE, wd.etat)
    wd.enregistrer_mesure()
    cas("Retour à l'état actif", "mesure suivante", ACTIVE, wd.etat)
    return resultats
