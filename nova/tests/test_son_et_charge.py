"""Le volume, et ce qui empeche Nova de confisquer la machine.

DEUX SUJETS DANS UN FICHIER, ET CE N'EST PAS UN HASARD

Le volume est la premiere action qui ne demande aucune reflexion sur le
bareme : le son se remonte. La charge est l'inverse — c'est le sujet ou une
valeur par defaut jamais choisie prenait toute la machine.

Les deux se rejoignent sur un point : ce sont les deux endroits ou Nova
touche a ce que la personne est en train de faire pendant qu'elle le fait.
"""

import subprocess
import sys

import pytest

from nova import orchestrator
from nova.core import contrats, plateforme
from nova.core.registre import Registre
from nova.outils import systeme
from nova.voice import comprehension as vc
from nova.voice import intentions as vi


def comprise(texte: str, *, sure: bool = True):
    return vc.Comprehension(
        texte=texte, origine=texte,
        confiance=0.95 if sure else 0.40,
        intention=vi.reconnaitre(texte),
    )


@pytest.fixture
def osascript(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")

    class Carnet(list):
        sortie, code, erreur = "60", 0, ""

        def repondre(self, **quoi):
            self.__dict__.update(quoi)

    carnet = Carnet()
    monkeypatch.setattr(
        systeme.subprocess, "run",
        lambda c, **kw: carnet.append(c)
        or subprocess.CompletedProcess(c, carnet.code, carnet.sortie, carnet.erreur),
    )
    return carnet


# ── Deux silences qui n'ont rien a voir ───────────────────────────────────


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("coupe le son", "silence"),
        ("mets en sourdine", "silence"),
        ("coupe le volume", "silence"),
        ("tais toi", "stop_parole"),
        ("arrête de parler", "stop_parole"),
        ("chut", "stop_parole"),
    ],
)
def test_couper_le_son_et_se_taire_sont_deux_demandes(phrase, attendu):
    """⚠️ LE MEME DEFAUT QUE « arrête l'ordinateur », AU MEME ENDROIT.

    « coupe le son » parle du HAUT-PARLEUR ; « tais-toi » parle de NOVA. Les
    deux vivaient sous une seule intention, sans consequence tant qu'aucun
    outil n'y repondait. Brancher la sourdine systeme aurait rendu le Mac
    muet chaque fois qu'on demande a Nova de se taire — et il aurait fallu
    aller le rallumer a la souris.
    """
    assert vi.reconnaitre(phrase).nom == attendu


def test_se_taire_ne_declenche_aucune_action(outils_du_son):
    """`stop_parole` est reconnu et n'a pas d'outil : Nova en parle, elle
    n'agit pas. C'est exactement le comportement voulu tant que « arrêter de
    parler » n'est pas implemente cote interface."""
    assert orchestrator.executer_intention(comprise("tais toi")).etat == "ignoree"
    assert outils_du_son == []


# ── Le volume ─────────────────────────────────────────────────────────────


def test_aucun_argument_ne_commence_par_un_tiret(osascript):
    """⚠️ LE BUG QUI A RENDU « baisse le son » INUTILISABLE, ET QUI ETAIT DEJA
    CONNU QUINZE LIGNES PLUS HAUT.

    La premiere version passait le pas signe : `str(-12)`. Releve dans les
    journaux de la vraie machine :

        /usr/bin/osascript: illegal option -- 1

    `osascript` a lu « -12 » comme une option. Baisser le son n'a donc jamais
    fonctionne une seule fois. Le meme piege etait deja identifie et bloque
    pour les noms d'applications, dans le meme fichier — et il ne l'etait pas
    ici. Une garde qui ne protege qu'un appel sur deux ne protege rien.
    """
    for outil in systeme._actions_du_son():
        osascript.clear()
        # Le reglage absolu EXIGE un niveau ; les autres n'en veulent pas.
        outil.executer(niveau="30") if outil.pas == 0 else outil.executer()
        for argument in osascript[0][3:]:
            assert not argument.startswith("-"), f"« {argument} » sera lu comme une option"


def test_monter_le_son_demande_plus(osascript):
    systeme.ReglerLeSon("monter_le_son", "", systeme.PAS_VOLUME).executer()
    assert osascript[0][-2:] == ["plus", str(systeme.PAS_VOLUME)]


def test_baisser_le_son_demande_moins(osascript):
    systeme.ReglerLeSon("baisser_le_son", "", -systeme.PAS_VOLUME).executer()
    assert osascript[0][-2:] == ["moins", str(systeme.PAS_VOLUME)]


def test_le_niveau_atteint_est_annonce(osascript):
    """« Volume à 72 % » vaut mieux que « c'est fait » : ca dit ou on en est
    sans avoir a regarder l'ecran."""
    osascript.repondre(sortie="72")
    assert "72" in systeme.ReglerLeSon("monter_le_son", "", 12).executer()


def test_couper_le_son_ne_passe_pas_de_pas(osascript):
    message = systeme.ReglerLeSon("couper_le_son", "", None).executer()
    assert "coupé" in message
    assert len(osascript[0]) == 3, "la sourdine n'a pas d'argument"


def test_une_sortie_qui_gere_son_volume_le_dit(osascript):
    """Un casque Bluetooth rend `missing value`. Annoncer un reglage qui n'a
    pas eu lieu serait un mensonge de plus dans la meme famille."""
    osascript.repondre(sortie="inconnu")
    with pytest.raises(systeme.ActionImpossible, match="elle-même"):
        systeme.ReglerLeSon("monter_le_son", "", 12).executer()


def test_le_pas_est_borne_dans_le_script():
    """Sans bornes, « monte le son » dix fois ecrirait 220 — refuse par
    macOS, donc une action qui echoue au lieu de saturer."""
    assert "if vise > 100 then set vise to 100" in systeme._SCRIPT_VOLUME
    assert "if vise < 0 then set vise to 0" in systeme._SCRIPT_VOLUME


def test_monter_le_son_demute(osascript):
    """Monter le son sur une machine en sourdine ne doit rien changer
    d'audible si on oublie de lever la sourdine — donc on la leve."""
    assert "set volume without output muted" in systeme._SCRIPT_VOLUME


def test_le_son_est_reversible_et_ne_demande_rien():
    """L'exemple canonique : l'erreur se corrige en la redemandant. Demander
    confirmation pour monter le son serait absurde — on le demande parce
    qu'on n'entend pas, pas pour en discuter."""
    for outil in systeme._actions_du_son():
        assert outil.niveau == contrats.REVERSIBLE
        assert not contrats.exige_confirmation(outil.niveau)


@pytest.fixture
def outils_du_son(monkeypatch):
    from nova import outils as module

    registre = Registre("outil")
    faits: list[str] = []

    class Faux:
        capacite, niveau = "action", contrats.REVERSIBLE

        def __init__(self, nom):
            self.nom, self.description = nom, nom

        def executer(self, **arguments):
            faits.append((self.nom, arguments.get("niveau", "")))
            return "fait"

    for nom in ("monter_le_son", "baisser_le_son", "regler_le_son", "couper_le_son"):
        registre.enregistrer(Faux(nom))
    monkeypatch.setattr(module, "registre_outils", registre)
    return faits


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("monte le son", ("monter_le_son", "")),
        ("plus fort", ("monter_le_son", "")),
        ("baisse le volume", ("baisser_le_son", "")),
        ("moins fort", ("baisser_le_son", "")),
        ("coupe le son", ("couper_le_son", "")),
    ],
)
def test_de_la_phrase_a_l_action(outils_du_son, phrase, attendu):
    assert orchestrator.executer_intention(comprise(phrase)).agie
    assert outils_du_son == [attendu]


def test_une_parole_douteuse_ne_touche_pas_au_volume(outils_du_son):
    assert orchestrator.executer_intention(comprise("monte le son", sure=False)).etat == "ignoree"
    assert outils_du_son == []


# ── Le pourcentage visé ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("baisse le son à 20%", "20"),
        ("baisse le son à 20 %", "20"),
        ("monte le son à 80 pour cent", "80"),
        ("monte le son à 80", "80"),
        ("Nova, baisse le son à 20%.", "20"),
        ("monte le son", ""),
        ("plus fort", ""),
    ],
)
def test_le_pourcentage_se_lit_dans_la_phrase(phrase, attendu):
    """RELEVE EN CONDITIONS REELLES : « Nova, baisse le son à 20%. »

    Nova appliquait son pas de 12 et ignorait le 20. Il fallait redemander
    jusqu'a tomber juste — c'est-a-dire ne jamais tomber juste.
    """
    assert vi.reconnaitre(phrase).cible == attendu


def test_le_pourcentage_se_cherche_dans_le_texte_original():
    """La normalisation supprime le signe « % » : « 20% » y devient « 20 »,
    indiscernable d'un nombre quelconque. Chercher dans le texte reduit
    aurait donc marche par accident, et casse au premier « ouvre 20 »."""
    assert vi.pourcentage("baisse le son à 20%") == "20"
    assert vi.pourcentage("ouvre Photoshop") == ""


def test_le_pourcentage_arrive_jusqu_a_l_outil(outils_du_son):
    orchestrator.executer_intention(comprise("baisse le son à 20%"))
    assert outils_du_son == [("baisser_le_son", "20")]


def test_un_pourcentage_vise_devient_une_valeur_absolue(osascript):
    """« baisse le son à 20 % » ne baisse pas DE 20, il vise 20."""
    systeme.ReglerLeSon("baisser_le_son", "", -12).executer(niveau="20")
    assert osascript[0][-2:] == ["absolu", "20"]


def test_sans_pourcentage_on_applique_le_pas(osascript):
    systeme.ReglerLeSon("baisser_le_son", "", -12).executer()
    assert osascript[0][-2:] == ["moins", "12"]


def test_un_pourcentage_absurde_est_borne_avant_de_partir(osascript):
    """Whisper colle parfois deux chiffres : « 20 » devient « 2020 ». Le
    script bornerait aussi, mais un argument absurde ne doit pas voyager
    jusque-la pour etre rattrape au dernier moment."""
    systeme.ReglerLeSon("monter_le_son", "", 12).executer(niveau="2020")
    assert osascript[0][-2:] == ["absolu", "100"]


# ── Regler, qui n'est ni monter ni baisser ────────────────────────────────


@pytest.mark.parametrize(
    ("phrase", "attendu"),
    [
        ("mets le son à 30%", "30"),
        ("met le son à 30 %", "30"),
        ("règle le son à 45%", "45"),
        ("mets le volume à 60 pour cent", "60"),
        # RELEVE EN CONDITIONS REELLES : dit « mets », transcrit « me ».
        ("me le son à 30 %", "30"),
    ],
)
def test_regler_le_son_a_un_niveau_precis(phrase, attendu):
    """« Nova, mets le son à 30 % » etait IGNOREE.

    La table ne connaissait que deux directions, et cette phrase n'en donne
    aucune : elle donne une DESTINATION. C'est pourtant la formulation la plus
    naturelle quand on sait ou l'on veut aller.
    """
    intention = vi.reconnaitre(phrase)
    assert intention.nom == "volume_absolu"
    assert intention.cible == attendu


def test_regler_sans_destination_demande_au_lieu_de_deviner(osascript):
    """« mets le son » seul ne dit pas a combien.

    Le ranger sous « monte » aurait monte le son — ce qui ne veut pas dire ca.
    Choisir un niveau a sa place serait deviner ; ne rien faire en silence
    serait pire.
    """
    with pytest.raises(systeme.ActionImpossible, match="quel niveau"):
        systeme.ReglerLeSon("regler_le_son", "", 0).executer()
    assert osascript == [], "une commande est partie sans destination"


@pytest.mark.parametrize("phrase", ["mets la table", "mets de la musique", "met moi une photo"])
def test_mettre_autre_chose_ne_touche_pas_au_volume(phrase):
    assert vi.reconnaitre(phrase).nom == "aucune"


def test_regler_le_son_arrive_jusqu_a_l_outil(outils_du_son):
    orchestrator.executer_intention(comprise("mets le son à 30%"))
    assert outils_du_son == [("regler_le_son", "30")]


# ── « monte » entendu « montre » ──────────────────────────────────────────


@pytest.mark.parametrize(
    ("entendu", "attendu", "niveau"),
    [
        # RELEVE EN CONDITIONS REELLES, deux fois de suite.
        ("montre le son à 80%", "volume_haut", "80"),
        ("montre le son du PC à 80%", "volume_haut", "80"),
        ("Nova montre le son du PC à 80%", "volume_haut", "80"),
        ("montre le sont", "volume_haut", ""),
        ("éteint l'ordinateur", "arret_pc", ""),
    ],
)
def test_un_declencheur_mal_transcrit_est_rapproche(entendu, attendu, niveau):
    """« monte » et « montre » ne different que d'une lettre, et « montre »
    est bien plus frequent en francais : Whisper choisit le mot courant.

    Ajouter « montre le son » a la table aurait marche pour cette phrase-la.
    Il aurait fallu y ajouter « mont le son », « montent le son », « monte le
    sont » — une famille ouverte dont chaque membre manquant ressemble a une
    panne. Rapprocher par le SON les traite tous.
    """
    intention = vi.reconnaitre(entendu)
    assert intention.nom == attendu
    assert intention.cible == niveau


@pytest.mark.parametrize(
    "phrase",
    [
        "montre-moi une photo de Mars",
        "montre moi Discord",
        "je te montre le son",
        "donne moi le son juste",
        "raconte moi une histoire",
        "quelle est la masse du Soleil",
        "parle moi de la Lune",
    ],
)
def test_le_rapprochement_ne_devient_pas_un_pari(phrase):
    """LES TESTS QUI COMPTENT LE PLUS ICI.

    Mesure sur les declencheurs reels : « montre le son » ~ « monte le son »
    donne 0,875, tandis que « quelle » ~ « kill » plafonne a 0,667 et
    « donne moi le son » ~ « monte le son » a 0,500. C'est ce TROU, et non le
    seuil lui-meme, qui rend la regle defendable.

    « montre-moi une photo » est la phrase qu'on prononcerait naturellement et
    que la moindre imprudence transformerait en reglage de volume.
    """
    assert vi.reconnaitre(phrase).nom == "aucune"


def test_un_declencheur_exact_n_est_jamais_reinterprete():
    """Le rapprochement est un DERNIER recours. Tant qu'un declencheur est
    ecrit exactement, une phrase juste ne doit pas etre relue."""
    intention = vi.reconnaitre("coupe le son")
    assert intention.nom == "silence"
    assert intention.arguments == {}


def test_un_rapprochement_recoit_la_confiance_minimale_qui_agit():
    """Deliberement au seuil : le jour ou `SEUIL_INTENTION` monte, les
    rapprochements sont les premiers exclus, avant toute reconnaissance
    exacte."""
    from nova.core import actions

    rapproche = vi.reconnaitre("montre le son à 80%")
    exact = vi.reconnaitre("monte le son à 80%")
    assert rapproche.confiance == actions.SEUIL_INTENTION
    assert exact.confiance > rapproche.confiance


def test_seuls_les_declencheurs_sans_cible_sont_rapproches():
    """Pour « ouvre » ou « ferme », la cible est ensuite retrouvee dans le
    texte ORIGINAL. Reparer le declencheur d'un cote et pas de l'autre ferait
    perdre la cible en silence — un echec bien pire que l'absence de
    rapprochement."""
    for nom, declencheurs, exige_cible in vi.DECLENCHEURS:
        if not exige_cible:
            continue
        for declencheur in declencheurs:
            repare, trace = vi._rapprocher_le_declencheur(declencheur + " machin")
            assert trace == "", f"« {nom} » a une cible et a ete rapproche : {trace}"


def test_le_rapprochement_arrive_jusqu_au_volume(outils_du_son):
    """Le chemin complet : Whisper se trompe, et le son monte quand meme."""
    assert orchestrator.executer_intention(comprise("montre le son à 80%")).agie
    assert outils_du_son == [("monter_le_son", "80")]


# ── La forme d'une phrase ne dit pas qu'elle est ratee ────────────────────


@pytest.mark.parametrize(
    "ordre",
    [
        "me le son à 30 %", "mets le son à 30 %", "monte le son à 80 %",
        "baisse le son à 50 %", "ferme le PC", "monte le son", "coupe le son",
        "ouvre Discord", "éteins l'ordinateur", "il est quelle heure",
    ],
)
def test_un_ordre_bref_n_est_pas_un_decoupage_rate(ordre):
    """⚠️ LE CRITERE PUNISSAIT CE POUR QUOI NOVA EXISTE.

    Releve en conditions reelles : « me le son à 30 % » notee 0,45 sur ce seul
    critere, donc rejetee. Trois causes cumulees :

      — « % » comptait comme un mot d'un caractere ;
      — « 30 » comptait comme un mot suspect, alors qu'un nombre est souvent
        le mot le plus utile de la phrase ;
      — un ratio etait applique a trois mots, ou il ne veut rien dire :
        « ferme le PC » y donne 2/3.

    Les ordres sont brefs par nature. Un critere qui penalise la brievete
    penalise la moitie de ce que Nova sait faire.
    """
    from nova.voice import comprehension as vc

    note, raison = vc._confiance_structurelle(ordre)
    assert note == 1.0, f"« {ordre} » penalise : {raison}"


@pytest.mark.parametrize(
    "bruit",
    ["et de la de le a ce", "je ne l ai de a en", "a b c de le la",
     "d un a la de", "le de la a en on"],
)
def test_un_vrai_decoupage_rate_est_toujours_attrape(bruit):
    """Ce que le critere doit attraper reste attrape.

    Whisper qui perd le fil produit une trainee de mots-outils — bavarde par
    nature, ce qui est exactement ce qui la distingue d'un ordre bref.
    """
    from nova.voice import comprehension as vc

    note, raison = vc._confiance_structurelle(bruit)
    assert note < 1.0 and raison


def test_la_chaine_complete_laisse_passer_l_ordre_mal_entendu():
    """LE CAS DE BOUT EN BOUT, avec le logprob reellement releve (-0,56).

    Trois corrections devaient se cumuler pour que cette phrase agisse :
    l'intention `volume_absolu` qui n'existait pas, le rapprochement
    « me » → « mets », et le critere de forme. Aucune des trois ne suffisait
    seule — c'est pour ca qu'elle etait ignoree.
    """
    from nova.voice import comprehension as vc

    comprise_ = vc.comprendre("me le son à 30 %", logprob=-0.56)
    assert comprise_.intention.nom == "volume_absolu"
    assert comprise_.intention.cible == "30"
    assert comprise_.sure, f"confiance {comprise_.confiance} — l'ordre serait ignore"


# ── La machine reste a son proprietaire ───────────────────────────────────


def test_la_transcription_laisse_deux_coeurs(monkeypatch):
    """⚠️ L'ARGUMENT ABSENT ETAIT UN CHOIX QUE PERSONNE N'AVAIT FAIT.

    `WhisperModel` etait construit sans `cpu_threads`. Le defaut de la
    bibliotheque est 0, et 0 y signifie « tous les coeurs ». Pendant chaque
    transcription, la machine entiere se retrouvait sans un seul coeur libre
    — pas seulement Nova : le systeme, et ce que la personne faisait a cote.
    """
    from nova.voice import transcribe

    monkeypatch.setattr(transcribe.os, "cpu_count", lambda: 8)
    assert transcribe._fils_de_calcul() == 6


def test_une_machine_minuscule_garde_au_moins_un_fil(monkeypatch):
    """Sur deux coeurs, « tous sauf deux » vaut zero — et zero signifierait
    « prends tout », c'est-a-dire exactement l'inverse."""
    from nova.voice import transcribe

    monkeypatch.setattr(transcribe.os, "cpu_count", lambda: 2)
    assert transcribe._fils_de_calcul() == 1


def test_un_reglage_explicite_l_emporte(monkeypatch):
    from nova.settings import get_settings
    from nova.voice import transcribe

    reglages = get_settings()
    monkeypatch.setattr(reglages, "whisper_threads", 3)
    monkeypatch.setattr(transcribe, "get_settings", lambda: reglages)
    assert transcribe._fils_de_calcul() == 3


# ── La mesure qui departage deux pannes opposees ──────────────────────────


def test_le_swap_se_lit_quelle_que_soit_la_langue_du_systeme():
    """LE DETAIL QUI NE SE VOIT JAMAIS EN TEST ET TOUJOURS CHEZ L'UTILISATEUR.

    `sysctl` suit la langue du systeme pour le separateur decimal. Sur un Mac
    francais, « used = 1234,50M » — et `float("1234,50")` leve.
    """
    anglais = "total = 2048,00M  used = 1234,50M  free = 813,50M"
    assert plateforme._octets(anglais, "used") == 1.21

    point = "total = 2048.00M  used = 1234.50M  free = 813.50M"
    assert plateforme._octets(point, "used") == 1.21


def test_les_unites_sont_converties():
    assert plateforme._octets("used = 2,00G", "used") == 2.0
    assert plateforme._octets("used = 512,00M", "used") == 0.5
    assert plateforme._octets("used = 0,00M", "used") == 0.0


def test_un_demi_giga_de_swap_n_est_pas_une_pagination():
    """macOS y depose des pages froides en permanence. Alerter la-dessus
    apprendrait a ignorer l'alerte."""
    assert not plateforme.Pression(0.4, 2.0).pagine
    assert plateforme.Pression(1.5, 2.0).pagine


def test_une_transcription_vide_n_accuse_pas_un_reglage_eteint():
    """⚠️ UN DIAGNOSTIC FAUX COUTE PLUS CHER QUE PAS DE DIAGNOSTIC.

    Le message disait « filtre VAD trop strict (NOVA_WHISPER_VAD) » a chaque
    transcription vide. Or ce filtre est DESACTIVE par defaut : la piste
    envoyait chercher la panne dans un reglage qui ne tournait pas — et elle
    l'envoyait avec assurance, ce qui est le pire des deux.
    """
    from nova.voice import transcribe

    eteint = transcribe.piste_du_silence(vad_actif=False)
    assert "NOVA_WHISPER_VAD" not in eteint, "on accuse un reglage qui ne tourne pas"
    assert "micro" in eteint

    allume = transcribe.piste_du_silence(vad_actif=True)
    assert "NOVA_WHISPER_VAD" in allume, "le VAD actif est une piste, et il faut la donner"


def test_une_mesure_impossible_ne_declare_pas_la_paix():
    """`disponible=False` veut dire « je ne sais pas », pas « tout va bien ».

    Repondre `pagine=False` a une mesure ratee ferait chercher la panne du
    mauvais cote — exactement ce que cette mesure existe pour eviter.
    """
    inconnue = plateforme.Pression(0.0, 0.0, disponible=False)
    assert not inconnue.pagine
    assert "inconnue" in str(inconnue)


def test_la_pression_ne_leve_jamais(monkeypatch):
    """Un diagnostic qui fait tomber Nova serait pire que pas de diagnostic."""
    monkeypatch.setattr(plateforme.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        plateforme, "_swap_macos", lambda: (_ for _ in ()).throw(OSError("sysctl absent"))
    )
    assert plateforme.pression_memoire().disponible is False
