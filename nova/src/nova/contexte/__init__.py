"""Le contexte actif : de quoi on parle, et depuis quand.

CE QUI EXISTAIT DEJA, ET QU'IL NE FALLAIT PAS REFAIRE

    reprise.py      « cette phrase renvoie-t-elle a ce qui precede ? »
    conversations   le journal des echanges, avec un budget de caracteres
    focus.py        LE fichier ou L'image dont on vient de parler, et la liste
                    annoncee — c'est deja une resolution de reference, et elle
                    marche : « ouvre le deuxieme », « analyse-la »
    session.py      la fenetre d'ecoute ouverte, et la proposition en attente
    memory/         les faits durables, choisis par pertinence
    espaces/        un CLASSIFIEUR de domaine, sans etat

⚠️ CE QUI MANQUAIT N'EST PAS DE LA MEMOIRE. C'EST UN ETAT DE TRAVAIL.

`focus` retient un fichier pendant dix minutes. `memory` retient des faits
pour toujours. Entre les deux, rien ne retenait ce sur quoi on TRAVAILLE :
l'objectif du moment, les decisions prises cet apres-midi, l'hypothese qu'on
est en train de faire evoluer, la tache qu'on vient d'ajouter.

C'est ce qui manque pour que « et si on gardait le meme moteur ? » veuille
dire quelque chose trois phrases plus tard.

⚠️ ET CE MODULE NE RESOUT AUCUNE REFERENCE LUI-MEME.

C'est la decision de conception la plus importante ici, et elle est
explicitement demandee : pas de regle « si la phrase dit "augmente ca" alors
… ». Une telle regle donnerait l'ILLUSION de comprendre, et casserait a la
premiere tournure non prevue — le francais ne se met pas en liste.

Ce module fournit les REFERENTS : les entites en jeu, la tache en cours, les
dernieres decisions. C'est le modele qui resout « ca ». Notre travail est de
faire en sorte qu'il ait de quoi le faire, et rien de plus.

C'est exactement ce qui a marche pour « le deuxieme » : nous ne devinons pas
lequel, nous retenons la LISTE dans l'ordre annonce.

⚠️ UN SEUL PROJET ACTIF, ET LA BASE LE GARANTIT.

« De quoi parlons-nous maintenant » n'a qu'une reponse. Un index unique
partiel le dit, plutot que du code qui essaie d'y penser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from nova.logging_setup import get_logger

log = get_logger(__name__)

#: Les genres d'elements qu'un contexte porte. Le meme vocabulaire que le
#: schema — une seule source, et la base refuse le reste.
GENRES: tuple[str, ...] = ("decision", "hypothese", "tache", "entite", "question")


@dataclass(frozen=True)
class Element:
    """Une decision, une hypothese, une tache, une entite ou une question."""

    id: int
    genre: str
    contenu: str
    #: ⚠️ LA RAISON. « Rappelle-moi pourquoi on avait choisi cette approche »
    #: ne se repond pas avec une liste de decisions.
    pourquoi: str | None = None
    statut: str = "ouvert"
    source: str | None = None
    cree_le: datetime | None = None


@dataclass(frozen=True)
class Projet:
    """Ce sur quoi on travaille, et ce qu'on en sait."""

    id: int
    nom: str
    objectif: str | None = None
    espace: str | None = None
    #: « personnel » quand on a dit vouloir garder ca pour soi. Les outils le
    #: lisent AVANT d'ecrire ou d'envoyer quoi que ce soit.
    confidentialite: str = "normal"
    #: Ou le projet vit sur le disque, quand Nova l'y a ecrit. Vide sinon.
    dossier: str | None = None
    #: Quand Nova a propose de l'ecrire. Rempli meme si la reponse fut non :
    #: c'est ce qui distingue « jamais demande » de « demande et refuse ».
    document_propose_le: datetime | None = None
    elements: tuple[Element, ...] = ()

    def par_genre(self, genre: str, *, ouverts_seulement: bool = True):
        return tuple(
            e
            for e in self.elements
            if e.genre == genre and (not ouverts_seulement or e.statut == "ouvert")
        )

    @property
    def decisions(self):
        return self.par_genre("decision", ouverts_seulement=False)

    @property
    def hypotheses(self):
        return self.par_genre("hypothese")

    @property
    def taches(self):
        return self.par_genre("tache")

    @property
    def entites(self):
        """Les REFERENTS : ce que « ca », « celui-la », « cette valeur »
        peuvent designer. On les fournit, le modele les resout."""
        return self.par_genre("entite")

    @property
    def questions(self):
        return self.par_genre("question")


@dataclass(frozen=True)
class ContexteActif:
    """L'etat mental de travail, tel que Nova le croit.

    ⚠️ « TEL QUE NOVA LE CROIT » N'EST PAS UNE PRECAUTION DE STYLE.

    Ce contexte est deduit de ce qui a ete dit. Il peut etre en retard, ou
    faux. C'est pour cela qu'il est LISIBLE — `/v1/contexte` le rend en
    entier — et corrigeable a la voix. Un etat cache qu'on ne peut pas
    contredire est le meilleur moyen de rendre un assistant infrequentable.
    """

    projet: Projet | None = None
    #: Ce que `focus` retient : le fichier ou l'image dont on vient de parler.
    #: Repris ici pour que le bloc de prompt soit d'une seule piece.
    en_tete: str = ""
    fichiers: tuple[str, ...] = field(default_factory=tuple)

    @property
    def vide(self) -> bool:
        return self.projet is None and not self.en_tete and not self.fichiers
