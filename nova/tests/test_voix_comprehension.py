"""Le pipeline de comprehension vocale, etage par etage.

    micro -> STT -> nettoyage -> correction -> intention -> validation -> LLM

La regle qui gouverne tout, et que la moitie de ces tests verifie :

    ne jamais deviner. Corriger quand on est sur, demander quand on ne l'est
    pas, et NE RIEN TOUCHER quand la phrase est deja correcte.
"""

import pytest

from nova.voice import phonetique
from nova.voice.comprehension import SEUIL_DOUTEUX, SEUIL_SUR, comprendre
from nova.voice.intentions import reconnaitre
from nova.voice.lexique import Lexique
from nova.voice.nettoyage import nettoyer


@pytest.fixture
def lex() -> Lexique:
    lexique = Lexique()
    lexique.ajouter_tous(
        ["Ollama", "Rafale", "Electron", "Mistral", "Gemma", "Llama",
         "Aznavour", "Sentinel", "Discord", "Spotify"],
        "declare",
    )
    return lexique


# ── Phonetique ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Ollama", "aux lamas"),      # cas reel : aucune lettre commune utile
        ("Electron", "electron"),
        ("Rafale", "raffale"),
        ("bonjour", "bonjours"),      # finale muette
    ],
)
def test_les_homophonies_sont_reconnues(a, b):
    assert phonetique.ressemblance(a, b) > 0.85


@pytest.mark.parametrize(("a", "b"), [("bonjour", "bonsoir"), ("Discord", "Spotify"),
                                      ("chat", "chien"), ("Ollama", "Mistral")])
def test_les_mots_differents_restent_separes(a, b):
    # Sans cette propriete, tout se corrigerait en tout.
    assert phonetique.ressemblance(a, b) < 0.7


# ── Nettoyage ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("entree", "attendu"),
    [
        ("euh ouvre ouvre Discord", "ouvre Discord"),
        ("alors donc euh lance Spotify", "lance Spotify"),
        ("quelle heure il est, non, quel jour on est", "quel jour on est"),
        ("ouvreDiscord", "ouvre Discord"),
    ],
)
def test_le_nettoyage_retire_ce_que_personne_n_a_voulu_dire(entree, attendu):
    assert nettoyer(entree).texte == attendu


@pytest.mark.parametrize(
    "phrase",
    ["ouvre Discord", "bon", "non", "c'est bon", "tres tres bien merci",
     "quelle heure est-il ?"],
)
def test_le_nettoyage_ne_touche_pas_a_une_phrase_saine(phrase):
    assert nettoyer(phrase).texte == phrase


# ── Intentions ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "formulation",
    [
        "Ouvre Discord",
        "Lance Discord",
        "Tu pourrais ouvrir Discord ?",
        "Est-ce que tu peux ouvrir Discord ?",
        "J'aimerais que tu lances Discord s'il te plait",
        "ouvre l'application Discord",
    ],
)
def test_toutes_les_formulations_donnent_la_meme_intention(formulation):
    # L'exigence explicite du projet : quatre facons de dire, une intention.
    intention = reconnaitre(formulation)
    assert intention.nom == "ouvrir_application"
    assert intention.cible == "Discord"


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("Ouvre Chrome", "ouvrir_application"),
        ("Lance Spotify", "ouvrir_application"),
        ("Quel temps fera-t-il demain ?", "meteo"),
        ("Eteins mon PC", "arret_pc"),
        ("Quelle heure est-il ?", "heure"),
        ("Ferme Spotify", "fermer_application"),
        ("monte le son", "volume_haut"),
        ("que sais-tu de moi", "memoire"),
    ],
)
def test_les_intentions_du_cahier_des_charges(phrase, attendu):
    assert reconnaitre(phrase).nom == attendu


@pytest.mark.parametrize(
    "phrase",
    ["bonjour", "Sur quelle planète pourrions-nous vivre ?",
     "je me demande si tu peux ouvrir", "merci beaucoup"],
)
def test_une_phrase_sans_ordre_ne_produit_aucune_intention(phrase):
    assert not reconnaitre(phrase).reconnue


# ── Lexique et correction ─────────────────────────────────────────────────


def test_le_lexique_rattrape_un_nom_propre_massacre(lex):
    corrige, faites = lex.corriger("installe aux lamas sur mon mac")
    assert corrige == "installe Ollama sur mon mac"
    assert faites and faites[0].propose == "Ollama"


def test_le_lexique_ne_touche_pas_a_une_phrase_correcte(lex):
    for phrase in ("bonjour comment vas-tu", "ouvre Discord", "il fait beau aujourd'hui"):
        corrige, faites = lex.corriger(phrase)
        assert corrige == phrase and not faites, phrase


def test_une_correction_incertaine_est_proposee_et_non_appliquee(lex):
    # « as na vour » ressemble a « Aznavour » sans certitude : on demande.
    corrige, faites = lex.corriger("qui etait as na vour")
    assert not faites, "une correction douteuse ne doit jamais etre appliquee"
    assert any(s.propose == "Aznavour" for s in lex.suggestions(corrige))


def test_un_terme_declare_pese_plus_qu_un_terme_appris():
    lexique = Lexique()
    lexique.ajouter("Rafale", "appris")
    faible = lexique.chercher("raffale").confiance
    lexique.ajouter("Rafale", "declare")
    assert lexique.chercher("raffale").confiance >= faible


def test_le_lexique_apprend_par_repetition():
    lexique = Lexique()
    premier = lexique.ajouter("Sentinel", "appris")
    for _ in range(5):
        lexique.ajouter("Sentinel", "appris")
    assert lexique.chercher("Sentinel").terme.occurrences > premier.occurrences


def test_un_mot_trop_court_n_entre_pas_au_lexique():
    # Sur trois lettres, une erreur suffit a en faire un autre mot.
    lexique = Lexique()
    assert lexique.ajouter("PC") is None
    assert len(lexique) == 0


# ── Le pipeline complet ───────────────────────────────────────────────────


def test_une_demande_claire_passe_sans_rien_demander(lex):
    comprise = comprendre("euh ouvre ouvre Discord", lexique=lex)
    assert comprise.sure
    assert comprise.texte == "ouvre Discord"
    assert comprise.intention.nom == "ouvrir_application"


def test_une_correction_sure_est_appliquee_en_silence(lex):
    comprise = comprendre("installe aux lamas", lexique=lex)
    assert comprise.sure and comprise.texte == "installe Ollama"


def test_une_correction_douteuse_declenche_une_question(lex):
    comprise = comprendre("qui etait as na vour", lexique=lex)
    assert comprise.a_confirmer
    assert "Aznavour" in comprise.question()
    assert comprise.question().startswith("As-tu dit")


def test_une_transcription_incertaine_fait_repeter(lex):
    # LE CAS DU CAHIER DES CHARGES. Aucun lexique ne peut reconstruire
    # « pourrions-nous vivre » — mais Nova peut savoir qu'elle n'a pas
    # compris, et c'est infiniment mieux que de repondre a cote.
    comprise = comprendre(
        "Sur quelle planete pour lui en ouvrir", lexique=lex, logprob=-0.75
    )
    assert comprise.incomprise
    assert "répéter" in comprise.question()


def test_une_phrase_correcte_et_bien_transcrite_ne_bouge_pas(lex):
    phrase = "Sur quelle planète pourrions-nous vivre ?"
    comprise = comprendre(phrase, lexique=lex, logprob=-0.10)
    assert comprise.sure
    assert comprise.texte == phrase


def test_un_decoupage_rate_est_detecte(lex):
    comprise = comprendre("a le de la un", lexique=lex)
    assert comprise.incomprise


def test_le_pipeline_ne_leve_jamais(lex):
    for entree in ("", "   ", "?", "euh", "a", "!!!"):
        comprise = comprendre(entree, lexique=lex)
        assert isinstance(comprise.confiance, float)


def test_sans_lexique_le_pipeline_fonctionne_quand_meme():
    # Chaque capacite est facultative : l'absence de lexique degrade la
    # finesse, jamais la capacite a comprendre.
    comprise = comprendre("euh ouvre ouvre Discord")
    assert comprise.texte == "ouvre Discord"
    assert comprise.intention.nom == "ouvrir_application"


def test_les_seuils_sont_coherents():
    assert 0 < SEUIL_DOUTEUX < SEUIL_SUR <= 1.0


def test_les_raisons_expliquent_toujours_la_decision(lex):
    comprise = comprendre("euh ouvre ouvre Discord", lexique=lex)
    assert comprise.raisons, "une decision sans raison est indebogable"


# ── Le determinant en tete de cible ───────────────────────────────────────
#
# « ouvre l'application Discord » donnait la cible « l'application Discord »
# parce que le bruit etait compare sur la chaine brute (« l'application »)
# alors que la table le contient normalise (« l application »). Deux
# ecritures du meme mot, jamais egales.


@pytest.mark.parametrize(
    "phrase",
    [
        "ouvre l'application Discord",
        "ouvre l application Discord",
        "lance le logiciel Discord",
        "lance le programme Discord",
        "ouvre l'appli Discord s'il te plaît",
        "est-ce que tu peux ouvrir l'application Discord ?",
    ],
)
def test_le_determinant_ne_reste_jamais_colle_a_la_cible(phrase):
    intention = reconnaitre(phrase)
    assert intention.nom == "ouvrir_application"
    assert intention.cible == "Discord", f"{phrase!r} -> {intention.cible!r}"


def test_le_bruit_ne_coupe_pas_un_mot_en_deux():
    # « l » est dans la table du bruit. Sans la garde de frontiere, il
    # couperait « l'appli » et laisserait « appli » — un demi-mot qu'aucun
    # lexique ne retrouve.
    from nova.voice.intentions import _retirer_bruit_initial

    assert _retirer_bruit_initial("l'appli Discord") == "Discord"
    assert _retirer_bruit_initial("Discord") == "Discord"
    # Retirer le bruit ne doit jamais tout consommer.
    assert _retirer_bruit_initial("le") == "le"


def test_une_cible_qui_est_un_vrai_nom_compose_survit():
    intention = reconnaitre("ouvre Visual Studio Code")
    assert intention.cible == "Visual Studio Code"


# ── L'index phonetique est reconstruit une fois, pas a chaque ajout ───────


def test_l_index_suit_les_ajouts_tardifs():
    lexique = Lexique()
    lexique.ajouter("Ollama", "declare")
    assert lexique.chercher("aux lamas").propose == "Ollama"
    # Un terme ajoute APRES une premiere recherche doit etre trouve : c'est
    # exactement ce qu'une indexation paresseuse mal faite casserait.
    lexique.ajouter("Spotify", "declare")
    assert lexique.chercher("spotifi").propose == "Spotify"


def test_charger_un_gros_lexique_reste_lineaire():
    # Reindexer a chaque ajout rendait le chargement quadratique, paye a
    # chaque phrase dictee. On verifie l'ordre de grandeur, pas la vitesse
    # absolue : un test de duree qui mesure la machine est un test instable.
    import time

    def duree(nombre: int) -> float:
        mots = [f"Terme{n:05d}" for n in range(nombre)]
        debut = time.perf_counter()
        Lexique().ajouter_tous(mots, "declare")
        return time.perf_counter() - debut

    petit, grand = duree(100), duree(800)
    # 8x plus de termes : lineaire donne ~8x, quadratique ~64x.
    assert grand < petit * 25, f"chargement non lineaire : {petit:.4f} -> {grand:.4f}"
