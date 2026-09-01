"""Quels fournisseurs existent sur CETTE machine, d'apres la configuration.

⚠️ UN FOURNISSEUR NON CONFIGURE N'EST PAS CONSTRUIT.

Ce n'est pas une precaution de style. Un fournisseur distant construit « au
cas ou » se retrouve dans le catalogue du routeur, donc dans la liste des
candidats, donc dans le journal — et quelqu'un qui lit « 2 modeles
disponibles » croit raisonnablement qu'il en a deux. Il en a un.

`mode_local_seul` va plus loin : le fournisseur distant n'est meme pas
instancie. Un interrupteur qu'un routage pourrait contourner n'est pas un
interrupteur.

POURQUOI CE CATALOGUE EST RECONSTRUIT A CHAQUE APPEL

Il ne coute que la lecture des reglages, deja mis en cache par
`get_settings`. Le mettre en cache lui-meme obligerait a l'invalider quand la
configuration change — et les bancs, eux, changent la configuration a chaque
banc. Un cache qui se trompe une fois sur mille coute plus cher que ce qu'il
economise ici.
"""

from __future__ import annotations

from nova.core.routeur import Routeur
from nova.logging_setup import get_logger
from nova.modeles import Fournisseur

log = get_logger(__name__)


def fournisseurs() -> tuple[Fournisseur, ...]:
    """Les fournisseurs utilisables sur cette machine.

    ⚠️ UN SEUL AUJOURD'HUI, ET AUCUN NE SORT DE LA MACHINE.

    Un fournisseur distant a existe ici — Claude, par l'API Anthropic. Il a
    ete retire sur demande explicite : « je ne veux pas de Claude ».

    Ce qui reste est ce qui valait la peine d'etre construit : le contrat
    `Fournisseur`, le classement par usage, le recours. Un second fournisseur
    — un autre modele Ollama, un modele specialise, le modele Nova le jour
    venu — s'ajoute ici et nulle part ailleurs.

    ⚠️ ET GARDER UN FOURNISSEUR DISTANT « AU CAS OU » AURAIT ETE PIRE.

    Du code mort qu'on garde finit par etre execute par accident. C'est la
    lecon de `_TOUT_OUVRIR`, retire pour la meme raison : un motif que plus
    personne n'atteint se lit comme une garde, et la prochaine correction se
    fait dedans.
    """
    from nova.modeles.local import Ollama
    from nova.settings import get_settings

    return (Ollama(get_settings().ollama_url),)


def routeur(sources: tuple[Fournisseur, ...] | None = None) -> Routeur:
    """Le routeur charge de tout ce que les fournisseurs disponibles proposent.

    ⚠️ SEULS LES FOURNISSEURS DISPONIBLES ENTRENT.

    Declarer un modele qu'on ne peut pas joindre ferait choisir au routeur un
    candidat condamne — le recours le rattraperait, mais apres un aller-retour
    perdu et un message d'erreur qui accuserait le reseau plutot que la
    configuration manquante.
    """
    catalogue = Routeur()
    for fournisseur in sources if sources is not None else fournisseurs():
        if not fournisseur.disponible():
            continue
        for modele in fournisseur.modeles():
            catalogue.declarer(modele)
    return catalogue


def par_id(identifiant: str, sources: tuple[Fournisseur, ...] | None = None):
    """Le fournisseur qui porte cet identifiant, ou `None`.

    C'est ce qui referme la boucle : le routeur rend un `Modele`, le modele
    porte le nom de son fournisseur, et cette fonction rend l'objet capable de
    l'executer.
    """
    for fournisseur in sources if sources is not None else fournisseurs():
        if fournisseur.id == identifiant:
            return fournisseur
    return None
