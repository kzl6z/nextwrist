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
import re
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


#: Poids approximatif des modeles courants, en Go, quantification par defaut
#: d'Ollama (Q4). Approximatif ET utile : il ne s'agit pas de facturer un
#: octet pres, mais de distinguer « ca tient » de « ca va ramer une heure ».
POIDS_CONNUS: dict[str, float] = {
    "llama3.2:1b": 1.3, "llama3.2:3b": 2.0, "llama3.1:8b": 4.9,
    "qwen2.5:3b": 1.9, "qwen2.5:7b": 4.7,
    "qwen3:1.7b": 1.4, "qwen3:4b": 2.6, "qwen3:8b": 5.2,
    "gemma2:2b": 1.6, "gemma3:4b": 3.3,
    "mistral:7b": 4.1, "phi3:mini": 2.3,
}


def poids_modele_go(nom: str) -> float | None:
    """Le poids probable d'un modele, ou `None` si inconnu.

    On tolere les variantes de suffixe (`qwen3:8b-instruct-q4_K_M`) : ce qui
    determine le poids est la famille et le nombre de parametres, pas la
    declinaison.
    """
    if nom in POIDS_CONNUS:
        return POIDS_CONNUS[nom]
    for connu, poids in POIDS_CONNUS.items():
        if nom.startswith(connu):
            return poids
    return None


def modele_trop_lourd(nom: str) -> str | None:
    """Un avertissement si ce modele ne tient pas dans le budget, sinon `None`.

    POURQUOI CET AVERTISSEMENT EXISTE

    Un modele plus gros que la memoire disponible ne refuse pas de tourner :
    il tourne, en paginant sur le disque. La difference ne se voit nulle part
    — ni erreur, ni journal — sauf sur le chronometre, ou elle se compte en
    minutes. C'est la panne la plus couteuse a diagnostiquer, parce qu'elle
    ressemble a « l'IA locale est lente », alors qu'elle veut dire « ce modele
    n'est pas pour cette machine ».

    Nova ne choisit pas a ta place : elle le DIT, une fois, au demarrage.
    """
    machine = detecter()
    poids = poids_modele_go(nom)
    if poids is None or machine.memoire_go == 0:
        return None
    if poids <= machine.budget_modele_go:
        return None
    return (
        f"Le modele « {nom} » pese environ {poids} Go, pour un budget de "
        f"{machine.budget_modele_go} Go sur cette machine ({machine.memoire_go} Go, "
        f"profil {machine.profil}).\n"
        f"Il fonctionnera, mais en paginant sur le disque — c'est-a-dire tres "
        f"lentement, sans qu'aucune erreur ne le signale.\n"
        f"Modeles qui tiennent dans ce budget : "
        f"{', '.join(sorted(n for n, p in POIDS_CONNUS.items() if p <= machine.budget_modele_go))}"
    )


def _memoire_go() -> float:
    """Memoire totale, sans dependance externe.

    `os.sysconf` couvre macOS et Linux. Windows n'expose pas ces constantes :
    on rend 0, et l'appelant traite l'inconnu comme tel plutot que de recevoir
    un chiffre invente.

    ⚠️ 2**30 ET NON 1e9, ET LA DIFFERENCE N'EST PAS COSMETIQUE

    Quand un constructeur ecrit « 8 Go de memoire », il parle de 8 Gio, soit
    8 589 934 592 octets. Divise par 1e9, cela donne 8,6 — et le seuil
    `memoire_go <= 8` du profil ne se declenche JAMAIS sur une machine de
    8 Go. Releve sur la machine de reference :

        8.6 Go (confortable)     <- faux, c'est un Mac 8 Go, profil « etroit »

    Consequence en chaine : le budget modele passait de 3,6 a 3,9 Go, et
    surtout Nova annoncait « confortable » a une machine qui ne l'est pas —
    donc n'incitait pas a choisir un modele plus leger. Une unite mal choisie
    a fait mentir tout le diagnostic.
    """
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)
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


@dataclass(frozen=True)
class Pression:
    """L'etat de la memoire MAINTENANT, pas ce que la machine contient.

    POURQUOI CETTE MESURE EXISTE, ET POURQUOI ELLE ARRIVE SI TARD

    « Tout se fige pendant qu'elle repond, sauf la souris » a exactement deux
    explications sur une puce a memoire unifiee, et elles demandent des
    corrections opposees :

        contention GPU   le modele et l'affichage se disputent la meme puce
        pagination       la machine ecrit sur le disque pour faire de la place

    La premiere se corrige en ralentissant l'animation. La seconde ne se
    corrige QUE par un modele plus leger — aucun reglage d'interface n'y peut
    rien. Choisir sans mesurer, c'est une chance sur deux de passer une
    journee du mauvais cote.

    Le curseur qui continue de bouger ne departage pas : il est dessine par un
    chemin prioritaire dans les deux cas.
    """

    swap_utilise_go: float
    swap_total_go: float
    disponible: bool = True

    @property
    def pagine(self) -> bool:
        """La machine ecrit-elle de la memoire sur le disque ?

        Un demi-gigaoctet de swap sur macOS est normal et sans effet ressenti
        — le systeme y depose des pages froides. Au-dela, ce sont des pages
        chaudes qui partent, et chacune revient au prix d'une lecture disque.
        """
        return self.disponible and self.swap_utilise_go >= 1.0

    def __str__(self) -> str:
        if not self.disponible:
            return "pagination inconnue"
        return f"swap {self.swap_utilise_go} Go / {self.swap_total_go} Go"


def pression_memoire() -> Pression:
    """Combien de memoire est actuellement repoussee sur le disque.

    N'est PAS mise en cache, contrairement a `detecter()` : c'est une mesure
    d'instant, et la garder reviendrait a mesurer autre chose.
    """
    try:
        if platform.system() == "Darwin":
            return _swap_macos()
        if platform.system() == "Linux":
            return _swap_linux()
    except Exception:  # noqa: BLE001
        pass
    return Pression(0.0, 0.0, disponible=False)


def _swap_macos() -> Pression:
    """`sysctl vm.swapusage` — sans dependance, et deja installe partout.

    Sortie : « total = 2048,00M  used = 1234,50M  free = 813,50M ».
    Le separateur decimal SUIT LA LANGUE DU SYSTEME : sur un Mac francais
    c'est une virgule, et `float("1234,50")` leve. C'est le genre de detail
    qui ne se voit jamais en test et toujours chez l'utilisateur.
    """
    import subprocess

    sortie = subprocess.run(
        ["/usr/sbin/sysctl", "-n", "vm.swapusage"],
        capture_output=True, text=True, timeout=2.0, check=False,
    ).stdout
    return Pression(_octets(sortie, "used"), _octets(sortie, "total"))


def _octets(sortie: str, champ: str) -> float:
    """Le champ demande, en Go, quelle que soit l'unite et la langue."""
    trouve = re.search(rf"{champ}\s*=\s*([\d.,]+)([KMG])", sortie)
    if not trouve:
        return 0.0
    valeur = float(trouve.group(1).replace(",", "."))
    facteur = {"K": 1 / 2**20, "M": 1 / 2**10, "G": 1.0}[trouve.group(2)]
    return round(valeur * facteur, 2)


def _swap_linux() -> Pression:
    valeurs: dict[str, float] = {}
    with open("/proc/meminfo") as meminfo:
        for ligne in meminfo:
            if ligne.startswith(("SwapTotal:", "SwapFree:")):
                clef, valeur, *_ = ligne.replace(":", "").split()
                valeurs[clef] = float(valeur) / 2**20      # kio -> Gio
    total = valeurs.get("SwapTotal", 0.0)
    return Pression(round(total - valeurs.get("SwapFree", 0.0), 2), round(total, 2))


def resume() -> str:
    """Une ligne pour le journal de demarrage."""
    m = detecter()
    return (
        f"{m.systeme} {m.version} · {m.architecture} · {m.coeurs} coeurs · "
        f"{m.memoire_go} Go ({m.profil}) · {m.disque_libre_go} Go libres · "
        f"budget modele {m.budget_modele_go} Go"
    )
