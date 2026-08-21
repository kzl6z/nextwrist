"""La circulation des resultats : un plan est-il une chaine, ou cinq demandes ?

LE DEFAUT QUE CE BANC EXISTE POUR EMPECHER DE REVENIR

L'executeur parcourait les etapes dans l'ordre, et chaque executant ne
recevait que son etape :

    Executant = Callable[[Etape], Any]

Un plan de cinq etapes n'etait donc pas une chaine — c'etaient cinq demandes
independantes posees a la suite. « Presenter le diagnostic » redigeait a
partir de la question d'origine, sans jamais voir ce que « Observer l'objet »
avait constate.

⚠️ ET RIEN NE LE SIGNALAIT.

Chaque etape rendait `faite`. Le compte rendu etait complet, le statut
`terminee`, et la reponse finale etait une phrase plausible sans aucun
rapport avec l'image. C'est exactement la forme de mensonge que l'executeur
avait ete ecrit pour rendre impossible — et elle passait par le seul endroit
qu'il ne regardait pas : ce qu'il transmet.

D'ou la forme de ce banc. Il verifie trois choses, et la troisieme n'est pas
la moins importante :

    ce qui CIRCULE          l'observation atteint-elle la redaction
    ce qui NE circule PAS   une etape echouee n'a rien produit
    ce qui NE CHANGE PAS    le cas courant doit couter ce qu'il coutait
"""

from __future__ import annotations

import pytest

from nova.core.contrats import Demande, Etape, Plan
from nova.core.executeur import Acquis, Resultat, executer, socle


def _fait(numero: int, intitule: str, valeur) -> Resultat:
    return Resultat(numero, intitule, "faite", valeur=valeur)


def _chaine(*intitules: tuple[str, str]) -> Plan:
    """Un plan en chaine : chaque etape depend de la precedente."""
    return Plan(
        demande="x",
        etapes=tuple(
            Etape(intitule, capacite, depend_de=(rang - 1,) if rang else ())
            for rang, (intitule, capacite) in enumerate(intitules)
        ),
    )


# ══════════════════════════════════════════════════════════════════════════
#  LE SOCLE — ce qu'une etape a le droit de voir
# ══════════════════════════════════════════════════════════════════════════
def test_le_socle_est_transitif():
    """⚠️ LA DECISION CENTRALE DU MODULE.

    L'etape 5 ne declare qu'une dependance : l'etape 4. S'en tenir aux
    dependances DIRECTES lui donnerait les causes probables et lui cacherait
    l'observation d'origine — celle qui dit ce qu'on regarde. Elle redigerait
    un diagnostic sans savoir de quel objet il s'agit.
    """
    plan = _chaine(
        ("Observer", "vision"),
        ("Identifier", "extraction"),
        ("Rechercher", "recherche"),
        ("Etablir les causes", "raisonnement"),
        ("Presenter", "redaction"),
    )

    assert socle(plan, 4) == (0, 1, 2, 3)
    assert socle(plan, 0) == ()


def test_le_socle_ne_ramasse_pas_une_branche_sans_rapport():
    """⚠️ TRANSITIF N'EST PAS « TOUT CE QUI PRECEDE ».

    Sur un losange, deux branches independantes se rejoignent. Donner a
    l'etape 2 le travail de l'etape 1 melangerait des sujets sans rapport et
    ferait passer un budget de prompt dans du bruit.
    """
    plan = Plan(
        demande="x",
        etapes=(
            Etape("Brancher a gauche", "recherche"),
            Etape("Brancher a droite", "recherche"),
            Etape("Suivre a gauche", "raisonnement", depend_de=(0,)),
            Etape("Reunir", "redaction", depend_de=(1, 2)),
        ),
    )

    assert socle(plan, 2) == (0,), "la branche gauche ignore la droite"
    assert socle(plan, 3) == (0, 1, 2), "la reunion voit les deux"


def test_un_cycle_ne_fait_pas_boucler_le_socle():
    plan = Plan(
        demande="x",
        etapes=(
            Etape("A", "recherche", depend_de=(1,)),
            Etape("B", "recherche", depend_de=(0,)),
        ),
    )

    assert socle(plan, 0) == (0, 1)


def test_une_dependance_inexistante_est_ignoree_sans_lever():
    plan = Plan(demande="x", etapes=(Etape("Seule", "recherche", depend_de=(7,)),))

    assert socle(plan, 0) == ()


# ══════════════════════════════════════════════════════════════════════════
#  L'ACQUIS — ce qu'on transmet, et ce qu'on refuse de transmettre
# ══════════════════════════════════════════════════════════════════════════
def test_un_acquis_vide_est_faux():
    assert not Acquis()
    assert Acquis().texte() == ""


def test_le_texte_nomme_l_etape_qui_a_produit():
    """Sans le numero ni l'intitule, le modele recoit des valeurs orphelines
    et ne peut pas savoir laquelle repond a quoi."""
    acquis = Acquis((_fait(1, "Observer l'objet", "une casquette blanche"),))

    texte = acquis.texte()

    assert "Etape 1" in texte
    assert "Observer l'objet" in texte
    assert "une casquette blanche" in texte


def test_un_dictionnaire_devient_lisible():
    acquis = Acquis((_fait(1, "Observer", {"image": "piece.png", "description": "cassee"}),))

    texte = acquis.texte()

    assert "image : piece.png" in texte
    assert "description : cassee" in texte


def test_les_champs_vides_ne_prennent_pas_de_place():
    acquis = Acquis((_fait(1, "Observer", {"image": "a.png", "note": "", "autre": None}),))

    texte = acquis.texte()

    assert "note" not in texte
    assert "autre" not in texte


def test_une_valeur_illisible_ne_fait_pas_tomber_l_execution():
    """⚠️ CETTE FONCTION EST APPELEE SUR CE QU'UN OUTIL A RENDU.

    Donc sur n'importe quoi. Un defaut d'affichage ne doit pas detruire un
    travail reel.
    """

    class Recalcitrant:
        def __str__(self) -> str:
            raise RuntimeError("je refuse")

    assert "illisible" in Acquis((_fait(1, "X", Recalcitrant()),)).texte()


def test_le_budget_garde_les_etapes_recentes():
    """⚠️ SUR UNE CHAINE, LA DERNIERE PORTE LE TRAVAIL DES PRECEDENTES.

    Couper par la fin jetterait le resultat le plus abouti pour garder une
    observation brute deja consommee.
    """
    acquis = Acquis(
        (
            _fait(1, "Premiere", "vieux" * 100),
            _fait(2, "Seconde", "recent" * 100),
        )
    )

    texte = acquis.texte(budget=300)

    assert "recent" in texte
    assert "vieux" not in texte, "c'est l'ancien qu'on coupe, pas le recent"
    assert len(texte) <= 320, "le budget est respecte a l'en-tete pres"


def test_la_valeur_d_une_etape_se_retrouve_par_son_numero():
    acquis = Acquis((_fait(1, "Observer", "vu"), _fait(2, "Rediger", "ecrit")))

    assert acquis.valeur(2) == "ecrit"
    assert acquis.valeur(9) is None


def test_un_champ_se_retrouve_a_travers_les_dictionnaires():
    """C'est ce qui permet a l'etape suivante de reutiliser un chemin de
    fichier deja etabli, plutot que de le redemander a un modele."""
    acquis = Acquis((_fait(1, "Observer", {"chemin": "/tmp/piece.png"}),))

    assert acquis.champ("chemin") == "/tmp/piece.png"
    assert acquis.champ("absent") is None


def test_le_champ_le_plus_recent_gagne():
    """Sur une chaine, la valeur la plus recente est celle qui a ete calculee
    en connaissance des precedentes."""
    acquis = Acquis(
        (_fait(1, "Observer", {"chemin": "/a.png"}), _fait(2, "Corriger", {"chemin": "/b.png"}))
    )

    assert acquis.champ("chemin") == "/b.png"


# ══════════════════════════════════════════════════════════════════════════
#  LE PARCOURS — ce qui circule reellement
# ══════════════════════════════════════════════════════════════════════════
def test_l_observation_atteint_la_derniere_etape():
    """LE BANC CENTRAL : le defaut d'origine, en une assertion."""
    recus: list[str] = []

    def executant(etape, acquis):
        recus.append(acquis.texte())
        return f"resultat de {etape.intitule}"

    plan = _chaine(
        ("Observer l'objet", "vision"),
        ("Etablir les causes", "raisonnement"),
        ("Presenter le diagnostic", "redaction"),
    )

    executer(plan, executant=executant)

    assert recus[0] == "", "la premiere etape ne depend de rien"
    assert "Observer l'objet" in recus[2], "l'observation doit atteindre la redaction"
    assert "Etablir les causes" in recus[2]


def test_une_etape_echouee_ne_transmet_rien():
    """⚠️ LE MENSONGE DEPLACE D'UN CRAN.

    Faire figurer une etape echouee avec une valeur vide donnerait a la
    suivante l'impression d'avoir une base.
    """
    vus: list[tuple[int, ...]] = []

    def executant(etape, acquis):
        vus.append(tuple(r.numero for r in acquis.resultats))
        if etape.numero == 1:
            raise RuntimeError("l'image est illisible")
        return "suite"

    plan = Plan(
        demande="x",
        etapes=(
            Etape("Observer", "vision"),
            Etape("Chercher", "recherche"),
            Etape("Rediger", "redaction", depend_de=(0, 1)),
        ),
    )

    execution = executer(plan, executant=executant)

    assert execution.resultats[0].statut == "echouee"
    # L'etape 3 n'est jamais tentee — sa dependance n'a pas abouti. C'est la
    # protection de premier rang ; l'acquis en est une seconde.
    assert execution.resultats[2].statut == "ignoree"


def test_seules_les_etapes_faites_entrent_dans_l_acquis():
    """La regle, verifiee sans dependre de l'ordre du parcours."""
    acquis = Acquis(
        tuple(
            r
            for r in (
                _fait(1, "Faite", "utile"),
                Resultat(2, "Echouee", "echouee", "casse"),
                Resultat(3, "Ignoree", "ignoree", "pas d'executant"),
            )
            if r.accomplie
        )
    )

    texte = acquis.texte()

    assert "utile" in texte
    assert "casse" not in texte
    assert "pas d'executant" not in texte


# ══════════════════════════════════════════════════════════════════════════
#  ⚠️ CE QUI NE DOIT PAS CHANGER
# ══════════════════════════════════════════════════════════════════════════
def test_un_executant_a_un_seul_argument_marche_toujours():
    """⚠️ TOUT LE PROJET EN ECRIVAIT AINSI, BANCS COMPRIS.

    Exiger un second parametre inutilise de tous les executants pour le
    benefice de quelques-uns aurait ete du bruit — et une migration a risque
    pour une fonctionnalite qui n'en demandait pas.
    """
    plan = _chaine(("Repondre", "conversation"))

    execution = executer(plan, executant=lambda etape: f"fait : {etape.intitule}")

    assert execution.accomplie
    assert execution.resultats[0].valeur == "fait : Repondre"


def test_le_nom_de_l_executant_survit_a_l_adaptation():
    """⚠️ UNE ENVELOPPE ANONYME AURAIT PERDU L'AUTEUR DU TRAVAIL.

    `_tenter` lit `executant.nom` pour dire QUI a fait quoi. Adapter la
    signature ne doit pas transformer le compte rendu en « executant : None »
    sur toutes les etapes.
    """

    def executant(etape):
        return "fait"

    executant.nom = "gestionnaire"

    execution = executer(_chaine(("Repondre", "conversation")), executant=executant)

    assert execution.resultats[0].executant == "gestionnaire"


def test_un_appelable_a_la_signature_illisible_ne_casse_pas():
    """Le repli qui ne coute rien : au pire il ignore un contexte, au lieu de
    lever un TypeError qui ferait echouer une etape executable."""

    class Exotique:
        nom = "exotique"

        def __call__(self, *args):
            return "fait"

    execution = executer(_chaine(("Repondre", "conversation")), executant=Exotique())

    assert execution.accomplie


def test_sans_executant_le_compte_rendu_est_inchange():
    execution = executer(_chaine(("Repondre", "conversation")))

    assert execution.resultats[0].statut == "ignoree"
    assert "aucun executant" in execution.resultats[0].detail


# ══════════════════════════════════════════════════════════════════════════
#  LES AGENTS
# ══════════════════════════════════════════════════════════════════════════
def test_le_conversationnel_sans_acquis_repond_exactement_comme_avant():
    """⚠️ LE CAS COURANT NE DOIT PAS PAYER POUR LE CAS RARE.

    L'ecrasante majorite des demandes sont des plans directs a une seule
    etape. « Qu'est-ce qu'un trou noir ? » n'a aucun acquis et doit continuer
    de couter exactement ce qu'elle coutait. Une amelioration qui ralentit le
    cas courant pour servir le cas rare est l'echange que ce projet a deja
    paye trois fois.
    """
    from nova.agents import Conversationnel

    recus: list[str] = []
    agent = Conversationnel(lambda q: recus.append(q) or "ok")

    agent.executer(Etape("Repondre", "conversation"), Demande(texte="qu'est-ce qu'un trou noir"))

    assert recus == ["qu'est-ce qu'un trou noir"], "aucun enrobage ajoute"


def test_le_conversationnel_avec_acquis_recoit_le_contexte():
    from nova.agents import Conversationnel

    recus: list[str] = []
    agent = Conversationnel(lambda q: recus.append(q) or "ok")
    acquis = Acquis((_fait(1, "Observer", "a white cap with 'alo' on it"),))

    agent.executer(
        Etape("Presenter le diagnostic", "redaction"),
        Demande(texte="analyse cette casquette"),
        acquis,
    )

    assert "white cap" in recus[0], "l'observation doit etre transmise"
    assert "francais" in recus[0], "la reponse doit etre demandee en francais"
    assert "analyse cette casquette" in recus[0], "la demande d'origine reste"


def test_un_agent_a_deux_parametres_reste_appelable():
    """Le contrat `Agent` est satisfait par les deux formes : la vision
    regarde une image, pas un contexte."""
    from nova.core.gestionnaire import _accepte_acquis

    class Deux:
        def executer(self, etape, demande):
            return "fait"

    class Trois:
        def executer(self, etape, demande, acquis=None):
            return "fait"

    assert not _accepte_acquis(Deux().executer)
    assert _accepte_acquis(Trois().executer)


# ══════════════════════════════════════════════════════════════════════════
#  LA DEDUCTION D'ARGUMENTS
# ══════════════════════════════════════════════════════════════════════════
def test_un_chemin_deja_etabli_n_est_pas_redemande_a_un_modele():
    """⚠️ LE PIRE DES GASPILLAGES.

    L'agent de vision rend `{"chemin": "/…/piece.png"}` ; l'etape suivante
    attend un `chemin`. Le redecouvrir par probabilite serait absurde — et
    parfois faux.
    """
    from nova.core.arguments import deduire

    class Lister:
        nom = "lister_banc"
        description = "liste ce que montre une image"
        capacite = "extraction"
        niveau = 0

        def executer(self, chemin: str) -> str:
            return chemin

    appels: list[str] = []
    acquis = Acquis((_fait(1, "Observer", {"chemin": "/tmp/piece.png", "image": "piece.png"}),))

    trouves = deduire(
        Lister(),
        Etape("Identifier les composants", "extraction"),
        Demande(texte="analyse cette piece"),
        proposer=lambda c: appels.append(c) or "{}",
        acquis=acquis,
    )

    assert trouves == {"chemin": "/tmp/piece.png"}
    assert appels == [], "aucun modele appele : la valeur etait deja sure"


def test_l_acquis_ne_recouvre_pas_ce_que_l_intention_a_trouve():
    """L'ordre des etages est une precedence : le deterministe garde la main."""
    from nova.core.arguments import deduire

    class Ouvrir:
        nom = "ouvrir_banc"
        description = "ouvre une application"
        capacite = "action"
        niveau = 0

        def executer(self, cible: str) -> str:
            return cible

    acquis = Acquis((_fait(1, "Observer", {"cible": "Terminal"}),))

    trouves = deduire(
        Ouvrir(), Etape("Ouvrir Spotify", "action"), Demande(texte="ouvre Spotify"), acquis=acquis
    )

    assert trouves == {"cible": "Spotify"}


def test_un_acquis_absent_laisse_la_deduction_inchangee():
    from nova.core.arguments import deduire

    class Chercheur:
        nom = "chercher_banc"
        description = "cherche"
        capacite = "recherche"
        niveau = 0

        def executer(self, question: str) -> str:
            return question

    assert deduire(
        Chercheur(), Etape("Chercher", "recherche"), Demande(texte="les trous noirs")
    ) == {"question": "les trous noirs"}


def test_la_consigne_du_modele_porte_l_acquis():
    """Le modele n'a plus a deviner ce qui est etabli — il lui reste a le
    reconnaitre, ce qui est une tache beaucoup plus sure."""
    from nova.core.arguments import consigne

    class Exigeant:
        nom = "exigeant"
        description = "demande un chemin"
        capacite = "extraction"
        niveau = 0

        def executer(self, chemin: str) -> str:
            return chemin

    texte = consigne(
        Exigeant(),
        Etape("Lire", "extraction"),
        Demande(texte="lis ca"),
        Acquis((_fait(1, "Observer", "le fichier est rapport.txt"),)),
    )

    assert "Deja etabli" in texte
    assert "rapport.txt" in texte


# ══════════════════════════════════════════════════════════════════════════
#  LA CHAINE COMPLETE
# ══════════════════════════════════════════════════════════════════════════
def test_la_chaine_complete_transmet_l_observation_a_la_redaction(tmp_path):
    """plan → gestionnaire → agent de vision → agent conversationnel.

    C'est le scenario qui a motive tout ce module : un modele de vision qui
    decrit en anglais, et une redaction francaise qui doit s'appuyer dessus.
    """
    from nova.agents import registre_agents
    from nova.agents.vision import Vision
    from nova.core.gestionnaire import enregistrer_agents_standard, executant_pour
    from nova.outils import enregistrer_outils_standard
    from nova.vision import Observation

    class MoteurAnglais:
        def decrire(self, image):
            from pathlib import Path

            return Observation(source=Path(image), description="a white cap, brim bent")

    recus: list[str] = []
    enregistrer_outils_standard(tmp_path)
    (tmp_path / "casquette.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    # ⚠️ LE REGISTRE EST GLOBAL, ET `enregistrer_agents_standard` EST IDEMPOTENT.
    #
    # Enregistrer ici un conversationnel de banc le laissait en place pour
    # TOUS les fichiers suivants — qui appelaient bien la fonction, mais
    # n'obtenaient rien puisque le nom etait deja pris. Un banc d'un autre
    # fichier recevait alors « diagnostic en francais » a la place de sa
    # propre reponse, et echouait pour une raison qui n'etait pas chez lui.
    #
    # On remet donc le registre exactement dans l'etat ou on l'a trouve.
    avant = dict(registre_agents._entrees)  # noqa: SLF001
    registre_agents._entrees.clear()  # noqa: SLF001
    try:
        enregistrer_agents_standard(
            lambda q: recus.append(q) or "diagnostic en francais", tmp_path
        )
        registre_agents._entrees["vision"] = Vision(  # noqa: SLF001
            tmp_path, moteur=MoteurAnglais()
        )

        demande = Demande(texte="analyse cette casquette")
        plan = _chaine(
            ("Observer l'objet et son etat", "vision"),
            ("Presenter le diagnostic", "redaction"),
        )

        execution = executer(plan, executant=executant_pour(demande))

        assert execution.accomplie, execution.resume()
        assert "a white cap, brim bent" in recus[-1], "l'observation anglaise doit remonter"
        assert "francais" in recus[-1], "et la redaction doit etre demandee en francais"
    finally:
        registre_agents._entrees.clear()  # noqa: SLF001
        registre_agents._entrees.update(avant)  # noqa: SLF001


@pytest.mark.parametrize("valeur", [None, "", [], {}])
def test_une_valeur_vide_ne_produit_pas_de_bloc_fantome(valeur):
    """⚠️ CE BANC A D'ABORD ETE ECRIT DE FACON A NE JAMAIS POUVOIR ECHOUER.

    Sa premiere version — « pas d'en-tete OU du texte non vide » — etait vraie
    dans les deux cas possibles. Elle cachait un vrai defaut : `texte()`
    n'ecartait un bloc que si l'ENSEMBLE en-tete+valeur etait vide, or
    l'en-tete ne l'est jamais. Une etape sans resultat produisait donc
    « [Etape 1 — Vide] » suivi de rien — ce qui laisse croire qu'elle a
    produit quelque chose d'illisible plutot que rien.

    Une assertion qui ne peut pas echouer n'est pas un banc.
    """
    assert Acquis((_fait(1, "Vide", valeur),)).texte() == ""


def test_une_etape_vide_n_efface_pas_les_suivantes():
    """Ecarter un bloc vide ne doit pas interrompre le parcours des autres."""
    acquis = Acquis((_fait(1, "Utile", "gardee"), _fait(2, "Vide", None)))

    assert "gardee" in acquis.texte()
