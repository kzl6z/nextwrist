"""La conversation ouverte : dire « Nova » une fois, puis parler.

CE QUI MANQUAIT

    « Nova, retrouve mes impots de 2024 »
    « Nova, ouvre le deuxieme »
    « Nova, et celui d'avant »

Trois fois le meme mot pour une seule conversation. Personne ne parle comme
ca — et le repeter casse le fil au moment ou l'on en a le plus besoin, juste
apres une reponse.

⚠️ LA SESSION VIT ICI, PAS DANS L'APPLICATION.

L'application de bureau envoie deja a `/v1/audio/wake` tout extrait sonore
qui depasse un seuil, et n'agit que si la reponse dit `wake: true`. Il suffit
donc que Nova Core reponde `true` pendant une conversation ouverte : le
comportement voulu apparait sans qu'une seule ligne de l'application change.

Faire l'inverse — un etat dans l'application — aurait duplique la regle dans
deux depots, avec la certitude qu'ils divergent.

⚠️ ET C'EST UNE FENETRE D'ECOUTE. IL FAUT LE DIRE.

Pendant qu'elle est ouverte, TOUT ce qui depasse le seuil sonore part a Nova :
une conversation avec quelqu'un d'autre, la television, une phrase qui ne lui
etait pas destinee. C'est le prix de ne plus dire son nom, et il n'est
acceptable qu'a trois conditions, toutes tenues ici :

    la fenetre est COURTE et se compte depuis le dernier echange
    une phrase explicite la referme (« c'est bon », « mets-toi en veille »)
    elle ne s'ouvre JAMAIS toute seule — il faut avoir dit « Nova »
"""

from __future__ import annotations

import re
import threading
import time
import unicodedata

from nova.logging_setup import get_logger

log = get_logger(__name__)

#: Duree d'ecoute apres le dernier echange, en secondes.
#:
#: ⚠️ DEPUIS LE DERNIER ECHANGE, PAS DEPUIS LE REVEIL.
#:
#: Une fenetre comptee depuis « Nova » se refermerait pendant que Nova parle :
#: elle met plusieurs secondes a dire sa reponse, et l'on repond juste apres.
#: Chaque echange repousse donc l'echeance — une conversation qui dure reste
#: ouverte, un silence la referme.
#:
#: Quarante-cinq secondes : assez pour reflechir a la reponse de Nova et
#: enchainer, trop court pour qu'un micro ouvert s'oublie.
DUREE_S = 45.0

_ouverte_jusqu_a: float = 0.0
_proposition: tuple[str, dict] | None = None
_libelle: str = ""
_verrou = threading.Lock()


def _plat(texte: str) -> str:
    sans = "".join(
        c
        for c in unicodedata.normalize("NFD", texte or "")
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", " ", sans.lower()).strip()


#: Ce qui referme la conversation.
#:
#: ⚠️ LA PHRASE ENTIERE DOIT ETRE UN CONGE, PAS UN MOT DEDANS.
#:
#: « merci » seul apparait au milieu d'une demande — « merci de m'ouvrir
#: ca ». Le prendre pour un conge couperait la conversation au pire moment.
#: Le motif est donc ancre aux deux bouts.
#:
#: ⚠️ MAIS « c'est bon, tu peux t'eteindre » N'ETAIT PAS RECONNU NON PLUS.
#:
#: La premiere version exigeait une correspondance exacte avec une liste, et
#: l'on ne dit jamais deux fois la meme formule. On admet donc une amorce
#: optionnelle — « c'est bon », « ok », « merci » — et une queue de
#: politesse, tout en gardant les deux ancres.
_CONGE = re.compile(
    r"^(?:(?:c est bon|ok|d accord|merci|bon|voila|nova)[, ]+)*"
    r"(?:"
    r"c est bon|c est tout|ca ira|ca suffit|ca marche|"
    r"(?:tu peux )?t eteindre|(?:tu peux )?te mettre en veille|"
    r"mets? toi en veille|va en veille|mise en veille|eteins? toi|"
    r"laisse tomber|laisse moi|arrete de m ecouter|stop l ecoute|"
    r"a plus tard|a toute|bonne nuit|au revoir|salut|"
    r"nova en veille|tais toi c est bon|"
    r"j ai fini|c est fini|termine|on arrete|merci"
    r")"
    r"(?:[, ]+(?:merci|nova|maintenant|s il te plait|stp))*$"
)


def demande_de_veille(texte: str) -> bool:
    """Cette phrase referme-t-elle la conversation ?"""
    return bool(_CONGE.match(_plat(texte)))


def ouvrir() -> None:
    """Le mot de reveil a ete entendu : la conversation commence."""
    global _ouverte_jusqu_a
    with _verrou:
        _ouverte_jusqu_a = time.monotonic() + DUREE_S
    log.info("Conversation ouverte pour %.0f s — « Nova » devient facultatif.", DUREE_S)


def prolonger() -> None:
    """Un echange vient d'avoir lieu : on repousse l'echeance.

    Ne rouvre JAMAIS une conversation fermee. Sans cette garde, une reponse
    tardive — la synthese vocale, un outil lent — ranimerait une fenetre que
    le silence venait de refermer.
    """
    global _ouverte_jusqu_a
    with _verrou:
        if _ouverte_jusqu_a > time.monotonic():
            _ouverte_jusqu_a = time.monotonic() + DUREE_S


def fermer(raison: str = "conge") -> None:
    """Retour a l'ecoute du seul mot de reveil."""
    global _ouverte_jusqu_a, _proposition, _libelle
    with _verrou:
        etait_ouverte = _ouverte_jusqu_a > time.monotonic()
        _ouverte_jusqu_a = 0.0
        _proposition = None
        _libelle = ""
    if etait_ouverte:
        log.info("Conversation fermee (%s) — « Nova » redevient necessaire.", raison)


def est_ouverte() -> bool:
    """Peut-on parler a Nova sans la nommer ?"""
    with _verrou:
        return _ouverte_jusqu_a > time.monotonic()


def restant() -> float:
    """Secondes d'ecoute restantes. Pour le journal et les bancs."""
    with _verrou:
        return max(0.0, _ouverte_jusqu_a - time.monotonic())


# ══════════════════════════════════════════════════════════════════════════
#  LA PROPOSITION EN ATTENTE — « je l'ouvre ? » « oui »
# ══════════════════════════════════════════════════════════════════════════
#: Ce qui vaut « oui » quand une proposition attend.
#:
#: ⚠️ UN « OUI » NU NE VEUT RIEN DIRE HORS D'UNE PROPOSITION.
#:
#: C'est la seule raison pour laquelle on peut se permettre une liste aussi
#: courte et aussi generique. Sans proposition en attente, ces mots repartent
#: vers le modele comme n'importe quelle phrase.
_ACCORD = re.compile(
    r"^(?:oui|ouais|ouaip|oui merci|oui s il te plait|vas y|vas y oui|"
    r"d accord|dac|ok|okay|c est ca|exactement|volontiers|je veux bien|"
    r"s il te plait|fais le|allez y|allez|bien sur)$"
)

#: Et ce qui vaut « non ».
_REFUS = re.compile(
    r"^(?:non|non merci|pas la peine|laisse|surtout pas|pas maintenant|"
    r"non c est bon|non pas celui la)$"
)


def proposer(outil: str, arguments: dict, *, comme: str = "") -> None:
    """Note l'action que Nova vient de proposer, pour qu'« oui » la declenche.

    ⚠️ UNE SEULE A LA FOIS, ET ELLE MEURT AVEC LA CONVERSATION.

    Empiler des propositions ferait qu'un « oui » repondrait a la mauvaise —
    et l'on ne saurait pas laquelle. Une proposition non suivie d'un accord
    disparait simplement.
    """
    global _proposition, _libelle
    with _verrou:
        _proposition = (outil, dict(arguments))
        _libelle = comme
    log.info("Proposition en attente : %s %s", outil, arguments)


def libelle() -> str:
    """Comment DIRE la chose proposee — les mots de la demande, pas le nom de
    fichier. « ta carte d'identite » plutot que « CNI BERANGERE RECTO-1.png »."""
    with _verrou:
        return _libelle


def accord(texte: str) -> tuple[str, dict] | None:
    """La proposition en attente si cette phrase l'accepte, sinon `None`.

    Consomme la proposition : un « oui » ne vaut qu'une fois. Sans cela, un
    second « oui » — ou un « oui » qui repond a autre chose — rejouerait
    l'action.
    """
    global _proposition
    plat = _plat(texte)
    with _verrou:
        en_attente = _proposition
        if en_attente is None:
            return None
        if _REFUS.match(plat):
            _proposition = None
            log.info("Proposition refusee.")
            return None
        if not _ACCORD.match(plat):
            return None
        _proposition = None
    log.info("Proposition acceptee : %s", en_attente[0])
    return en_attente


def en_attente() -> tuple[str, dict] | None:
    """La proposition, sans la consommer. Pour le journal et les bancs."""
    with _verrou:
        return _proposition


# ══════════════════════════════════════════════════════════════════════════
#  LE PROPOS PRECEDENT — CE QUE « CA » DESIGNE
# ══════════════════════════════════════════════════════════════════════════
#: La derniere phrase prononcee avant celle qu'on traite.
#:
#: ⚠️ « AJOUTE CA AUX PROCHAINES ETAPES » NE PORTE PAS SON CONTENU.
#:
#: Dans une conversation, « ca » designe ce qu'on vient de dire. Sans cette
#: memoire d'une phrase, l'ordre est compris et vide : Nova noterait une tache
#: sans intitule, ou pire en inventerait un.
#:
#: Une seule phrase, en memoire vive, effacee avec la conversation. Ce n'est
#: pas de la memoire — c'est le fil de la phrase en cours.
_propos_precedent: str = ""


def noter_le_propos(texte: str) -> str:
    """Enregistre la phrase courante et rend CELLE D'AVANT.

    Les deux d'un coup, et c'est deliberé : un appelant qui lirait puis
    ecrirait en deux temps introduirait une course, et l'ordre des appels
    entre l'application et Nova Core n'est pas garanti.
    """
    global _propos_precedent
    with _verrou:
        avant = _propos_precedent
        if (texte or "").strip():
            _propos_precedent = texte.strip()
    return avant


def propos_precedent() -> str:
    """La phrase d'avant, sans rien enregistrer. Pour le journal et les bancs."""
    with _verrou:
        return _propos_precedent


def oublier() -> None:
    """Remet tout a zero. Pour les bancs."""
    global _propos_precedent
    with _verrou:
        _propos_precedent = ""
    fermer("remise a zero")
