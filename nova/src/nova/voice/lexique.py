"""Le lexique personnel : les mots que Nova doit reconnaitre parce qu'ils sont
les TIENS.

LE PROBLEME QU'IL RESOUT

Whisper se trompe sur ce qui est rare dans la langue. « Ollama », « Rafale »,
« Electron », « Mistral » ne sont pas rares pour toi — ils le sont pour lui.
Un lexique personnel comble exactement cet ecart, et rien d'autre.

    entendu « aux lamas »   ->  code OLA   ->  « Ollama »   (0,95)
    entendu « la rafale »   ->  code RAFAL ->  « Rafale »   (0,90)
    entendu « bonsoir »     ->  code BOSWAR -> aucun voisin (on ne touche a rien)

L'APPRENTISSAGE, ET SA LIMITE

Un terme entre dans le lexique quand il est CONFIRME — pas quand il est
entendu. Trois sources, par ordre de confiance :

    declare     tu l'as ecrit dans .env             confiance maximale
    memoire     il figure dans un fait confirme     confiance haute
    appris      tu as confirme une correction       confiance croissante

La distinction n'est pas theorique : apprendre depuis les transcriptions
brutes ferait entrer « aux lamas » dans le lexique et Nova apprendrait sa
propre erreur. C'est le mode d'echec classique de ce genre de systeme, et il
est silencieux.

POURQUOI UN INDEX PHONETIQUE ET PAS UNE SIMPLE LISTE

Chercher « aux lamas » dans une liste de mots ne donne rien : aucune lettre
ne coincide. Chercher son CODE PHONETIQUE dans un index de codes le trouve
immediatement. L'index est reconstruit a chaque changement du lexique, ce qui
est negligeable — quelques centaines de termes au plus.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from nova.logging_setup import get_logger
from nova.voice import phonetique

log = get_logger(__name__)

#: En dessous, on ne propose rien. Choisi haut a dessein : le cout d'une
#: correction fausse (Nova repond a cote) depasse celui d'une correction
#: manquee (Nova demande a repeter).
SEUIL_PROPOSITION = 0.82

#: Au-dessus, on corrige sans demander. Un terme du lexique retrouve
#: quasi exactement ne merite pas d'interrompre la conversation.
SEUIL_CERTITUDE = 0.94

#: En dessous, un terme est trop court pour etre corrige sans risque : sur
#: trois lettres, une erreur suffit a en faire un autre mot.
LONGUEUR_MIN = 4


@dataclass(frozen=True)
class Terme:
    """Un mot du vocabulaire personnel, et d'ou il vient."""

    mot: str
    source: str = "appris"      # declare | memoire | appris
    occurrences: int = 1

    @property
    def poids(self) -> float:
        """Confiance intrinseque du terme, de 0 a 1.

        Un terme declare a la main vaut mieux qu'un terme deduit ; un terme
        confirme dix fois vaut mieux qu'un terme confirme une fois. La
        progression est volontairement lente et bornee : on ne veut pas qu'un
        terme frequent ecrase tous les autres.
        """
        base = {"declare": 1.0, "memoire": 0.9, "appris": 0.75}.get(self.source, 0.7)
        return min(1.0, base + 0.02 * min(self.occurrences - 1, 10))


@dataclass(frozen=True)
class Proposition:
    """Une correction possible, avec de quoi decider quoi en faire."""

    entendu: str
    propose: str
    confiance: float
    terme: Terme

    @property
    def certaine(self) -> bool:
        """Assez sure pour corriger sans demander."""
        return self.confiance >= SEUIL_CERTITUDE


class Lexique:
    """Le vocabulaire personnel, indexe par le son.

    Ne touche ni a la base, ni aux fichiers : on l'alimente depuis
    l'exterieur. C'est ce qui le rend testable en trois lignes et
    independant de la facon dont Nova stocke sa memoire — qui changera.
    """

    def __init__(self) -> None:
        self._termes: dict[str, Terme] = {}
        self._index: dict[str, list[Terme]] = {}
        self._index_perime = False

    # -- alimentation ------------------------------------------------------

    def ajouter(self, mot: str, source: str = "appris") -> Terme | None:
        """Ajoute ou renforce un terme. `None` si le mot est inexploitable.

        Un mot deja present voit ses occurrences augmenter, et sa source
        s'ameliorer si la nouvelle est meilleure : un terme appris qui est
        ensuite declare a la main devient declare.
        """
        propre = mot.strip(" .,;:!?«»\"'()")
        if len(propre) < LONGUEUR_MIN or not any(c.isalpha() for c in propre):
            return None

        clef = propre.lower()
        rangs = {"declare": 3, "memoire": 2, "appris": 1}
        if ancien := self._termes.get(clef):
            garde_ancienne = rangs.get(ancien.source, 0) >= rangs.get(source, 0)
            meilleure = ancien.source if garde_ancienne else source
            terme = replace(ancien, occurrences=ancien.occurrences + 1, source=meilleure)
        else:
            terme = Terme(mot=propre, source=source)

        self._termes[clef] = terme
        # On NE reindexe PAS ici. Charger trois cents termes appelait
        # `_reindexer` trois cents fois, soit un travail quadratique paye a
        # chaque phrase dictee. On note simplement que l'index est perime ; il
        # sera reconstruit une seule fois, a la premiere recherche.
        self._index_perime = True
        return terme

    def ajouter_tous(self, mots: list[str], source: str = "appris") -> int:
        """Ajoute une liste. Retourne le nombre de termes reellement retenus."""
        retenus = 0
        for mot in mots:
            if self.ajouter(mot, source) is not None:
                retenus += 1
        return retenus

    def _reindexer(self) -> None:
        """Reconstruit l'index phonetique, si et seulement s'il a change.

        Reconstruire entierement plutot que mettre a jour : quelques centaines
        de termes, donc quelques millisecondes, contre une classe de bugs
        d'index desynchronise en moins. Le bon compromis a cette echelle — a
        condition de ne le faire qu'UNE fois par lot d'ajouts, d'ou le drapeau.
        """
        if not self._index_perime:
            return
        self._index = {}
        for terme in self._termes.values():
            self._index.setdefault(phonetique.coder(terme.mot), []).append(terme)
        self._index_perime = False

    # -- consultation ------------------------------------------------------

    def __len__(self) -> int:
        return len(self._termes)

    def __contains__(self, mot: object) -> bool:
        return isinstance(mot, str) and mot.lower() in self._termes

    def termes(self) -> tuple[Terme, ...]:
        """Du plus confirme au moins confirme — l'ordre d'injection dans l'amorce."""
        return tuple(sorted(self._termes.values(), key=lambda t: -t.poids))

    def mots(self) -> tuple[str, ...]:
        return tuple(t.mot for t in self.termes())

    # -- correction --------------------------------------------------------

    @staticmethod
    def _fragment_valide(fragment: str) -> bool:
        """Un fragment ne doit pas se terminer par de la ponctuation seule.

        Sans cette garde, « Discord ? » etait reconnu comme « Discord » — le
        code phonetique de « ? » etant vide — et la correction AVALAIT le
        point d'interrogation. Un fragment de plusieurs mots peut ainsi
        supprimer de la ponctuation sans que rien ne le signale.
        """
        mots = fragment.split()
        return bool(mots) and any(c.isalpha() for c in mots[-1])

    def chercher(self, fragment: str) -> Proposition | None:
        """Le terme du lexique qui sonne comme ce fragment, s'il existe.

        La confiance combine la ressemblance PHONETIQUE et le poids du terme :
        un terme declare a la main l'emporte sur un terme appris une fois, a
        ressemblance egale. C'est ce qui fait qu'un vocabulaire soigne donne de
        meilleurs resultats qu'un vocabulaire subi.
        """
        if not fragment or len(fragment.strip()) < LONGUEUR_MIN:
            return None

        code = phonetique.coder(fragment)
        if not code:
            return None

        self._reindexer()   # sans effet si rien n'a change depuis la derniere fois

        # Correspondance exacte du code : le cas le plus frequent et le plus sur.
        if exacts := self._index.get(code):
            meilleur = max(exacts, key=lambda t: t.poids)
            confiance = min(1.0, 0.96 + 0.04 * meilleur.poids)
            return Proposition(fragment, meilleur.mot, confiance, meilleur)

        meilleure: Proposition | None = None
        for terme in self._termes.values():
            proximite = phonetique.ressemblance(fragment, terme.mot)
            if proximite < SEUIL_PROPOSITION:
                continue
            # Le poids du terme module la confiance, sans jamais la creer :
            # un terme tres confirme mais phonetiquement lointain reste ecarte.
            confiance = proximite * (0.85 + 0.15 * terme.poids)
            if meilleure is None or confiance > meilleure.confiance:
                meilleure = Proposition(fragment, terme.mot, confiance, terme)
        return meilleure

    def corriger(self, texte: str, taille_max: int = 3) -> tuple[str, tuple[Proposition, ...]]:
        """Corrige les fragments qui correspondent a un terme du lexique.

        On essaie des groupes de plusieurs mots, du plus long au plus court :
        « aux lamas » ne se trouve qu'en regardant DEUX mots ensemble. C'est
        precisement la ou une correction mot a mot echoue, et c'est le cas le
        plus frequent des erreurs de Whisper sur les noms propres.

        Seules les corrections CERTAINES sont appliquees ici. Les autres sont
        rendues a l'appelant, qui decidera s'il demande confirmation.
        """
        mots = texte.split()
        if not mots:
            return texte, ()

        appliquees: list[Proposition] = []
        sortie: list[str] = []
        i = 0
        while i < len(mots):
            trouve = False
            # Du plus long au plus court : « aux lamas » avant « aux ».
            for taille in range(min(taille_max, len(mots) - i), 0, -1):
                fragment = " ".join(mots[i : i + taille])
                if not self._fragment_valide(fragment):
                    continue
                proposition = self.chercher(fragment)
                if proposition is None or not proposition.certaine:
                    continue
                # Un fragment deja identique au terme n'est pas une correction.
                if fragment.lower() == proposition.propose.lower():
                    continue
                sortie.append(proposition.propose)
                appliquees.append(proposition)
                i += taille
                trouve = True
                break
            if not trouve:
                sortie.append(mots[i])
                i += 1

        return " ".join(sortie), tuple(appliquees)

    def suggestions(self, texte: str, taille_max: int = 3) -> tuple[Proposition, ...]:
        """Les corrections POSSIBLES mais pas certaines.

        Servent a formuler « as-tu dit… ? ». Les rendre plutot que les
        appliquer est tout l'objet de la regle : ne jamais deviner en dessous
        du seuil de certitude.
        """
        mots = texte.split()
        proposees: list[Proposition] = []
        for i in range(len(mots)):
            for taille in range(min(taille_max, len(mots) - i), 0, -1):
                fragment = " ".join(mots[i : i + taille])
                if not self._fragment_valide(fragment):
                    continue
                proposition = self.chercher(fragment)
                if (
                    proposition is not None
                    and not proposition.certaine
                    and fragment.lower() != proposition.propose.lower()
                ):
                    proposees.append(proposition)
                    break
        return tuple(proposees)
