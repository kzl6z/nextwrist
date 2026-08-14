"""« Pas encore de donnees » n'est pas « pas de micro ».

LE DEFAUT QUE CES TESTS PROTEGENT

avfoundation livre ses trames de facon ASYNCHRONE. Tant que la carte son
n'en a pas produit, toute lecture rend EAGAIN — errno 35, « reessaie plus
tard ». Ce n'est pas une panne, c'est une attente.

Le diagnostic sur la machine reelle le montrait noir sur blanc :

    :0  — ouvre mais ne capte rien ([Errno 35])
    :1  — ouvre mais ne capte rien ([Errno 35])

Deux micros s'ouvraient parfaitement. On abandonnait a la premiere
occurrence, donc systematiquement : la premiere lecture arrive toujours
avant la premiere trame.

LA SUBTILITE QUI FAIT QU'UN SIMPLE `try` NE SUFFIT PAS

Le generateur de PyAV se referme quand une exception le traverse. Le
reprendre apres coup rend StopIteration immediatement — le silence, sans
erreur. Il faut le RECREER. C'est exactement ce qu'un test verifie ici, et
que personne ne verrait a la lecture.
"""

import sys
import threading
import types

import pytest


class FausseErreurBloquante(OSError):
    """Ce que PyAV leve quand la carte son n'a rien de pret."""


@pytest.fixture(autouse=True)
def faux_module_av(monkeypatch):
    """Un module `av` minimal : `lire_en_boucle` n'a besoin que de son erreur.

    faster-whisper — donc PyAV — n'est pas installe partout. Le comportement
    teste ici est notre logique de reprise, pas celle de la bibliotheque : un
    double suffit, et rend le test executable sur toutes les machines.
    """
    module = types.ModuleType("av")
    module.error = types.SimpleNamespace(BlockingIOError=FausseErreurBloquante)
    monkeypatch.setitem(sys.modules, "av", module)
    return module


class FauxFlux:
    """Rend EAGAIN un certain nombre de fois, puis livre des trames."""

    def __init__(self, refus: int, trames: int = 3) -> None:
        self.refus_restants = refus
        self.trames = trames
        self.generateurs_crees = 0
        self.livrees = 0

    def decode(self, audio=0):
        self.generateurs_crees += 1

        def generateur():
            if self.refus_restants > 0:
                self.refus_restants -= 1
                raise FausseErreurBloquante(35, "Resource temporarily unavailable")
            for _ in range(self.trames):
                self.livrees += 1
                yield object()

        return generateur()


class FauxReechantillonneur:
    @staticmethod
    def resample(trame):
        return [types.SimpleNamespace(to_ndarray=lambda: _Tableau())]


class _Tableau:
    @staticmethod
    def tobytes():
        return b"\0" * 320


def lire(flux, arret=None, patience: float = 1.0) -> list[bytes]:
    from enregistrer_voix import lire_en_boucle

    recolte: list[bytes] = []
    arret = arret or threading.Event()
    # Sans arret programme, la boucle tournerait jusqu'a la patience.
    threading.Timer(0.3, arret.set).start()
    lire_en_boucle(flux, FauxReechantillonneur(), arret, recolte.append, patience=patience)
    return recolte


# ── La reprise apres EAGAIN ───────────────────────────────────────────────


def test_un_refus_initial_ne_fait_pas_abandonner():
    """Le cas exact de la machine reelle : EAGAIN avant la premiere trame."""
    flux = FauxFlux(refus=1)
    assert lire(flux), "abandonner au premier EAGAIN, c'est ne jamais rien capter"


def test_plusieurs_refus_de_suite_sont_toleres():
    flux = FauxFlux(refus=5)
    assert lire(flux)
    assert flux.livrees > 0


def test_le_generateur_est_recree_et_non_repris():
    """La subtilite qui fait qu'un simple `try` autour de la boucle echoue.

    Un generateur traverse par une exception est mort : le reprendre rend
    StopIteration tout de suite, donc du silence sans erreur — le pire cas.
    """
    flux = FauxFlux(refus=3)
    lire(flux)
    assert flux.generateurs_crees >= 4, (
        "le generateur doit etre recree apres chaque refus, pas repris"
    )


def test_sans_aucun_refus_tout_passe():
    flux = FauxFlux(refus=0)
    assert lire(flux)


# ── La borne : un micro vraiment muet ne doit pas bloquer ─────────────────


def test_un_micro_definitivement_muet_finit_par_lever():
    """Sans borne, la boucle tournerait indefiniment — ce qui ressemble a un
    blocage de l'application, et se diagnostique bien plus mal qu'une erreur.
    """
    flux = FauxFlux(refus=10**9)
    with pytest.raises(TimeoutError, match="ne produit aucun son"):
        lire(flux, arret=threading.Event(), patience=0.15)


def test_apres_du_son_recu_la_patience_ne_s_applique_plus():
    """Un silence en cours d'enregistrement est normal : on parle, on
    s'arrete, on reprend. Seule l'absence TOTALE de son est une panne.
    """
    flux = FauxFlux(refus=0, trames=1)
    flux.refus_restants = 0
    recolte = lire(flux, patience=0.05)
    assert recolte, "le son deja recu doit desamorcer la borne"


# ── L'arret demande est respecte ──────────────────────────────────────────


def test_l_arret_interrompt_la_lecture():
    from enregistrer_voix import lire_en_boucle

    flux = FauxFlux(refus=0, trames=10**6)
    arret = threading.Event()
    recolte: list[bytes] = []

    def garder(octets):
        recolte.append(octets)
        if len(recolte) >= 5:
            arret.set()

    lire_en_boucle(flux, FauxReechantillonneur(), arret, garder, patience=2.0)
    assert 5 <= len(recolte) <= 6, "l'arret doit etre pris en compte tout de suite"
