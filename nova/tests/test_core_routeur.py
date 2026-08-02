"""Le routeur : quel modele pour quelle tache.

L'utilisateur ne choisit pas l'IA. Nova choisit — et se fonde sur des mesures,
jamais sur des reputations. Les chiffres ci-dessous sont ceux releves par
`scripts/bench_models.py` sur l'iMac M1 de reference.
"""

import pytest

from nova.core.contrats import Modele
from nova.core.routeur import AucunModele, Routeur

# Mesures reelles, application fermee.
LLAMA_3B = Modele("llama3.2:3b", frozenset({"conversation", "raisonnement", "extraction"}),
                  vitesse=28.8, poids=2.0)
LLAMA_1B = Modele("llama3.2:1b", frozenset({"conversation"}), vitesse=42.7, poids=1.3)
QWEN_15B = Modele("qwen2.5:1.5b", frozenset({"conversation", "code"}), vitesse=55.1, poids=1.0)
RAISONNEUR = Modele("qwen3:4b", frozenset({"conversation", "raisonnement"}),
                    vitesse=3.0, poids=2.5, raisonne_a_voix_haute=True)
DISTANT = Modele("claude", frozenset({"conversation", "raisonnement", "code", "vision"}),
                 vitesse=90.0, poids=99.0, distant=True)


def test_prefere_le_plus_capable_et_non_le_plus_rapide():
    # qwen2.5:1.5b ecrit deux fois plus vite, mais les deux sont largement
    # sous le seuil de confort : la vitesse en plus ne s'entend pas, le
    # milliard de parametres en moins si.
    routeur = Routeur((LLAMA_3B, LLAMA_1B, QWEN_15B))
    assert routeur.choisir("vocal").nom == "llama3.2:3b"


def test_sous_le_seuil_la_vitesse_reprend_la_main():
    lent = Modele("gros:8b", frozenset({"conversation"}), vitesse=4.0, poids=5.0)
    routeur = Routeur((lent, LLAMA_1B))
    assert routeur.choisir("vocal").nom == "llama3.2:1b"


def test_un_modele_qui_monologue_est_disqualifie_pour_le_vocal():
    # La lecon la plus chere du projet : qwen3:4b, excellent sur le papier,
    # inutilisable a l'oral.
    routeur = Routeur((RAISONNEUR, LLAMA_1B))
    assert routeur.choisir("vocal").nom == "llama3.2:1b"


def test_mais_il_reste_admissible_pour_du_raisonnement_ecrit():
    routeur = Routeur((RAISONNEUR, LLAMA_3B))
    # Personne n'attend a voix haute : le plus gros gagne.
    assert routeur.choisir("raisonnement").nom == "qwen3:4b"


def test_le_vocal_exige_le_local():
    routeur = Routeur((DISTANT, LLAMA_3B))
    assert routeur.choisir("vocal").nom == "llama3.2:3b"


def test_mais_le_distant_est_admis_quand_rien_ne_l_interdit():
    routeur = Routeur((DISTANT, LLAMA_3B))
    assert routeur.choisir("raisonnement").nom == "claude"


def test_une_capacite_absente_ecarte_le_modele():
    routeur = Routeur((LLAMA_1B, QWEN_15B))
    assert routeur.choisir("code").nom == "qwen2.5:1.5b"


def test_l_echec_explique_ce_qui_a_ete_ecarte():
    # Un mauvais choix silencieux est pire qu'un echec : il se manifeste par
    # des reponses mediocres qu'on attribue au projet entier.
    routeur = Routeur((RAISONNEUR,))
    with pytest.raises(AucunModele) as erreur:
        routeur.choisir("vocal")
    message = str(erreur.value)
    assert "monologue" in message
    assert "bench_models" in message


def test_un_usage_inconnu_est_refuse_avec_la_liste():
    with pytest.raises(AucunModele) as erreur:
        Routeur((LLAMA_3B,)).choisir("telepathie")
    assert "vocal" in str(erreur.value)


def test_declarer_remplace_le_modele_de_meme_nom():
    # Sert a mettre a jour un modele apres une nouvelle mesure, sans doublon.
    routeur = Routeur((LLAMA_3B,))
    routeur.declarer(Modele("llama3.2:3b", frozenset({"conversation"}), vitesse=7.6, poids=2.0))
    assert len(routeur.modeles) == 1
    assert routeur.modeles[0].vitesse == 7.6


def test_expliquer_donne_le_pourquoi():
    explication = Routeur((LLAMA_3B,)).expliquer("vocal")
    assert "llama3.2:3b" in explication and "local" in explication
