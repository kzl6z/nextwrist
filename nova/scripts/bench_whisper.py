"""Mesure la PRECISION de la transcription, sur TA voix, sur TA machine.

    make whisper MODELES=base,small     la question courante, en 2 modeles
    make whisper                        tout, `medium` compris (1,5 Go)

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


def configurations() -> tuple[tuple[str, int], ...]:
    """Les configurations a mesurer, restreintes par `MODELES=` s'il est pose.

    ⚠️ MESURER `medium` COUTE UN TELECHARGEMENT DE ~1,5 Go ET UNE LONGUE
       ATTENTE, POUR UN MODELE QUI NE TIENDRA PAS SUR 8 Go A COTE DU RESTE.

    La question posee est « base ou small ». Y repondre ne devrait pas obliger
    a mesurer ce qu'on n'installera pas :

        MODELES=base,small uv run python scripts/bench_whisper.py

    Sans la variable, on mesure tout : c'est le comportement d'origine, et
    c'est le bon quand on ne sait pas encore ce qu'on cherche.
    """
    import os

    demandes = [m.strip() for m in os.environ.get("MODELES", "").split(",") if m.strip()]
    if not demandes:
        return CONFIGURATIONS
    retenues = tuple((m, b) for m, b in CONFIGURATIONS if m in demandes)
    return retenues or CONFIGURATIONS


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


#: Tous les formats que le decodeur sait lire — c'est-a-dire tous ceux que
#: Whisper lui-meme accepte. Dictaphone exporte en .m4a, QuickTime en .m4a,
#: le script d'enregistrement en .wav : refuser l'un d'eux obligerait a
#: convertir pour rien.
EXTENSIONS = (".wav", ".m4a", ".mp3", ".aiff", ".aif", ".caf", ".flac", ".ogg", ".mp4")


def audios() -> list[Path]:
    """Les enregistrements, quel que soit leur format, dans l'ordre du nom."""
    return sorted(
        (f for f in DOSSIER.iterdir() if f.suffix.lower() in EXTENSIONS),
        key=lambda f: f.name,
    ) if DOSSIER.exists() else []


def echantillons() -> list[tuple[Path, str]]:
    """Les paires (audio, ce qui a ete reellement dit).

    Le texte vient du .txt de meme nom. S'il manque, l'audio est ignore
    plutot que devine : mesurer un ecart contre une phrase supposee
    condamnerait un modele qui n'a rien fait de mal.
    """
    paires = []
    for audio in audios():
        reference = audio.with_suffix(".txt")
        if reference.exists():
            paires.append((audio, reference.read_text(encoding="utf-8").strip()))
    return paires


def mesurer(modele: str, beam: int, paires: list[tuple[Path, str]], amorce: str) -> Resultat:
    """Mesure en passant par LA FONCTION QUE NOVA UTILISE VRAIMENT.

    ⚠️ NE PAS REECRIRE L'APPEL A WHISPER ICI.

    Ce banc appelait `WhisperModel.transcribe()` directement, avec sa propre
    liste de parametres. Il en manquait trois, dont
    `compression_ratio_threshold=2.4` — le garde-fou qui coupe les
    repetitions en boucle. Resultat mesure :

        dit      « Qu'est-ce qu'un trou noir ? »
        entendu  « Qu'est-ce qu'un trou moire ? Qu'est-ce qu'un trou moire ? »

    Nova en production aurait filtre cette repetition. Le banc mesurait donc
    un systeme qui n'existe pas, et sur-estimait le taux d'erreur.

    Un banc qui teste une configuration voisine de la vraie est pire qu'un
    banc absent : il donne une raison chiffree de se tromper. On passe donc
    par `transcribe.transcrire()`, exactement comme l'API — les deux ne
    peuvent plus diverger, meme si quelqu'un ajoute un reglage demain.
    """
    from nova.voice import transcribe

    resultat = Resultat(modele=modele, beam=beam)

    # Charger le modele AVANT de chronometrer. Sinon la premiere phrase de
    # chaque configuration porte le cout du chargement, et un gros modele
    # parait deux fois plus lent qu'il ne l'est reellement a l'usage — ou
    # Nova le garde resident.
    transcribe._modele(modele)

    for audio, attendu in paires:
        octets = audio.read_bytes()
        depart = time.perf_counter()
        transcription = transcribe.transcrire(
            octets, langue="fr", modele=modele, amorce=amorce, beam=beam
        )
        resultat.secondes += time.perf_counter() - depart
        resultat.audio_secondes += transcription.duree

        obtenu = transcription.texte
        mots_attendus, mots_obtenus = _mots(attendu), _mots(obtenu)
        resultat.mots_totaux += len(mots_attendus)
        erreurs = distance_mots(mots_attendus, mots_obtenus)
        resultat.erreurs += erreurs
        if erreurs:
            resultat.exemples.append((attendu, obtenu))

    return resultat


def associer_les_textes() -> int:
    """Ecrit les .txt manquants a partir de la liste de phrases, dans l'ordre.

    POURQUOI CE MODE EXISTE

    Recopier douze phrases dans douze fichiers est fastidieux, et surtout
    c'est la seule etape ou une faute passe INAPERCUE : un decalage d'une
    ligne, et le banc compare chaque phrase a la suivante. Il annoncerait
    alors 20 % de mots justes pour un modele parfait, et on changerait de
    modele pour rien.

    On associe donc par l'ORDRE : premier fichier, premiere phrase. C'est a
    l'utilisateur de nommer ses enregistrements 01, 02, 03… — ce que
    Dictaphone fait deja si on les exporte dans l'ordre.
    """
    from enregistrer_voix import PHRASES

    fichiers = audios()
    if not fichiers:
        print(f"\nAucun enregistrement dans {DOSSIER}\n")
        return 1

    print(f"\n{len(fichiers)} enregistrement(s). Association par l'ordre des noms :\n")
    # `strict=False` a dessein : on peut avoir enregistre huit phrases sur
    # douze, ou en avoir une de trop. S'arreter a la plus courte des deux
    # listes est le comportement voulu — le surplus est signale plus bas.
    for numero, (audio, phrase) in enumerate(zip(fichiers, PHRASES, strict=False), 1):
        texte = audio.with_suffix(".txt")
        etat = "existe deja" if texte.exists() else "ecrit"
        if not texte.exists():
            texte.write_text(phrase, encoding="utf-8")
        print(f"  {numero:2}. {audio.name:24} → « {phrase} »   [{etat}]")

    if len(fichiers) > len(PHRASES):
        surplus = len(fichiers) - len(PHRASES)
        print(f"\n  ⚠️  {surplus} enregistrement(s) en trop : aucune phrase de reference.")
        print("      Ils seront ignores par la mesure.")

    print("\n⚠️  VERIFIE LA LISTE CI-DESSUS AVANT DE MESURER.")
    print("    Si une ligne ne correspond pas a ce que tu as reellement dit,")
    print("    corrige le .txt : le banc mesurerait un ecart qui n'existe pas.\n")
    print("Puis :  make whisper MODELES=base,small\n")
    return 0


def mode_d_emploi() -> None:
    presents = len(audios())
    from enregistrer_voix import PHRASES

    liste = "\n".join(f"       {n:2}. {p}" for n, p in enumerate(PHRASES, 1))
    print(f"""
Aucun echantillon exploitable dans {DOSSIER}
({presents} fichier(s) audio trouve(s), aucun accompagne de son texte)

POURQUOI TA PROPRE VOIX, ET PAS UN JEU DE TEST TOUT FAIT

Ce qu'on cherche a savoir, c'est comment le modele se comporte avec TON
micro, TA piece et TON accent. Une mesure faite sur d'autres voix
choisirait un modele pour quelqu'un d'autre.

╭─ VOIE 1 — le script d'enregistrement ─────────────────────────────────╮

  uv run python scripts/enregistrer_voix.py

  Entree, tu dis la phrase, Entree. Les fichiers audio et texte sont
  ecrits ensemble, donc toujours d'accord.

  Si le micro refuse :
      uv run python scripts/enregistrer_voix.py --tester

╰───────────────────────────────────────────────────────────────────────╯

╭─ VOIE 2 — Dictaphone, si le micro resiste ────────────────────────────╮

  1. Ouvre l'application Dictaphone et enregistre ces phrases, une par
     memo, DANS CET ORDRE :

{liste}

  2. Selectionne-les toutes, glisse-les dans ce dossier :

         {DOSSIER}

     Le format n'a pas d'importance : .m4a, .wav, .mp3 conviennent.

  3. Renomme-les 01, 02, 03… dans l'ordre ou tu les as dites, puis :

         uv run python scripts/bench_whisper.py --associer

     Les fichiers texte sont ecrits pour toi, et affiches pour que tu
     verifies l'appariement avant de mesurer.

╰───────────────────────────────────────────────────────────────────────╯

Puis, dans les deux cas :

    make whisper MODELES=base,small

Huit phrases suffisent pour trancher. Douze donnent un chiffre plus stable.
""")


def main() -> int:
    if "--associer" in sys.argv:
        return associer_les_textes()

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
    for modele, beam in configurations():
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

    # ⚠️ LE CONSEIL DOIT VENIR DE LA MESURE, PAS D'UN EXEMPLE.
    #
    # Ces deux lignes etaient ecrites en dur : « small, beam 5 ». La premiere
    # mesure reelle a designe small beam 1 (68,7 %) et classe small beam 5
    # DERNIER des deux (59,7 %) — le banc contredisait donc sa propre
    # conclusion, dans la ligne la plus lue de sa sortie. Un outil qui mesure
    # puis conseille autre chose est pire qu'un outil qui ne conseille rien.
    gagnant = max(resultats, key=lambda r: (r.precision, -r.secondes))
    print("CE QUE LA MESURE DESIGNE")
    print(f"    {gagnant.modele} en beam {gagnant.beam} — {gagnant.precision:.1%} de mots justes,")
    par_phrase = gagnant.secondes / max(len(paires), 1)
    print(f"    soit {par_phrase:.1f} s par phrase.\n")
    print("Pour l'appliquer, dans .env :")
    print(f"    NOVA_WHISPER_MODEL={gagnant.modele}")
    print(f"    NOVA_WHISPER_BEAM={gagnant.beam}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
