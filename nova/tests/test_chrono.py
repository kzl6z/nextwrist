"""Le chronometre du chemin critique.

CE QUE CE BANC PROTEGE

Un outil de mesure a une contrainte que les autres modules n'ont pas : il doit
etre assez bon marche pour rester allume. Un profileur qu'on active quand ca
rate ne mesure jamais le jour ou ca rate, parce que l'activer change les
conditions — et parce qu'on n'y pense pas.

Les trois proprietes verifiees ici decoulent toutes de la :

    le cout       negligeable devant ce qu'il mesure, sinon on l'eteint
    la borne      Nova tourne des heures ; une file non bornee fuit
    les centiles  une moyenne cache exactement le cas qu'on cherche
"""

from __future__ import annotations

import threading
import time

from nova.core import chrono


def setup_function() -> None:
    chrono.vider()


def test_une_etape_mesuree_apparait_au_releve():
    with chrono.mesurer("etape"):
        time.sleep(0.01)

    stats = chrono.releve()["etape"]
    assert stats["n"] == 1
    assert 5 <= stats["median"] <= 200, stats


def test_une_etape_qui_echoue_est_quand_meme_mesuree():
    """⚠️ UNE PANNE LENTE COUTE SON TEMPS, EXACTEMENT COMME UN SUCCES.

    Une transcription qui part en erreur au bout de huit secondes a fait
    attendre huit secondes. Ne mesurer que les succes rendrait invisibles
    precisement les cas les plus couteux.
    """
    try:
        with chrono.mesurer("qui casse"):
            raise RuntimeError("panne")
    except RuntimeError:
        pass

    assert chrono.releve()["qui casse"]["n"] == 1


def test_la_mediane_et_le_p95_separent_le_normal_de_l_occasionnel():
    """Neuf appels rapides et un lent : c'est le cas reel, pas une figure.

    Une moyenne donnerait 990 ms — ni le cas normal, ni le cas qui derange.
    """
    for _ in range(9):
        chrono.enregistrer("melange", 100.0)
    chrono.enregistrer("melange", 9000.0)

    stats = chrono.releve()["melange"]
    assert stats["median"] == 100.0, "la mediane doit montrer le cas normal"
    assert stats["p95"] > 1000, "le p95 doit montrer le mauvais jour"
    assert stats["max"] == 9000.0


def test_la_fenetre_est_bornee():
    """⚠️ L'OUTIL DE DIAGNOSTIC NE DOIT PAS DEVENIR LA FUITE.

    Nova tourne des heures sur une machine de 8 Go. Une file non bornee
    croitrait a chaque phrase prononcee — le genre de fuite lente qu'on met
    des semaines a soupconner, et qu'on soupconnerait en dernier dans le
    module cense la detecter.
    """
    for i in range(chrono.FENETRE * 3):
        chrono.enregistrer("beaucoup", float(i))

    assert chrono.releve()["beaucoup"]["n"] == chrono.FENETRE


def test_le_cout_du_chronometre_est_negligeable():
    """S'il coutait cher, on l'eteindrait — et on ne mesurerait plus rien."""
    debut = time.perf_counter()
    for _ in range(10_000):
        chrono.enregistrer("cout", 1.0)
    par_appel_us = (time.perf_counter() - debut) / 10_000 * 1e6

    # 20 µs est deja mille fois moins que la plus rapide des etapes reelles
    # (la construction du prompt, ~20 ms). La marge est volontairement large :
    # ce banc doit attraper une regression d'ordre de grandeur, pas la
    # variabilite d'une machine de test partagee.
    assert par_appel_us < 20, f"{par_appel_us:.1f} µs par mesure"


def test_plusieurs_fils_peuvent_mesurer_en_meme_temps():
    """Nova synthetise une phrase pendant que le modele ecrit la suivante."""
    def travailler() -> None:
        for _ in range(100):
            chrono.enregistrer("concurrent", 1.0)

    fils = [threading.Thread(target=travailler) for _ in range(8)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()

    # 800 mesures pour une fenetre de 200 : on verifie qu'aucune n'a fait
    # exploser la structure, pas qu'elles sont toutes la.
    assert chrono.releve()["concurrent"]["n"] == chrono.FENETRE


def test_le_releve_est_vide_au_depart_et_apres_reinitialisation():
    """Un releve vide n'est pas une panne : c'est « personne n'a parle »."""
    assert chrono.releve() == {}

    chrono.enregistrer("quelque chose", 1.0)
    assert chrono.releve() != {}

    chrono.vider()
    assert chrono.releve() == {}


# ══════════════════════════════════════════════════════════════════════════
#  LE POINT D'ENTREE
# ══════════════════════════════════════════════════════════════════════════
def _client():
    from fastapi.testclient import TestClient

    from nova.api.app import app

    return TestClient(app)


def test_le_point_d_entree_rend_les_etapes_et_la_machine():
    chrono.enregistrer("modele — premier jeton", 1234.0)

    corps = _client().get("/performance").json()

    assert corps["etapes"]["modele — premier jeton"]["median"] == 1234.0
    assert "resume" in corps["machine"]
    assert corps["depuis_secondes"] >= 0


def test_la_reinitialisation_permet_de_comparer_avant_et_apres():
    """Sans ce bouton, une optimisation se noie dans l'historique.

    La mediane de deux cents appels bouge a peine quand les vingt derniers
    sont deux fois plus rapides : on ne verrait pas le gain qu'on vient
    d'obtenir.
    """
    chrono.enregistrer("avant", 500.0)
    client = _client()

    assert client.post("/performance/reset").status_code == 204

    assert client.get("/performance").json()["etapes"] == {}
