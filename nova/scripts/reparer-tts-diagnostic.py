#!/usr/bin/env python3
"""Rendre a ElevenLabs le droit de dire pourquoi il refuse.

⚠️ CE CORRECTIF A COUTE TROIS ALLERS-RETOURS DE DIAGNOSTIC.

`electron/tts.js` lisait le corps de la reponse, puis l'effacait :

    let detail = buf.toString('utf8').slice(0, 300);      // la verite
    if (res.statusCode === 401) detail = 'cle API refusee';  // ... remplacee
    if (res.statusCode === 404) detail = 'Voice ID introuvable';
    if (res.statusCode === 429) detail = 'quota ElevenLabs depasse';

L'application affichait donc « HTTP 401 — cle API refusee » a chaque echec.
Or ElevenLabs renvoie 401 pour au moins trois causes sans rapport :

    invalid_api_key             la cle est fausse
    quota_exceeded              la cle est bonne, le compte est a sec
    detected_unusual_activity   le compte est suspendu

C'etait la deuxieme. Le message existait, complet et exact, dans chaque
reponse :

    {"detail":{"code":"quota_exceeded","message":"This request exceeds your
     quota of 10000. You have 3 credits remaining, while 10 credits are
     required for this request."}}

On a change la cle deux fois, verifie les permissions, teste l'URL au curl et
lu le code de lecture du fichier — pour une information que le programme
tenait dans une variable et jetait a la ligne suivante.

CE QU'ON CORRIGE, ET LE PRINCIPE

Les etiquettes lisibles restent : « quota ElevenLabs depasse » se comprend
mieux qu'un JSON. Mais elles s'AJOUTENT au message d'origine au lieu de le
remplacer. Une traduction n'a pas a supprimer l'original.

La regle vaut au-dela de ce fichier : un programme peut resumer ce qu'il a
recu, jamais l'effacer. Le resume sert l'utilisateur pressé ; l'original sert
celui qui cherche — et c'est toujours le second qui en a besoin.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def reparer(source: str) -> tuple[str, list[str]]:
    """Retourne (source corrigee, liste des changements appliques)."""
    faits: list[str] = []

    # 1. Garder le corps brut dans une variable qui, elle, ne bouge plus.
    #
    #    Une constante et non une variable : c'est ce qui rend l'effacement
    #    impossible plutot qu'improbable. Le defaut d'origine venait d'un
    #    `let` qu'on pouvait ecraser sans y penser — et qu'on a ecrase.
    motif_lecture = re.compile(
        r"^(\s*)(?:let|const)\s+detail\s*=\s*buf\.toString\('utf8'\)\.slice\(0,\s*300\);",
        re.MULTILINE,
    )
    if motif_lecture.search(source):
        source = motif_lecture.sub(
            lambda m: (
                f"{m.group(1)}const brut = buf.toString('utf8').slice(0, 300);\n"
                f"{m.group(1)}let detail = brut;"
            ),
            source,
            count=1,
        )
        faits.append("le corps brut est conserve dans `brut`")

    # 2. Remettre les etiquettes a leur forme simple.
    #
    #    Un rustine posee en urgence avait deja fait « 'cle API refusee — ' +
    #    detail » sur le seul cas 401. On normalise : l'ajout du brut se fait
    #    UNE fois, a la fin, pour tous les codes — sinon le prochain code
    #    ajoute redevient muet, et on recommence l'enquete.
    #
    # ⚠️ ON COMPARE AVANT/APRES PLUTOT QUE DE COMPTER LES CORRESPONDANCES.
    #
    # La premiere version comptait `re.subn`, qui rend 1 des que le motif est
    # trouve — y compris quand il remplace un texte par lui-meme. Relancer le
    # script annoncait donc trois corrections sans rien changer. Un outil qui
    # dit avoir travaille alors qu'il n'a rien fait apprend a ne plus le croire.
    for etiquette in ("clé API refusée", "Voice ID introuvable", "quota ElevenLabs dépassé"):
        motif = re.escape(f"detail = '{etiquette} — ' + detail;")
        avant = source
        source = re.sub(motif, f"detail = '{etiquette}';", source, count=1)
        if source != avant:
            faits.append(f"etiquette normalisee : {etiquette}")

    # 3. Le test du cas 400 doit porter sur le brut, pas sur `detail` — sinon
    #    il examine parfois une etiquette qu'on vient d'ecrire soi-meme.
    source, n = re.subn(
        r"(/output_format\|format/i\.test\()detail(\))", r"\1brut\2", source, count=1
    )
    if n:
        faits.append("le test du code 400 lit le brut")

    # 4. Recoller le brut a la fin, une seule fois, quel que soit le code.
    ancre = re.compile(
        r"^(\s*)(console\.error\('\[NOVA\] ElevenLabs a REFUSÉ la requête)", re.MULTILINE
    )
    if "if (detail !== brut)" not in source and ancre.search(source):
        source = ancre.sub(
            lambda m: (
                f"{m.group(1)}// L'etiquette RESUME, elle ne remplace pas : sans cette ligne,\n"
                f"{m.group(1)}// « quota_exceeded » redevient « cle API refusee » et l'enquete\n"
                f"{m.group(1)}// recommence a zero.\n"
                f"{m.group(1)}if (detail !== brut) detail += ' — ' + brut;\n"
                f"{m.group(1)}{m.group(2)}"
            ),
            source,
            count=1,
        )
        faits.append("le brut est recolle a l'etiquette, pour tous les codes")

    return source, faits


def main() -> int:
    defaut = Path.home() / "Desktop" / "nova-project" / "electron" / "tts.js"
    chemin = Path(sys.argv[1]) if len(sys.argv) > 1 else defaut

    if not chemin.is_file():
        print(f"✗ introuvable : {chemin}", file=sys.stderr)
        print("  usage : reparer-tts-diagnostic.py [chemin/vers/tts.js]", file=sys.stderr)
        return 1

    original = chemin.read_text(encoding="utf-8")
    corrige, faits = reparer(original)

    if not faits:
        print("Rien a faire — le correctif est deja en place.")
        return 0

    # ⚠️ NE JAMAIS ECRASER UNE SAUVEGARDE EXISTANTE.
    #
    # La premiere version ecrivait la sauvegarde a chaque passage. Au deuxieme,
    # elle enregistrait donc le fichier DEJA MODIFIE par-dessus l'original —
    # c'est-a-dire qu'elle detruisait exactement ce qu'elle pretendait garder,
    # et silencieusement. Une sauvegarde qui se laisse ecraser par le second
    # essai protege du cas ou l'on se trompe une fois, et pas deux.
    sauvegarde = chemin.with_suffix(".js.avant-diagnostic")
    if not sauvegarde.exists():
        sauvegarde.write_text(original, encoding="utf-8")
    chemin.write_text(corrige, encoding="utf-8")

    # ⚠️ On modifie du JavaScript avec des expressions regulieres. C'est
    # acceptable UNIQUEMENT parce que `node --check` a le dernier mot : une
    # application qui ne demarre plus coute infiniment plus cher qu'un message
    # d'erreur imprecis.
    verif = subprocess.run(["node", "--check", str(chemin)], capture_output=True, text=True)
    if verif.returncode != 0:
        chemin.write_text(original, encoding="utf-8")
        print("✗ correctif annule : le fichier ne parsait plus", file=sys.stderr)
        if verif.stderr:
            print(f"  {verif.stderr.strip().splitlines()[0]}", file=sys.stderr)
        return 1

    for fait in faits:
        print(f"  ✓ {fait}")
    print(f"\n✓ tts.js corrige. Sauvegarde : {sauvegarde}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
