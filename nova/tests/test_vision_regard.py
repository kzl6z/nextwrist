"""Regarder une image pendant une conversation.

CE QUE CE BANC PROTEGE

Deux choses, et la seconde est celle qu'on oublie.

1. QUE CA MARCHE. « Nova, analyse l'image que je viens de recevoir » doit
   declencher un regard, sur la bonne image, prise au bon endroit.

2. QUE CA NE COUTE RIEN AU RESTE. Ce branchement est sur le chemin de TOUTES
   les reponses. Le chemin conversationnel a ete ramene de 8-11 s a 1,8-3,1 s
   avant le premier mot au prix de plusieurs tours ; un declencheur trop
   large, ou une detection par modele, rendrait tout le monde lent pour
   servir un cas rare.

⚠️ LA MAJORITE DES BANCS CI-DESSOUS VERIFIENT DONC UN NON.

« raconte-moi l'histoire de la photographie » parle de photos et ne demande
pas de regarder. « analyse ce texte » demande une analyse et ne parle pas
d'image. Chacun de ces deux cas, pris seul, ferait charger un modele de
2 Go — 7 secondes d'attente pour une question qui n'en avait pas besoin.
"""

from __future__ import annotations

import pytest

from nova.vision.regard import bloc, parle_d_une_image

#: Un PNG REELLEMENT valide : 1 pixel, 67 octets.
#:
#: ⚠️ `b"\x89PNG\r\n\x1a\n"` — l'en-tete seul — SUFFISAIT tant que les bancs
#: remplacaient le moteur par un double. Des qu'on fait passer le vrai
#: moteur, Pillow ouvre le fichier et le refuse. Un faux fichier ne trahit
#: rien tant que personne ne le lit vraiment ; c'est la meme lecon que le
#: double du moteur, un etage plus bas.
PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001" "0d0a2db4000000004945" "4e44ae426082"
)


# ══════════════════════════════════════════════════════════════════════════
#  LE DECLENCHEUR — ce qui doit partir
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase",
    [
        "Nova, peux-tu m'analyser l'image s'il te plait ?",
        "analyse l'image que je viens de recevoir",
        "decris cette image",
        "décris-moi la photo",
        "regarde la capture d'ecran",
        "qu'y a-t-il sur cette image ?",
        "que vois-tu sur la photo",
        "montre-moi ce qu'il y a sur ce screenshot",
        "identifie ce qu'il y a sur l'image",
        "observe cette capture",
        # ⚠️ LES TOURNURES ORDINAIRES MANQUAIENT, ET C'EST CE QU'ON DIT.
        #
        # Personne ne formule « decris-moi cette image » quand il peut dire
        # « c'est quoi cette photo ». Un declencheur qui n'attrape que la
        # formulation soignee n'attrape que les demonstrations.
        "c'est quoi cette photo",
        "qu'est-ce qu'il y a sur la photo que je viens de recevoir",
        # ⚠️ ACCENTUES : `re.IGNORECASE` ne fait rien pour les accents, et
        # tous les cas de ce banc etaient ecrits sans, comme les motifs.
        "décris-moi ce cliché",
        "regarde ce schéma",
        "montre-moi la copie d'écran",
        "tu peux me dire ce qu'il y a sur cette image",
        "c'est quoi l'image que j'ai telechargee",
        "qu'est-ce que cette capture montre",
        "Nova peux-tu me décrire la dernière image que j'ai transférée "
        "depuis mon téléphone ?",
    ],
)
def test_une_demande_de_regard_est_reconnue(phrase):
    assert parle_d_une_image(phrase), phrase


def test_un_chemin_ecrit_suffit_sans_le_mot_image():
    """« decris ~/Downloads/x.jpg » n'a pas besoin de dire « image »."""
    assert parle_d_une_image("decris ~/Downloads/casquette.jpg")
    assert parle_d_une_image("qu'est-ce que photos/piece.png")


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ LE DECLENCHEUR — CE QUI NE DOIT SURTOUT PAS PARTIR
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase",
    [
        # Un VERBE de regard, aucun objet visuel.
        "analyse ce texte",
        "analyse cette phrase et corrige-la",
        "decris-moi la situation politique",
        "regarde dans mes documents si j'ai parle de Mars",
        "examine ce raisonnement",
        # Un OBJET visuel, aucun verbe de regard.
        "raconte-moi l'histoire de la photographie",
        "combien de photos ai-je dans mes documents",
        "envoie cette image a Pierre",
        "supprime la capture d'ecran",
        # ⚠️ L'ARTICLE INDEFINI : UNE QUESTION, PAS UN FICHIER.
        #
        # Elargir les verbes aux tournures interrogatives a ouvert cette
        # famille de faux positifs d'un coup. « qu'est-ce qu'UNE photo
        # argentique » est une question de culture generale ; « c'est quoi
        # CETTE photo » demande de regarder. L'article porte toute
        # l'information, et c'est ce qui evite de charger deux gigaoctets
        # pour repondre a une question de vocabulaire.
        "qu'est-ce qu'une photo argentique",
        "c'est quoi une image vectorielle",
        "explique-moi ce qu'est une capture d'ecran",
        "comment fonctionne un scan",
        # Ni l'un ni l'autre — le cas de l'ecrasante majorite.
        "quelle heure est-il",
        "qu'est-ce qu'un trou noir",
        "parle-moi de Mars",
        "bonjour",
        "",
    ],
)
def test_une_demande_ordinaire_ne_declenche_aucun_regard(phrase):
    """⚠️ CHACUN DE CES CAS COUTERAIT 7 SECONDES DE CHARGEMENT.

    Exiger un verbe de regard ET un objet visuel dans la meme phrase ecarte
    les deux familles de faux positifs sans liste d'exceptions.
    """
    assert not parle_d_une_image(phrase), phrase


def test_le_bloc_est_vide_et_gratuit_quand_rien_n_est_demande():
    """⚠️ LE BANC LE PLUS IMPORTANT DU FICHIER.

    `bloc` est appele a l'assemblage de CHAQUE prompt. S'il faisait autre
    chose qu'une expression reguliere avant de rendre `""`, chaque question
    de Nova paierait la vision.
    """
    assert bloc("qu'est-ce qu'un trou noir") == ""
    assert bloc("") == ""


# ══════════════════════════════════════════════════════════════════════════
#  LE BLOC — ce qu'il dit quand ca marche
# ══════════════════════════════════════════════════════════════════════════
def test_le_bloc_porte_l_observation_et_reclame_du_francais(monkeypatch, tmp_path):
    """⚠️ C'EST CE QUI REND UTILISABLE UN MODELE DE VISION ANGLOPHONE.

    moondream decrit en anglais. L'observation devient un bloc de prompt, et
    c'est le modele de langue francophone qui redige la reponse — dans la
    voix de Nova, et par le flux normal, donc par la synthese vocale.
    """
    from nova.vision import Observation, images, moteur

    image = tmp_path / "casquette.png"
    image.write_bytes(PNG_1x1)

    class MoteurAnglais:
        def __init__(self, *a, **k) -> None: ...

        def decrire(self, cible):
            return Observation(source=cible, description="a white cap with 'alo' on it")

    monkeypatch.setattr(moteur, "disponible", lambda: (True, ""))
    monkeypatch.setattr(images, "dossiers_surveilles", lambda: (tmp_path,))
    monkeypatch.setattr(moteur, "MoteurOllama", MoteurAnglais)

    sortie = bloc("Nova, peux-tu m'analyser l'image s'il te plait ?")

    assert "casquette.png" in sortie, "l'image regardee doit etre nommee"
    assert "a white cap" in sortie, "l'observation doit etre transmise"
    assert "francais" in sortie, "la reponse doit etre exigee en francais"
    assert "plus recente" in sortie, "et le fait de l'avoir devinee doit etre dit"


def test_le_bloc_nomme_les_inventions_au_lieu_de_les_interdire(monkeypatch, tmp_path):
    """⚠️ « N'AJOUTE RIEN » N'A PAS SUFFI, ET C'EST MESURE.

    Releve sur la machine : la vision avait bien tourne — la lecture de la
    question etait passee de 1939 ms a 11 631 ms, soit exactement le cout de
    moondream — et nova-leger a repondu « une capture d'ecran de 1920x1080
    pixels ». moondream n'enonce jamais de dimensions : le chiffre etait du
    remplissage, greffe sur une observation par ailleurs exacte.

    Une interdiction abstraite laisse un petit modele juger lui-meme ce qui
    compte comme un ajout. Enumerer les categories qu'il invente reellement
    lui donne une liste a reconnaitre — une tache qu'il sait faire.
    """
    from nova.vision import Observation, images, moteur

    (tmp_path / "capture.png").write_bytes(PNG_1x1)

    class MoteurDeBanc:
        def __init__(self, *a, **k) -> None: ...

        def decrire(self, cible):
            return Observation(source=cible, description="a screenshot with text")

    monkeypatch.setattr(moteur, "disponible", lambda: (True, ""))
    monkeypatch.setattr(images, "dossiers_surveilles", lambda: (tmp_path,))
    monkeypatch.setattr(moteur, "MoteurOllama", MoteurDeBanc)

    sortie = bloc("analyse cette image")

    # L'observation est delimitee : le modele doit pouvoir voir ou elle
    # s'arrete, sans quoi « ne dis que ca » n'a pas de referent.
    assert "<<< a screenshot with text >>>" in sortie
    for invention in ("dimensions", "poids", "format", "dossier", "date"):
        assert invention in sortie, f"« {invention} » doit etre nomme"


def test_un_chemin_nomme_l_emporte_sur_la_plus_recente(monkeypatch, tmp_path):
    from nova.vision import Observation, images, moteur

    (tmp_path / "ancienne.png").write_bytes(PNG_1x1)
    (tmp_path / "voulue.png").write_bytes(PNG_1x1)

    class MoteurDeBanc:
        def __init__(self, *a, **k) -> None: ...

        def decrire(self, cible):
            return Observation(source=cible, description="vu")

    monkeypatch.setattr(moteur, "disponible", lambda: (True, ""))
    monkeypatch.setattr(images, "dossiers_surveilles", lambda: (tmp_path,))
    monkeypatch.setattr(moteur, "MoteurOllama", MoteurDeBanc)

    sortie = bloc("decris ancienne.png")

    assert "ancienne.png" in sortie
    assert "nommee explicitement" in sortie


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ LE BRANCHEMENT REEL — sans double du moteur
#
#  CES DEUX BANCS EXISTENT PARCE QUE LES AUTRES ONT LAISSE PASSER UN DEFAUT.
#
#  `regard.bloc` passe au moteur un TUPLE de dossiers ; `MoteurOllama` faisait
#  `Path(racine)`, ce qui leve sur un tuple. La vision echouait donc a CHAQUE
#  demande vocale — et l'utilisateur recevait une description entierement
#  inventee.
#
#  Les 898 bancs passaient. Tous ceux du regard remplacaient `MoteurOllama`
#  par un double : le seul branchement casse etait precisement celui qu'aucun
#  banc n'exercait. Remplacer par un double la piece qu'on veut verifier, ce
#  n'est pas tester — c'est verifier son propre double.
#
#  Ici on construit le VRAI moteur, et on ne remplace que le client HTTP.
# ══════════════════════════════════════════════════════════════════════════
class ClientDeBanc:
    """Le seul double : ce qui parlerait a Ollama par le reseau."""

    def chat(self, messages, *, temperature=None) -> str:
        return "a white cap with 'alo' on it"


def test_le_moteur_accepte_plusieurs_dossiers(tmp_path):
    """⚠️ LE DEFAUT EXACT, EN UNE LIGNE.

    `Path(tuple)` leve « argument should be a str or an os.PathLike object
    […] not 'tuple' ». Trois caracteres de plomberie, transformes en
    hallucination par la couche du dessus.
    """
    from nova.vision.moteur import MoteurOllama

    telechargements = tmp_path / "Downloads"
    telechargements.mkdir()
    (telechargements / "casquette.png").write_bytes(PNG_1x1)

    moteur = MoteurOllama((telechargements, tmp_path / "Desktop"), client=ClientDeBanc())

    assert moteur.decrire("casquette.png").description == "a white cap with 'alo' on it"


def test_le_regard_traverse_le_vrai_moteur(monkeypatch, tmp_path):
    """La chaine complete de la conversation, sans aucun double de vision.

    Seul le client HTTP est remplace. Si `regard` et `MoteurOllama` cessent
    de s'entendre, ce banc tombe — ce que les precedents ne pouvaient pas
    faire.
    """
    from nova.llm import client as llm_client
    from nova.vision import images, moteur

    (tmp_path / "casquette.png").write_bytes(PNG_1x1)
    monkeypatch.setattr(moteur, "disponible", lambda: (True, ""))
    monkeypatch.setattr(images, "dossiers_surveilles", lambda: (tmp_path,))
    monkeypatch.setattr(llm_client, "LLMClient", lambda **_: ClientDeBanc())

    sortie = bloc("Nova, peux-tu m'analyser l'image s'il te plait ?")

    assert "a white cap" in sortie, sortie
    assert "casquette.png" in sortie
    assert "RIEN" not in sortie, "aucun empechement ne doit etre rapporte"


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ CE QU'IL DIT QUAND CA NE MARCHE PAS
# ══════════════════════════════════════════════════════════════════════════
def test_la_vision_eteinte_produit_un_bloc_qui_dit_pourquoi():
    """⚠️ RENDRE `""` AURAIT ETE LE PIRE CHOIX.

    Le modele aurait alors repondu « je ne peux pas voir les images » de
    lui-meme — une phrase plausible, jamais la bonne raison, et impossible a
    deboguer. Un bloc qui porte la cause exacte se corrige.
    """
    sortie = bloc("analyse cette image")

    assert sortie != "", "un empechement doit etre DIT, pas tu"
    assert "NOVA_VISION_ACTIVE" in sortie
    assert "Reponds EXACTEMENT ceci" in sortie, "la phrase doit etre dictee"
    assert "RIEN" in sortie


def test_aucune_image_trouvee_produit_un_bloc_qui_dit_ou_deposer(monkeypatch, tmp_path):
    from nova.vision import images, moteur

    monkeypatch.setattr(moteur, "disponible", lambda: (True, ""))
    monkeypatch.setattr(images, "dossiers_surveilles", lambda: (tmp_path,))

    sortie = bloc("analyse cette image")

    assert "Aucune image" in sortie
    assert "Reponds EXACTEMENT ceci" in sortie


def test_un_moteur_en_panne_ne_fait_pas_tomber_la_reponse(monkeypatch, tmp_path):
    """⚠️ CETTE FONCTION EST SUR LE CHEMIN DE TOUTES LES REPONSES.

    Une vision en panne doit degrader la reponse, jamais l'empecher. Meme
    regle que la recherche documentaire et la memoire : chaque capacite est
    facultative, et c'est ce qui rend le systeme robuste quand on en ajoute
    dix autres.
    """
    from nova.vision import images, moteur

    (tmp_path / "x.png").write_bytes(PNG_1x1)

    class MoteurCasse:
        def __init__(self, *a, **k) -> None: ...

        def decrire(self, cible):
            raise ConnectionError("Ollama est eteint")

    monkeypatch.setattr(moteur, "disponible", lambda: (True, ""))
    monkeypatch.setattr(images, "dossiers_surveilles", lambda: (tmp_path,))
    monkeypatch.setattr(moteur, "MoteurOllama", MoteurCasse)

    sortie = bloc("analyse cette image")

    # ⚠️ LA RAISON TECHNIQUE RESTE DANS LE JOURNAL, PAS DANS LA BOUCHE DE NOVA.
    #
    # « argument should be a str or an os.PathLike object where __fspath__
    # returns a str, not 'tuple' » est le message exact d'un vrai defaut — et
    # il n'a aucun sens dit a voix haute dans un salon.
    assert "erreur technique" in sortie
    assert "Ollama est eteint" not in sortie, "pas de message de pile a l'oral"
    assert "Reponds EXACTEMENT ceci" in sortie


# ══════════════════════════════════════════════════════════════════════════
#  LES DOSSIERS SURVEILLES — la borne, deplacee mais pas supprimee
# ══════════════════════════════════════════════════════════════════════════
def test_la_plus_recente_traverse_plusieurs_dossiers(tmp_path):
    """⚠️ C'EST LE POINT DE DEPART DE TOUT CE MODULE.

    Une image qui arrive du telephone, d'un mail ou de Chrome atterrit dans
    « Telechargements » ; une capture d'ecran atterrit sur le Bureau. Exiger
    de la deplacer dans `data/` avant d'en parler, c'est demander de ranger
    avant de poser sa question — donc ne jamais s'en servir.
    """
    import os

    from nova.vision.images import la_plus_recente

    telechargements = tmp_path / "Downloads"
    bureau = tmp_path / "Desktop"
    for dossier in (telechargements, bureau):
        dossier.mkdir()
    vieille = telechargements / "vieille.png"
    recente = bureau / "recente.png"
    for fichier in (vieille, recente):
        fichier.write_bytes(PNG_1x1)
    os.utime(vieille, (1, 1))

    assert la_plus_recente([telechargements, bureau]) == recente


def test_un_dossier_configure_absent_ne_fait_pas_tout_echouer(tmp_path):
    """`~/Desktop` peut ne pas exister. Ce n'est pas une raison de refuser de
    regarder dans les autres."""
    from nova.vision.images import la_plus_recente

    reel = tmp_path / "Downloads"
    reel.mkdir()
    (reel / "piece.png").write_bytes(PNG_1x1)

    assert la_plus_recente([reel, tmp_path / "nexiste-pas"]).name == "piece.png"


def test_la_borne_vaut_pour_chacun_des_dossiers(tmp_path):
    """⚠️ ELARGIR LA RECHERCHE N'ELARGIT PAS LE DROIT DE LIRE.

    Ajouter des dossiers deplace la borne, elle ne la supprime pas : hors de
    ceux qui sont declares, Nova refuse toujours.
    """
    from nova.vision.images import ImageIllisible, resoudre

    permis = tmp_path / "Downloads"
    permis.mkdir()
    interdit = tmp_path / "Documents prives"
    interdit.mkdir()
    (interdit / "secret.png").write_bytes(PNG_1x1)

    with pytest.raises(ImageIllisible) as refus:
        resoudre(str(interdit / "secret.png"), [permis])

    assert "sort des dossiers" in str(refus.value)


def test_les_dossiers_caches_sont_ignores(tmp_path):
    """`~/Library`, `.git`, les caches d'applications : des milliers d'images
    qui ne sont jamais « la derniere que j'ai apportee »."""
    from nova.vision.images import ImageIntrouvable, la_plus_recente

    cache = tmp_path / ".cache"
    cache.mkdir()
    (cache / "vignette.png").write_bytes(PNG_1x1)

    with pytest.raises(ImageIntrouvable):
        la_plus_recente(tmp_path)


def test_la_descente_est_bornee_en_profondeur(tmp_path):
    """Un parcours illimite d'un Bureau bien rempli arrive dans la question de
    l'utilisateur, pas dans un fil de fond."""
    from nova.vision.images import ImageIntrouvable, la_plus_recente

    profond = tmp_path / "a" / "b" / "c" / "d"
    profond.mkdir(parents=True)
    (profond / "trop-loin.png").write_bytes(PNG_1x1)

    with pytest.raises(ImageIntrouvable):
        la_plus_recente(tmp_path)

    # Mais deux niveaux restent atteignables : « Bureau/photos/piece.jpg ».
    (tmp_path / "a" / "b" / "atteignable.png").write_bytes(PNG_1x1)
    assert la_plus_recente(tmp_path).name == "atteignable.png"
