"""Le passe ne doit remonter que quand la question s'y appuie.

LE DEFAUT, RELEVE EN CONDITIONS REELLES, DEUX TOURS D'AFFILEE

    — « quelle est la carte la plus rare, Pokemon ? »
      Nova repond sur les cartes.
    — « trouve-moi dans mon PC une image ou je tiens une casquette blanche »
      « Je ne trouve pas de CARTE BLANCHE correspondant a un SKATE. »

La carte venait de la question d'avant. On donnait au modele douze messages
precedents sans lui dire lesquels comptaient encore — et un modele de deux
milliards de parametres ne le devine pas.

⚠️ CE BANC PROTEGE LES DEUX SENS, ET LE SECOND EST LE PLUS FRAGILE.

Ne plus rappeler le passe est facile. Continuer a le rappeler quand il faut
l'est moins : « Et on pourrait y vivre ? » n'a aucun sens sans « Parle-moi de
Mars », et c'est pour ce cas precis que le rappel avait ete ecrit. Le casser
en corrigeant l'autre defaut serait un echange perdant.

D'ou la forme : deux listes symetriques, et un banc qui rejoue la sequence
exacte du releve.
"""

from __future__ import annotations

import pytest

from nova.memory.reprise import raison, reprend_le_passe


# ══════════════════════════════════════════════════════════════════════════
#  CE QUI SE SUFFIT A SOI-MEME — le passe brouillerait
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "question",
    [
        # ⚠️ LES DEUX PHRASES DU RELEVE, DANS L'ORDRE.
        "quelle est la carte la plus rare, Pokémon ?",
        "trouve-moi dans mon PC une image où je tiens une casquette blanche",
        # Des questions ordinaires, qui portent leur propre sujet.
        "qu'est-ce qu'un trou noir",
        "parle-moi de Mars",
        "quelle heure est-il",
        "ouvre Roblox",
        "décris la dernière image",
        "monte le son",
        "combien pèse la Terre",
    ],
)
def test_une_question_autonome_ne_rappelle_pas_le_passe(question):
    assert not reprend_le_passe(question), f"{question} — {raison(question)}"


# ══════════════════════════════════════════════════════════════════════════
#  CE QUI NE SE COMPREND PAS SEUL — le passe est indispensable
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "question",
    [
        # ⚠️ LE CAS POUR LEQUEL LE RAPPEL AVAIT ETE ECRIT.
        "Et on pourrait y vivre ?",
        # Un connecteur en tete enchaine sur ce qui precede.
        "donc c'est possible ?",
        "mais alors comment",
        "et celle d'avant",
        # Une reprise sans antecedent.
        "ça veut dire quoi",
        "raconte-moi la suite",
        "et le reste",
        # Une reference explicite.
        "tu disais quoi déjà",
        "explique mieux",
        "répète",
        # Rien qui porte un sujet.
        "pourquoi ?",
        "comment ?",
        "vraiment ?",
        "encore",
        "oui",
        "ok",
    ],
)
def test_une_suite_rappelle_le_passe(question):
    assert reprend_le_passe(question), f"{question} — {raison(question)}"


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ LA LONGUEUR N'EST PAS LE CRITERE
# ══════════════════════════════════════════════════════════════════════════
def test_une_question_courte_peut_etre_autonome():
    """⚠️ MA PREMIERE VERSION SE TROMPAIT EXACTEMENT LA.

    « une phrase courte est une suite » attrapait « parle-moi de Mars »
    (17 caracteres) et « qu'est-ce qu'un trou noir » (24) — deux questions
    parfaitement autonomes, qui auraient donc continue de trainer le passe.

    Ce qui distingue « pourquoi ? » de « parle-moi de Mars » n'est pas la
    longueur : c'est que la seconde porte un SUJET.
    """
    assert not reprend_le_passe("parle-moi de Mars")
    assert not reprend_le_passe("il fait quel temps")
    assert reprend_le_passe("pourquoi ?")


def test_un_connecteur_ne_compte_qu_en_tete_de_phrase():
    """« il pleut ET il vente » n'enchaine sur rien ; « ET il vente ? » si.
    La position porte tout le sens — sans elle, on attraperait la moitie du
    francais."""
    assert not reprend_le_passe("il pleut et il vente sur la Bretagne")
    assert reprend_le_passe("et il vente ?")


def test_les_articles_ne_sont_pas_des_reprises():
    """⚠️ « la », « le », « les » SONT AUSSI DES ARTICLES.

    Les compter comme des reprises ferait repondre VRAI sur presque toute
    phrase francaise — et le rappel redeviendrait systematique, c'est-a-dire
    le defaut qu'on repare.
    """
    assert not reprend_le_passe("la Tour Eiffel mesure combien")
    assert not reprend_le_passe("les planètes du système solaire")


# ══════════════════════════════════════════════════════════════════════════
#  LA RAISON EST DITE — une decision invisible se cherche des heures
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    ("question", "attendu"),
    [
        ("parle-moi de Mars", "autonome"),
        ("et on pourrait y vivre ?", "enchaine"),
        ("raconte-moi la suite", "reprise"),
        ("tu disais quoi déjà", "renvoie"),
        ("pourquoi ?", "aucun sujet"),
    ],
)
def test_la_raison_est_lisible(question, attendu):
    assert attendu in raison(question)


# ══════════════════════════════════════════════════════════════════════════
#  LE BRANCHEMENT REEL
# ══════════════════════════════════════════════════════════════════════════
def test_la_sequence_du_releve_ne_traine_plus_la_carte(monkeypatch):
    """⚠️ LE BANC CENTRAL : LA SEQUENCE EXACTE, BOUT EN BOUT.

    Sans le filtre, la question sur la casquette recevait les cartes Pokemon
    dans son prompt — et la reponse parlait de « carte blanche ».
    """
    from nova import orchestrator

    envoyes: dict = {}

    class ClientDeBanc:
        def stream(self, messages, **k):
            envoyes["messages"] = messages
            return iter(["ok"])

    monkeypatch.setattr(orchestrator, "LLMClient", lambda *a, **k: ClientDeBanc())
    monkeypatch.setattr(
        orchestrator, "build_system_prompt", lambda *a, **k: ("SYS", [])
    )
    monkeypatch.setattr(orchestrator.conversations, "get_or_create", lambda *a: 1)
    monkeypatch.setattr(orchestrator.conversations, "log_message", lambda *a, **k: None)
    monkeypatch.setattr(
        orchestrator.conversations,
        "derniers_echanges",
        lambda *a, **k: [
            {"role": "user", "content": "quelle est la carte la plus rare Pokemon"},
            {"role": "assistant", "content": "L'Evocation est la carte la plus rare."},
        ],
    )

    list(
        orchestrator.answer_stream(
            [
                {
                    "role": "user",
                    "content": (
                        "trouve-moi dans mon PC une image où je tiens une "
                        "casquette blanche"
                    ),
                }
            ]
        )
    )

    prompt = " ".join(m["content"] for m in envoyes["messages"])
    assert "carte" not in prompt.lower(), "le sujet abandonne ne doit pas revenir"
    assert "casquette" in prompt


def test_une_vraie_suite_recoit_toujours_le_passe(monkeypatch):
    """⚠️ L'AUTRE SENS, ET C'EST LE PLUS FRAGILE.

    Corriger le debordement en cassant « Et on pourrait y vivre ? » serait un
    echange perdant : c'est le cas pour lequel le rappel avait ete ecrit.
    """
    from nova import orchestrator

    envoyes: dict = {}

    class ClientDeBanc:
        def stream(self, messages, **k):
            envoyes["messages"] = messages
            return iter(["ok"])

    monkeypatch.setattr(orchestrator, "LLMClient", lambda *a, **k: ClientDeBanc())
    monkeypatch.setattr(
        orchestrator, "build_system_prompt", lambda *a, **k: ("SYS", [])
    )
    monkeypatch.setattr(orchestrator.conversations, "get_or_create", lambda *a: 1)
    monkeypatch.setattr(orchestrator.conversations, "log_message", lambda *a, **k: None)
    monkeypatch.setattr(
        orchestrator.conversations,
        "derniers_echanges",
        lambda *a, **k: [
            {"role": "user", "content": "parle-moi de Mars"},
            {"role": "assistant", "content": "Mars est la quatrieme planete."},
        ],
    )

    list(
        orchestrator.answer_stream(
            [{"role": "user", "content": "Et on pourrait y vivre ?"}]
        )
    )

    prompt = " ".join(m["content"] for m in envoyes["messages"])
    assert "Mars" in prompt, "« y » n'a aucun sens sans la phrase precedente"
