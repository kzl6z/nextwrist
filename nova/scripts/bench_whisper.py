"""Mesure la PRECISION de la transcription, sur TA voix, sur TA machine.

    uv run python scripts/bench_whisper.py

POURQUOI CET OUTIL EXISTE

J'ai deja tranche deux fois sans mesurer sur cette question, et je me suis
trompe les deux fois — d'abord en passant a `small` (regression de vitesse),
puis en revenant a `base` (regression de precision). Releve en conditions
reelles avec `base` :

    « quel est le diametre de la Terre »  ->  « quelle est-il de germetre… »
    « les planetes du systeme solaire »   ->  « les planeles du systeme… »
    « qu'est-ce qu'un trou noir »         ->  « qu'est-ce qu'en trouvoir »

Aucun de ces mots n'est rare. Ce n'est donc pas un probleme de vocabulaire —
que le lexique personnel saurait corriger — mais de MODELE.

CE QUE CET OUTIL MESURE, ET POURQUOI LES DEUX ENSEMBLE

Une transcription se juge sur deux axes qui s'opposent :

    PRECISION   combien de mots sont justes
    DUREE       combien de temps elle prend

Regarder l'un sans l'autre conduit systematiquement a la mauvaise decision.
Une transcription fausse coute un aller-retour complet — Nova repond a cote,
tu reformules, tu attends de nouveau. Sur cette machine, cet aller-retour
vaut environ six secondes. Une transcription plus lente d'une seconde mais
juste est donc largement gagnante, et c'est exactement le calcul qu'on ne
peut pas faire sans les deux chiffres cote a cote.

COMMENT S'EN SERVIR

1. Enregistre quelques phrases avec le script d'enregistrement affiche a la
   fin, ou depose des .wav dans data/voix-test/ accompagnes d'un .txt du
   meme nom contenant ce que tu as REELLEMENT dit.
2. Lance ce script.
3. Choisis la ligne qui te convient et reporte-la dans .env.

Sans fichiers de reference, le script explique comment en fabriquer et
s'arrete : mesurer sur des phrases inventees ne dirait rien de ta voix, de
ton micro, ni de ton accent.
"""

from __future__ import annotations

import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "data" / "voix-test"

#: Les configurations comparees. `base` est le reglage actuel : il figure en
#: premier pour servir de reference a toutes les autres.
CONFIGURATIONS: tuple[tuple[str, int], ...] = (
    ("base", 1),
    ("base", 5),
    ("small", 1),
    ("small", 5),
    ("medium", 1),
)


# ── Comparer deux phrases ─────────────────────────────────────────────────


def _mots(phrase: str) -> list[str]:
    """Les mots, sans accents ni ponctuation ni majuscules.

    On ne juge pas l'orthographe des accents : Whisper ecrit parfois
    « planetes » et parfois « planètes », et compter ca comme une erreur
    noierait les vraies — celles qui changent le sens.
    """
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFD", phrase) if unicodedata.category(c) != "Mn"
    )
    garde = "".join(c if c.isalnum() or c.isspace() else " " for c in sans_accents.lower())
    return garde.split()


def distance_mots(attendu: list[str], obtenu: list[str]) -> int:
    """Nombre de mots a changer pour passer de l'un a l'autre.

    Levenshtein au niveau des MOTS et non des lettres : ce qui compte est
    combien de mots sont faux, pas de combien de lettres ils le sont.
    « germetre » pour « diametre » est UNE erreur, pas cinq.
    """
    precedente = list(range(len(obtenu) + 1))
    for i, mot_attendu in enumerate(attendu, 1):
        courante = [i]
        for j, mot_obtenu in enumerate(obtenu, 1):
            courante.append(
                min(
                    precedente[j] + 1,                                  # suppression
                    courante[j - 1] + 1,                                # insertion
                    precedente[j - 1] + (mot_attendu != mot_obtenu),    # substitution
                )
            )
        precedente = courante
    return precedente[-1]


@dataclass
class Resultat:
    modele: str
    beam: int
    mots_totaux: int = 0
    erreurs: int = 0
    secondes: float = 0.0
    audio_secondes: float = 0.0
    exemples: list[tuple[str, str]] = None  # (attendu, obtenu) quand ca differe

    def __post_init__(self) -> None:
        if self.exemples is None:
            self.exemples = []

    @property
    def precision(self) -> float:
        """Part des mots corrects, de 0 a 1."""
        if not self.mots_totaux:
            return 0.0
        return max(0.0, 1 - self.erreurs / self.mots_totaux)

    @property
    def temps_reel(self) -> float:
        """Secondes de calcul par seconde d'audio. En dessous de 1, c'est
        plus rapide que la parole elle-meme."""
        return self.secondes / self.audio_secondes if self.audio_secondes else 0.0


# ── Le banc ───────────────────────────────────────────────────────────────


def echantillons() -> list[tuple[Path, str]]:
    """Les paires (audio, ce qui a ete reellement dit)."""
    paires = []
    for audio in sorted(DOSSIER.glob("*.wav")):
        reference = audio.with_suffix(".txt")
        if reference.exists():
            paires.append((audio, reference.read_text(encoding="utf-8").strip()))
    return paires


def mesurer(modele: str, beam: int, paires: list[tuple[Path, str]], amorce: str) -> Resultat:
    from faster_whisper import WhisperModel

    from nova.settings import get_settings

    moteur = WhisperModel(modele, device="cpu", compute_type=get_settings().whisper_compute)
    resultat = Resultat(modele=modele, beam=beam)

    for audio, attendu in paires:
        depart = time.perf_counter()
        segments, info = moteur.transcribe(
            str(audio),
            language="fr",
            beam_size=beam,
            initial_prompt=amorce,
            condition_on_previous_text=False,
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        )
        obtenu = " ".join(s.text.strip() for s in segments).strip()
        resultat.secondes += time.perf_counter() - depart
        resultat.audio_secondes += info.duration

        mots_attendus, mots_obtenus = _mots(attendu), _mots(obtenu)
        resultat.mots_totaux += len(mots_attendus)
        erreurs = distance_mots(mots_attendus, mots_obtenus)
        resultat.erreurs += erreurs
        if erreurs:
            resultat.exemples.append((attendu, obtenu))

    return resultat


def mode_d_emploi() -> None:
    print(f"""
Aucun echantillon dans {DOSSIER}

CE QU'IL FAUT, ET POURQUOI TA PROPRE VOIX

Mesurer sur des enregistrements tiers ne dirait rien : ce qu'on cherche a
savoir, c'est comment le modele se comporte avec TON micro, TA piece et TON
accent. Il faut donc des phrases dites par toi.

1. Cree le dossier :

       mkdir -p {DOSSIER}

2. Enregistre une dizaine de phrases, une par fichier. Le plus simple sur
   Mac est l'application « Dictaphone », puis Fichier > Exporter en .wav.
   Prends des phrases que tu poserais vraiment a Nova, dont celles qui
   echouent aujourd'hui :

       Quel est le diametre de la Terre ?
       Quelles sont les planetes du systeme solaire ?
       Qu'est-ce qu'un trou noir ?
       Ouvre Discord.
       Qui etait Charles Aznavour ?

3. A cote de chaque `.wav`, un `.txt` du MEME nom contenant exactement ce que
   tu as dit :

       {DOSSIER}/01.wav
       {DOSSIER}/01.txt   ->  Quel est le diametre de la Terre ?

4. Relance :

       uv run python scripts/bench_whisper.py

Dix phrases suffisent pour trancher. Vingt donnent un chiffre plus stable.
""")


def main() -> int:
    paires = echantillons()
    if not paires:
        mode_d_emploi()
        return 1

    from nova import orchestrator

    amorce = orchestrator.amorce_dictee()
    duree_totale = 0.0

    print(f"\n{len(paires)} phrase(s) de reference, amorce de {len(amorce)} caracteres.")
    print("Le premier passage de chaque modele inclut son telechargement.\n")

    resultats: list[Resultat] = []
    for modele, beam in CONFIGURATIONS:
        print(f"  {modele} (beam {beam})… ", end="", flush=True)
        try:
            resultat = mesurer(modele, beam, paires, amorce)
        except Exception as exc:  # noqa: BLE001
            print(f"impossible : {exc}")
            continue
        resultats.append(resultat)
        duree_totale = resultat.audio_secondes
        print(f"{resultat.precision:.1%} de mots justes, {resultat.secondes:.1f} s")

    if not resultats:
        print("\nAucune configuration n'a pu etre mesuree.")
        return 1

    print(f"\n{'modele':10} {'beam':>5} {'mots justes':>12} {'duree':>9} {'x temps reel':>13}")
    print("─" * 54)
    reference = resultats[0]
    for r in resultats:
        marque = "  <- actuel" if r is reference else ""
        print(
            f"{r.modele:10} {r.beam:>5} {r.precision:>11.1%} "
            f"{r.secondes:>8.1f}s {r.temps_reel:>12.2f}x{marque}"
        )

    print(f"\n({duree_totale:.1f} s d'audio au total)")

    # ── La lecture qui evite de se tromper ──
    #
    # Le chiffre qui decide n'est aucun des deux pris seul : c'est le temps
    # PERDU par erreur. Une transcription fausse coute un aller-retour
    # complet, pas quelques millisecondes.
    print("\nCOMMENT LIRE CE TABLEAU")
    print("  Une transcription fausse coute un aller-retour complet — Nova")
    print("  repond a cote, tu reformules, tu attends de nouveau. Sur cette")
    print("  machine, cet aller-retour vaut environ 6 secondes.")
    print()
    for r in resultats:
        supplement = r.secondes - reference.secondes
        erreurs_evitees = reference.erreurs - r.erreurs
        # Une erreur de mot ne provoque pas toujours une reformulation ; on
        # compte prudemment une reformulation toutes les trois erreurs.
        gagne = erreurs_evitees / 3 * 6.0 - supplement
        if r is reference:
            print(f"  {r.modele:8} beam {r.beam} : reference")
        else:
            verdict = "GAGNANT" if gagne > 0 else "perdant"
            print(
                f"  {r.modele:8} beam {r.beam} : {supplement:+.1f}s de calcul, "
                f"{erreurs_evitees:+d} erreurs — {verdict} ({gagne:+.1f}s)"
            )

    pire = max(resultats, key=lambda r: r.erreurs)
    if pire.exemples:
        print(f"\nExemples d'erreurs ({pire.modele}, beam {pire.beam}) :")
        for attendu, obtenu in pire.exemples[:5]:
            print(f"    dit      « {attendu} »")
            print(f"    entendu  « {obtenu} »\n")

    print("Pour appliquer un choix, dans .env :")
    print("    NOVA_WHISPER_MODEL=small")
    print("    NOVA_WHISPER_BEAM=5\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
