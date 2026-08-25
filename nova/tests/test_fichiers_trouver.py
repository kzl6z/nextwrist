"""Retrouver un fichier : le moteur, le classement, et la conversation.

CE QUE CE BANC PROTEGE

    « Nova, retrouve-moi mon releve de compte de 2024 »
        → ~/Documents/Banque/2024/releve-mars.pdf, et Nova l'ouvre.

⚠️ ET IL PROTEGE SURTOUT CE QUE NOVA NE DOIT PAS FAIRE.

Cette fonctionnalite regarde le disque entier. Trois interdits en decoulent,
et chacun a son banc : ne jamais nommer un fichier de clef, ne jamais
descendre dans `~/Library`, ne jamais ouvrir hors des dossiers declares.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest

from nova.fichiers import Trouvaille
from nova.fichiers.moteurs import Parcours, acceptable, interrogation
from nova.fichiers.requete import lire
from nova.fichiers.trouver import bloc, classer, demande_de_fichier, score

MAINTENANT = datetime(2026, 8, 23)


def _poser(racine: Path, chemins: list[str], *, annee: int | None = None) -> None:
    """Cree des fichiers vides, avec une date de modification choisie."""
    import os
    import time

    for relatif in chemins:
        cible = racine / relatif
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text("x")
        if annee:
            quand = time.mktime(datetime(annee, 6, 1).timetuple())
            os.utime(cible, (quand, quand))


@pytest.fixture
def maison(tmp_path, monkeypatch):
    """Un faux dossier personnel, et Nova bornee a lui."""
    from nova.fichiers import trouver

    monkeypatch.setattr(trouver, "dossiers_cherches", lambda: (tmp_path,))
    return tmp_path


# ══════════════════════════════════════════════════════════════════════════
#  LE DECLENCHEMENT
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase",
    [
        "retrouve-moi mon releve de compte de 2024",
        "peux-tu chercher dans mes fichiers ma facture EDF",
        "ou est mon contrat d'assurance",
        "montre-moi mes documents d'impots",
    ],
)
def test_une_demande_de_fichier_se_reconnait(phrase):
    assert demande_de_fichier(phrase), phrase


@pytest.mark.parametrize(
    "phrase",
    [
        # ⚠️ LE VERBE SEUL NE SUFFIT PAS.
        #
        # « trouve-moi une idee de cadeau » emploie exactement le meme verbe.
        # Sans second signal, chaque question partirait fouiller le disque.
        "trouve-moi une idee de cadeau",
        "cherche ce que veut dire ce mot",
        "quelle heure est-il",
        "parle-moi de Mars",
        # Une image se cherche par son CONTENU, dans le catalogue d'images.
        # Cette phrase-la ne doit pas atterrir ici.
        "retrouve-moi l'image avec la casquette",
    ],
)
def test_ce_qui_ne_cherche_pas_un_fichier(phrase):
    assert not demande_de_fichier(phrase), phrase


# ══════════════════════════════════════════════════════════════════════════
#  CE QUE NOVA N'A PAS LE DROIT DE NOMMER
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "chemin",
    [
        "/Users/h/Library/Keychains/login.keychain",
        "/Users/h/.ssh/id_rsa",
        "/Users/h/projet/.env",
        "/Users/h/certs/serveur.pem",
        "/Users/h/Documents/mes_secrets.txt",
        "/Users/h/code/node_modules/paquet/README.md",
        "/Users/h/.config/token.json",
    ],
)
def test_un_fichier_sensible_n_est_jamais_nomme(chemin):
    """⚠️ NOMMER UN FICHIER DE CLEF EST DEJA UN RENSEIGNEMENT.

    Nova ne le lit pas — mais dire « tu as un id_rsa dans ~/.ssh » informe
    quand meme quelqu'un qui ecoute. La recherche voit tout le disque : c'est
    ici que la liste des interdits compte.
    """
    assert not acceptable(Path(chemin))


def test_un_fichier_ordinaire_passe():
    assert acceptable(Path("/Users/h/Documents/Banque/releve-2024.pdf"))


def test_le_parcours_ne_descend_pas_dans_les_zones_interdites(tmp_path):
    """L'elagage se fait AVANT de descendre, pas apres."""
    _poser(
        tmp_path,
        [
            "Documents/releve-2024.pdf",
            "Library/Caches/releve-cache.pdf",
            "code/node_modules/truc/releve.pdf",
            ".cache/releve-cache.pdf",
        ],
    )

    trouves = Parcours((tmp_path,)).chercher(lire("mon releve", aujourdhui=MAINTENANT))

    assert [t.nom for t in trouves] == ["releve-2024.pdf"]


# ══════════════════════════════════════════════════════════════════════════
#  L'INTERROGATION SPOTLIGHT
# ══════════════════════════════════════════════════════════════════════════
def test_l_interrogation_cherche_dans_le_nom_et_dans_le_texte():
    """⚠️ `kMDItemPath` N'EST PAS INDEXE PAR SPOTLIGHT.

    J'avais cherche dedans pour attraper le nom du DOSSIER. Une requete sur
    cet attribut ne rend rien — en silence, sans erreur. Releve sur la
    machine avec une transcription pourtant parfaite : « mes impots de 2024 »
    ne trouvait plus `impots 2024 3.pdf`, que son NOM designait pourtant.

    Le nom du dossier reste cherchable, mais par `_avec_les_dossiers` : un
    dossier est une entree indexee comme une autre.
    """
    question = interrogation(["releve"], tous=True)

    assert "kMDItemFSName" in question
    assert "kMDItemPath" not in question, "cet attribut n'est pas indexe"
    assert "kMDItemTextContent" in question
    assert "*releve*" in question


def test_la_passe_precise_exige_tous_les_mots():
    assert " && " in interrogation(["releve", "compte"], tous=True)
    assert " || " in interrogation(["releve", "extrait"], tous=False)


def test_une_phrase_transcrite_ne_peut_pas_s_echapper():
    """⚠️ LA PHRASE VIENT DE WHISPER, ET FINIT DANS UNE INTERROGATION.

    La liste d'arguments rend deja l'injection impossible. On retire quand
    meme tout ce qui n'est pas alphanumerique : deux garde-fous pour une
    surface qui recoit du texte non maitrise.
    """
    question = interrogation(['releve" || kMDItemFSName == "*'], tous=True)

    # Le mot injecte ressort en un seul bloc alphanumerique : plus de
    # guillemet, plus d'espace, plus d'operateur. Il ne peut donc plus
    # refermer la chaine ni ajouter de condition.
    injecte = question.split("*")[1]
    assert injecte.isalnum(), injecte
    # La STRUCTURE reste celle d'un seul mot cherche : un groupe, deux
    # conditions (le nom et le texte). Le mot « kMDItemFSName » subsiste a
    # l'interieur des guillemets — c'est du texte a chercher, pas un operateur,
    # et c'est precisement la difference qui compte.
    assert question.count("(") == 1
    assert question.count("==") == 2


# ══════════════════════════════════════════════════════════════════════════
#  LE CLASSEMENT
# ══════════════════════════════════════════════════════════════════════════
def _trouvaille(chemin: str, annee: int = 2024, precis: bool = True) -> Trouvaille:
    import time

    quand = time.mktime(datetime(annee, 6, 1).timetuple())
    return Trouvaille(chemin=Path(chemin), modifie=quand, octets=1, precis=precis)


def test_le_dossier_compte_autant_que_le_nom():
    """⚠️ « ~/Documents/Banque/2024/mars.pdf » EST LA REPONSE.

    Son nom ne contient ni « releve » ni « compte ». C'est le CHEMIN qui le
    dit. Un classement qui ne lit que le nom rate exactement les fichiers de
    ceux qui rangent bien.
    """
    recherche = lire("mon releve de compte de 2024", aujourdhui=MAINTENANT)
    range = _trouvaille("/h/Documents/Banque/releve-compte/2024/mars.pdf")
    ailleurs = _trouvaille("/h/Downloads/truc.pdf", annee=2019, precis=False)

    assert score(range, recherche) > score(ailleurs, recherche)


def test_l_annee_dans_le_nom_pese_plus_que_la_date_du_fichier():
    """Un papier recopie en 2025 garde 2024 dans son nom. Le nom dit vrai."""
    recherche = lire("mon releve de 2024", aujourdhui=MAINTENANT)
    nomme = _trouvaille("/h/Documents/releve-2024.pdf", annee=2025)
    date = _trouvaille("/h/Documents/releve.pdf", annee=2024)

    assert score(nomme, recherche) > score(date, recherche)


def test_une_mauvaise_annee_penalise_sans_exclure():
    """⚠️ ON PENALISE, ON N'EXCLUT PAS.

    Un releve de 2024 peut avoir ete recopie : sa date de modification ment.
    L'exclure ferait disparaitre la bonne reponse sans recours.
    """
    recherche = lire("mon releve de compte de 2024", aujourdhui=MAINTENANT)
    vieux = _trouvaille("/h/Documents/releve-compte.pdf", annee=2019)

    note = score(vieux, recherche)

    assert 0 < note < 1.0


def test_un_nom_long_ne_gagne_pas_par_accident():
    """⚠️ LA LECON DU CATALOGUE : UNE PROPORTION, PAS UN COMPTE.

    Un nom bavard attrape des mots au hasard. Le score mesure la part des
    mots CHERCHES qui sont presents, pas combien le nom en contient.
    """
    recherche = lire("mon releve de compte", aujourdhui=MAINTENANT)
    bavard = _trouvaille(
        "/h/rapport-compte-rendu-final-corrige-v3-relecture.pdf", precis=False
    )
    juste = _trouvaille("/h/Documents/releve-compte.pdf")

    assert score(juste, recherche) > score(bavard, recherche)


def test_rien_sous_le_seuil_n_est_propose():
    recherche = lire("mon releve de compte de 2024", aujourdhui=MAINTENANT)
    hasard = _trouvaille("/h/Downloads/chat.png", annee=2011, precis=False)

    assert classer([hasard], recherche) == []


# ══════════════════════════════════════════════════════════════════════════
#  LA CONVERSATION — LE VRAI CABLAGE
# ══════════════════════════════════════════════════════════════════════════
def test_la_phrase_fondatrice_trouve_le_fichier(maison, monkeypatch):
    """LE BANC CENTRAL : la demande telle qu'elle a ete formulee, jusqu'au
    bloc de prompt, en passant par `bloc()` et non par une fonction d'aide."""
    _poser(
        maison,
        [
            "Documents/Banque/releve-compte-2024-03.pdf",
            "Documents/vacances.pdf",
            "Downloads/chat.png",
        ],
        annee=2024,
    )
    ouvertes: list[str] = []
    import nova.outils as outils

    monkeypatch.setattr(
        outils, "executer_outil", lambda nom, **kw: ouvertes.append(kw["chemin"])
    )

    sortie = bloc(
        "Nova, peux-tu me retrouver dans mes fichiers mon releve de compte "
        "ou de revenus qui date de deux mille vingt-quatre ?"
    )

    assert "releve-compte-2024-03.pdf" in sortie
    assert "vacances.pdf" not in sortie
    # ⚠️ ON PROPOSE, ON N'OUVRE PAS : LA PHRASE NE DEMANDAIT QUE DE CHERCHER.
    #
    # Ouvrir sans demander etait defendable quand chaque tour coutait un
    # « Nova ». Dans une conversation ouverte, un tour ne coute rien, et une
    # fenetre qui s'ouvre seule sur le mauvais fichier coute plus qu'une
    # question.
    from nova.voice import session

    assert ouvertes == []
    assert "je te l'ouvre ?" in sortie
    assert session.en_attente() == (
        "ouvrir_fichier",
        {"chemin": str(maison / "Documents/Banque/releve-compte-2024-03.pdf")},
    )


def test_rien_trouve_dit_pourquoi(maison):
    """⚠️ « RIEN TROUVE » A DEUX CAUSES OPPOSEES.

    Le fichier n'existe pas — ou il existe et rien dedans ne se cherche,
    parce qu'il est scanne. Les confondre laisserait quelqu'un reformuler dix
    fois une question qui ne pouvait pas aboutir.
    """
    _poser(maison, ["Documents/vacances.pdf"])

    sortie = bloc("retrouve-moi mon releve de compte de 2024")

    assert "AUCUN fichier" in sortie
    assert "scanne" in sortie


def test_une_question_ordinaire_ne_coute_rien(maison):
    """Le bloc doit rendre `""` sans toucher au disque."""
    assert bloc("quelle heure est-il") == ""
    assert bloc("parle-moi de Mars") == ""


def test_deux_candidats_a_egalite_n_ouvrent_rien(maison, monkeypatch):
    """Meme garde-fou que pour les images et les applications."""
    _poser(
        maison,
        [
            "Documents/releve-compte-2024-mars.pdf",
            "Documents/releve-compte-2024-avril.pdf",
        ],
        annee=2024,
    )
    ouvertes: list[str] = []
    import nova.outils as outils

    monkeypatch.setattr(
        outils, "executer_outil", lambda nom, **kw: ouvertes.append(kw["chemin"])
    )

    sortie = bloc("retrouve-moi mon releve de compte de 2024")

    assert ouvertes == [], "deux fichiers a egalite n'en designent aucun"
    assert "releve-compte-2024" in sortie


def test_le_fichier_trouve_est_retenu_pour_la_suite(maison, monkeypatch):
    """« ouvre-le » doit designer CE fichier, pas autre chose."""
    from nova.vision import focus

    _poser(maison, ["Documents/Banque/releve-compte-2024.pdf"], annee=2024)
    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", lambda nom, **kw: "ouvert")

    bloc("retrouve-moi mon releve de compte de 2024")

    retenu = focus.derniere("fichier")
    assert retenu is not None
    assert retenu.chemin.name == "releve-compte-2024.pdf"


def test_un_pdf_retenu_ne_part_pas_dans_le_moteur_de_vision(maison, monkeypatch):
    """⚠️ LES DEUX RECHERCHES PARTAGENT UNE MEMOIRE. LE GENRE LES SEPARE.

    Sans lui, « decris-moi la photo » juste apres une recherche de releve
    enverrait un PDF a moondream — qui repondrait quelque chose, ce qui est
    pire qu'une erreur.
    """
    from nova.vision import focus
    from nova.vision.regard import image_en_tete_pour

    _poser(maison, ["Documents/releve-compte-2024.pdf"], annee=2024)
    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", lambda nom, **kw: "ouvert")

    bloc("retrouve-moi mon releve de compte de 2024")

    assert focus.derniere("fichier") is not None, "le fichier est bien retenu"
    assert focus.derniere("image") is None, "mais pas comme une image"
    assert image_en_tete_pour("photo") is None


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ LES PAPIERS QUE LE DECLENCHEUR NE CONNAISSAIT PAS
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "phrase",
    [
        # Releve en une phrase : « ca marche avec les cartes d'identite ? ».
        # Non. Le declencheur avait ete ecrit a partir du seul exemple donne
        # — « mon releve de compte » — et ne couvrait donc que la banque.
        # « retrouve-moi ma carte d'identite » ne declenchait RIEN, en
        # silence : Nova repondait comme a une question ordinaire.
        "retrouve-moi ma carte d'identité",
        "où est ma carte d'identité",
        "cherche mon passeport",
        "retrouve mon permis de conduire",
        "cherche ma carte vitale",
        "où est ma carte grise",
        "trouve mon titre de séjour",
        "trouve mon acte de naissance",
        "où est mon livret de famille",
        "retrouve mon ordonnance",
        "trouve-moi mon diplôme",
        "cherche mon attestation d'assurance",
    ],
)
def test_les_papiers_d_identite_declenchent_la_recherche(phrase):
    assert demande_de_fichier(phrase), phrase


@pytest.mark.parametrize(
    "phrase",
    [
        # ⚠️ CES MOTS-LA SONT D'ABORD DU FRANCAIS ORDINAIRE.
        #
        # « carte », « avis », « analyse », « resultat », « sejour » figurent
        # dans les familles de synonymes — ils servent a ELARGIR une
        # recherche, pas a la DECLENCHER. Les accepter comme signal ferait
        # fouiller le disque a chaque question de culture generale.
        "cherche la carte du monde",
        "cherche l'avis des critiques sur ce film",
        "trouve-moi une bonne analyse de ce texte",
        "cherche le résultat du match",
        "trouve-moi un séjour pas cher",
        "trouve-moi une idée de cadeau",
    ],
)
def test_un_mot_ordinaire_ne_declenche_pas_une_fouille(phrase):
    assert not demande_de_fichier(phrase), phrase


def test_le_declencheur_et_l_elargissement_lisent_la_meme_source():
    """⚠️ DEUX LISTES DE VOCABULAIRE AURAIENT DIVERGE DES LA PREMIERE
       CORRECTION.

    L'une saurait reconnaitre « carte d'identite », l'autre saurait l'elargir
    a « passeport » — et personne ne verrait laquelle manque. Ce banc exige
    que tout mot capable de DECLENCHER une recherche sache aussi l'ELARGIR.
    """
    from nova.fichiers.requete import FAMILLES, PAPIERS

    connus = {mot for famille in FAMILLES for mot in famille}
    orphelins = sorted(
        mot
        for mot in PAPIERS
        if " " not in mot and mot not in connus and mot.rstrip("s") not in connus
    )

    assert orphelins == [], (
        f"ces mots declenchent une recherche mais n'elargissent rien : {orphelins}"
    )


def test_une_carte_d_identite_se_retrouve_de_bout_en_bout(maison, monkeypatch):
    """Le vrai cablage, du francais parle jusqu'au fichier ouvert."""
    _poser(
        maison,
        ["Documents/Papiers/carte-identite-recto.pdf", "Documents/vacances.pdf"],
        annee=2024,
    )
    ouvertes: list[str] = []
    import nova.outils as outils

    monkeypatch.setattr(
        outils, "executer_outil", lambda nom, **kw: ouvertes.append(kw["chemin"])
    )

    sortie = bloc("Nova, retrouve-moi ma carte d'identité et ouvre-la")

    assert "carte-identite-recto.pdf" in sortie
    assert "vacances.pdf" not in sortie
    # ⚠️ « ET OUVRE-LA » A DEJA REPONDU A LA QUESTION.
    #
    # Sans ce verbe, Nova proposerait. Avec, la reposer serait ne pas
    # ecouter.
    assert ouvertes == [str(maison / "Documents/Papiers/carte-identite-recto.pdf")]


def test_un_passeport_se_retrouve_par_synonyme(maison, monkeypatch):
    """⚠️ ON DIT « MES PAPIERS D'IDENTITE », LE FICHIER S'APPELLE
       « passeport.pdf ».

    C'est exactement ce que la table de synonymes existe pour rattraper.
    """
    _poser(maison, ["Documents/passeport-2023.pdf"], annee=2023)
    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", lambda nom, **kw: "ouvert")

    sortie = bloc("retrouve-moi ma carte d'identité")

    assert "passeport-2023.pdf" in sortie


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ CE QUE LES JOURNAUX DE LA MACHINE ONT MONTRE
#
#      Recherche de fichier : mots=['besoin', 'impots'] annee=2024
#      Spotlight : 2984 resultats ramenes a 400.
#      Fichiers : 8 candidat(s), 0 retenu(s)
# ══════════════════════════════════════════════════════════════════════════
def test_besoin_n_est_pas_un_mot_a_chercher():
    """⚠️ « j'ai BESOIN que tu me retrouves mes impots » CHERCHAIT « besoin ».

    Pire que du bruit : la passe precise exige que chaque groupe de sens soit
    present, et « besoin » formait son propre groupe. Aucun fichier ne pouvait
    satisfaire la requete — et Nova lisait « aucun fichier correspondant a
    BESOIN IMPOTS de 2024 » a voix haute.
    """
    recherche = lire(
        "j'ai besoin que tu me retrouves mes impôts de 2024", aujourdhui=MAINTENANT
    )

    assert recherche.mots == ("impots",)
    assert recherche.annee == 2024


def test_aucun_commentaire_ne_fuit_dans_les_mots_vides():
    """La liste des mots vides est un `\"\"\".split()` : un `#` y deviendrait un
    mot vide nomme « # », et le commentaire avec."""
    from nova.fichiers.requete import _PROPRES

    assert all(mot.isalpha() for mot in _PROPRES), sorted(
        m for m in _PROPRES if not m.isalpha()
    )


def test_un_synonyme_ne_se_cherche_que_dans_le_nom():
    """⚠️ LA CORRECTION QUI VALAIT 2907 RESULTATS.

    Un fichier dont le NOM porte « avis » est un avis d'imposition. Un fichier
    dont le CONTENU contient « avis » est n'importe quel document francais.
    Chercher les synonymes dans le texte ramenait tout le disque, tronque a
    400 au hasard — et le bon fichier n'y etait plus.
    """
    from nova.fichiers.moteurs import interrogation_par_groupes
    from nova.fichiers.requete import groupes

    recherche = lire("retrouve mes impôts de 2024", aujourdhui=MAINTENANT)
    question = interrogation_par_groupes(groupes(recherche.mots), recherche.mots)

    dans_le_texte = set(re.findall(r'TextContent == "\*(\w+)\*"', question))
    dans_le_nom = set(re.findall(r'FSName == "\*(\w+)\*"', question))

    assert "avis" in dans_le_nom, "le synonyme reste cherchable par le nom"
    assert "avis" not in dans_le_texte, "mais jamais dans le contenu des fichiers"
    assert "taxe" not in dans_le_texte
    # Le mot prononce, lui, garde le droit d'etre cherche dans le texte.
    assert "impots" in dans_le_texte


def test_le_pluriel_prononce_retrouve_le_singulier_ecrit():
    """On dit « mes impotS », l'avis ecrit « impôt sur le revenu »."""
    from nova.fichiers.moteurs import interrogation_par_groupes
    from nova.fichiers.requete import groupes

    recherche = lire("retrouve mes impôts", aujourdhui=MAINTENANT)
    question = interrogation_par_groupes(groupes(recherche.mots), recherche.mots)

    dans_le_texte = set(re.findall(r'TextContent == "\*(\w+)\*"', question))

    assert {"impot", "impots"} <= dans_le_texte, (
        "une variante de nombre n'est pas un synonyme, c'est le meme mot"
    )


def test_chaque_idee_est_exigee_et_pas_seulement_l_une_d_elles():
    """⚠️ ET ENTRE LES IDEES, OU A L'INTERIEUR.

    « facture EDF » veut les deux : un OU ramenait toutes les factures du
    disque plus tout ce qui mentionne EDF.
    """
    from nova.fichiers.moteurs import interrogation_par_groupes
    from nova.fichiers.requete import groupes

    recherche = lire("retrouve ma facture EDF", aujourdhui=MAINTENANT)
    question = interrogation_par_groupes(groupes(recherche.mots), recherche.mots)

    assert " && " in question, question
    # Deux groupes : la famille « facture », et « edf » qui n'en a aucune.
    assert question.count(" && ") == 1


def test_le_meme_mot_ne_s_accroche_pas_a_n_importe_quoi():
    from nova.fichiers.moteurs import _meme_mot

    assert _meme_mot("impots", "impot")
    assert _meme_mot("fiscale", "fiscal")
    assert not _meme_mot("impots", "taxe")
    assert not _meme_mot("avis", "avenant"), "trois lettres communes ne suffisent pas"
    assert not _meme_mot("cv", "cvtheque")


def test_un_avis_d_imposition_se_retrouve_de_bout_en_bout(maison, monkeypatch):
    """La demande exacte de la machine, jusqu'au fichier ouvert."""
    _poser(
        maison,
        [
            "Documents/Impots/avis-imposition-2024.pdf",
            "Documents/vacances.pdf",
            "Documents/Impots/avis-imposition-2019.pdf",
        ],
        annee=2024,
    )
    ouvertes: list[str] = []
    import nova.outils as outils

    monkeypatch.setattr(
        outils, "executer_outil", lambda nom, **kw: ouvertes.append(kw["chemin"])
    )

    sortie = bloc("j'ai besoin que tu me retrouves mes impôts de 2024")

    assert "avis-imposition-2024.pdf" in sortie
    assert "vacances.pdf" not in sortie
    # ⚠️ ET LE NOM CHERCHE EST LISIBLE A VOIX HAUTE.
    #
    # « aucun fichier correspondant a BESOIN IMPOTS de 2024 » etait la phrase
    # reellement prononcee par Nova.
    assert "besoin" not in sortie.lower()


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ LE DOSSIER « avis d impositions » DE LA MACHINE
#
#      impos 2024 1.pdf     ← « impos », sans le t
#      impos 2024 2.pdf     ← « impos », sans le t
#      impots 2024 3.pdf    ← le seul que Nova trouvait
# ══════════════════════════════════════════════════════════════════════════
def test_le_dossier_retrouve_les_fichiers_que_leur_nom_ne_nomme_pas(
    maison, monkeypatch
):
    """⚠️ DEUX AVIS SUR TROIS N'ONT AUCUN MOT CHERCHABLE DANS LEUR NOM.

    Leur DOSSIER les nomme tous les trois. La requete ne regardait que
    `kMDItemFSName` — alors que le classement, lui, lisait deja le chemin
    entier. La requete cherchait moins loin que le classement, qui n'a donc
    jamais eu la chance de faire son travail.
    """
    _poser(
        maison,
        [
            "Desktop/avis d impositions/impos 2024 1.pdf",
            "Desktop/avis d impositions/impos 2024 2.pdf",
            "Desktop/avis d impositions/impots 2024 3.pdf",
            "Desktop/vacances.pdf",
        ],
        annee=2024,
    )
    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", lambda nom, **kw: "ouvert")

    sortie = bloc("retrouve-moi mes avis d'imposition de 2024")

    for nom in ("impos 2024 1.pdf", "impos 2024 2.pdf", "impots 2024 3.pdf"):
        assert nom in sortie, f"{nom} manquait — c'est le dossier qui le nomme"
    assert "vacances.pdf" not in sortie


def test_trois_fichiers_egaux_n_en_ouvrent_aucun(maison, monkeypatch):
    """Nova doit les LISTER, pas en ouvrir un au hasard.

    C'est le meme garde-fou que pour les images et les applications, et c'est
    exactement ce qu'on veut ici : « les deux autres » n'a de sens que si les
    trois ont ete nommes.
    """
    _poser(
        maison,
        [
            "Desktop/avis d impositions/impos 2024 1.pdf",
            "Desktop/avis d impositions/impos 2024 2.pdf",
            "Desktop/avis d impositions/impots 2024 3.pdf",
        ],
        annee=2024,
    )
    ouvertes: list[str] = []
    import nova.outils as outils

    monkeypatch.setattr(
        outils, "executer_outil", lambda nom, **kw: ouvertes.append(kw["chemin"])
    )

    bloc("retrouve-moi mes avis d'imposition de 2024")

    assert ouvertes == [], "trois candidats a egalite n'en designent aucun"


def test_un_mot_parasite_ne_fait_plus_tomber_toute_la_recherche(maison, monkeypatch):
    """⚠️ LA CORRECTION STRUCTURELLE, PLUTOT QU'UN MOT VIDE DE PLUS.

    « les DEUX AUTRES avis d'imposition » : chaque mot inconnu formait une
    idee de plus, qu'aucun fichier ne pouvait couvrir, et TOUS les candidats
    tombaient sous le seuil. Le meme defaut est revenu trois fois avec un mot
    different — « besoin », « tiens », « autres ».

    Ce sont maintenant les RESULTATS qui tranchent : une idee que pas un seul
    fichier ne porte sort du calcul.
    """
    from nova.fichiers.trouver import groupes_utiles

    _poser(maison, ["Desktop/avis d impositions/impos 2024 1.pdf"], annee=2024)
    import nova.outils as outils

    monkeypatch.setattr(outils, "executer_outil", lambda nom, **kw: "ouvert")

    # Deux mots inconnus, et un fichier remonte par la passe de repli — la
    # situation exacte de la machine : « les DEUX AUTRES avis d'imposition »
    # formait deux idees de plus qu'aucun fichier ne pouvait couvrir.
    recherche = lire("les zorglub schtroumpf avis d'imposition", aujourdhui=MAINTENANT)
    assert {"zorglub", "schtroumpf"} <= set(recherche.mots)

    trouve = _trouvaille(
        str(maison / "Desktop/avis d impositions/impos 2024 1.pdf"), precis=False
    )

    # ⚠️ ON PASSE PAR `classer`, PAS PAR LA FONCTION D'AIDE.
    #
    # Une premiere version de ce banc appelait `groupes_utiles` directement.
    # Retirer le correctif du cablage la laissait passer — elle verifiait la
    # piece, pas son montage. C'est la meme erreur que le tuple de dossiers et
    # que `image_en_tete_pour` : trois fois dans ce projet.
    assert classer([trouve], recherche), (
        "le mot inconnu ne doit plus faire tomber le fichier sous le seuil"
    )

    utiles = groupes_utiles([trouve], recherche)
    assert not any("zorglub" in g for g in utiles), "l'idee morte est ecartee"


def test_sans_aucune_correspondance_on_garde_tout(maison):
    """Si RIEN n'est couvert, noter sur un ensemble vide donnerait la note
    maximale a tout le monde. On garde alors toutes les idees."""
    from nova.fichiers.trouver import groupes_utiles

    recherche = lire("mon releve de compte", aujourdhui=MAINTENANT)
    hasard = _trouvaille("/h/Downloads/chat.png", annee=2011, precis=False)

    utiles = groupes_utiles([hasard], recherche)

    assert len(utiles) == 1, "le groupe releve/compte est conserve"
    # Et par le cablage : rien ne doit remonter.
    assert classer([hasard], recherche) == []


def test_un_dossier_trouve_rend_les_fichiers_qu_il_contient():
    """⚠️ CE QUI REMPLACE `kMDItemPath`, ET SUR DU SOLIDE.

    Le dossier « avis d impositions » contient `impos 2024 1.pdf` et
    `impos 2024 2.pdf` — deux fichiers dont le NOM ne porte aucun mot
    cherchable. Leur dossier, lui, les nomme : il ressort de la meme requete
    Spotlight, puisqu'un dossier est une entree indexee comme une autre.

    On n'ouvre pas un dossier ; on remplace donc le dossier par ce qu'il
    contient. Le tri se fait en Python, ou `is_dir()` ne ment pas.
    """
    import tempfile

    from nova.fichiers.moteurs import _avec_les_dossiers

    racine = Path(tempfile.mkdtemp())
    dossier = racine / "avis d impositions"
    dossier.mkdir()
    for nom in ("impos 2024 1.pdf", "impos 2024 2.pdf"):
        (dossier / nom).write_text("x")
    seul = racine / "ailleurs.pdf"
    seul.write_text("x")

    rendus = sorted(p.name for p in _avec_les_dossiers([dossier, seul]))

    assert rendus == ["ailleurs.pdf", "impos 2024 1.pdf", "impos 2024 2.pdf"]


def test_un_gros_dossier_ne_deverse_pas_tout_le_classement():
    """Un dossier « Documents » qui correspondrait par accident ne doit pas
    noyer le classement sous dix mille fichiers."""
    import tempfile

    from nova.fichiers.moteurs import FICHIERS_PAR_DOSSIER, _avec_les_dossiers

    dossier = Path(tempfile.mkdtemp()) / "Documents"
    dossier.mkdir()
    for i in range(FICHIERS_PAR_DOSSIER + 15):
        (dossier / f"fichier-{i:03d}.pdf").write_text("x")

    assert len(list(_avec_les_dossiers([dossier]))) == FICHIERS_PAR_DOSSIER


def test_une_entree_disparue_ne_fait_pas_tomber_l_expansion():
    """Spotlight garde des entrees pour des fichiers deplaces : les rendre
    ferait proposer d'ouvrir le vide, mais lever serait pire."""
    from nova.fichiers.moteurs import _avec_les_dossiers

    assert list(_avec_les_dossiers([Path("/nulle/part/du/tout")])) == [
        Path("/nulle/part/du/tout")
    ]
