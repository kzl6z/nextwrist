"""Cette question s'appuie-t-elle sur ce qui vient d'etre dit ?

LE DEFAUT, RELEVE EN CONDITIONS REELLES

    — « quelle est la carte la plus rare, Pokemon ? »
      Nova repond sur les cartes.
    — « trouve-moi dans mon PC une image ou je tiens une casquette blanche »
      « Je ne trouve pas de CARTE BLANCHE correspondant a un SKATE. »

La carte vient de la question d'avant. Elle n'avait rien a faire la, et le
modele n'avait aucun moyen de le savoir : on lui donnait douze messages
precedents sans lui dire lesquels comptaient encore.

⚠️ LE PASSE ETAIT INJECTE A CHAQUE QUESTION, SANS EXCEPTION.

C'etait le bon reflexe quand il manquait — « Et on pourrait y vivre ? » n'a
aucun sens sans « Parle-moi de Mars ». Mais l'inverse est aussi vrai, et bien
plus frequent : l'ecrasante majorite des questions se suffisent a
elles-memes, et leur donner le passe ne les aide pas — ca les brouille.

Le cout est double, et le second est le pire :

    1. 1200 caracteres de prompt en plus, sur CHAQUE question
    2. un sujet abandonne qui revient dans une reponse sans rapport

⚠️ CE MODULE NE DECIDE PAS DE CE QU'IL FAUT SE RAPPELER.

Il repond a une seule question : la phrase courante RENVOIE-T-ELLE a quelque
chose d'anterieur ? C'est une propriete de la phrase, lisible sans modele,
sans base et sans historique. Le rappel lui-meme reste ou il etait.

⚠️ ET IL SE TROMPE DANS LE BON SENS.

Un faux positif coute 1200 caracteres de prompt. Un faux negatif rend « et
pourquoi ? » incomprehensible. Dans le doute, on rappelle — d'ou une phrase
courte, une question nue ou un simple « oui » qui declenchent le rappel sans
autre signal.
"""

from __future__ import annotations

import re
import unicodedata

#: Mots qui ne portent aucun sujet : grammaire, interrogatifs nus,
#: acquiescements.
#:
#: ⚠️ J'AI D'ABORD UTILISE LA LONGUEUR DE LA PHRASE. C'ETAIT FAUX.
#:
#: « une phrase courte est une suite » attrapait « parle-moi de Mars » (17
#: caracteres) et « qu'est-ce qu'un trou noir » (24) — deux questions
#: parfaitement autonomes. Le seuil faisait tout le travail, et le faisait
#: mal.
#:
#: Ce qui distingue « pourquoi ? » de « parle-moi de Mars » n'est pas la
#: longueur : c'est que la seconde porte un SUJET et la premiere non. On
#: compte donc les mots porteurs, et zero signifie que la phrase ne peut
#: parler que de ce qui precede.
_VIDES: frozenset[str] = frozenset(
    """
    le la les un une des du de d au aux a et ou ni mais donc or car
    je tu il elle on nous vous ils elles me te se lui leur y en moi toi
    ce cet cette ces mon ma mes ton ta tes son sa ses notre votre nos vos
    est sont etre ete suis es sommes etes ai as avons avez ont avoir fait
    qui que quoi dont ou quel quelle quels quelles comment pourquoi combien
    quand
    ne pas plus moins tres bien mal encore aussi deja toujours jamais si
    oui non ok okay merci stp svp plait plais d'accord
    ca cela c'est
    peux peut peuvent veux veut veulent faut faudrait pourrait pourrais
    apres avant maintenant vraiment sur pour avec sans dans par en
    alors puis ensuite vas y allez
    """.split()
)


def _porte_un_sujet(plat: str) -> bool:
    """La phrase contient-elle au moins un mot qui designe quelque chose ?"""
    return any(mot not in _VIDES and len(mot) > 1 for mot in plat.split())


def _plat(texte: str) -> str:
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", texte or "") if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]+", " ", sans_accents.lower())).strip()


#: Un connecteur EN TETE de phrase enchaine sur ce qui precede.
#:
#: En tete seulement : « il pleut et il vente » n'enchaine sur rien, alors que
#: « et il vente ? » suppose une phrase avant. La position porte tout le sens,
#: et c'est ce qui evite d'attraper la moitie du francais.
_ENCHAINE = re.compile(
    r"^(?:et|mais|donc|alors|puis|ensuite|sinon|aussi|d'ailleurs|du coup|"
    r"par contre|en fait|bref|ok|d'accord|oui|non|ah|ben|bon)\b",
    re.IGNORECASE,
)

#: Un pronom ou un adverbe qui ne designe rien tout seul.
#:
#: ⚠️ LISTE COURTE, ET PAS PAR PARESSE.
#:
#: « la », « le », « les » sont aussi des articles — les inclure ferait
#: renvoyer VRAI sur presque toute phrase francaise, et le rappel
#: redeviendrait systematique. On ne garde que ce qui ne peut pas etre autre
#: chose qu'une reprise.
_REPREND = re.compile(
    r"\b(?:y|ca|cela|celui|celle|ceux|celles|"
    r"celui[- ]ci|celle[- ]ci|celui[- ]la|celle[- ]la|"
    r"la[- ]dessus|la[- ]dedans|en[- ]dessous|"
    r"pareil|meme chose|la suite|le reste|l'autre|les autres)\b",
    re.IGNORECASE,
)

#: Une reference explicite a l'echange precedent.
_RENVOIE = re.compile(
    r"\b(?:tu disais|tu as dit|tu viens de|tout a l'heure|"
    r"precedent|precedente|juste avant|on parlait|on disait|"
    r"derniere fois|comme tu|redis|repete|reformule|explique mieux)\b",
    re.IGNORECASE,
)


def reprend_le_passe(texte: str) -> bool:
    """La phrase renvoie-t-elle a quelque chose d'anterieur ?

    ⚠️ LE DEFAUT EST « NON », ET C'EST L'INVERSE DE CE QUI EXISTAIT.

    Avant, le passe partait toujours. Ici il faut un SIGNAL — un connecteur en
    tete, un pronom sans antecedent, une reference explicite, ou une phrase
    trop courte pour porter son sujet.
    """
    plat = _plat(texte)
    if not plat:
        return False
    if not _porte_un_sujet(plat):
        return True
    return bool(_ENCHAINE.search(plat) or _REPREND.search(plat) or _RENVOIE.search(plat))


def raison(texte: str) -> str:
    """Pourquoi le passe a ete rappele, ou non. Pour le journal.

    Une decision invisible qui change la reponse est une decision qu'on
    passera des heures a chercher. Celle-ci se lit dans la console.
    """
    plat = _plat(texte)
    if not plat:
        return "question vide"
    if not _porte_un_sujet(plat):
        return "ne porte aucun sujet propre"
    if _ENCHAINE.search(plat):
        return "enchaine sur ce qui precede"
    if _REPREND.search(plat):
        return "contient une reprise sans antecedent"
    if _RENVOIE.search(plat):
        return "renvoie explicitement a l'echange precedent"
    return "question autonome"
