"""Les premiers outils qui AGISSENT sur la machine.

⚠️ CE FICHIER EST LE PLUS DANGEREUX DU PROJET. IL MERITE D'ETRE LU EN ENTIER.

Jusqu'ici Nova ne faisait que lire. Ces outils-la modifient l'etat de
l'ordinateur, sur la foi d'une phrase prononcee, transcrite par un modele qui
se trompe, interpretee par un autre modele qui se trompe aussi.

TROIS REGLES, ET AUCUNE N'EST NEGOCIABLE

1. JAMAIS DE SHELL.

   `subprocess.run("open -a " + nom)` serait une porte ouverte : il suffirait
   qu'une transcription contienne « ; rm -rf ~ » pour que Nova l'execute. On
   passe donc TOUJOURS une liste d'arguments, jamais une chaine, et
   `shell=False` (le defaut, qu'on ne change pas).

   Avec une liste, « ; rm -rf ~ » est un NOM D'APPLICATION contenant des
   caracteres bizarres. macOS ne le trouve pas, et il ne se passe rien.

2. LES ARGUMENTS SONT VALIDES AVANT, PAS APRES.

   Un nom d'application est fait de lettres, de chiffres, d'espaces et de
   quelques signes. Tout le reste est refuse — non parce que c'est
   exploitable ici, mais parce que la validation doit tenir meme si
   quelqu'un remplace `open` par autre chose dans trois ans.

3. LE NIVEAU DIT LA VERITE.

   Eteindre l'ordinateur est IRREVERSIBLE. Le declarer REVERSIBLE parce que
   « on peut le rallumer » serait un mensonge : le travail non enregistre,
   lui, ne se rallume pas.

CE QUI N'EST PAS ICI, ET POURQUOI

Aucun outil generique du genre « executer une commande ». C'est la
fonctionnalite que tout le monde ajoute en premier et qui annule toutes les
autres protections d'un coup. Chaque action que Nova sait faire est ecrite
ici, nommement, avec son niveau.
"""

from __future__ import annotations

import re
import subprocess
import sys

from nova.core import contrats
from nova.logging_setup import get_logger

log = get_logger(__name__)

#: Delai maximal d'une action systeme. Court a dessein : `open` rend la main
#: immediatement, et une commande qui tarde davantage est bloquee.
DELAI_S = 10.0

#: Ce qu'un nom d'application a le droit de contenir. Volontairement etroit :
#: lettres (accents compris), chiffres, espace, point, tiret, apostrophe,
#: esperluette. Assez pour « Visual Studio Code », « Adobe Photoshop 2025 »
#: ou « Numbers ». Rien de plus.
_NOM_VALIDE = re.compile(r"^[\w .\-'&+]{1,60}$", re.UNICODE)


class ActionImpossible(RuntimeError):
    """L'action n'a pas pu etre effectuee, avec la raison en francais."""


def _verifier_macos(action: str) -> None:
    if sys.platform != "darwin":
        raise ActionImpossible(
            f"« {action} » n'est disponible que sur macOS "
            f"(cette machine : {sys.platform})."
        )


def _nom_propre(nom: str) -> str:
    """Valide un nom d'application, ou refuse.

    Le message dit ce qui a ete refuse et pourquoi : une transcription
    bancale doit se diagnostiquer sans lire le code.
    """
    propre = (nom or "").strip()
    if not propre:
        raise ActionImpossible("Aucune application indiquee.")
    if propre.startswith("-"):
        # Aucune application ne s'appelle ainsi, et un argument commencant par
        # un tiret se fait prendre pour une OPTION par la commande qui le
        # recoit. Le refuser coute une ligne ; le laisser passer laisserait un
        # nom d'application piloter `osascript`.
        raise ActionImpossible(f"« {propre} » ne peut pas etre un nom d'application.")
    if not _NOM_VALIDE.match(propre):
        raise ActionImpossible(
            f"« {propre} » n'est pas un nom d'application valide. "
            "Attendu des lettres, des chiffres et des espaces."
        )
    return propre


class OuvrirApplication:
    """Ouvre une application par son nom.

    Niveau REVERSIBLE : si Nova se trompe d'application, on ferme la fenetre
    et il ne reste rien. C'est exactement le genre d'action qui ne merite pas
    d'interrompre la conversation pour demander.
    """

    nom = "ouvrir_application"
    description = "Ouvre une application par son nom (macOS)"
    capacite = "action"
    niveau = contrats.REVERSIBLE

    def executer(self, cible: str) -> str:
        _verifier_macos(self.nom)
        application = _nom_propre(cible)
        # Liste d'arguments, jamais une chaine : c'est ce qui rend l'injection
        # impossible plutot qu'improbable.
        resultat = subprocess.run(          # noqa: S603
            ["/usr/bin/open", "-a", application],
            capture_output=True, text=True, timeout=DELAI_S,
        )
        if resultat.returncode != 0:
            detail = (resultat.stderr or "").strip()
            raise ActionImpossible(
                f"Impossible d'ouvrir « {application} »."
                + (f" {detail}" if detail else " Est-elle installee ?")
            )
        log.info("Application ouverte : %s", application)
        return f"{application} est ouverte."


#: Le script de fermeture. Le nom de l'application arrive en ARGUMENT, il
#: n'est jamais recolle dans le texte du script.
#:
#: C'est la meme regle que pour le shell, appliquee a AppleScript : construire
#: `tell application "…" to quit` par concatenation rouvrirait exactement la
#: porte que la liste d'arguments avait fermee. `on run argv` est a
#: AppleScript ce qu'une requete parametree est au SQL.
#:
#: LE PIEGE APPLESCRIPT QUE LE PREMIER TEST EVITE
#:
#: `tell application "Machin" to quit` LANCE Machin s'il ne tourne pas. Une
#: demande de fermeture ouvrirait donc l'application — le contraire exact de
#: ce qui a ete dit. On teste avant, et on ne dit `quit` qu'a ce qui tourne.
#:
#: POURQUOI `is running` ET NON `System Events`
#:
#: La verification evidente — « ce nom figure-t-il dans la liste des
#: processus ? » — se trompe sur les applications dont le processus ne porte
#: pas le nom du dossier. Le processus de « Visual Studio Code » s'appelle
#: « Code » : Nova aurait repondu « elle n'est pas ouverte » a une fenetre
#: bien visible a l'ecran.
#:
#: `application X is running` raisonne sur l'APPLICATION, pas sur le nom du
#: processus, et c'est l'une des rares proprietes qu'on peut lire sans la
#: lancer. Elle evite au passage de dependre de System Events, donc de
#: l'autorisation d'Accessibilite — une permission de trop pour fermer une
#: fenetre.
_SCRIPT_FERMER = """
on run argv
    set nomApp to item 1 of argv
    if not (application nomApp is running) then return "absente"
    tell application nomApp to quit
    repeat 10 times
        delay 0.2
        if not (application nomApp is running) then return "fermee"
    end repeat
    return "refusee"
end run
"""


class FermerApplication:
    """Ferme une application, proprement.

    POURQUOI REVERSIBLE ET NON CONSEQUENT — LE PREMIER NIVEAU QUI SE DISCUTE

    « Fermer » evoque une perte : le travail non enregistre. C'est ce qui a
    fait classer `eteindre_ordinateur` en IRREVERSIBLE, et le raisonnement
    semblait devoir se repeter ici.

    Il ne se repete pas, et la difference est mecanique. Une extinction
    s'impose aux applications ; un `quit` leur est PROPOSE. Une application
    qui a du travail non enregistre refuse de partir et affiche sa propre
    demande d'enregistrement. Le veto sur la partie irreversible appartient
    donc a macOS et a l'application, pas a Nova — qui n'a pas les moyens de
    passer outre par ce chemin.

    Ce qui reste du cote de Nova est un devoir d'honnetete : annoncer « c'est
    ferme » alors qu'une fenetre de sauvegarde attend serait un mensonge, et
    un mensonge sur ce sujet precis vaut mieux ne pas exister. On verifie donc
    que le processus a bel et bien disparu avant de le dire.

    CE QUI FERAIT CHANGER LE NIVEAU

    Une fermeture FORCEE — `kill -9`, ou `osascript` avec « force quit » —
    detruirait le travail non enregistre sans rien demander a personne. Elle
    serait IRREVERSIBLE, et elle n'est pas implementee. Le declencheur vocal
    « kill » aboutit ici, sur la fermeture douce : le mot est brutal, l'action
    ne l'est pas.
    """

    nom = "fermer_application"
    description = "Ferme une application par son nom (macOS)"
    capacite = "action"
    niveau = contrats.REVERSIBLE

    def executer(self, cible: str) -> str:
        _verifier_macos(self.nom)
        application = _nom_propre(cible)
        resultat = subprocess.run(          # noqa: S603
            ["/usr/bin/osascript", "-e", _SCRIPT_FERMER, application],
            capture_output=True, text=True, timeout=DELAI_S,
        )
        if resultat.returncode != 0:
            detail = (resultat.stderr or "").strip()
            raise ActionImpossible(
                f"Impossible de fermer « {application} »." + (f" {detail}" if detail else "")
            )

        etat = (resultat.stdout or "").strip()
        if etat == "absente":
            return f"{application} n'est pas ouverte."
        if etat == "refusee":
            # Le seul cas ou l'application a le dernier mot, et le seul ou
            # Nova pourrait mentir sans s'en apercevoir.
            log.info("« %s » n'a pas quitte : elle attend probablement une reponse.", application)
            return (
                f"{application} ne s'est pas fermée — elle attend probablement "
                "que tu enregistres quelque chose. Je la laisse."
            )
        log.info("Application fermee : %s", application)
        return f"{application} est fermée."


class EteindreOrdinateur:
    """Eteint la machine.

    Niveau IRREVERSIBLE, et la nuance compte : on peut rallumer un
    ordinateur, on ne peut pas rallumer le travail non enregistre. Classer
    cette action « reversible » parce que le bouton existe serait un
    mensonge confortable.
    """

    nom = "eteindre_ordinateur"
    description = "Eteint l'ordinateur"
    capacite = "action"
    niveau = contrats.IRREVERSIBLE

    def executer(self) -> str:
        _verifier_macos(self.nom)
        resultat = subprocess.run(          # noqa: S603
            ["/usr/bin/osascript", "-e", 'tell application "System Events" to shut down'],
            capture_output=True, text=True, timeout=DELAI_S,
        )
        if resultat.returncode != 0:
            raise ActionImpossible((resultat.stderr or "Extinction refusee.").strip())
        log.warning("Extinction de l'ordinateur demandee.")
        return "L'ordinateur va s'eteindre."


def enregistrer_actions_systeme(registre) -> None:
    """Ajoute les actions systeme au registre fourni.

    Une fonction plutot qu'un decorateur au chargement : les tests doivent
    pouvoir construire un registre isole, et l'application doit pouvoir
    choisir de ne pas les activer du tout.
    """
    for outil in (OuvrirApplication(), FermerApplication(), EteindreOrdinateur()):
        if outil.nom not in registre:
            registre.enregistrer(outil)
