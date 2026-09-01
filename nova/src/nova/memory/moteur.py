"""Le Memory Engine : que retenir, quoi rappeler, quand oublier.

CE QUI EXISTAIT DEJA, ET QU'IL NE FALLAIT PAS REFAIRE

    facts.py         la table des faits, `add`, `list_facts`, `confirm`,
                     `archive`, et le BUDGET de caracteres du prompt
    reprise.py       « cette phrase renvoie-t-elle a ce qui precede ? » —
                     la memoire courte, deja mesuree et deja branchee
    conversations.py le journal des echanges — la memoire episodique brute
    documents/       pgvector et la recherche semantique sur les documents

Ce module ne remplace rien de tout cela. Il ajoute les trois choses qui
manquaient, et qui manquaient VRAIMENT — verifiees sur une base reelle avant
d'ecrire une ligne :

⚠️ 1. RIEN N'ECRIVAIT EN MEMOIRE DEPUIS UNE CONVERSATION.

    « souviens-toi que mon projet s'appelle NOVA »
    → intention « memoire » reconnue, aucune action derriere, RIEN EN BASE.

Le seul chemin d'ecriture etait la ligne de commande et l'API d'administration.
La recette du cahier des charges — memoriser, redemarrer, se rappeler — ne
pouvait pas passer.

⚠️ 2. TOUTE LA MEMOIRE PARTAIT DANS CHAQUE PROMPT.

`render_for_prompt` injecte TOUS les faits confirmes, tronques par DATE quand
le budget est atteint. A vingt faits c'est le bon choix, et le commentaire de
`facts.py` le defend bien : « le fait important est souvent celui qui ne
ressemble pas a la question ».

A trois cents faits, c'est intenable — 3,3 ms par caractere avant le premier
mot sur cette machine — et la troncature par date fait disparaitre en silence
un fait critique de l'an dernier derriere trois preferences notees hier.

Les deux ont raison a des echelles differentes. On garde donc le NOYAU
toujours injecte, et l'on choisit le reste par pertinence.

⚠️ 3. UNE INFORMATION QUI CHANGE CREAIT UNE CONTRADICTION.

`add` empilait. « Le modele principal est X » et « le modele principal est Y »
coexistaient, tous deux confirmes, tous deux injectes. Le modele en choisissait
un — au hasard, du point de vue de l'utilisateur.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime, timedelta

from nova.logging_setup import get_logger
from nova.memory.models import Fact

log = get_logger(__name__)

#: Ce qui ne tombe jamais du prompt, quel que soit le budget.
NOYAU: frozenset[str] = frozenset({"critique"})

#: Rang de chaque niveau, pour trier.
RANGS: dict[str, int] = {"basse": 0, "moyenne": 1, "haute": 2, "critique": 3}


def _plat(texte: str) -> str:
    """Minuscules, sans accents, ponctuation en espaces.

    Le meme aplatissement que `requete._normaliser`, `session._plat` et
    `reprise._plat` — quatre endroits qui recoivent de la parole transcrite,
    et la meme regle. Les rassembler un jour serait bien ; les laisser
    diverger serait pire.
    """
    sans = "".join(
        c
        for c in unicodedata.normalize("NFD", texte or "")
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", " ", sans.lower()).strip()


# ══════════════════════════════════════════════════════════════════════════
#  1. FAUT-IL RETENIR ? — LA DECISION
# ══════════════════════════════════════════════════════════════════════════
#: Une demande EXPLICITE de memoriser. Elle ne se discute pas.
#:
#: ⚠️ CE MOTIF EST LE SEUL QUI ECRIT AUJOURD'HUI, ET C'EST DELIBERE.
#:
#: Deduire tout seul ce qui merite d'etre retenu est la premiere cause de
#: pourrissement d'une memoire (risque R5, deja nomme dans `facts.py`) : au
#: bout d'un an, Nova est confiante et fausse. Le schema le prevoit depuis le
#: premier jour — `origin` separe ce que TU declares de ce que le modele
#: DEDUIT, et le deduit entre en `proposed`, pas en `confirmed`.
#:
#: On commence donc par ce qui ne peut pas se tromper : ce que tu demandes.
_DEMANDE_DE_RETENIR = re.compile(
    r"\b(?:"
    r"souviens? toi|souvenez vous|retiens|retenez|"
    r"note que|notes que|n oublie pas que|garde en memoire|"
    r"rappelle toi|memorise|enregistre que|"
    r"il faut que tu saches"
    r")\b"
)

#: Ce qui suit l'amorce et n'apporte rien : « que », « bien que je »…
_APRES_L_AMORCE = re.compile(r"^(?:que|qu|de|d|:)\s+", re.IGNORECASE)


def demande_de_retenir(texte: str) -> bool:
    """Cette phrase demande-t-elle explicitement de memoriser ?"""
    return bool(_DEMANDE_DE_RETENIR.search(_plat(texte)))


def contenu_a_retenir(texte: str) -> str:
    """Ce qu'il faut ecrire, sans l'amorce.

    « souviens-toi que mon projet s'appelle NOVA » → « mon projet s'appelle
    NOVA ». On stocke le FAIT, pas la phrase qui a servi a le dire : « Nova,
    souviens-toi que… » n'est pas une information sur l'utilisateur.
    """
    plat_original = texte or ""
    trouve = _DEMANDE_DE_RETENIR.search(_plat(plat_original))
    if trouve is None:
        return plat_original.strip()
    # On coupe sur le texte D'ORIGINE, a la position equivalente : l'aplati a
    # la meme longueur mot pour mot dans les cas courants, et l'on prefere
    # rendre la phrase entiere plutot qu'une decoupe fausse.
    reste = _APRES_L_AMORCE.sub("", plat_original[trouve.end() :].strip())
    return (reste or plat_original).strip(" ,.!?;:")


#: Les mots qui trahissent une information DURABLE sur la personne.
#:
#: Sert a proposer une categorie, jamais a decider d'ecrire : c'est la
#: demande explicite qui decide.
_CATEGORIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("projet", re.compile(r"\b(?:projet|application|appli|logiciel|depot|code|nova)\b")),
    (
        "preference",
        re.compile(r"\b(?:prefere|preferes|aime|adore|deteste|plutot|toujours|jamais)\b"),
    ),
    (
        "contrainte",
        re.compile(r"\b(?:allergi\w*|ne peux pas|interdit|jamais de|handicap|sante)\b"),
    ),
    ("objectif", re.compile(r"\b(?:objectif|but|je veux|j aimerais|ambition)\b")),
)


def categorie_probable(contenu: str) -> str:
    """Une categorie plausible, `profil` par defaut.

    Une proposition, pas un verdict : `facts.CATEGORIES` reste la reference et
    l'interface d'administration permet de corriger.
    """
    plat = _plat(contenu)
    for nom, motif in _CATEGORIES:
        if motif.search(plat):
            return nom
    return "profil"


#: Ce qui, dit explicitement, signale une information temporaire.
_TEMPORAIRE = re.compile(
    r"\b(?:aujourd hui|ce soir|ce matin|cet apres midi|demain|cette semaine|"
    r"ce week end|jusqu a|pour l instant|en ce moment|temporairement)\b"
)

#: Duree de vie d'une information temporaire, faute de date precise.
DUREE_TEMPORAIRE = timedelta(days=7)


def peremption_probable(contenu: str, *, maintenant: datetime | None = None):
    """Une date de peremption si l'information se dit temporaire, sinon `None`.

    ⚠️ ON NE DEVINE PAS DE DUREE PRECISE.

    « jusqu'a vendredi » demanderait de resoudre une date relative, donc de se
    tromper d'un jour une fois sur trois. Sept jours est un choix assume : au
    pire l'information survit un peu trop, au mieux elle disparait toute
    seule. Une date fausse serait pire que pas de date.
    """
    if not _TEMPORAIRE.search(_plat(contenu)):
        return None
    return (maintenant or datetime.now(UTC)) + DUREE_TEMPORAIRE


# ══════════════════════════════════════════════════════════════════════════
#  2. ECRIRE — ET NE PAS EMPILER DE CONTRADICTIONS
# ══════════════════════════════════════════════════════════════════════════
#: Sous ce recouvrement, deux faits parlent d'autre chose.
#:
#: ⚠️ CETTE VALEUR EST MESUREE, PAS CHOISIE AU JUGE.
#:
#: La premiere valait 0,55, et un banc l'a prise en defaut : « j'habite a
#: Lyon » contre « j'habite a Paris » vaut 0,50 — deux faits qui se
#: contredisent evidemment, et qui coexistaient donc en base.
#:
#: Quatorze paires reelles ont ete mesurees, sept qui parlent du meme sujet et
#: sept qui n'ont rien a voir :
#:
#:     meme sujet, le plus BAS      0,50   « j'habite a Lyon » / « a Paris »
#:     sujets differents, le + HAUT 0,33   « ma soeur s'appelle X » /
#:                                         « mon projet s'appelle Y »
#:
#: Les deux classes se separent — ce qui n'allait pas de soi, et n'a pas ete
#: le cas pour le rapprochement phonetique, ou aucun seuil ne passait entre
#: « empeaux »→impots (0,67) et « porsche »→impots (0,67). Ici il y a un
#: intervalle, et 0,45 se place dedans avec de la marge des deux cotes.
#:
#: ⚠️ ET L'ERREUR N'EST PAS SYMETRIQUE.
#:
#: Un faux positif archive un fait a tort : recuperable, il n'est pas
#: supprime. Un faux negatif laisse deux faits contradictoires dans le prompt,
#: et le modele en choisit un au hasard — c'est le defaut qu'on corrige.
SEUIL_CONTRADICTION = 0.45


def _mots_utiles(texte: str) -> frozenset[str]:
    """Les mots porteurs de sens, sans la grammaire."""
    from nova.memory.reprise import _VIDES

    return frozenset(
        mot for mot in _plat(texte).split() if mot not in _VIDES and len(mot) > 2
    )


def recouvrement(a: str, b: str) -> float:
    """Part de mots utiles communs, entre 0 et 1.

    ⚠️ UNE PROPORTION, PAS UN COMPTE — MEME REGLE QUE PARTOUT AILLEURS.

    Compter les mots communs ferait gagner les faits LONGS : une phrase de
    trente mots en partage forcement quelques-unes avec tout le monde.
    """
    mots_a, mots_b = _mots_utiles(a), _mots_utiles(b)
    if not mots_a or not mots_b:
        return 0.0
    return len(mots_a & mots_b) / min(len(mots_a), len(mots_b))


def contradictions(contenu: str, existants: list[Fact]) -> list[Fact]:
    """Les faits actifs qui parlent visiblement de la meme chose.

    ⚠️ « PARLE DE LA MEME CHOSE » N'EST PAS « DIT LE CONTRAIRE ».

    Etablir qu'une phrase contredit une autre demanderait de comprendre les
    deux — donc un modele, donc un appel, donc du temps sur le chemin d'une
    reponse. Et un modele de trois milliards de parametres s'y trompe.

    Ce qu'on peut faire sans modele, et sans se tromper : reperer que deux
    faits portent sur le meme SUJET. Le plus recent gagne, l'ancien est
    archive et le lien dit lequel remplace lequel. Si les deux etaient
    compatibles, on a perdu une redite ; s'ils se contredisaient, on a evite
    que le modele choisisse au hasard.
    """
    return [
        fait
        for fait in existants
        if fait.status != "archived"
        and recouvrement(contenu, fait.content) >= SEUIL_CONTRADICTION
    ]


def retenir(
    texte: str,
    *,
    origine: str = "user",
    source: str | None = None,
    maintenant: datetime | None = None,
) -> Fact | None:
    """Ecrit un fait depuis une phrase, et archive ce qu'il remplace.

    Rend le fait ecrit, ou `None` si la phrase ne demandait rien.

    ⚠️ NE PRETEND JAMAIS AVOIR RETENU QUELQUE CHOSE QUI N'EST PAS EN BASE.

    C'est la regle explicite du cahier des charges, et c'est aussi la seule
    facon d'etre utile : une memoire qui dit « c'est note » sans noter est
    pire qu'une absence de memoire, parce qu'on cesse de verifier.
    """
    from nova.memory import facts

    if not demande_de_retenir(texte):
        return None
    contenu = contenu_a_retenir(texte)
    if not contenu:
        return None

    log.info("[Memory] Demande de memorisation recue")
    remplaces = contradictions(contenu, facts.list_facts())
    if remplaces:
        log.info(
            "[Memory] %d fait(s) portant sur le meme sujet seront archives",
            len(remplaces),
        )

    fait = facts.add(
        contenu,
        category=categorie_probable(contenu),
        origin=origine,
        source=source,
        importance="haute" if remplaces else "moyenne",
        expires_at=peremption_probable(contenu, maintenant=maintenant),
        supersedes=remplaces[0].id if remplaces else None,
    )
    for ancien in remplaces:
        facts.archive(ancien.id)
    log.info("[Memory] Fait %d enregistre (%s)", fait.id, fait.category)
    return fait


# ══════════════════════════════════════════════════════════════════════════
#  3. RAPPELER — MAIS SEULEMENT CE QUI SERT
# ══════════════════════════════════════════════════════════════════════════
def actifs(tous: list[Fact], *, maintenant: datetime | None = None) -> list[Fact]:
    """Les faits utilisables : confirmes et non perimes."""
    reference = maintenant or datetime.now(UTC)
    return [
        fait
        for fait in tous
        if fait.status == "confirmed" and not fait.perime(reference)
    ]


def pertinence(fait: Fact, question: str) -> float:
    """A quel point ce fait sert a repondre a cette question, entre 0 et 1.

    ⚠️ L'IMPORTANCE COMPTE MEME SANS RAPPORT AVEC LA QUESTION.

    C'est ce qui repond a l'objection — juste — de `facts.py` : « le fait
    important est souvent celui qui ne ressemble pas a la question ». Une
    allergie n'a aucun mot en commun avec « propose-moi un restaurant », et
    c'est precisement le fait qu'il ne faut pas rater.

    Le recouvrement de mots ne fait donc que HAUSSER un fait, il n'en abaisse
    aucun sous son plancher d'importance.
    """
    plancher = RANGS.get(fait.importance, 1) / 6.0  # 0,00 a 0,50
    return min(1.0, plancher + 0.5 * recouvrement(question, fait.content))


def pertinents(
    question: str,
    tous: list[Fact],
    *,
    budget: int,
    maintenant: datetime | None = None,
) -> list[Fact]:
    """Les faits a injecter pour CETTE question, dans le budget donne.

    ⚠️ LE NOYAU PASSE D'ABORD, ET NE SE NEGOCIE PAS.

    Un fait « critique » entre quoi qu'il arrive : c'est ce que ce niveau
    signifie. Le reste concourt, du plus pertinent au moins pertinent, et
    s'arrete quand le budget est atteint.

    ⚠️ ET LA TRONCATURE NE SE FAIT PLUS PAR DATE.

    `render_for_prompt` gardait les plus RECENTS. A vingt faits cela ne se
    voyait pas ; a trois cents, un fait critique de l'an dernier disparaissait
    derriere trois preferences notees hier — en silence, ce qui est le pire.
    """
    utilisables = actifs(tous, maintenant=maintenant)
    if not utilisables:
        log.info("[Memory] Aucun fait actif")
        return []

    noyau = [f for f in utilisables if f.importance in NOYAU]
    reste = [f for f in utilisables if f.importance not in NOYAU]
    reste.sort(key=lambda f: (pertinence(f, question), f.created_at), reverse=True)

    gardes: list[Fact] = []
    total = 0
    for fait in noyau + reste:
        cout = len(fait.content) + 3  # « - » et le retour a la ligne
        if total + cout > budget and fait.importance not in NOYAU:
            continue
        gardes.append(fait)
        total += cout

    log.info(
        "[Memory] %d fait(s) retenu(s) sur %d actifs (%d/%d caracteres)",
        len(gardes), len(utilisables), total, budget,
    )
    return gardes


# ══════════════════════════════════════════════════════════════════════════
#  4. OUBLIER
# ══════════════════════════════════════════════════════════════════════════
#: « Nova, oublie ca », « supprime cette information ».
#:
#: ⚠️ « N'OUBLIE PAS QUE… » EST UNE DEMANDE DE RETENIR. LE PIRE CONTRESENS.
#:
#: Les deux formules contiennent le mot « oublie ». Sans la garde ci-dessous,
#: « n'oublie pas que je suis allergique aux arachides » effacait un fait au
#: moment precis ou l'on demandait de le garder — et l'oubli etant teste en
#: premier, il gagnait.
#:
#: Trouve par un banc, pas par la relecture : les deux motifs avaient l'air
#: distincts en les lisant l'un apres l'autre.
#:
#: La negation se lit dans les deux sens, parce que la parole transcrite
#: produit les deux : « n'oublie pas » devient « n oublie pas » une fois
#: aplati, et « ne pas oublier » existe aussi.
_DEMANDE_D_OUBLI = re.compile(
    r"(?<!n )(?<!ne )\b(?:"
    r"oublie(?! pas)(?: ca| cela| cette| ce| tout| moi ca)?|oubliez(?! pas)|"
    r"supprime (?:ca|cela|cette|ce|de ta memoire)|"
    r"efface(?: ca| cela| cette| ce)?|"
    r"retire (?:ca|cela) de ta memoire|"
    r"ne (?:te )?souviens? plus"
    r")\b"
)


def demande_d_oubli(texte: str) -> bool:
    """Cette phrase demande-t-elle de supprimer une information ?"""
    return bool(_DEMANDE_D_OUBLI.search(_plat(texte)))


def oublier(texte: str) -> list[Fact]:
    """Archive les faits que la phrase designe. Rend ceux qui l'ont ete.

    ⚠️ « OUBLIE CA » SANS AUTRE PRECISION OUBLIE LE DERNIER FAIT ECRIT.

    C'est ce que la phrase veut dire dans une conversation : « ca » designe ce
    dont on vient de parler. Oublier au hasard serait pire que ne rien faire,
    et oublier TOUT sur un « oublie ca » serait une catastrophe silencieuse.

    ⚠️ ON ARCHIVE, ON NE SUPPRIME PAS.

    Meme regle que `facts.archive`, et pour la meme raison : un fait retire
    garde de la valeur, et un effacement definitif ne se rattrape pas. Du
    point de vue de Nova, un fait archive n'existe plus — il ne sort d'aucune
    lecture, d'aucun prompt.
    """
    from nova.memory import facts

    if not demande_d_oubli(texte):
        return []

    tous = [f for f in facts.list_facts() if f.status != "archived"]
    if not tous:
        log.info("[Memory] Rien a oublier : aucun fait actif")
        return []

    # Ce que la phrase designe, en retirant la formule d'oubli elle-meme.
    cible = _DEMANDE_D_OUBLI.sub(" ", _plat(texte)).strip()
    vises = [f for f in tous if recouvrement(cible, f.content) >= SEUIL_CONTRADICTION]
    if not vises:
        # « oublie ca » : le dernier ecrit. `list_facts` rend du plus recent
        # au plus ancien.
        vises = [tous[0]]
        log.info("[Memory] « %s » designe le dernier fait retenu", texte[:40])

    for fait in vises:
        facts.archive(fait.id)
    log.info("[Memory] %d fait(s) oublie(s)", len(vises))
    return vises
