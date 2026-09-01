"""Le Model Router a l'execution : choisir, appeler, et se rabattre s'il faut.

    demande  →  routeur.classer(usage)  →  fournisseur.flux()  →  jetons
                        |
                        └─ echec avant le premier jeton  →  candidat suivant

⚠️ LE RECOURS S'ARRETE AU PREMIER JETON SORTI.

C'est la seule regle de ce module qui ne se negocie pas. Une fois qu'un
fragment est parti vers l'interface — donc vers la synthese vocale, qui l'a
peut-etre deja prononce — changer de modele ne repare rien : cela colle la
fin d'une reponse a la moitie d'une autre. L'utilisateur entendrait une
phrase qu'aucun modele n'a ecrite.

« Ne jamais pretendre qu'un modele a repondu si la requete n'a pas ete
executee » vaut dans les deux sens. Ne jamais assembler deux moities non
plus.

⚠️ LE ROUTAGE LUI-MEME NE COUTE RIEN, ET C'EST UNE EXIGENCE.

Choisir, c'est lire des reglages deja en cache et trier une liste de deux
elements. Aucun appel reseau, aucun appel de modele, aucune comparaison de
reponses. Une question simple doit rester aussi rapide qu'avant ce module —
sinon le routeur coute plus qu'il ne rapporte.

C'est pour cela que `Fournisseur.disponible()` interdit le reseau : verifier
qu'Ollama repond avant chaque question ajouterait un aller-retour a chacune.
On decouvre la panne en echouant, une fois, et le recours prend la main.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Sequence

from nova.core.contrats import Modele
from nova.core.routeur import AucunModele, Routeur
from nova.logging_setup import get_logger
from nova.modeles import Fournisseur, Message

log = get_logger(__name__)


class AucunModeleN_aRepondu(RuntimeError):
    """Tous les candidats ont ete essayes, aucun n'a produit un mot.

    Porte la liste de ce qui a ete tente et pourquoi chacun a echoue. Un
    « ca n'a pas marche » sans detail envoie chercher au hasard : ici, on sait
    si Ollama etait eteint, si la clef distante etait refusee, ou si aucun
    modele ne convenait des le depart.
    """


def _preparer(
    usage: str,
    routeur: Routeur | None,
    sources: tuple[Fournisseur, ...] | None,
) -> tuple[tuple[Modele, ...], dict[str, Fournisseur]]:
    """Les candidats ordonnes, et de quoi joindre chacun.

    Les deux ensemble : un `Modele` seul ne dit pas a qui le demander, et
    c'est precisement ce qui empechait le routeur de servir a quelque chose.
    """
    from nova.modeles.catalogue import fournisseurs
    from nova.modeles.catalogue import routeur as catalogue_routeur

    disponibles = sources if sources is not None else fournisseurs()
    choix = routeur if routeur is not None else catalogue_routeur(disponibles)
    par_id = {f.id: f for f in disponibles}
    return choix.classer(usage), par_id


def flux(
    usage: str,
    messages: Sequence[Message],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    json_mode: bool = False,
    routeur: Routeur | None = None,
    sources: tuple[Fournisseur, ...] | None = None,
) -> Iterator[str]:
    """La reponse en flux, du meilleur modele disponible pour cet usage.

    Leve `AucunModele` si aucun candidat n'existe — c'est une erreur de
    configuration, pas une panne — et `AucunModeleN_aRepondu` si tous ont ete
    essayes sans qu'un seul mot sorte.
    """
    candidats, par_id = _preparer(usage, routeur, sources)
    log.info("[Model Router] Tache recue : usage « %s »", usage)
    log.info(
        "[Model Router] Capacite requise : %s — %d candidat(s) : %s",
        _capacite(usage),
        len(candidats),
        ", ".join(f"{m.nom}@{m.fournisseur}" for m in candidats),
    )

    echecs: list[str] = []
    for rang, modele in enumerate(candidats):
        fournisseur = par_id.get(modele.fournisseur)
        if fournisseur is None:
            echecs.append(f"{modele.nom} : fournisseur « {modele.fournisseur} » absent")
            continue
        if rang:
            log.warning("[Model Router] Recours : le fournisseur precedent a echoue")
            log.info("[Model Router] Fournisseur de recours : %s", fournisseur.nom)
        else:
            log.info("[Model Router] Fournisseur retenu : %s", fournisseur.nom)
        log.info("[Model Router] Modele : %s", modele.nom)

        # ⚠️ « SORTI » AU SENS DE : PARTI CHEZ L'APPELANT.
        #
        # Pas « recu du moteur ». C'est le `yield` qui engage, parce que
        # c'est lui qui peut deja avoir ete prononce.
        sorti = False
        depart = time.perf_counter()
        try:
            for morceau in fournisseur.flux(
                modele,
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            ):
                if not sorti:
                    sorti = True
                    log.info(
                        "[Model Router] Flux demarre (%s, premier mot en %.2f s)",
                        modele.nom,
                        time.perf_counter() - depart,
                    )
                yield morceau
        except Exception as erreur:  # noqa: BLE001
            if sorti:
                # ⚠️ ICI, ON NE SE RABAT PAS. ON REMONTE.
                #
                # Une partie de la reponse est deja partie. Recommencer
                # ailleurs produirait un texte que personne n'a ecrit, et
                # l'appelant croirait avoir une reponse complete.
                log.error(
                    "[Model Router] %s a echoue APRES avoir commence a repondre : %s",
                    modele.nom,
                    erreur,
                )
                raise
            echecs.append(f"{modele.nom}@{modele.fournisseur} : {erreur}")
            log.warning("[Model Router] %s a echoue : %s", modele.nom, erreur)
            continue

        if sorti:
            log.info("[Model Router] Termine (%s)", modele.nom)
            return
        # Aucun mot, aucune exception : ce n'est pas une reponse. On le dit et
        # on laisse sa chance au suivant plutot que de rendre le vide.
        echecs.append(f"{modele.nom}@{modele.fournisseur} : aucun mot produit")
        log.warning("[Model Router] %s n'a produit aucun mot", modele.nom)

    raise AucunModeleN_aRepondu(_pourquoi(usage, echecs))


def generer(
    usage: str,
    messages: Sequence[Message],
    *,
    temperature: float | None = None,
    routeur: Routeur | None = None,
    sources: tuple[Fournisseur, ...] | None = None,
) -> str:
    """La reponse complete. Meme selection, meme recours, sans flux.

    ⚠️ ICI LE RECOURS EST TOTAL, ET C'EST LA DIFFERENCE AVEC `flux`.

    Rien n'est parti chez l'appelant tant que la reponse n'est pas entiere :
    reessayer ailleurs ne peut donc rien couper en deux.
    """
    candidats, par_id = _preparer(usage, routeur, sources)
    log.info("[Model Router] Tache recue : usage « %s » (sans flux)", usage)

    echecs: list[str] = []
    for rang, modele in enumerate(candidats):
        fournisseur = par_id.get(modele.fournisseur)
        if fournisseur is None:
            echecs.append(f"{modele.nom} : fournisseur « {modele.fournisseur} » absent")
            continue
        if rang:
            log.warning("[Model Router] Recours : le fournisseur precedent a echoue")
        log.info("[Model Router] Fournisseur retenu : %s — %s", fournisseur.nom, modele.nom)
        try:
            texte = fournisseur.generer(modele, messages, temperature=temperature)
        except Exception as erreur:  # noqa: BLE001
            echecs.append(f"{modele.nom}@{modele.fournisseur} : {erreur}")
            log.warning("[Model Router] %s a echoue : %s", modele.nom, erreur)
            continue
        if texte:
            log.info("[Model Router] Termine (%s)", modele.nom)
            return texte
        echecs.append(f"{modele.nom}@{modele.fournisseur} : reponse vide")

    raise AucunModeleN_aRepondu(_pourquoi(usage, echecs))


def _capacite(usage: str) -> str:
    from nova.core.routeur import USAGES

    exigence = USAGES.get(usage)
    return exigence.capacite if exigence else "?"


def _pourquoi(usage: str, echecs: list[str]) -> str:
    """Le message d'echec : ce qui a ete tente, et ce que chacun a dit.

    Sans ce detail, « aucun modele n'a repondu » envoie chercher au hasard.
    Avec, on lit « Ollama injoignable » ou « clef refusee » et on sait quoi
    faire.
    """
    detail = "\n  ".join(echecs) or "aucun candidat pour cet usage"
    return f"aucun modele n'a repondu pour l'usage « {usage} ».\n  {detail}"


def expliquer(usage: str) -> str:
    """Ce que le routeur ferait, sans rien appeler. Pour l'interface et le journal."""
    try:
        candidats, par_id = _preparer(usage, None, None)
    except AucunModele as erreur:
        return str(erreur)
    if not candidats:
        return f"aucun modele pour l'usage « {usage} »"
    lignes = []
    for rang, modele in enumerate(candidats, start=1):
        servi_par = par_id.get(modele.fournisseur)
        qui = servi_par.nom if servi_par else modele.fournisseur
        recours = " (recours)" if rang > 1 else ""
        lignes.append(f"{rang}. {modele.nom} — {qui}{recours}")
    return "\n".join(lignes)
