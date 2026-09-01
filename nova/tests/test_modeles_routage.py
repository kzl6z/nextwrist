"""Le Model Router : quel cerveau pour quelle tache, et que faire s'il tombe.

CE QUE CES BANCS PROTEGENT

    demande  →  routeur.classer(usage)  →  fournisseur.flux()  →  jetons
                        |
                        └─ echec AVANT le premier jeton  →  candidat suivant

⚠️ ET ILS PROTEGENT SURTOUT DEUX CHOSES QU'ON NE VOIT PAS EN LISANT.

Un recours APRES le premier jeton collerait deux moities de reponses : ce
n'est pas une degradation, c'est une phrase qu'aucun modele n'a ecrite.

Et le local d'abord n'est pas une preference de style : sans lui, un modele
distant configure emporte toute la conversation courante — latence, cout, et
sortie de donnees, pour une reponse que le local donnait deja.
"""

from __future__ import annotations

import pytest

from nova.core.contrats import Modele
from nova.core.routeur import AucunModele, Routeur
from nova.modeles import routage
from nova.modeles.routage import AucunModeleN_aRepondu


# ══════════════════════════════════════════════════════════════════════════
#  DES FOURNISSEURS DE BANC
#
#  ⚠️ AUCUN RESEAU, AUCUN MODELE, AUCUNE MACHINE.
#
#  C'est la raison d'etre du contrat `Fournisseur` : le routage se teste
#  entierement sans Ollama et sans clef. Un routeur qu'on ne peut exercer que
#  sur la machine de quelqu'un d'autre, on le casse sans le savoir — c'est
#  exactement ce qui vient d'arriver aux bancs de fichiers.
# ══════════════════════════════════════════════════════════════════════════
class FauxFournisseur:
    """Rend ce qu'on lui dit de rendre, et retient ce qu'on lui a demande."""

    def __init__(
        self,
        identifiant: str,
        modeles: tuple[Modele, ...],
        *,
        morceaux: tuple[str, ...] = ("bonjour",),
        echoue: Exception | None = None,
        echoue_apres: int | None = None,
        libre: bool = True,
    ) -> None:
        self.id = identifiant
        self.nom = f"Fournisseur {identifiant}"
        self._modeles = modeles
        self._morceaux = morceaux
        self._echoue = echoue
        self._echoue_apres = echoue_apres
        self._libre = libre
        self.appels: list[str] = []

    def modeles(self) -> tuple[Modele, ...]:
        return self._modeles

    def disponible(self) -> bool:
        return self._libre

    def flux(self, modele, messages, **kw):
        self.appels.append(modele.nom)
        if self._echoue is not None and self._echoue_apres is None:
            raise self._echoue
        for rang, morceau in enumerate(self._morceaux):
            if self._echoue_apres is not None and rang == self._echoue_apres:
                raise self._echoue or RuntimeError("coupure")
            yield morceau

    def generer(self, modele, messages, **kw):
        self.appels.append(modele.nom)
        if self._echoue is not None:
            raise self._echoue
        return "".join(self._morceaux)

    def sante(self) -> bool:
        return self._libre


LOCAL = Modele(
    nom="llama-local",
    capacites=frozenset({"conversation", "raisonnement", "extraction"}),
    vitesse=28.8,
    poids=2.0,
    distant=False,
    fournisseur="local",
)
DISTANT = Modele(
    nom="claude-distant",
    capacites=frozenset({"conversation", "raisonnement", "long_contexte"}),
    vitesse=60.0,
    poids=100.0,
    distant=True,
    fournisseur="distant",
)


def _routeur(*modeles: Modele) -> Routeur:
    return Routeur(modeles)


# ══════════════════════════════════════════════════════════════════════════
#  1 & 2. LE MODELE LOCAL, PRESENT OU NON
# ══════════════════════════════════════════════════════════════════════════
def test_le_modele_local_disponible_repond():
    local = FauxFournisseur("local", (LOCAL,), morceaux=("c'est", " bon"))

    sortie = "".join(
        routage.flux("conversation", [], routeur=_routeur(LOCAL), sources=(local,))
    )

    assert sortie == "c'est bon"
    assert local.appels == ["llama-local"]


def test_sans_aucun_modele_le_routeur_refuse_au_lieu_d_inventer():
    """⚠️ UN CHOIX APPROXIMATIF SILENCIEUX EST PIRE QU'UN ECHEC.

    Il se manifeste par des reponses mediocres qu'on attribue au projet
    entier. Le routeur leve, et son message dit ce qui a ete ecarte.
    """
    with pytest.raises(AucunModele):
        list(routage.flux("conversation", [], routeur=_routeur(), sources=()))


def test_le_local_indisponible_laisse_la_main_au_distant():
    from nova.llm.client import LLMError

    local = FauxFournisseur("local", (LOCAL,), echoue=LLMError("Ollama est eteint"))
    distant = FauxFournisseur("distant", (DISTANT,), morceaux=("je", " prends", " le", " relais"))

    sortie = "".join(
        routage.flux(
            "conversation", [], routeur=_routeur(LOCAL, DISTANT), sources=(local, distant)
        )
    )

    assert sortie == "je prends le relais"
    assert local.appels == ["llama-local"], "le local a bien ete essaye EN PREMIER"
    assert distant.appels == ["claude-distant"]


# ══════════════════════════════════════════════════════════════════════════
#  3 & 4. SIMPLE OU COMPLEXE — ET C'EST LE LOCAL D'ABORD QUI TRANCHE
# ══════════════════════════════════════════════════════════════════════════
def test_une_question_courante_reste_sur_le_modele_local():
    """⚠️ SANS `local_suffit`, LE DISTANT RAFLAIT LA CONVERSATION.

    La regle du routeur est « le plus capable », et le poids en est
    l'approximation : un modele distant pese cent. « Quelle heure est-il »
    serait parti sur Internet — latence, cout par question, et sortie de
    donnees — pour une reponse que le local donnait deja.
    """
    ordre = _routeur(LOCAL, DISTANT).classer("conversation")

    assert [m.nom for m in ordre] == ["llama-local", "claude-distant"]


def test_une_tache_de_raisonnement_va_au_plus_capable():
    """Le local reste dans la liste, DERRIERE : il sert de recours."""
    ordre = _routeur(LOCAL, DISTANT).classer("raisonnement")

    assert [m.nom for m in ordre] == ["claude-distant", "llama-local"]


def test_le_vocal_ne_sort_jamais_de_la_machine():
    """⚠️ ET LA PANNE NE CHANGE RIEN A CELA.

    Un usage local n'admet pas le distant en recours : ce serait echanger une
    panne visible contre une sortie de donnees que personne n'a autorisee.
    """
    ordre = _routeur(LOCAL, DISTANT).classer("vocal")

    assert [m.nom for m in ordre] == ["llama-local"]


# ══════════════════════════════════════════════════════════════════════════
#  5. LA SELECTION PAR CAPACITE
# ══════════════════════════════════════════════════════════════════════════
def test_un_agent_demande_une_capacite_pas_un_fournisseur():
    """« J'ai besoin de cent mille jetons de contexte » — le routeur trouve.

    L'agent ne nomme ni Ollama, ni Claude, ni un modele. C'est toute la
    raison d'etre de cette couche.
    """
    ordre = _routeur(LOCAL, DISTANT).classer("long_contexte")

    assert [m.nom for m in ordre] == ["claude-distant"]


def test_une_capacite_que_personne_ne_porte_est_refusee_en_nommant_le_manque():
    with pytest.raises(AucunModele) as erreur:
        _routeur(LOCAL, DISTANT).classer("vision")

    assert "vision" in str(erreur.value)


# ══════════════════════════════════════════════════════════════════════════
#  6 & 7. LE RECOURS, ET SA LIMITE
# ══════════════════════════════════════════════════════════════════════════
def test_un_delai_depasse_declenche_le_recours():
    import httpx

    lent = FauxFournisseur("local", (LOCAL,), echoue=httpx.ReadTimeout("trop lent"))
    distant = FauxFournisseur("distant", (DISTANT,), morceaux=("voila",))

    sortie = "".join(
        routage.flux(
            "conversation", [], routeur=_routeur(LOCAL, DISTANT), sources=(lent, distant)
        )
    )

    assert sortie == "voila"


def test_le_recours_s_arrete_au_premier_jeton_sorti():
    """⚠️ LE BANC LE PLUS IMPORTANT DE CE FICHIER.

    Un fragment parti vers l'interface a peut-etre deja ete PRONONCE.
    Recommencer ailleurs collerait la fin d'une reponse a la moitie d'une
    autre : l'utilisateur entendrait une phrase qu'aucun modele n'a ecrite.

    « Ne jamais pretendre qu'un modele a repondu si la requete n'a pas ete
    executee » vaut dans les deux sens.
    """
    coupe = FauxFournisseur(
        "local",
        (LOCAL,),
        morceaux=("Il fait ", "beau ", "aujourd'hui"),
        echoue=RuntimeError("connexion perdue"),
        echoue_apres=2,
    )
    distant = FauxFournisseur("distant", (DISTANT,), morceaux=("TOUT AUTRE CHOSE",))

    recus: list[str] = []
    with pytest.raises(RuntimeError, match="connexion perdue"):
        for morceau in routage.flux(
            "conversation", [], routeur=_routeur(LOCAL, DISTANT), sources=(coupe, distant)
        ):
            recus.append(morceau)

    assert recus == ["Il fait ", "beau "], "ce qui etait sorti reste sorti"
    assert distant.appels == [], "le second n'a PAS ete appele : il aurait colle sa reponse"


def test_sans_flux_le_recours_est_total():
    """Rien n'est parti tant que la reponse n'est pas entiere : on peut tout refaire."""
    casse = FauxFournisseur("local", (LOCAL,), echoue=RuntimeError("panne"))
    distant = FauxFournisseur("distant", (DISTANT,), morceaux=("reponse complete",))

    texte = routage.generer(
        "conversation", [], routeur=_routeur(LOCAL, DISTANT), sources=(casse, distant)
    )

    assert texte == "reponse complete"


def test_quand_tous_echouent_le_message_dit_ce_qui_a_ete_tente():
    """⚠️ « CA N'A PAS MARCHE » ENVOIE CHERCHER AU HASARD.

    Ollama eteint et clef refusee se corrigent differemment. Le message porte
    donc chaque tentative et sa raison.
    """
    from nova.llm.client import LLMError

    local = FauxFournisseur("local", (LOCAL,), echoue=LLMError("Ollama est eteint"))
    distant = FauxFournisseur("distant", (DISTANT,), echoue=LLMError("clef refusee (401)"))

    with pytest.raises(AucunModeleN_aRepondu) as erreur:
        list(
            routage.flux(
                "conversation", [], routeur=_routeur(LOCAL, DISTANT), sources=(local, distant)
            )
        )

    assert "Ollama est eteint" in str(erreur.value)
    assert "clef refusee" in str(erreur.value)


def test_un_modele_muet_n_est_pas_une_reponse():
    """Aucune exception et aucun mot : le suivant a sa chance plutot que le vide."""
    muet = FauxFournisseur("local", (LOCAL,), morceaux=())
    distant = FauxFournisseur("distant", (DISTANT,), morceaux=("me voila",))

    sortie = "".join(
        routage.flux(
            "conversation", [], routeur=_routeur(LOCAL, DISTANT), sources=(muet, distant)
        )
    )

    assert sortie == "me voila"


# ══════════════════════════════════════════════════════════════════════════
#  8. LE FLUX RESTE UN FLUX
# ══════════════════════════════════════════════════════════════════════════
def test_les_jetons_arrivent_un_par_un_sans_etre_accumules():
    """⚠️ ATTENDRE LA REPONSE COMPLETE ANNULERAIT L'OPTIMISATION EXISTANTE.

    Sur un modele local, la premiere phrase arrive en une seconde alors que la
    reponse complete peut en prendre trente. C'est la difference entre « ca
    repond » et « c'est fige ». Un routeur qui bufferise pour pouvoir se
    rabattre la detruirait — et c'est precisement la tentation que le banc du
    premier jeton interdit.
    """
    local = FauxFournisseur("local", (LOCAL,), morceaux=("un", "deux", "trois"))

    vus = list(routage.flux("conversation", [], routeur=_routeur(LOCAL), sources=(local,)))

    assert vus == ["un", "deux", "trois"], "trois morceaux distincts, pas une chaine"


# ══════════════════════════════════════════════════════════════════════════
#  9 & 11. PLUSIEURS FOURNISSEURS, ET LE COUT DU CHOIX
# ══════════════════════════════════════════════════════════════════════════
def test_le_routage_ne_coute_aucun_appel_reseau():
    """⚠️ UNE QUESTION SIMPLE DOIT RESTER AUSSI RAPIDE QU'AVANT CE MODULE.

    C'est l'exigence qui interdit `disponible()` d'interroger le reseau :
    verifier qu'Ollama repond avant CHAQUE question ajouterait un aller-retour
    a chacune. On decouvre la panne en echouant, une fois.

    Ce banc mesure le choix seul, sans appel de modele.
    """
    import time

    routeur = _routeur(LOCAL, DISTANT)
    depart = time.perf_counter()
    for _ in range(1000):
        routeur.classer("conversation")
    millisecondes = (time.perf_counter() - depart) * 1000

    assert millisecondes < 200, f"1000 routages ont coute {millisecondes:.0f} ms"


def test_un_fournisseur_indisponible_n_entre_pas_au_catalogue():
    """⚠️ « DEUX MODELES DISPONIBLES » DOIT VOULOIR DIRE DEUX.

    Un fournisseur sans clef declare dans le catalogue ferait choisir au
    routeur un candidat condamne : le recours le rattraperait, apres un
    aller-retour perdu et un message accusant le reseau plutot que la
    configuration.
    """
    from nova.modeles.catalogue import routeur as construire

    sans_clef = FauxFournisseur("distant", (DISTANT,), libre=False)
    local = FauxFournisseur("local", (LOCAL,))

    catalogue = construire((local, sans_clef))

    assert [m.nom for m in catalogue.modeles] == ["llama-local"]


# ══════════════════════════════════════════════════════════════════════════
#  10. LE CABLAGE REEL — SANS LUI, TOUT CE QUI PRECEDE EST DECORATIF
#
#  ⚠️ C'EST EXACTEMENT LE DEFAUT QUE CETTE COUCHE CORRIGE.
#
#  Le routeur choisissait deja, avec des mesures, et personne ne lisait sa
#  reponse : `LLMClient()` relisait `settings.chat_model`. Un routeur teste
#  dont le resultat est jete passe pour fait a la revue.
#
#  Ces bancs vont donc jusqu'aux points d'entree reels.
# ══════════════════════════════════════════════════════════════════════════
def test_la_reponse_en_flux_passe_par_le_routeur(monkeypatch):
    """Le chemin de la conversation — celui qui sert a chaque question."""
    from nova import orchestrator

    vus: dict = {}

    def _flux(usage, messages, **kw):
        vus["usage"] = usage
        yield "ok"

    monkeypatch.setattr(orchestrator.routage, "flux", _flux)
    monkeypatch.setattr(orchestrator, "build_system_prompt", lambda *a, **k: ("SYS", []))
    monkeypatch.setattr(orchestrator.conversations, "get_or_create", lambda *a, **k: 1)
    monkeypatch.setattr(orchestrator.conversations, "log_message", lambda *a, **k: None)
    monkeypatch.setattr(orchestrator.conversations, "derniers_echanges", lambda *a, **k: [])

    list(orchestrator.answer_stream([{"role": "user", "content": "bonjour"}]))

    assert vus["usage"] == "vocal", "la reponse peut etre prononcee : usage le plus contraint"


def test_le_gestionnaire_d_agents_demande_un_usage_pas_un_moteur(monkeypatch):
    """⚠️ LE MAILLON `AGENT MANAGER → MODEL ROUTER`.

    C'est le seul endroit de la chaine planificateur → executeur →
    gestionnaire qui ait besoin d'un modele. Il appelait `LLMClient()`
    directement — donc Ollama, donc un seul cerveau possible.
    """
    from nova.api import noyau

    vus: dict = {}

    def _generer(usage, messages, **kw):
        vus["usage"] = usage
        return "/h/Documents/releve.pdf"

    # `noyau` importe le routage a l'interieur de la fonction : on remplace
    # donc sur le module lui-meme, ce qui vaut pour tous ses appelants.
    monkeypatch.setattr(routage, "generer", _generer)

    resultat = noyau._proposer_des_arguments("Quel chemin ?")  # noqa: SLF001

    assert resultat == "/h/Documents/releve.pdf"
    assert vus["usage"] == "extraction", "deduire un chemin ne sort pas de la machine"


def test_avec_le_seul_ollama_le_client_recoit_exactement_ce_qu_il_recevait(monkeypatch):
    """⚠️ LES PERFORMANCES ACTUELLES NE DOIVENT PAS BOUGER D'UN ARGUMENT.

    Avec le seul fournisseur local — le defaut, et la configuration de la
    machine de reference — le routage doit aboutir au MEME appel qu'avant :
    meme methode, memes arguments. Sinon le filtre <think>, la coupure du
    JSON, `keep_alive` et les delais separes seraient contournes sans que
    personne ne le voie.

    Le cout ajoute est un tri de liste sur des reglages deja en cache.
    """
    from nova.llm import client as client_module
    from nova.modeles.local import Ollama

    recus: dict = {}

    class ClientDeBanc:
        def __init__(self, base_url=None, model=None):
            recus["model"] = model

        def stream(self, messages, *, temperature=None, max_tokens=None, json_mode=False):
            recus["messages"] = messages
            recus["temperature"] = temperature
            recus["max_tokens"] = max_tokens
            recus["json_mode"] = json_mode
            yield "ok"

    monkeypatch.setattr(client_module, "LLMClient", ClientDeBanc)

    local = Ollama()
    modele = local.modeles()[0]
    messages = [{"role": "user", "content": "bonjour"}]

    sortie = "".join(
        routage.flux(
            "vocal",
            messages,
            max_tokens=250,
            sources=(local,),
        )
    )

    assert sortie == "ok"
    assert recus["model"] == modele.nom, "le modele CHOISI, pas un nom relu ailleurs"
    assert recus["messages"] == messages
    assert recus["max_tokens"] == 250
    assert recus["json_mode"] is False
