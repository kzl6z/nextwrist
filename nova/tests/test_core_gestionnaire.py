"""Le gestionnaire d'agents : qui fait quoi, et ce que personne ne fait.

CE QUE CE BANC PROTEGE

Le defaut qu'il a servi a trouver ne se voyait nulle part : `Conversationnel`
et `Documentaire` existaient, avec leurs propres bancs qui passaient, et
AUCUN code ne les enregistrait. Le registre les aurait d'ailleurs refuses —
il exige un `niveau` de risque, et ces agents avaient ete ecrits avant ce
bareme. `/v1/capacites` annoncait donc sincerement zero agent : un inventaire
exact d'un systeme vide, alors que le code etait la et teste.

Un module teste que rien n'appelle est plus trompeur qu'un module absent : la
revue du code le compte comme fait.

D'ou la forme de ce banc : il verifie surtout des BRANCHEMENTS. Que
l'enregistrement passe reellement, que le choix aboutisse a un appel, et que
l'absence d'executant soit dite plutot que contournee.
"""

from __future__ import annotations

import pytest

from nova.agents import registre_agents
from nova.core.contrats import CAPACITES_CONNUES, Demande, Etape, Plan
from nova.core.executeur import executer
from nova.core.gestionnaire import (
    SansExecutant,
    capacites_sans_executant,
    choisir,
    enregistrer_agents_standard,
    executant_pour,
    inventaire,
)
from nova.core.planificateur import planifier
from nova.outils import enregistrer_outils_standard, registre_outils


@pytest.fixture(autouse=True)
def briques(tmp_path):
    """Registres remplis comme au demarrage de l'application.

    ⚠️ `tmp_path` VA AUSSI AUX AGENTS DEPUIS L'AGENT DE VISION.

    Sans la racine, celui-ci retombait sur `settings.root / "data"` — le vrai
    dossier du projet. Un banc qui lit le disque de la machine ou il tourne
    passe ou echoue selon ce qui traine dedans.
    """
    enregistrer_outils_standard(tmp_path)
    enregistrer_agents_standard(lambda question: f"reponse a « {question} »", tmp_path)
    yield


# ══════════════════════════════════════════════════════════════════════════
#  L'ENREGISTREMENT
# ══════════════════════════════════════════════════════════════════════════
def test_les_agents_sont_reellement_inscrits():
    """⚠️ LE DEFAUT D'ORIGINE : LE REGISTRE LES REFUSAIT EN SILENCE.

    Faute d'attribut `niveau`, `registre_agents.enregistrer` levait — et
    comme personne n'appelait cette fonction, personne ne voyait l'exception.
    """
    assert "conversationnel" in registre_agents
    assert "documentaire" in registre_agents
    # ⚠️ INSCRIT MEME VISION DESACTIVEE.
    #
    # Un agent absent produit « aucun executant pour la capacite vision » ;
    # present, il produit « la vision est desactivee, voici comment
    # l'activer ». Le premier se cherche, le second se corrige.
    assert "vision" in registre_agents


def test_enregistrer_deux_fois_ne_casse_pas():
    """Relancer l'application ne doit pas echouer sur un doublon."""
    assert enregistrer_agents_standard(lambda q: q) == ()


def test_chaque_agent_declare_son_niveau_de_risque():
    """Tout ce qui s'execute doit dire ce qu'il en coute si Nova se trompe."""
    for agent in registre_agents.tout():
        assert isinstance(agent.niveau, int), agent.nom


# ══════════════════════════════════════════════════════════════════════════
#  LE CHOIX
# ══════════════════════════════════════════════════════════════════════════
def test_une_etape_de_conversation_va_a_un_agent():
    assert choisir(Etape("Repondre", "conversation")) == ("agent", "conversationnel")


def test_une_capacite_sans_personne_ne_rend_rien():
    """⚠️ RIEN, ET PAS UN OUTIL AU HASARD.

    Il serait facile d'appeler n'importe quoi pour eviter un trou dans le
    compte rendu. Ce serait exactement le mensonge que l'executeur est fait
    pour rendre impossible.
    """
    assert choisir(Etape("Ecrire un script", "code")) is None


def test_l_outil_appelable_sans_argument_passe_devant():
    """⚠️ CE FILTRE ETAIT UNE EXCLUSION, IL EST DEVENU UN DEPARTAGE.

    Il ecartait les outils exigeant des arguments, faute de savoir les
    deduire : mieux valait « aucun executant » qu'un `TypeError` accusant
    l'outil. Depuis `core.arguments`, les ecarter reviendrait a se priver
    d'outils utilisables — mais on prefere toujours celui qu'on peut appeler
    a coup sur.

    ⚠️ CE BANC A D'ABORD PASSE SEUL ET ECHOUE EN GROUPE.

    Ecrit sur « action », il choisissait `monter_le_son` des qu'un autre banc
    avait enregistre les actions systeme : le departage n'etait pas exerce,
    l'ordre d'enregistrement l'etait. Une capacite que rien d'autre ne couvre
    isole la propriete.
    """
    class Exigeant:
        nom = "exigeant"
        description = "demande un chemin"
        capacite = "code"
        niveau = 0

        def executer(self, chemin: str) -> str:
            return chemin

    class Simple:
        nom = "simple"
        description = "ne demande rien"
        capacite = "code"
        niveau = 0

        def executer(self) -> str:
            return "fait"

    registre_outils.enregistrer(Exigeant())
    registre_outils.enregistrer(Simple())
    try:
        assert choisir(Etape("Ecrire un script", "code")) == ("outil", "simple")
    finally:
        registre_outils._entrees.pop("exigeant", None)  # noqa: SLF001
        registre_outils._entrees.pop("simple", None)  # noqa: SLF001


def test_un_outil_qui_exige_des_arguments_reste_choisi_faute_de_mieux():
    """⚠️ « JE N'AI PAS SU DEDUIRE `chemin` » EST UN DIAGNOSTIC.

    « aucun executant pour la capacite code » alors qu'un outil existe n'en
    est pas un : il decrit le systeme comme plus pauvre qu'il n'est. Maintenant
    que la deduction sait refuser en nommant ce qui manque, mieux vaut essayer
    et dire pourquoi ca n'a pas marche.
    """
    class Exigeant:
        nom = "exigeant"
        description = "demande un chemin"
        capacite = "code"
        niveau = 0

        def executer(self, chemin: str) -> str:
            return chemin

    registre_outils.enregistrer(Exigeant())
    try:
        assert choisir(Etape("Ecrire un script", "code")) == ("outil", "exigeant")
    finally:
        registre_outils._entrees.pop("exigeant", None)  # noqa: SLF001


def test_une_etape_qui_nomme_son_executant_est_respectee():
    etape = Etape("Chercher", "recherche", executant="documentaire")

    assert choisir(etape) == ("agent", "documentaire")


# ══════════════════════════════════════════════════════════════════════════
#  L'INVENTAIRE — CE QUE PERSONNE NE SAIT FAIRE
# ══════════════════════════════════════════════════════════════════════════
def test_l_inventaire_couvre_toutes_les_capacites_connues():
    """Une capacite absente de l'inventaire serait un angle mort : le
    planificateur peut la produire, et rien ne dirait qu'elle n'est pas
    couverte."""
    assert set(inventaire()) == set(CAPACITES_CONNUES)


def test_les_capacites_sans_executant_sont_nommees():
    """⚠️ UNE PROMESSE DU PLANIFICATEUR QUE RIEN NE TIENDRA.

    Le dire au demarrage evite de le decouvrir au milieu d'un plan de sept
    etapes.
    """
    manquantes = capacites_sans_executant()

    assert "code" in manquantes, "personne ne sait ecrire du code, et il faut le dire"
    assert "conversation" not in manquantes


# ══════════════════════════════════════════════════════════════════════════
#  LE BRANCHEMENT SUR L'EXECUTEUR
# ══════════════════════════════════════════════════════════════════════════
def test_l_executant_du_gestionnaire_fait_reellement_travailler_un_agent():
    """Le branchement complet : plan → gestionnaire → agent → compte rendu."""
    demande = Demande(texte="Qu'est-ce qu'un trou noir ?")
    plan = planifier(demande)

    execution = executer(plan, executant=executant_pour(demande))

    assert execution.accomplie
    assert "trou noir" in str(execution.resultats[0].valeur)
    assert execution.resultats[0].executant == "gestionnaire"


def test_une_capacite_non_couverte_devient_une_etape_expliquee():
    """⚠️ LA CHAINE COMPLETE DOIT DIRE POURQUOI, PAS SEULEMENT QUE.

    Le gestionnaire leve `SansExecutant` plutot que de rendre `None` :
    l'executeur traduirait `None` en « l'executant n'a rien produit », ce qui
    est vrai mais se cherche. « aucun agent ni outil pour la capacite code »
    se corrige.

    ⚠️ CE BANC A D'ABORD DEPENDU DE L'ENVIRONNEMENT.

    Il partait d'un vrai plan de presentation, dont l'etape de recherche
    interroge la base documentaire. Sans base, cette etape echouait AVANT
    l'etape non couverte, qui ressortait alors « ignoree » — et le banc
    echouait pour une raison sans rapport avec ce qu'il annonce. Un plan
    construit ici isole la propriete testee.

    ⚠️ IL A AUSSI CHANGE DE CAPACITE, ET C'EST LE SUJET.

    Il s'appuyait sur « vision » comme exemple de ce que personne ne sait
    faire. L'agent de vision l'a couverte : le banc passait alors pour une
    raison qui n'existait plus. « code » est aujourd'hui la seule capacite
    sans executant — et le jour ou un agent la couvrira, ce banc echouera de
    nouveau. C'est ce qu'on lui demande.
    """
    demande = Demande(texte="ecris-moi un script")
    plan = Plan(demande=demande.texte, etapes=(Etape("Ecrire un script", "code"),))

    execution = executer(plan, executant=executant_pour(demande))

    assert execution.resultats[0].statut == "echouee"
    assert "code" in execution.resultats[0].detail
    assert not execution.accomplie


def test_l_absence_d_executant_est_une_exception_pas_un_silence():
    with pytest.raises(SansExecutant) as absence:
        executant_pour(Demande(texte="x"))(Etape("Ecrire un script", "code"))

    assert "code" in str(absence.value)


def test_le_gestionnaire_transmet_les_arguments_deduits():
    """⚠️ IL LES DEMANDE, IL NE LES DEVINE PAS.

    Le gestionnaire appelle `core.arguments` et transmet le resultat. La
    cible vient ici de la reconnaissance d'intention, sans modele : le
    branchement complet doit donc marcher hors ligne.
    """
    recus: list[str] = []

    class Ouvrir:
        nom = "ouvrir_banc"
        description = "Ouvre une application"
        capacite = "action"
        niveau = 0

        def executer(self, cible: str) -> str:
            recus.append(cible)
            return f"ouvert : {cible}"

    registre_outils.enregistrer(Ouvrir())
    try:
        etape = Plan(
            demande="x", etapes=(Etape("Ouvrir Spotify", "action", executant="ouvrir_banc"),)
        ).etapes[0]

        resultat = executant_pour(Demande(texte="ouvre Spotify"))(etape)

        assert recus == ["Spotify"]
        assert resultat == "ouvert : Spotify"
    finally:
        registre_outils._entrees.pop("ouvrir_banc", None)  # noqa: SLF001


def test_une_deduction_impossible_devient_une_etape_expliquee():
    """⚠️ ET PAS UN `TypeError` QUI ACCUSE L'OUTIL.

    Sans modele injecte, `chemin` reste introuvable. Le compte rendu doit
    nommer le parametre manquant : c'est ce qui distingue un defaut qu'on
    corrige d'un defaut qu'on cherche.
    """
    class Exigeant:
        nom = "exigeant"
        description = "demande un chemin"
        capacite = "action"
        niveau = 0

        def executer(self, chemin: str) -> str:  # pragma: no cover - jamais atteint
            return chemin

    registre_outils.enregistrer(Exigeant())
    try:
        demande = Demande(texte="fais le necessaire")
        plan = Plan(
            demande=demande.texte,
            etapes=(Etape("Agir", "action", executant="exigeant"),),
        )

        execution = executer(plan, executant=executant_pour(demande))

        assert execution.resultats[0].statut == "echouee"
        assert "chemin" in execution.resultats[0].detail
        assert "TypeError" not in execution.resultats[0].detail
    finally:
        registre_outils._entrees.pop("exigeant", None)  # noqa: SLF001


def test_un_outil_consequent_reste_soumis_a_confirmation():
    """⚠️ LE GESTIONNAIRE NE CONTOURNE PAS LE BAREME DE RISQUE.

    Il passe par `executer_outil`, qui verifie le niveau et leve
    `ConfirmationRequise`. Un chemin d'execution qui court-circuiterait ce
    controle rendrait le bareme decoratif.
    """
    from nova.outils import ConfirmationRequise, contrats

    class Consequent:
        nom = "envoyer_tout"
        description = "envoie quelque chose"
        capacite = "action"
        niveau = contrats.CONSEQUENT

        def executer(self) -> str:
            return "envoye"

    registre_outils.enregistrer(Consequent())
    try:
        # ⚠️ L'ETAPE NOMME SON OUTIL, ET CE N'EST PAS DU CONFORT.
        #
        # Sans ce nom, le banc dependait de l'ordre d'enregistrement : les
        # actions systeme couvrent aussi la capacite « action », et lancer la
        # suite complete faisait choisir l'une d'elles. Un banc qui passe seul
        # et echoue en groupe teste l'ordre des tests, pas le code.
        etape = Plan(
            demande="x",
            etapes=(Etape("Envoyer", "action", executant="envoyer_tout"),),
        ).etapes[0]

        traiter = executant_pour(Demande(texte="envoie"))
        with pytest.raises(ConfirmationRequise):
            traiter(etape)

        # Avec l'accord de l'utilisateur, la meme etape passe.
        avec_accord = executant_pour(Demande(texte="envoie"), confirmees=[1])
        assert avec_accord(etape) == "envoye"
    finally:
        registre_outils._entrees.pop("envoyer_tout", None)  # noqa: SLF001
