"""Les deux defauts qui ont transforme une reponse lente en aucune reponse.

CE QUE CES TESTS PROTEGENT

Question « qu'est-ce qu'un trou noir », releve en conditions reelles :
240 737 ms, puis un message de repli disant « je ne sais pas encore traiter
cette demande ». Aucun modele n'avait ecrit un seul mot.

Deux causes, toutes deux invisibles dans le code pris ligne a ligne :

  1. LA HIERARCHIE DES DELAIS ETAIT INVERSEE. L'application attendait Nova
     Core 120 s ; Nova Core attendait Ollama 300 s. Un appelant qui abandonne
     avant son appele ne recoit jamais le vrai diagnostic — il rend le sien,
     qui est faux.

  2. LA MEMOIRE DE LA MACHINE ETAIT LUE EN Go DECIMAUX. 8 Gio se lisent
     « 8,6 Go », et le seuil « <= 8 » du profil ne se declenchait jamais :
     un Mac de 8 Go etait classe « confortable » et recevait un modele de
     5,2 Go pour un budget de 3,6.

Les deux se rattrapent par un test d'une ligne. Aucun ne se voit a la lecture.
"""

import httpx
import pytest

from nova.core import plateforme
from nova.llm import client as llm
from nova.settings import get_settings

# ── 1. La hierarchie des delais ───────────────────────────────────────────

#: Delai que l'application de bureau accorde a Nova Core (brain.js,
#: `DELAI_LOCAL_MS`). Recopie ici a dessein : c'est la contrainte que le
#: reglage Python doit respecter, et un test est le seul endroit ou les deux
#: peuvent se rencontrer.
DELAI_APPLICATION_S = 120.0


def test_nova_core_abandonne_avant_son_appelant():
    """Nova Core doit rendre la main AVANT que l'application ne l'abandonne.

    Sinon le message utile — « Ollama ne repond pas » — n'est jamais
    transmis, et l'application conclut « Nova Core est-il lance ? » alors
    que Nova Core va parfaitement bien.
    """
    assert get_settings().request_timeout < DELAI_APPLICATION_S


def test_il_reste_de_la_marge_pour_transmettre_l_erreur():
    """Assez de marge pour que le diagnostic voyage, pas seulement l'echec."""
    marge = DELAI_APPLICATION_S - get_settings().request_timeout
    assert marge >= 15.0, "trop juste : l'erreur risque d'arriver apres l'abandon"


def test_connecter_et_repondre_ne_partagent_pas_le_meme_delai():
    """Constater une absence doit etre rapide ; attendre une reponse, non.

    Un delai unique oblige a choisir le plus grand, donc a attendre une
    minute pour apprendre qu'un service est eteint.
    """
    delais = llm._delais(90.0)
    assert delais.connect <= 5.0, "constater une absence doit etre rapide"
    assert delais.read == 90.0, "ecrire une reponse a le droit d'etre lent"
    assert delais.connect < delais.read


def test_le_delai_de_connexion_est_le_meme_partout():
    """Toutes les voies d'appel partagent la meme patience de connexion."""
    for lecture in (5.0, 90.0, 180.0):
        assert llm._delais(lecture).connect == llm.CONNEXION_S


def test_les_delais_sont_bien_un_objet_httpx():
    assert isinstance(llm._delais(10.0), httpx.Timeout)


# ── 2. La memoire de la machine ───────────────────────────────────────────


def machine(memoire_go: float) -> plateforme.Machine:
    return plateforme.Machine(
        systeme="macOS", version="14.6.1", architecture="arm64",
        coeurs=8, memoire_go=memoire_go, disque_libre_go=18.0,
    )


def test_un_mac_de_8_go_est_etroit_pas_confortable():
    """Le defaut exact releve sur la machine de reference.

    Avec une conversion en Go decimaux, 8 Gio donnaient 8,6 — et le seuil
    « <= 8 » ne se declenchait pas. Nova annoncait « confortable » a une
    machine qui ne l'est pas, donc n'incitait a rien.
    """
    assert machine(8.0).profil == "etroit"


@pytest.mark.parametrize(
    ("memoire", "attendu"),
    [(8.0, "etroit"), (16.0, "confortable"), (24.0, "confortable"), (32.0, "large")],
)
def test_les_profils_couvrent_les_machines_reelles(memoire, attendu):
    assert machine(memoire).profil == attendu


def test_la_memoire_est_lue_en_gibioctets():
    """8 Gio doivent se lire 8,0 — pas 8,6.

    On verifie l'unite sur la vraie machine : le chiffre rendu doit etre
    coherent avec une puissance de deux, jamais avec une puissance de dix.
    """
    lu = plateforme._memoire_go()
    if lu == 0.0:
        pytest.skip("memoire non detectable sur cette plateforme")
    # Une conversion decimale rendrait ~7,4 % de plus. Un ecart de cet ordre
    # avec la valeur entiere la plus proche trahirait le retour de la faute.
    assert abs(lu - round(lu)) < 0.35 or lu < 4.0


# ── 3. Un modele trop lourd doit se dire ──────────────────────────────────


def test_un_modele_trop_lourd_est_signale(monkeypatch):
    """5,2 Go de modele pour 3,6 Go de budget : ca doit s'ecrire quelque part.

    Sans avertissement, ce defaut ne produit AUCUNE erreur : le modele
    tourne, en paginant sur le disque. La seule trace est le chronometre.
    """
    monkeypatch.setattr(plateforme, "detecter", lambda: machine(8.0))
    alerte = plateforme.modele_trop_lourd("qwen3:8b")
    assert alerte is not None
    assert "qwen3:8b" in alerte
    # L'avertissement doit proposer une sortie, pas seulement constater.
    assert "llama3.2:3b" in alerte


def test_un_modele_qui_tient_ne_dit_rien(monkeypatch):
    """Ne jamais crier quand tout va bien : une alerte permanente ne se lit plus."""
    monkeypatch.setattr(plateforme, "detecter", lambda: machine(8.0))
    assert plateforme.modele_trop_lourd("llama3.2:3b") is None


def test_un_modele_inconnu_ne_declenche_pas_de_fausse_alerte(monkeypatch):
    """Ignorer vaut mieux qu'inventer un poids."""
    monkeypatch.setattr(plateforme, "detecter", lambda: machine(8.0))
    assert plateforme.modele_trop_lourd("un-modele-jamais-vu:42b") is None


def test_les_variantes_de_suffixe_sont_reconnues(monkeypatch):
    """« qwen3:8b-instruct-q4_K_M » pese autant que « qwen3:8b »."""
    monkeypatch.setattr(plateforme, "detecter", lambda: machine(8.0))
    assert plateforme.modele_trop_lourd("qwen3:8b-instruct-q4_K_M") is not None


def test_une_machine_large_accepte_le_gros_modele(monkeypatch):
    monkeypatch.setattr(plateforme, "detecter", lambda: machine(32.0))
    assert plateforme.modele_trop_lourd("qwen3:8b") is None


# ── 4. Le defaut doit tenir sur la machine du projet ──────────────────────


def test_le_modele_par_defaut_tient_sur_la_machine_de_reference():
    """Un defaut qui ne fonctionne pas sur la machine du projet n'est pas un defaut.

    Il valait « qwen3:8b » : 5,2 Go pour un budget de 3,6. Personne ne l'avait
    vu parce qu'un modele trop gros ne produit aucune erreur — il pagine.
    """
    from nova.settings import Settings

    defaut = Settings.model_fields["chat_model"].default
    poids = plateforme.poids_modele_go(defaut)
    assert poids is not None, f"poids de « {defaut} » inconnu : ajoute-le a POIDS_CONNUS"
    assert poids <= machine(8.0).budget_modele_go, (
        f"« {defaut} » pese {poids} Go pour un budget de "
        f"{machine(8.0).budget_modele_go} Go sur l'iMac M1 de reference"
    )


#: Le modele avec lequel `vitesse_mesuree` a ete relevee, et sa mesure.
#: Ces deux valeurs vont ENSEMBLE : changer l'une sans l'autre fait mentir
#: le routeur, qui s'en sert pour juger si un modele est assez rapide.
MODELE_MESURE = "llama3.2:3b"
VITESSE_MESUREE = 28.8


def test_la_vitesse_par_defaut_decrit_bien_le_modele_par_defaut():
    """Les deux reglages par defaut doivent parler du MEME modele.

    C'est un declencheur volontaire, pas une verification de logique : il
    n'existe aucun moyen de deduire d'un chiffre le modele sur lequel il a
    ete releve. Ce test echoue donc des qu'on touche a l'un des deux, et
    rappelle de remesurer plutot que de laisser les valeurs diverger.

    Ce qu'il a rattrape : `vitesse_mesuree` = 28,8 jetons/s relevee avec
    llama3.2:3b, pendant que `chat_model` valait qwen3:8b. Le routeur croyait
    donc qu'un modele de 5,2 Go ecrivait a la vitesse d'un modele de 2,0 Go.
    """
    from nova.settings import Settings

    assert Settings.model_fields["chat_model"].default == MODELE_MESURE, (
        "Le modele par defaut a change. Remesure la vitesse "
        "(uv run python scripts/bench_models.py), reporte-la dans "
        "`vitesse_mesuree`, puis mets ce test a jour."
    )
    assert Settings.model_fields["vitesse_mesuree"].default == VITESSE_MESUREE, (
        "La vitesse par defaut a change sans que le modele change : "
        "s'agit-il bien d'une nouvelle mesure sur " + MODELE_MESURE + " ?"
    )
