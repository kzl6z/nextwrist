"""Reconnaissance d'intention : ce que la personne VEUT, pas ce qu'elle a dit.

LE PRINCIPE

Quatre phrases, une seule intention :

    « Ouvre Discord »
    « Lance Discord »
    « Tu pourrais ouvrir Discord ? »
    « Est-ce que tu peux ouvrir Discord ? »

        -> ouvrir_application(cible="Discord")

La methode tient en deux temps, et c'est ce qui la rend robuste sans etre
fragile :

  1. DEPOLITESSER — retirer l'enrobage. « Est-ce que tu peux », « tu
     pourrais », « s'il te plait » ne portent aucune information sur
     l'intention. Les enlever ramene les quatre phrases a deux.
  2. RECONNAITRE — un verbe declencheur, puis ce qui suit est la cible.

Enumerer les formulations completes aurait demande des centaines d'entrees et
en aurait raté autant. Enumerer les VERBES et les tournures de politesse
demande vingt lignes et couvre tout le reste.

POURQUOI CE N'EST PAS UN MODELE QUI FAIT CA

Un modele local mettrait deux secondes et se tromperait parfois. Ici c'est
zero milliseconde, reproductible, et testable. Le modele reste pour ce qui
demande du jugement — pas pour reconnaitre « ouvre ».

CE QUI ARRIVE ENSUITE, ET QUI N'EST PAS ICI

Une intention reconnue n'est PAS une action executee. `ouvrir_application`
dit ce qui est voulu ; c'est au Tool Manager de decider s'il sait le faire, et
a la politique d'autorisation de decider s'il en a le droit. Separer les deux
est ce qui permettra d'ajouter des actions sans jamais toucher ce fichier.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from nova.voice import phonetique

#: Enrobage de politesse et de tournure. Retire avant toute reconnaissance.
#: L'ordre compte : les plus longues d'abord, sinon « tu peux » consommerait
#: le debut de « est-ce que tu peux ».
POLITESSES: tuple[str, ...] = (
    "est ce que tu pourrais", "est-ce que tu pourrais",
    "est ce que tu peux", "est-ce que tu peux",
    "est ce que tu veux bien", "serait il possible de", "serais tu capable de",
    "j aimerais que tu", "je voudrais que tu", "je veux que tu", "il faudrait que tu",
    "tu pourrais", "tu peux", "peux tu", "pourrais tu", "voudrais tu",
    "s il te plait", "s il vous plait", "stp", "merci de",
    "j aimerais", "je voudrais", "je veux",
    "vas y", "allez", "dis moi",
)

#: Determinants et prepositions a retirer en tete de cible.
#: « ouvre l'application Chrome » -> cible « Chrome ».
BRUIT_CIBLE: tuple[str, ...] = (
    "l application", "l appli", "le logiciel", "le programme", "le site",
    "la page", "le fichier", "le dossier", "moi", "le", "la", "les", "l", "un", "une", "du", "de",
)


@dataclass(frozen=True)
class Intention:
    """Ce que Nova a compris de la demande.

    `confiance` n'est pas cosmetique : elle decide si Nova agit, demande
    confirmation, ou laisse passer au modele. Une intention a 0,55 ne doit
    jamais declencher l'extinction d'un ordinateur.
    """

    nom: str
    cible: str = ""
    confiance: float = 0.0
    #: Le fragment qui a declenche la reconnaissance. Pour le journal et pour
    #: pouvoir expliquer une reconnaissance surprenante.
    declencheur: str = ""
    arguments: dict[str, str] = field(default_factory=dict)

    @property
    def reconnue(self) -> bool:
        return self.nom != "aucune"


AUCUNE = Intention(nom="aucune")


#: Les intentions, leurs verbes declencheurs, et si elles attendent une cible.
#:
#: Ajouter une intention = ajouter une ligne. C'est le critere qui a decide
#: de cette forme plutot que d'une fonction par intention.
DECLENCHEURS: tuple[tuple[str, tuple[str, ...], bool], ...] = (
    # (nom, verbes ou expressions, exige une cible)
    ("ouvrir_application", ("ouvre", "ouvrir", "lance", "lancer", "demarre", "demarrer",
                            "execute", "executer", "start"), True),
    ("fermer_application", ("ferme", "fermer", "quitte", "quitter", "arrete", "arreter",
                            "termine", "kill"), True),
    ("arret_pc", ("eteins", "eteindre", "arrete l ordinateur", "arrete le pc",
                  "eteins le pc", "eteins l ordinateur", "shutdown"), False),
    ("redemarrer_pc", ("redemarre", "redemarrer", "reboot"), False),
    ("meteo", ("quel temps", "la meteo", "il va pleuvoir", "il fera",
               "temperature", "va t il pleuvoir"), False),
    ("heure", ("quelle heure", "il est quelle heure", "l heure"), False),
    ("date", ("quel jour", "quelle date", "on est quel", "la date"), False),
    ("volume_haut", ("monte le son", "augmente le volume", "monte le volume", "plus fort"), False),
    ("volume_bas", ("baisse le son", "baisse le volume", "diminue le volume", "moins fort"), False),
    # ⚠️ NI MONTER NI BAISSER : REGLER.
    #
    # Releve en conditions reelles : « Nova, mets le son à 30 % » — ignoree.
    # La table ne connaissait que deux directions, et cette phrase n'en donne
    # aucune : elle donne une DESTINATION. C'est d'ailleurs la formulation la
    # plus naturelle quand on sait ou l'on veut aller.
    #
    # La ranger sous « monte » aurait marche tant qu'un pourcentage suit, et
    # aurait monte le son sur un « mets le son » seul — ce qui ne veut pas
    # dire ca.
    ("volume_absolu", ("mets le son", "met le son", "mets le volume",
                       "met le volume", "regle le son", "regle le volume"), False),
    # ⚠️ DEUX SILENCES QUI N'ONT RIEN A VOIR, ET QUI ETAIENT CONFONDUS
    #
    # « coupe le son » parle du HAUT-PARLEUR. « tais-toi » parle de NOVA.
    # Les reunir sous une seule intention n'avait aucune consequence tant
    # qu'aucun outil n'y repondait ; brancher la sourdine systeme aurait
    # rendu le Mac muet chaque fois qu'on demande a Nova de se taire.
    #
    # Meme lecon que « arrête l'ordinateur » : le defaut n'est pas cree par
    # l'outil, il l'attend.
    ("silence", ("coupe le son", "coupe le volume", "mets en sourdine", "sourdine"), False),
    ("stop_parole", ("tais toi", "arrete de parler", "chut", "silence", "stop"), False),
    ("recherche_web", ("cherche", "chercher", "recherche sur", "google", "trouve moi"), True),
    ("memoire", ("que sais tu de moi", "retiens", "souviens toi", "rappelle toi",
                 "note que", "mes projets"), False),
)


def _normaliser(texte: str) -> str:
    """Minuscules, sans accents, apostrophes et tirets devenus espaces.

    Les apostrophes deviennent des espaces a dessein : « s'il te plait » et
    « s il te plait » doivent se comparer pareil, et Whisper produit les deux.
    """
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )
    reduit = re.sub(r"[''`\-_]", " ", sans_accents.lower())
    return re.sub(r"[^a-z0-9 ]+", " ", reduit)


def depolitesser(texte: str) -> str:
    """Retire l'enrobage de politesse et de tournure.

    C'est l'etape qui fait que quatre formulations donnent une intention. On
    boucle : « est-ce que tu peux s'il te plait ouvrir » en contient deux.
    """
    reduit = re.sub(r"\s+", " ", _normaliser(texte)).strip()
    change = True
    while change:
        change = False
        for tournure in POLITESSES:
            for motif in (rf"^{re.escape(tournure)}\b", rf"\b{re.escape(tournure)}$"):
                nouveau = re.sub(motif, " ", reduit).strip()
                if nouveau != reduit:
                    reduit, change = re.sub(r"\s+", " ", nouveau).strip(), True
    return reduit


def _aligner(mots: list[str]) -> tuple[list[str], list[int]]:
    """Les jetons normalises, et le mot original dont chacun provient.

    LE PIEGE QUE CETTE FONCTION EXISTE POUR EVITER

    « s'il » est UN mot pour l'utilisateur et DEUX apres normalisation
    (« s il ») ; « l'application » de meme. Compter les mots du cote normalise
    pour en retirer du cote original coupe donc au mauvais endroit — dans un
    sens on laisse « Discord s'il te », dans l'autre on ne reconnait jamais
    « l'application » parce qu'on la compare a « l application ».

    Cette correspondance jeton -> mot d'origine est la reponse aux deux cas.
    """
    jetons: list[str] = []
    portee: list[int] = []   # index du mot original pour chaque jeton
    for index, mot in enumerate(mots):
        for jeton in _normaliser(mot).split():
            jetons.append(jeton)
            portee.append(index)
    return jetons, portee


def _retirer_politesse_finale(texte: str) -> str:
    """Retire la politesse en fin de phrase, sur le texte ORIGINAL."""
    mots = texte.split()
    if not mots:
        return texte

    jetons, portee = _aligner(mots)
    for tournure in POLITESSES:
        attendus = tournure.split()
        if len(attendus) > len(jetons):
            continue
        if jetons[-len(attendus):] == attendus:
            premier_mot = portee[len(jetons) - len(attendus)]
            return " ".join(mots[:premier_mot]).strip(" ?!.,")
    return texte


def _retirer_bruit_initial(texte: str) -> str:
    """Retire UN determinant ou une locution en tete de cible.

    Meme alignement que pour la politesse finale, et pour la meme raison :
    « ouvre l'application Discord » donne la cible « l'application Discord »,
    dont les jetons sont « l application discord » alors que le mot original
    en tete est « l'application ». Une comparaison brute sur la chaine ne
    trouve donc jamais le bruit, et la cible garde son determinant.

    La coupure n'est acceptee qu'a une FRONTIERE de mot original : sans cette
    garde, le bruit « l » couperait « l'appli » en deux et laisserait
    « appli » — un demi-mot, qu'aucun lexique ne retrouvera.
    """
    mots = texte.split()
    if not mots:
        return texte

    jetons, portee = _aligner(mots)
    for bruit in BRUIT_CIBLE:
        attendus = bruit.split()
        # Il doit rester quelque chose : « ouvre le » n'a pas de cible « le »,
        # mais retirer « le » pour ne rien laisser n'aide personne non plus.
        if len(attendus) >= len(jetons):
            continue
        if jetons[: len(attendus)] != attendus:
            continue
        # Frontiere de mot original.
        if portee[len(attendus) - 1] == portee[len(attendus)]:
            continue
        return " ".join(mots[portee[len(attendus)] :]).strip()
    return texte


def _nettoyer_cible(brut: str) -> str:
    """Enleve les determinants en tete et la politesse en queue de cible.

    La politesse en queue compte autant que celle en tete : la cible de
    « lance Discord s'il te plait » est « Discord », pas « Discord s'il te
    plait ». Sans ce retrait, aucune application ne serait jamais retrouvee
    dans le lexique.
    """
    cible = re.sub(r"\s+", " ", brut).strip(" ?!.,")

    change = True
    while change:
        change = False
        for etage in (_retirer_bruit_initial, _retirer_politesse_finale):
            reduit = etage(cible)
            if reduit != cible:
                cible, change = reduit.strip(" ?!.,"), True
    return cible.strip(" ?!.,")


#: Les intentions dont la phrase peut porter une valeur visee.
AVEC_POURCENTAGE = frozenset({"volume_haut", "volume_bas", "volume_absolu"})

#: « 20 % », « 20 pour cent », « à 20 ». Cherche dans le texte ORIGINAL : la
#: normalisation supprime le signe %, et « 20% » y devient « 20 » — donc
#: indiscernable d'un nombre quelconque.
_POURCENTAGE = re.compile(
    r"(\d{1,3})\s*(?:%|pour\s?cents?)|(?:\bà|\ba)\s+(\d{1,3})\b", re.IGNORECASE
)


def pourcentage(texte: str) -> str:
    """Le pourcentage vise dans la phrase, ou une chaine vide.

    Une CHAINE et non un entier : c'est ce que transporte `Intention.cible`,
    et lui faire porter deux types selon l'intention aurait oblige chaque
    lecteur a savoir laquelle il regarde.
    """
    trouve = _POURCENTAGE.search(texte or "")
    if not trouve:
        return ""
    return trouve.group(1) or trouve.group(2) or ""


#: Ressemblance minimale pour reparer un declencheur mal transcrit.
#:
#: MESURE, PAS CHOISI. Sur les declencheurs reels :
#:
#:     « montre le son »  ~ « monte le son »     0,875   a reparer
#:     « quelle »         ~ « kill »             0,667   surtout pas
#:     « donne moi le son » ~ « monte le son »   0,500   surtout pas
#:     « parle »          ~ « demarre »          0,500   surtout pas
#:
#: Le trou entre 0,875 et 0,667 est large. C'est lui qui rend ce seuil
#: defendable, pas le chiffre lui-meme.
SEUIL_DECLENCHEUR = 0.85

#: En dessous, un declencheur est trop court pour etre rapproche sans risque :
#: sur quatre lettres, deux mots sans rapport se ressemblent facilement.
LONGUEUR_MIN_DECLENCHEUR = 8


def _rapprocher_le_declencheur(reduit: str) -> tuple[str, str]:
    """Repare un declencheur que la transcription a mal ecrit.

    LE CAS RELEVE EN CONDITIONS REELLES

        dit      « Nova, monte le son à 80 % »
        ecrit    « Nova montre le son à 80 % »
        compris  rien du tout

    « monte » et « montre » ne different que d'une lettre, et « montre » est
    bien plus frequent en francais : Whisper choisit le mot courant. Aucun
    reglage de transcription n'y peut rien de fiable.

    POURQUOI REPARER LE TEXTE PLUTOT QUE D'ELARGIR LA RECONNAISSANCE

    Ajouter « montre le son » a la table aurait marche pour cette phrase-la.
    Il aurait fallu y ajouter ensuite « mont le son », « montent le son »,
    « monte le sont » — une famille ouverte, dont chaque membre manquant
    ressemble a une panne. Rapprocher par le SON les traite tous.

    Et le faire AVANT la reconnaissance plutot que dedans laisse tout ce qui
    suit inchange : positions, extraction de cible, confiances.

    DEUX GARDES, ET ELLES COMPTENT PLUS QUE LA REGLE

      — uniquement les declencheurs SANS cible. Pour « ouvre » ou « ferme »,
        la cible est ensuite retrouvee dans le texte ORIGINAL ; la reparer
        d'un cote et pas de l'autre ferait perdre la cible en silence.
      — uniquement en TETE de phrase. « je te montre le son » n'est pas un
        ordre, et ne doit pas le devenir parce qu'il sonne comme un.
    """
    mots = reduit.split()
    if not mots:
        return reduit, ""

    # Depart 0 ou 1 : le mot de reveil survit parfois a l'application, et
    # « Nova monte le son » decalerait tout d'un mot. Meme tolerance que la
    # reconnaissance exacte, qui accepte un declencheur jusqu'au 12e caractere.
    departs = [0] + ([1] if mots and len(mots[0]) <= 12 else [])

    for _nom, declencheurs, exige_cible in DECLENCHEURS:
        if exige_cible:
            continue
        for declencheur in declencheurs:
            if len(declencheur) < LONGUEUR_MIN_DECLENCHEUR:
                continue
            taille = len(declencheur.split())
            for depart in departs:
                if depart + taille > len(mots):
                    continue
                tete = " ".join(mots[depart : depart + taille])
                if tete == declencheur:
                    return reduit, ""      # deja juste : rien a reparer
                if phonetique.ressemblance(tete, declencheur) >= SEUIL_DECLENCHEUR:
                    repare = [*mots[:depart], declencheur, *mots[depart + taille :]]
                    return " ".join(repare), f"{tete} → {declencheur}"
    return reduit, ""


def _candidats(reduit: str) -> list[tuple[str, str, bool, re.Match]]:
    """Les declencheurs presents dans la phrase, DU PLUS PRECIS AU PLUS VAGUE.

    ⚠️ LE BUG QUE CET ORDRE EMPECHE, ET QUI ETAIT DEJA LA

    « arrête l'ordinateur » contient « arrete », declencheur de
    `fermer_application`, ET « arrete l ordinateur », declencheur d'`arret_pc`.
    En parcourant la table dans l'ordre d'ecriture, le premier trouve gagnait —
    c'est-a-dire le plus vague. « arrête l'ordinateur » etait donc compris
    comme « ferme l'application ordinateur ».

    C'etait sans consequence tant qu'aucun outil ne repondait a
    `fermer_application` : Nova en parlait, sans agir. Le jour ou l'outil
    arrive, la meme phrase devient une action sur une cible inventee. Le
    defaut n'a pas ete cree par l'outil ; il attendait.

    Trier par LONGUEUR du declencheur regle la classe entiere plutot que ce
    cas : « arrete l ordinateur » (19 caracteres) l'emporte sur « arrete »
    (6), et il en ira de meme pour tous les declencheurs qu'on ajoutera. Se
    contenter de deplacer une ligne dans la table aurait marche aujourd'hui et
    se serait redefait au prochain ajout, en silence.

    A longueur egale, l'ordre de la table decide : il reste le dernier mot.
    """
    trouves: list[tuple[int, int, int, str, str, bool, re.Match]] = []
    for rang, (nom, declencheurs, exige_cible) in enumerate(DECLENCHEURS):
        for declencheur in declencheurs:
            # `[sz]?` tolere la conjugaison : « lance », « lances », « lancez ».
            # Enumerer les formes conjuguees aurait triple la table pour rien —
            # et en aurait rate autant. Uniquement sur les declencheurs d'UN
            # mot : « quel temps » n'a pas de forme en -s.
            fin = "[sz]?" if " " not in declencheur else ""
            motif = re.compile(rf"(?:^|\b)({re.escape(declencheur)}{fin})\b")
            # En tete, ou precede uniquement d'un mot outil deja retire par
            # `depolitesser`. Chercher n'importe ou produirait des faux
            # positifs — « je me demande si tu peux ouvrir » n'est pas un ordre.
            if trouve := motif.search(reduit):
                trouves.append(
                    (-len(declencheur), trouve.start(), rang, nom, declencheur, exige_cible, trouve)
                )

    trouves.sort(key=lambda c: c[:3])
    return [(nom, decl, exige, m) for *_, nom, decl, exige, m in trouves]


def reconnaitre(texte: str) -> Intention:
    """L'intention de la phrase, ou `AUCUNE`.

    La confiance suit deux regles simples et defendables :

      — une intention SANS cible attendue est sure des que son declencheur
        est present : « eteins le pc » ne veut rien dire d'autre ;
      — une intention AVEC cible n'est sure que si la cible existe. « ouvre »
        tout seul n'est pas une demande, c'est un debut de phrase.
    """
    if not texte or not texte.strip():
        return AUCUNE

    reduit = depolitesser(texte)
    if not reduit:
        return AUCUNE

    candidats = _candidats(reduit)
    rapproche = ""
    if not candidats:
        # UNIQUEMENT en dernier recours. Tant qu'un declencheur est ecrit
        # exactement, on ne va pas chercher ce qui lui ressemble : une phrase
        # juste ne doit jamais etre reinterpretee.
        reduit, rapproche = _rapprocher_le_declencheur(reduit)
        if rapproche:
            candidats = _candidats(reduit)

    for nom, declencheur, exige_cible, trouve in candidats:
        if not exige_cible:
            # Le declencheur doit occuper l'essentiel de la phrase :
            # « quelle heure est-il » oui, « je me souviens de l'heure ou
            # nous nous sommes rencontres » non.
            if trouve.start() > 12:
                continue
            return Intention(
                nom=nom,
                # Un declencheur RAPPROCHE recoit la confiance minimale qui
                # agit encore (`SEUIL_INTENTION`). Deliberement : le jour ou
                # ce seuil monte, les rapprochements sont les premiers exclus,
                # avant toute reconnaissance exacte.
                confiance=0.90 if rapproche else 0.95,
                declencheur=declencheur,
                arguments={"rapproche": rapproche} if rapproche else {},
                # « baisse le son à 20 % » porte une valeur VISEE. Sans elle,
                # Nova appliquait son pas et il fallait redemander jusqu'a
                # tomber juste — releve en conditions reelles.
                cible=pourcentage(texte) if nom in AVEC_POURCENTAGE else "",
            )

        cible = _nettoyer_cible(texte[len(texte) - len(reduit) :][trouve.end() :]) \
            if len(reduit) <= len(texte) else ""
        # On prefere retrouver la cible dans le texte ORIGINAL : c'est la
        # que « Discord » garde sa majuscule et son orthographe.
        cible = _cible_dans_original(texte, declencheur) or cible
        if not cible:
            continue
        return Intention(
            nom=nom,
            cible=cible,
            confiance=0.9 if trouve.start() <= 12 else 0.7,
            declencheur=declencheur,
        )

    return AUCUNE


def _cible_dans_original(texte: str, declencheur: str) -> str:
    """Ce qui suit le declencheur, dans le texte tel qu'il a ete dit.

    Passer par le texte normalise ferait perdre les majuscules et les accents
    du nom cherche — or « Discord » et « discord » ne se lancent pas pareil,
    et c'est ce nom qui sera compare au lexique des applications.
    """
    mots_origine = texte.split()
    mots_reduits = [_normaliser(m).strip() for m in mots_origine]
    cible_mots = declencheur.split()

    for debut in range(len(mots_reduits) - len(cible_mots) + 1):
        fenetre = mots_reduits[debut : debut + len(cible_mots)]
        # Meme tolerance a la conjugaison que dans `reconnaitre` : sans elle,
        # la cible de « lances Discord » serait introuvable alors que
        # l'intention, elle, a bien ete reconnue.
        conjugue = (
            len(cible_mots) == 1
            and bool(fenetre)
            and fenetre[0].rstrip("sz") == cible_mots[0].rstrip("sz")
            and fenetre[0].startswith(
                cible_mots[0][:-1] if len(cible_mots[0]) > 3 else cible_mots[0]
            )
        )
        if fenetre == cible_mots or conjugue:
            return _nettoyer_cible(" ".join(mots_origine[debut + len(cible_mots) :]))
    return ""


def intentions_connues() -> tuple[str, ...]:
    """Le catalogue, pour l'interface et pour le journal."""
    return tuple(nom for nom, _, _ in DECLENCHEURS)
