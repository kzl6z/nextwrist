"""La verification d'un corpus enregistre.

⚠️ CE BANC PROTEGE LES VINGT-CINQ MINUTES DE QUELQU'UN D'AUTRE.

Une personne accepte de lire deux cent quarante-cinq phrases. Si la prise est
mauvaise, on ne le decouvre qu'apres l'entrainement — donc il faut lui demander
de tout recommencer.

L'enregistreur verifie chaque phrase ISOLEMENT : duree, niveau, saturation. Les
trois defauts qui coutent le plus cher ne se voient qu'en comparant les prises
entre elles, ou en regardant a l'interieur d'une prise :

    derive de niveau    la personne s'est eloignee du micro pendant la seance
    bruit de fond       un ventilateur, une rue, un frigo
    blancs en bord      du silence appris comme faisant partie de la parole

Ils ont en commun de ne jamais rendre un fichier invalide. Tout se lit, tout
passe, et le modele sort mediocre sans qu'aucune etape n'ait rien signale.

Les prises de ce banc sont SYNTHETISEES : une somme d'harmoniques sous
enveloppe syllabique, ce qui suffit a exercer les mesures. Enregistrer de la
vraie voix rendrait le banc dependant d'un micro, donc inexecutable en
integration — et c'est justement la mesure qu'on veut verifier, pas l'oreille.
"""

from __future__ import annotations

import importlib.util
import math
import random
import struct
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "verifier_voix", RACINE / "scripts" / "verifier_voix_clone.py"
)
verifier_voix = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verifier_voix)

TAUX = verifier_voix.TAUX_ATTENDU


def _prise(niveau: float, bruit: float, blanc: float = 0.15, gain: float = 1.0):
    """Une fausse prise : silence, parole modulee, silence."""
    from array import array

    aleatoire = random.Random(7)
    echantillons: list[float] = []
    n_blanc = int(blanc * TAUX)

    echantillons += [aleatoire.gauss(0, bruit) for _ in range(n_blanc)]
    for i in range(int(2.0 * TAUX)):
        t = i / TAUX
        enveloppe = 0.5 + 0.5 * math.sin(2 * math.pi * 3.5 * t)
        harmoniques = sum(
            math.sin(2 * math.pi * f * t) / k
            for k, f in enumerate((180, 360, 540, 720), start=1)
        )
        echantillons.append(niveau * enveloppe * harmoniques / 2 + aleatoire.gauss(0, bruit))
    echantillons += [aleatoire.gauss(0, bruit) for _ in range(n_blanc)]

    valeurs = array("h")
    for v in echantillons:
        valeurs.append(max(-32768, min(32767, int(v * gain * 32767))))
    return valeurs


def test_le_plancher_de_bruit_ignore_la_parole():
    """⚠️ LA MOYENNE NE DIRAIT RIEN — ELLE EST DOMINEE PAR LA VOIX.

    C'est tout l'interet du dixieme percentile sur des fenetres de 50 ms : il
    regarde les passages les plus calmes, c'est-a-dire exactement ce qu'on
    cherche a mesurer.
    """
    propre = verifier_voix._plancher_de_bruit(_prise(0.25, 0.0003), TAUX)
    bruyante = verifier_voix._plancher_de_bruit(_prise(0.25, 0.02), TAUX)

    assert bruyante > propre * 5


def test_le_bruit_de_fond_est_detecte():
    """Inaudible quand on parle, parfaitement appris par le modele."""
    valeurs = _prise(0.25, 0.02)
    niveau = verifier_voix._rms(valeurs)
    fond = verifier_voix._plancher_de_bruit(valeurs, TAUX)
    snr = verifier_voix._db(niveau) - verifier_voix._db(fond)

    assert snr < verifier_voix.SNR_MIN_DB


def test_une_prise_propre_passe():
    valeurs = _prise(0.25, 0.0003)
    niveau = verifier_voix._rms(valeurs)
    fond = verifier_voix._plancher_de_bruit(valeurs, TAUX)

    assert verifier_voix._db(niveau) - verifier_voix._db(fond) >= verifier_voix.SNR_MIN_DB


def test_les_blancs_en_bord_sont_mesures():
    """Du silence appris comme faisant partie de la parole.

    C'est le defaut qui donne ces clones qui « hesitent » avant de parler.
    """
    valeurs = _prise(0.25, 0.0003, blanc=1.4)
    fond = verifier_voix._plancher_de_bruit(valeurs, TAUX)
    avant, apres = verifier_voix._blancs(valeurs, TAUX, max(fond * 3, 0.005))

    assert avant > verifier_voix.BLANC_MAX_S
    assert apres > verifier_voix.BLANC_MAX_S


def test_une_prise_serree_ne_declenche_pas_l_alerte():
    valeurs = _prise(0.25, 0.0003, blanc=0.1)
    fond = verifier_voix._plancher_de_bruit(valeurs, TAUX)
    avant, apres = verifier_voix._blancs(valeurs, TAUX, max(fond * 3, 0.005))

    assert avant <= verifier_voix.BLANC_MAX_S
    assert apres <= verifier_voix.BLANC_MAX_S


def test_l_ecretage_est_detecte():
    """Sature, le modele apprend l'ecretage comme un trait de la voix."""
    assert verifier_voix._ecretage(_prise(0.25, 0.0003, gain=6.0)) > verifier_voix.ECRETAGE_MAX
    assert verifier_voix._ecretage(_prise(0.25, 0.0003)) <= verifier_voix.ECRETAGE_MAX


def test_la_derive_de_niveau_se_voit_sur_l_ensemble():
    """⚠️ AUCUNE PRISE ISOLEE NE PEUT MONTRER CE DEFAUT.

    Chacune est parfaitement correcte. C'est leur SUITE qui apprend au modele
    deux distances au micro, et il en rend la moyenne.
    """
    niveaux = [verifier_voix._rms(_prise(0.30 - i * 0.018, 0.0003)) for i in range(12)]
    moitie = len(niveaux) // 2

    debut = sum(niveaux[:moitie]) / moitie
    fin = sum(niveaux[moitie:]) / (len(niveaux) - moitie)
    derive = verifier_voix._db(fin) - verifier_voix._db(debut)

    assert abs(derive) > verifier_voix.DERIVE_MAX_DB

    # ... et une seance constante ne doit surtout pas etre denoncee.
    stables = [verifier_voix._rms(_prise(0.25, 0.0003)) for _ in range(12)]
    debut = sum(stables[:6]) / 6
    fin = sum(stables[6:]) / 6
    assert abs(verifier_voix._db(fin) - verifier_voix._db(debut)) <= verifier_voix.DERIVE_MAX_DB


def test_le_logarithme_de_zero_ne_casse_rien():
    """Un fichier entierement muet ne doit pas faire echouer la verification."""
    assert verifier_voix._db(0.0) < -100
    assert verifier_voix._rms([]) == 0.0
