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
