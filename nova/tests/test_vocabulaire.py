"""Vocabulaire personnel injecte dans la transcription.

Whisper se trompe sur ce qui est rare dans la langue, pas sur ce qui est
rare pour le modele. Releve en conditions reelles :

    « pinata » -> « pierre pienita »

Le seul reglage qui agisse specifiquement la-dessus est l'amorce. Et les
noms propres que l'utilisateur prononce sont exactement ceux que Nova a
deja en memoire.
"""

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
