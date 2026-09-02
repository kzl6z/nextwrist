"""Lire, ecrire et basculer le contexte de travail.

⚠️ TOUT CE MODULE EST SANS MODELE.

Aucune fonction ici n'appelle une IA. Ouvrir un projet, noter une decision,
basculer d'un sujet a l'autre : ce sont des ecritures, et elles doivent etre
exactes, rapides et verifiables. Le modele, lui, INTERPRETE — et il le fait
avec ce que ce module lui donne.

C'est la meme separation que partout ailleurs : `focus` retient la liste,
le modele dit « le deuxieme ».
"""

from __future__ import annotations

from nova.contexte import ContexteActif, Element, Projet
from nova.db import connection
from nova.logging_setup import get_logger

log = get_logger(__name__)

#: Ce qu'on montre d'un projet dans le prompt, par genre.
#:
#: ⚠️ BORNE, POUR LA MEME RAISON QUE LE BUDGET DES FAITS.
#:
#: Sur un modele local, le temps avant le premier mot est proportionnel a la
#: TAILLE du prompt — ~3,3 ms par caractere, mesure sur l'iMac M1. Un contexte
#: qui grossit sans borne ralentit Nova a mesure qu'on travaille, c'est-a-dire
#: exactement quand on en a le plus besoin.
COMBIEN_PAR_GENRE = 5

#: Budget total du bloc de contexte, en caracteres.
BUDGET = 900


def _element(ligne: dict) -> Element:
    return Element(
        id=ligne["id"],
        genre=ligne["genre"],
        contenu=ligne["contenu"],
        pourquoi=ligne.get("pourquoi"),
        statut=ligne.get("statut", "ouvert"),
        source=ligne.get("source"),
        cree_le=ligne.get("cree_le"),
    )


def _projet(ligne: dict, elements: tuple[Element, ...] = ()) -> Projet:
    return Projet(
        id=ligne["id"],
        nom=ligne["nom"],
        objectif=ligne.get("objectif"),
        espace=ligne.get("espace"),
        confidentialite=ligne.get("confidentialite", "normal"),
        elements=elements,
    )


# ══════════════════════════════════════════════════════════════════════════
#  LIRE
# ══════════════════════════════════════════════════════════════════════════
def projet_actif() -> Projet | None:
    """Le projet en cours, avec ses elements. `None` s'il n'y en a pas.

    Un seul appel en base : la jointure evite le defaut classique — une
    requete pour le projet, puis une par genre — qui coute cinq allers-retours
    sur le chemin d'une reponse.
    """
    with connection() as conn:
        ligne = conn.execute(
            "SELECT * FROM projets WHERE actif ORDER BY dernier_contact DESC LIMIT 1"
        ).fetchone()
        if ligne is None:
            return None
        elements = conn.execute(
            """
            SELECT * FROM elements
            WHERE projet_id = %s
            ORDER BY cree_le DESC
            """,
            (ligne["id"],),
        ).fetchall()
    return _projet(ligne, tuple(_element(e) for e in elements))


def projets(limite: int = 20) -> list[Projet]:
    """Tous les projets connus, le plus recemment touche en premier."""
    with connection() as conn:
        lignes = conn.execute(
            "SELECT * FROM projets ORDER BY dernier_contact DESC LIMIT %s", (limite,)
        ).fetchall()
    return [_projet(ligne) for ligne in lignes]


def courant() -> ContexteActif:
    """Le contexte complet : le projet, et ce dont on vient de parler.

    Ne leve JAMAIS. Un contexte indisponible degrade la reponse — Nova en
    sait moins — il ne l'empeche pas. Meme regle que la memoire, la vision et
    la recherche documentaire.
    """
    projet = None
    try:
        projet = projet_actif()
    except Exception as erreur:  # noqa: BLE001
        log.warning("[Contexte] Projet actif illisible : %s", erreur)

    en_tete, fichiers = "", ()
    try:
        from nova.vision import focus

        if (retenue := focus.derniere()) is not None:
            en_tete = retenue.demande or retenue.chemin.name
            fichiers = tuple(c.name for c in retenue.liste) or (retenue.chemin.name,)
    except Exception as erreur:  # noqa: BLE001
        log.warning("[Contexte] Retenue illisible : %s", erreur)

    return ContexteActif(projet=projet, en_tete=en_tete, fichiers=fichiers)


# ══════════════════════════════════════════════════════════════════════════
#  ECRIRE
# ══════════════════════════════════════════════════════════════════════════
def ouvrir(nom: str, *, objectif: str | None = None, espace: str | None = None) -> Projet:
    """Ouvre un projet et le rend actif. Le cree s'il n'existe pas.

    ⚠️ IDEMPOTENT, ET C'EST NECESSAIRE.

    « ouvre le projet moteur » dit deux fois ne doit pas creer deux projets
    moteur, ni perdre ce qui a ete accumule dans le premier.
    """
    with connection() as conn:
        conn.execute("UPDATE projets SET actif = false WHERE actif")
        ligne = conn.execute(
            """
            INSERT INTO projets (nom, objectif, espace, actif, dernier_contact)
            VALUES (%s, %s, %s, true, now())
            ON CONFLICT (nom) DO UPDATE SET
                actif = true,
                dernier_contact = now(),
                objectif = COALESCE(EXCLUDED.objectif, projets.objectif),
                espace = COALESCE(EXCLUDED.espace, projets.espace)
            RETURNING *
            """,
            (nom.strip(), objectif, espace),
        ).fetchone()
    log.info("[Contexte] Projet actif : « %s »", ligne["nom"])
    return _projet(ligne)


def basculer(nom: str) -> Projet | None:
    """Rend actif un projet DEJA connu. `None` s'il n'existe pas.

    ⚠️ DISTINCT D'`ouvrir`, ET LA DIFFERENCE COMPTE.

    « revenons au projet NOVA » suppose qu'il existe : le creer a la volee sur
    un nom mal transcrit fabriquerait un projet fantome, vide, qui prendrait
    la place du vrai. On rend `None`, et l'appelant demande.
    """
    with connection() as conn:
        existe = conn.execute(
            "SELECT id FROM projets WHERE lower(nom) = lower(%s)", (nom.strip(),)
        ).fetchone()
        if existe is None:
            log.info("[Contexte] Aucun projet « %s » — rien n'est bascule.", nom)
            return None
        conn.execute("UPDATE projets SET actif = false WHERE actif")
        ligne = conn.execute(
            """
            UPDATE projets SET actif = true, dernier_contact = now()
            WHERE id = %s RETURNING *
            """,
            (existe["id"],),
        ).fetchone()
    log.info("[Contexte] Retour au projet « %s »", ligne["nom"])
    return _projet(ligne)


def fixer_objectif(objectif: str) -> Projet | None:
    """« On va essayer de gagner 15 % de puissance » — l'objectif du moment."""
    with connection() as conn:
        ligne = conn.execute(
            """
            UPDATE projets SET objectif = %s, dernier_contact = now()
            WHERE actif RETURNING *
            """,
            (objectif.strip(),),
        ).fetchone()
    if ligne is None:
        return None
    log.info("[Contexte] Objectif : %s", objectif.strip()[:60])
    return _projet(ligne)


def confidentialite(niveau: str) -> Projet | None:
    """« Je veux garder ca pour moi » devient une propriete du projet.

    ⚠️ SANS CE CHAMP, LA PHRASE EST ENTENDUE PUIS PERDUE.

    Elle doit se traduire quelque part que les outils puissent LIRE avant
    d'ecrire ou d'envoyer. Une intention de confidentialite qui ne vit que
    dans l'historique de conversation ne protege rien.
    """
    if niveau not in ("normal", "personnel"):
        raise ValueError(f"confidentialite inconnue « {niveau} »")
    with connection() as conn:
        ligne = conn.execute(
            "UPDATE projets SET confidentialite = %s WHERE actif RETURNING *",
            (niveau,),
        ).fetchone()
    if ligne is None:
        return None
    log.info("[Contexte] Confidentialite : %s", niveau)
    return _projet(ligne)


def noter(
    genre: str,
    contenu: str,
    *,
    pourquoi: str | None = None,
    source: str | None = None,
) -> Element | None:
    """Ajoute un element au projet actif. `None` s'il n'y en a pas.

    ⚠️ ON NE NOTE RIEN SANS PROJET, ET ON NE L'INVENTE PAS.

    Creer un projet « sans titre » pour pouvoir noter reviendrait a fabriquer
    du contexte que personne n'a demande — et il faudrait ensuite deviner
    quand le fermer.
    """
    from nova.contexte import GENRES

    if genre not in GENRES:
        raise ValueError(f"genre inconnu « {genre} ». Connus : {GENRES}")
    contenu = contenu.strip()
    if not contenu:
        return None

    with connection() as conn:
        projet = conn.execute("SELECT id FROM projets WHERE actif").fetchone()
        if projet is None:
            log.info("[Contexte] Rien note : aucun projet actif.")
            return None
        ligne = conn.execute(
            """
            INSERT INTO elements (projet_id, genre, contenu, pourquoi, source)
            VALUES (%s, %s, %s, %s, %s) RETURNING *
            """,
            (projet["id"], genre, contenu, pourquoi, source),
        ).fetchone()
        conn.execute(
            "UPDATE projets SET dernier_contact = now() WHERE id = %s", (projet["id"],)
        )
    log.info("[Contexte] %s notee : %s", genre.capitalize(), contenu[:60])
    return _element(ligne)


def clore(element_id: int, statut: str = "fait") -> None:
    """Une tache faite, une hypothese abandonnee.

    On ne SUPPRIME pas : « revenons a ce qu'on disait » a besoin de ce qui a
    ete abandonne. Meme regle que `facts.archive`.
    """
    if statut not in ("fait", "abandonne"):
        raise ValueError(f"statut inconnu « {statut} »")
    with connection() as conn:
        conn.execute(
            "UPDATE elements SET statut = %s, mis_a_jour_le = now() WHERE id = %s",
            (statut, element_id),
        )


# ══════════════════════════════════════════════════════════════════════════
#  LE BLOC DE PROMPT
# ══════════════════════════════════════════════════════════════════════════
def _lignes(titre: str, elements, *, avec_raison: bool = False) -> list[str]:
    if not elements:
        return []
    lignes = [titre]
    for element in elements[:COMBIEN_PAR_GENRE]:
        if avec_raison and element.pourquoi:
            lignes.append(f"- {element.contenu} (parce que {element.pourquoi})")
        else:
            lignes.append(f"- {element.contenu}")
    return lignes


def bloc(question: str = "") -> str:
    """Ce que Nova doit savoir du travail en cours, pour CETTE phrase.

    ⚠️ CE BLOC NE RESOUT AUCUNE REFERENCE. IL FOURNIT LES REFERENTS.

    C'est la decision de conception centrale, et elle est explicitement
    demandee : pas de regle « si la phrase dit "augmente ca" alors … ». Une
    telle regle donnerait l'illusion de comprendre et casserait a la premiere
    tournure non prevue — le francais ne se met pas en liste.

    On dit au modele CE DONT ON PARLE. C'est lui qui rattache « ca » a la
    bonne chose, et c'est son travail.

    C'est exactement ce qui a marche pour « ouvre le deuxieme » : nous ne
    devinons pas lequel, nous retenons la LISTE dans l'ordre annonce.

    ⚠️ ET IL EST BORNE, POUR LA MEME RAISON QUE LES FAITS.

    ~3,3 ms par caractere avant le premier mot sur l'iMac M1. Un contexte qui
    grossit sans borne ralentit Nova a mesure qu'on travaille — exactement
    quand on en a le plus besoin.
    """
    etat = courant()
    if etat.vide:
        return ""

    lignes: list[str] = ["## Le travail en cours"]
    projet = etat.projet

    if projet is not None:
        lignes.append(f"Projet : {projet.nom}")
        if projet.objectif:
            lignes.append(f"Objectif : {projet.objectif}")
        if projet.confidentialite == "personnel":
            # ⚠️ ON LE DIT AU MODELE, ET LES OUTILS LE LISENT AUSSI.
            #
            # Une consigne dans le prompt est une intention, pas une garantie.
            # Ce champ existe en base precisement pour que les outils puissent
            # le verifier sans faire confiance au modele.
            lignes.append(
                "Confidentialite : PERSONNEL — ne propose aucune destination "
                "partagee ni aucun envoi."
            )
        lignes += _lignes("Entites dont on parle :", projet.entites)
        lignes += _lignes("Taches en cours :", projet.taches)
        lignes += _lignes("Decisions prises :", projet.decisions, avec_raison=True)
        lignes += _lignes("Hypotheses en cours :", projet.hypotheses)
        lignes += _lignes("Questions en attente :", projet.questions)

    if etat.en_tete:
        # ⚠️ CE DONT ON PARLE, JAMAIS LE NOM DU FICHIER.
        #
        # La premiere version numerotait les fichiers annonces. Un banc l'a
        # prise en defaut, et il avait raison : Nova ne cite plus les
        # documents qu'elle trouve, et remettre leurs noms dans le prompt
        # defaisait cette correction par la porte de derriere.
        #
        # Le modele n'en a pas besoin. « le deuxieme » est resolu par
        # `fichier_en_tete_pour` et `image_en_tete_pour`, hors du modele, sur
        # la liste retenue dans l'ordre. Lui donner les noms ne l'aiderait pas
        # a mieux choisir — ca lui donnerait de quoi les prononcer.
        lignes.append(f"Dont on vient de parler : {etat.en_tete}")
        if len(etat.fichiers) > 1:
            lignes.append(
                f"{len(etat.fichiers)} documents ont ete annonces, dans l'ordre. "
                "Tu n'as pas leurs noms : « le deuxieme » est resolu sans toi."
            )

    if len(lignes) == 1:  # rien que le titre
        return ""

    lignes.append(
        "Quand une phrase dit « ca », « celui-la », « cette valeur », elle "
        "designe quelque chose de cette liste. Si deux choses conviennent, "
        "demande LAQUELLE en une phrase courte."
    )

    texte = "\n".join(lignes)
    if len(texte) > BUDGET:
        # ⚠️ ON COUPE PAR LA FIN, PAS AU HASARD.
        #
        # Les lignes sont dans l'ordre d'importance : le projet et l'objectif
        # d'abord, les hypotheses ensuite. Ce qui tombe est ce dont on peut se
        # passer — et la consigne finale est reattachee, parce que sans elle
        # le reste ne sert a rien.
        garde: list[str] = []
        total = 0
        for ligne in lignes[:-1]:
            if total + len(ligne) + 1 > BUDGET - len(lignes[-1]):
                break
            garde.append(ligne)
            total += len(ligne) + 1
        garde.append(lignes[-1])
        texte = "\n".join(garde)
        log.info("[Contexte] Bloc tronque a %d caracteres (budget %d).", len(texte), BUDGET)

    log.info("[Contexte] %d caracteres injectes.", len(texte))
    return texte
