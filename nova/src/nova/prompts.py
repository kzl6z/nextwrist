"""Chargement des prompts depuis `config/prompts/`.

Pourquoi des fichiers plutot que des chaines dans le code : le prompt d'identite
sera modifie des dizaines de fois. Dans un fichier, il est versionne par git,
comparable d'une version a l'autre, et modifiable sans toucher au code.

C'est le principal levier de personnalisation de Nova — bien avant le choix du
modele.
"""

from __future__ import annotations

from nova.settings import get_settings


def load(name: str) -> str:
    """Charge `config/prompts/<name>.md`.

    Volontairement sans cache : tu peux modifier un prompt et recharger la page
    sans redemarrer Nova. Le cout d'une lecture de fichier est negligeable
    devant celui d'un appel au modele.
    """
    path = get_settings().prompts_dir / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt introuvable : {path}")
    return path.read_text(encoding="utf-8").strip()
