"""Le registre : comment une brique entre dans Nova.

Une brique mal formee doit echouer A L'ENREGISTREMENT, au demarrage, avec un
message qui dit quoi corriger. Decouvrir six mois plus tard qu'un outil n'a
jamais eu de description est exactement la dette qu'on refuse.
"""

import pytest

from nova.core import contrats
from nova.core.registre import ErreurRegistre, Registre


def _registre():
    return Registre("outil")


class Correct:
    nom = "correct"
    description = "Un outil bien forme"
    capacite = "recherche"
    niveau = contrats.LECTURE

    def executer(self):
        return 42


def test_enregistre_une_classe_et_l_instancie():
    r = _registre()
    r.enregistrer(Correct)
    assert r.exiger("correct").executer() == 42


def test_enregistre_aussi_une_instance_deja_construite():
    # Necessaire pour les outils qui prennent un reglage a la construction.
    r = _registre()
    r.enregistrer(Correct())
    assert "correct" in r


def test_refuse_une_brique_sans_description():
    class Muet:
        nom = "muet"
        description = ""
        capacite = "recherche"

    with pytest.raises(ErreurRegistre, match="description"):
        _registre().enregistrer(Muet)


def test_refuse_une_capacite_inconnue_et_explique():
    class Farfelu:
        nom = "farfelu"
        description = "Fait n'importe quoi"
        capacite = "telepathie"

    with pytest.raises(ErreurRegistre) as erreur:
        _registre().enregistrer(Farfelu)
    # Le message doit dire ce qui est acceptable, pas seulement ce qui est faux.
    assert "telepathie" in str(erreur.value)
    assert "conversation" in str(erreur.value)


def test_refuse_deux_briques_de_meme_nom():
    # Sans ce refus, la seconde masquerait la premiere en silence.
    r = _registre()
    r.enregistrer(Correct)
    with pytest.raises(ErreurRegistre, match="deja enregistre"):
        r.enregistrer(Correct)


def test_exiger_explique_ce_qui_existe():
    r = _registre()
    r.enregistrer(Correct)
    with pytest.raises(ErreurRegistre) as erreur:
        r.exiger("absent")
    assert "correct" in str(erreur.value)


def test_recherche_par_capacite():
    class Autre:
        nom = "autre"
        description = "Agit"
        capacite = "action"
        niveau = contrats.REVERSIBLE

        def executer(self):
            return None

    r = _registre()
    r.enregistrer(Correct)
    r.enregistrer(Autre)
    assert [b.nom for b in r.par_capacite("recherche")] == ["correct"]
    assert [b.nom for b in r.par_capacite("action")] == ["autre"]


def test_l_ordre_est_celui_de_l_enregistrement():
    # Previsible et reproductible : un choix « le premier qui convient » n'a
    # de sens que si l'ordre ne depend pas du hasard d'un dictionnaire.
    class A:
        nom, description, capacite = "a", "A", "action"
    class B:
        nom, description, capacite = "b", "B", "action"

    r = _registre()
    r.enregistrer(A)
    r.enregistrer(B)
    assert r.noms() == ("a", "b")


def test_le_catalogue_est_lisible():
    r = _registre()
    r.enregistrer(Correct)
    catalogue = r.catalogue()
    assert "correct" in catalogue and "recherche" in catalogue
    assert "Aucun" in _registre().catalogue()
