import time
import unittest

from data_processing import classify_alert, creer_resultat, validate_data


class TestValidation(unittest.TestCase):
    """Tests de validate_data."""

    def test_mesure_valide(self):
        """Une mesure normale est acceptée."""
        self.assertTrue(validate_data({"temperature": 25.0, "humidity": 50.0})[0])

    def test_limites_acceptees(self):
        """Les bornes -40, 80, 0 et 100 sont acceptées."""
        self.assertTrue(validate_data({"temperature": -40, "humidity": 0})[0])
        self.assertTrue(validate_data({"temperature": 80, "humidity": 100})[0])

    def test_humidite_trop_haute(self):
        """Humidité 100.1 refusée."""
        self.assertFalse(validate_data({"temperature": 25, "humidity": 100.1})[0])

    def test_humidite_negative(self):
        """Humidité négative refusée."""
        self.assertFalse(validate_data({"temperature": 25, "humidity": -1})[0])

    def test_temperature_hors_plage(self):
        """Température -40.1 et 80.1 refusées."""
        self.assertFalse(validate_data({"temperature": -40.1, "humidity": 50})[0])
        self.assertFalse(validate_data({"temperature": 80.1, "humidity": 50})[0])

    def test_non_numerique(self):
        """Texte refusé (même s'il ressemble à un nombre)."""
        self.assertFalse(validate_data({"temperature": "abc", "humidity": 50})[0])
        self.assertFalse(validate_data({"temperature": "25", "humidity": 50})[0])

    def test_booleen_refuse(self):
        """True n'est pas une mesure valide."""
        self.assertFalse(validate_data({"temperature": True, "humidity": 50})[0])

    def test_nan_et_inf(self):
        """NaN et infini refusés."""
        self.assertFalse(validate_data({"temperature": float("nan"), "humidity": 50})[0])
        self.assertFalse(validate_data({"temperature": 25, "humidity": float("inf")})[0])
        self.assertFalse(validate_data({"temperature": float("-inf"), "humidity": 50})[0])

    def test_champ_manquant_ou_none(self):
        """Champ absent ou None refusé."""
        self.assertFalse(validate_data({"humidity": 50})[0])
        self.assertFalse(validate_data({"temperature": None, "humidity": 50})[0])
        self.assertFalse(validate_data({})[0])

    def test_donnees_absentes(self):
        """None à la place des données : refusé."""
        self.assertFalse(validate_data(None)[0])

    def test_message_de_rejet(self):
        """Le message explique le rejet."""
        self.assertEqual(validate_data({"temperature": 25, "humidity": 50}), (True, "OK"))
        self.assertIn("manquant", validate_data({"humidity": 50})[1])


class TestClassification(unittest.TestCase):
    """Tests de classify_alert."""

    def test_cas_du_tp(self):
        """Les cinq cas demandés par le TP."""
        self.assertEqual(classify_alert(25, 50), "LOW")
        self.assertEqual(classify_alert(45, 60), "MEDIUM")
        self.assertEqual(classify_alert(35, 75), "MEDIUM")
        self.assertEqual(classify_alert(65, 50), "HIGH")
        self.assertEqual(classify_alert(30, 85), "HIGH")

    def test_limites_low(self):
        """40/70 est encore LOW (seuils stricts)."""
        self.assertEqual(classify_alert(40, 70), "LOW")

    def test_limites_medium(self):
        """60/80 est encore MEDIUM ; juste au-dessus de 40 ou 70 : MEDIUM."""
        self.assertEqual(classify_alert(60, 80), "MEDIUM")
        self.assertEqual(classify_alert(40.1, 50), "MEDIUM")
        self.assertEqual(classify_alert(20, 70.1), "MEDIUM")

    def test_limites_high(self):
        """Juste au-dessus de 60 ou 80 : HIGH."""
        self.assertEqual(classify_alert(60.1, 50), "HIGH")
        self.assertEqual(classify_alert(20, 80.1), "HIGH")

    def test_high_prioritaire(self):
        """HIGH l'emporte même si l'autre valeur est MEDIUM."""
        self.assertEqual(classify_alert(65, 75), "HIGH")
        self.assertEqual(classify_alert(45, 85), "HIGH")

    def test_valeurs_negatives(self):
        """Une température négative est LOW."""
        self.assertEqual(classify_alert(-10, 20), "LOW")

    def test_nan_inf_et_texte(self):
        """NaN, inf, None et texte lèvent ValueError."""
        with self.assertRaises(ValueError):
            classify_alert(float("nan"), 50)
        with self.assertRaises(ValueError):
            classify_alert(25, float("inf"))
        with self.assertRaises(ValueError):
            classify_alert(None, 50)
        with self.assertRaises(ValueError):
            classify_alert("abc", 50)

    def test_resultat_jamais_vide(self):
        """Pour des valeurs valides, la sortie est toujours un des trois niveaux."""
        self.assertIsNotNone(classify_alert(0, 0))
        self.assertIn(classify_alert(50, 50), ("LOW", "MEDIUM", "HIGH"))


def run_unit_tests():
    """Lance les tests unittest un par un et retourne la liste des résultats (dictionnaires)."""
    chargeur = unittest.TestLoader()
    suite = unittest.TestSuite([chargeur.loadTestsFromTestCase(TestValidation),
                                chargeur.loadTestsFromTestCase(TestClassification)])
    resultats = []
    for test in _liste_tests(suite):
        bilan = unittest.TestResult()
        debut = time.perf_counter()
        test.run(bilan)
        duree_ms = (time.perf_counter() - debut) * 1000
        ok = bilan.wasSuccessful()
        erreur = ""
        if not ok:
            erreur = (bilan.failures + bilan.errors)[0][1].strip().splitlines()[-1]
        description = test.shortDescription() or test.id()
        resultats.append(creer_resultat(
            f"{type(test).__name__}.{test._testMethodName}", description,
            "test réussi", "test réussi" if ok else "test échoué", ok, duree_ms, erreur))
    return resultats


def _liste_tests(suite):
    """Aplatit une suite unittest en liste de tests individuels."""
    tests = []
    for element in suite:
        if isinstance(element, unittest.TestSuite):
            tests.extend(_liste_tests(element))
        else:
            tests.append(element)
    return tests


if __name__ == "__main__":
    unittest.main()
