"""Regarder les images en tache de fond, pour pouvoir les retrouver ensuite.

⚠️ CE FIL EST LE SEUL ENDROIT DU PROJET QUI CHARGE UN MODELE SANS QU'ON LUI
   AIT RIEN DEMANDE. TOUT CE FICHIER EN DECOULE.

Sur une machine de 8 Go, charger le modele de vision decharge celui de la
langue. Si ce fil le fait pendant que quelqu'un parle a Nova, la reponse
attend — et personne ne comprend pourquoi, puisque rien n'a ete demande.

Trois garde-fous, dans l'ordre d'importance :

  1. IL NE DEMARRE QUE SI LA VISION EST ACTIVE. Elle est eteinte par defaut ;
     ce fil n'existe donc pas pour qui ne s'en sert pas.
  2. IL ATTEND LE SILENCE. Rien n'est indexe tant qu'une reponse a ete
     produite dans les dernieres minutes.
  3. IL TRAVAILLE PAR PETITS LOTS, en laissant du temps entre chacun.

⚠️ ET IL S'ARRETE QUAND IL N'Y A PLUS RIEN A FAIRE.

Une fois les images connues, il ne reste que les nouvelles — quelques-unes
par jour. Un fil qui recharge un modele de 2 Go toutes les cinq minutes pour
constater qu'il n'y a rien a faire coûterait plus cher que le service rendu.
"""

from __future__ import annotations

import threading
import time

from nova.logging_setup import get_logger

log = get_logger(__name__)

#: Silence exige avant d'oser charger le modele de vision, en secondes.
#:
#: Assez long pour qu'une conversation en cours ne soit jamais interrompue,
#: assez court pour que l'indexation avance des qu'on pose le telephone.
SILENCE_S = 120.0

#: Repos entre deux lots. Le fil n'est pas presse : personne ne l'attend.
REPOS_S = 30.0

#: Repos quand il n'y a rien a faire. Long : c'est le cas courant une fois le
#: rattrapage termine.
REPOS_VIDE_S = 900.0

#: Delai avant le tout premier lot, en secondes.
#:
#: ⚠️ SANS LUI, L'INDEXATION DEMARRAIT AU PIRE MOMENT POSSIBLE.
#:
#: `_repos_depuis_la_derniere_reponse` rend « plus que le silence exige »
#: quand personne n'a encore parle — ce qui est vrai, et qui faisait charger
#: le modele de vision A LA SECONDE du demarrage. C'est-a-dire pendant que
#: Whisper se prechauffe et que le modele de langue se met en place : trois
#: chargements concurrents sur une machine de 8 Go.
#:
#: Le fil n'est jamais presse. Attendre que le demarrage soit fini ne coute
#: rien a personne, et evite de faire passer Nova pour lente au moment ou on
#: la lance.
DEMARRAGE_S = 120.0

#: Instant de la derniere reponse produite. Ecrit par l'orchestrateur.
_derniere_activite = 0.0
_verrou = threading.Lock()


def signaler_activite() -> None:
    """A appeler quand Nova repond. Repousse l'indexation d'autant.

    ⚠️ APPELE SUR LE CHEMIN DE CHAQUE REPONSE — DONC GRATUIT.

    Une horloge et un verrou : quelques microsecondes. Tout ce qui coute plus
    n'a rien a faire ici, et ce fichier n'a le droit de rien demander de plus
    a l'orchestrateur.
    """
    global _derniere_activite
    with _verrou:
        _derniere_activite = time.monotonic()


def _repos_depuis_la_derniere_reponse() -> float:
    with _verrou:
        dernier = _derniere_activite
    return time.monotonic() - dernier if dernier else SILENCE_S + 1


def _machine_saturee() -> bool:
    """La machine pagine-t-elle deja ? Ne leve jamais.

    Une mesure indisponible ne doit pas empecher d'indexer : on repond « non »
    et on laisse les autres garde-fous faire leur travail. Bloquer une
    capacite sur l'absence d'une mesure serait plus couteux que le risque.
    """
    try:
        from nova.core import plateforme

        pression = plateforme.pression_memoire()
    except Exception as erreur:  # noqa: BLE001
        log.debug("Pression memoire illisible (%s).", erreur)
        return False
    if pression.pagine:
        log.info("Indexation reportee : la machine pagine (%s).", pression)
        return True
    return False


def _traduire_avec(client) -> list[str]:
    """Rend une fonction qui traduit un LOT de descriptions en une fois."""

    def traduire(descriptions: list[str]) -> list[str]:
        # ⚠️ UNE LIGNE PAR IMAGE, ET ON VERIFIE LE COMPTE EN SORTIE.
        #
        # Un modele qui fusionne deux lignes attribuerait la description
        # d'une image a une autre — une erreur invisible, qui ferait ouvrir
        # le mauvais fichier des mois plus tard. `catalogue.indexer` refuse
        # une traduction dont le nombre de lignes ne correspond pas.
        numerotees = "\n".join(f"{i + 1}. {d}" for i, d in enumerate(descriptions))
        reponse = client.chat(
            [
                {
                    "role": "user",
                    "content": (
                        "Traduis en francais chacune de ces descriptions "
                        "d'images. Rends EXACTEMENT une ligne par description, "
                        "numerotee comme l'entree, sans commentaire.\n\n"
                        f"{numerotees}"
                    ),
                }
            ],
            temperature=0.0,
        )
        lignes = [
            ligne.split(". ", 1)[-1].strip()
            for ligne in (reponse or "").splitlines()
            if ligne.strip() and ligne.strip()[0].isdigit()
        ]
        return lignes

    return traduire


def _un_passage() -> int:
    """Un lot. Rend le nombre d'images ajoutees. Ne leve jamais."""
    from nova.llm.client import LLMClient
    from nova.vision import catalogue as cat
    from nova.vision.images import dossiers_surveilles
    from nova.vision.moteur import MoteurOllama

    catalogue = cat.Catalogue(cat.fichier_par_defaut())
    if oubliees := catalogue.oublier_les_disparues():
        log.info("Catalogue d'images : %d entree(s) disparue(s) retiree(s).", oubliees)
        catalogue.enregistrer()

    restantes = [c for c in cat.a_indexer() if not catalogue.a_jour(c)]
    if not restantes:
        return 0

    log.info("Indexation des images : %d restante(s).", len(restantes))
    moteur = MoteurOllama(dossiers_surveilles())
    return cat.indexer(
        restantes,
        catalogue,
        decrire=lambda chemin: moteur.decrire(chemin).description,
        traduire=_traduire_avec(LLMClient()),
    )


def entretenir(arret: threading.Event) -> None:
    """Le fil. Indexe quand la machine se tait, dort le reste du temps."""
    from nova.vision.moteur import disponible

    utilisable, raison = disponible()
    if not utilisable:
        log.info("Indexation des images non demarree : %s", raison.splitlines()[0])
        return

    log.info(
        "Indexation des images : premier lot dans %d s, puis des que la "
        "machine se tait pendant %d s.",
        int(DEMARRAGE_S), int(SILENCE_S),
    )
    # Le demarrage charge deja Whisper et le modele de langue. On ne s'y
    # ajoute pas.
    if arret.wait(DEMARRAGE_S):
        return

    while not arret.is_set():
        repos = REPOS_S
        if _repos_depuis_la_derniere_reponse() < SILENCE_S:
            # Quelqu'un parle a Nova. Charger le modele de vision maintenant
            # ferait attendre la reponse suivante sans raison visible.
            repos = SILENCE_S - _repos_depuis_la_derniere_reponse()
        elif _machine_saturee():
            # ⚠️ TROISIEME GARDE-FOU, AJOUTE APRES UNE MESURE REELLE.
            #
            # Releve au demarrage sur la machine : « La machine pagine (swap
            # 2,27 Go / 3,0 Go) ». Charger 2 Go de plus dans cet etat ne
            # ralentit pas seulement Nova — ca ralentit TOUT, y compris ce
            # que la personne etait en train de faire.
            #
            # Le silence ne suffit donc pas comme condition : une machine
            # peut etre silencieuse ET saturee. On repousse, et l'indexation
            # reprendra quand la memoire se sera liberee.
            repos = REPOS_VIDE_S
        else:
            try:
                if _un_passage() == 0:
                    repos = REPOS_VIDE_S
            except Exception as erreur:  # noqa: BLE001
                # Une indexation en panne ne doit jamais faire tomber Nova.
                # Elle reessaiera plus tard ; en attendant, la recherche
                # d'images se contente de ce qui est deja connu.
                log.warning("Indexation des images interrompue : %s", erreur)
                repos = REPOS_VIDE_S
        # ⚠️ ON SORT SUR LE RETOUR DE `wait`, PAS SEULEMENT SUR `is_set`.
        #
        # `arret.wait()` rend `True` quand l'arret a ete demande. L'ignorer
        # marchait avec un vrai `Event` — `is_set()` devient vrai au tour
        # suivant — et a fait tourner un banc en boucle infinie avec un double
        # qui rend `True` sans se marquer. Un fil qui ne peut pas etre arrete
        # par le seul objet prevu pour ca est un fil qu'on ne peut pas arreter.
        if arret.wait(max(repos, 5.0)):
            return
