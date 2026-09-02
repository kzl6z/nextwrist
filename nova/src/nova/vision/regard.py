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
import unicodedata
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


def sans_accents(texte: str) -> str:
    """« dernière » → « derniere ». Rien d'autre.

    ⚠️ CE MODULE COMPARAIT DES MOTS ACCENTUES A DES MOTIFS QUI NE L'ETAIENT
       PAS, ET `re.IGNORECASE` NE FAIT RIEN POUR LES ACCENTS.

    Releve en conditions reelles : « peux-tu ouvrir la derniere image que j'ai
    transferee sur mon PC » — Whisper avait parfaitement transcrit
    « dernière », et le motif cherchait « derniere ». Le repli sur un fichier
    image ne pouvait donc jamais se declencher a la voix, alors qu'il passait
    tous ses bancs : ceux-ci etaient ecrits sans accents, comme le motif.

    Le reste du projet depouille les accents avant toute comparaison
    (`voice/intentions.py`, `espaces/__init__.py`). Ce module ne le faisait
    pas, et c'est la seule raison.

    ⚠️ ON NE TOUCHE NI AUX APOSTROPHES NI AUX TIRETS.

    `intentions._normaliser` les transforme en espaces, ce qui lui convient.
    Ici les motifs contiennent « c'est quoi », « qu'est-ce », « l' » : les
    remplacer casserait la reconnaissance qu'on vient d'elargir.

    La longueur est PRESERVEE — une lettre accentuee precomposee se decompose
    en lettre + marque, et retirer la marque rend la lettre seule. Les
    positions rendues par `finditer` restent donc valables sur le texte
    d'origine, ce dont `parle_d_une_image` a besoin.
    """
    return "".join(
        c
        for c in unicodedata.normalize("NFD", texte or "")
        if unicodedata.category(c) != "Mn"
    )


#: Une reprise qui ne peut designer qu'une chose deja evoquee.
#:
#: ⚠️ ENCLITIQUE OU DEMONSTRATIF SEUL — RIEN D'AUTRE.
#:
#: « analyse-LA » et « CELLE avec la porsche » ne peuvent renvoyer qu'a
#: quelque chose de deja designe. « regarde LA voiture » non : « la » y est un
#: article. Accepter l'article ferait basculer vers l'image retenue toute
#: phrase contenant « la », pendant les dix minutes ou une image est en
#: memoire — c'est-a-dire pendant toute la conversation qui suit.
_PRONOM_IMAGE = re.compile(
    r"-(?:la|le|les)\b|\b(?:celle|celui|celles|ceux|ca|cela)\b", re.IGNORECASE
)


def _image_en_tete() -> bool:
    """Une image est-elle encore « celle dont on parle » ?"""
    from nova.vision import focus

    # Genre « image » exige : la recherche de fichiers retient dans la meme
    # memoire, et un PDF ne se decrit pas avec un modele de vision.
    return focus.derniere("image") is not None


#: Les mots qui, seuls, ne peuvent designer qu'« une image » en general.
#:
#: Assez pour reconnaitre « la photo » une fois le determinant retire, et
#: assez etroit pour ne jamais attraper un nom d'application reel : aucune ne
#: s'appelle « capture d'ecran » ou « cliche ».
#:
#: ⚠️ « PHOTOS » Y FIGURE, ET C'EST UNE APPLICATION macOS.
#:
#: C'est assume, et c'est tout l'interet : le mot seul est ambigu, le CONTEXTE
#: ne l'est pas. Hors d'une conversation sur une image, `image_en_tete_pour`
#: rend `None` et l'application gagne comme avant.
_MOT_D_IMAGE_SEUL: frozenset[str] = frozenset(
    {
        "photo", "photos", "image", "images", "capture", "captures",
        "screenshot", "cliche", "cliché", "capture d'ecran", "capture d'écran",
    }
)


#: Ce qui reste accroche a une cible et ne designe rien.
#:
#: ⚠️ CETTE SECONDE PASSE EXISTE PARCE QUE LA PREMIERE NE PEUT PAS TOUT VOIR.
#:
#: `intentions.BRUIT_CIBLE` retire UN prefixe, sur des mots entiers. Il ne
#: peut rien contre « ouvre-LA », dont la cible arrive comme « -la » : le
#: tiret colle au pronom, et il n'y a plus de mot entier a reconnaitre.
#:
#: On ne corrige pas ca en amont — le tiret est ce qui distingue l'enclitique
#: (« analyse-la ») de l'article (« analyse la situation »), et le detruire
#: casserait la reprise d'image. Il se retire ICI, ou l'on sait deja qu'on
#: cherche quelque chose a ouvrir.
#: ⚠️ « OUVRE CELUI-CI AUSSI » N'OUVRAIT RIEN.
#:
#: Releve en conditions reelles, juste apres que Nova ait nomme un second
#: fichier : « Je ne trouve pas d'application "celui-ci aussi" ». « celui »
#: etait bien reconnu, « ci » et « aussi » non — il restait donc deux mots a
#: recouper, et ils ne recoupaient rien.
#:
#: Ces mots-la n'ajoutent aucune designation : ils accompagnent celle qui est
#: deja faite. « celui-ci », « celui-la », « aussi », « encore » disent tous
#: « le meme genre de chose que ce dont on vient de parler ».
_ACCROCHES: frozenset[str] = frozenset(
    {"la", "le", "les", "l", "ce", "cet", "cette", "ces", "ca", "cela",
     "celle", "celui", "ceux", "celles", "mon", "ma", "mes", "de", "du",
     "des", "moi", "ci", "aussi", "encore", "egalement", "meme", "aut"}
)


def _depouiller(cible: str) -> str:
    """« -la » → « la », « cette photo » → « photo ». Rend `""` s'il ne reste rien."""
    mots = [m for m in re.split(r"[^\w]+", sans_accents(cible or "").lower()) if m]
    if not mots:
        return ""
    utiles = [m for m in mots if m not in _ACCROCHES]
    # Si TOUT etait une accroche, c'est que la cible etait un pronom seul —
    # « ouvre-la ». Elle ne peut alors designer que ce dont on vient de parler.
    return " ".join(utiles)


def image_en_tete_pour(cible: str):
    """L'image retenue, si « cible » ne designe rien de plus precis qu'elle.

    Rend un `Path` ou `None`. Sert a l'orchestrateur, la ou le determinant a
    deja ete retire de la cible et ou seul le contexte peut trancher.

    ⚠️ TROIS FACONS DE DESIGNER LA MEME PHOTO, ET DEUX MANQUAIENT.

    Releve en conditions reelles, juste apres que Nova ait annonce deux
    photos de casquette :

        « ouvre la premiere »
        → « "premiere" peut designer "Grapher", "Print Center" ou
           "Preview". Laquelle ? »

        « ouvre la photo ou je tiens une casquette »
        → « Je ne trouve pas d'application "Photos ou je tiens une
           casquette" sur cette machine. »

    Deux reponses exactes du point de vue du catalogue d'applications, et
    absurdes du point de vue de la conversation : Nova venait de nommer ces
    photos elle-meme.

    On accepte donc les trois formes :

        LE PRONOM      « ouvre-la »            — deja gere
        LE RANG        « ouvre la premiere »   — compris, puis JETE
        LA DEMANDE     « la photo ou je tiens une casquette »
    """
    from nova.vision import focus

    if not (cible or "").strip():
        return None
    retenue = focus.derniere("image")
    if retenue is None:
        return None

    # ── LE RANG, ET IL PASSE AVANT TOUT LE RESTE ─────────────────────────
    #
    # ⚠️ IL ETAIT DEJA COMPRIS, ET PERSONNE NE LE LISAIT.
    #
    # `rang_demande` rendait bien 1 pour « la premiere ». Mais seul le
    # resolveur de FICHIERS le consultait, et il ne regarde qu'une retenue de
    # genre « fichier » : apres une recherche d'IMAGE, la reponse etait
    # toujours `None` et la cible partait au catalogue des applications.
    #
    # Le rang est l'information la plus precise d'une phrase : il passe avant
    # le recoupement de mots, ici comme cote fichiers.
    from nova.fichiers.trouver import _au_rang, rang_demande

    if (rang := rang_demande(cible)) is not None:
        if (choisie := _au_rang(retenue.liste, rang)) is not None:
            log.info("Rang %d demande : %s", rang, choisie.name)
            return choisie
        log.info(
            "Rang %d demande, mais la liste annoncee en compte %d.",
            rang, len(retenue.liste),
        )
        # ⚠️ ON NE RABAT PAS SUR LA PLUS PROCHE.
        #
        # Meme regle que cote fichiers : « la cinquieme » quand il y en a
        # deux est une meconnaissance, pas une approximation.
        return None

    reste = _depouiller(cible)
    # Vide = la cible n'etait qu'un pronom (« ouvre-la ») : elle designe
    # forcement ce dont on vient de parler.
    if not reste or reste in _MOT_D_IMAGE_SEUL:
        return retenue.chemin

    # ── LES MOTS DE LA DEMANDE ───────────────────────────────────────────
    #
    # ⚠️ ON COMPARAIT AU NOM DU FICHIER, QUI N'EST JAMAIS CE QU'ON DIT.
    #
    # « la photo ou je tiens une casquette » n'a aucun mot commun avec
    # « IMG_8156.JPG » — et ne peut pas en avoir. Ce que la personne redit,
    # c'est SA PROPRE DEMANDE, celle qui a servi a trouver la photo.
    #
    # La retenue la garde depuis `_bloc_recherche` : c'est elle qu'on
    # recoupe, et accessoirement la description du catalogue.
    contre = " ".join(
        filter(None, (retenue.demande, retenue.description, retenue.chemin.name))
    )
    mots_dits = {
        mot
        for mot in re.findall(r"[a-z0-9]{4,}", sans_accents(reste).lower())
        if mot not in _ACCROCHES
    }
    if mots_dits and any(mot in sans_accents(contre).lower() for mot in mots_dits):
        log.info("« %s » designe l'image retenue (%s).", cible, retenue.chemin.name)
        return retenue.chemin
    return None


def _reprise_d_image(texte: str) -> bool:
    """La phrase reprend-elle une image deja evoquee, sans la nommer ?

    ⚠️ N'EST VRAIE QUE PENDANT UNE CONVERSATION SUR UNE IMAGE.

    Hors de ce cadre, « analyse-la » ne designe rien et doit suivre son cours
    normal. C'est ce qui evite qu'un pronom quelconque declenche la vision au
    milieu d'une discussion qui n'a rien a voir.
    """
    return bool(_PRONOM_IMAGE.search(sans_accents(texte))) and _image_en_tete()


def _objet_defini(plat: str) -> bool:
    """Un mot d'image y designe-t-il un EXEMPLAIRE plutot qu'une categorie ?

    « cette photo » oui, « une photo » non. Il suffit qu'UNE occurrence
    designe un fichier precis : dans « c'est quoi cette photo, c'est une photo
    de vacances ? », la premiere suffit.
    """
    generiques = {m.end() for m in _INDEFINI.finditer(plat)}
    return any(m.end() not in generiques for m in _OBJET_SEUL.finditer(plat))


#: Ce qui designe la plus recente du dossier, et non celle qu'on tient.
#:
#: ⚠️ SANS CETTE LISTE, UNE IMAGE RETENUE CAPTERAIT « LA DERNIERE IMAGE ».
#:
#: Pendant dix minutes, « decris la derniere photo que j'ai transferee »
#: renverrait a celle dont on parlait avant — exactement l'erreur qu'on est en
#: train de corriger, mais dans l'autre sens. Ces mots designent le dossier :
#: ils l'emportent sur ce qu'on tient en main.
_VERS_LA_PLUS_RECENTE = re.compile(
    r"\b(?:derniere|dernier|recente|recent|nouvelle|nouveau|nouvelles|"
    r"transferee|transfere|transferees|recue|recus|recue|recues|"
    r"importee|importees|telechargee|telechargees|arrivee|arrivees|"
    r"viens de (?:transferer|recevoir|mettre|deposer|prendre))\b",
    re.IGNORECASE,
)


def _designe_la_retenue(texte: str) -> bool:
    """La phrase renvoie-t-elle a l'image dont on vient de parler ?

    ⚠️ LE PRONOM N'EST PAS LA SEULE FACON DE REPRENDRE.

    « analyse-LA » etait couvert. « decris-moi LA PHOTO » ne l'etait pas, et
    c'est la formulation qui vient naturellement une fois l'image a l'ecran.
    Releve en conditions reelles : Nova venait de trouver et d'OUVRIR la bonne
    image, on lui dit « decris-moi la photo », et elle a decrit celle du
    dessus de la pile. La reponse etait juste — sur une autre image.

    C'est le meme defaut que « ouvre la photo » qui ouvrait l'application
    Photos : corrige a l'etage de l'OUVERTURE par `image_en_tete_pour`, jamais
    applique a celui du REGARD.

    ⚠️ CETTE FONCTION N'ELARGIT AUCUN DECLENCHEUR.

    Elle n'est consultee qu'apres `parle_d_une_image` : elle ne decide pas SI
    l'on regarde, seulement LAQUELLE on regarde. « regarde la voiture qui
    passe » n'arrive donc jamais jusqu'ici.
    """
    if not _image_en_tete():
        return False
    plat = sans_accents(texte)
    # Un pronom ne peut renvoyer qu'a du deja-designe : il gagne toujours.
    if _PRONOM_IMAGE.search(plat):
        return True
    if _VERS_LA_PLUS_RECENTE.search(plat):
        return False
    # « la photo », « cette image », « l'image » : un exemplaire precis, mais
    # rien qui le distingue de celui dont on vient de parler.
    return _objet_defini(plat)


def parle_d_une_image(texte: str) -> bool:
    """Cette phrase demande-t-elle de regarder quelque chose ?

    Un chemin d'image ecrit noir sur blanc suffit : « decris
    ~/Downloads/x.jpg » n'a pas besoin du mot « image ».
    """
    if not texte:
        return False
    # Le chemin se cherche sur le texte D'ORIGINE : un nom de fichier peut
    # porter des accents, et on le veut tel qu'il est ecrit sur le disque.
    # Les MOTS, eux, se comparent depouilles.
    if CHEMIN.search(texte):
        return True
    plat = sans_accents(texte)

    # ⚠️ « ANALYSE-LA » NE CONTIENT AUCUN MOT D'IMAGE.
    #
    # Le declencheur exige un VERBE de regard ET un OBJET visuel. C'est ce qui
    # le rend precis — et c'est ce qui laissait tomber la suite naturelle
    # d'une recherche : on vient de trouver et d'ouvrir une image, on dit
    # « analyse-la », et rien ne partait. Le pronom remplace l'objet, mais
    # seulement tant qu'une image est en tete.
    if re.search(rf"\b(?:{_VERBES})", plat, re.IGNORECASE) and _reprise_d_image(texte):
        return True

    if not DEMANDE_DE_REGARD.search(plat):
        return False

    # Reste a trancher entre « cette photo » et « une photo ».
    return _objet_defini(plat)


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
#:
#: ⚠️ L'ELISION NE MET JAMAIS D'ESPACE, ET LE MOTIF EN EXIGEAIT UN.
#:
#: `l'\s+` ne peut pas correspondre a « l'image » — la forme la plus
#: naturelle en francais, et celle que Whisper produit. Releve en conditions
#: reelles : « peux-tu ouvrir l'image … » repartait vers le catalogue des
#: applications. Les determinants elides sont donc traites a part : apres eux
#: l'espace est FACULTATIF, apres les autres il reste obligatoire — sans quoi
#: « la » collerait a n'importe quel mot commencant par « image ».
_DETERMINE = re.compile(
    rf"\b(?:l'|d')\s*(?:\w+\s+){{0,2}}(?:{_OBJETS})\b"
    rf"|\b(?:la|le|les|l|ce|cet|cette|ces|ma|mon|mes|ta|ton|tes|"
    rf"derniere|dernier)\s+(?:\w+\s+){{0,2}}(?:{_OBJETS})\b",
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
    return bool(CHEMIN.search(cible) or _DETERMINE.search(sans_accents(cible)))


#: Ce qui distingue « retrouve-moi l'image ou… » de « decris cette image ».
#:
#: ⚠️ LA DIFFERENCE N'EST PAS LE VERBE, C'EST LA DESCRIPTION DU CONTENU.
#:
#:     « decris cette image »              → regarde celle du dessus de la pile
#:     « l'image ou il y a une casquette » → cherche laquelle, parmi toutes
#:
#: Le second dit ce qu'il y a DANS l'image. C'est cette subordonnee — « ou il
#: y a », « avec », « qui montre » — qui fait basculer d'un regard vers une
#: recherche. Sans elle, « retrouve mon image » ne designe rien de precis et
#: retombe sur la plus recente, ce qui est le bon comportement.
#: ⚠️ LA CAPTURE S'ARRETE A LA VIRGULE, ET CE N'EST PAS UN DETAIL.
#:
#: Sans elle, « … ou il y a une casquette tenue dans une main, est-ce que tu
#: peux me la retrouver ? » capturait la question avec. Le score etant une
#: PROPORTION des mots cherches, chaque mot parasite le fait BAISSER :
#: « retrouver » n'apparaitra dans aucune description d'image, et la bonne
#: reponse passait sous le seuil. Plus la phrase etait polie, moins la
#: recherche marchait.
_CONTENU = re.compile(
    rf"\b(?:{_OBJETS})\b[^.?!,]*?\b(?:ou il y a|ou on voit|ou il y avait|"
    rf"avec|qui montre|qui represente|qui contient|contenant|montrant|"
    rf"montre|represente|contient|affiche|de la|du|des|de mon|de ma|de mes)"
    rf"\s+(?P<quoi>[^.?!,]{{3,120}})",
    re.IGNORECASE,
)

#: Les verbes qui demandent de CHERCHER plutot que de regarder.
_RETROUVER = re.compile(
    r"\b(?:retrouv\w*|retrouve[- ]moi|cherch\w*|trouv\w*|ou est|ou se trouve|"
    r"laquelle|quelle image|quelle photo|as[- ]tu|acces a)\b",
    re.IGNORECASE,
)


def contenu_cherche(texte: str, *, tolerant: bool = True) -> str:
    """Ce que la personne dit voir DANS l'image, ou `""`.

    Rend la partie utile a la recherche — « une casquette tenue dans une
    main » — et non la phrase entiere : « est-ce que tu peux me retrouver
    l'image » ne contient aucun mot qui designe une image en particulier, et
    les inclure ferait ressembler la question a toutes les descriptions.

    ⚠️ DEUX LECTURES, PARCE QUE LA VOIX NE FAIT PAS DE GRAMMAIRE.

    La premiere cherche une tournure propre — « ou il y a », « avec », « qui
    montre ». Elle est precise et decoupe juste.

    La seconde existe parce que la premiere a echoue sur une phrase reelle.
    Releve tel quel : « où il y a une casquette » a ete transcrit « ou je
    train casquette ». Aucun motif grammatical ne rattrapera ca — et exiger
    une grammaire correcte d'une transcription vocale, c'est ne marcher que
    dans les demonstrations.

    On prend alors TOUT ce qui suit le mot « image » ou « photo », et on
    laisse les mots vides faire le tri. « train casquette » cherchera
    « casquette » : un mot parasite coute un peu de score, une phrase non
    reconnue coute la fonctionnalite entiere.
    """
    if not texte:
        return ""
    plat = sans_accents(texte)

    if trouve := _CONTENU.search(plat):
        # On decoupe sur le texte D'ORIGINE, aux memes positions : le
        # depouillement des accents preserve les longueurs, et une
        # description accentuee doit rester lisible dans le compte rendu.
        debut, fin = trouve.span("quoi")
        return texte[debut:fin].strip(" ?.!,")

    # ⚠️ LE REPLI TOLERANT CONVIENT POUR REPONDRE, PAS POUR OUVRIR.
    #
    # Rendre une phrase ou l'on nomme le fichier qu'on a retenu est
    # rattrapable d'un mot. OUVRIR le mauvais fichier ne l'est pas de la meme
    # facon — et sur une transcription massacree, « l'image a l'eau. penge
    # sur pege » donnerait « a l'eau. penge sur pege » comme contenu cherche.
    # Le catalogue ne trouverait rien, et Nova REFUSERAIT d'ouvrir alors
    # qu'ouvrir la plus recente etait la bonne reponse.
    if not tolerant:
        return ""

    # Repli : le dernier mot d'image — ou le pronom qui en tient lieu — puis
    # tout ce qui suit.
    dernier = None
    for occurrence in _OBJET_SEUL.finditer(plat):
        dernier = occurrence
    if dernier is None and _reprise_d_image(texte):
        for occurrence in _PRONOM_IMAGE.finditer(plat):
            dernier = occurrence
    if dernier is None:
        return ""
    suite = texte[dernier.end() :].strip(" ?.!,")
    # Sans mot porteur derriere, la phrase ne designe rien de precis —
    # « retrouve mon image » doit rester une demande de regard, pas de
    # recherche.
    from nova.vision.catalogue import mots

    return suite if mots(suite) else ""


def demande_de_retrouver(texte: str) -> bool:
    """Cette phrase demande-t-elle de CHERCHER une image parmi d'autres ?

    Il faut un mot d'image, quelque chose a chercher, ET — quand la tournure
    n'est pas explicite — un verbe qui demande de retrouver. Sans ce dernier,
    « decris cette image en detail » partirait chercher « en detail ».
    """
    if not texte:
        return False
    plat = sans_accents(texte)
    # ⚠️ « ET CELLE AVEC LA PORSCHE » NE CONTIENT AUCUN MOT D'IMAGE.
    #
    # C'est pourtant une recherche, et une formulation parfaitement
    # naturelle : on vient de parler d'images, le pronom suffit. Il ne tient
    # lieu d'objet que pendant cette conversation-la.
    if not _OBJET_SEUL.search(plat) and not _reprise_d_image(texte):
        return False
    if not contenu_cherche(texte):
        return False
    return bool(_CONTENU.search(plat) or _RETROUVER.search(plat) or _reprise_d_image(texte))



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


def retrouver(quoi: str, limite: int = 3):
    """Les images du catalogue qui correspondent. Ne leve jamais.

    Rend une liste de couples `(Entree, score)`, vide si rien ne depasse le
    seuil de pertinence.
    """
    from nova.vision import catalogue as cat

    try:
        catalogue = cat.Catalogue(cat.fichier_par_defaut())
    except Exception as erreur:  # noqa: BLE001
        log.warning("Catalogue d'images illisible : %s", erreur)
        return []
    return [
        (entree, score)
        for entree, score in catalogue.chercher(quoi, limite)
        if score >= cat.SEUIL_PERTINENCE
    ]


#: Ecart minimal avec le deuxieme candidat pour ouvrir sans demander.
#:
#: ⚠️ MEME RAISON QUE POUR LES APPLICATIONS : UNE RESSEMBLANCE PARFAITE AVEC
#:    DEUX FICHIERS N'EN DESIGNE AUCUN.
#:
#: `_resoudre_application` a exactement ce garde-fou, pour exactement ce
#: probleme. Deux captures d'ecran qui se ressemblent donnent deux scores
#: proches ; en ouvrir une au hasard serait une reussite apparente, plus
#: difficile a deboguer qu'un echec.
MARGE_OUVERTURE = 0.20


def _ouvrir_si_evident(trouvees) -> bool:
    """Ouvre l'image quand une seule se detache. Rend `True` si c'est fait.

    ⚠️ OUVRIR EST UNE ACTION, ET ELLE PASSE PAR LE PORTILLON.

    `executer_outil` verifie le bareme de risque — REVERSIBLE ici : une
    fenetre s'ouvre, on la ferme, il ne reste rien. C'est le meme niveau
    qu'« ouvre Discord », qui s'execute deja sans demander. Court-circuiter
    le portillon parce que « ce n'est qu'une ouverture » rendrait le bareme
    decoratif.

    Ne leve jamais : une image qu'on n'a pas su ouvrir ne doit pas empecher
    Nova de DIRE qu'elle l'a trouvee.
    """
    meilleure, score = trouvees[0]
    # ⚠️ DEUX FICHIERS IDENTIQUES NE SONT PAS UNE AMBIGUITE.
    #
    # Releve sur la machine : `alo.JPG` et `IMG_8156.JPG` sont la MEME photo,
    # donc la meme description, donc deux scores a 100 %. La marge n'etait
    # jamais atteinte et Nova n'ouvrait rien — alors que n'importe laquelle
    # des deux etait la bonne reponse.
    #
    # On ecarte donc les doublons avant de mesurer l'ecart : ce qui compte
    # est le premier candidat qui dit AUTRE CHOSE.
    distincts = [
        (entree, valeur)
        for entree, valeur in trouvees
        if entree.description != meilleure.description
    ]
    second = distincts[0][1] if distincts else 0.0
    if score - second < MARGE_OUVERTURE:
        log.info(
            "Ouverture non declenchee : %s a %.0f %% contre %.0f %% pour le suivant.",
            meilleure.nom, score * 100, second * 100,
        )
        return False

    try:
        from nova.outils import executer_outil

        executer_outil("ouvrir_image", chemin=meilleure.chemin)
    except Exception as erreur:  # noqa: BLE001
        log.warning("Image trouvee mais non ouverte : %s", erreur)
        return False
    return True


def _bloc_recherche(texte: str) -> str:
    """Le bloc de prompt pour « retrouve-moi l'image ou il y a… ».

    ⚠️ CE BLOC NE REGARDE AUCUNE IMAGE.

    Il lit le catalogue — des descriptions obtenues il y a des heures, en
    tache de fond. Cout : une comparaison de texte. C'est toute la raison
    d'etre du catalogue : regarder quarante images a la demande prendrait
    deux minutes, et personne n'attend deux minutes.
    """
    from nova.vision import catalogue as cat

    quoi = contenu_cherche(texte)
    with chrono.mesurer("vision — recherche au catalogue"):
        trouvees = retrouver(quoi)

    if not trouvees:
        connues = len(cat.Catalogue(cat.fichier_par_defaut()))
        # ⚠️ « RIEN TROUVE » ET « RIEN INDEXE » SONT DEUX PANNES OPPOSEES.
        #
        # La premiere se corrige en decrivant autrement, la seconde en
        # attendant que l'indexation ait tourne. Les confondre laisserait
        # quelqu'un reformuler dix fois une question sur un catalogue vide.
        etat = (
            f"Nova a deja regarde {connues} image(s) et aucune ne correspond."
            if connues
            else "Nova n'a encore regarde aucune image : l'indexation n'a pas "
            "encore tourne. Elle travaille quand la machine est au repos."
        )
        return (
            "## Recherche d'image\n\n"
            f"Recherche demandee : « {quoi} »\n"
            f"Resultat : AUCUNE image ne correspond. {etat}\n\n"
            "Reponds EXACTEMENT ceci, et rien d'autre :\n\n"
            f"« Je n'ai trouve aucune image correspondant a {quoi}. {etat} »"
        )

    meilleure, meilleur_score = trouvees[0]
    log.info(
        "Recherche « %s » : %d resultat(s), meilleur %s.",
        quoi, len(trouvees), meilleure.nom,
    )

    # ⚠️ ON RETIENT TOUJOURS, ON N'OUVRE QUE SI C'EST NET.
    #
    # Retenir permet a « analyse-la » de designer CETTE image et non la plus
    # recente du dossier. Ouvrir est une action : elle ne se declenche que
    # lorsqu'une image se detache franchement, sans quoi Nova ouvrirait un
    # fichier au hasard parmi trois candidats equivalents.
    from nova.vision import focus

    focus.retenir(
        meilleure.chemin,
        description=meilleure.description,
        origine="recherche",
        # ⚠️ DANS L'ORDRE EXACT OU ELLES ONT ETE CLASSEES.
        #
        # C'est ce qui donne un sens a « ouvre la deuxieme » et a « c'est quoi
        # le nom de la troisieme ». Retenir un autre ordre que celui du
        # classement ouvrirait une image que personne n'a designee, en ayant
        # l'air d'obeir.
        liste=tuple(entree.chemin for entree, _ in trouvees),
        # Ce que la personne redira pour la designer — jamais le nom du
        # fichier, qu'elle n'a pas entendu et ne prononcera pas.
        demande=quoi,
    )
    ouverte = _ouvrir_si_evident(trouvees)

    # ⚠️ NOVA PROPOSE, ET « OUI » SUFFIT ENSUITE.
    #
    # On ne note la proposition QUE si rien n'a ete ouvert : proposer
    # d'ouvrir ce qui est deja a l'ecran ferait repondre « oui » a une
    # question sans objet.
    if ouverte is None:
        from nova.voice import session

        session.proposer(
            "ouvrir_image",
            {"chemin": str(meilleure.chemin)},
            # Les mots de la demande, pas le nom du fichier : « ta casquette
            # blanche » se dit, « IMG_8156.JPG » ne se prononce pas.
            comme=quoi,
        )

    # ══════════════════════════════════════════════════════════════════════
    #  ⚠️ NI LE NOM NI LA DESCRIPTION NE SONT DANS CE BLOC.
    #
    #  La version precedente donnait les deux au modele et lui demandait
    #  explicitement de « nommer » l'image et de « resumer la description ».
    #  Il obeissait. Releve en conditions reelles :
    #
    #      « L'image IMG_8156.JPG montre une main tenant une casquette
    #        blanche avec l'inscription "alo". »
    #
    #  Demande textuelle : « quand elle la trouve je veux juste que ca dise
    #  photo trouvee, voulez-vous que je l'ouvre ».
    #
    #  Un nom de fichier ne se prononce pas, et redecrire une photo a
    #  quelqu'un qui l'a prise ne lui apprend rien — il l'a decrite lui-meme
    #  pour la retrouver.
    #
    #  ⚠️ ET ON NE LUI DEMANDE PAS DE SE TAIRE : ON NE LUI DIT RIEN.
    #
    #  Meme correction que pour les documents, pour la meme raison : un
    #  modele de trois milliards de parametres CONTINUE ce qu'il vient de
    #  lire. La seule consigne qu'il ne peut pas enfreindre est celle qui
    #  porte sur une donnee qu'il n'a pas.
    #
    #  Le nom reste accessible — `focus` retient la liste — mais il faut le
    #  DEMANDER : « c'est quoi le nom de la photo ? ».
    # ══════════════════════════════════════════════════════════════════════
    combien = (
        f"dis que tu as trouve {len(trouvees)} photos qui correspondent a "
        f"« {quoi} »."
        if len(trouvees) > 1
        else f"dis que tu as trouve la photo : « {quoi} »."
    )
    suite = (
        "dis que tu viens de l'ouvrir a l'ecran."
        if ouverte
        else "demande simplement : « je te l'ouvre ? »"
        if len(trouvees) == 1
        else "demande laquelle ouvrir, par son rang — « la premiere ou la deuxieme ? »"
    )
    return (
        "## Recherche d'image\n\n"
        "Ta reponse, en francais, UNE SEULE PHRASE COURTE :\n"
        f"- {combien}\n"
        f"- {suite}\n"
        "- tu n'as ni les noms, ni ce qu'on y voit, ni les dimensions, ni les "
        "dates : n'en invente aucun."
    )


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
    # ⚠️ LA RECHERCHE PASSE AVANT LE REGARD, ET DANS CET ORDRE SEULEMENT.
    #
    # « retrouve-moi l'image ou il y a une casquette » parle bien d'une image,
    # donc `parle_d_une_image` dit oui — et regarder la plus recente serait
    # une reponse a une autre question. Une phrase qui decrit le CONTENU
    # cherche une image precise ; sans description de contenu, on regarde
    # celle du dessus de la pile.
    #
    # La recherche ne charge aucun modele : elle lit le catalogue. La placer
    # en premier evite donc aussi de payer 7 s de vision pour rien.
    if demande_de_retrouver(texte):
        return _bloc_recherche(texte)

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

    from nova.vision import focus

    dossiers = dossiers_surveilles()
    try:
        with chrono.mesurer("vision — choix de l'image"):
            if cite := CHEMIN.search(texte):
                cible, provenance = resoudre(cite.group(1), dossiers), "nommee"
            # ⚠️ « ANALYSE-LA » ET « DECRIS-MOI LA PHOTO » DESIGNENT CE DONT ON
            #    VIENT DE PARLER.
            #
            # Sans cette ligne, Nova retombait sur la plus recente du dossier
            # — c'est-a-dire presque toujours une AUTRE image que celle qu'elle
            # venait de trouver et d'ouvrir. La reponse etait alors juste sur
            # une image que personne n'avait demandee : une erreur qui a l'air
            # de marcher, donc la plus couteuse a diagnostiquer.
            elif (
                _designe_la_retenue(texte)
                and (retenue := focus.derniere("image")) is not None
            ):
                cible, provenance = retenue.chemin, "retenue"
            else:
                cible, provenance = la_plus_recente(dossiers), "devinee"
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
    explication = {
        "nommee": "Elle a ete nommee explicitement dans la demande.",
        "retenue": "C'est celle dont vous veniez de parler.",
        "devinee": (
            f"Nova ne l'a pas choisie au hasard : c'est la plus recente de "
            f"ses dossiers surveilles, deposee {quand}."
        ),
    }[provenance]
    focus.retenir(cible, description=observation.description, origine="regard")
    log.info("Regard : %s (%s)", cible.name, provenance)

    return (
        "## Ce que Nova voit\n\n"
        f"Fichier : {cible.name}"
        + (f" ({quand})" if quand else "")
        + f"\n{explication}\n\n"
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
