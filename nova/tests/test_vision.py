"""La vision : ce qu'elle regarde, ce qu'elle refuse, et ce qu'elle ne pretend pas.

CE QUE CE BANC PROTEGE

Un modele multimodal ne tourne pas dans un banc d'essai : il pese deux
gigaoctets et il n'y en a pas ici. Ce n'est pas une limite, c'est la forme du
module — le moteur est INJECTE partout, comme la fonction de reponse du
conversationnel et le `proposer` du planificateur. On teste donc tout sauf ce
qui demande vraiment un modele, c'est-a-dire tout ce qui peut se tromper :

    ou l'image est cherchee, et dans quel ordre
    ce qui est refuse, et si le refus dit quoi faire
    ce qui sort du dossier de travail            ← la seule propriete de securite
    ce que la vision NE PRETEND PAS savoir faire

⚠️ LA DERNIERE LIGNE EST LA PLUS IMPORTANTE ICI.

`detecter` pourrait rendre des `Region` : un multimodal generaliste produit
volontiers des coordonnees bien formees et fausses. Un banc qui verifie que
la methode LEVE encore est un banc qui protege contre une regression par
enthousiasme.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nova.core.contrats import Demande, Etape
from nova.vision import Observation, PasEncoreImplemente
from nova.vision.images import (
    ImageIllisible,
    ImageIntrouvable,
    est_une_image,
    la_plus_recente,
    preparer,
    resoudre,
)

#: Le plus petit PNG valide : 1 pixel, 67 octets. Suffit a tout ce qui est
#: teste ici — on ne verifie jamais le CONTENU d'une image, seulement les
#: chemins, les bornes et les formats.
PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001" "0d0a2db4000000004945" "4e44ae426082"
)


def _image(dossier: Path, nom: str = "piece.png") -> Path:
    cible = dossier / nom
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(PNG_1x1)
    return cible


class MoteurDeBanc:
    """Un moteur qui rend une observation fixe et retient ce qu'on lui a donne."""

    def __init__(self) -> None:
        self.vues: list[Path] = []

    def decrire(self, image: Path | str) -> Observation:
        self.vues.append(Path(image))
        return Observation(source=Path(image), description="Une piece cassee.")


# ══════════════════════════════════════════════════════════════════════════
#  LA BORNE — la seule propriete de securite de ce module
# ══════════════════════════════════════════════════════════════════════════
def test_une_image_hors_du_dossier_de_travail_est_refusee(tmp_path):
    """⚠️ LA VISION RACONTE LE CONTENU D'UN FICHIER.

    C'est donc un excellent moyen d'exfiltration si le chemin n'est pas
    borne : « decris ~/.ssh/id_rsa.png » lirait a voix haute ce qu'on a le
    plus interet a garder. Meme regle que `LireFichier`, meme raison.
    """
    racine = tmp_path / "travail"
    racine.mkdir()
    dehors = _image(tmp_path / "ailleurs", "secret.png")

    with pytest.raises(ImageIllisible) as refus:
        resoudre(str(dehors), racine)

    assert "sort du dossier de travail" in str(refus.value)


def test_remonter_avec_des_points_ne_contourne_pas_la_borne(tmp_path):
    """⚠️ COMPARER DES CHAINES NE SUFFIRAIT PAS.

    `data/../../.ssh/cle.png` commence bien par `data/`. Seule une resolution
    reelle attrape ce cas — et c'est exactement celui qu'un attaquant essaie.
    """
    racine = tmp_path / "travail"
    racine.mkdir()
    _image(tmp_path, "vole.png")

    with pytest.raises(ImageIllisible):
        resoudre("sous/../../vole.png", racine)


def test_un_lien_symbolique_vers_l_exterieur_est_refuse(tmp_path):
    """`resolve` suit les liens — c'est pour ca qu'on l'utilise."""
    racine = tmp_path / "travail"
    racine.mkdir()
    dehors = _image(tmp_path / "ailleurs", "secret.png")
    (racine / "innocent.png").symlink_to(dehors)

    with pytest.raises(ImageIllisible) as refus:
        resoudre("innocent.png", racine)

    # Le refus doit porter sur la BORNE, pas sur « fichier absent » : un lien
    # casse leverait aussi, et le banc passerait pour la mauvaise raison.
    assert "sort du dossier de travail" in str(refus.value)


def test_un_chemin_relatif_dans_le_dossier_est_accepte(tmp_path):
    _image(tmp_path / "photos", "piece.png")

    assert resoudre("photos/piece.png", tmp_path).name == "piece.png"


# ══════════════════════════════════════════════════════════════════════════
#  LES REFUS, ET CE QU'ILS DISENT
# ══════════════════════════════════════════════════════════════════════════
def test_un_fichier_absent_est_nomme(tmp_path):
    with pytest.raises(ImageIntrouvable) as absence:
        resoudre("piece.png", tmp_path)

    assert "piece.png" in str(absence.value)


def test_un_fichier_qui_n_est_pas_une_image_est_refuse(tmp_path):
    (tmp_path / "notes.txt").write_text("bonjour")

    with pytest.raises(ImageIllisible) as refus:
        resoudre("notes.txt", tmp_path)

    assert "n'est pas une image" in str(refus.value)


def test_un_dossier_sans_image_dit_quoi_faire(tmp_path):
    """⚠️ « AUCUNE IMAGE » NE SE CORRIGE PAS TOUT SEUL.

    « Depose-la la, ou donne son chemin » se corrige. La difference entre les
    deux messages est la seule chose qui separe une erreur d'un mode d'emploi.
    """
    with pytest.raises(ImageIntrouvable) as absence:
        la_plus_recente(tmp_path)

    assert "Depose-la la" in str(absence.value)


def test_le_heic_est_reconnu_comme_image_meme_sans_savoir_le_lire():
    """⚠️ C'EST LE FORMAT PAR DEFAUT D'UN IPHONE.

    Le classer « pas une image » serait faux et incomprehensible. On l'accepte
    puis on explique ce qui manque pour le convertir — ce sont deux problemes
    differents, et les confondre donne le mauvais remede.
    """
    assert est_une_image(Path("photo.HEIC"))


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("PIL") is not None,
    reason="Pillow est installe : la reduction fonctionne, ce repli ne s'exerce pas",
)
def test_sans_pillow_un_format_indirect_dit_quoi_installer(tmp_path):
    cible = tmp_path / "photo.heic"
    cible.write_bytes(b"pas vraiment du heic")

    with pytest.raises(ImageIllisible) as refus:
        preparer(cible)

    assert "Pillow" in str(refus.value)
    assert '".[vision]"' in str(refus.value)


# ══════════════════════════════════════════════════════════════════════════
#  LA PREPARATION
# ══════════════════════════════════════════════════════════════════════════
def test_une_image_preparee_porte_une_uri_utilisable(tmp_path):
    prete = preparer(_image(tmp_path))

    assert prete.uri.startswith("data:image/")
    assert ";base64," in prete.uri
    assert prete.octets > 0


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("PIL") is None,
    reason="Pillow absent : la reduction ne peut pas etre exercee",
)
def test_une_grande_image_est_reellement_reduite(tmp_path):
    """⚠️ LE PIEGE QUE CE BANC MESURE VRAIMENT.

    Une photo d'iPhone fait 12 megapixels. Encodee en base64 dans un prompt,
    elle pese une quinzaine de megaoctets — que le moteur avale, puis reduit
    lui-meme a 1024 pixels avant de regarder quoi que ce soit. Sans reduction
    prealable, on paie l'envoi et l'attente pour arriver a l'image qu'on
    aurait pu envoyer directement, et le delai de lecture expire en accusant
    le modele.
    """
    import base64
    import io

    from PIL import Image

    grande = tmp_path / "photo.png"
    # RGBA a dessein : un PNG a canal alpha ne s'enregistre pas en JPEG tel
    # quel, et l'erreur qui en sort parle de modes de couleur — pas du fichier
    # qu'on essayait de lire.
    Image.new("RGBA", (3000, 2000), (120, 60, 30, 255)).save(grande)

    prete = preparer(grande, cote_max=1024)

    assert prete.reduite
    assert prete.mime == "image/jpeg"
    assert prete.octets < grande.stat().st_size

    with Image.open(io.BytesIO(base64.b64decode(prete.donnees))) as sortie:
        assert max(sortie.size) == 1024


def test_la_plus_recente_est_bien_la_plus_recente(tmp_path):
    import os
    import time

    ancienne = _image(tmp_path, "ancienne.png")
    time.sleep(0.01)
    recente = _image(tmp_path, "recente.png")
    os.utime(ancienne, (1, 1))

    assert la_plus_recente(tmp_path) == recente


# ══════════════════════════════════════════════════════════════════════════
#  L'AGENT — le seul endroit ou la vision decide de quelque chose
# ══════════════════════════════════════════════════════════════════════════
def test_un_chemin_ecrit_dans_la_demande_est_prefere(tmp_path):
    from nova.agents.vision import Vision

    _image(tmp_path, "attendue.png")
    _image(tmp_path, "autre.png")
    moteur = MoteurDeBanc()

    resultat = Vision(tmp_path, moteur=moteur).executer(
        Etape("Observer", "vision"), Demande(texte="decris attendue.png")
    )

    assert resultat["image"] == "attendue.png"
    assert resultat["image_devinee"] is False


def test_sans_chemin_l_agent_prend_la_plus_recente_et_LE_DIT(tmp_path):
    """⚠️ LE CHAMP `image_devinee` EST LA RAISON D'ETRE DE CE BANC.

    Deviner l'image la plus recente est la bonne lecture de « decris cette
    image ». Mais sans ce champ, une description du mauvais fichier est
    indiscernable d'une description du bon — et personne ne comprendrait
    pourquoi Nova parle d'autre chose.
    """
    from nova.agents.vision import Vision

    _image(tmp_path, "recente.png")
    moteur = MoteurDeBanc()

    resultat = Vision(tmp_path, moteur=moteur).executer(
        Etape("Observer l'objet et son etat", "vision"), Demande(texte="decris cette image")
    )

    assert resultat["image"] == "recente.png"
    assert resultat["image_devinee"] is True


def test_le_chemin_peut_aussi_venir_de_l_etape(tmp_path):
    """Un plan ecrit « Observer piece.png » : l'etape porte l'information."""
    from nova.agents.vision import Vision

    _image(tmp_path, "piece.png")
    _image(tmp_path, "distraction.png")
    moteur = MoteurDeBanc()

    resultat = Vision(tmp_path, moteur=moteur).executer(
        Etape("Observer piece.png", "vision"), Demande(texte="analyse ca")
    )

    assert resultat["image"] == "piece.png"
    assert resultat["image_devinee"] is False


def test_un_mot_ordinaire_ne_devient_pas_un_chemin(tmp_path):
    """⚠️ LE MOTIF EXIGE UNE EXTENSION D'IMAGE, ET C'EST DELIBERE.

    Un motif plus large attraperait « analyse ma trottinette » et fabriquerait
    un chemin a partir d'un mot ordinaire — puis echouerait en accusant un
    fichier qui n'a jamais existe.
    """
    from nova.agents.vision import chemin_cite

    assert chemin_cite("analyse ma trottinette et dis-moi pourquoi") is None
    assert chemin_cite("regarde photos/piece.jpg stp") == "photos/piece.jpg"


def test_l_agent_ne_pretend_jamais_avoir_vu(tmp_path):
    """⚠️ AUCUNE DESCRIPTION VIDE, AUCUN « JE NE DISTINGUE PAS BIEN ».

    Une phrase qui a l'air d'une observation alors que rien n'a ete regarde
    est le pire resultat possible ici : elle est indiscernable d'une vraie
    observation ratee.
    """
    from nova.agents.vision import Vision
    from nova.vision.moteur import VisionIndisponible

    with pytest.raises(VisionIndisponible) as absence:
        Vision(tmp_path, moteur=MoteurDeBanc()).executer(
            Etape("Observer", "vision"), Demande(texte="decris cette image")
        )

    assert "Aucune image" in str(absence.value)


def test_l_agent_borne_aussi_les_chemins_qu_il_lit(tmp_path):
    """La borne vaut pour ce que l'agent trouve, pas seulement pour l'outil."""
    from nova.agents.vision import Vision

    racine = tmp_path / "travail"
    racine.mkdir()
    dehors = _image(tmp_path / "ailleurs", "secret.png")

    with pytest.raises(ImageIllisible):
        Vision(racine, moteur=MoteurDeBanc()).trouver(
            Etape("Observer", "vision"), Demande(texte=f"decris {dehors}")
        )


# ══════════════════════════════════════════════════════════════════════════
#  LE MOTEUR — sans modele, mais avec un client de banc
# ══════════════════════════════════════════════════════════════════════════
class ClientDeBanc:
    """Un client qui retient le message envoye et rend une reponse fixe."""

    def __init__(self, reponse: str = "Une trottinette, roue avant voilee.") -> None:
        self.reponse = reponse
        self.messages: list = []

    def chat(self, messages, *, temperature=None) -> str:
        self.messages = messages
        return self.reponse


def test_l_image_part_bien_dans_le_message(tmp_path):
    """⚠️ LE FORMAT MULTIMODAL EST LE SEUL ENDROIT OU CE MODULE PEUT MENTIR.

    Un message mal forme ne leve pas : le modele recoit le texte seul, decrit
    une image qu'il n'a pas vue, et rend un paragraphe plausible. C'est
    l'hallucination la plus difficile a reperer de tout le projet, parce que
    tout le reste a l'air de marcher.
    """
    from nova.vision.moteur import MoteurOllama

    _image(tmp_path, "piece.png")
    client = ClientDeBanc()

    observation = MoteurOllama(tmp_path, client=client).decrire("piece.png")

    contenu = client.messages[0]["content"]
    genres = [morceau["type"] for morceau in contenu]
    assert genres == ["text", "image_url"]
    assert contenu[1]["image_url"]["url"].startswith("data:image/")
    assert observation.description == "Une trottinette, roue avant voilee."


def test_un_modele_muet_est_signale_pas_masque(tmp_path):
    """Un modele non multimodal rend une chaine vide. Rendre une Observation
    vide ferait passer ca pour « l'image ne montre rien »."""
    from nova.vision.moteur import MoteurOllama, VisionIndisponible

    _image(tmp_path, "piece.png")

    with pytest.raises(VisionIndisponible) as absence:
        MoteurOllama(tmp_path, client=ClientDeBanc("   ")).decrire("piece.png")

    assert "multimodal" in str(absence.value)


def test_les_composants_sortent_en_liste_pas_en_paragraphe(tmp_path):
    """L'etape suivante du plan de diagnostic cherche des pannes par nom de
    piece : un paragraphe l'obligerait a redecouper du texte."""
    from nova.vision.moteur import MoteurOllama

    _image(tmp_path, "piece.png")
    client = ClientDeBanc("- roue avant\n* guidon\n\n  frein arriere  \n")

    composants = MoteurOllama(tmp_path, client=client).identifier_composants("piece.png")

    assert composants == ("roue avant", "guidon", "frein arriere")


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ CE QUE LA VISION NE PRETEND PAS SAVOIR FAIRE
# ══════════════════════════════════════════════════════════════════════════
def test_localiser_dans_l_image_leve_toujours(tmp_path):
    """⚠️ UN BANC CONTRE LA REGRESSION PAR ENTHOUSIASME.

    Un multimodal generaliste rend volontiers des coordonnees : bien formees,
    plausibles, et fausses. Des `Region` fabriquees a partir de ca seraient
    structurees, precises et mensongeres — la pire forme disponible ici.
    """
    from nova.vision.moteur import MoteurOllama

    with pytest.raises(PasEncoreImplemente) as manque:
        MoteurOllama(tmp_path, client=ClientDeBanc()).detecter(tmp_path / "x.png")

    assert "coordonnees" in str(manque.value)


def test_la_video_leve_en_disant_ce_qu_elle_couterait(tmp_path):
    from nova.vision.moteur import MoteurOllama

    with pytest.raises(PasEncoreImplemente) as manque:
        MoteurOllama(tmp_path, client=ClientDeBanc()).analyser_video(tmp_path / "x.mp4")

    assert "images-cles" in str(manque.value)


# ══════════════════════════════════════════════════════════════════════════
#  LA DISPONIBILITE — dire non, et dire pourquoi
# ══════════════════════════════════════════════════════════════════════════
def test_desactivee_la_vision_dit_comment_l_activer():
    """⚠️ UN BOOLEEN SEUL AURAIT ETE INUTILISABLE.

    « non » ne se corrige pas. « la vision est desactivee, mets
    NOVA_VISION_ACTIVE=true » se corrige. C'est la meme raison qui a fait de
    `Resultat` une structure a quatre etats plutot qu'un booleen.
    """
    from nova.vision.moteur import disponible

    utilisable, raison = disponible()

    assert utilisable is False, "la vision doit rester desactivee par defaut"
    assert "NOVA_VISION_ACTIVE" in raison


def test_le_moteur_refuse_de_se_construire_quand_la_vision_est_eteinte(tmp_path):
    from nova.vision.moteur import VisionIndisponible, moteur

    with pytest.raises(VisionIndisponible):
        moteur(tmp_path)


def test_disponible_ne_ment_plus_en_dur():
    """⚠️ CETTE FONCTION RENDAIT `False` EN DUR.

    C'etait exact tant que rien ne voyait. Le jour ou la vision est arrivee,
    elle serait devenue un mensonge — et un mensonge dans une fonction qui
    s'appelle `disponible` est ce qui fait griser un bouton qui marche.
    """
    import inspect

    from nova import vision

    assert "return False" not in inspect.getsource(vision.disponible)
