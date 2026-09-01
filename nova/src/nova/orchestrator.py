"""Le coeur de Nova : assembler le contexte, puis interroger le modele.

C'est le seul module autorise a connaitre tous les autres. Tout le reste
respecte la regle de dependance :

    api -> orchestrator -> memory / documents / llm -> db

Ce que fait l'orchestrateur, dans l'ordre :
  1. charge l'identite de Nova (config/prompts/identity.md)
  2. y ajoute les faits confirmes te concernant     <- la memoire
  3. cherche des extraits pertinents                <- les documents
  4. assemble le message systeme
  5. appelle le modele en flux
  6. journalise l'echange

Choix de conception V1 : c'est NOTRE code qui decide de chercher, pas le modele.
C'est deterministe, debogable et previsible. L'appel d'outils par le modele
(MCP) s'ajoutera en V0.3 par-dessus cette base, sans la remplacer.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from nova import prompts
from nova.core import chrono
from nova.core.contrats import Demande, Plan
from nova.core.planificateur import planifier
from nova.core.routeur import Routeur
from nova.documents import search as document_search
from nova.llm.client import Message
from nova.logging_setup import get_logger
from nova.memory import conversations, facts, reprise
from nova.memory.models import SearchHit
from nova.modeles import routage
from nova.settings import get_settings, get_tuning
from nova.voice import vocabulaire

if TYPE_CHECKING:
    # Importes UNIQUEMENT pour les annotations. A l'execution, ces modules
    # sont charges tard, dans les fonctions qui s'en servent : la couche voix
    # est facultative, et Nova doit demarrer sans elle.
    from nova.voice import comprehension as voice_comprehension
    from nova.voice import lexique as voice_lexique

log = get_logger(__name__)

# En dessous, la question ne porte pas assez d'information pour qu'une recherche
# documentaire soit utile ("ok", "merci", "et ensuite ?").
MIN_QUERY_LENGTH = 12

# Noms francais ecrits en dur plutot que via la locale du systeme : `strftime`
# renvoie « Saturday » sur une machine configuree en anglais, et Nova annoncerait
# la date en anglais sans que personne ne comprenne pourquoi.
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS = (
    "janvier",
    "fevrier",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "aout",
    "septembre",
    "octobre",
    "novembre",
    "decembre",
)


# ══════════════════════════════════════════════════════════════════════════
#  LE NOYAU, VU DEPUIS L'ORCHESTRATEUR
#
#  `core` ne connait ni la base, ni le moteur, ni l'interface : il ne
#  manipule que des descriptions et des decisions. C'est l'orchestrateur qui
#  lui fournit la matiere et qui execute ce qu'il decide. La fleche ne
#  remonte jamais.
#
#  L'integration est volontairement OBSERVABLE avant d'etre agissante : le
#  plan est calcule et journalise, la reponse continue de passer par le
#  chemin eprouve. Brancher l'execution des agents le meme jour aurait mis en
#  jeu tout ce qui fonctionne pour une capacite que rien n'attend encore.
# ══════════════════════════════════════════════════════════════════════════


def routeur() -> Routeur:
    """Le catalogue des modeles, tel que les fournisseurs le declarent.

    ⚠️ CETTE FONCTION DECLARAIT SA PROPRE LISTE, ET C'ETAIT UN DOUBLON.

    Elle construisait un `Modele` a la main — nom, capacites, vitesse, poids —
    exactement comme le fait maintenant `modeles/local.py`. Deux descriptions
    du meme modele dans deux fichiers auraient diverge a la premiere
    correction : l'une saurait que le modele fait du code, l'autre non, et
    personne ne verrait laquelle est lue.

    C'est le meme raisonnement que `trouver._signal_fichier`, qui deduit son
    vocabulaire de `requete.PAPIERS` au lieu de le recopier a cote.

    Les capacites et la vitesse continuent de venir de `.env`, donc de la
    MESURE faite par `scripts/bench_models.py`, jamais d'une reputation.
    """
    from nova.modeles.catalogue import routeur as catalogue

    return catalogue()


def analyser(texte: str) -> tuple[Plan, str | None]:
    """Le plan de Nova et l'espace de travail concerne, sans rien executer.

    Ne fait AUCUN appel au modele : le planificateur deterministe suffit pour
    les familles connues, et le reste est une phrase a laquelle on repond.
    C'est ce qui permet d'appeler cette fonction a chaque demande sans en
    payer le prix.
    """
    from nova.espaces import choisir_espace  # tard : evite un cycle a l'import

    demande = Demande(texte=texte)
    plan = planifier(demande)
    espace = choisir_espace(demande)
    nom_espace = espace.nom if espace else None

    if not plan.direct:
        log.info(
            "Plan (%s) — %d etapes%s : %s",
            plan.origine,
            len(plan.etapes),
            f", espace « {nom_espace} »" if nom_espace else "",
            " → ".join(e.intitule for e in plan.etapes),
        )
    return plan, nom_espace


#: Duree de vie du vocabulaire deduit de la memoire, en secondes.
#:
#: POURQUOI UN CACHE, ET POURQUOI COURT
#:
#: Chaque phrase dictee declenchait DEUX lectures de la memoire — une pour
#: l'amorce de transcription, une pour le lexique de correction — avant meme
#: que Whisper ne commence. Sur une base distante ou indisponible, c'est du
#: temps d'attente pur, paye a chaque mot prononce.
#:
#: Les faits confirmes changent quelques fois par jour ; le vocabulaire qu'on
#: en tire, encore moins. Une minute de cache supprime la quasi-totalite de ces
#: lectures et retarde d'au plus une minute la prise en compte d'un nom
#: nouveau — un delai qu'aucun usage ne remarque. `oublier_le_vocabulaire()`
#: est la pour les cas ou on ne veut pas attendre du tout.
DUREE_CACHE_VOCABULAIRE = 60.0

#: (instant de calcul, termes, bloc memoire). Volontairement un simple tuple
#: protege par un verrou plutot qu'un `lru_cache` : il faut pouvoir
#: l'invalider a la demande.
#:
#: ⚠️ LE BLOC MEMOIRE EST ICI PARCE QU'IL VIENT DE LA MEME LECTURE.
#:
#: `facts.render_for_prompt()` refaisait sa propre requete `list_facts` a
#: CHAQUE question, en bloquant, pour des donnees qui changent quelques fois
#: par jour. Deux allers-retours en base par question la ou un seul, mis en
#: cache, suffit — et surtout : cette lecture-la etait sur le chemin critique
#: de la parole. Le meme defaut avait deja ete corrige pour le vocabulaire,
#: avec la mesure qui va avec : « base injoignable, 30 secondes avant la
#: premiere transcription ». Le bloc memoire y etait reste exposé.
_vocabulaire_cache: tuple[float, tuple[str, ...], str] | None = None
_verrou_vocabulaire = threading.Lock()

#: Empeche dix requetes simultanees de lancer dix relectures de la base.
_rafraichissement_en_cours = False
_verrou_demande = threading.Lock()


def rafraichir_le_vocabulaire() -> tuple[str, ...]:
    """Relit la memoire MAINTENANT, en bloquant. Ne leve jamais.

    Appele par le fil d'entretien, jamais depuis une requete : c'est ici que
    l'attente est acceptable, parce que personne ne la subit.
    """
    global _vocabulaire_cache

    with _verrou_vocabulaire:
        termes: tuple[str, ...] = ()
        bloc = ""
        try:
            confirmes = facts.list_facts(status="confirmed")
        except Exception as exc:  # noqa: BLE001
            # Memoire indisponible : vocabulaire vide, donc une transcription
            # moins fine sur les noms propres. Jamais une panne.
            log.warning("Memoire indisponible : %s", exc)
            _vocabulaire_cache = (time.monotonic(), termes, bloc)
            return termes

        # ⚠️ LES DEUX PRODUITS SONT CALCULES SEPAREMENT, ET C'EST VOULU.
        #
        # Une premiere version les enveloppait dans le meme `try`. Un echec du
        # rendu effacait alors AUSSI le vocabulaire — deux capacites
        # independantes tombant ensemble parce qu'elles partageaient une
        # accolade. Le banc du cache l'a attrape, en montrant un lexique vide
        # pour une raison qui n'avait rien a voir avec lui.
        try:
            termes = tuple(vocabulaire.extraire_termes([f.content for f in confirmes]))
        except Exception as exc:  # noqa: BLE001
            log.warning("Vocabulaire non extrait de la memoire : %s", exc)
        try:
            # La MEME liste : deux consommateurs, une seule requete.
            bloc = facts.render_for_prompt(confirmes)
        except Exception as exc:  # noqa: BLE001
            log.warning("Bloc memoire non rendu : %s", exc)

        _vocabulaire_cache = (time.monotonic(), termes, bloc)
        return termes


def _termes_de_la_memoire() -> tuple[str, ...]:
    """Le vocabulaire connu, SANS JAMAIS ATTENDRE.

    ⚠️ CETTE FONCTION EST DANS LE CHEMIN VOCAL. ELLE NE DOIT RIEN BLOQUER.

    Elle lisait la base directement. Tant que la base repond en dix
    millisecondes, personne ne le voit. Le jour ou elle tarde — reveil de
    veille, disque occupe, service arrete — c'est la PAROLE de Nova qui
    attend. Mesure avec une base injoignable : 30 secondes avant la premiere
    transcription, pour un enrichissement facultatif.

    Un travail previsible doit se faire pendant que personne ne regarde. On
    rend donc ce qu'on a, et on demande une relecture EN FOND si c'est vieux.
    Le pire cas devient « Nova entend un peu moins bien les noms propres
    pendant une minute », au lieu de « Nova ne repond pas ».
    """
    cache = _vocabulaire_cache
    if cache is None:
        # Rien encore : on demande une lecture de fond et on repond tout de
        # suite. La toute premiere phrase perd les noms propres ; le
        # prechauffage au demarrage fait que ce cas n'arrive quasiment jamais.
        _demander_un_rafraichissement()
        return ()

    if time.monotonic() - cache[0] >= DUREE_CACHE_VOCABULAIRE:
        _demander_un_rafraichissement()
    return cache[1]


def _bloc_memoire() -> str:
    """Les faits confirmes, prets pour le prompt, SANS attendre la base.

    ⚠️ LE CACHE FROID SE LIT EN BLOQUANT, ET C'EST DELIBERE.

    Pour le vocabulaire, un cache vide se contente de rendre () : Nova entend
    un peu moins bien les noms propres pendant une minute. Ici la degradation
    ne serait pas du meme ordre — un bloc vide, c'est Nova qui repond a la
    premiere question sans se souvenir de qui tu es. Une perte de memoire ne
    s'echange pas contre dix millisecondes.

    On ne paie donc l'attente qu'une fois, au tout premier appel, et encore :
    le fil d'entretien amorce le cache au demarrage, avant que quiconque ait
    parle. Les appels suivants sont servis instantanement et la relecture se
    fait derriere.
    """
    cache = _vocabulaire_cache
    if cache is None:
        rafraichir_le_vocabulaire()
        cache = _vocabulaire_cache
        if cache is None:  # la lecture a echoue : pas de memoire, pas de panne
            return ""

    if time.monotonic() - cache[0] >= DUREE_CACHE_VOCABULAIRE:
        _demander_un_rafraichissement()
    return cache[2]


def _demander_un_rafraichissement() -> None:
    """Lance une relecture en fond, sauf s'il y en a deja une."""
    global _rafraichissement_en_cours

    with _verrou_demande:
        if _rafraichissement_en_cours:
            return
        _rafraichissement_en_cours = True

    def travailler() -> None:
        global _rafraichissement_en_cours
        try:
            rafraichir_le_vocabulaire()
        finally:
            with _verrou_demande:
                _rafraichissement_en_cours = False

    threading.Thread(target=travailler, name="nova-vocabulaire", daemon=True).start()


def oublier_le_vocabulaire() -> None:
    """Le vocabulaire a change : on le relit, en fond, tout de suite.

    A appeler quand un fait vient d'etre confirme. La relecture est lancee
    immediatement plutot qu'a la prochaine phrase : entre le moment ou tu
    confirmes un fait et celui ou tu prononces le nom qu'il contient, il
    s'ecoule des secondes — largement de quoi la terminer sans que personne
    n'attende.
    """
    global _vocabulaire_cache
    _vocabulaire_cache = None
    _demander_un_rafraichissement()


def lexique_personnel() -> voice_lexique.Lexique:
    """Le vocabulaire personnel de Nova, assemble depuis ses trois sources.

    C'EST ICI PAR RESPECT DE LA REGLE DE DEPENDANCE

    `voice/lexique.py` sait indexer et comparer des mots ; il ne sait pas d'ou
    ils viennent, et c'est ce qui le rend testable en trois lignes. Aller les
    chercher dans les reglages puis dans la memoire est le travail de
    l'orchestrateur, seul module autorise a connaitre les autres.

    Trois sources, par ordre de confiance decroissante :

        declare   NOVA_WHISPER_VOCABULAIRE, ecrit a la main
        memoire   noms propres des faits confirmes
        appris    corrections que tu as confirmees (a venir)

    L'ordre compte : un terme declare a la main l'emporte sur un terme deduit,
    a ressemblance phonetique egale.
    """
    from nova.voice import lexique as voice_lexique

    lex = voice_lexique.Lexique()
    reglages = get_settings()

    if declares := reglages.whisper_vocabulaire.strip():
        lex.ajouter_tous([t.strip() for t in declares.split(",") if t.strip()], "declare")

    lex.ajouter_tous(list(_termes_de_la_memoire()), "memoire")
    return lex


def comprendre_la_parole(transcription) -> voice_comprehension.Comprehension:
    """Transforme une transcription brute en demande sure — ou en question.

    Assemble le pipeline complet : nettoyage, correction lexicale, intention,
    puis la decision d'agir, de demander confirmation, ou de faire repeter.

    Ne leve jamais : une comprehension qui echoue rendrait Nova muette, alors
    qu'une comprehension degradee la rend seulement moins fine.
    """
    from nova.voice import comprehension as voice_comprehension

    texte = getattr(transcription, "texte", transcription) or ""
    logprob = getattr(transcription, "logprob", None)

    try:
        comprise = voice_comprehension.comprendre(
            texte, lexique=lexique_personnel(), logprob=logprob
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Comprehension indisponible, texte brut conserve : %s", exc)
        from nova.voice.intentions import AUCUNE

        return voice_comprehension.Comprehension(
            texte=texte, origine=texte, confiance=1.0, intention=AUCUNE,
        )

    niveau = "sûre" if comprise.sure else ("à confirmer" if comprise.a_confirmer else "incomprise")
    log.info(
        "Parole %s (%.2f) : « %s »%s",
        niveau,
        comprise.confiance,
        comprise.texte,
        f" — {' · '.join(comprise.raisons)}" if comprise.raisons else "",
    )
    return comprise


def amorce_dictee() -> str:
    """L'amorce de transcription, enrichie des noms propres que Nova connait.

    C'EST ICI ET PAS DANS `voice/` PAR RESPECT DE LA REGLE DE DEPENDANCE

    `voice/vocabulaire.py` ne connait rien du projet : il transforme des
    phrases en termes. Aller chercher ces phrases dans la memoire est le
    travail de l'orchestrateur, seul module autorise a connaitre les autres.
    Sans ca, la couche voix dependrait de la couche memoire et la fleche
    remonterait.

    POURQUOI CA MARCHE

    Whisper se trompe sur ce qui est rare dans la langue — les noms propres.
    Releve en conditions reelles : « pinata » entendu « pierre pienita ».
    Une amorce contenant le mot le fait reconnaitre ; le meme mot absent est
    massacre, quelle que soit la taille du modele.

    Or les noms que l'utilisateur prononce sont exactement ceux que Nova a
    deja en memoire. Plus elle te connait, mieux elle t'entend.
    """
    reglages = get_settings()
    base = reglages.whisper_amorce_dictee

    termes: list[str] = []
    # Le vocabulaire declare a la main passe en premier : c'est un choix
    # explicite de l'utilisateur, il ne doit pas etre evince par la memoire.
    if declares := reglages.whisper_vocabulaire.strip():
        termes.extend(t.strip() for t in declares.split(",") if t.strip())

    # Meme source, meme cache que le lexique de correction : les deux etages
    # de la chaine vocale lisent desormais la memoire une fois pour deux.
    termes.extend(_termes_de_la_memoire())

    return vocabulaire.construire_amorce(base, termes)


#: Ce qui fait entrer l'horloge dans le prompt.
#:
#: ⚠️ CETTE LISTE PENCHE VOLONTAIREMENT DU COTE DE L'INCLUSION.
#:
#: Les deux erreurs ne coutent pas la meme chose. Garder le bloc pour rien
#: produit une reponse a cote, agacante et visible. Le retirer a tort fait
#: INVENTER une heure, avec aplomb — et « quelle heure est-il » est la
#: premiere question que tout le monde pose a un assistant vocal, donc le
#: premier endroit ou il perd la confiance de son utilisateur.
#:
#: Dans le doute, le bloc reste. On n'ecarte que ce qui ne parle visiblement
#: pas de temps.
_QUESTION_DE_TEMPS = re.compile(
    r"\b(?:"
    r"heures?|heure|minutes?|secondes?|"
    r"date|dates|jour|jours|journee|semaine|semaines|mois|annee|annees|an|ans|"
    r"aujourd hui|demain|hier|avant hier|apres demain|"
    r"matin|matinee|midi|apres midi|soir|soiree|minuit|nuit|"
    r"maintenant|actuellement|en ce moment|tout a l heure|"
    r"quand|quelle? heure|combien de temps|depuis|jusqu a|d ici|"
    # « on est le combien » : une demande de date qui ne porte aucun des mots
    # attendus. Le motif entier, parce que « combien » seul attraperait
    # « combien ca coute ».
    r"on est le combien|le combien sommes nous|quantieme|"
    r"tot|tard|retard|avance|calendrier|agenda|rendez vous|anniversaire|"
    r"lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|"
    r"janvier|fevrier|mars|avril|mai|juin|juillet|"
    r"aout|septembre|octobre|novembre|decembre|"
    # ⚠️ « TEMPS » Y FIGURE, ET C'EST LUI QUI A CAUSE LE DEFAUT.
    #
    # « reparer le temps » parlait de physique, pas d'horloge. Mais « il fait
    # quel temps » et « combien de temps » sont des demandes legitimes, et le
    # mot est trop courant pour etre ecarte sans casser le cas normal. Il
    # reste : la phrase qui a echoue — « pourrais-tu faire ces calculs ? » —
    # ne le contient pas, et c'est elle qu'il fallait laisser passer.
    r"temps"
    r")\b"
)


def _question_de_temps(texte: str) -> bool:
    """Cette phrase a-t-elle besoin de savoir l'heure qu'il est ?"""
    if not texte:
        return False
    from nova.fichiers.requete import sans_accents

    # ⚠️ APOSTROPHES ET TIRETS DEVIENNENT DES ESPACES.
    #
    # Sans cela, « aujourd'hui » et « sommes-nous » ne correspondent a aucun
    # motif : le tiret et l'apostrophe collent les mots. C'est exactement le
    # meme aplatissement que `requete._normaliser` et `session._plat` — trois
    # endroits qui recoivent de la parole transcrite, et la meme regle.
    plat = re.sub(r"[^a-z0-9]+", " ", sans_accents(texte).lower())
    return bool(_QUESTION_DE_TEMPS.search(plat))


def instant_present(maintenant: datetime | None = None) -> str:
    """Date et heure, en francais, pour le prompt systeme."""
    maintenant = maintenant or datetime.now().astimezone()
    return (
        f"{JOURS[maintenant.weekday()]} {maintenant.day} "
        f"{MOIS[maintenant.month - 1]} {maintenant.year}, il est "
        f"{maintenant.strftime('%H:%M')}"
    )


def _format_sources(hits: list[SearchHit], budget: int | None = None) -> str:
    """Met les extraits en forme pour le prompt, dans un budget de caracteres.

    Chaque extrait est explicitement etiquete par sa source afin que le modele
    puisse citer. Sans cette etiquette, il invente les references — c'est
    systematique.

    POURQUOI UN BUDGET, ET PAS SEULEMENT UN NOMBRE D'EXTRAITS

    Exactement la meme raison que pour la memoire (R13), et le meme defaut
    trouve au meme endroit : borner le NOMBRE ne borne pas la TAILLE, et le
    temps de lecture d'un modele local est proportionnel a la taille.

    Mesure en conditions reelles, pour « Dis bonjour en une phrase » :

        identite 1495 + memoire 260 + instant 183 + documents 4825
        -> prompt 6805 car. -> premier mot 10,4 s

    Les documents pesaient 71 % du prompt, sur une demande qui n'en appelait
    aucun. Les extraits arrivent deja classes par pertinence : couper par la
    fin sacrifie donc les moins utiles.
    """
    budget = get_tuning().extraits_budget if budget is None else budget
    blocks: list[str] = []
    total = 0
    for hit in hits:
        label = hit.heading or "sans titre"
        bloc = f'--- [{hit.document_title}, "{label}"]\n{hit.content}'
        if total + len(bloc) > budget:
            # On saute plutot que d'arreter : un extrait anormalement long ne
            # doit pas faire taire les suivants, qui tiendraient tres bien.
            continue
        blocks.append(bloc)
        total += len(bloc)

    if len(blocks) < len(hits):
        log.info(
            "Documents : %d extraits sur %d injectes (budget %d caracteres). "
            "Au-dela, chaque caractere ajoute ~1,5 ms d'attente a CHAQUE question.",
            len(blocks), len(hits), budget,
        )
    return "\n\n".join(blocks)


def build_system_prompt(
    user_message: str, *, mode: str = "normal", contrat: str | None = None
) -> tuple[str, list[SearchHit]]:
    """Construit le message systeme complet. Retourne aussi les sources utilisees.

    Renvoyer les sources permet de les journaliser et, plus tard, de les
    afficher dans l'interface : une reponse verifiable est une reponse a
    laquelle on peut faire confiance.
    """
    # `contrat` : consigne imposee par une application cliente (format de sortie,
    # role attendu). On la RESPECTE au lieu de la remplacer.
    #
    # Nuance importante, apprise en branchant une vraie application : pour une
    # interface de conversation, ignorer le prompt du client est le bon choix —
    # l'identite de Nova ne se delegue pas. Mais un client STRUCTURE attend un
    # format precis ; ecraser sa consigne casse l'application sans un mot.
    # On distingue donc les deux cas, et dans les deux la memoire est injectee.
    # ── ORDRE DES MORCEAUX : DU PLUS STABLE AU PLUS VOLATIL ───────────────
    #
    # Ce n'est pas une question de lisibilite, c'est une question de temps.
    # Le moteur d'inference garde en cache le travail deja fait sur un debut
    # de prompt identique. Ce cache vaut jusqu'au PREMIER caractere qui
    # change : tout ce qui suit est relu de zero.
    #
    # L'instant present contient les minutes. Place en deuxieme position,
    # comme il l'etait, il invalidait donc la memoire et les documents a
    # chaque nouvelle minute — c'est-a-dire presque toujours. Relegue a la
    # fin, il ne coute plus que lui-meme.
    #
    # Mesure qui motive tout ce bloc, sur l'iMac M1 :
    #     prompt 6573 car.  ->  21,4 s avant le premier mot
    # Le modele n'etait pas lent : il relisait tout, a chaque question.
    parts: list[tuple[str, str]] = []

    def ajouter(nom: str, contenu: str) -> None:
        if contenu:
            parts.append((nom, contenu))

    # 1. Stable — ne change jamais d'une question a l'autre.
    ajouter("contrat" if contrat else "identite",
            contrat or prompts.load("identity"))
    if mode == "critique" and not contrat:
        ajouter("mode critique", prompts.load("mode_critique"))
    if not get_settings().thinking:
        # Interrupteur documente de Qwen 3. Inoffensif pour les modeles qui ne
        # le connaissent pas : ce n'est qu'une ligne de texte de plus.
        #
        # ⚠️ IL ETAIT CONDITIONNE A `not contrat`, ET C'ETAIT L'INVERSE DE CE
        # QU'IL FALLAIT.
        #
        # L'application de bureau envoie TOUJOURS son contrat (le JSON a une
        # clef `response`). Le seul chemin qui n'en envoie pas est la CLI. Le
        # coupe-monologue etait donc actif exactement la ou personne ne parle a
        # Nova, et desactive sur le chemin vocal — celui ou quelqu'un attend en
        # silence devant une sphere qui tourne.
        #
        # Ca ne se voyait pas tant que le modele n'etait pas un raisonneur.
        # Avec une base Qwen 3.x, ca se compte en dizaines de secondes de
        # silence avant le premier mot. `ThinkFilter` cache le monologue, il ne
        # le rembourse pas : « Ce filtre ne rend pas le modele plus rapide : le
        # temps est deja depense » (llm/client.py).
        #
        # Un contrat decrit la FORME de la reponse. `/no_think` decide s'il y a
        # un monologue AVANT. Les deux ne parlent pas de la meme chose et n'ont
        # aucune raison de s'exclure. Qui veut le raisonnement met
        # NOVA_THINKING=true — c'est le champ prevu pour, et il vaut maintenant
        # pour les deux chemins.
        #
        # ⚠️ CETTE LIGNE N'EST PLUS L'INTERRUPTEUR. ELLE NE L'A JAMAIS ETE
        # POUR LE MODELE DU PROJET.
        #
        # `/no_think` appartient a Qwen 3. Sur la base Qwen 3.5 de `nova`, il
        # est ignore — verifie sur la machine : le modele raisonnait alors que
        # `/no_think` etait le message systeme ENTIER. Le vrai interrupteur est
        # `reasoning_effort: "none"`, envoye dans la requete par
        # `llm/client.py`, sous la meme condition `NOVA_THINKING`.
        #
        # On garde la ligne : elle coute neuf caracteres et reste le seul
        # levier pour un Qwen 3 servi par un Ollama trop ancien pour connaitre
        # `reasoning_effort`. Mais elle ne garantit rien, et c'est ecrit ici
        # pour que personne ne la croie sur parole une deuxieme fois.
        ajouter("no_think", "/no_think")

    # 2. Lent — ne bouge que quand la memoire evolue.
    #
    # Servi depuis le cache partage avec le vocabulaire : la lecture en base
    # se fait dans le fil d'entretien, pas dans la question de l'utilisateur.
    ajouter("memoire", _bloc_memoire())

    # 3. Volatil — change a chaque minute, puis a chaque question.
    #
    # Un modele n'a AUCUNE notion du temps : sans cette ligne, « quelle heure
    # est-il » recoit une heure inventee, avec aplomb. C'est la premiere
    # question que tout le monde pose a un assistant vocal, et le premier
    # endroit ou il perd la confiance de son utilisateur.
    # ⚠️ ET SEULEMENT QUAND ON PARLE DE TEMPS. RELEVE EN CONDITIONS REELLES :
    #
    #     « Suivant cette loi-la, nous pourrions retourner dans le passe. »
    #     → « C'est possible si l'energie est suffisante pour reparer le
    #        temps, mais cela demande des calculs precis. »
    #     « Pourrais-tu faire ces calculs ? »
    #     → « Il reste 23 heures de la journee. Le temps est calme. »
    #
    # La question ne portait ni sur l'heure ni sur la date. Le modele a
    # cherche des nombres, n'a trouve que ceux de l'horloge — il etait 23 h —
    # et a repondu dessus. Le mot « temps » de l'echange precedent a fait le
    # reste : en francais il designe la duree ET la meteo, et le bloc parlait
    # justement de duree.
    #
    # Un bloc inutile ne coute pas que du temps de lecture : il donne au
    # modele de quoi repondre a cote. C'est la meme raison qui rend le bloc de
    # recherche de fichiers conditionnel.
    if _question_de_temps(user_message):
        ajouter(
            "instant present",
            f"## Instant present\nNous sommes {instant_present()}.\n"
            "Utilise cette information telle quelle pour toute question de date ou "
            "d'heure. Ne la recalcule pas, ne l'estime pas.",
        )

    # 4. Ce que Nova voit.
    #
    # ⚠️ APRES L'INSTANT PRESENT, ET CE N'EST PAS ARBITRAIRE.
    #
    # Meme raison que pour l'ordre des autres blocs : le cache du moteur vaut
    # jusqu'au premier caractere qui change. Une observation d'image change a
    # chaque image, donc plus souvent que tout le reste — elle va donc apres
    # ce qui est stable, pour ne couter qu'elle-meme.
    #
    # ⚠️ ET GRATUIT QUAND LA DEMANDE NE PARLE PAS D'IMAGE.
    #
    # `regard.bloc` commence par une expression reguliere. Elle rend `""` en
    # zero milliseconde pour l'ecrasante majorite des questions — ce qui est
    # la condition pour que ce branchement ne coute rien a personne.
    # ⚠️ LA RECHERCHE DE FICHIERS PASSE AVANT LE REGARD, ET IL LE FAUT.
    #
    # « retrouve dans mes fichiers ou dans mes photos mon releve de compte de
    # 2024 » contient le mot « photos ». Le catalogue d'images le prend pour
    # lui et part chercher une casquette — reponse exacte a une autre
    # question. Le mot « releve » est un signal bien plus specifique que
    # « photos » : il tranche.
    #
    # ⚠️ ET UN SEUL DES DEUX BLOCS PART.
    #
    # Deux recherches concurrentes dans le meme prompt — l'une qui dit « aucune
    # image ne correspond », l'autre qui nomme un PDF — font choisir un modele
    # de deux milliards de parametres au hasard, ou melanger les deux.
    # ⚠️ ET UN ECHEC NE PRE-EMPTE RIEN. C'EST TOUTE LA CORRECTION.
    #
    # Premiere version : un bloc de fichier NON VIDE empechait le regard. Or
    # « aucun fichier ne correspond » est un bloc non vide. Releve en
    # conditions reelles, et c'etait une regression :
    #
    #     « peux-tu me retrouver une photo dans mon PC ou je tiens une
    #       casquette blanche »
    #
    # « dans mon PC » a suffi a declencher la recherche de fichiers ; aucun
    # fichier ne s'appelle « casquette » ; et le catalogue d'images — qui
    # connaissait cette photo par sa DESCRIPTION, l'avait deja trouvee et
    # ouverte la veille — n'a jamais ete consulte.
    #
    # L'ordre est donc : ce qui a TROUVE parle. A defaut, chacun essaie. Le
    # « je n'ai rien trouve » ne sort qu'en dernier recours, quand personne
    # d'autre n'a rien a dire.
    bloc_fichier, fichier_trouve = "", False
    try:
        from nova.fichiers import trouver

        # ⚠️ LE NOM NE SE DONNE QUE SUR DEMANDE — ET C'EST CETTE DEMANDE.
        #
        # Nova ne cite plus les fichiers qu'elle trouve : elle dit combien.
        # « c'est quoi le nom du troisieme ? » est desormais la seule facon
        # d'en obtenir un, et la reponse est lue dans la liste retenue, pas
        # produite par le modele — un nom de fichier ne se paraphrase pas.
        #
        # AVANT la recherche : « donne-moi le nom du troisieme document »
        # declenche les deux, et relancer Spotlight pour repondre a une
        # question sur ce qu'on vient de trouver serait absurde.
        bloc_fichier = trouver.bloc_du_nom(user_message)
        fichier_trouve = bool(bloc_fichier)
        if not fichier_trouve:
            bloc_fichier, fichier_trouve = trouver.bloc_et_resultat(user_message)
    except Exception as exc:  # noqa: BLE001
        log.warning("Recherche de fichiers indisponible : %s", exc)

    if fichier_trouve:
        ajouter("fichiers", bloc_fichier)
    else:
        bloc_regard = ""
        try:
            from nova.vision import regard

            bloc_regard = regard.bloc(user_message)
        except Exception as exc:  # noqa: BLE001
            # Une capacite en panne degrade la reponse, elle ne l'empeche jamais.
            log.warning("Vision indisponible : %s", exc)
        if bloc_regard:
            ajouter("regard", bloc_regard)
        elif bloc_fichier:
            ajouter("fichiers", bloc_fichier)

    hits: list[SearchHit] = []
    ms_recherche = 0.0
    if len(user_message.strip()) >= MIN_QUERY_LENGTH:
        debut_recherche = time.perf_counter()
        try:
            hits = document_search.search(user_message)
        except Exception as exc:  # noqa: BLE001
            # Une recherche en echec ne doit JAMAIS empecher Nova de repondre.
            # Chaque capacite est facultative : c'est ce qui rend le systeme
            # robuste quand on en ajoutera dix autres.
            log.warning("Recherche documentaire indisponible : %s", exc)
        ms_recherche = (time.perf_counter() - debut_recherche) * 1000
        chrono.enregistrer("recherche documentaire", ms_recherche)

    if hits:
        ajouter(
            "documents",
            "## Extraits de tes documents\n\n"
            "Appuie-toi dessus en priorite et cite la source entre crochets. "
            "S'ils ne repondent pas a la question, dis-le explicitement.\n\n"
            + _format_sources(hits),
        )

    # De quoi voir, en un coup d'oeil, quel morceau coute cher. Sans ce
    # detail, « le prompt fait 6573 caracteres » ne dit pas quoi couper.
    log.info(
        "Prompt systeme : %s",
        " + ".join(f"{nom} {len(contenu)}" for nom, contenu in parts),
    )
    # ── LE TEMPS PASSE AVANT MEME D'APPELER LE MODELE ────────────────────
    #
    # Ce chiffre manquait, et son absence a coute un tour entier. Le filtre
    # de pertinence a divise le prompt par deux (3376 -> 1812) sans changer
    # le temps avant le premier mot (5,1 -> 5,2 s) : la taille du prompt
    # n'etait donc pas le goulot. Il fallait chercher AILLEURS, et rien ne
    # disait ou.
    #
    # La recherche documentaire embarque un appel a bge-m3 pour vectoriser
    # la question — un second modele, de 1,2 Go, sur une machine de 8 Go. Ce
    # cout-la est paye meme quand AUCUN extrait n'est retenu.
    if ms_recherche >= 50:
        log.info(
            "Assemblage du prompt : recherche documentaire %.0f ms "
            "(vectorisation de la question comprise)%s",
            ms_recherche,
            "" if hits else " — pour zero extrait retenu",
        )
    return "\n\n".join(contenu for _, contenu in parts), hits


def answer_stream(
    messages: list[Message],
    *,
    conversation_external_id: str | None = None,
    mode: str = "normal",
    contrat: str | None = None,
    json_mode: bool = False,
    max_tokens: int | None = None,
) -> Iterator[str]:
    """Produit la reponse morceau par morceau, et journalise l'echange.

    `messages` est l'historique fourni par l'interface (format OpenAI). On
    remplace tout message systeme qu'elle aurait ajoute par le notre : l'identite
    de Nova ne doit pas dependre de l'interface.
    """
    user_messages = [m for m in messages if m.get("role") == "user"]
    last_user = user_messages[-1]["content"] if user_messages else ""

    with chrono.mesurer("construction du prompt"):
        system_prompt, hits = build_system_prompt(last_user, mode=mode, contrat=contrat)
    history = [m for m in messages if m.get("role") != "system"]

    conversation_id = conversations.get_or_create(conversation_external_id)

    # ── LE CONTEXTE CONVERSATIONNEL ──────────────────────────────────────
    #
    # Les echanges partaient en base et n'en revenaient jamais : ce module
    # savait ecrire, pas relire. Nova avait donc une memoire parfaite de ce
    # qui s'etait dit, et aucun moyen de s'en servir.
    #
    #     — « Parle-moi de Mars. »        Nova repond.
    #     — « Et on pourrait y vivre ? »  « y » ne renvoie a rien.
    #
    # On relit ICI, avant de journaliser la question en cours — sinon elle
    # figurerait deux fois dans le prompt, une fois comme passe et une fois
    # comme present.
    #
    # LA GARDE : un client qui envoie DEJA son historique fait foi.
    #
    # L'application de bureau n'envoie qu'un message ; un autre client
    # pourrait envoyer toute la conversation. Injecter le notre par-dessus le
    # sien donnerait deux versions du meme passe, dans le desordre — et le
    # modele n'aurait aucun moyen de trancher.
    # ── ⚠️ ET ON NE LE RAPPELLE QUE SI LA QUESTION S'Y APPUIE ────────────
    #
    # Le passe partait a CHAQUE question. C'etait le bon reflexe quand il
    # manquait — « Et on pourrait y vivre ? » n'a aucun sens sans « Parle-moi
    # de Mars ». Mais l'ecrasante majorite des questions se suffisent a
    # elles-memes, et leur donner le passe ne les aide pas : ca les brouille.
    #
    # Releve en conditions reelles, deux tours d'affilee :
    #
    #     — « quelle est la carte la plus rare, Pokemon ? »
    #     — « trouve-moi une image ou je tiens une casquette blanche »
    #       « Je ne trouve pas de CARTE BLANCHE correspondant a un SKATE. »
    #
    # La carte venait de la question d'avant. Le modele n'avait aucun moyen
    # de savoir qu'elle ne comptait plus.
    #
    # `reprise` repond a une seule question, sans modele et sans base : cette
    # phrase renvoie-t-elle a quelque chose d'anterieur ? Sinon, 1200
    # caracteres de prompt en moins, et aucun sujet abandonne pour revenir.
    passe: list[Message] = []
    if len(history) <= 1 and reprise.reprend_le_passe(last_user):
        try:
            with chrono.mesurer("rappel de l'historique"):
                passe = conversations.derniers_echanges(
                    conversation_id, budget_caracteres=get_tuning().historique_budget
                )
        except Exception as exc:  # noqa: BLE001
            # Un contexte indisponible degrade la conversation ; il ne doit
            # jamais empecher de repondre. Chaque capacite est facultative.
            log.warning("Historique de conversation indisponible : %s", exc)

    full: list[Message] = [{"role": "system", "content": system_prompt}, *passe, *history]
    if passe:
        log.info(
            "Contexte : %d message(s) precedent(s) rappeles (%d caracteres) — %s.",
            len(passe),
            sum(len(m["content"]) for m in passe),
            reprise.raison(last_user),
        )
    elif len(history) <= 1:
        # Une decision invisible qui change la reponse est une decision qu'on
        # passera des heures a chercher. Celle-ci se lit dans la console.
        log.info("Contexte : aucun rappel — %s.", reprise.raison(last_user))

    conversations.log_message(conversation_id, "user", last_user)

    # ⚠️ CHAQUE ECHANGE REPOUSSE LA FERMETURE DE LA CONVERSATION.
    #
    # La fenetre d'ecoute se compte depuis le dernier echange, pas depuis le
    # reveil : Nova met plusieurs secondes a DIRE sa reponse, et l'on
    # enchaine juste apres. Comptee depuis « Nova », elle se refermerait
    # pendant qu'elle parle.
    #
    # `prolonger` ne rouvre jamais une conversation fermee — sinon une
    # reponse tardive ranimerait une fenetre que le silence venait de clore.
    try:
        from nova.voice import session

        session.prolonger()
    except Exception as exc:  # noqa: BLE001
        log.warning("Session de conversation indisponible : %s", exc)

    # Repousse l'indexation des images : charger le modele de vision pendant
    # qu'on parle a Nova ferait attendre la reponse suivante sans raison
    # visible. Une horloge et un verrou — quelques microsecondes.
    try:
        from nova.vision.indexation import signaler_activite

        signaler_activite()
    except Exception:  # noqa: BLE001, S110
        pass

    # ══════════════════════════════════════════════════════════════════════
    #  ⚠️ C'EST ICI QUE LE CHOIX DU ROUTEUR ARRIVE ENFIN QUELQUE PART.
    #
    #  Cette ligne etait `client = LLMClient()`. Le routeur, lui, choisissait
    #  un modele depuis des mesures faites sur cette machine — et personne ne
    #  lisait sa reponse : `LLMClient()` relisait `settings.chat_model`. Son
    #  seul appelant etait `/v1/capacites`, pour AFFICHER la liste.
    #
    #  Un module qui existe, qui est teste, et dont le resultat est jete est
    #  plus trompeur qu'un module absent.
    #
    #  ⚠️ ET LE CHEMIN NE CHANGE PAS QUAND IL N'Y A QU'UN MODELE.
    #
    #  Avec le seul Ollama declare — le defaut, et la configuration de la
    #  machine de reference — le routage rend un candidat, et ce candidat
    #  appelle exactement le meme `LLMClient.stream` qu'avant, avec les memes
    #  arguments. Rien de ce qui a ete regle a l'usage n'est contourne : le
    #  filtre <think>, la coupure du JSON, keep_alive, les delais separes.
    #
    #  Le cout ajoute est un tri de liste sur des reglages deja en cache.
    # ══════════════════════════════════════════════════════════════════════
    #
    # `parlee` n'est pas devinable ici : ce point d'entree sert l'ecrit comme
    # le vocal. On prend l'usage le plus contraint des deux — local exige,
    # pas de monologue — parce que se tromper dans ce sens degrade une
    # reponse ecrite, alors que l'inverse ferait sortir de la machine des
    # donnees qu'une reponse prononcee ne doit pas laisser partir.
    usage = "extraction" if json_mode else "vocal"
    collected: list[str] = []
    completed = False

    # ── Ou passent les secondes ? ────────────────────────────────────────
    #
    # « C'est lent » n'est pas un diagnostic : un modele local peut etre lent
    # a lire la question (prefill) ou lent a ecrire la reponse (generation), et
    # les deux se corrigent a l'oppose l'un de l'autre. Raccourcir le prompt
    # d'un cote, reduire le plafond de jetons de l'autre.
    #
    # On separe donc les deux, en clair, a chaque appel. Sans cette ligne on
    # optimise a l'aveugle — ce qui a deja coute deux tours ici.
    taille_prompt = sum(len(m.get("content", "")) for m in full)
    depart = time.perf_counter()
    premier_morceau: float | None = None

    try:
        for piece in routage.flux(
            usage, full, json_mode=json_mode, max_tokens=max_tokens
        ):
            if premier_morceau is None:
                premier_morceau = time.perf_counter() - depart
            collected.append(piece)
            yield piece
        completed = True
    finally:
        total = time.perf_counter() - depart
        sortie = "".join(collected)
        if premier_morceau is not None:
            # ~4 caracteres par jeton en francais : approximation grossiere,
            # mais suffisante pour distinguer 3 jetons/s de 15.
            jetons = max(1, len(sortie) / 4)
            generation = max(total - premier_morceau, 1e-6)
            # Les deux moities de l'attente, separees : lire la question et
            # ecrire la reponse ne se corrigent pas du meme cote.
            chrono.enregistrer("modele — premier jeton", premier_morceau * 1000)
            chrono.enregistrer("modele — generation", generation * 1000)
            chrono.enregistrer("modele — total", total * 1000)
            log.info(
                "Modele %s : prompt %d car. → premier mot %.1f s, total %.1f s "
                "(%d car. produits, ~%.1f jetons/s)",
                get_settings().chat_model,
                taille_prompt,
                premier_morceau,
                total,
                len(sortie),
                jetons / generation,
            )
        else:
            log.warning(
                "Modele %s : aucun mot produit en %.1f s.",
                get_settings().chat_model,
                total,
            )

        # `finally` est indispensable ici, et la raison n'est pas theorique :
        # si l'utilisateur ferme l'onglet en cours de reponse, Python ferme le
        # generateur (GeneratorExit) et tout code place APRES la boucle ne
        # s'executerait jamais. La reponse serait perdue — inacceptable pour un
        # systeme dont la memoire est justement la raison d'etre.
        # Bug constate en coupant reellement un flux, pas en relisant le code.
        if collected:
            conversations.log_message(
                conversation_id,
                "assistant",
                "".join(collected),
                model=get_settings().chat_model,
                meta={
                    "sources": [h.document_path for h in hits],
                    "mode": mode,
                    "interrompu": not completed,
                },
            )


def answer(question: str, *, mode: str = "normal") -> str:
    """Reponse complete en un bloc. Pour la CLI et les traitements de fond."""
    return "".join(answer_stream([{"role": "user", "content": question}], mode=mode))


# ══════════════════════════════════════════════════════════════════════════
#  EXECUTER UNE INTENTION
#
#  C'est ici, et nulle part ailleurs, que Nova passe de la parole a l'acte.
#  L'orchestrateur est le seul module autorise a connaitre a la fois la
#  couche voix (qui reconnait) et la couche outils (qui agit) — les deux
#  s'ignorent, et c'est ce qui permet d'ajouter une action sans toucher a la
#  reconnaissance vocale.
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Resultat:
    """Ce qu'il est advenu d'une intention.

    Quatre issues, et il faut les quatre. Rendre un simple booleen forcerait
    l'appelant a deviner POURQUOI rien ne s'est passe — et il devinerait mal.
    """

    etat: str            # executee | a_confirmer | ignoree | echouee
    message: str
    outil: str | None = None
    niveau: int | None = None
    arguments: dict | None = None

    @property
    def agie(self) -> bool:
        return self.etat == "executee"


def _niveau_de(nom_outil: str) -> int | None:
    """Le niveau de risque declare par un outil, ou `None` s'il est illisible."""
    from nova.outils import registre_outils

    niveau = getattr(registre_outils.get(nom_outil), "niveau", None)
    if isinstance(niveau, bool) or not isinstance(niveau, int):
        return None
    return niveau


#: En dessous, un nom n'evoque rien d'installe et il vaut mieux le dire.
#:
#: CE CHIFFRE EST MESURE, PAS CHOISI. Sur un catalogue macOS realiste :
#:
#:     Fineur      -> Finder        0,600   a proposer
#:     Messagerie  -> Messages      0,625   a proposer
#:     Blender     -> Calendrier    0,556   rien d'installe, on le dit
#:     Slack       -> Plans         0,500   rien d'installe, on le dit
#:     Excel       -> TextEdit      0,500   rien d'installe, on le dit
SEUIL_APPLICATION = 0.60

#: Ecart minimal avec le deuxieme candidat pour parler de certitude. Une
#: ressemblance parfaite avec DEUX applications a la fois n'en designe aucune.
MARGE_APPLICATION = 0.15


@dataclass(frozen=True)
class _Cible:
    """Ce qu'on a pu faire d'une cible entendue.

    `candidats` existe pour le seul etat qui en a besoin : « Adobe » designe
    Photoshop ET Illustrator, et rendre le premier trouve reviendrait a tirer
    au sort. Une ambiguite doit se POSER, pas se trancher en silence.
    """

    nom: str
    etat: str                       # exact | propose | ambigu | inconnu
    candidats: tuple[str, ...] = ()


def _resoudre_application(cible: str) -> _Cible:
    """Confronte une cible entendue au catalogue reel.

        exact         on sait de quelle application il s'agit
        propose       on a un candidat, pas une certitude — il faut demander
        ambigu        plusieurs applications portent ce mot
        inconnu       rien de ressemblant n'est installe
        inverifiable  aucun catalogue lisible : on ne peut rien affirmer

    ⚠️ POURQUOI UNE RESSEMBLANCE ELEVEE NE SUFFIT PAS A AGIR

    Mesure sur un catalogue macOS realiste, cas devant passer et cas devant
    echouer melanges :

        Écoledirecte -> EcoleDirecte  1,000   il fallait ouvrir
        Gogol Chrome -> Google Chrome 0,875   il fallait ouvrir
        Discorde     -> Discord       0,857   il fallait ouvrir
        Photoshop    -> Photo Booth   0,833   IL NE FALLAIT PAS
        Photo bousse -> Photo Booth   0,714   il fallait ouvrir
        Fineur       -> Finder        0,600   il fallait ouvrir

    « Photoshop » n'est pas installe et ressemble davantage a « Photo Booth »
    que « Fineur » ne ressemble a « Finder ». AUCUN seuil ne separe donc les
    deux colonnes — le chercher aurait produit un chiffre arbitraire et une
    application ouverte a tort un jour sur dix.

    La regle qui en decoule est plus simple et plus honnete : on n'agit sans
    demander que sur une correspondance ECRITE (`resoudre`, qui ignore casse
    et accents) ou sur un son IDENTIQUE et sans rival. Tout le reste se
    PROPOSE. Le cout est une question de temps en temps ; le cout de l'autre
    choix etait d'ouvrir la mauvaise application en silence.

    C'EST ICI PAR RESPECT DE LA REGLE DE DEPENDANCE

    `outils/applications.py` sait lire un disque, `voice/phonetique.py` sait
    comparer des sons, et aucun des deux ne connait l'autre. L'orchestrateur
    est le seul module autorise a les faire se rencontrer.

    LE CAS QUI DECIDE DE TOUT : UN CATALOGUE VIDE

    Sur une machine qui n'est pas un Mac, ou si les dossiers sont illisibles,
    `installees()` rend un tuple vide. Il serait tentant d'en conclure
    « aucune application n'existe » et de tout refuser. Ce serait remplacer
    une capacite imparfaite par une panne franche. On laisse passer la cible
    telle quelle : le comportement redevient celui d'avant ce fichier, ce qui
    est le pire acceptable.
    """
    from nova.outils import applications
    from nova.voice import phonetique

    catalogue = applications.installees()
    if not catalogue:
        # ⚠️ « INVERIFIABLE » N'EST PAS « EXACT », ET LES CONFONDRE A COUTE
        #    UN REPLI QUI NE POUVAIT PAS SE DECLENCHER.
        #
        # Cet etat rendait « exact » : on laisse passer la cible telle quelle
        # plutot que de tout refuser, ce qui reste le bon comportement. Mais
        # « je sais que c'est cette application » et « je n'ai aucun moyen de
        # savoir » ne sont pas la meme information, et tout appelant qui se
        # fie a « exact » pour conclure a une certitude se trompe.
        #
        # Le repli sur un fichier image s'y est casse : sur une machine sans
        # catalogue, « ouvre la derniere image » ressortait « exact » et
        # partait vers `ouvrir_application`.
        #
        # L'etat traverse `_confronter_au_reel` exactement comme avant — il
        # n'est ni ambigu, ni inconnu, ni propose — donc rien ne change pour
        # qui ne le lit pas.
        return _Cible(cible, "inverifiable")

    if reel := applications.resoudre(cible):
        return _Cible(reel, "exact")

    # ── LE SOUS-NOM ──────────────────────────────────────────────────────
    #
    # Personne ne dit « ouvre Adobe Photoshop 2025 » : on dit « Photoshop ».
    # La forme longue est sur le disque, la forme courte est prononcee, et
    # l'ecart est la regle. Un mot ECRIT pareil est une correspondance aussi
    # sure qu'un nom entier — a condition qu'il n'en designe qu'une.
    if sous_noms := applications.par_sous_nom(cible):
        if len(sous_noms) == 1:
            log.info("Application « %s » reconnue comme « %s ».", cible, sous_noms[0])
            return _Cible(sous_noms[0], "exact")
        log.info("Application « %s » : %d candidates.", cible, len(sous_noms))
        return _Cible(cible, "ambigu", sous_noms)

    # Rien d'ecrit pareil : reste l'oreille. On classe TOUT le catalogue —
    # et rien d'autre. La memoire et le vocabulaire declare n'ont pas a
    # concourir ici, ou « Adam » finirait par designer « Adobe ».
    #
    # Chaque application est jugee sur son MEILLEUR angle : son nom entier ou
    # l'un de ses mots. « Crome » ne ressemble pas a « Google Chrome » (0,43)
    # et sonne exactement comme son mot « Chrome » (1,00).
    def note(nom: str) -> float:
        angles = (nom, *applications.jetons(nom))
        return max(phonetique.ressemblance(cible, angle) for angle in angles)

    classement = sorted(((note(nom), nom) for nom in catalogue), reverse=True)
    meilleur, nom = classement[0]

    if meilleur < SEUIL_APPLICATION:
        return _Cible(cible, "inconnu")

    # Les candidats que rien ne separe du premier.
    #
    # « Fotochop » sonne EXACTEMENT autant comme « Photo Booth » que comme
    # « Adobe Photoshop 2025 » — 0,667 des deux cotes. J'ai cherche un
    # departage : longueur du fragment retenu, position du mot. Aucun ne
    # separait ces deux-la sans en melanger d'autres. La conclusion honnete
    # est qu'il n'y a pas de signal, et proposer le premier par ordre
    # alphabetique aurait maquille un tirage au sort en decision.
    ex_aequo = tuple(n for score, n in classement if meilleur - score < MARGE_APPLICATION)
    if len(ex_aequo) > 1:
        log.info("Application « %s » : %d lectures aussi vraisemblables.", cible, len(ex_aequo))
        return _Cible(cible, "ambigu", ex_aequo)

    if meilleur >= 1.0:
        # Meme son exactement, et un seul candidat : « Saffari » pour
        # « Safari », « Crome » pour « Google Chrome ». Demander ici
        # n'apprendrait rien a personne.
        log.info("Application « %s » reconnue comme « %s ».", cible, nom)
        return _Cible(nom, "exact")

    log.info(
        "Application « %s » : « %s » ressemble (%.2f) sans certitude — je demande.",
        cible, nom, meilleur,
    )
    return _Cible(nom, "propose")


#: Au-dela, une liste dite a voix haute ne s'ecoute plus. Trois noms tiennent
#: dans une phrase ; huit ne sont plus une question mais un inventaire.
CANDIDATS_CITES = 3


def _enumerer(noms: tuple[str, ...]) -> str:
    """« A, B ou C », et « A, B ou 4 autres » au-dela.

    Ecrit pour l'OREILLE : cette phrase sera prononcee, pas lue. Une liste a
    puces ne s'entend pas, et une enumeration sans « ou » final laisse croire
    que Nova s'est interrompue.
    """
    cites = list(noms[:CANDIDATS_CITES])
    reste = len(noms) - len(cites)
    if reste > 0:
        cites.append(f"{reste} autre{'s' if reste > 1 else ''}")
    if len(cites) == 1:
        return f"« {cites[0]} »"
    debut = ", ".join(f"« {n} »" for n in cites[:-1])
    dernier = cites[-1]
    fin = dernier if dernier[0].isdigit() else f"« {dernier} »"
    return f"{debut} ou {fin}"


def _confronter_au_reel(
    action, cible: str, *, confirme: bool
) -> tuple[object, dict | None, Resultat | None]:
    """Valide la cible avant qu'elle n'atteigne l'outil.

    Rend l'ACTION a executer, les arguments, ou le `Resultat` qui interrompt.

    ⚠️ L'ACTION EST RENDUE PARCE QU'ELLE PEUT CHANGER.

    Elle etait passee en entree et jamais en sortie, ce qui supposait que
    confronter une cible au reel ne pouvait que la valider ou la refuser. Or
    « ouvre la derniere image » demande un autre outil que « ouvre Discord » —
    et la seule facon de le savoir est justement d'avoir confronte la cible.

    L'alternative etait de faire passer un nom d'outil dans le dictionnaire
    d'arguments. Elle aurait marche jusqu'au premier outil prenant un
    argument du meme nom.
    """
    from nova.core import actions, contrats

    if action.catalogue != actions.CATALOGUE_APPLICATIONS or not action.argument:
        return action, ({action.argument: cible} if action.argument else {}), None

    # ── « OUVRE LA PHOTO » JUSTE APRES EN AVOIR TROUVE UNE ───────────────
    #
    # ⚠️ LE DETERMINANT EST DETRUIT AVANT D'ARRIVER ICI.
    #
    # `intentions.BRUIT_CIBLE` retire « la » de la cible — c'est ce qui fait
    # marcher « ouvre l'application Chrome ». Consequence : « ouvre LA photo »
    # et « ouvre Photos » arrivent tous les deux comme « photo ». Le signal
    # sur lequel repose `designe_une_image` n'existe plus a cet etage.
    #
    # Releve en conditions reelles : Nova venait de trouver IMG_8156.JPG, on
    # lui dit « ouvre la photo », et elle a ouvert l'APPLICATION Photos de
    # macOS. Correct du point de vue du catalogue, absurde du point de vue de
    # la conversation.
    #
    # Le contexte tranche ou la grammaire ne le peut plus : si une image est
    # en tete, « la photo » designe CETTE image. Hors de ce cas — aucune image
    # en tete — « ouvre Photos » ouvre l'application, comme avant.
    if action.outil == "ouvrir_application":
        from nova.vision.regard import image_en_tete_pour

        if (retenue := image_en_tete_pour(cible)) is not None:
            log.info("« %s » : ouverture de l'image en tete (%s).", cible, retenue.name)
            return (
                actions.Action("ouvrir_image", "chemin"),
                {"chemin": str(retenue)},
                None,
            )

        # ⚠️ ET LA MEME CHOSE POUR UN FICHIER QU'ON VIENT DE TROUVER.
        #
        # « ouvre cet avis d'imposition de 2024 » rendait « Je ne trouve pas
        # d'application "cette envie d'imposition de 2024" sur cette
        # machine ». Le verbe « ouvre » ne connaissait que les applications et
        # les images ; la recherche de fichiers venait pourtant de designer le
        # bon PDF une phrase plus tot.
        from nova.fichiers.trouver import fichier_en_tete_pour

        if (papier := fichier_en_tete_pour(cible)) is not None:
            log.info("« %s » : ouverture du fichier en tete (%s).", cible, papier.name)
            return (
                actions.Action("ouvrir_fichier", "chemin"),
                {"chemin": str(papier)},
                None,
            )

    trouvee = _resoudre_application(cible)
    retenu, etat = trouvee.nom, trouvee.etat

    # ── LE REPLI SUR UN FICHIER IMAGE ────────────────────────────────────
    #
    # ⚠️ APRES LE CATALOGUE, JAMAIS AVANT.
    #
    # « ouvre-moi la derniere image que j'ai transferee » rendait « Je ne
    # trouve pas d'application "derniere image que j'ai transferee" sur cette
    # machine » — exact, et inutile : le message decrivait ce que Nova avait
    # cherche, pas ce qu'on lui avait demande. Le verbe « ouvre » ne
    # connaissait qu'une seule chose a ouvrir.
    #
    # Pre-empter aurait ete plus simple a ecrire et FAUX : « ouvre Photos »
    # vise l'application Photos de macOS, et « photos » est justement le mot
    # qui designe une image. Le determinant tranche — « LA photo » contre
    # « Photos » — mais s'y fier seul reviendrait a parier sur la grammaire
    # d'une transcription vocale.
    #
    # Un repli n'enleve rien : une application reellement installee gagne
    # toujours. Il remplace seulement un echec par une reussite.
    if etat != "exact" and action.outil == "ouvrir_application":
        from nova.vision.regard import CHEMIN, designe_une_image

        if designe_une_image(cible):
            nomme = CHEMIN.search(cible)
            # ⚠️ « OUVRE L'IMAGE OU IL Y A UNE CASQUETTE » N'EST PAS
            #    « OUVRE LA DERNIERE IMAGE ».
            #
            # La premiere decrit un CONTENU : sans consulter le catalogue, on
            # ouvrirait la plus recente — une image que personne n'a demandee,
            # et Nova annoncerait fierement l'avoir ouverte. C'est le genre de
            # reussite apparente qui est pire qu'un echec.
            from nova.vision.regard import contenu_cherche, retrouver

            # `tolerant=False` : seule une tournure EXPLICITE — « ou il y a »,
            # « avec », « qui montre » — vaut une recherche au catalogue. Le
            # repli tolerant sert a repondre, ou l'on nomme le fichier retenu
            # et ou l'utilisateur corrige d'un mot.
            if not nomme and (quoi := contenu_cherche(cible, tolerant=False)):
                if trouvees := retrouver(quoi, limite=1):
                    entree = trouvees[0][0]
                    log.info("« %s » retrouvee au catalogue : %s", quoi, entree.nom)
                    return (
                        actions.Action("ouvrir_image", "chemin"),
                        {"chemin": entree.chemin},
                        None,
                    )
                return action, None, Resultat(
                    "echouee",
                    f"Je n'ai trouvé aucune image correspondant à {quoi}.",
                    outil="ouvrir_image", arguments={"chemin": ""},
                )
            log.info("« %s » ne designe aucune application : ouverture comme image.", cible)
            # L'action est REMPLACEE, pas contournee. Faire passer un nom
            # d'outil dans le dictionnaire d'arguments aurait marche
            # aujourd'hui et se serait paye au premier outil qui prend un
            # argument du meme nom.
            return (
                actions.Action("ouvrir_image", "chemin"),
                {"chemin": nomme.group(1) if nomme else ""},
                None,
            )

    if etat == "ambigu":
        # On NE tranche PAS a la place de l'utilisateur. La question est posee
        # en `echouee` et non en `a_confirmer` a dessein : « oui » ne saurait
        # pas designer laquelle. Elle se repond en nommant l'application, ce
        # qui repart comme une demande neuve — sans etat a garder.
        return action, None, Resultat(
            "echouee",
            f"« {cible} » peut désigner {_enumerer(trouvee.candidats)}. Laquelle ?",
            outil=action.outil, arguments={action.argument: cible},
        )

    if etat == "inconnu":
        # Dire ce qu'on ne trouve pas vaut mieux que laisser `open` echouer
        # avec un message en anglais sur un nom que Nova a peut-etre mal
        # entendu.
        return action, None, Resultat(
            "echouee",
            f"Je ne trouve pas d'application « {cible} » sur cette machine.",
            outil=action.outil, arguments={action.argument: cible},
        )

    if etat == "propose":
        # ⚠️ DEUX QUESTIONS NE PEUVENT PAS TENIR DANS UN SEUL « OUI ».
        #
        # La confirmation remonte par un unique champ booleen. Si un outil
        # dangereux avait AUSSI une cible incertaine, le « oui » de
        # l'utilisateur repondrait aux deux a la fois — il croirait valider un
        # nom et validerait une action irreversible. On refuse plutot que de
        # confondre : aujourd'hui aucun outil n'est dans ce cas, et le jour ou
        # l'un le sera, il trouvera cette garde au lieu du piege.
        if contrats.exige_confirmation(_niveau_de(action.outil) or contrats.IRREVERSIBLE):
            return action, None, Resultat(
                "echouee",
                f"Je ne suis pas sûre de « {cible} » — je ne devine pas sur une "
                "action de cette importance.",
                outil=action.outil, arguments={action.argument: cible},
            )
        if not confirme:
            return action, None, Resultat(
                "a_confirmer",
                f"Je ne connais pas « {cible} ». Tu veux dire « {retenu} » ?",
                outil=action.outil, niveau=_niveau_de(action.outil),
                arguments={action.argument: retenu},
            )

    return action, {action.argument: retenu}, None


def ouvrir_toute_la_liste(chemins) -> Resultat:
    """Ouvre tous les fichiers que Nova vient d'annoncer. Ne leve jamais.

    ⚠️ UN ECHEC SUR L'UN N'ARRETE PAS LES AUTRES.

    Trois avis d'imposition, le deuxieme deplace entre-temps : ouvrir le
    premier puis abandonner serait le pire des deux mondes. On ouvre ce qu'on
    peut et on dit combien.
    """
    from nova.outils import executer_outil

    ouverts, rates = [], []
    for chemin in chemins:
        try:
            executer_outil("ouvrir_fichier", chemin=str(chemin))
        except Exception as erreur:  # noqa: BLE001
            log.warning("« %s » non ouvert : %s", chemin, erreur)
            rates.append(str(chemin))
        else:
            ouverts.append(str(chemin))

    if not ouverts:
        return Resultat("echouee", "Je n'ai réussi à en ouvrir aucun.")
    combien = f"J'ai ouvert les {len(ouverts)} fichiers."
    if rates:
        combien = f"J'ai ouvert {len(ouverts)} fichiers sur {len(ouverts) + len(rates)}."
    return Resultat("executee", combien, outil="ouvrir_fichier")


def executer_outil_propose(outil: str, arguments: dict, *, comme: str = "") -> Resultat:
    """Execute une action que NOVA a proposee et que l'utilisateur a acceptee.

    ⚠️ ELLE PASSE PAR LE MEME PORTILLON QUE TOUTES LES AUTRES.

    Le bareme de risque s'applique : une proposition acceptee n'est pas un
    laissez-passer. `executer_outil` refusera toujours ce qui demande une
    confirmation explicite — et c'est voulu, parce que « oui » repond ici a
    « je te l'ouvre ? », pas a une question qu'on n'a pas posee.

    Ne leve jamais : un refus ou une panne doivent se DIRE, pas remonter.
    """
    from nova.outils import ConfirmationRequise, executer_outil

    try:
        message = executer_outil(outil, **arguments)
    except ConfirmationRequise as demande:
        return Resultat("a_confirmer", str(demande), outil=outil, arguments=arguments)
    except Exception as erreur:  # noqa: BLE001
        log.warning("Proposition acceptee mais impossible : %s", erreur)
        return Resultat("echouee", str(erreur), outil=outil, arguments=arguments)
    # ⚠️ ON DIT CE QUE LA PERSONNE A DEMANDE, PAS LE NOM DU FICHIER.
    #
    # « J'ai ouvert CNI BERANGERE RECTO-1.png » est illisible a voix haute et
    # ne ressemble a rien de ce qui a ete dit. « J'ai ouvert ta carte
    # d'identite » reprend ses mots.
    dit = f"J'ai ouvert ta {comme}." if comme else str(message)
    return Resultat("executee", dit, outil=outil, arguments=arguments)


def executer_intention(comprise, *, confirme: bool = False) -> Resultat:
    """Passe a l'acte, si et seulement si tout concorde. Ne leve jamais.

    `confirme` vient de l'UTILISATEUR, jamais du modele : c'est la reponse
    a une question posee, pas un champ qu'une IA peut remplir elle-meme.
    """
    from nova.core import actions
    from nova.outils import ConfirmationRequise, executer_outil

    intention = comprise.intention
    if not intention.reconnue:
        return Resultat("ignoree", "Aucune intention reconnue.")

    # ── LES DEUX CONFIANCES, ET POURQUOI IL EN FAUT DEUX ─────────────────
    #
    # « Sur quelle planete pour lui en ouvrir » etait une transcription
    # bancale contenant « ouvrir » : intention nette, parole douteuse. Agir
    # sur ce seul signal aurait lance une application au milieu d'une
    # question d'astronomie.
    #
    # Dans le doute, Nova PARLE au lieu d'AGIR. C'est rattrapable dans ce
    # sens-la, jamais dans l'autre.
    if not actions.executable(intention.nom, intention.confiance, comprise.sure):
        raison = (
            "action inconnue" if actions.action_pour(intention.nom) is None
            else "parole ou intention trop incertaine"
        )
        log.info(
            "Intention « %s » NON executee (%s) : parole %s (%.2f), intention %.2f.",
            intention.nom, raison,
            "sûre" if comprise.sure else "douteuse",
            comprise.confiance, intention.confiance,
        )
        return Resultat("ignoree", f"Intention reconnue mais non executee : {raison}.")

    action = actions.action_pour(intention.nom)

    # La cible est confrontee au reel AVANT d'atteindre l'outil. Un nom
    # d'application mal entendu doit se rattraper ici, ou il deviendra un
    # echec de `open` sur lequel personne ne peut rien.
    action, arguments, interruption = _confronter_au_reel(
        action, intention.cible, confirme=confirme
    )
    if interruption is not None:
        log.info(
            "Cible « %s » non retenue pour « %s » : %s",
            intention.cible, action.outil, interruption.etat,
        )
        return interruption

    try:
        message = executer_outil(action.outil, confirme=confirme, **arguments)
        return Resultat("executee", str(message), outil=action.outil, arguments=arguments)
    except ConfirmationRequise as attente:
        return Resultat(
            "a_confirmer", attente.question(),
            outil=action.outil, niveau=attente.niveau, arguments=arguments,
        )
    except Exception as exc:  # noqa: BLE001
        # Une action qui echoue doit le DIRE. Un echec silencieux laisse
        # croire que Nova a agi, ce qui est la pire des issues.
        log.warning("Action « %s » en echec : %s", action.outil, exc)
        return Resultat("echouee", str(exc), outil=action.outil, arguments=arguments)
