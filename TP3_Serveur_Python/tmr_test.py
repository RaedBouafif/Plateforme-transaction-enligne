"""TMR (Triple Modular Redundancy) : trois classifieurs différents + vote majoritaire.

Les trois fonctions donnent le même résultat mais sont écrites différemment :
un défaut dans l'une d'elles est alors masqué par les deux autres.
"""
from collections import Counter

import firebase_config as cfg
from data_processing import executer_cas


def classifier_if(temperature, humidity):
    """Version 1 : tests if / elif."""
    if temperature > 60 or humidity > 80:
        return "HIGH"
    elif temperature > 40 or humidity > 70:
        return "MEDIUM"
    return "LOW"


def classifier_score(temperature, humidity):
    """Version 2 : un score (0, 1 ou 2) par mesure, on garde le pire."""
    score_temp = (temperature > 40) + (temperature > 60)
    score_hum = (humidity > 70) + (humidity > 80)
    niveaux = ["LOW", "MEDIUM", "HIGH"]
    return niveaux[max(score_temp, score_hum)]


# Version 3 : table de seuils, du niveau le plus grave au moins grave
TABLE_SEUILS = [("HIGH", 60, 80), ("MEDIUM", 40, 70)]


def classifier_table(temperature, humidity):
    """Version 3 : on parcourt la table de seuils."""
    for niveau, seuil_temp, seuil_hum in TABLE_SEUILS:
        if temperature > seuil_temp or humidity > seuil_hum:
            return niveau
    return "LOW"


def vote_majoritaire(resultats):
    """Vote : retourne (valeur, message). Sans majorité, valeur = None (jamais de choix arbitraire)."""
    if not resultats:
        return None, "aucun résultat"
    valeur, nombre = Counter(resultats).most_common(1)[0]
    if nombre > len(resultats) / 2:
        return valeur, f"majorité ({nombre} sur {len(resultats)})"
    return None, "pas de majorité"


def tmr_classifier(temperature, humidity, fonctions=None):
    """Applique les trois classifieurs puis le vote. Retourne (valeur, message, liste des 3 sorties)."""
    fonctions = fonctions or [classifier_if, classifier_score, classifier_table]
    sorties = [f(temperature, humidity) for f in fonctions]
    valeur, message = vote_majoritaire(sorties)
    return valeur, message, sorties


def _texte(valeur):
    """Valeur du vote en texte : 'pas de majorité' si None."""
    return "pas de majorité" if valeur is None else valeur


def run_tmr_test():
    """Teste les trois classifieurs et les scénarios du vote. Retourne la liste des résultats."""
    resultats = []
    # 1) Les trois classifieurs sont d'accord sur les cas du TP
    for t, h, attendu in [(25, 50, "LOW"), (45, 60, "MEDIUM"), (35, 75, "MEDIUM"),
                          (65, 50, "HIGH"), (30, 85, "HIGH"), (40, 70, "LOW"), (60, 80, "MEDIUM")]:
        resultats.append(executer_cas(
            f"TMR cas réel {t}/{h}", f"temp={t}, hum={h}, 3 classifieurs", attendu,
            lambda t=t, h=h: _texte(tmr_classifier(t, h)[0])))
    # 2) Scénarios de vote
    scenarios = [
        ("Vote : trois résultats identiques", ["LOW", "LOW", "LOW"], "LOW"),
        ("Vote : 2 contre 1 (majorité)", ["NORMAL", "NORMAL", "HIGH"], "NORMAL"),
        ("Vote : 2 contre 1 (HIGH majoritaire)", ["LOW", "HIGH", "HIGH"], "HIGH"),
        ("Vote : tous différents", ["LOW", "MEDIUM", "HIGH"], "pas de majorité"),
    ]
    for nom, entrees, attendu in scenarios:
        resultats.append(executer_cas(nom, entrees, attendu,
                                      lambda e=entrees: _texte(vote_majoritaire(e)[0])))
    # 3) Panne simulée : un classifieur donne un résultat faux, les autres le masquent
    def panne():
        faux = lambda t, h: "HIGH"
        return _texte(tmr_classifier(25, 50, [classifier_if, classifier_score, faux])[0])
    resultats.append(executer_cas("TMR : un classifieur défaillant masqué", "25/50, 3e fonction renvoie HIGH", "LOW", panne))
    def deux_pannes():
        f1 = lambda t, h: "LOW"
        f2 = lambda t, h: "MEDIUM"
        f3 = lambda t, h: "HIGH"
        return _texte(tmr_classifier(25, 50, [f1, f2, f3])[0])
    resultats.append(executer_cas("TMR : trois sorties différentes", "LOW/MEDIUM/HIGH", "pas de majorité", deux_pannes))
    return resultats
