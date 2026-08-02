"""Le pipeline de comprehension : de la transcription brute a une demande sure.

    micro -> STT -> nettoyage -> correction -> intention -> validation -> LLM

Ce module est l'ASSEMBLAGE. Chaque etage vit dans son fichier et se teste
seul ; ici on les enchaine, on additionne les incertitudes, et on decide quoi
en faire. C'est le seul endroit du pipeline vocal qui ait le droit de decider.

LA REGLE QUI GOUVERNE TOUT

    Ne jamais deviner. Corriger quand on est sur, demander quand on ne l'est
    pas, et ne rien toucher quand la phrase est deja correcte.

Elle a une consequence qu'il faut assumer : Nova demandera parfois de
repeter. C'est voulu. Un assistant qui repond a cote sans le savoir est bien
pire qu'un assistant qui demande — le premier fait perdre confiance, le
second en inspire.

D'OU VIENT LA CONFIANCE

Trois sources, multipliees. Une seule faible suffit a faire douter, ce qui
est le comportement voulu :

    acoustique   ce que Whisper pense de son propre travail (`avg_logprob`)
    lexicale     les corrections ont-elles ete surs ou approximatives
    structurelle la phrase a-t-elle une forme comprehensible

La premiere est disponible depuis toujours et etait JETEE. C'est la plus
honnete des trois : c'est le modele lui-meme qui dit qu'il a doute.

CE QUE CE MODULE NE FAIT PAS, ET NE FERA PAS

Il ne reconstruit pas une phrase francaise arbitraire. « sur quelle planete
pour lui en ouvrir » -> « sur quelle planete pourrions-nous vivre » demande un
modele de langue, pas un lexique : « pourrions-nous vivre » n'est pas un terme
rare, c'est du francais ordinaire.

Ce que ce module fait dans ce cas, et qui vaut mieux que d'y repondre a
l'aveugle : il DETECTE que la phrase est douteuse, et demande.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nova.logging_setup import get_logger
from nova.voice import intentions, nettoyage
from nova.voice.intentions import Intention
from nova.voice.lexique import Lexique, Proposition

log = get_logger(__name__)

#: Au-dessus, on transmet la demande sans rien demander.
SEUIL_SUR = 0.80

#: En dessous, on ne transmet rien : on demande de repeter. Entre les deux,
#: on propose une reformulation a confirmer.
SEUIL_DOUTEUX = 0.55

#: `avg_logprob` de Whisper : 0 = parfait, -1 = tres incertain. La conversion
#: en probabilite est grossiere et suffit — on cherche un signal, pas une
#: mesure. -0,35 est le seuil ou, en pratique, la transcription commence a
#: contenir des mots inventes.
LOGPROB_BON = -0.20
LOGPROB_MAUVAIS = -0.90


@dataclass(frozen=True)
class Comprehension:
    """Ce que Nova a compris, et a quel point elle en est sure."""

    texte: str                      # la version retenue, corrigee
    origine: str                    # la transcription brute
    confiance: float
    intention: Intention
    corrections: tuple[Proposition, ...] = ()
    suggestions: tuple[Proposition, ...] = ()
    retires: tuple[str, ...] = ()
    #: Pourquoi cette confiance. Sans ca, un doute est indebogable.
    raisons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def sure(self) -> bool:
        return self.confiance >= SEUIL_SUR

    @property
    def a_confirmer(self) -> bool:
        return SEUIL_DOUTEUX <= self.confiance < SEUIL_SUR

    @property
    def incomprise(self) -> bool:
        return self.confiance < SEUIL_DOUTEUX

    def question(self) -> str:
        """La demande de confirmation a prononcer, si elle est necessaire.

        Formulee comme un humain le ferait : on propose ce qu'on a cru
        entendre plutot que d'annoncer un echec. « As-tu dit… ? » invite a
        confirmer d'un mot ; « je n'ai pas compris » oblige a tout repeter.
        """
        if self.incomprise:
            return "Je n'ai pas bien saisi. Tu peux répéter ?"
        propose = self.texte
        for suggestion in self.suggestions:
            propose = propose.replace(suggestion.entendu, suggestion.propose)
        return f"As-tu dit : {propose} ?"


def _confiance_acoustique(logprob: float | None) -> tuple[float, str | None]:
    """Ce que Whisper pense de son propre travail.

    Disponible depuis toujours dans `faster-whisper` et jete jusqu'ici. C'est
    pourtant le signal le plus honnete : le modele dit lui-meme qu'il a hesite.
    """
    if logprob is None:
        return 1.0, None   # information absente : on ne penalise pas
    if logprob >= LOGPROB_BON:
        return 1.0, None
    if logprob <= LOGPROB_MAUVAIS:
        return 0.35, f"transcription incertaine (logprob {logprob:.2f})"
    # Interpolation lineaire entre les deux bornes.
    etendue = LOGPROB_BON - LOGPROB_MAUVAIS
    part = (logprob - LOGPROB_MAUVAIS) / etendue
    return 0.35 + 0.65 * part, f"transcription moyennement sure (logprob {logprob:.2f})"


def _confiance_structurelle(texte: str) -> tuple[float, str | None]:
    """La phrase a-t-elle une forme comprehensible ?

    Deux signaux grossiers mais utiles : une phrase d'un seul mot n'est pas
    forcement une demande, et une phrase ou presque tous les mots font moins
    de trois lettres n'est generalement pas du francais mais un decoupage
    rate — c'est exactement ce que produit Whisper quand il perd le fil.
    """
    mots = texte.split()
    if not mots:
        return 0.0, "aucun mot"
    if len(mots) == 1:
        return 0.85, None   # « oui », « stop » sont des demandes valides
    courts = sum(1 for m in mots if len(m.strip(" ,.!?;:")) <= 2)
    if courts / len(mots) > 0.6:
        return 0.45, "beaucoup de mots tres courts : decoupage probablement rate"
    return 1.0, None


def comprendre(
    transcription: str,
    *,
    lexique: Lexique | None = None,
    logprob: float | None = None,
) -> Comprehension:
    """Le pipeline complet. Ne leve jamais.

    `lexique` est INJECTE : ce module ne sait pas d'ou vient le vocabulaire
    personnel — memoire, fichier de configuration, apprentissage. C'est ce qui
    le rend testable sans base de donnees, et ce qui permettra de changer le
    stockage sans y toucher.
    """
    origine = transcription or ""
    raisons: list[str] = []

    # 1. NETTOYAGE — sur, jamais un pari.
    propre = nettoyage.nettoyer(origine)
    if propre.retires:
        raisons.append(f"nettoyé : {', '.join(propre.retires)}")

    if not propre.texte:
        return Comprehension(
            texte="", origine=origine, confiance=0.0,
            intention=intentions.AUCUNE,
            raisons=("rien à comprendre",),
        )

    # 2. CORRECTION — uniquement ce dont on est certain.
    texte = propre.texte
    corrections: tuple[Proposition, ...] = ()
    suggestions: tuple[Proposition, ...] = ()
    confiance_lexicale = 1.0
    if lexique is not None and len(lexique):
        texte, corrections = lexique.corriger(texte)
        suggestions = lexique.suggestions(texte)
        if corrections:
            raisons.append(
                "corrigé : " + ", ".join(f"« {c.entendu} » → « {c.propose} »" for c in corrections)
            )
        if suggestions:
            # Une suggestion NON APPLIQUEE est un doute qu'on n'a pas leve.
            #
            # Attention au contresens : la confiance de la suggestion mesure
            # la qualite de la CORRECTION, pas celle de la phrase. Une
            # suggestion a 0,86 signifie « je crois assez fort qu'il faut
            # corriger » — donc que la phrase actuelle est probablement
            # fausse. La reprendre telle quelle rendait la phrase « sure »
            # justement quand il fallait demander.
            #
            # On plafonne donc explicitement sous le seuil : tant qu'un doute
            # n'est pas leve, la demande passe par une confirmation.
            confiance_lexicale = SEUIL_SUR - 0.05
            raisons.append(
                "hésitation : " + ", ".join(f"« {s.entendu} » ?" for s in suggestions)
            )

    # 3. INTENTION — ce que la personne veut.
    intention = intentions.reconnaitre(texte)
    if intention.reconnue:
        raisons.append(f"intention {intention.nom}")

    # 4. CONFIANCE — le produit des trois, jamais leur moyenne.
    #    Une moyenne laisserait un signal fort masquer un signal faible ; or
    #    un seul doute serieux suffit a rendre la demande incertaine.
    acoustique, raison_acoustique = _confiance_acoustique(logprob)
    structurelle, raison_structurelle = _confiance_structurelle(texte)
    for raison in (raison_acoustique, raison_structurelle):
        if raison:
            raisons.append(raison)

    confiance = acoustique * structurelle * confiance_lexicale

    # Une intention clairement reconnue est un signal fort de comprehension :
    # « ouvre Discord » ne veut rien dire d'autre, meme mal transcrit.
    if intention.reconnue and intention.confiance >= 0.9:
        confiance = min(1.0, confiance + 0.15)
        raisons.append("intention nette : confiance relevée")

    return Comprehension(
        texte=texte,
        origine=origine,
        confiance=round(confiance, 3),
        intention=intention,
        corrections=corrections,
        suggestions=suggestions,
        retires=propre.retires,
        raisons=tuple(raisons),
    )
