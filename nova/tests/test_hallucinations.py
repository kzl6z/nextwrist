"""Formules de sous-titrage produites par Whisper sur le quasi-silence.

Whisper a ete entraine sur des sous-titres : prive de parole claire, il rend
ce qui terminait ces fichiers plutot qu'une chaine vide. Envoyees telles
quelles au modele de langue, ces phrases coutaient 22 secondes de reflexion
sur une demande que personne n'avait formulee.
"""

import types

import pytest

from nova.voice import transcribe
from nova.voice.transcribe import est_hallucination


def test_reconnait_la_formule_observee():
    # Relevee dans les logs de la machine.
    assert est_hallucination("les sous-titres réalisés par la communauté d'Amara.org")
    assert est_hallucination("Sous-titres réalisés par la communauté d'Amara.org")


def test_reconnait_les_autres_formules_courantes():
    assert est_hallucination("Sous-titrage Société Radio-Canada")
    assert est_hallucination("Merci d'avoir regardé cette vidéo !")
    assert est_hallucination("Abonnez-vous à la chaîne")


def test_reconnait_une_signature_de_studio_jamais_vue():
    """⚠️ LA LISTE EXACTE NE POUVAIT PAS SUFFIRE, ET NE SUFFIRA JAMAIS.

    Releve en conditions reelles, sur un bruit de clavier :

        enchaine sur : « Sous-titrage ST' 501 »
        Nova : « C'est un film de science-fiction… »

    Cette formule n'etait dans aucune des huit connues, et il y en a des
    centaines : chaque studio signe la sienne. Ce qu'elles ont toutes en
    commun, c'est de COMMENCER par le mot.
    """
    assert est_hallucination("Sous-titrage ST' 501")
    assert est_hallucination("Sous-titrage FR : Studio Machin")
    assert est_hallucination("Sous-titres : Nathalie D.")


def test_laisse_passer_une_vraie_demande():
    assert not est_hallucination("Nova, quelle heure est-il ?")
    assert not est_hallucination("Ouvre le dossier du projet")
    assert not est_hallucination("")


def test_laisse_passer_une_phrase_qui_parle_de_sous_titres():
    # Une vraie demande sur le sujet ne doit pas etre confondue avec la
    # formule : elle est plus longue, et c'est ce qui les distingue.
    assert not est_hallucination(
        "Nova, peux-tu me trouver les sous-titres realises pour la video "
        "que j'ai enregistree hier soir avec la camera du salon ?"
    )


# ══════════════════════════════════════════════════════════════════════════
#  LA PONCTUATION SEULE
#
#  ⚠️ CE CAS A COUTE HUIT SECONDES ET UNE REPONSE INVENTEE.
#
#  Sur du silence, Whisper rend parfois de la ponctuation plutot qu'une
#  chaine vide. Releve en conditions reelles :
#
#      [NOVA/ecoute] transcrit en 3284 ms : « . . . »
#      [NOVA] User Input Received « . . . »
#      [NOVA] LECTURE de la question : 8313 ms
#
#  Ces trois points sont partis au modele de langue, qui a repondu — un
#  modele repond toujours. Nova a parle toute seule, longuement, sur une
#  phrase que personne n'avait prononcee.
# ══════════════════════════════════════════════════════════════════════════
class _FauxSegment:
    def __init__(self, texte):
        self.text, self.start, self.end, self.avg_logprob = texte, 0.0, 2.0, -0.4


def _whisper_qui_rend(monkeypatch, texte):
    class FauxModele:
        def transcribe(self, chemin, **kw):
            info = types.SimpleNamespace(duration=2.0)
            return [_FauxSegment(texte)], info

    monkeypatch.setattr(transcribe, "_modele", lambda nom=None: FauxModele())


@pytest.mark.parametrize("bruit", ["...", ". . .", "…", " ?! ", "-- ,, --"])
def test_une_transcription_sans_mot_est_du_silence(monkeypatch, bruit):
    """Un texte sans caractere alphanumerique ne peut etre ni question ni ordre."""
    _whisper_qui_rend(monkeypatch, bruit)

    resultat = transcribe.transcrire(b"\0" * 5000)

    assert resultat.texte == "", f"« {bruit} » est parti au modele de langue"
    assert not resultat


def test_le_filtre_d_hallucination_ne_couvrait_pas_ce_cas():
    """Il se declarait meme incompetent : `_reduire('...')` est vide."""
    assert not est_hallucination("...")


def test_une_vraie_phrase_traverse(monkeypatch):
    """Le garde-fou ne doit pas manger la parole qu'il est cense proteger."""
    _whisper_qui_rend(monkeypatch, "Nova, ouvre le dossier du projet.")

    assert "dossier" in transcribe.transcrire(b"\0" * 5000).texte


# ══════════════════════════════════════════════════════════════════════════
#  LE BRUIT DE CLAVIER
#
#  ⚠️ NOVA A PARLE ALORS QUE PERSONNE NE LUI AVAIT RIEN DIT.
#
#  Releve en conditions reelles, pendant que l'utilisateur TAPAIT :
#
#      [NOVA/reveil] 1920 ms → « Nova. Nova. Nova. Nova. … »  (cinquante fois)
#      declenche — enchaine sur : « Sous-titrage ST' 501 »
#      Nova : « C'est un film de science-fiction… »
#
#  Le clavier a reveille Nova, ouvert une conversation, et le fragment suivant
#  est parti au modele de langue comme une question.
# ══════════════════════════════════════════════════════════════════════════
def test_le_mot_de_reveil_repete_cinquante_fois_est_du_bruit():
    """Personne ne dit cinquante fois le meme mot en deux secondes."""
    assert transcribe.est_radotage("Nova. " * 50)


def test_le_radotage_est_reconnu_quel_que_soit_le_mot():
    """⚠️ IL NE SE COMPARE A AUCUNE LISTE.

    C'est ce qui le separe du filtre de sous-titrage : la repetition se
    reconnait toute seule. Whisper s'accroche au mot qu'il veut.
    """
    assert transcribe.est_radotage("oui oui oui oui oui oui oui oui")
    assert transcribe.est_radotage("Merci. Merci. Merci. Merci. Merci. Merci.")


@pytest.mark.parametrize(
    "parole",
    [
        # Une insistance normale : trop courte pour etre du bruit.
        "non non non",
        "oui oui",
        # De vraies demandes, ou aucun mot ne domine.
        "Nova, retrouve mes impots de 2024",
        "ouvre le deuxieme fichier s'il te plait",
        # ⚠️ UN MOT FREQUENT NE FAIT PAS UN RADOTAGE.
        #
        # « de » revient quatre fois ici, et la phrase est parfaitement
        # normale. C'est la PROPORTION qui tranche, pas le compte seul.
        "retrouve le releve de compte de la banque de mars de 2024",
        "",
    ],
)
def test_la_parole_normale_traverse(parole):
    assert not transcribe.est_radotage(parole), parole


def test_le_radotage_est_filtre_de_bout_en_bout(monkeypatch):
    """⚠️ LE FILTRE D'AMORCE NE POUVAIT PAS L'ATTRAPER.

    Il n'examine que les extraits de moins de 90 caracteres, et cinquante
    « Nova » en font 250. La repetition passait entre les mailles PARCE
    QU'ELLE ETAIT LONGUE. Ce banc va jusqu'a `transcrire`, sans quoi il
    protegerait une fonction que personne n'appelle.
    """
    _whisper_qui_rend(monkeypatch, "Nova. " * 50)

    resultat = transcribe.transcrire(b"\0" * 5000, amorce=AMORCE)

    assert resultat.texte == "", "le bruit de clavier est parti au modele de langue"


def test_la_signature_de_studio_est_filtree_de_bout_en_bout(monkeypatch):
    """Le second fragment du meme releve, celui qui a fait parler Nova."""
    _whisper_qui_rend(monkeypatch, "Sous-titrage ST' 501")

    assert transcribe.transcrire(b"\0" * 5000).texte == ""


# ══════════════════════════════════════════════════════════════════════════
#  L'ECHO DE L'AMORCE
#
#  ⚠️ CE DEFAUT FAIT REPONDRE NOVA A UNE QUESTION QUE PERSONNE N'A POSEE.
#
#  Releve en conditions reelles, personne n'ayant parle :
#
#      Transcription : 2.05 s d'audio → « No, no, va, qu'est-ce qu'un trou noir »
#      Relecture : « quelle heure est-il » → « qu'est-ce qu'un trou noir »
#
#  « qu'est-ce qu'un trou noir » etait un exemple de l'amorce, mot pour mot.
#  Nova a repondu, longuement, sur ce trou noir.
# ══════════════════════════════════════════════════════════════════════════
AMORCE = (
    "Conversation avec Nova, assistante vocale francaise. "
    "Nova, qu'est-ce qu'un trou noir ? Nova, ouvre un nouveau projet."
)


def test_une_amorce_recopiee_avec_doute_est_du_silence():
    """Le cas exact du journal : le texte vient de l'amorce, la confiance est basse."""
    assert transcribe.est_echo_de_l_amorce(
        "qu'est-ce qu'un trou noir", AMORCE, logprob=-0.62
    )


def test_la_meme_phrase_dite_clairement_traverse():
    """⚠️ L'AMORCE CONTIENT LE VOCABULAIRE QU'ON EMPLOIE VRAIMENT.

    « ouvre un nouveau projet » appartient a l'amorce et reste une commande
    parfaitement legitime. Ce qui separe l'echo de la parole n'est pas le
    texte mais le DOUTE du modele.
    """
    assert not transcribe.est_echo_de_l_amorce(
        "ouvre un nouveau projet", AMORCE, logprob=-0.18
    )


def test_une_phrase_absente_de_l_amorce_traverse_meme_dans_le_doute():
    """Un audio difficile n'est pas une raison de jeter ce qui a ete dit."""
    assert not transcribe.est_echo_de_l_amorce(
        "rappelle-moi d'appeler le plombier", AMORCE, logprob=-0.80
    )


def test_sans_confiance_connue_on_ne_jette_rien():
    """Dans le doute sur le doute, on garde la parole."""
    assert not transcribe.est_echo_de_l_amorce(
        "qu'est-ce qu'un trou noir", AMORCE, logprob=None
    )


def test_une_longue_phrase_n_est_jamais_un_echo():
    """Au-dela, il y a une vraie phrase autour et la coincidence n'en est plus une."""
    longue = (
        "qu'est-ce qu'un trou noir et pourquoi la lumiere n'en ressort jamais "
        "meme quand elle arrive tres vite depuis une etoile lointaine"
    )
    assert not transcribe.est_echo_de_l_amorce(longue, AMORCE + longue, logprob=-0.9)


def test_l_echo_est_filtre_de_bout_en_bout(monkeypatch):
    """Le garde-fou doit agir dans `transcrire`, pas seulement en theorie."""
    _whisper_qui_rend(monkeypatch, "qu'est-ce qu'un trou noir")

    class _SegmentDouteux(_FauxSegment):
        def __init__(self, texte):
            super().__init__(texte)
            self.avg_logprob = -0.62

    def transcribe_douteux(chemin, **kw):
        return [_SegmentDouteux("qu'est-ce qu'un trou noir")], types.SimpleNamespace(
            duration=2.05
        )

    class FauxModele:
        transcribe = staticmethod(transcribe_douteux)

    monkeypatch.setattr(transcribe, "_modele", lambda nom=None: FauxModele())

    resultat = transcribe.transcrire(b"\0" * 5000, amorce=AMORCE)

    assert resultat.texte == "", "l'amorce recopiee est repartie vers le modele"
