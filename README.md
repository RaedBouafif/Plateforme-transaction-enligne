# TP3 - Serveur Python pour le test et la validation d'une plateforme en ligne

Serveur Python qui lit les mesures d'un ESP32 (température, humidité) dans Firebase Realtime Database,
les valide, les classe (LOW / MEDIUM / HIGH), les enregistre dans un CSV et lance 7 familles de tests,
avec une interface Tkinter qui ne se fige jamais.

## 1. Installation (Windows 10/11, Python 3.13, VS Code)

1. Ouvrir le dossier `TP3_Serveur_Python` dans VS Code.
2. Terminal VS Code :
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Copier **serviceAccountKey.json** (clé du compte de service Firebase, téléchargée dans la console Firebase :
   Paramètres du projet > Comptes de service > Générer une nouvelle clé privée) dans le dossier du projet.
   Ce fichier est secret : il est dans `.gitignore`, ne le mettez jamais sur GitHub et ne le partagez pas.
   Pour changer son emplacement : modifier `CHEMIN_CLE` dans `firebase_config.py`.

Tkinter est fourni avec l'installateur Python officiel pour Windows.

## 2. Lancer

| Commande | Effet |
|---|---|
| `python main.py` | ouvre l'interface graphique |
| `python main.py --tests` | lance les 7 familles de tests dans la console et écrit un rapport dans `reports/` |
| `python -m unittest unit_tests -v` | lance seulement les tests unitaires (affichage unittest classique) |

Sans `serviceAccountKey.json`, tout fonctionne en mode hors ligne (données de test), sauf la lecture réelle de Firebase ;
le test « Fichier de clé présent » est alors marqué *échoué*, c'est normal.

## 3. Structure du projet

```
TP3_Serveur_Python/
  main.py                lance la GUI ou les tests en console (--tests)
  firebase_config.py     chemins, URL, seuils, délais, nettoyage des messages d'erreur
  data_processing.py     connect_firebase, get_data, validate_data, classify_alert, traiter_cycle, generate_report
  csv_manager.py         save_measure (écriture sans doublon), import_csv (pandas), exporter_resultats
  unit_tests.py          run_unit_tests          (unittest)
  integration_tests.py   run_integration_tests   (+ tests sur CSV importé)
  performance_tests.py   run_performance_tests
  robustness_tests.py    run_robustness_tests
  security_tests.py      run_security_tests
  tmr_test.py            run_tmr_test            (3 classifieurs + vote)
  watchdog_test.py       run_watchdog_test       (classe Watchdog)
  interface.py           interface Tkinter
  data/mesures.csv       exemple avec lignes valides ET invalides
  reports/               rapports générés (JSON + texte)
  serviceAccountKey.json (à ajouter par vous, non fourni)
```

Chaque test renvoie une liste de dictionnaires : `test, donnees, attendu, obtenu, statut ("réussi"/"échoué"), duree_ms, erreur`.
La console et l'interface utilisent exactement les mêmes résultats.

## 4. Règles de classification (seuils stricts)

- **HIGH** si température > 60 **ou** humidité > 80 (prioritaire sur tout)
- sinon **MEDIUM** si température > 40 **ou** humidité > 70
- sinon **LOW** (température <= 40 et humidité <= 70)

Exemples : 25/50 LOW, 45/60 MEDIUM, 35/75 MEDIUM, 65/50 HIGH, 30/85 HIGH ; limites : 40/70 LOW, 60/80 MEDIUM.

## 5. Choix de conception (à pouvoir expliquer)

- **Plage de validation** : température de -40 à 80 °C (plage du capteur DHT22), humidité de 0 à 100 %.
  Sont refusés : valeur absente ou `None`, texte, booléen, `NaN`, infini, hors plage.
- **Réception d'une mesure** : l'ESP32 n'écrit pas d'horodatage. Le serveur prend donc l'heure de réception.
  Une **lecture réussie et valide** = une réception (elle remet le watchdog à zéro).
  La **ligne CSV** n'est écrite que pour une **nouvelle mesure** : valeurs différentes de la précédente
  (ou `timestamp` différent si Firebase fournit un champ `timestamp`, qui est alors utilisé tel quel).
  `save_measure` refuse en plus un timestamp déjà présent.
  *Limite* : comme Firebase garde la dernière valeur, une lecture réussie prouve que le serveur et Firebase communiquent,
  pas que l'ESP32 envoie encore ; sans champ `timestamp`, deux mesures identiques de suite ne donnent qu'une ligne CSV.
- **Watchdog** : délai maximum 30 s (l'ESP32 envoie toutes les 5 s). Alerte seulement si le temps écoulé est
  **strictement supérieur** à 30 s : un retard de 8 s ne déclenche rien. États : `communication active`,
  `délai dépassé`, `communication rétablie` (première mesure après une coupure), plus `aucune mesure reçue` au démarrage.
  L'horloge est injectable : les tests n'attendent jamais 30 secondes réelles.
- **Import CSV** : le fichier d'origine n'est jamais modifié et rien n'est corrigé en silence.
  Les lignes invalides sont comptées et expliquées (manquant, non numérique, hors plage, date invalide,
  timestamp en double, date antérieure à la ligne précédente). Le bouton « Exporter » crée deux nouveaux fichiers
  dans `reports/` : `mesures_valides.csv` et `mesures_rejetees.csv` (avec la colonne `raison`).
- **Supervision automatique** : lecture toutes les 3 s dans un thread ; les nouvelles mesures sont **ajoutées à `data/mesures.csv`**.
  Gardez une copie de l'exemple si vous voulez retrouver exactement 6 lignes valides / 4 invalides.

## 6. Comment fonctionne chaque famille de tests

1. **Unitaires** (`unit_tests.py`) : `unittest` avec `assertEqual`, `assertTrue`, `assertFalse`, `assertIsNotNone`, `assertRaises`
   sur la validation et la classification (cas du TP, limites, `NaN`, `inf`, champ manquant).
2. **Intégration** (`integration_tests.py`) : cycle complet lecture > champs > validation > classification > callback (GUI) > CSV.
   La source est injectable : données de test, ou Firebase réel (un test supplémentaire « Lecture Firebase réelle » est ajouté
   si vous êtes connecté). Cas : flux valide, champ manquant, Firebase injoignable, pas de doublon CSV, valeur invalide.
   Les tests écrivent dans un dossier temporaire, jamais dans `data/mesures.csv`.
3. **Performance** (`performance_tests.py`) : `time.perf_counter()` sur validation, classification, lots de 100 / 1000 / 10000
   mesures et import CSV de 1000 / 10000 lignes. Le temps local est séparé du temps réseau (lecture Firebase, mesuré seulement si connecté).
   Le test indique l'opération locale la plus lente et compare local / réseau.
4. **Robustesse** (`robustness_tests.py`) : on introduit un problème (valeur manquante, texte, humidité < 0 ou > 100, réponse vide,
   interruption Firebase, CSV absent / sans colonne / incomplet / vide) ; le tableau montre problème introduit, attendu, obtenu.
   Tout est protégé par `try/except` : le programme ne plante pas.
5. **Sécurité** (`security_tests.py`, uniquement sur votre propre base) : clé présente, clé configurée = clé utilisée, clé dans `.gitignore`,
   requête GET **sans authentification** sur votre base (indique si elle est publique : information, non bloquant),
   fausse clé > erreur propre, messages nettoyés (`nettoyer_message`), aucun secret dans le code, protections proposées.
6. **TMR** (`tmr_test.py`) : trois classifieurs écrits différemment (`if/elif`, score, table de seuils) et un vote majoritaire.
   Scénarios : tous identiques, 2 contre 1 (la majorité l'emporte), tous différents (`pas de majorité`, aucun choix arbitraire).
7. **Watchdog** (`watchdog_test.py`) : horloge simulée ; vérifie les états et que 8 s de retard ne déclenche pas d'alerte.

## 7. Interface

- **Firebase** : *Se connecter*, état de connexion, *Lire maintenant*.
- **Supervision** : température, humidité, niveau d'alerte coloré (vert / orange / rouge), date de dernière mesure,
  état de la communication, état du watchdog, démarrage / arrêt de la supervision automatique.
- **Tests** : un bouton par famille, *Tout lancer*, *Générer le rapport*, résultats dans un tableau (Treeview).
- **CSV** : choisir, importer, compteurs valides / invalides, tester les données importées, exporter.
- L'interface ne se fige pas : Firebase et les tests tournent dans des threads (`threading`) qui envoient leurs résultats
  dans une file (`queue`) ; la fenêtre lit cette file avec `root.after()`.

## 8. Sécurité : rappel

- Ne jamais écrire la clé dans le code, ne jamais l'afficher, ne jamais la commiter (`.gitignore`).
- Si la clé a fuité : la supprimer dans la console Google Cloud et en générer une nouvelle.
- Pour un vrai projet, remplacer les règles publiques de Realtime Database par des règles qui exigent une authentification.
