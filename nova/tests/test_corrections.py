"""Homophones : les mots qui se prononcent pareil et s'ecrivent autrement.

Whisper entend un son, doit choisir une graphie, et se trompe. Aucun reglage
n'y peut rien — le son est REELLEMENT identique.

La regle generale : APRES UN PRONOM SUJET, IL FAUT LA FORME VERBALE DE CE
PRONOM. Treize groupes de sons engendrent 149 regles.

Les tests NEGATIFS comptent plus que les positifs : un correcteur qui casse
des phrases justes est pire que pas de correcteur du tout.
"""

import pytest

from nova.voice.corrections import GROUPES, corriger


@pytest.mark.parametrize(
    ("entree", "attendu"),
    [
        # Le cas releve en conditions reelles.
        ("que c'est-tu de moi ?", "que sais-tu de moi ?"),
        ("Que ces-tu de moi ?", "Que sais-tu de moi ?"),
        ("que sait-tu de moi", "que sais-tu de moi"),
        # La meme regle, sur d'autres verbes — c'est tout l'interet.
        ("il et parti hier", "il est parti hier"),
        ("on et pret", "on est pret"),
        ("tu à raison", "tu as raison"),
        ("il à faim", "il a faim"),
        ("je peu venir", "je peux venir"),
        ("il peu attendre", "il peut attendre"),
        ("je c'est ce que tu veux", "je sais ce que tu veux"),
        ("tu ces bien que non", "tu sais bien que non"),
        ("il fais le necessaire", "il fait le necessaire"),
        ("je fait mes valises", "je fais mes valises"),
        ("je mes la table", "je mets la table"),
        ("il mes du temps", "il met du temps"),
        ("tu dit quoi", "tu dis quoi"),
        ("je dit rien", "je dis rien"),
        ("il voix la mer", "il voit la mer"),
        ("tu va bien", "tu vas bien"),
        ("ils son la", "ils sont la"),
        ("ils on compris", "ils ont compris"),
        ("elles son parties", "elles sont parties"),
        ("il prend le train", "il prend le train"),
        ("je veut partir", "je veux partir"),
        # Inversion interrogative : le verbe precede le pronom.
        ("peu-tu venir ?", "peux-tu venir ?"),
        ("et-il la ?", "est-il la ?"),
        ("à-t-il compris ?", "a-t-il compris ?"),
    ],
)
def test_corrige_les_formes_impossibles(entree, attendu):
    corrige, changements = corriger(entree)
    assert corrige == attendu
    if entree != attendu:
        assert changements, "une correction doit toujours etre signalee"


@pytest.mark.parametrize(
    "phrase",
    [
        # Formes verbales deja correctes.
        "il est parti", "elle est la", "on est pret", "tu es gentil",
        "il a faim", "tu as raison", "on a compris",
        "je sais deja", "tu sais bien", "il sait tout",
        "je peux venir", "il peut attendre",
        "je fais mes valises", "il fait beau",
        "je mets la table", "il met du temps",
        "tu dis quoi", "il dit oui",
        "il voit la mer", "je vois bien",
        "tu vas bien", "il va mieux", "on va partir",
        "ils sont la", "elles sont parties", "ils ont compris",
        # Homonymes hors contexte verbal : rien a corriger.
        "c'est tout ce que je voulais dire",
        "ces tulipes sont magnifiques",
        "ses tuiles ont ete refaites",
        "un peu de patience",
        "il y a peu de temps",
        "sa voix est belle",
        "mes affaires sont pretes",
        "dix euros",
        "le fait est la",
        # Pronominaux : « s'est » apres il/elle/on est parfaitement correct.
        "il s'est tu pendant la reunion",
        "elle s'est levee tot",
        "on s'est bien amuses",
        "",
    ],
)
def test_ne_touche_pas_aux_phrases_correctes(phrase):
    corrige, changements = corriger(phrase)
    assert corrige == phrase
    assert changements == []


@pytest.mark.parametrize(
    "phrase",
    [
        # ── Le piege du « et » de coordination ──
        # Un pronom SUJET ne se coordonne pas : on dit « lui et son frere »,
        # jamais « il et son frere ». Mais « elle » est aussi une forme
        # accentuee, donc « elle et … » peut etre parfaitement correct.
        "elle et lui sont partis",
        "elle et moi allons au cinema",
        "elle et Marie se connaissent",
        "elle et son frere arrivent",
        "elle et les autres attendent",
        "elle, et puis lui aussi",
    ],
)
def test_le_et_de_coordination_survit(phrase):
    assert corriger(phrase)[0] == phrase


def test_apres_il_le_et_est_toujours_fautif():
    # La contrepartie de la garde ci-dessus : « il » ne se coordonnant jamais,
    # aucune garde n'est necessaire et la correction s'applique.
    assert corriger("il et son frere")[0] == "il est son frere"


def test_qu_il_et_qu_elle_sont_couverts():
    # L'apostrophe est une frontiere de mot : aucun traitement special requis.
    assert corriger("je pense qu'il et parti")[0] == "je pense qu'il est parti"


def test_les_changements_sont_rapportes():
    _, changements = corriger("que c'est-tu de moi")
    assert changements == ["c'est-tu"]


def test_aucun_groupe_ne_se_corrige_lui_meme():
    # Garde-fou sur la table : si la forme correcte d'un pronom etait absente
    # de ses propres graphies, une phrase juste serait « corrigee » en boucle.
    for groupe in GROUPES:
        for pronom, correcte in groupe.formes.items():
            assert correcte in groupe.graphies, (
                f"{groupe.son} : « {correcte} » ({pronom}) doit figurer dans les graphies, "
                "sinon la forme juste serait elle-meme corrigee"
            )


# ══════════════════════════════════════════════════════════════════════════
#  L'ORDRE ADRESSE A NOVA — UN DECOUPAGE, PAS UNE CONJUGAISON
#
#  Les regles precedentes corrigent une graphie apres un pronom. Celle-ci
#  corrige un endroit de coupure. Releve en conditions reelles :
#
#      dit      « parle-moi de Mars »
#      entendu  « par le mois de mars »
#      repondu  « Le mois de mars est une periode de transition pour… »
#
#  /paʁ lə mwa də/ et /paʁl mwa də/ sont le meme son : aucun modele ne peut
#  trancher a l'oreille. La grammaire, elle, le peut sans ambiguite — « par le
#  mois de X » n'existe pas en francais.
#
#  Le cout de l'erreur est eleve et silencieux : Nova ne repond pas a cote,
#  elle repond serieusement a une question inventee.
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    ("entendu", "attendu"),
    [
        ("Nova, par le mois de Mars", "Nova, parle-moi de Mars"),
        ("par le mois des trous noirs", "parle-moi des trous noirs"),
        ("par le mois du soleil", "parle-moi du soleil"),
        ("par le mois d'Einstein", "parle-moi d'Einstein"),
        ("par le moi de toi", "parle-moi de toi"),
        # Le trait d'union manquant : cosmetique, mais gratuit.
        ("parle moi de la Lune", "parle-moi de la Lune"),
    ],
)
def test_le_decoupage_fautif_est_recolle(entendu, attendu):
    assert corriger(entendu)[0] == attendu


@pytest.mark.parametrize(
    "juste",
    [
        # ⚠️ CES PHRASES SONT CORRECTES. LES « CORRIGER » SERAIT LE VRAI DEFAUT.
        "au mois de mars il fait encore froid",
        "je l'ai vu le mois dernier",
        "par le mois dernier",          # attrape par la borne de mot
        "le mois de juin est charge",
        "on se voit par le train de midi",
    ],
)
def test_ce_qui_peut_etre_juste_n_est_pas_touche(juste):
    """Un correcteur qui remplace tout ce qui sonne pareil casse plus de
    phrases justes qu'il n'en repare, et le fait en silence."""
    assert corriger(juste)[0] == juste


def test_la_borne_de_mot_empeche_une_correction_inventee():
    """⚠️ LA PREMIERE VERSION FABRIQUAIT UN AUTRE DECOUPAGE FAUTIF.

    Sans borne apres « de », le « de » de « dernier » correspondait :
    « par le mois dernier » devenait « parle-moi dernier ». La regle censee
    reparer un mauvais decoupage en inventait un autre — sur une phrase qui,
    elle, etait plausible.
    """
    assert "parle-moi dernier" not in corriger("par le mois dernier")[0]


def test_la_correction_est_rapportee():
    """Corriger en silence rend indebogable une correction qui se trompe."""
    _, changements = corriger("par le mois de Mars")
    assert changements, "aucun changement rapporte"
