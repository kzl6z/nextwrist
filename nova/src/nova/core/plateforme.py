"""Plateforme : ce que la machine permet, et ce qu'elle interdit.

POURQUOI CE MODULE EXISTE ALORS QUE L'APPLICATION A DEJA `platform.js`

Ce sont deux questions differentes, posees par deux couches differentes.

    platform.js  ->  « puis-je flouter le fond ? »          (rendu)
    ce module    ->  « puis-je faire tenir ce modele ? »    (calcul)

Les melanger obligerait le noyau a dependre de l'interface, ce qui est
exactement la fleche qu'on refuse. Nova doit tourner sans interface.

CE QU'ON EN FAIT

Le routeur y lit combien de memoire est disponible ; le profil vocal y lit
s'il faut menager le processeur graphique. Des mesures de cette session :

    modele resident a cote du modele de langue  ->  x3 sur le temps d'ecriture
    animation continue partageant le GPU        ->  x73 sur le temps de lecture

Sur une machine confortable, ces deux precautions sont inutiles. Sur 8 Go
partages, elles font la difference entre utilisable et abandonne. D'ou un
module qui les nomme au lieu de les supposer.
"""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Machine:
    """Ce qu'on sait de la machine, et ce qu'on en deduit."""

    systeme: str          # "macOS", "Windows", "Linux"
    version: str
    architecture: str     # "arm64", "x86_64"
    coeurs: int
    memoire_go: float
    disque_libre_go: float

    @property
    def apple_silicon(self) -> bool:
        """Memoire unifiee : le modele et l'affichage partagent la meme puce.

        Ce n'est pas une curiosite technique. C'est la raison pour laquelle une
        animation continue peut multiplier par 73 le temps de lecture d'un
        modele — mesure sur cette machine.
        """
        return self.systeme == "macOS" and self.architecture == "arm64"

    @property
    def budget_modele_go(self) -> float:
        """Memoire raisonnablement allouable a un modele.

        Environ 45 % du total. Le reste n'est pas du gaspillage : c'est le
        systeme, le navigateur, la base, la transcription — et la marge sans
        laquelle la machine bascule en memoire virtuelle, ce qui coute bien
        plus cher que le modele economise.
        """
        return round(self.memoire_go * 0.45, 1)

    @property
    def menager_le_gpu(self) -> bool:
        """Faut-il brider le rendu pendant que le modele travaille ?"""
        return self.apple_silicon and self.memoire_go <= 16

    @property
    def profil(self) -> str:
        """« etroit », « confortable » ou « large ». Un mot, pas un score."""
        if self.memoire_go <= 8:
            return "etroit"
        if self.memoire_go <= 24:
            return "confortable"
        return "large"


def _memoire_go() -> float:
    """Memoire totale, sans dependance externe.

    `os.sysconf` couvre macOS et Linux. Windows n'expose pas ces constantes :
    on rend 0, et l'appelant traite l'inconnu comme tel plutot que de recevoir
    un chiffre invente.
    """
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9, 1)
    except (ValueError, AttributeError, OSError):
        return 0.0


@lru_cache
def detecter() -> Machine:
    """La machine, mesuree une fois puis mise en cache."""
    noms = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}
    systeme = noms.get(platform.system(), platform.system())
    return Machine(
        systeme=systeme,
        version=platform.mac_ver()[0] if systeme == "macOS" else platform.release(),
        architecture=platform.machine(),
        coeurs=os.cpu_count() or 1,
        memoire_go=_memoire_go(),
        disque_libre_go=round(shutil.disk_usage(os.getcwd()).free / 1e9, 1),
    )


def resume() -> str:
    """Une ligne pour le journal de demarrage."""
    m = detecter()
    return (
        f"{m.systeme} {m.version} · {m.architecture} · {m.coeurs} coeurs · "
        f"{m.memoire_go} Go ({m.profil}) · {m.disque_libre_go} Go libres · "
        f"budget modele {m.budget_modele_go} Go"
    )
