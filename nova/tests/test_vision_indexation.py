"""Le fil qui regarde les images en tache de fond.

⚠️ CE FIL EST LE SEUL DU PROJET QUI CHARGE UN MODELE SANS QU'ON LUI AIT RIEN
   DEMANDE. TOUS LES BANCS D'ICI VERIFIENT QU'IL SE TAIT.

Sur 8 Go, charger le modele de vision decharge celui de la langue. Si ce fil
le fait au mauvais moment, la reponse suivante attend — et personne ne
comprend pourquoi, puisque rien n'a ete demande. Une capacite de fond qui
ralentit le premier plan est pire que pas de capacite du tout.
"""

from __future__ import annotations

import threading

import pytest

from nova.vision import indexation

#: ⚠️ ON ENREGISTRE, ON NE LEVE PAS.
#:
#: La premiere version de ces bancs utilisait un double qui levait
#: `AssertionError` s'il etait appele. Or `entretenir` rattrape TOUTE
#: exception — c'est voulu, une indexation en panne ne doit pas faire tomber
#: Nova — donc le banc passait meme quand le fil demarrait au mauvais moment.
#:
#: Un double qui leve ne prouve rien face a un code qui rattrape.
_passages: list[int] = []


def _compter() -> int:
    _passages.append(1)
    return 0


@pytest.fixture(autouse=True)
def etat_propre():
    """⚠️ `_derniere_activite` EST UN ETAT DE MODULE, ET IL FUIT.

    Sans cette remise a zero, un banc qui appelle `signaler_activite` laisse
    le fil en periode de silence pour TOUS les suivants — qui sautent alors
    l'indexation et passent pour la mauvaise raison. C'est exactement ce qui
    est arrive : « un seul lot » rendait zero lot, et l'echec designait le
    code alors que la cause etait le banc precedent.
    """
    _passages.clear()
    indexation._derniere_activite = 0.0
    yield
    indexation._derniere_activite = 0.0


def test_il_ne_demarre_pas_quand_la_vision_est_eteinte(monkeypatch):
    """⚠️ LE DEFAUT EST « ETEINTE ». PERSONNE NE PAIE POUR CE QU'IL N'UTILISE PAS.

    Un fil qui tourne pour rien, sur une capacite desactivee, est du cout pur
    — et invisible, donc jamais remis en cause.

    Le delai de demarrage est rendu negligeable ici : sans la sortie
    anticipee, le banc appellerait `_un_passage` et echouerait franchement,
    au lieu d'attendre deux minutes pour rien.
    """
    monkeypatch.setattr(indexation, "DEMARRAGE_S", 0.01)
    monkeypatch.setattr(indexation, "_un_passage", _compter)

    indexation.entretenir(threading.Event())

    assert _passages == []


def test_il_attend_avant_le_premier_lot(monkeypatch):
    """⚠️ SANS CE DELAI, IL DEMARRAIT A LA SECONDE DU LANCEMENT.

    `_repos_depuis_la_derniere_reponse` rend « plus que le silence exige »
    quand personne n'a encore parle — ce qui est vrai, et qui faisait charger
    le modele de vision pendant que Whisper se prechauffe et que le modele de
    langue se met en place. Trois chargements concurrents sur 8 Go.

    Le banc verifie que le fil ATTEND, en le coupant pendant cette attente :
    aucun passage ne doit avoir eu lieu.
    """
    from nova.vision import moteur

    monkeypatch.setattr(moteur, "disponible", lambda: (True, ""))
    monkeypatch.setattr(indexation, "_un_passage", _compter)

    class ArretPendantLAttente(threading.Event):
        """Rend `True` au premier `wait` — comme un arret pendant le delai."""

        def wait(self, timeout=None):  # noqa: D102
            return True

    indexation.entretenir(ArretPendantLAttente())

    assert _passages == [], "aucune image ne doit etre regardee pendant le delai"


def test_le_fil_s_arrete_quand_on_le_lui_demande(monkeypatch):
    """⚠️ UN FIL QU'ON NE PEUT PAS ARRETER PAR L'OBJET PREVU POUR CA.

    La boucle ne regardait que `arret.is_set()` et ignorait le retour de
    `arret.wait()`. Avec un vrai `Event` la difference ne se voit pas — au
    tour suivant `is_set()` devient vrai. Avec un double qui rend `True` sans
    se marquer, le fil tournait indefiniment : c'est ce qui a fait tourner
    la suite de bancs en boucle jusqu'a expiration.
    """
    from nova.vision import moteur

    monkeypatch.setattr(moteur, "disponible", lambda: (True, ""))
    monkeypatch.setattr(indexation, "DEMARRAGE_S", 0.01)
    monkeypatch.setattr(indexation, "_un_passage", _compter)

    class ArretApresLePremierLot(threading.Event):
        """Laisse passer le delai de demarrage, puis demande l'arret."""

        def __init__(self) -> None:
            super().__init__()
            self.appels = 0

        def wait(self, timeout=None):  # noqa: D102
            self.appels += 1
            # ⚠️ BORNE : UNE BOUCLE CASSEE DOIT ECHOUER, PAS PENDRE.
            #
            # Sans elle, retirer la sortie sur `wait` faisait tourner ce banc
            # indefiniment — la suite entiere expirait au bout de deux
            # minutes, sans dire lequel. Un banc qui pend ne designe rien.
            assert self.appels < 10, "le fil ignore l'arret qu'on lui demande"
            return self.appels > 1

    indexation.entretenir(ArretApresLePremierLot())

    assert _passages == [1], "un seul lot, puis l'arret est respecte"


def test_une_machine_qui_pagine_repousse_l_indexation(monkeypatch):
    """⚠️ LE SILENCE NE SUFFIT PAS : UNE MACHINE PEUT ETRE SILENCIEUSE ET SATUREE.

    Releve au demarrage sur la machine reelle : « La machine pagine (swap
    2,27 Go / 3,0 Go) ». Charger 2 Go de plus dans cet etat ne ralentit pas
    seulement Nova — ca ralentit tout ce que la personne est en train de
    faire, sans qu'elle ait rien demande.
    """
    from nova.core import plateforme
    from nova.vision import moteur

    class Sature:
        pagine = True

        def __str__(self) -> str:
            return "swap 2.27 Go / 3.0 Go"

    monkeypatch.setattr(moteur, "disponible", lambda: (True, ""))
    monkeypatch.setattr(plateforme, "pression_memoire", lambda: Sature())
    monkeypatch.setattr(indexation, "DEMARRAGE_S", 0.01)
    monkeypatch.setattr(indexation, "_un_passage", _compter)

    class ArretApresUnTour(threading.Event):
        def __init__(self) -> None:
            super().__init__()
            self.appels = 0

        def wait(self, timeout=None):  # noqa: D102
            self.appels += 1
            assert self.appels < 10, "le fil ignore l'arret qu'on lui demande"
            return self.appels > 1

    indexation.entretenir(ArretApresUnTour())

    assert _passages == [], "rien ne doit etre indexe pendant que la machine pagine"


def test_une_mesure_memoire_indisponible_n_empeche_pas_d_indexer(monkeypatch):
    """Bloquer une capacite sur l'ABSENCE d'une mesure couterait plus que le
    risque qu'elle sert a eviter."""
    from nova.core import plateforme

    def casse():
        raise OSError("vm_stat introuvable")

    monkeypatch.setattr(plateforme, "pression_memoire", casse)

    assert indexation._machine_saturee() is False


def test_une_reponse_recente_repousse_l_indexation(monkeypatch):
    """Quelqu'un parle a Nova : ce n'est pas le moment de charger 2 Go."""
    indexation.signaler_activite()

    assert indexation._repos_depuis_la_derniere_reponse() < indexation.SILENCE_S


def test_sans_aucune_activite_le_silence_est_acquis():
    """Une machine qu'on vient d'allumer est silencieuse — c'est le delai de
    demarrage qui protege ce cas, pas le compteur d'activite."""
    monkeypatch_valeur = indexation._derniere_activite
    try:
        indexation._derniere_activite = 0.0
        assert indexation._repos_depuis_la_derniere_reponse() > indexation.SILENCE_S
    finally:
        indexation._derniere_activite = monkeypatch_valeur


def test_signaler_l_activite_ne_coute_presque_rien():
    """⚠️ APPELE SUR LE CHEMIN DE CHAQUE REPONSE.

    Une horloge et un verrou. Tout ce qui couterait plus n'a rien a faire
    la — le chemin conversationnel a ete ramene de 8-11 s a 1,8-3,1 s au prix
    de plusieurs tours, et ce n'est pas un compteur de fond qui va le reprendre.
    """
    import time

    debut = time.perf_counter()
    for _ in range(10_000):
        indexation.signaler_activite()

    assert time.perf_counter() - debut < 0.5


def test_une_traduction_par_lot_rend_une_ligne_par_image():
    """⚠️ LE COMPTE EST VERIFIE PARCE QU'UN DECALAGE EST INDETECTABLE.

    Un modele qui fusionne deux lignes attribuerait la description d'une
    image a une autre. L'erreur ne se verrait que des mois plus tard, en
    ouvrant le mauvais fichier — sans rien qui rattache la surprise a sa
    cause.
    """

    class ClientDeBanc:
        def chat(self, messages, *, temperature=None):
            return "1. une casquette blanche\n2. un document\n3. un ecran"

    traduire = indexation._traduire_avec(ClientDeBanc())

    assert traduire(["a cap", "a document", "a screen"]) == [
        "une casquette blanche",
        "un document",
        "un ecran",
    ]


def test_une_reponse_bavarde_du_modele_est_ramenee_aux_lignes_numerotees():
    """Un petit modele ajoute « Voici la traduction : » avant de repondre."""

    class ClientBavard:
        def chat(self, messages, *, temperature=None):
            return (
                "Bien sur ! Voici les traductions :\n"
                "1. une casquette\n"
                "2. un document\n"
                "\nJ'espere que ca aide."
            )

    traduire = indexation._traduire_avec(ClientBavard())

    assert traduire(["a cap", "a doc"]) == ["une casquette", "un document"]
