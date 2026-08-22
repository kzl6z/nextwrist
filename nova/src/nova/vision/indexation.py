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
from nova.vision.catalogue import LOT as _LOT_CATALOGUE

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

#: Repos quand la machine pagine deja.
#:
#: ⚠️ MA PREMIERE VALEUR RENDAIT L'INDEXATION INUTILISABLE.
#:
#: Une image toutes les cinq minutes : 42 images = 3 h 30. La machine de
#: reference pagine en permanence, donc c'etait le regime NORMAL — et
#: l'utilisateur devait lancer `make images FORCER=1` a la main, ce qui est
#: exactement ce que la tache de fond devait lui epargner.
#:
#: Or son propre releve montre dix images avalees en cinquante secondes, sans
#: rien de perceptible. J'avais surprotege une machine qui n'en demandait pas
#: tant.
#:
#:     au repos      lot=10, repos= 30 s  ->   6,7 min pour 42 images
#:     en paginant   lot= 4, repos= 60 s  ->  14,7 min pour 42 images
#:
#: Un quart d'heure d'inactivite, une seule fois. C'est le prix de « je n'ai
#: rien a faire ».
REPOS_SATURE_S = 60.0

#: Images par passage quand la machine pagine. Reduit, pas supprime.
LOT_SATURE = 4

#: Images regardees par passage. Importe ici parce qu'il sert de valeur par
#: defaut a `_un_passage` — donc evalue a l'import du module, pas a l'appel.
LOT = _LOT_CATALOGUE

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
    """Rend une fonction qui traduit un lot de descriptions.

    ⚠️ LE LOT D'ABORD, LIGNE PAR LIGNE SI LE COMPTE NE TOMBE PAS JUSTE.

    Releve sur la machine : « Traduction ignoree : 6 ligne(s) pour 10
    image(s) ». Le garde-fou a bien fonctionne — il a refuse d'attribuer la
    description d'une image a une autre — mais le resultat etait inutilisable :
    dix descriptions restees en anglais, et « casquette » ne trouvait rien.

    Un modele de deux milliards de parametres fusionne des lignes. On ne peut
    pas le lui interdire ; on peut retomber sur des appels ou l'erreur est
    IMPOSSIBLE : une description a l'entree, une reponse a la sortie. Dix
    appels courts au lieu d'un long, mais en tache de fond, ou personne
    n'attend.

    Le lot reste essaye d'abord : quand il marche — et il marche souvent — il
    coute dix fois moins.
    """

    def _une_a_une(descriptions: list[str]) -> list[str]:
        """Un appel par description. Le compte ne peut plus se tromper."""
        rendues: list[str] = []
        for description in descriptions:
            try:
                reponse = client.chat(
                    [
                        {
                            "role": "user",
                            "content": (
                                "Traduis cette description d'image en francais. "
                                "Reponds UNIQUEMENT par la traduction, sans "
                                "commentaire ni guillemets.\n\n"
                                f"{description}"
                            ),
                        }
                    ],
                    temperature=0.0,
                )
            except Exception as erreur:  # noqa: BLE001
                log.warning("Description non traduite (%s).", erreur)
                rendues.append(description)
                continue
            # Une reponse vide ou bavarde retombe sur l'original : l'anglais
            # cherchable vaut mieux qu'une ligne perdue.
            propre = (reponse or "").strip().strip('"«» ').splitlines()
            rendues.append(propre[0].strip() if propre and propre[0].strip() else description)
        return rendues

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
        if len(lignes) == len(descriptions):
            return lignes

        log.info(
            "Traduction par lot incomplete (%d/%d) — reprise une par une.",
            len(lignes), len(descriptions),
        )
        return _une_a_une(descriptions)

    return traduire


def _un_passage(lot: int = LOT) -> int:
    """Un lot. Rend le nombre d'images ajoutees. Ne leve jamais.

    `lot` est reduit a 1 quand la machine pagine : le travail avance sans
    ajouter de pression, plutot que de s'arreter definitivement.
    """
    from nova.llm.client import LLMClient
    from nova.vision import catalogue as cat
    from nova.vision.images import dossiers_surveilles
    from nova.vision.moteur import MoteurOllama

    catalogue = cat.Catalogue(cat.fichier_par_defaut())
    if oubliees := catalogue.oublier_les_disparues():
        log.info("Catalogue d'images : %d entree(s) disparue(s) retiree(s).", oubliees)
        catalogue.enregistrer()

    # ⚠️ RATTRAPER LES TRADUCTIONS RATEES AVANT DE REGARDER PLUS D'IMAGES.
    #
    # Une entree restee en anglais est une image introuvable en francais : le
    # catalogue se remplit et la recherche reste vide. Ce rattrapage ne coute
    # aucun appel au modele de VISION — les descriptions sont deja la, seule
    # leur langue change — donc il passe avant, toujours.
    if reprises := cat.retraduire(catalogue, _traduire_avec(LLMClient()), lot=lot):
        return reprises

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
        lot=lot,
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
        else:
            # ⚠️ SOUS PRESSION, ON RALENTIT. ON NE S'ARRETE PAS.
            #
            # La version precedente sautait le passage quand la machine
            # paginait. Sur le papier c'etait prudent ; en pratique c'etait un
            # blocage definitif : `pagine` est vrai des 1 Go de swap, la
            # machine de reference en a 2,27, et sur macOS le swap ne
            # redescend quasiment jamais. L'indexation n'aurait JAMAIS tourne
            # — precisement sur la machine pour laquelle elle est ecrite.
            #
            # Un garde-fou qui ne peut pas se relacher n'est pas un garde-fou,
            # c'est une panne silencieuse. On indexe donc UNE image au lieu de
            # dix, et on espace : le travail avance, la pression reste
            # minimale, et l'utilisateur n'a rien a comprendre.
            sature = _machine_saturee()
            try:
                if _un_passage(lot=LOT_SATURE if sature else LOT) == 0:
                    repos = REPOS_VIDE_S
                elif sature:
                    repos = REPOS_SATURE_S
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
