"""Fermer une application : la symetrique d'ouvrir, sauf sur un point.

CE QUI N'EST PAS SYMETRIQUE

Ouvrir se defait en fermant. Fermer se defait en rouvrant — mais pas le
travail non enregistre, et c'est ce qui a rendu le niveau discutable.

La reponse tient a la MECANIQUE, pas au vocabulaire : un `quit` est une
demande, pas un ordre. Une application qui a du travail en cours la refuse et
affiche sa propre fenetre d'enregistrement. Le veto sur la partie
irreversible appartient a macOS ; Nova n'a pas les moyens de passer outre par
ce chemin, et n'a donc pas a demander une permission qu'elle ne pourrait pas
utiliser.

Ce qui reste de son cote est le devoir de ne pas mentir : annoncer « c'est
ferme » pendant qu'une fenetre de sauvegarde attend serait faux, et c'est la
que portent la moitie des tests de ce fichier.
"""

import subprocess
import sys

import pytest

from nova import orchestrator
from nova.core import actions, contrats
from nova.core.registre import Registre
from nova.outils import applications, systeme
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
    """Remplace `osascript` par un carnet : ce qu'on lui demande, ce qu'il rend."""
    monkeypatch.setattr(sys, "platform", "darwin")

    class Carnet(list):
        sortie, code, erreur = "fermee", 0, ""

        def repondre(self, **quoi):
            self.__dict__.update(quoi)

    carnet = Carnet()

    def faux_run(commande, **kw):
        carnet.append(commande)
        return subprocess.CompletedProcess(commande, carnet.code, carnet.sortie, carnet.erreur)

    monkeypatch.setattr(systeme.subprocess, "run", faux_run)
    return carnet


# ── Le declencheur : « arrête l'ordinateur » n'est pas une application ────


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("arrête l'ordinateur", "arret_pc"),
        ("arrête le pc", "arret_pc"),
        ("éteins l'ordinateur", "arret_pc"),
        ("arrête Spotify", "fermer_application"),
        ("ferme Discord", "fermer_application"),
        ("quitte Safari", "fermer_application"),
    ],
)
def test_le_declencheur_le_plus_precis_gagne(phrase, attendu):
    """LE DEFAUT QUI ATTENDAIT SON OUTIL.

    « arrête l'ordinateur » contient « arrete » — declencheur de
    `fermer_application` — ET « arrete l ordinateur », declencheur d'
    `arret_pc`. Le premier trouve dans la table gagnait, c'est-a-dire le plus
    vague : la phrase etait comprise comme « ferme l'application ordinateur ».

    Sans outil branche, Nova en parlait et n'agissait pas. Avec l'outil, la
    meme phrase serait devenue une action sur une cible inventee. Le defaut
    n'a pas ete cree par l'outil de ce fichier : il l'attendait.
    """
    assert vi.reconnaitre(phrase).nom == attendu


# ── Le piege AppleScript ──────────────────────────────────────────────────


def test_on_verifie_qu_elle_tourne_avant_de_dire_quit(osascript):
    """⚠️ `tell application "X" to quit` LANCE X s'il ne tourne pas.

    Une demande de fermeture ouvrirait l'application — le contraire exact de
    ce qui a ete dit. Le test de presence doit donc precéder le `quit`, pas
    le suivre.
    """
    avant_quit = systeme._SCRIPT_FERMER.split("quit")[0]
    assert "is running" in avant_quit
    assert 'return "absente"' in avant_quit


def test_la_presence_se_juge_sur_l_application_pas_sur_le_processus():
    """Le processus de « Visual Studio Code » s'appelle « Code ».

    Chercher le nom dans la liste des processus aurait fait repondre « elle
    n'est pas ouverte » a une fenetre bien visible a l'ecran. `is running`
    raisonne sur l'APPLICATION — et evite au passage de dependre de System
    Events, donc de l'autorisation d'Accessibilite.
    """
    assert "System Events" not in systeme._SCRIPT_FERMER
    assert "is running" in systeme._SCRIPT_FERMER


def test_le_nom_arrive_en_argument_jamais_dans_le_script(osascript):
    """La regle du shell, appliquee a AppleScript.

    Recoller le nom dans `tell application "…" to quit` rouvrirait la porte
    que la liste d'arguments avait fermee. `on run argv` est a AppleScript ce
    qu'une requete parametree est au SQL.
    """
    systeme.FermerApplication().executer("Discord")
    commande = osascript[0]
    assert commande[-1] == "Discord", "le nom doit etre le dernier argument"
    assert "Discord" not in commande[2], "le nom a ete recolle dans le script"
    assert "item 1 of argv" in commande[2]


@pytest.mark.parametrize(
    "cible",
    ['Discord" to quit\ntell application "Terminal', "-e", "$(whoami)", "`id`", "", "A" * 200],
)
def test_un_nom_douteux_est_refuse_avant_le_systeme(cible, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    with pytest.raises(systeme.ActionImpossible):
        systeme.FermerApplication().executer(cible)


def test_un_nom_commencant_par_un_tiret_est_refuse(monkeypatch):
    """Un argument en « - » se fait prendre pour une OPTION par la commande
    qui le recoit. Aucune application ne s'appelle ainsi."""
    monkeypatch.setattr(sys, "platform", "darwin")
    for outil in (systeme.FermerApplication(), systeme.OuvrirApplication()):
        with pytest.raises(systeme.ActionImpossible):
            outil.executer("-e")


# ── L'honnetete du compte rendu ───────────────────────────────────────────


def test_une_fermeture_reussie_le_dit(osascript):
    osascript.repondre(sortie="fermee")
    assert "fermée" in systeme.FermerApplication().executer("Discord")


def test_une_application_qui_ne_tourne_pas_le_dit(osascript):
    """« Discord n'est pas ouverte » vaut mieux que « Discord est fermée » :
    la seconde laisserait croire que Nova vient d'agir."""
    osascript.repondre(sortie="absente")
    message = systeme.FermerApplication().executer("Discord")
    assert "n'est pas ouverte" in message


def test_une_application_qui_refuse_de_partir_ne_passe_pas_pour_fermee(osascript):
    """LE TEST QUI JUSTIFIE LE NIVEAU REVERSIBLE.

    Une application avec du travail non enregistre refuse de quitter et
    affiche sa propre demande. Nova doit le dire — annoncer « c'est fermé »
    pendant qu'une fenetre de sauvegarde attend serait un mensonge, et un
    mensonge sur ce sujet precis vaudrait mieux ne pas exister.
    """
    osascript.repondre(sortie="refusee")
    message = systeme.FermerApplication().executer("Pages")
    assert message != "Pages est fermée.", "Nova annonce une fermeture qui n'a pas eu lieu"
    assert "ne s'est pas fermée" in message
    assert "enregistres" in message


def test_un_echec_d_osascript_leve_au_lieu_de_mentir(osascript):
    osascript.repondre(code=1, sortie="", erreur="autorisation refusée")
    with pytest.raises(systeme.ActionImpossible, match="autorisation"):
        systeme.FermerApplication().executer("Discord")


def test_hors_macos_l_action_le_dit_au_lieu_d_essayer(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(systeme.ActionImpossible, match="macOS"):
        systeme.FermerApplication().executer("Discord")


# ── Le niveau, et ce qui le ferait changer ────────────────────────────────


def test_fermer_est_reversible_et_ne_demande_donc_rien():
    assert systeme.FermerApplication.niveau == contrats.REVERSIBLE
    assert not contrats.exige_confirmation(systeme.FermerApplication.niveau)


def test_aucune_fermeture_forcee_n_est_livree():
    """Une fermeture FORCEE detruirait le travail non enregistre sans rien
    demander : elle serait IRREVERSIBLE, et elle n'existe pas.

    Le declencheur vocal « kill » aboutit sur la fermeture douce — le mot est
    brutal, l'action ne l'est pas. Ce test tombera le jour ou quelqu'un
    ajoutera un `-9` ou un « force quit » sans revoir le niveau.
    """
    script = systeme._SCRIPT_FERMER.lower()
    assert "force" not in script
    assert "-9" not in script
    assert "kill" not in script


# ── Le raccord complet ────────────────────────────────────────────────────


@pytest.fixture
def outils(monkeypatch):
    from nova import outils as module

    registre = Registre("outil")
    faits: list[tuple[str, str]] = []

    class Ouvrir:
        nom, description, capacite = "ouvrir_application", "Ouvre", "action"
        niveau = contrats.REVERSIBLE

        def executer(self, cible):
            faits.append(("ouvrir", cible))
            return f"{cible} est ouverte."

    class Fermer:
        nom, description, capacite = "fermer_application", "Ferme", "action"
        niveau = contrats.REVERSIBLE

        def executer(self, cible):
            faits.append(("fermer", cible))
            return f"{cible} est fermée."

    registre.enregistrer(Ouvrir)
    registre.enregistrer(Fermer)
    monkeypatch.setattr(module, "registre_outils", registre)
    monkeypatch.setattr(
        applications, "installees",
        lambda **_: ("Discord", "Google Chrome", "Adobe Photoshop 2025", "Safari"),
    )
    return faits


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("ferme Discord", "Discord"),
        ("quitte Chrome", "Google Chrome"),          # sous-nom
        ("ferme Photoshop", "Adobe Photoshop 2025"), # sous-nom
        ("arrête Saffari", "Safari"),                # meme son, sans rival
    ],
)
def test_fermer_herite_de_tout_le_travail_d_ouvrir(outils, phrase, attendu):
    """Le catalogue, le sous-nom et la phonetique servent les deux sens sans
    une ligne de plus : c'est le signe que le decoupage etait le bon."""
    assert orchestrator.executer_intention(comprise(phrase)).agie
    assert outils == [("fermer", attendu)]


def test_fermer_une_application_absente_le_dit(outils):
    resultat = orchestrator.executer_intention(comprise("ferme Blender"))
    assert resultat.etat == "echouee"
    assert "Blender" in resultat.message
    assert outils == []


def test_une_parole_douteuse_ne_ferme_rien(outils):
    """Les quatre barrieres valent pour fermer comme pour ouvrir."""
    assert orchestrator.executer_intention(comprise("ferme Discord", sure=False)).etat == "ignoree"
    assert outils == []


def test_fermer_declare_son_catalogue():
    assert actions.ACTIONS["fermer_application"].catalogue == actions.CATALOGUE_APPLICATIONS
