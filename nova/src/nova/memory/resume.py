"""Le resume de session : ce qui reste quand les messages tombent du budget.

⚠️ LE DEFAUT QUE CE MODULE CORRIGE EST SILENCIEUX, ET C'EST LE PIRE.

`derniers_echanges` borne le passe a 1200 caracteres, en gardant les
messages RECENTS. C'est le bon arbitrage — le present se sert avant le
passe, et le risque R13 (« Nova ralentit a mesure qu'elle apprend ») ne se
tient pas autrement. Mais au bout d'une heure de travail, tout ce qui a ete
etabli au debut a disparu du prompt. Sans un mot, sans une ligne de journal.
On croit parler a quelqu'un qui suit, et on parle a quelqu'un qui a oublie
le sujet.

    — « On part sur un moteur electrique, batterie a l'arriere. »
      … quarante messages plus tard …
    — « Et le refroidissement, on le met ou ? »
      « De quel refroidissement parles-tu ? »

CE QUE FAIT CE MODULE : IL COMPRESSE, IL NE JETTE PAS

Les vieux messages ne tombent plus du budget, ils y entrent sous une forme
plus courte. Le resume couvre les messages jusqu'a `jusqu_au_message` ; ceux
d'apres restent mot pour mot. Deux formes du meme passe, jamais les deux
pour le meme message.

⚠️ ET LE TOTAL NE GROSSIT PAS.

Le resume ne s'ajoute pas au budget : il en prend une part. Un module qui
resout l'oubli en allongeant le prompt de 700 caracteres deplace le probleme
sur chaque question suivante — a 3,3 ms par caractere mesures sur la machine
de reference, ce sont deux secondes de plus avant le premier mot.

⚠️ RESUMER COUTE UN APPEL DE MODELE. IL N'ARRIVE JAMAIS PENDANT QU'ON PARLE.

C'est la regle que suivent deja le vocabulaire personnel et l'indexation des
images : un travail previsible se fait pendant que personne ne regarde. Le
fil d'entretien attend qu'une conversation se taise avant de la resumer.
Rien de ce module n'est appele depuis le chemin d'une reponse, sauf la
lecture — qui est une requete SQL sur un index.

⚠️ LE RESUME NE SORT PAS DE LA MACHINE.

`usage="extraction"` porte `local_exige=True` : le routeur n'a pas le droit
d'envoyer une conversation entiere a un fournisseur distant pour la
condenser. Le resume vit dans la meme base que les messages dont il est
tire — il n'expose donc rien que la base ne contienne deja.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

from nova.db import connection
from nova.logging_setup import get_logger
from nova.memory import conversations

log = get_logger(__name__)

# ── Quand resumer ────────────────────────────────────────────────────────

#: Messages accumules au-dela du dernier resume avant qu'un nouveau vaille
#: son appel de modele.
#:
#: ⚠️ TROP BAS, ON RESUME UNE CONVERSATION QUI TIENT ENCORE DANS LE BUDGET.
#:
#: Douze messages courts pesent moins que 1200 caracteres : le rappel brut
#: suffit, et le resume n'aurait rien sauve. Le seuil ne se compte pas en
#: caracteres pour autant — une conversation de douze longs messages a
#: DEJA perdu son debut, et c'est justement celle-la qu'il faut attraper.
MESSAGES_AVANT_RESUME = 12

#: Messages toujours gardes mot pour mot, jamais absorbes par le resume.
#:
#: ⚠️ SANS CETTE GARDE, LE RESUME MANGE LA PHRASE PRECEDENTE.
#:
#: « Et on pourrait y vivre ? » ne se resout pas avec « l'utilisateur a
#: parle de Mars » : il faut la phrase, telle qu'elle a ete dite. Le resume
#: sert le lointain ; le proche reste brut.
GARDE_BRUTE = 6

#: Silence, en secondes, apres lequel une conversation est consideree comme
#: posee et donc resumable. Mesure sur `last_message_at`, par conversation :
#: on ne resume pas celle dans laquelle quelqu'un est en train de parler.
SILENCE_S = 120.0

#: Le demarrage charge deja Whisper et le modele de langue. On ne s'y ajoute
#: pas — meme raison que le fil d'indexation des images.
DEMARRAGE_S = 150.0

#: Entre deux passages du fil d'entretien.
REPOS_S = 60.0

# ── Ce que le resume a le droit de peser ─────────────────────────────────

#: Plafond dur du texte stocke. Au-dela, ce n'est plus un resume.
RESUME_MAX_CARACTERES = 700

#: Part du budget de rappel reservee aux messages BRUTS quand un resume
#: existe. Le present passe avant le passe, ici comme ailleurs.
PART_DU_PRESENT = 0.6


@dataclass(frozen=True)
class Resume:
    """Un resume enregistre, et jusqu'ou il porte."""

    texte: str
    jusqu_au_message: int
    cree_le: datetime | None = None


@dataclass(frozen=True)
class Rappel:
    """Ce qu'on redonne au modele : un resume du lointain, le proche brut."""

    resume: str = ""
    messages: list[dict[str, str]] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.resume or self.messages)


# ══════════════════════════════════════════════════════════════════════════
#  LECTURE — sur le chemin de la reponse. Une requete, pas un modele.
# ══════════════════════════════════════════════════════════════════════════


def courant(conversation_id: int) -> Resume | None:
    """Le dernier resume de cette conversation, s'il y en a un."""
    with connection() as conn:
        row = conn.execute(
            """
            SELECT resume, jusqu_au_message, cree_le
            FROM resumes_de_session
            WHERE conversation_id = %s
            ORDER BY cree_le DESC, id DESC
            LIMIT 1
            """,
            (conversation_id,),
        ).fetchone()
    if not row or not (row["resume"] or "").strip():
        return None
    return Resume(
        texte=row["resume"].strip(),
        jusqu_au_message=row["jusqu_au_message"] or 0,
        cree_le=row["cree_le"],
    )


def rappeler(
    conversation_id: int, *, budget_caracteres: int, tours_max: int = 8
) -> Rappel:
    """Le passe de cette conversation, resume pour le lointain, brut pour le proche.

    Remplace l'appel nu a `derniers_echanges` : meme budget total, mais le
    debut de la conversation n'est plus perdu — il est condense.

    Sans resume enregistre, le resultat est EXACTEMENT ce que rendait
    `derniers_echanges`. C'est ce qui permet a ce module d'arriver sans rien
    changer tant que le fil d'entretien n'a pas tourne.
    """
    # ⚠️ UNE PANNE DE RESUME NE DOIT PAS EMPORTER LE RAPPEL BRUT.
    #
    # `rappeler` a remplace un appel nu a `derniers_echanges`. En lisant le
    # resume EN PREMIER, elle a introduit un point de panne devant une
    # fonctionnalite qui marchait : table absente, migration non appliquee,
    # base momentanement injoignable — et le passe recent disparaissait avec.
    #
    # Trois bancs ecrits bien avant ce module l'ont montre, le jour ou la base
    # s'est arretee pendant une passe. Ils avaient raison : le resume est un
    # PLUS, et un plus ne prend pas en otage ce qu'il complete.
    try:
        vieux = courant(conversation_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("[Resume] Resume indisponible, rappel brut conserve : %s", exc)
        vieux = None
    if vieux is None:
        return Rappel(
            messages=conversations.derniers_echanges(
                conversation_id,
                budget_caracteres=budget_caracteres,
                tours_max=tours_max,
            )
        )

    pour_le_present = max(1, int(budget_caracteres * PART_DU_PRESENT))
    messages = conversations.derniers_echanges(
        conversation_id,
        budget_caracteres=pour_le_present,
        tours_max=tours_max,
        apres=vieux.jusqu_au_message,
    )
    reste = budget_caracteres - sum(len(m["content"]) for m in messages)
    return Rappel(resume=_tronquer(vieux.texte, max(0, reste)), messages=messages)


def bloc(rappel: Rappel) -> str:
    """Le resume, mis en forme pour le prompt systeme. Vide s'il n'y en a pas.

    ⚠️ AUCUNE CONSIGNE DE COMPORTEMENT ICI.

    Un modele de 3 milliards de parametres CONTINUE ce qu'il vient de lire.
    « Ne reponds pas a ce resume » est une consigne qu'il enfreint une fois
    sur trois, et qui lui souffle en prime l'idee d'y repondre. Un titre et
    du texte : il le lit comme du contexte, ce qu'il est.
    """
    if not rappel.resume:
        return ""
    return "## Le debut de cette conversation\n\n" + rappel.resume + "\n"


def _tronquer(texte: str, plafond: int) -> str:
    """Coupe a la ligne, jamais au milieu d'un mot.

    Le resume est une liste de points : en couper un a la moitie donnerait
    une phrase fausse, ce qui est pire que de la perdre entiere.
    """
    if len(texte) <= plafond:
        return texte
    gardees: list[str] = []
    total = 0
    for ligne in texte.splitlines():
        if total + len(ligne) + 1 > plafond:
            break
        gardees.append(ligne)
        total += len(ligne) + 1
    return "\n".join(gardees)


# ══════════════════════════════════════════════════════════════════════════
#  ECRITURE — fil d'entretien uniquement. Coute un appel de modele.
# ══════════════════════════════════════════════════════════════════════════

_INSTRUCTIONS = (
    "Ecris en francais le resume de cette conversation, pour t'en souvenir "
    "plus tard.\n\n"
    "Format, sans rien autour :\n"
    "- une ligne par point, chaque ligne commencant par « - »\n"
    "- six lignes au maximum\n"
    "- ce que l'utilisateur cherche a faire, ce qui a ete decide, ce qui "
    "reste en suspens\n"
    "- les noms, chiffres et dates cites, tels quels\n\n"
    "N'ecris aucun titre, aucune introduction, aucune conclusion. "
    "N'ecris rien qui ne figure pas ci-dessus."
)


def a_resumer(conversation_id: int) -> tuple[str, list[dict[str, str]], int] | None:
    """Ce qu'il y aurait a plier, sans appeler de modele. `None` s'il n'y a rien.

    Rend le resume precedent, les messages a absorber, et l'identifiant du
    dernier d'entre eux. Separee de `resumer` pour que le fil d'entretien
    puisse decider SANS charger quoi que ce soit — et pour que les bancs
    puissent verifier le seuil sans modele.
    """
    vieux = courant(conversation_id)
    depuis = vieux.jusqu_au_message if vieux else 0
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content
            FROM messages
            WHERE conversation_id = %s AND id > %s AND role IN ('user', 'assistant')
            ORDER BY id
            """,
            (conversation_id, depuis),
        ).fetchall()

    # Le proche reste brut : on ne plie que ce qui est derriere la garde.
    pliables = rows[: max(0, len(rows) - GARDE_BRUTE)]
    if len(pliables) < MESSAGES_AVANT_RESUME:
        return None
    echanges = [
        {"role": r["role"], "content": (r["content"] or "").strip()}
        for r in pliables
        if (r["content"] or "").strip()
    ]
    if not echanges:
        return None
    return (vieux.texte if vieux else "", echanges, pliables[-1]["id"])


def resumer(conversation_id: int) -> str | None:
    """Plie le lointain de cette conversation en quelques lignes. BLOQUE.

    ⚠️ NE JAMAIS APPELER DEPUIS UNE REQUETE.

    Un appel de modele sur deux mille caracteres coute plusieurs secondes sur
    la machine de reference. Appele depuis `answer_stream`, il se paierait
    sur la reponse suivante — exactement la panne que l'indexation des images
    a deja provoquee une fois.

    Rend le resume ecrit, ou `None` s'il n'y avait rien a plier.
    """
    from nova.modeles import routage

    travail = a_resumer(conversation_id)
    if travail is None:
        return None
    precedent, echanges, jusqu_a = travail

    transcription = "\n".join(
        f"{'Utilisateur' if m['role'] == 'user' else 'Nova'} : {m['content']}"
        for m in echanges
    )
    # ⚠️ LE RESUME PRECEDENT ENTRE DANS LE SUIVANT, ET C'EST TOUT LE MECANISME.
    #
    # Sans cette ligne, chaque resume ne couvrirait que la tranche qui vient
    # de passer, et le debut de la conversation retomberait du prompt une
    # heure plus tard — le defaut d'origine, avec une etape de plus. En le
    # reinjectant, ce qui compte survit a autant de compressions qu'il faut,
    # et le cout de chacune reste borne par la tranche, pas par la longueur
    # totale de la conversation.
    entree = (
        (f"Resume de ce qui precede :\n{precedent}\n\n" if precedent else "")
        + f"Suite de la conversation :\n{transcription}\n\n"
        + _INSTRUCTIONS
    )

    depart = time.perf_counter()
    texte = routage.generer(
        "extraction",
        [
            {
                "role": "system",
                "content": (
                    "Tu resumes une conversation. Tu n'ecris que ce qui y "
                    "figure : aucun ajout, aucune interpretation."
                ),
            },
            {"role": "user", "content": entree},
        ],
        temperature=0.0,
    )
    texte = _tronquer((texte or "").strip(), RESUME_MAX_CARACTERES)
    if not texte:
        log.warning("[Resume] Le modele n'a rien rendu pour la conversation %d", conversation_id)
        return None

    projet_id = _projet_actif()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO resumes_de_session
                (conversation_id, projet_id, resume, jusqu_au_message)
            VALUES (%s, %s, %s, %s)
            """,
            (conversation_id, projet_id, texte, jusqu_a),
        )
    log.info(
        "[Resume] Conversation %d : %d message(s) plies en %d caracteres (%.1f s).",
        conversation_id,
        len(echanges),
        len(texte),
        time.perf_counter() - depart,
    )
    return texte


def _projet_actif() -> int | None:
    """Le projet en cours, quand il y en a un. Jamais une panne."""
    try:
        from nova.contexte import actif

        projet = actif.projet_actif()
        return projet.id if projet else None
    except Exception as exc:  # noqa: BLE001
        log.debug("[Resume] Projet actif indisponible : %s", exc)
        return None


# ══════════════════════════════════════════════════════════════════════════
#  LE FIL — il attend que ca se taise.
# ══════════════════════════════════════════════════════════════════════════


def conversations_posees(silence_s: float | None = None) -> list[int]:
    """Les conversations dont personne ne parle plus depuis assez longtemps.

    ⚠️ LE SILENCE SE MESURE PAR CONVERSATION, PAS SUR LA MACHINE.

    Le fil d'indexation des images regarde une horloge globale : « Nova
    a-t-elle repondu recemment ». Ici ce serait faux — on peut parler dans
    une conversation pendant qu'une autre, ouverte ce matin, attend son
    resume depuis des heures. `last_message_at` repond exactement a la bonne
    question, et la base la tient deja a jour.

    Le delai se lit A L'APPEL et non dans la signature : une valeur par defaut
    figee a l'import ne suivrait plus le module, et un banc qui la deplace
    croirait tester ce qu'il ne teste pas.
    """
    if silence_s is None:
        silence_s = SILENCE_S
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id
            FROM conversations
            WHERE last_message_at < now() - make_interval(secs => %s)
            ORDER BY last_message_at DESC
            LIMIT 20
            """,
            (silence_s,),
        ).fetchall()
    return [r["id"] for r in rows]


def entretenir(arret: threading.Event) -> None:
    """Le fil. Resume les conversations posees, dort le reste du temps."""
    log.info(
        "Resumes de session : premier passage dans %d s, puis toutes les %d s.",
        int(DEMARRAGE_S),
        int(REPOS_S),
    )
    if arret.wait(DEMARRAGE_S):
        return

    while not arret.is_set():
        try:
            un_passage()
        except Exception as exc:  # noqa: BLE001
            # Un resume rate degrade une conversation longue. Il ne doit
            # jamais arreter le fil : la prochaine tranche reessaiera.
            log.warning("[Resume] Passage interrompu : %s", exc)
        arret.wait(REPOS_S)


def un_passage() -> int:
    """Resume au plus UNE conversation. Rend le nombre de resumes ecrits.

    ⚠️ UNE SEULE PAR PASSAGE, ET C'EST DELIBERE.

    Vingt conversations en retard, c'est vingt appels de modele d'affilee sur
    une machine de 8 Go. Le fil n'est jamais presse : il en fait une, dort une
    minute, et rattrape son retard en vingt minutes que personne ne voit.
    """
    for conversation_id in conversations_posees():
        if a_resumer(conversation_id) is None:
            continue
        return 1 if resumer(conversation_id) else 0
    return 0
