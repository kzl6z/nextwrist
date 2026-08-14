"""Les niveaux de risque : un modele PROPOSE, il n'AUTORISE jamais.

POURQUOI CE BAREME EXISTE AVANT LE PREMIER OUTIL QUI AGIT

C'est la seule fenetre ou il peut etre ecrit sans douleur. Une fois qu'un
outil sait supprimer un fichier ou envoyer un message, ajouter des niveaux
devient une migration : retrouver tous les appelants, decider pour chacun,
et vivre avec ceux qu'on a oublies.

CE QUE LE BAREME GARANTIT, ET CE QU'IL NE GARANTIT PAS

Il ne rend pas le modele plus fiable — rien ne le fera. Un modele local de
trois milliards de parametres hallucine des noms de fichiers, confond deux
applications, prend une transcription bancale pour un ordre. Le bareme rend
ces erreurs RATTRAPABLES, ce qui est la seule garantie possible.
"""

import pytest

from nova.core import contrats
from nova.core.registre import ErreurRegistre, Registre
from nova.outils import ConfirmationRequise, executer_outil, registre_outils


def outil(nom: str, niveau, *, capacite: str = "action"):
    """Fabrique un outil de test au niveau demande."""

    class Fabrique:
        pass

    Fabrique.nom = nom
    Fabrique.description = f"outil de test {nom}"
    Fabrique.capacite = capacite
    if niveau is not ...:
        Fabrique.niveau = niveau
    Fabrique.executer = lambda self, **kw: {"fait": nom, **kw}
    return Fabrique


# ── Le bareme lui-meme ────────────────────────────────────────────────────


def test_les_quatre_niveaux_sont_ordonnes():
    """L'ordre porte le sens : plus le chiffre est haut, moins ca se defait."""
    assert contrats.LECTURE < contrats.REVERSIBLE < contrats.CONSEQUENT < contrats.IRREVERSIBLE


@pytest.mark.parametrize(
    ("niveau", "attendu"),
    [
        (contrats.LECTURE, False),
        (contrats.REVERSIBLE, False),
        (contrats.CONSEQUENT, True),
        (contrats.IRREVERSIBLE, True),
    ],
)
def test_la_confirmation_commence_au_consequent(niveau, attendu):
    """Pourquoi 2 et pas 3.

    « Envoyer un message a la mauvaise personne » ne se defait pas davantage
    que « supprimer un fichier », et se remarque bien plus. Reserver la
    confirmation a l'irreversible laisserait passer exactement la categorie
    d'erreurs qui coute le plus cher socialement.
    """
    assert contrats.exige_confirmation(niveau) is attendu


def test_un_niveau_inconnu_exige_la_confirmation():
    """Le seul defaut sur possible.

    Si quelqu'un ajoute un niveau 4 sans toucher a cette fonction, on demande
    au lieu d'agir. L'inverse — agir sur un niveau qu'on ne comprend pas —
    est precisement ce qu'on cherche a rendre impossible.
    """
    assert contrats.exige_confirmation(4) is True
    assert contrats.exige_confirmation(-1) is True


def test_chaque_niveau_a_un_nom_lisible():
    for niveau in contrats.NIVEAUX:
        assert contrats.nom_du_niveau(niveau).isalpha()
    assert "inconnu" in contrats.nom_du_niveau(99)


# ── Le registre refuse ce qui ne se declare pas ───────────────────────────


def test_un_outil_sans_niveau_est_refuse():
    """PAS de valeur par defaut, et surtout pas LECTURE.

    Un defaut a zero ferait passer pour inoffensif tout outil dont l'auteur a
    oublie d'y penser — c'est-a-dire exactement ceux dont il faut se mefier.
    """
    with pytest.raises(ErreurRegistre, match="niveau"):
        Registre("outil").enregistrer(outil("sans_niveau", ...))


def test_le_message_dit_quoi_ecrire():
    """Une erreur au demarrage doit se corriger sans aller lire le code."""
    with pytest.raises(ErreurRegistre) as erreur:
        Registre("outil").enregistrer(outil("muet", ...))
    message = str(erreur.value)
    for attendu in ("LECTURE", "REVERSIBLE", "CONSEQUENT", "IRREVERSIBLE"):
        assert attendu in message


def test_un_niveau_hors_bareme_est_refuse():
    with pytest.raises(ErreurRegistre, match="inconnu"):
        Registre("outil").enregistrer(outil("exotique", 7))


def test_un_booleen_n_est_pas_un_niveau():
    """`True` vaut 1 en Python : sans garde, il passerait pour REVERSIBLE."""
    with pytest.raises(ErreurRegistre, match="niveau"):
        Registre("outil").enregistrer(outil("piege", True))


def test_une_brique_qui_n_execute_rien_n_a_pas_besoin_de_niveau():
    """Un espace de travail ou un modele ne fait rien : lui en demander un
    n'aurait pas de sens, et forcerait a inventer une valeur sans objet."""

    class Espace:
        nom = "etude"
        description = "Reviser, apprendre"
        capacite = "raisonnement"

    Registre("espace").enregistrer(Espace)   # ne doit pas lever


# ── Le portillon ──────────────────────────────────────────────────────────


@pytest.fixture
def bac(monkeypatch):
    """Un registre d'outils isole, substitue au vrai."""
    from nova import outils

    registre = Registre("outil")
    monkeypatch.setattr(outils, "registre_outils", registre)
    return registre


def test_une_lecture_s_execute_sans_rien_demander(bac):
    bac.enregistrer(outil("lire", contrats.LECTURE, capacite="recherche"))
    assert executer_outil("lire")["fait"] == "lire"


def test_une_action_reversible_s_execute_aussi(bac):
    """Ouvrir une application ne demande pas de ceremonie : si Nova se
    trompe, on ferme la fenetre."""
    bac.enregistrer(outil("ouvrir", contrats.REVERSIBLE))
    assert executer_outil("ouvrir", cible="Discord")["cible"] == "Discord"


def test_une_action_consequente_est_suspendue(bac):
    bac.enregistrer(outil("envoyer", contrats.CONSEQUENT))
    with pytest.raises(ConfirmationRequise):
        executer_outil("envoyer", destinataire="Adam")


def test_une_action_irreversible_est_suspendue(bac):
    bac.enregistrer(outil("supprimer", contrats.IRREVERSIBLE))
    with pytest.raises(ConfirmationRequise):
        executer_outil("supprimer", fichier="notes.md")


def test_la_confirmation_explicite_laisse_passer(bac):
    """`confirme` vient de l'utilisateur, JAMAIS du modele — sinon le
    controle revient a demander au renard s'il peut entrer au poulailler."""
    bac.enregistrer(outil("supprimer", contrats.IRREVERSIBLE))
    assert executer_outil("supprimer", confirme=True, fichier="a.md")["fait"] == "supprimer"


def test_la_question_dit_ce_qui_va_se_passer(bac):
    """« Je confirme ? » sans preciser quoi ne vaut pas mieux qu'aucune
    question : on approuve sans savoir."""
    bac.enregistrer(outil("supprimer", contrats.IRREVERSIBLE))
    with pytest.raises(ConfirmationRequise) as erreur:
        executer_outil("supprimer", fichier="notes.md")
    question = erreur.value.question()
    assert "supprimer" in question and "notes.md" in question


def test_un_outil_ayant_contourne_le_registre_est_refuse(bac):
    """Ceinture ET bretelles.

    Le registre refuse deja les outils sans niveau. Si l'un se trouve
    malgre tout dans le registre — insertion directe, test mal ecrit,
    rechargement a chaud — le portillon ne suppose pas qu'il est inoffensif.
    """
    fabrique = outil("clandestin", ...)
    bac._entrees["clandestin"] = fabrique()      # contournement deliberé
    with pytest.raises(ConfirmationRequise):
        executer_outil("clandestin")


def test_un_outil_inconnu_ne_s_execute_pas(bac):
    with pytest.raises(ErreurRegistre, match="introuvable"):
        executer_outil("inexistant")


# ── Les outils reellement livres ──────────────────────────────────────────


def test_tous_les_outils_livres_declarent_leur_niveau():
    for brique in registre_outils.tout():
        niveau = getattr(brique, "niveau", None)
        assert niveau in contrats.NIVEAUX, f"« {brique.nom} » n'a pas de niveau valide"


def test_tout_outil_dangereux_a_reellement_un_garde_fou():
    """L'invariant a CHANGE DE NATURE, et il faut le dire.

    Sa premiere version affirmait « aucun outil livre n'exige de
    confirmation » — vrai tant que Nova ne faisait que lire, et concu pour
    echouer le jour ou une action dangereuse arriverait. Ce jour est venu
    avec `eteindre_ordinateur`, le test a sonne, et il a fait son travail.

    Constater l'absence de danger ne veut plus rien dire maintenant que le
    danger est la. Ce qui compte desormais est que chaque outil dangereux
    soit REELLEMENT bloque — pas qu'il ait une etiquette.

    On l'appelle donc pour de vrai, sans confirmation, et on exige qu'il
    refuse. Une etiquette « irreversible » sur un outil qui s'execute quand
    meme serait pire que pas d'etiquette du tout : elle rassure a tort.
    """
    from nova.outils.systeme import enregistrer_actions_systeme

    enregistrer_actions_systeme(registre_outils)
    dangereux = [
        b for b in registre_outils.tout()
        if contrats.exige_confirmation(getattr(b, "niveau", 99))
    ]
    assert dangereux, "aucun outil dangereux : ce test ne verifie plus rien"

    for outil_dangereux in dangereux:
        with pytest.raises(ConfirmationRequise) as attente:
            executer_outil(outil_dangereux.nom)
        question = attente.value.question()
        assert outil_dangereux.nom in question and question.endswith("?"), (
            f"« {outil_dangereux.nom} » bloque, mais sans question posable."
        )
