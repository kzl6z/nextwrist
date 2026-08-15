"""Le catalogue des applications : confronter une cible entendue au reel.

CE QUI CHANGE PAR RAPPORT A L'ETAPE PRECEDENTE

Nova savait agir, mais sur un nom que personne ne verifiait. « ouvre
Ecoledirecte » partait vers `open -a` et revenait en echec, sans que Nova
puisse dire mieux que « ca n'a pas marche ».

LES DEUX ERREURS SYMETRIQUES A EVITER

    trop confiante   ouvrir « Adobe » parce qu'on a entendu « Adam »
    trop prudente    refuser tout des que le catalogue est illisible

La deuxieme est la plus insidieuse : elle transforme une capacite imparfaite
en panne franche, et sur une machine qui n'est pas un Mac, elle casserait
tout ce qui marchait avant.
"""

import pytest

from nova import orchestrator
from nova.core import actions, contrats
from nova.core.registre import Registre
from nova.outils import applications
from nova.voice import comprehension as vc
from nova.voice import intentions as vi


@pytest.fixture(autouse=True)
def cache_propre():
    """Le catalogue est mis en cache : sans ca, un test verrait celui du precedent."""
    applications.oublier()
    yield
    applications.oublier()


@pytest.fixture
def disque(tmp_path, monkeypatch):
    """Un faux /Applications, dont les tests decident du contenu."""
    racine = tmp_path / "Applications"
    racine.mkdir()
    monkeypatch.setattr(applications, "DOSSIERS", (racine,))

    def installer(*noms: str) -> None:
        for nom in noms:
            (racine / f"{nom}.app").mkdir(parents=True, exist_ok=True)
        applications.oublier()

    installer.racine = racine
    return installer


# ── Lire le disque ────────────────────────────────────────────────────────


def test_le_catalogue_liste_ce_qui_est_installe(disque):
    disque("Discord", "Numbers", "EcoleDirecte")
    assert applications.installees() == ("Discord", "EcoleDirecte", "Numbers")


def test_le_suffixe_app_n_est_pas_un_nom(disque):
    """`open -a` attend « Discord », pas « Discord.app »."""
    disque("Discord")
    assert applications.installees() == ("Discord",)


def test_un_sous_dossier_est_explore(disque):
    """« /Applications/Utilities/Terminal.app » compte autant que le reste."""
    (disque.racine / "Utilities" / "Terminal.app").mkdir(parents=True)
    applications.oublier()
    assert "Terminal" in applications.installees()


def test_on_ne_descend_jamais_dans_un_bundle(disque):
    """LE PIEGE QUE CE TEST GARDE FERME.

    Xcode.app contient une douzaine d'applications internes. Les remonter
    gonflerait le catalogue de noms que personne ne prononce, et qui feraient
    ensuite concurrence aux vrais lors de la comparaison phonetique.
    """
    interne = disque.racine / "Xcode.app" / "Contents" / "Applications"
    (interne / "Instruments.app").mkdir(parents=True)
    applications.oublier()
    catalogue = applications.installees()
    assert "Xcode" in catalogue
    assert "Instruments" not in catalogue


def test_un_dossier_absent_ne_fait_pas_tomber(monkeypatch, tmp_path):
    """Toutes les machines n'ont pas ~/Applications."""
    monkeypatch.setattr(applications, "DOSSIERS", (tmp_path / "nulle-part",))
    assert applications.installees() == ()


def test_une_application_installee_est_vue_sans_attendre(disque):
    """Le cache est invalide par la date du dossier, pas par un delai.

    Un delai d'expiration ferait dire « je ne trouve pas » pendant une minute
    apres une installation — exactement le moment ou on essaie le nom.
    """
    disque("Discord")
    assert applications.installees() == ("Discord",)
    (disque.racine / "Spotify.app").mkdir()
    assert "Spotify" in applications.installees()


# ── Retrouver le bon nom ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "entendu",
    ["EcoleDirecte", "ecoledirecte", "Écoledirecte", "ECOLEDIRECTE", "école directe"],
)
def test_la_casse_les_accents_et_les_espaces_ne_comptent_pas(disque, entendu):
    """Ce qui distingue ces cinq graphies ne s'entend pas."""
    disque("EcoleDirecte")
    assert applications.resoudre(entendu) == "EcoleDirecte"


def test_le_nom_rendu_est_celui_du_disque(disque):
    """C'est celui-la que `open -a` attend, pas celui qui a ete prononce."""
    disque("Visual Studio Code")
    assert applications.resoudre("visual studio code") == "Visual Studio Code"


def test_une_application_absente_ne_se_devine_pas(disque):
    disque("Discord")
    assert applications.resoudre("Photoshop") is None


def test_un_nom_vide_ne_correspond_a_rien(disque):
    disque("Discord")
    assert applications.resoudre("") is None
    assert applications.resoudre("   ") is None


# ── Le raccord : de la parole a la bonne application ──────────────────────


def comprise(texte: str, *, sure: bool = True):
    return vc.Comprehension(
        texte=texte, origine=texte,
        confiance=0.95 if sure else 0.40,
        intention=vi.reconnaitre(texte),
    )


@pytest.fixture
def outils(monkeypatch):
    """Un registre isole : on note ce qui est ouvert, sans rien ouvrir."""
    from nova import outils as module

    registre = Registre("outil")
    faits: list[str] = []

    class Ouvrir:
        nom, description, capacite = "ouvrir_application", "Ouvre", "action"
        niveau = contrats.REVERSIBLE

        def executer(self, cible):
            faits.append(cible)
            return f"{cible} est ouverte."

    registre.enregistrer(Ouvrir)
    monkeypatch.setattr(module, "registre_outils", registre)
    return faits


@pytest.fixture
def installe(monkeypatch):
    """Fixe le catalogue vu par l'orchestrateur, sans toucher au disque."""

    def poser(*noms: str) -> None:
        monkeypatch.setattr(applications, "installees", lambda **_: tuple(noms))

    return poser


def test_le_nom_exact_du_disque_est_utilise(outils, installe):
    """« ouvre écoledirecte » doit lancer « EcoleDirecte ».

    C'est le cas qui a motive tout ce fichier : Whisper ne restitue ni la
    casse interne ni l'absence d'accent d'un nom de marque.
    """
    installe("EcoleDirecte", "Discord")
    resultat = orchestrator.executer_intention(comprise("ouvre écoledirecte"))
    assert resultat.agie
    assert outils == ["EcoleDirecte"]


@pytest.mark.parametrize(("entendu", "attendu"), [("Diskord", "Discord"), ("Saffari", "Safari")])
def test_un_son_identique_et_sans_rival_suffit(outils, installe, entendu, attendu):
    """Le seul cas ou l'oreille agit seule : meme son exactement, un seul
    candidat. Whisper ecrit « Diskord » ou « Saffari » ; ca se prononce
    a l'identique, et demander n'apprendrait rien a personne."""
    installe("Discord", "Safari", "Numbers")
    resultat = orchestrator.executer_intention(comprise(f"ouvre {entendu}"))
    assert resultat.agie
    assert outils == [attendu]


def test_une_application_absente_le_dit_au_lieu_d_essayer(outils, installe):
    """Un message qui nomme ce qu'on n'a pas trouve, pas une erreur de `open`."""
    installe("Discord", "Safari")
    resultat = orchestrator.executer_intention(comprise("ouvre Photoshop"))
    assert resultat.etat == "echouee"
    assert "Photoshop" in resultat.message
    assert outils == [], "une application inconnue a quand meme ete lancee"


def test_un_catalogue_illisible_ne_bloque_rien(outils, installe):
    """LA REGRESSION QUE CE TEST INTERDIT.

    Sur une machine qui n'est pas un Mac, `installees()` rend un tuple vide.
    En conclure « aucune application n'existe » remplacerait une capacite
    imparfaite par une panne franche. On repasse la cible telle quelle : le
    comportement redevient celui d'avant le catalogue.
    """
    installe()
    resultat = orchestrator.executer_intention(comprise("ouvre Discord"))
    assert resultat.agie
    assert outils == ["Discord"]


# ── Le doute : proposer, jamais deviner ───────────────────────────────────


def test_un_doute_pose_une_question_au_lieu_d_agir(outils, installe):
    """« NOVA ne doit jamais transformer silencieusement une phrase ambigue
    en action potentiellement dangereuse. »

    « Discorde » ressemble a 0,857 a « Discord ». C'est beaucoup, et ce n'est
    pas une certitude : « Photoshop » ressemble a 0,833 a « Photo Booth »
    alors qu'il ne faut surtout pas l'ouvrir. On demande.
    """
    installe("Discord", "Safari", "Numbers")
    resultat = orchestrator.executer_intention(comprise("ouvre Discorde"))
    assert resultat.etat == "a_confirmer"
    assert "Discord" in resultat.message and resultat.message.endswith("?")
    assert outils == []


def test_le_oui_de_l_utilisateur_tranche(outils, installe):
    installe("Discord", "Safari", "Numbers")
    resultat = orchestrator.executer_intention(comprise("ouvre Discorde"), confirme=True)
    assert resultat.agie
    assert outils == ["Discord"]


def test_le_cas_qui_a_decide_de_la_regle(outils, installe):
    """« Photoshop » absent, « Photo Booth » present : 0,833 de ressemblance.

    C'est LE contre-exemple qui interdit d'agir sur la seule ressemblance.
    Nova propose, elle n'ouvre pas.
    """
    installe("Photo Booth", "Photos", "Safari")
    resultat = orchestrator.executer_intention(comprise("ouvre Photoshop"))
    assert resultat.etat == "a_confirmer"
    assert outils == [], "Photo Booth s'est ouvert alors qu'on demandait Photoshop"


def test_jamais_deux_questions_dans_un_seul_oui(monkeypatch, installe):
    """⚠️ L'INVARIANT LE PLUS SUBTIL DE CETTE ETAPE.

    La confirmation remonte par UN booleen. Si un outil dangereux avait aussi
    une cible incertaine, le « oui » de l'utilisateur repondrait aux deux
    questions a la fois : il croirait valider un nom, et validerait une action
    irreversible.

    Aujourd'hui aucun outil n'est dans ce cas. Ce test existe pour que le jour
    ou l'un le sera, il trouve une garde et non un piege.
    """
    from nova import outils as module

    registre = Registre("outil")
    faits: list[str] = []

    class Supprimer:
        nom, description, capacite = "supprimer_application", "Supprime", "action"
        niveau = contrats.IRREVERSIBLE

        def executer(self, cible):
            faits.append(cible)
            return "supprimee"

    registre.enregistrer(Supprimer)
    monkeypatch.setattr(module, "registre_outils", registre)
    monkeypatch.setitem(
        actions.ACTIONS, "ouvrir_application",
        actions.Action("supprimer_application", "cible", catalogue=actions.CATALOGUE_APPLICATIONS),
    )
    installe("Discord", "Safari", "Numbers")

    resultat = orchestrator.executer_intention(comprise("ouvre Discorde"))
    assert resultat.etat == "echouee", "une action irreversible a demande sur une cible devinee"
    assert faits == []


# ── Le sous-nom : la forme longue est sur le disque, la courte est dite ───


def test_les_jetons_ecartent_le_millesime_et_les_mots_courts():
    """« 2025 » est un millesime, « App » se retrouve partout."""
    assert applications.jetons("Adobe Photoshop 2025") == ("Adobe", "Photoshop")
    assert applications.jetons("App Store") == ("Store",)
    assert applications.jetons("Visual Studio Code") == ("Visual", "Studio", "Code")


@pytest.mark.parametrize(
    ("dit", "attendu"),
    [
        ("Chrome", "Google Chrome"),
        ("Photoshop", "Adobe Photoshop 2025"),
        ("Word", "Microsoft Word"),
        ("Code", "Visual Studio Code"),
    ],
)
def test_un_mot_du_nom_suffit_quand_il_ne_designe_qu_une_application(
    outils, installe, dit, attendu
):
    """Personne ne dit « ouvre Adobe Photoshop 2025 »."""
    installe("Google Chrome", "Adobe Photoshop 2025", "Microsoft Word",
             "Visual Studio Code", "Safari")
    assert orchestrator.executer_intention(comprise(f"ouvre {dit}")).agie
    assert outils == [attendu]


def test_un_mot_partage_par_deux_applications_se_demande(outils, installe):
    """« Adobe » designe Photoshop ET Illustrator.

    Rendre le premier trouve reviendrait a tirer au sort. Nova nomme les deux
    et laisse choisir.
    """
    installe("Adobe Photoshop 2025", "Adobe Illustrator 2025", "Safari")
    resultat = orchestrator.executer_intention(comprise("ouvre Adobe"))
    assert resultat.etat == "echouee"
    assert "Photoshop" in resultat.message and "Illustrator" in resultat.message
    assert outils == [], "une des deux a ete ouverte au hasard"


def test_l_ambiguite_se_repond_en_nommant_pas_en_disant_oui(outils, installe):
    """POURQUOI CET ETAT N'EST PAS `a_confirmer`.

    La boucle de confirmation ne transporte qu'un booleen. « oui » ne saurait
    pas designer LAQUELLE des deux. La question se repond donc en nommant
    l'application, ce qui repart comme une demande neuve — sans etat a garder
    entre les deux tours.
    """
    installe("Adobe Photoshop 2025", "Adobe Illustrator 2025")
    assert orchestrator.executer_intention(comprise("ouvre Adobe")).etat != "a_confirmer"

    resultat = orchestrator.executer_intention(comprise("ouvre Illustrator"))
    assert resultat.agie
    assert outils == ["Adobe Illustrator 2025"]


def test_un_mot_entendu_de_travers_retrouve_son_application(outils, installe):
    """« Crome » ne ressemble pas a « Google Chrome » (0,43) et sonne
    exactement comme son mot « Chrome » (1,00). Chaque application est jugee
    sur son MEILLEUR angle."""
    installe("Google Chrome", "Safari", "Keynote")
    assert orchestrator.executer_intention(comprise("ouvre Crome")).agie
    assert outils == ["Google Chrome"]


def test_le_sous_nom_n_ouvre_pas_la_porte_a_n_importe_quoi(outils, installe):
    """LA REGRESSION QUE CETTE ETAPE POUVAIT INTRODUIRE.

    Juger chaque application sur son meilleur mot AUGMENTE mecaniquement tous
    les scores. Le risque etait qu'un nom absent finisse par ressembler assez
    a un mot quelconque pour declencher une ouverture.
    """
    installe("Google Chrome", "Adobe Photoshop 2025", "Visual Studio Code",
             "Photo Booth", "App Store", "Calendrier", "Finder")
    for absent in ("Blender", "Figma", "Steam", "Slack", "Zoom"):
        etat = orchestrator.executer_intention(comprise(f"ouvre {absent}")).etat
        assert etat == "echouee", f"« {absent} » a produit « {etat} »"
    assert outils == []


def test_deux_lectures_aussi_vraisemblables_ne_se_tranchent_pas(outils, installe):
    """« Fotochop » sonne EXACTEMENT autant comme « Photo Booth » que comme
    « Adobe Photoshop 2025 » — 0,667 des deux cotes.

    J'ai cherche un departage : longueur du fragment retenu, position du mot.
    Aucun ne separait ces deux-la sans en melanger d'autres. Proposer le
    premier par ordre alphabetique aurait maquille un tirage au sort en
    decision ; Nova nomme les deux.
    """
    installe("Photo Booth", "Adobe Photoshop 2025", "Safari")
    resultat = orchestrator.executer_intention(comprise("ouvre Fotochop"))
    assert resultat.etat == "echouee"
    assert "Photo Booth" in resultat.message
    assert "Adobe Photoshop 2025" in resultat.message
    assert outils == []


def test_un_candidat_nettement_devant_reste_une_proposition(outils, installe):
    """L'egalite ne doit pas devenir la reponse a tout : « Discorde » designe
    « Discord » a 0,857 contre 0,43 au suivant. Ca se propose, ca se
    confirme d'un « oui », et ca n'a pas a devenir une liste."""
    installe("Discord", "App Store", "Safari")
    resultat = orchestrator.executer_intention(comprise("ouvre Discorde"))
    assert resultat.etat == "a_confirmer"
    assert "Discord" in resultat.message


def test_une_liste_trop_longue_reste_une_phrase(outils, installe):
    """Cette phrase sera PRONONCEE. Huit noms ne sont plus une question."""
    installe(*[f"Adobe {n} 2025" for n in
               ("Photoshop", "Illustrator", "InDesign", "Premiere", "Audition")])
    message = orchestrator.executer_intention(comprise("ouvre Adobe")).message
    assert message.count("«") <= 4, message
    assert "2 autres" in message, message


# ── Le catalogue reste une donnee, pas un cas particulier ─────────────────


def test_les_actions_sans_catalogue_passent_leur_cible_telle_quelle():
    """`arret_pc` n'a pas de cible ; rien ne doit tenter de la resoudre."""
    assert actions.ACTIONS["arret_pc"].catalogue is None


def test_ouvrir_declare_son_catalogue():
    assert actions.ACTIONS["ouvrir_application"].catalogue == actions.CATALOGUE_APPLICATIONS
