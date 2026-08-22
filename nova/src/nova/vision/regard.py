"""Regarder une image PENDANT une conversation, sans passer par un plan.

CE QUI MANQUAIT, ET POURQUOI CE FICHIER EXISTE

L'agent de vision, les outils, la circulation des resultats : tout cela
fonctionne — par `/v1/executer`. Or personne ne parle a Nova en `curl`.

    « Nova, analyse l'image que je viens de recevoir. »

Cette phrase part sur le chemin de CONVERSATION, qui ne parcourt aucun plan :
il assemble un prompt, appelle le modele, et rend la reponse. La vision n'y
etait branchee nulle part. Nova repondait donc « je ne peux pas voir les
images » — sincerement, et a cote de la verite, puisqu'elle savait le faire
depuis un autre point d'entree.

⚠️ ON NE FAIT PAS PASSER LA CONVERSATION PAR LE PLANIFICATEUR.

C'etait l'autre solution, et elle aurait coute le travail de cette session :
le chemin conversationnel a ete ramene de 8-11 s a 1,8-3,1 s avant le premier
mot. Le faire passer par plan + gestionnaire + executeur pour les 99 % de
demandes qui ne parlent d'aucune image aurait rendu tout le monde lent pour
servir un cas rare. C'est l'echange que ce projet a deja paye trois fois.

LA FORME RETENUE : UN BLOC DE PROMPT, COMME LES DOCUMENTS

`build_system_prompt` assemble deja des blocs — identite, memoire, instant
present, extraits de documents. L'observation d'une image en devient un de
plus. Consequences, et elles sont toutes souhaitables :

    la reponse est en FRANCAIS, meme si le modele de vision parle anglais
    elle est dans la VOIX de Nova, pas dans celle du modele de vision
    elle passe par le flux normal, donc par la synthese vocale
    elle est melangee a la memoire et aux documents, donc situee

⚠️ LE DECLENCHEMENT EST DETERMINISTE, ET GRATUIT QUAND IL N'A PAS LIEU.

Une detection par modele coûterait une seconde a CHAQUE question pour
decider si elle parle d'une image. Ici, une expression reguliere sur des mots
declencheurs : zero milliseconde quand la reponse est non, ce qui est le cas
de l'ecrasante majorite des questions.
"""

from __future__ import annotations

import re
from pathlib import Path

from nova.core import chrono
from nova.logging_setup import get_logger

log = get_logger(__name__)

#: Ce qu'on cherche : un VERBE de regard, et un OBJET qui soit une image.
#:
#: ⚠️ LES DEUX SONT EXIGES, ET C'EST LA TOUTE LA PRECISION DU FILTRE.
#:
#: « analyse » seul attraperait « analyse ce texte » ; « photo » seul
#: attraperait « raconte-moi l'histoire de la photographie ». Exiger les deux
#: dans la meme phrase ecarte les deux cas sans liste d'exceptions.
_VERBES = (
    r"analys\w*|decri\w*|décri\w*|regard\w*|observ\w*|examin\w*|"
    r"vois|voir|montre\w*|lis|lire|reconnais\w*|identifi\w*|"
    # Les tournures interrogatives ordinaires. Elles manquaient, et c'est
    # exactement ce qu'on dit dans la vraie vie : personne ne formule
    # « decris-moi cette image » quand il peut dire « c'est quoi cette
    # photo ». Un declencheur qui n'attrape que la formulation soignee
    # n'attrape que les demonstrations.
    r"c'est quoi|c est quoi|qu'est[- ]ce|qu est[- ]ce|"
    r"ce qu'il y a|ce qu il y a|qu'y a[- ]t[- ]il|que vois[- ]tu|"
    r"dis[- ]moi ce qu|tu peux me dire"
)
_OBJETS = (
    r"image|images|photo|photos|capture|captures|screenshot|"
    r"copie d'ecran|copie d'écran|dessin|schema|schéma|illustration|"
    r"visuel|scan|cliche|cliché"
)

DEMANDE_DE_REGARD = re.compile(
    rf"(?=.*\b(?:{_VERBES}))(?=.*\b(?:{_OBJETS})\b)", re.IGNORECASE
)

#: Un objet visuel precede d'un article INDEFINI.
#:
#: ⚠️ C'EST CE QUI SEPARE UNE QUESTION D'UNE DEMANDE DE REGARD.
#:
#:     « qu'est-ce qu'UNE photo argentique »  → une question de culture
#:     « c'est quoi CETTE photo »             → regarde-la
#:
#: Sans cette distinction, elargir les verbes aux tournures interrogatives
#: faisait charger un modele de 2 Go pour repondre a « qu'est-ce qu'une
#: image vectorielle ». L'article porte toute l'information : indefini, on
#: parle de la categorie ; defini ou demonstratif, on parle d'un fichier.
_INDEFINI = re.compile(
    rf"\b(?:un|une|des|d'|de)\s+(?:{_OBJETS})\b", re.IGNORECASE
)
_OBJET_SEUL = re.compile(rf"\b(?:{_OBJETS})\b", re.IGNORECASE)

#: Un chemin d'image ecrit dans la phrase l'emporte sur toute heuristique.
CHEMIN = re.compile(
    r"(?<![\w/.-])((?:~|\.{1,2})?[\w./\\-]*\.(?:jpe?g|png|webp|gif|bmp|heic|heif|tiff?))",
    re.IGNORECASE,
)


def parle_d_une_image(texte: str) -> bool:
    """Cette phrase demande-t-elle de regarder quelque chose ?

    Un chemin d'image ecrit noir sur blanc suffit : « decris
    ~/Downloads/x.jpg » n'a pas besoin du mot « image ».
    """
    if not texte:
        return False
    if CHEMIN.search(texte):
        return True
    if not DEMANDE_DE_REGARD.search(texte):
        return False

    # Reste a trancher entre « cette photo » et « une photo ». Il suffit
    # qu'UNE occurrence designe un fichier precis : dans « c'est quoi cette
    # photo, c'est une photo de vacances ? », la premiere suffit.
    generiques = {m.end() for m in _INDEFINI.finditer(texte)}
    return any(m.end() not in generiques for m in _OBJET_SEUL.finditer(texte))


#: Un objet visuel precede d'un DETERMINANT qui designe un exemplaire precis.
#:
#: ⚠️ CE MOTIF EXISTE POUR NE PAS CONFONDRE UNE IMAGE AVEC UNE APPLICATION.
#:
#: « ouvre Photos » vise l'application Photos de macOS. « ouvre la derniere
#: photo » vise un fichier. Le mot est le meme ; c'est le DETERMINANT qui
#: tranche — et l'absence de determinant est la marque d'un nom propre.
#:
#:     Photos, Photo Booth, Aperçu   ← des applications, aucun determinant
#:     la photo, cette image, mes captures, la derniere photo
#:
#: Les adjectifs intercales sont admis (« la DERNIERE photo »), au plus deux :
#: au-dela on ne designe plus, on decrit.
_DETERMINE = re.compile(
    rf"\b(?:la|le|les|l'|l|ce|cet|cette|ces|ma|mon|mes|derniere|dernier)\s+"
    rf"(?:\w+\s+){{0,2}}(?:{_OBJETS})\b",
    re.IGNORECASE,
)


def designe_une_image(cible: str) -> bool:
    """Cette cible designe-t-elle un FICHIER image plutot qu'une application ?

    ⚠️ SERT DE REPLI, JAMAIS DE PRIORITE.

    L'orchestrateur consulte d'abord le catalogue des applications reelles :
    une application qui s'appelle vraiment « Photos » gagne toujours. Ce n'est
    que lorsque rien d'installe ne correspond qu'on se demande si la personne
    parlait d'un fichier.

    L'ordre importe : pre-empter aurait casse « ouvre Photos », qui marche
    depuis longtemps. Un repli n'enleve rien a ce qui fonctionnait deja — il
    remplace seulement un echec par une reussite.
    """
    if not cible:
        return False
    return bool(CHEMIN.search(cible) or _DETERMINE.search(cible))


def _situer(cible: Path) -> str:
    """« il y a 4 minutes », « il y a 3 jours » — ou rien si c'est illisible."""
    from nova.vision.images import age_en_heures

    heures = age_en_heures(cible)
    if heures < 0:
        return ""
    if heures < 1 / 60:
        return "a l'instant"

    def dire(nombre: int, unite: str) -> str:
        # Nova relit ce bloc a voix haute par la bouche du modele. « il y a 1
        # minutes » se remarque a l'oreille bien plus qu'a l'ecrit.
        return f"il y a {nombre} {unite}{'s' if nombre > 1 else ''}"

    if heures < 1:
        return dire(max(int(heures * 60), 1), "minute")
    if heures < 48:
        return dire(int(heures), "heure")
    return dire(int(heures / 24), "jour")


def bloc(texte: str) -> str:
    """L'observation a injecter dans le prompt, ou `""` s'il n'y a rien a voir.

    ⚠️ CETTE FONCTION NE LEVE JAMAIS.

    Elle est appelee dans l'assemblage du prompt, sur le chemin de toutes les
    reponses. Une vision en panne — modele absent, image illisible, dossier
    vide — doit degrader la reponse, jamais l'empecher. C'est la meme regle
    que la recherche documentaire et la memoire : chaque capacite est
    facultative, et c'est ce qui rend le systeme robuste quand on en ajoute
    dix autres.

    ⚠️ ET ELLE NE MENT PAS NON PLUS.

    Quand la vision echoue, elle rend un bloc qui DIT qu'elle a echoue et
    pourquoi. Rendre `""` laisserait le modele repondre « je ne vois pas
    d'image » de lui-meme — une phrase plausible, jamais la bonne raison, et
    impossible a deboguer.
    """
    if not parle_d_une_image(texte):
        return ""

    from nova.vision.images import (
        ImageIllisible,
        ImageIntrouvable,
        dossiers_surveilles,
        la_plus_recente,
        resoudre,
    )
    from nova.vision.moteur import MoteurOllama, disponible

    utilisable, raison = disponible()
    if not utilisable:
        return _empechement(raison)

    dossiers = dossiers_surveilles()
    try:
        with chrono.mesurer("vision — choix de l'image"):
            if cite := CHEMIN.search(texte):
                cible, devinee = resoudre(cite.group(1), dossiers), False
            else:
                cible, devinee = la_plus_recente(dossiers), True
    except (ImageIntrouvable, ImageIllisible) as absence:
        return _empechement(str(absence))

    try:
        with chrono.mesurer("vision — observation"):
            observation = MoteurOllama(dossiers).decrire(cible)
    # On rattrape TOUT : le moteur parle a Ollama par le reseau, et une
    # capacite facultative n'a pas le droit de faire tomber une reponse.
    except Exception as erreur:  # noqa: BLE001
        log.warning("Vision indisponible pendant la conversation : %s", erreur)
        return _empechement(_humain(erreur))

    quand = _situer(cible)
    provenance = (
        f"Nova ne l'a pas choisie au hasard : c'est la plus recente de ses "
        f"dossiers surveilles, deposee {quand}."
        if devinee
        else "Elle a ete nommee explicitement dans la demande."
    )
    log.info("Regard : %s%s", cible.name, " (la plus recente)" if devinee else "")

    return (
        "## Ce que Nova voit\n\n"
        f"Fichier : {cible.name}"
        + (f" ({quand})" if quand else "")
        + f"\n{provenance}\n\n"
        "Observation du modele de vision — c'est la SEULE chose qui a ete "
        "vue :\n"
        f"<<< {observation.description} >>>\n\n"
        "Ta reponse : traduis et reformule ce qui est entre <<< >>> en "
        "francais, en une ou deux phrases, en nommant le fichier.\n\n"
        # ⚠️ ON NOMME LES INVENTIONS OBSERVEES, PAS « N'INVENTE RIEN ».
        #
        # Premiere version : « n'ajoute rien que l'observation ne dise ».
        # Releve sur la machine — la vision avait bien tourne, et nova-leger
        # a repondu « une capture d'ecran de 1920x1080 pixels ». moondream
        # n'enonce jamais de dimensions : le chiffre etait pur remplissage,
        # greffe sur une observation par ailleurs exacte.
        #
        # Une interdiction ABSTRAITE laisse un petit modele juger lui-meme ce
        # qui compte comme un ajout. Enumerer les categories qu'il invente
        # reellement — taille, poids, format, dossier, date — lui donne une
        # liste a reconnaitre, ce qu'il sait faire.
        "Tu n'as pas vu l'image toi-meme. Les dimensions en pixels, le poids, "
        "le format, le dossier, la date : rien de tout cela ne figure entre "
        "<<< >>>, donc rien de tout cela ne doit figurer dans ta reponse."
    )


def _humain(erreur: Exception) -> str:
    """Une raison DISABLE a voix haute, pas un message de pile.

    ⚠️ NOVA LIT CE TEXTE A VOIX HAUTE.

    « argument should be a str or an os.PathLike object where __fspath__
    returns a str, not 'tuple' » est le message exact d'un vrai defaut — et il
    n'a aucun sens dit dans un salon. Le detail technique reste dans le
    journal, ou il sert ; l'utilisateur entend ce qui le concerne.
    """
    from nova.vision.images import ImageIllisible, ImageIntrouvable
    from nova.vision.moteur import VisionIndisponible

    if isinstance(erreur, (ImageIntrouvable, ImageIllisible, VisionIndisponible)):
        return str(erreur)
    return (
        "une erreur technique m'en a empechee — le detail est dans le journal "
        "de Nova"
    )


def _empechement(raison: str) -> str:
    """Un bloc qui dit ce qui a empeche de voir, plutot que de se taire.

    ⚠️ IL DICTE LA PHRASE. IL NE DEMANDE PAS DE NE PAS MENTIR.

    Premiere version : « n'invente aucune description ». Releve en conditions
    reelles — la vision echouait, ce bloc partait dans le prompt, et
    nova-leger repondait « La photo a l'eau sur ton bureau est un fichier
    JPEG de 1920x1080 pixels, stocke dans le dossier Photos, avec un format
    de compression JPEG de qualite 90 % ». Tout etait invente.

    Une consigne NEGATIVE demande a un modele de deux milliards de parametres
    de reconnaitre ce qu'il ne doit pas faire, au milieu d'un prompt de 3500
    caracteres. Une consigne POSITIVE lui donne la phrase a produire — c'est
    une tache de copie, et une copie ne s'hallucine pas.

    La consigne vient AVANT la raison, pas apres : ce qui est lu en dernier
    dans un bloc a moins de poids que ce qui l'ouvre.
    """
    return (
        "## Ce que Nova voit\n\n"
        "RIEN. Aucune image n'a ete regardee. Toute description serait "
        "inventee.\n\n"
        "Reponds EXACTEMENT ceci, et rien d'autre :\n\n"
        f"« Je n'ai pas pu regarder l'image : {raison} »"
    )
