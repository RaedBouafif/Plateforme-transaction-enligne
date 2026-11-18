import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import csv_manager
import firebase_config as cfg
from data_processing import (connect_firebase, creer_resultat, creer_source_firebase,
                             generate_report, traiter_cycle)
from integration_tests import run_tests_sur_import
from watchdog_test import Watchdog

COULEURS_ALERTE = {"LOW": "#4caf50", "MEDIUM": "#ff9800", "HIGH": "#f44336"}
COULEUR_NEUTRE = "#cccccc"
COLONNES_TABLEAU = ("test", "donnees", "attendu", "obtenu", "statut", "duree_ms", "erreur")
TITRES_TABLEAU = ("Test", "Données utilisées", "Attendu", "Obtenu", "Statut", "Durée (ms)", "Erreurs")


class Application:
    """Fenêtre principale : construit les widgets et traite les messages des threads."""

    def __init__(self, racine, familles):
        """Prépare l'état (file de messages, watchdog) puis construit la fenêtre."""
        self.racine = racine
        self.familles = familles            # {nom: fonction(source)}
        self.file = queue.Queue()           # messages envoyés par les threads
        self.source = None                  # source Firebase (None tant qu'on n'est pas connecté)
        self.watchdog = Watchdog()
        self.derniere_mesure = None         # dernier résultat valide (pour éviter les doublons CSV)
        self.lecture_en_cours = False
        self.supervision_active = False
        self.tests_en_cours = False
        self.import_courant = None          # résultat de import_csv
        self.chemin_import = ""
        self.resultats_par_famille = {}     # pour le rapport

        self.construire_interface()
        self.racine.after(100, self.traiter_file)          # lecture de la file
        self.racine.after(1000, self.rafraichir_watchdog)  # mise à jour du watchdog
        self.racine.protocol("WM_DELETE_WINDOW", self.fermer)

    # ------------------------------------------------------------------
    # Construction de la fenêtre
    # ------------------------------------------------------------------
    def construire_interface(self):
        """Crée toutes les zones de la fenêtre."""
        self.racine.title("TP3 - Serveur Python : test et validation de la plateforme")
        self.racine.geometry("1150x780")
        self.construire_zone_firebase()
        self.construire_zone_supervision()
        self.construire_zone_tests()
        self.construire_zone_csv()
        self.construire_tableau()

    def construire_zone_firebase(self):
        """Zone Firebase : connexion, état et lecture manuelle."""
        cadre = ttk.LabelFrame(self.racine, text="Firebase")
        cadre.pack(fill="x", padx=8, pady=4)
        ttk.Button(cadre, text="Se connecter", command=self.clic_connecter).pack(side="left", padx=4, pady=4)
        ttk.Button(cadre, text="Lire maintenant", command=self.lancer_lecture).pack(side="left", padx=4)
        self.var_connexion = tk.StringVar(value="Non connecté")
        ttk.Label(cadre, textvariable=self.var_connexion).pack(side="left", padx=10)

    def construire_zone_supervision(self):
        """Zone de supervision : mesures, niveau d'alerte coloré, états."""
        cadre = ttk.LabelFrame(self.racine, text="Supervision")
        cadre.pack(fill="x", padx=8, pady=4)
        self.var_temp = tk.StringVar(value="Température : --")
        self.var_hum = tk.StringVar(value="Humidité : --")
        self.var_date = tk.StringVar(value="Dernière mesure : --")
        self.var_comm = tk.StringVar(value="Communication : --")
        self.var_watchdog = tk.StringVar(value="Watchdog : --")
        ttk.Label(cadre, textvariable=self.var_temp, width=24).grid(row=0, column=0, sticky="w", padx=6)
        ttk.Label(cadre, textvariable=self.var_hum, width=24).grid(row=0, column=1, sticky="w", padx=6)
        self.label_alerte = tk.Label(cadre, text="Alerte : --", bg=COULEUR_NEUTRE, width=18)
        self.label_alerte.grid(row=0, column=2, padx=6, pady=3)
        ttk.Label(cadre, textvariable=self.var_date).grid(row=1, column=0, sticky="w", padx=6)
        ttk.Label(cadre, textvariable=self.var_comm).grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(cadre, textvariable=self.var_watchdog).grid(row=1, column=2, sticky="w", padx=6)
        self.bouton_supervision = ttk.Button(cadre, text="Démarrer la supervision automatique",
                                             command=self.basculer_supervision)
        self.bouton_supervision.grid(row=0, column=3, rowspan=2, padx=10)

    def construire_zone_tests(self):
        """Un bouton par famille de tests, plus 'Tout lancer' et 'Générer le rapport'."""
        cadre = ttk.LabelFrame(self.racine, text="Tests")
        cadre.pack(fill="x", padx=8, pady=4)
        for nom in self.familles:
            ttk.Button(cadre, text=nom, command=lambda n=nom: self.lancer_famille(n)).pack(side="left", padx=3, pady=4)
        ttk.Button(cadre, text="Tout lancer", command=self.lancer_tout).pack(side="left", padx=8)
        ttk.Button(cadre, text="Générer le rapport", command=self.clic_rapport).pack(side="left", padx=3)
        ttk.Button(cadre, text="Effacer le tableau", command=self.effacer_tableau).pack(side="left", padx=3)

    def construire_zone_csv(self):
        """Zone CSV : choix du fichier, import, compteurs, tests sur les données importées."""
        cadre = ttk.LabelFrame(self.racine, text="Fichier CSV")
        cadre.pack(fill="x", padx=8, pady=4)
        ttk.Button(cadre, text="Choisir un fichier", command=self.clic_choisir_csv).pack(side="left", padx=4, pady=4)
        self.var_fichier = tk.StringVar(value=cfg.CHEMIN_CSV)
        ttk.Label(cadre, textvariable=self.var_fichier, width=45).pack(side="left", padx=4)
        ttk.Button(cadre, text="Importer", command=self.clic_importer).pack(side="left", padx=4)
        self.var_compteurs = tk.StringVar(value="Valides : -- | Invalides : --")
        ttk.Label(cadre, textvariable=self.var_compteurs).pack(side="left", padx=8)
        ttk.Button(cadre, text="Tester les données importées", command=self.clic_tester_import).pack(side="left", padx=4)
        ttk.Button(cadre, text="Exporter valides / rejetées", command=self.clic_exporter).pack(side="left", padx=4)
        self.chemin_import = cfg.CHEMIN_CSV

    def construire_tableau(self):
        """Tableau (Treeview) des résultats de tests."""
        cadre = ttk.Frame(self.racine)
        cadre.pack(fill="both", expand=True, padx=8, pady=4)
        self.tableau = ttk.Treeview(cadre, columns=COLONNES_TABLEAU, show="headings")
        largeurs = (230, 200, 190, 220, 70, 80, 220)
        for colonne, titre, largeur in zip(COLONNES_TABLEAU, TITRES_TABLEAU, largeurs):
            self.tableau.heading(colonne, text=titre)
            self.tableau.column(colonne, width=largeur, anchor="w")
        self.tableau.tag_configure("reussi", background="#e3f6e3")
        self.tableau.tag_configure("echoue", background="#fde0e0")
        barre = ttk.Scrollbar(cadre, orient="vertical", command=self.tableau.yview)
        self.tableau.configure(yscrollcommand=barre.set)
        self.tableau.pack(side="left", fill="both", expand=True)
        barre.pack(side="right", fill="y")

    # ------------------------------------------------------------------
    # Threads et file de messages
    # ------------------------------------------------------------------
    def lancer_en_arriere_plan(self, fonction, type_message):
        """Exécute fonction() dans un thread ; son résultat arrive dans la file avec type_message."""
        def tache():
            try:
                self.file.put((type_message, fonction()))
            except Exception as e:  # le thread ne doit jamais mourir en silence
                self.file.put(("erreur", cfg.nettoyer_message(f"{type(e).__name__}: {e}")))
        threading.Thread(target=tache, daemon=True).start()

    def traiter_file(self):
        """Lit tous les messages en attente (thread principal), met l'affichage à jour, se re-planifie."""
        try:
            while True:
                type_message, contenu = self.file.get_nowait()
                self.traiter_message(type_message, contenu)
        except queue.Empty:
            pass
        self.racine.after(100, self.traiter_file)

    def traiter_message(self, type_message, contenu):
        """Aiguille un message vers la bonne action d'affichage."""
        if type_message == "connexion":
            self.apres_connexion(contenu)
        elif type_message == "mesure":
            self.afficher_mesure(contenu)
        elif type_message == "fin_lecture":
            self.lecture_en_cours = False
        elif type_message == "tests":
            nom, resultats = contenu
            self.resultats_par_famille[nom] = resultats
            self.ajouter_resultats(resultats)
        elif type_message == "fin_tests":
            self.tests_en_cours = False
        elif type_message == "import":
            self.apres_import(contenu)
        elif type_message == "tests_import":
            self.ajouter_resultats(contenu)
            self.resultats_par_famille["Tests sur CSV importé"] = contenu
        elif type_message == "erreur":
            self.lecture_en_cours = False
            self.tests_en_cours = False
            self.var_comm.set("Erreur : " + str(contenu))

    # ------------------------------------------------------------------
    # Firebase et supervision
    # ------------------------------------------------------------------
    def clic_connecter(self):
        """Bouton 'Se connecter' : la connexion se fait dans un thread."""
        self.var_connexion.set("Connexion en cours...")
        self.lancer_en_arriere_plan(connect_firebase, "connexion")

    def apres_connexion(self, resultat):
        """Affiche le résultat de la connexion (message déjà nettoyé de tout secret)."""
        if resultat["ok"]:
            self.source = creer_source_firebase(resultat["reference"])
        self.var_connexion.set(resultat["message"])

    def lancer_lecture(self):
        """Lit Firebase une fois (thread) : bouton 'Lire maintenant' et supervision automatique."""
        if self.source is None:
            self.var_connexion.set("Connectez-vous d'abord à Firebase")
            return
        if self.lecture_en_cours:
            return
        self.lecture_en_cours = True
        precedente = self.derniere_mesure

        def lire():
            traiter_cycle(self.source, cfg.CHEMIN_CSV,
                          callback=lambda r: self.file.put(("mesure", r)), precedente=precedente)
            return None
        self.lancer_en_arriere_plan(lire, "fin_lecture")

    def afficher_mesure(self, r):
        """Met à jour la zone de supervision avec le résultat d'un cycle."""
        if r["ok"]:
            self.watchdog.enregistrer_mesure()
            self.derniere_mesure = r
            self.var_temp.set(f"Température : {r['temperature']} °C")
            self.var_hum.set(f"Humidité : {r['humidity']} %")
            self.var_date.set(f"Dernière mesure : {r['timestamp']}")
            self.var_comm.set("Communication Firebase : OK")
            self.label_alerte.config(text=f"Alerte : {r['niveau']}", bg=COULEURS_ALERTE[r["niveau"]])
        else:
            self.var_comm.set(f"Problème ({r['etape']}) : {r['erreur']}")
            self.label_alerte.config(text="Alerte : --", bg=COULEUR_NEUTRE)

    def basculer_supervision(self):
        """Démarre ou arrête la supervision automatique."""
        self.supervision_active = not self.supervision_active
        if self.supervision_active:
            self.bouton_supervision.config(text="Arrêter la supervision automatique")
            self.boucle_supervision()
        else:
            self.bouton_supervision.config(text="Démarrer la supervision automatique")

    def boucle_supervision(self):
        """Lit Firebase puis se re-planifie avec root.after tant que la supervision est active."""
        if not self.supervision_active:
            return
        self.lancer_lecture()
        self.racine.after(cfg.INTERVALLE_SUPERVISION * 1000, self.boucle_supervision)

    def rafraichir_watchdog(self):
        """Chaque seconde : affiche l'état du watchdog et le temps écoulé."""
        etat = self.watchdog.etat()
        ecoule = self.watchdog.temps_ecoule()
        suite = "" if ecoule is None else f" ({ecoule:.0f} s)"
        self.var_watchdog.set(f"Watchdog : {etat}{suite}")
        self.racine.after(1000, self.rafraichir_watchdog)

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def lancer_famille(self, nom):
        """Lance une famille de tests dans un thread."""
        if self.tests_en_cours:
            self.var_comm.set("Des tests sont déjà en cours...")
            return
        self.tests_en_cours = True
        source = self.source

        def tache():
            self.file.put(("tests", (nom, self.familles[nom](source))))
        self.lancer_en_arriere_plan(tache, "fin_tests")

    def lancer_tout(self):
        """Lance les 7 familles les unes après les autres dans un seul thread."""
        if self.tests_en_cours:
            self.var_comm.set("Des tests sont déjà en cours...")
            return
        self.tests_en_cours = True
        source = self.source

        def tache():
            for nom, fonction in self.familles.items():
                self.file.put(("tests", (nom, fonction(source))))   # affichage au fur et à mesure
        self.lancer_en_arriere_plan(tache, "fin_tests")

    def ajouter_resultats(self, resultats):
        """Ajoute des lignes au tableau (couleur selon réussi / échoué)."""
        for r in resultats:
            etiquette = "reussi" if r["statut"] == "réussi" else "echoue"
            valeurs = [r[c] for c in COLONNES_TABLEAU]
            self.tableau.insert("", "end", values=valeurs, tags=(etiquette,))
        self.tableau.yview_moveto(1.0)

    def effacer_tableau(self):
        """Vide le tableau et les résultats mémorisés."""
        self.tableau.delete(*self.tableau.get_children())
        self.resultats_par_famille = {}

    def clic_rapport(self):
        """Écrit le rapport JSON + texte des tests déjà lancés."""
        if not self.resultats_par_famille:
            messagebox.showinfo("Rapport", "Lancez d'abord au moins une famille de tests.")
            return
        rapport = generate_report(self.resultats_par_famille)
        messagebox.showinfo("Rapport", f"Rapport écrit :\n{rapport['json']}\n{rapport['txt']}")

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------
    def clic_choisir_csv(self):
        """Ouvre la boîte de dialogue de choix du fichier CSV."""
        chemin = filedialog.askopenfilename(title="Choisir un CSV", filetypes=[("CSV", "*.csv")])
        if chemin:
            self.chemin_import = chemin
            self.var_fichier.set(chemin)

    def clic_importer(self):
        """Importe le CSV choisi dans un thread."""
        chemin = self.chemin_import
        self.lancer_en_arriere_plan(lambda: csv_manager.import_csv(chemin), "import")

    def apres_import(self, resultat):
        """Affiche les compteurs et les lignes invalides dans le tableau."""
        self.import_courant = resultat
        if not resultat["ok"]:
            self.var_compteurs.set("Import impossible : " + resultat["erreur"])
            return
        self.var_compteurs.set(f"Valides : {resultat['valides']} | Invalides : {resultat['invalides']}"
                               f" (sur {resultat['total']} lignes)")
        lignes = [creer_resultat(f"Import CSV ligne {l['ligne']}",
                                 f"{l['timestamp']} ; {l['temperature']} ; {l['humidity']}",
                                 "ligne valide", "ligne invalide", False, 0, l["raison"])
                  for l in resultat["lignes_invalides"][:50]]
        self.ajouter_resultats(lignes)

    def clic_tester_import(self):
        """Lance les tests sur les données importées (thread)."""
        resultat = self.import_courant
        self.lancer_en_arriere_plan(lambda: run_tests_sur_import(resultat), "tests_import")

    def clic_exporter(self):
        """Écrit mesures_valides.csv et mesures_rejetees.csv dans reports/ (le fichier d'origine reste intact)."""
        if not self.import_courant or not self.import_courant["ok"]:
            messagebox.showinfo("Export", "Importez d'abord un CSV valide.")
            return
        chemins = csv_manager.exporter_resultats(self.import_courant, cfg.DOSSIER_RAPPORTS)
        messagebox.showinfo("Export", "Fichiers écrits :\n" + "\n".join(chemins))

    def fermer(self):
        """Arrête la supervision puis ferme la fenêtre."""
        self.supervision_active = False
        self.racine.destroy()


def lancer_interface(familles):
    """Crée la fenêtre Tk, l'application, et lance la boucle principale."""
    racine = tk.Tk()
    Application(racine, familles)
    racine.mainloop()
