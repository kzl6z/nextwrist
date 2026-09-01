"""L'horloge dans le prompt : indispensable, et couteuse quand elle est inutile.

⚠️ CE BLOC A FAIT REPONDRE NOVA A COTE, ET LE RELEVE EST SANS AMBIGUITE.

    « Suivant cette loi-la, nous pourrions retourner dans le passe. »
    → « C'est possible si l'energie est suffisante pour reparer le temps,
       mais cela demande des calculs precis. »
    « Pourrais-tu faire ces calculs ? »
    → « Il reste 23 heures de la journee. Le temps est calme. »

La question ne portait ni sur l'heure ni sur la date. Le modele a cherche des
nombres, n'a trouve que ceux de l'horloge — il etait 23 h — et a repondu
dessus.

⚠️ MAIS LE RETIRER TOUT COURT SERAIT PIRE, ET C'EST TOUT L'EQUILIBRE.

Sans lui, « quelle heure est-il » recoit une heure INVENTEE, avec aplomb.
C'est la premiere question que tout le monde pose a un assistant vocal, et le
premier endroit ou il perd la confiance de son utilisateur.

Les deux erreurs ne coutent donc pas la meme chose, et la reconnaissance
penche volontairement du cote de l'inclusion.
"""

from __future__ import annotations

import pytest

from nova.orchestrator import _question_de_temps


@pytest.mark.parametrize(
    "phrase",
    [
        # Les demandes directes, celles qu'on ne peut pas rater.
        "quelle heure est-il",
        "quelle heure est-il ?",
        "on est quel jour",
        "on est le combien",
        "le combien sommes-nous",
        "quelle est la date",
        # Les indirectes, qui ont autant besoin de l'horloge.
        "c'est quand mon rendez-vous",
        "il te reste combien de temps",
        "aujourd'hui j'ai beaucoup de choses a faire",
        "demain je pars tot",
        "hier j'ai oublie",
        "on se voit lundi",
        "je suis en retard",
        "a quelle heure ouvre la boulangerie",
        "qu'est-ce que j'ai prevu cette semaine",
        "il fait quel temps",
    ],
)
def test_une_question_de_temps_garde_l_horloge(phrase):
    assert _question_de_temps(phrase), phrase


@pytest.mark.parametrize(
    "phrase",
    [
        # ⚠️ LA PHRASE QUI A CAUSE LE DEFAUT, MOT POUR MOT.
        "Pourrais-tu faire ces calculs ?",
        # Celle d'avant, qui parle de temps en physique et non en horloge.
        "Suivant cette loi-la, nous pourrions retourner dans le passe.",
        "parle-moi des trous noirs",
        "ouvre Chrome",
        "quel age as-tu",
        "combien ca coute",
        "retrouve mes impots de 2024",
        "",
    ],
)
def test_ce_qui_n_a_aucun_besoin_de_l_heure(phrase):
    assert not _question_de_temps(phrase), phrase


# ══════════════════════════════════════════════════════════════════════════
#  LE CABLAGE — VERIFIER LA FONCTION SEULE NE PROTEGERAIT RIEN
# ══════════════════════════════════════════════════════════════════════════
def _prompt_pour(monkeypatch, question: str) -> str:
    """Le prompt systeme reellement construit, sans base ni recherche."""
    from nova import orchestrator
    from nova.documents import search as document_search
    from nova.memory import conversations, facts

    monkeypatch.setattr(document_search, "search", lambda *a, **k: [])
    monkeypatch.setattr(facts, "list_facts", lambda *a, **k: [])
    monkeypatch.setattr(conversations, "derniers_echanges", lambda *a, **k: [])
    prompt, _ = orchestrator.build_system_prompt(question)
    return prompt


def test_l_horloge_entre_dans_le_prompt_quand_on_demande_l_heure(monkeypatch):
    assert "Instant present" in _prompt_pour(monkeypatch, "quelle heure est-il ?")


def test_l_horloge_n_entre_pas_dans_le_prompt_pour_une_question_de_calcul(monkeypatch):
    """⚠️ LE BANC QUI PROTEGE LE DEFAUT RELEVE.

    Sans ce branchement, le modele a de quoi repondre « il reste 23 heures de
    la journee » a une question qui ne parlait pas d'horloge. Un bloc inutile
    ne coute pas que du temps de lecture : il donne au modele de quoi
    repondre a cote.
    """
    prompt = _prompt_pour(monkeypatch, "Pourrais-tu faire ces calculs ?")

    assert "Instant present" not in prompt
    assert "il est" not in prompt


def test_le_prompt_est_plus_court_sans_l_horloge(monkeypatch):
    """Un bloc en moins, c'est aussi du temps de lecture en moins — et la
    lecture est la moitie de l'attente sur cette machine."""
    avec = _prompt_pour(monkeypatch, "quelle heure est-il ?")
    sans = _prompt_pour(monkeypatch, "parle-moi des trous noirs")

    assert len(sans) < len(avec)
