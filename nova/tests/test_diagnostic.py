"""Le diagnostic doit nommer juste, sinon il envoie chercher ailleurs.

CE QUE CE FICHIER GARDE

Un diagnostic n'a qu'une qualite : dire ou regarder. Ma premiere version
classait les processus par memoire et totalisait 1,4 Go sur une machine de
8 Go qui paginait — donc elle ne montrait pas le coupable, et elle a coute un
aller-retour a l'utilisateur.

Deux causes, et les deux sont testees ici : les processus enfants n'etaient
pas regroupes, et les identifiants en notation inversee etaient coupes au
mauvais bout.
"""

import importlib.util
from pathlib import Path

import pytest

CHEMIN = Path(__file__).resolve().parent.parent / "scripts" / "diagnostic.py"


@pytest.fixture(scope="module")
def diagnostic():
    specification = importlib.util.spec_from_file_location("diagnostic", CHEMIN)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("chemin", "attendu"),
    [
        # ⚠️ LE CAS QUI A MOTIVE CE TEST.
        #
        # Couper au premier point rangeait les onglets de Safari sous « com »,
        # un nom qui ne veut rien dire — alors qu'ils sont souvent le premier
        # poste de memoire de la machine.
        (
            "/System/Library/Frameworks/WebKit.framework/Versions/A/XPCServices/"
            "com.apple.WebKit.WebContent.xpc/Contents/MacOS/com.apple.WebKit.WebContent",
            "WebContent",
        ),
        ("/Applications/Claude.app/Contents/MacOS/Claude", "Claude"),
        ("/Applications/Spotify.app/Contents/MacOS/Spotify", "Spotify"),
        ("/System/Applications/Mail.app/Contents/MacOS/Mail", "Mail"),
        ("/usr/local/bin/ollama", "ollama"),
        ("python3.11", "python3.11"),          # une version n'est pas un domaine
    ],
)
def test_un_processus_est_nomme_par_ce_qu_on_en_reconnait(diagnostic, chemin, attendu):
    assert diagnostic.nom_court(chemin) == attendu


def test_les_processus_enfants_sont_regroupes(diagnostic, monkeypatch):
    """LE DEFAUT PRINCIPAL DE LA PREMIERE VERSION.

    Un navigateur eclate en vingt processus n'apparait nulle part si on les
    compte separement : chacun pese peu, l'ensemble pese le plus. C'est
    exactement pour ca qu'un classement pouvait totaliser 1,4 Go sur une
    machine de 8 Go a bout de souffle.
    """
    faux_ps = "\n".join(
        [
            "  200000 /Applications/Safari.app/Contents/MacOS/com.apple.WebKit.WebContent",
            "  180000 /Applications/Safari.app/Contents/MacOS/com.apple.WebKit.WebContent",
            "  170000 /Applications/Safari.app/Contents/MacOS/com.apple.WebKit.WebContent",
            "  400000 /Applications/Claude.app/Contents/MacOS/Claude",
            "  entete illisible",
        ]
    )
    monkeypatch.setattr(diagnostic, "_sortie", lambda _: faux_ps)

    classement = diagnostic.voisins()
    premier_go, premier_nom = classement[0]
    assert premier_nom == "WebContent", "les onglets ne sont pas regroupes"
    assert premier_go == pytest.approx((200000 + 180000 + 170000) / 2**20, abs=0.01)
    assert classement[1][1] == "Claude"


def test_une_ligne_illisible_ne_fait_pas_tomber_le_diagnostic(diagnostic, monkeypatch):
    """Un outil de panne qui tombe en panne ne sert a rien."""
    monkeypatch.setattr(diagnostic, "_sortie", lambda _: "n'importe quoi\n\n  abc def\n")
    assert diagnostic.voisins() == []


def test_ollama_est_lu_chez_lui_plutot_que_devine(diagnostic, monkeypatch):
    """⚠️ MA TABLE DE POIDS SOUS-ESTIMAIT LE POSTE LE PLUS LOURD.

    `POIDS_CONNUS` donne le poids du FICHIER. `ollama ps` donne ce qui est
    reellement resident, contexte compris, et l'ecart approche souvent le
    double. Tout ce que j'ai annonce sur l'empreinte de Nova etait donc une
    sous-estimation — et systematiquement du plus gros poste.
    """
    monkeypatch.setattr(diagnostic.shutil, "which", lambda _: "/usr/local/bin/ollama")
    monkeypatch.setattr(
        diagnostic, "_sortie",
        lambda _: "NAME         ID      SIZE     PROCESSOR   UNTIL\n"
                  "llama3.2:3b  a80c    3.5 GB   100% GPU    4 minutes from now\n",
    )
    lignes = diagnostic.ollama_resident()
    assert lignes is not None
    assert any("3.5 GB" in ligne for ligne in lignes)
    assert any("GPU" in ligne for ligne in lignes), "le processeur utilise doit apparaitre"


def test_aucun_modele_charge_se_distingue_d_ollama_absent(diagnostic, monkeypatch):
    """Deux situations opposees qu'une liste vide confondrait.

    « rien de charge » veut dire que la prochaine reponse paiera la lecture
    du disque. « Ollama absent » veut dire qu'il n'y aura pas de reponse du
    tout. Les rendre identiques enverrait chercher la mauvaise panne.
    """
    monkeypatch.setattr(diagnostic.shutil, "which", lambda _: "/usr/local/bin/ollama")
    monkeypatch.setattr(diagnostic, "_sortie", lambda _: "NAME  ID  SIZE  PROCESSOR  UNTIL\n")
    assert diagnostic.ollama_resident() == []

    monkeypatch.setattr(diagnostic.shutil, "which", lambda _: None)
    assert diagnostic.ollama_resident() is None


def test_une_commande_absente_ne_fait_pas_tomber_le_diagnostic(diagnostic):
    """`ps` et `pgrep` n'existent pas partout. Le diagnostic doit rendre une
    reponse vide, pas une trace d'erreur."""
    assert diagnostic._sortie(["commande-qui-n-existe-pas"]) == ""
    assert diagnostic.tourne("processus-improbable-xyz") is False
