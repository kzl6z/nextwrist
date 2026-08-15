"""Le volume, et ce qui empeche Nova de confisquer la machine.

DEUX SUJETS DANS UN FICHIER, ET CE N'EST PAS UN HASARD

Le volume est la premiere action qui ne demande aucune reflexion sur le
bareme : le son se remonte. La charge est l'inverse — c'est le sujet ou une
valeur par defaut jamais choisie prenait toute la machine.

Les deux se rejoignent sur un point : ce sont les deux endroits ou Nova
touche a ce que la personne est en train de faire pendant qu'elle le fait.
"""

import subprocess
import sys

import pytest

from nova import orchestrator
from nova.core import contrats, plateforme
from nova.core.registre import Registre
from nova.outils import systeme
from nova.voice import comprehension as vc
from nova.voice import intentions as vi


def comprise(texte: str, *, sure: bool = True):
    return vc.Comprehension(
        texte=texte, origine=texte,
        confiance=0.95 if sure else 0.40,
        intention=vi.reconnaitre(texte),
    )


@pytest.fixture
def osascript(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")

    class Carnet(list):
        sortie, code, erreur = "60", 0, ""

        def repondre(self, **quoi):
            self.__dict__.update(quoi)

    carnet = Carnet()
    monkeypatch.setattr(
        systeme.subprocess, "run",
        lambda c, **kw: carnet.append(c)
        or subprocess.CompletedProcess(c, carnet.code, carnet.sortie, carnet.erreur),
    )
    return carnet


# ── Deux silences qui n'ont rien a voir ───────────────────────────────────


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("coupe le son", "silence"),
        ("mets en sourdine", "silence"),
        ("coupe le volume", "silence"),
        ("tais toi", "stop_parole"),
        ("arrête de parler", "stop_parole"),
        ("chut", "stop_parole"),
    ],
)
def test_couper_le_son_et_se_taire_sont_deux_demandes(phrase, attendu):
    """⚠️ LE MEME DEFAUT QUE « arrête l'ordinateur », AU MEME ENDROIT.

    « coupe le son » parle du HAUT-PARLEUR ; « tais-toi » parle de NOVA. Les
    deux vivaient sous une seule intention, sans consequence tant qu'aucun
    outil n'y repondait. Brancher la sourdine systeme aurait rendu le Mac
    muet chaque fois qu'on demande a Nova de se taire — et il aurait fallu
    aller le rallumer a la souris.
    """
    assert vi.reconnaitre(phrase).nom == attendu


def test_se_taire_ne_declenche_aucune_action(outils_du_son):
    """`stop_parole` est reconnu et n'a pas d'outil : Nova en parle, elle
    n'agit pas. C'est exactement le comportement voulu tant que « arrêter de
    parler » n'est pas implemente cote interface."""
    assert orchestrator.executer_intention(comprise("tais toi")).etat == "ignoree"
    assert outils_du_son == []


# ── Le volume ─────────────────────────────────────────────────────────────


def test_monter_le_son_passe_un_pas_positif(osascript):
    systeme.ReglerLeSon("monter_le_son", "", systeme.PAS_VOLUME).executer()
    assert osascript[0][-1] == str(systeme.PAS_VOLUME)


def test_baisser_le_son_passe_un_pas_negatif(osascript):
    systeme.ReglerLeSon("baisser_le_son", "", -systeme.PAS_VOLUME).executer()
    assert osascript[0][-1] == f"-{systeme.PAS_VOLUME}"


def test_le_niveau_atteint_est_annonce(osascript):
    """« Volume à 72 % » vaut mieux que « c'est fait » : ca dit ou on en est
    sans avoir a regarder l'ecran."""
    osascript.repondre(sortie="72")
    assert "72" in systeme.ReglerLeSon("monter_le_son", "", 12).executer()


def test_couper_le_son_ne_passe_pas_de_pas(osascript):
    message = systeme.ReglerLeSon("couper_le_son", "", None).executer()
    assert "coupé" in message
    assert len(osascript[0]) == 3, "la sourdine n'a pas d'argument"


def test_une_sortie_qui_gere_son_volume_le_dit(osascript):
    """Un casque Bluetooth rend `missing value`. Annoncer un reglage qui n'a
    pas eu lieu serait un mensonge de plus dans la meme famille."""
    osascript.repondre(sortie="inconnu")
    with pytest.raises(systeme.ActionImpossible, match="elle-même"):
        systeme.ReglerLeSon("monter_le_son", "", 12).executer()


def test_le_pas_est_borne_dans_le_script():
    """Sans bornes, « monte le son » dix fois ecrirait 220 — refuse par
    macOS, donc une action qui echoue au lieu de saturer."""
    assert "if vise > 100 then set vise to 100" in systeme._SCRIPT_VOLUME
    assert "if vise < 0 then set vise to 0" in systeme._SCRIPT_VOLUME


def test_monter_le_son_demute(osascript):
    """Monter le son sur une machine en sourdine ne doit rien changer
    d'audible si on oublie de lever la sourdine — donc on la leve."""
    assert "set volume without output muted" in systeme._SCRIPT_VOLUME


def test_le_son_est_reversible_et_ne_demande_rien():
    """L'exemple canonique : l'erreur se corrige en la redemandant. Demander
    confirmation pour monter le son serait absurde — on le demande parce
    qu'on n'entend pas, pas pour en discuter."""
    for outil in systeme._actions_du_son():
        assert outil.niveau == contrats.REVERSIBLE
        assert not contrats.exige_confirmation(outil.niveau)


@pytest.fixture
def outils_du_son(monkeypatch):
    from nova import outils as module

    registre = Registre("outil")
    faits: list[str] = []

    class Faux:
        capacite, niveau = "action", contrats.REVERSIBLE

        def __init__(self, nom):
            self.nom, self.description = nom, nom

        def executer(self):
            faits.append(self.nom)
            return "fait"

    for nom in ("monter_le_son", "baisser_le_son", "couper_le_son"):
        registre.enregistrer(Faux(nom))
    monkeypatch.setattr(module, "registre_outils", registre)
    return faits


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("monte le son", "monter_le_son"),
        ("plus fort", "monter_le_son"),
        ("baisse le volume", "baisser_le_son"),
        ("moins fort", "baisser_le_son"),
        ("coupe le son", "couper_le_son"),
    ],
)
def test_de_la_phrase_a_l_action(outils_du_son, phrase, attendu):
    assert orchestrator.executer_intention(comprise(phrase)).agie
    assert outils_du_son == [attendu]


def test_une_parole_douteuse_ne_touche_pas_au_volume(outils_du_son):
    assert orchestrator.executer_intention(comprise("monte le son", sure=False)).etat == "ignoree"
    assert outils_du_son == []


# ── La machine reste a son proprietaire ───────────────────────────────────


def test_la_transcription_laisse_deux_coeurs(monkeypatch):
    """⚠️ L'ARGUMENT ABSENT ETAIT UN CHOIX QUE PERSONNE N'AVAIT FAIT.

    `WhisperModel` etait construit sans `cpu_threads`. Le defaut de la
    bibliotheque est 0, et 0 y signifie « tous les coeurs ». Pendant chaque
    transcription, la machine entiere se retrouvait sans un seul coeur libre
    — pas seulement Nova : le systeme, et ce que la personne faisait a cote.
    """
    from nova.voice import transcribe

    monkeypatch.setattr(transcribe.os, "cpu_count", lambda: 8)
    assert transcribe._fils_de_calcul() == 6


def test_une_machine_minuscule_garde_au_moins_un_fil(monkeypatch):
    """Sur deux coeurs, « tous sauf deux » vaut zero — et zero signifierait
    « prends tout », c'est-a-dire exactement l'inverse."""
    from nova.voice import transcribe

    monkeypatch.setattr(transcribe.os, "cpu_count", lambda: 2)
    assert transcribe._fils_de_calcul() == 1


def test_un_reglage_explicite_l_emporte(monkeypatch):
    from nova.settings import get_settings
    from nova.voice import transcribe

    reglages = get_settings()
    monkeypatch.setattr(reglages, "whisper_threads", 3)
    monkeypatch.setattr(transcribe, "get_settings", lambda: reglages)
    assert transcribe._fils_de_calcul() == 3


# ── La mesure qui departage deux pannes opposees ──────────────────────────


def test_le_swap_se_lit_quelle_que_soit_la_langue_du_systeme():
    """LE DETAIL QUI NE SE VOIT JAMAIS EN TEST ET TOUJOURS CHEZ L'UTILISATEUR.

    `sysctl` suit la langue du systeme pour le separateur decimal. Sur un Mac
    francais, « used = 1234,50M » — et `float("1234,50")` leve.
    """
    anglais = "total = 2048,00M  used = 1234,50M  free = 813,50M"
    assert plateforme._octets(anglais, "used") == 1.21

    point = "total = 2048.00M  used = 1234.50M  free = 813.50M"
    assert plateforme._octets(point, "used") == 1.21


def test_les_unites_sont_converties():
    assert plateforme._octets("used = 2,00G", "used") == 2.0
    assert plateforme._octets("used = 512,00M", "used") == 0.5
    assert plateforme._octets("used = 0,00M", "used") == 0.0


def test_un_demi_giga_de_swap_n_est_pas_une_pagination():
    """macOS y depose des pages froides en permanence. Alerter la-dessus
    apprendrait a ignorer l'alerte."""
    assert not plateforme.Pression(0.4, 2.0).pagine
    assert plateforme.Pression(1.5, 2.0).pagine


def test_une_mesure_impossible_ne_declare_pas_la_paix():
    """`disponible=False` veut dire « je ne sais pas », pas « tout va bien ».

    Repondre `pagine=False` a une mesure ratee ferait chercher la panne du
    mauvais cote — exactement ce que cette mesure existe pour eviter.
    """
    inconnue = plateforme.Pression(0.0, 0.0, disponible=False)
    assert not inconnue.pagine
    assert "inconnue" in str(inconnue)


def test_la_pression_ne_leve_jamais(monkeypatch):
    """Un diagnostic qui fait tomber Nova serait pire que pas de diagnostic."""
    monkeypatch.setattr(plateforme.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        plateforme, "_swap_macos", lambda: (_ for _ in ()).throw(OSError("sysctl absent"))
    )
    assert plateforme.pression_memoire().disponible is False
