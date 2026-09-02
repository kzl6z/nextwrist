"""Les outils de fichiers : retrouver, et ouvrir.

⚠️ CES DEUX OUTILS N'ONT PAS LE MEME NIVEAU, ET C'EST LE SUJET.

`rechercher_fichier` est une LECTURE : il rend des noms, des dossiers et des
dates. Il n'ouvre rien, ne lit aucun contenu, et ne sort pas de la machine.

`ouvrir_fichier` est REVERSIBLE : quelque chose se passe a l'ecran. C'est le
meme niveau qu'`ouvrir_application` et `ouvrir_image`, pour la meme raison —
une fenetre s'ouvre, on la ferme, il ne reste rien.

⚠️ OUVRIR EST BORNE, ET LA BORNE N'EST PAS LA MEME QUE POUR LIRE.

`open` sur un chemin non verifie ouvrirait n'importe quoi : une application,
un script, un fichier de clef. La borne ici est double, et les deux
conditions sont exigees :

    le fichier est SOUS un dossier de recherche declare
    le fichier est ACCEPTABLE au sens de `fichiers/moteurs.py`

La seconde fait le vrai travail : elle ecarte les clefs, les jetons, les
dossiers caches et `~/Library`. Comparer des chaines ne suffirait pas —
`~/Documents/../.ssh/id_rsa` commence bien par `~/Documents`. On resout donc
reellement le chemin avant de comparer, comme `LireFichier` et
`vision/images.py:resoudre`.
"""

from __future__ import annotations

from pathlib import Path

from nova.core import contrats
from nova.logging_setup import get_logger

log = get_logger(__name__)


class FichierRefuse(PermissionError):
    """Le chemin sort de ce que Nova a le droit de toucher."""


def borner(chemin: str, racines: tuple[Path, ...]) -> Path:
    """Le chemin reel, s'il est dans une racine autorisee. Sinon, on refuse."""
    from nova.fichiers.moteurs import acceptable

    if not racines:
        raise FichierRefuse("Aucun dossier de recherche configure pour Nova.")
    if not chemin:
        raise FichierRefuse("Aucun fichier a ouvrir.")

    cible = Path(chemin).expanduser()
    try:
        cible = cible.resolve()
    except OSError as erreur:
        raise FichierRefuse(f"Chemin illisible : {erreur}") from erreur

    dedans = any(
        cible == racine or racine in cible.parents for racine in racines
    )
    if not dedans:
        raise FichierRefuse(
            f"« {cible.name} » sort des dossiers que Nova peut atteindre."
        )
    # Les racines sont deja connues ici : ce qui MENE a un dossier declare
    # n'a pas a etre juge une seconde fois.
    if not acceptable(cible, racines=racines):
        raise FichierRefuse(
            f"Nova ne touche pas a « {cible.name} » : ce genre de fichier est "
            "hors de sa portee."
        )
    if not cible.is_file():
        raise FichierRefuse(f"« {cible.name} » n'existe pas ou n'est pas un fichier.")
    return cible


class RechercherFichier:
    """Retrouve un fichier sur la machine, par son nom, son type et sa date."""

    nom = "rechercher_fichier"
    description = "Retrouve un fichier sur la machine d'apres sa description"
    capacite = "recherche"
    #: Rend des noms et des dates. N'ouvre rien, ne lit aucun contenu.
    niveau = contrats.LECTURE

    def executer(self, description: str, limite: int = 4) -> dict:
        from nova.fichiers.trouver import chercher

        recherche, classes = chercher(description, limite=int(limite))
        return {
            "cherche": " ".join(recherche.mots),
            "annee": recherche.annee,
            "trouves": [
                {
                    "nom": trouve.nom,
                    "chemin": str(trouve.chemin),
                    "dossier": trouve.dossier,
                    "date": trouve.date_lisible(),
                    "octets": trouve.octets,
                    "correspondance": round(note, 2),
                }
                for trouve, note in classes
            ],
        }


class OuvrirFichier:
    """Ouvre un fichier dans l'application par defaut du systeme."""

    nom = "ouvrir_fichier"
    description = "Ouvre un fichier de la machine dans l'application par defaut"
    capacite = "action"
    niveau = contrats.REVERSIBLE

    def executer(self, chemin: str = "") -> str:
        import subprocess

        from nova.fichiers.trouver import dossiers_cherches
        from nova.outils.systeme import DELAI_S, ActionImpossible, _verifier_macos

        _verifier_macos(self.nom)
        cible = borner(chemin, dossiers_cherches())

        # Liste d'arguments, jamais une chaine : l'injection devient
        # impossible plutot qu'improbable. Meme regle qu'`ouvrir_application`.
        resultat = subprocess.run(  # noqa: S603
            ["/usr/bin/open", str(cible)],
            capture_output=True, text=True, timeout=DELAI_S,
        )
        if resultat.returncode != 0:
            detail = (resultat.stderr or "").strip()
            raise ActionImpossible(
                f"Impossible d'ouvrir « {cible.name} »." + (f" {detail}" if detail else "")
            )
        log.info("Fichier ouvert : %s", cible)
        return f"J'ai ouvert {cible.name}."


class CreerDossier:
    """Cree un dossier, sous une racine ou Nova a le droit d'ecrire."""

    nom = "creer_dossier"
    description = "Cree un dossier sur la machine, dans une zone autorisee"
    capacite = "action"
    #: ⚠️ LE BAREME LE NOMMAIT DEJA.
    #
    # `contrats.REVERSIBLE` : « modifie quelque chose, mais le geste se
    # defait : ouvrir une application, CREER UN DOSSIER, monter le son ».
    # Ecrit avant le premier outil qui agit, precisement pour que ce choix ne
    # se decide pas au moment ou l'on a envie que ca marche.
    #
    # Le corollaire est dans `executer` : cet outil ne remplace RIEN. Ecraser
    # un dossier existant serait CONSEQUENT, donc a confirmer — on ne le fait
    # pas du tout plutot que de demander.
    niveau = contrats.REVERSIBLE

    # ⚠️ L'ARGUMENT NE PEUT PAS S'APPELER `nom`, ET LE BANC LE DIT.
    #
    # `executer_outil(nom, *, confirme, **arguments)` : son premier parametre
    # est le nom de L'OUTIL. Un outil qui declare un argument `nom` produit
    # « executer_outil() got multiple values for argument 'nom' » — au moment
    # de l'appel, jamais a l'enregistrement. La fonctionnalite se serait
    # cassee en conditions reelles, pas en relisant le code.
    def executer(self, dossier: str = "", ou: str = "") -> str:
        from nova.fichiers.creer import destination, nom_lisible

        propre = (dossier or "").strip()
        if not propre:
            raise FichierRefuse("Aucun nom de dossier.")

        parent = destination(ou)
        if parent is None:
            raise FichierRefuse(
                "Je n'ai pas le droit de créer là. "
                "Regarde NOVA_FICHIERS_CREATION_DOSSIERS."
            )

        cible = borner_creation(parent, propre)
        ou_dit = nom_lisible(parent)
        if cible.exists():
            # Ni erreur ni ecrasement : le dossier voulu est la, ce qui est le
            # resultat demande. Le dire evite d'en fabriquer un second sous un
            # nom legerement different.
            log.info("Dossier deja present : %s", cible)
            return f"Le dossier {cible.name} est déjà sur {ou_dit}."

        cible.mkdir()
        log.info("Dossier cree : %s", cible)
        return f"J'ai créé le dossier {cible.name} sur {ou_dit}."


class EcrireProjet:
    """Ecrit le projet actif sur le disque : un dossier, et un document dedans."""

    nom = "ecrire_projet"
    description = "Crée le dossier du projet en cours et y écrit ce qui a été dit"
    capacite = "action"
    #: ⚠️ REVERSIBLE PARCE QU'IL N'ECRASE RIEN, ET POUR AUCUNE AUTRE RAISON.
    #
    # Le bareme range « ecrire dans un fichier existant » dans CONSEQUENT :
    # ca se defait mal. Cet outil reste donc en deca — il cree un dossier
    # (nomme dans REVERSIBLE) et un fichier QUI N'EXISTE PAS. Quand le
    # document est deja la, il ne le touche pas et le dit.
    #
    # Mettre a jour un document existant est une autre action, avec son
    # niveau et sa confirmation. Elle n'existe pas encore, et il vaut mieux
    # ne pas l'avoir que l'avoir sans confirmation.
    niveau = contrats.REVERSIBLE

    def executer(self, projet: str = "", ou: str = "") -> str:
        from nova.contexte import actif, document

        courant, racine, fichier, ou_dit = _emplacement(projet, ou)
        racine.mkdir(exist_ok=True)

        if fichier.exists():
            # ⚠️ ON N'ECRASE PAS, ET ON NE SE TAIT PAS NON PLUS.
            #
            # Le document peut avoir ete repris a la main. Le reecrire
            # perdrait ce travail sans que rien ne le dise — exactement ce que
            # CONSEQUENT designe dans le bareme.
            actif.fixer_dossier(courant.id, str(racine))
            log.info("Document deja present : %s", fichier)
            return (
                f"Le dossier {racine.name} est déjà sur {ou_dit}, avec son "
                "document. Je n'y touche pas — dis-moi de le mettre à jour."
            )

        fichier.write_text(document.rendre(courant), encoding="utf-8")
        actif.fixer_dossier(courant.id, str(racine))
        log.info("Projet ecrit : %s", fichier)
        combien = document.poids(courant)
        return (
            f"C'est fait : le dossier {racine.name} est sur {ou_dit}, "
            f"avec {combien} élément(s) de notre conversation."
        )


class MettreAJourProjet:
    """Reecrit le document du projet avec ce qui a ete dit depuis."""

    nom = "mettre_a_jour_projet"
    description = "Réécrit le document d'un projet déjà écrit sur le disque"
    capacite = "action"
    #: ⚠️ CONSEQUENT, ET C'EST LE BAREME QUI LE DIT, MOT POUR MOT :
    #
    # « ecrire dans un fichier existant. Se defait mal. »
    #
    # `ecrire_projet` reste REVERSIBLE parce qu'il n'ecrase rien. Celui-ci
    # ecrase, donc il passe par le portillon : `executer_outil` refuse de
    # l'executer tant que `confirme` ne vient pas de l'UTILISATEUR. Un modele
    # ne peut pas remplir ce champ, et c'est toute la difference entre un
    # garde-fou et un decor.
    niveau = contrats.CONSEQUENT

    def executer(self, projet: str = "", ou: str = "") -> str:
        from nova.contexte import actif, document
        from nova.outils.systeme import ActionImpossible

        courant, racine, fichier, ou_dit = _emplacement(projet, ou)
        if not fichier.exists():
            raise ActionImpossible(
                f"Il n'y a pas encore de document pour {courant.nom}."
            )

        # ⚠️ ON GARDE L'ANCIEN AVANT DE L'EFFACER.
        #
        # Le portillon protege du « oui » distrait, pas de celui qu'on
        # regrette une seconde apres. Une copie coute quelques kilo-octets et
        # rend le seul accident possible ici entierement rattrapable.
        #
        # Une seule copie, remplacee a chaque fois : garder tout l'historique
        # remplirait le dossier de fichiers que personne ne relit.
        ancien = fichier.read_text(encoding="utf-8")
        (racine / document.nom_de_la_precedente(courant)).write_text(
            ancien, encoding="utf-8"
        )
        fichier.write_text(document.rendre(courant), encoding="utf-8")
        actif.fixer_dossier(courant.id, str(racine))
        log.info("Projet mis a jour : %s", fichier)
        return (
            f"C'est à jour : {document.poids(courant)} élément(s) dans le document "
            f"de {courant.nom}, sur {ou_dit}. J'ai gardé l'ancienne version à côté."
        )


class RangerDansLeProjet:
    """Deplace dans le dossier du projet les fichiers que Nova vient d'annoncer."""

    nom = "ranger_dans_le_projet"
    description = "Déplace les fichiers annoncés dans le dossier du projet en cours"
    capacite = "action"
    #: ⚠️ CONSEQUENT, ET C'EST LA TRACE QUI L'EMPECHE D'ETRE IRREVERSIBLE.
    #
    # Sur le papier, deplacer n'est ni supprimer ni ecraser : le fichier
    # existe toujours, entier, ailleurs. En pratique on ne retrouve pas ce
    # qu'on ne sait pas nommer — trois photos rangees au mauvais endroit sont
    # perdues, et la difference avec « detruites » n'interesse que les
    # informaticiens.
    #
    # `fichiers/ranger.py` enregistre d'ou venait chaque fichier. C'est ce qui
    # fait passer l'action de « ne se defait pas » a « se defait mal », donc
    # au niveau ou une confirmation suffit. Sans cette trace, il faudrait
    # IRREVERSIBLE — et le bareme n'a pas de niveau au-dessus.
    niveau = contrats.CONSEQUENT

    def executer(self, projet: str = "", ou: str = "") -> str:
        import shutil

        from nova.fichiers import ranger
        from nova.outils.systeme import ActionImpossible

        courant, racine, _, _ = _emplacement(projet, ou)
        if not racine.is_dir():
            raise ActionImpossible(
                f"Le dossier de {courant.nom} n'existe pas encore. "
                "Dis-moi d'abord de le créer."
            )

        chemins = _liste_a_ranger()
        if not chemins:
            raise ActionImpossible("Je n'ai rien annoncé récemment à ranger.")

        salve = ranger.nouvelle_salve()
        ranges, ignores = [], []
        for source in chemins:
            arrivee = racine / source.name
            # ⚠️ ON NE REMPLACE JAMAIS, MEME EN RANGEANT.
            #
            # Deux photos du meme nom venues de deux dossiers : la seconde
            # ecraserait la premiere, et le fichier serait detruit pour de
            # bon. `shutil.move` le fait sans rien dire.
            if arrivee.exists():
                ignores.append(source.name)
                continue
            try:
                shutil.move(str(source), str(arrivee))
            except Exception as erreur:  # noqa: BLE001
                log.warning("« %s » non range : %s", source, erreur)
                ignores.append(source.name)
                continue
            ranger.noter(courant.id, salve, source, arrivee)
            ranges.append(source.name)

        if not ranges:
            raise ActionImpossible("Je n'ai réussi à en ranger aucun.")
        log.info("%d fichier(s) ranges dans %s", len(ranges), racine)
        dit = f"J'ai rangé {len(ranges)} fichier(s) dans {racine.name}."
        if ignores:
            dit += f" J'en ai laissé {len(ignores)} : ils portaient un nom déjà pris."
        return dit + " Dis « remets-les où ils étaient » si je me suis trompée."


class RemettreOuIlsEtaient:
    """Defait le dernier rangement : chaque fichier retourne d'ou il venait."""

    nom = "remettre_ou_ils_etaient"
    description = "Remet à leur place les fichiers du dernier rangement"
    capacite = "action"
    #: Defaire un deplacement reste un deplacement : meme niveau, meme
    #: confirmation. Un « remets tout comme avant » mal entendu au milieu
    #: d'une phrase deferait un rangement qu'on venait de vouloir.
    niveau = contrats.CONSEQUENT

    def executer(self) -> str:
        import shutil

        from nova.contexte import actif
        from nova.fichiers import ranger
        from nova.outils.systeme import ActionImpossible

        courant = actif.projet_actif()
        faits = ranger.a_defaire(courant.id if courant else None)
        if not faits:
            raise ActionImpossible("Je n'ai rien rangé récemment.")

        remis, bloques = [], []
        for fait in faits:
            if not fait.est_alle_a.exists() or fait.venait_de.exists():
                bloques.append(fait.est_alle_a.name)
                continue
            try:
                fait.venait_de.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(fait.est_alle_a), str(fait.venait_de))
            except Exception as erreur:  # noqa: BLE001
                log.warning("« %s » non remis : %s", fait.est_alle_a, erreur)
                bloques.append(fait.est_alle_a.name)
                continue
            remis.append(fait.id)

        ranger.marquer_annules(remis)
        if not remis:
            raise ActionImpossible("Je n'ai pas pu en remettre un seul.")
        log.info("%d fichier(s) remis a leur place", len(remis))
        dit = f"C'est défait : {len(remis)} fichier(s) sont retournés d'où ils venaient."
        if bloques:
            dit += f" J'en ai laissé {len(bloques)} : leur place d'origine n'est plus libre."
        return dit


def _liste_a_ranger() -> tuple[Path, ...]:
    """Ce que Nova vient d'annoncer. Vide s'il n'y a rien de recent.

    ⚠️ C'EST LA BORNE LA PLUS IMPORTANTE DE CET OUTIL.

    Un outil qui accepterait un chemin libre pourrait ranger n'importe quoi.
    Celui-ci ne peut toucher que des fichiers dont Nova vient de dire le
    nombre a voix haute — et que l'on peut donc contester avant de dire oui.
    """
    from nova.vision import focus

    retenue = focus.derniere()
    if retenue is None or not retenue.liste:
        return ()
    return tuple(chemin for chemin in retenue.liste if chemin.is_file())


def _emplacement(projet: str, ou: str):
    """Le projet actif, son dossier, son document et comment DIRE l'endroit.

    Partage par les deux outils : ils doivent viser le meme fichier, et deux
    calculs separes finiraient par diverger sur un detail — un accent, une
    extension — que personne ne verrait avant de chercher un document a
    l'endroit ou il n'est pas.
    """
    from nova.contexte import actif, document
    from nova.fichiers.creer import _nom_propre, destination, nom_lisible
    from nova.outils.systeme import ActionImpossible

    courant = actif.projet_actif()
    if courant is None:
        raise ActionImpossible("Aucun projet ouvert.")
    # Le nom vient de la proposition ; le projet a pu changer entre-temps. On
    # ecrit ce qui est ACTIF, et on refuse si ce n'est plus le meme.
    if projet and _plat(projet) != _plat(courant.nom):
        raise ActionImpossible(
            f"Le projet en cours n'est plus « {projet} », mais « {courant.nom} »."
        )

    dossier_voulu = _nom_propre(courant.nom)
    if not dossier_voulu:
        raise FichierRefuse(f"« {courant.nom} » ne peut pas servir de nom de dossier.")

    parent = destination(ou)
    if parent is None:
        raise FichierRefuse(
            "Je n'ai pas le droit de créer là. "
            "Regarde NOVA_FICHIERS_CREATION_DOSSIERS."
        )

    racine = borner_creation(parent, dossier_voulu)
    return courant, racine, racine / document.nom_du_fichier(courant), nom_lisible(parent)


def _plat(texte: str) -> str:
    """Pour comparer deux noms de projet, pas pour les afficher."""
    import unicodedata

    sans = "".join(
        c for c in unicodedata.normalize("NFD", texte or "")
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(sans.lower().split())


def borner_creation(parent: Path, nom: str) -> Path:
    """Le chemin a creer, s'il est legitime. Sinon, on refuse.

    ⚠️ CE N'EST PAS `borner`, ET LES DEUX NE PEUVENT PAS FUSIONNER.

    `borner` exige `is_file()` : il verifie qu'une chose EXISTE avant d'y
    toucher. Ici la chose n'existe precisement pas encore, et c'est le PARENT
    qui doit exister. Une seule fonction pour les deux devrait donc rendre
    l'existence facultative — c'est-a-dire renoncer au controle qui fait tout
    l'interet de `borner`.

    Ce qui est verifie ici, dans cet ordre :

        le nom est UN SEUL cran — ni « / », ni « .. », ni un point en tete
        le parent est une racine d'ECRITURE declaree, resolue
        le resultat est encore SOUS ce parent apres resolution
        le resultat est ACCEPTABLE au sens de `fichiers/moteurs.py`

    La troisieme n'est pas redondante avec la premiere : sur macOS, un lien
    symbolique dans le parent peut faire sortir un nom pourtant anodin.
    """
    from nova.fichiers.creer import dossiers_ou_creer
    from nova.fichiers.moteurs import acceptable

    if nom in (".", "..") or "/" in nom or "\\" in nom or nom.startswith("."):
        raise FichierRefuse(f"« {nom} » n'est pas un nom de dossier valable.")

    racines = dossiers_ou_creer()
    if parent not in racines:
        raise FichierRefuse("Ce dossier n'est pas une zone où Nova peut créer.")
    if not parent.is_dir():
        raise FichierRefuse(f"« {parent.name} » n'existe pas sur cette machine.")

    cible = parent / nom
    try:
        resolu = cible.resolve()
    except OSError as erreur:
        raise FichierRefuse(f"Chemin illisible : {erreur}") from erreur
    if resolu.parent != parent.resolve():
        raise FichierRefuse(f"« {nom} » sort du dossier visé.")
    if not acceptable(resolu, racines=racines):
        raise FichierRefuse(f"Nova ne crée pas « {nom} » : ce nom est hors de sa portée.")
    return resolu


def enregistrer_outils_fichiers(registre) -> tuple[str, ...]:
    """Inscrit les outils de fichiers. Rend leurs noms.

    ⚠️ ENREGISTRES MEME QUAND LA RECHERCHE EST DESACTIVEE.

    Meme regle que les outils de vision : un outil qui apparait et disparait
    selon un reglage rend le catalogue different d'une machine a l'autre, et
    tout ce qui en depend — la deduction d'arguments, le routage, les bancs —
    devient impossible a raisonner. Le reglage decide de ce qui SE DECLENCHE
    dans la conversation, pas de ce qui EXISTE.
    """
    inscrits: list[str] = []
    for outil in (
        RechercherFichier(),
        OuvrirFichier(),
        CreerDossier(),
        EcrireProjet(),
        MettreAJourProjet(),
        RangerDansLeProjet(),
        RemettreOuIlsEtaient(),
    ):
        if outil.nom not in registre:
            registre.enregistrer(outil)
            inscrits.append(outil.nom)
    return tuple(inscrits)
