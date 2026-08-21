"""Vocabulaire personnel injecte dans la transcription.

Whisper se trompe sur ce qui est rare dans la langue, pas sur ce qui est
rare pour le modele. Releve en conditions reelles :

    « pinata » -> « pierre pienita »

Le seul reglage qui agisse specifiquement la-dessus est l'amorce. Et les
noms propres que l'utilisateur prononce sont exactement ceux que Nova a
deja en memoire.
"""

import re

from nova.voice.vocabulaire import BUDGET_AMORCE, construire_amorce, extraire_termes


def test_retrouve_les_noms_propres():
    faits = [
        "Hugo travaille sur le projet Sentinel depuis mars",
        "Il aime la musique de Charles Aznavour",
    ]
    termes = extraire_termes(faits)
    assert "Sentinel" in termes
    assert "Charles" in termes and "Aznavour" in termes


def test_ignore_les_mots_outils_en_debut_de_phrase():
    # Sans ce filtre, « Le », « Il », « Cette » noieraient les vrais termes
    # dans un budget qui est deja etroit.
    termes = extraire_termes(["Le projet avance bien. Il faut finir Sentinel."])
    assert "Le" not in termes
    assert "Il" not in termes
    assert "Sentinel" in termes


def test_garde_un_mot_outil_s_il_est_en_milieu_de_phrase():
    # « Nova » apres une virgule, ou un nom qui ressemble a un mot-outil,
    # doivent survivre : la position les distingue.
    termes = extraire_termes(["Je parle a Nova tous les jours"])
    assert "Nova" in termes


def test_ne_repete_pas_un_terme():
    termes = extraire_termes(["Sentinel avance", "Sentinel est en retard", "sentinel ok"])
    assert termes.count("Sentinel") == 1


def test_garde_l_ordre_de_premiere_apparition():
    # `list_facts` rend les faits du plus recent au plus ancien : a budget
    # egal, un nom recent vaut mieux qu'un nom ancien.
    termes = extraire_termes(["Aznavour", "Sentinel", "Piñata"])
    assert termes[:2] == ["Aznavour", "Sentinel"]


def test_l_amorce_place_le_vocabulaire_a_la_fin():
    # Whisper ne conserve que la FIN de l'amorce : ce qui compte le plus doit
    # s'y trouver.
    amorce = construire_amorce("Nova, quelle heure est-il ?", ["Sentinel", "Aznavour"])
    assert amorce.startswith("Nova, quelle heure est-il ?")
    assert amorce.rstrip(".").endswith("Aznavour")


def test_l_amorce_respecte_le_budget():
    termes = [f"Terme{i:03d}" for i in range(500)]
    amorce = construire_amorce("Base courte.", termes)
    assert len(amorce) <= BUDGET_AMORCE


def test_un_terme_trop_long_ne_bloque_pas_les_suivants():
    amorce = construire_amorce("Base.", ["A" * 5000, "Sentinel"])
    assert "Sentinel" in amorce


def test_sans_terme_l_amorce_reste_intacte():
    assert construire_amorce("Nova, quelle heure est-il ?", []) == "Nova, quelle heure est-il ?"


# ══════════════════════════════════════════════════════════════════════════
#  L'AMORCE NE DOIT CONTENIR AUCUNE PHRASE RECOPIABLE
#
#  ⚠️ CE BANC REMPLACE SON EXACT CONTRAIRE, ET LE RENVERSEMENT A UN COUT.
#
#  Il exigeait des questions d'exemple completes — « Nova, qu'est-ce qu'un
#  trou noir ? » et quatre autres — pour montrer a Whisper la charniere
#  interrogative. Le raisonnement etait bon et la correction marchait : la
#  construction « qu'est-ce qu'un X » etait mieux reconnue.
#
#  Mais une phrase montree est une phrase COPIABLE. Sur un audio peu clair,
#  Whisper ne rend pas le vide : il rend ce qu'il vient de lire. Releve en
#  conditions reelles, personne n'ayant parle :
#
#      Transcription : 2.05 s d'audio → « No, no, va, qu'est-ce qu'un trou noir »
#
#  Nova a repondu, longuement, sur ce trou noir. Une transcription fausse
#  coute une reformulation ; une transcription INVENTEE coute la confiance
#  dans l'assistant — on ne peut plus se fier a rien de ce qu'il entend.
#
#  Ce qu'on perd est reel et assume : les tournures interrogatives sont moins
#  bien reconnues sans exemples. Le garde-fou de `transcribe.py` couvre le cas
#  ou une amorce future en reintroduirait ; ce banc couvre la source.
# ══════════════════════════════════════════════════════════════════════════
def test_l_amorce_ne_fournit_aucune_phrase_a_recopier():
    from nova.settings import Settings

    reglages = Settings()

    for champ, amorce in (
        ("dictee", reglages.whisper_amorce_dictee),
        ("reveil", reglages.whisper_amorce),
    ):
        assert "?" not in amorce, (
            f"l'amorce de {champ} contient une question — Whisper la rendra "
            "un jour comme si elle avait ete prononcee"
        )
        # ⚠️ LE CRITERE EST LA REPRODUCTIBILITE, PAS LA LONGUEUR.
        #
        # Une premiere version de ce banc bornait l'amorce a 200 caracteres.
        # C'etait une approximation : ce qui rend une amorce dangereuse n'est
        # pas sa taille mais le fait qu'un morceau puisse en sortir comme une
        # demande. « qu'est-ce qu'un » est inoffensif quelle que soit la
        # longueur du reste ; « ouvre un nouveau projet » ne l'est pas, meme
        # dans une amorce courte.
        #
        # On interdit donc les ordres COMPLETS — un verbe suivi de son
        # complement — et on laisse les verbes nus, qui orientent le decodage
        # sans pouvoir etre executes.
        executable = re.search(
            r"\b(ouvre|ferme|lance|explique-moi|parle-moi|montre-moi)\s+"
            r"(un|une|le|la|les|des|mon|ma|mes|ce|cette)\b",
            amorce,
            re.IGNORECASE,
        )
        assert not executable, (
            f"l'amorce de {champ} contient un ordre complet : "
            f"« {executable.group(0) if executable else ''} » — Whisper le "
            "rendra un jour comme s'il avait ete prononce"
        )

    # Le mot de reveil reste amorce : sans lui, « Nova » devient « Nouveau ».
    assert "Nova" in reglages.whisper_amorce
    assert "Nova" in reglages.whisper_amorce_dictee
