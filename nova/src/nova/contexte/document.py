"""Le projet, ecrit sur le disque.

    « Bon, j'aimerais creer une centrale nucleaire. »
    … on explique, Nova note …
    « Veux-tu que je mette ce projet sur ton Bureau,
       dans un dossier « centrale nucleaire » ? »
    « oui »

⚠️ CE MODULE NE FAIT PAS APPEL AU MODELE, ET C'EST UN CHOIX, PAS UNE ECONOMIE.

« Elle synthetise » : la synthese a deja eu lieu. Elle s'est faite phrase par
phrase, quand Nova a note l'objectif, la decision et sa raison, la tache. Ce
qui reste ici est de la MISE EN FORME de ce qui a ete reellement dit.

Demander a un modele de 3 milliards de parametres de reecrire ces lignes en
prose ferait exactement une chose de plus : inventer. Sur un document qu'on
gardera, qu'on relira dans six mois, et dont on croira qu'il dit ce qu'on
avait decide. Une decision qu'on n'a jamais prise mais qui figure au proces
verbal est pire que pas de proces verbal du tout.

Le document ne contient donc rien que la base ne contienne. En echange, il
est instantane, il ne depend d'aucun modele charge, et il dit vrai.

⚠️ ET IL PORTE `pourquoi`.

C'est la colonne pour laquelle la table `elements` existe sous cette forme :
« rappelle-moi pourquoi on avait choisi cette approche » ne se repond pas
avec une liste de decisions. Une decision sans son motif est une contrainte
qu'on subit six mois plus tard sans savoir pourquoi — et un document qui la
perdrait ne vaudrait pas le disque qu'il occupe.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from nova.contexte import Projet

#: La ligne par laquelle Nova signe ses documents.
#:
#: ⚠️ ELLE NE SERT PAS QU'A FAIRE JOLI : ELLE REPOND A UNE QUESTION.
#:
#: « Ce fichier a-t-il ete repris a la main ? » n'a aucune autre reponse
#: bon marche. Avant de remplacer un document, Nova regarde si sa signature
#: est encore la — et si elle ne l'est plus, elle le DIT dans sa question,
#: parce que ce qu'on s'apprete a perdre n'est plus le sien.
SIGNATURE = "*Écrit par Nova le"

#: Le nom sous lequel l'ancienne version est gardee avant remplacement.
#:
#: Une seule, remplacee a chaque fois : garder tout l'historique remplirait
#: le dossier de fichiers que personne ne relit. Une seule suffit a rattraper
#: le « oui » de trop, qui est le seul accident possible ici.
SUFFIXE_PRECEDENTE = " (version précédente)"

#: Ce qu'il faut avoir dit d'un projet pour qu'un dossier vaille la peine.
#:
#: ⚠️ ON COMPTE CE QUI A ETE NOTE, ON NE DEVINE PAS L'INTENTION.
#:
#: L'alternative etait de demander a un modele « ce projet merite-t-il un
#: dossier ? » — un appel de plus sur le chemin de la reponse, pour une
#: question dont la reponse est un nombre. L'objectif compte pour un : c'est
#: souvent la premiere chose dite, et souvent la plus importante.
#:
#: Trois : en dessous, on propose un dossier a quelqu'un qui a prononce deux
#: phrases, et la proposition passe pour du zele.
ASSEZ = 3


def poids(projet: Projet) -> int:
    """Combien de choses Nova a notees sur ce projet."""
    return (1 if (projet.objectif or "").strip() else 0) + len(projet.elements)


def merite_un_dossier(projet: Projet | None) -> bool:
    """Faut-il proposer d'ecrire ce projet sur le disque ?

    ⚠️ TROIS CONDITIONS, ET LA DEUXIEME EST CELLE QU'ON OUBLIE.

    Le projet est assez fourni, il n'a pas deja son dossier, et la question
    n'a pas deja ete posee. Sans la troisieme, un refus serait suivi de la
    meme question a la decision suivante — ce n'est plus une proposition,
    c'est du harcelement, et l'on finit par ne plus rien dicter.
    """
    if projet is None or projet.dossier or projet.document_propose_le:
        return False
    return poids(projet) >= ASSEZ


def question(projet: Projet) -> str:
    """Comment Nova propose, a voix haute.

    Elle nomme le dossier qu'elle creerait. Une proposition qui dit seulement
    « je te mets ca sur ton Bureau ? » se fait accepter sans qu'on sache ce
    qui va apparaitre, et le nom est precisement ce qu'on voudrait corriger.
    """
    return f"Veux-tu que je mette ce projet sur ton Bureau, dans un dossier « {projet.nom} » ?"


def nom_du_fichier(projet: Projet) -> str:
    """Le document porte le nom du projet. Un seul par dossier."""
    return f"{projet.nom}.md"


def _points(titre: str, elements, *, avec_raison: bool = False) -> list[str]:
    if not elements:
        return []
    lignes = [f"## {titre}", ""]
    for element in elements:
        lignes.append(f"- {element.contenu}")
        # ⚠️ LA RAISON VA SUR SA PROPRE LIGNE, PAS EN INCISE.
        #
        # « — parce que il n'y a pas de pompe » : la raison est enregistree
        # telle qu'elle a ete dite, elision comprise, et recoller « parce
        # que » devant produit un francais faux une fois sur deux. Un
        # document qu'on garde n'a pas le droit d'etre mal ecrit.
        if avec_raison and (element.pourquoi or "").strip():
            lignes.append(f"  *Pourquoi :* {element.pourquoi.strip()}")
    lignes.append("")
    return lignes


def _taches(elements) -> list[str]:
    if not elements:
        return []
    # Des cases a cocher : le document n'est pas un rapport, c'est un point de
    # depart. On doit pouvoir le continuer a la main.
    return ["## À faire", "", *[f"- [ ] {e.contenu}" for e in elements], ""]


def rendre(projet: Projet, *, le_jour: date | None = None) -> str:
    """Le projet en Markdown. Rien qui ne vienne de ce qui a ete dit."""
    jour = (le_jour or date.today()).isoformat()

    lignes = [f"# {projet.nom}", ""]
    if (projet.objectif or "").strip():
        lignes += [f"**Objectif :** {projet.objectif.strip()}", ""]

    # ⚠️ LA CONFIDENTIALITE SE LIT SUR LE DOCUMENT, PAS SEULEMENT EN BASE.
    #
    # « Je veux garder ca pour moi » a ete dit a voix haute, et le fichier va
    # vivre sa vie : il sera copie, envoye, ouvert devant quelqu'un. La
    # propriete doit voyager AVEC lui.
    if projet.confidentialite == "personnel":
        lignes += ["> **Personnel.** Tu as demandé à garder ce projet pour toi.", ""]

    lignes += _points("Décisions", projet.decisions, avec_raison=True)
    lignes += _points("Hypothèses", projet.hypotheses)
    lignes += _taches(projet.taches)
    lignes += _points("Questions en attente", projet.questions)
    lignes += _points("Ce dont on parle", projet.entites)

    lignes += [
        "---",
        "",
        f"*Écrit par Nova le {jour}, à partir de ce qui a été dit à voix haute. "
        "Rien n'a été ajouté.*",
        "",
    ]
    return "\n".join(lignes)


# ══════════════════════════════════════════════════════════════════════════
#  METTRE A JOUR — l'action qui, elle, demande une confirmation
# ══════════════════════════════════════════════════════════════════════════


def _plat(texte: str) -> str:
    sans = "".join(
        c for c in unicodedata.normalize("NFD", texte or "")
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", sans.lower())).strip()


#: Remettre a jour, et non creer.
#:
#: ⚠️ CE MOTIF DOIT ETRE LU AVANT CELUI DE LA CREATION.
#:
#: « mets le dossier a jour » porte un verbe et le mot « dossier » : c'est
#: exactement ce que `fichiers/creer.py` cherche. Sans priorite, la mise a
#: jour serait comprise comme une creation, et Nova repondrait que le dossier
#: est deja la — poliment, sans rien faire.
_MISE_A_JOUR = re.compile(
    r"\b(?:mets? (?:le |la |ce |mon |notre )?\w* ?a jour|mets? a jour|"
    r"mettre a jour|met a jour|"
    r"actualise|actualiser|rafraichis|"
    r"reecris|reecrire|refais|regenere|"
    r"remets? (?:le |la )?\w* ?a jour)\b"
)

#: Et ce qu'on met a jour : le document du projet.
_OBJET_DU_PROJET = re.compile(r"\b(?:document|dossier|projet|fichier|note|notes)s?\b")


def demande_de_mise_a_jour(texte: str) -> bool:
    """Cette phrase demande-t-elle de reecrire le document du projet ?

    Deux signaux, comme ailleurs : le verbe seul — « actualise » — ne dit pas
    quoi, et « le document » seul n'est pas un ordre.
    """
    plat = _plat(texte)
    if not plat:
        return False
    return bool(_MISE_A_JOUR.search(plat) and _OBJET_DU_PROJET.search(plat))


def porte_la_signature(contenu: str) -> bool:
    """Ce document est-il encore celui que Nova a ecrit ?"""
    return SIGNATURE in (contenu or "")


def nom_de_la_precedente(projet: Projet) -> str:
    """Le nom de la copie gardee avant remplacement."""
    return f"{projet.nom}{SUFFIXE_PRECEDENTE}.md"


def question_de_remplacement(projet: Projet, *, repris_a_la_main: bool) -> str:
    """Ce que Nova demande AVANT de remplacer. Pas la formule generique.

    ⚠️ LA QUESTION PAR DEFAUT ETAIT IMPRONONCABLE.

    `ConfirmationRequise.question()` rend « Je m'apprete a
    mettre_a_jour_projet (projet = centrale nucleaire). Je confirme ? » —
    un nom d'outil et une liste d'arguments, lus a voix haute. Une
    confirmation qu'on ne comprend pas est une confirmation qu'on donne au
    hasard, et le portillon ne protege plus rien.

    Elle dit donc ce qui va etre remplace, et surtout SI le document a ete
    repris a la main : c'est le seul cas ou « oui » fait perdre quelque
    chose.
    """
    if repris_a_la_main:
        return (
            f"Le document de {projet.nom} a été modifié depuis que je l'ai écrit. "
            "Je le remplace quand même ? Je garde l'ancien à côté."
        )
    return f"Je réécris le document de {projet.nom} avec ce qu'on s'est dit depuis ?"
