"""La voix de Nova, revenue sur la machine.

POURQUOI CETTE BRIQUE EXISTE

La voix passait par ElevenLabs. Elle s'est arretee un soir, en pleine
conversation :

    "This request exceeds your quota of 10000. You have 3 credits remaining,
     while 10 credits are required for this request."

Dix mille credits par mois, une reponse de Nova ~150 caracteres : soixante
reponses mensuelles. Ce n'etait pas une panne mais un plafond — et il tombait
en silence, sur la voix du systeme, sans que rien n'explique pourquoi.

CE QUE CE BANC PROTEGE

Kokoro ne peut pas etre installe ici (le modele se telecharge depuis un hote
que cet environnement ne joint pas). On le remplace donc par un double, ce qui
est de toute facon la bonne granularite : ce qui peut casser dans ce code n'est
pas la qualite du modele — c'est l'enveloppe WAV, la conversion des
echantillons, et le comportement quand la brique est absente.

Le detail le plus fragile est la conversion flottant → 16 bits. Kokoro rend des
valeurs dans [-1, 1] ; sans bornage AVANT la conversion, un depassement repasse
par zero en arithmetique entiere et produit un claquement au lieu d'une
saturation. C'est le genre d'erreur qu'aucun test de bout en bout ne rattrape,
parce que le fichier reste un WAV parfaitement valide.
"""

from __future__ import annotations

import struct
import sys
import types
import wave

import pytest

from nova.voice import synthese


def _kokoro_double(monkeypatch, echantillons):
    """Installe un faux `kokoro` et vide le cache du pipeline."""
    class FauxPipeline:
        def __init__(self, lang_code):
            self.lang_code = lang_code

        def __call__(self, texte, voice=None):
            self.derniere_voix = voice
            yield (None, None, list(echantillons))

    module = types.ModuleType("kokoro")
    module.KPipeline = FauxPipeline
    monkeypatch.setitem(sys.modules, "kokoro", module)
    synthese._pipeline.cache_clear()
    return module


def _lire(wav: bytes):
    import io

    with wave.open(io.BytesIO(wav), "rb") as f:
        return f.getnchannels(), f.getsampwidth(), f.getframerate(), f.readframes(f.getnframes())


def test_le_wav_annonce_le_vrai_taux_du_modele(monkeypatch):
    """24 kHz : ecrire autre chose donnerait une voix trop lente ou trop aigue."""
    _kokoro_double(monkeypatch, [0.0, 0.5, -0.5])

    canaux, largeur, taux, _ = _lire(synthese.synthetiser("bonjour"))

    assert (canaux, largeur, taux) == (1, 2, synthese.ECHANTILLONNAGE) == (1, 2, 24000)


def test_les_depassements_saturent_au_lieu_de_claquer(monkeypatch):
    """⚠️ SANS BORNAGE, +1.5 REPASSE PAR ZERO ET DEVIENT UN CLAQUEMENT.

    Le fichier resterait un WAV valide, et le defaut ne s'entendrait que sur
    les syllabes fortes. Aucun test de bout en bout ne le verrait.
    """
    _kokoro_double(monkeypatch, [1.5, -1.5, 3.0, -3.0])

    _, _, _, brut = _lire(synthese.synthetiser("fort"))
    valeurs = struct.unpack(f"<{len(brut) // 2}h", brut)

    assert all(abs(v) >= 32000 for v in valeurs), f"depassement mal borne : {valeurs}"
    assert valeurs[0] > 0 and valeurs[1] < 0, "le signe a change — c'est le claquement"


def test_un_texte_vide_rend_un_wav_muet_et_valide(monkeypatch):
    """La parole en flux decoupe par phrases : un fragment vide peut arriver.

    Echouer ici casserait la lecture de TOUTE la reponse pour un signe de
    ponctuation isole.
    """
    _kokoro_double(monkeypatch, [0.1])

    canaux, largeur, taux, brut = _lire(synthese.synthetiser("   "))

    assert brut == b""
    assert (canaux, largeur, taux) == (1, 2, 24000)


def test_la_voix_demandee_est_bien_transmise(monkeypatch):
    """Le reglage doit atteindre le moteur, pas seulement exister."""
    vues = {}

    class FauxPipeline:
        def __init__(self, lang_code):
            vues["langue"] = lang_code

        def __call__(self, texte, voice=None):
            vues["voix"] = voice
            yield (None, None, [0.1])

    module = types.ModuleType("kokoro")
    module.KPipeline = FauxPipeline
    monkeypatch.setitem(sys.modules, "kokoro", module)
    synthese._pipeline.cache_clear()

    synthese.synthetiser("salut", voix="ff_autre", langue="f")

    assert vues == {"langue": "f", "voix": "ff_autre"}


def test_la_brique_absente_se_distingue_d_une_panne(monkeypatch):
    """503 et non 500 : il n'y a rien a deboguer, seulement a installer."""
    monkeypatch.setitem(sys.modules, "kokoro", None)
    synthese._pipeline.cache_clear()

    with pytest.raises(synthese.SyntheseIndisponible) as erreur:
        synthese.synthetiser("bonjour")

    # Le message doit porter le remede COMPLET. `espeak-ng` n'est mentionne
    # dans aucune documentation d'installation de Kokoro, et sans lui le
    # francais echoue sur une erreur qui parle de tout sauf de ca.
    assert "espeak-ng" in str(erreur.value)
    assert "[speech]" in str(erreur.value)


def test_le_moteur_n_est_charge_qu_une_fois(monkeypatch):
    """⚠️ IL EST APPELE UNE FOIS PAR PHRASE, PAS UNE FOIS PAR REPONSE.

    La parole en flux demande une synthese des la premiere phrase, pendant que
    le modele ecrit les suivantes. Un chargement par requete se paierait a
    chaque phrase prononcee.
    """
    chargements = []

    class FauxPipeline:
        def __init__(self, lang_code):
            chargements.append(lang_code)

        def __call__(self, texte, voice=None):
            yield (None, None, [0.1])

    module = types.ModuleType("kokoro")
    module.KPipeline = FauxPipeline
    monkeypatch.setitem(sys.modules, "kokoro", module)
    synthese._pipeline.cache_clear()

    for phrase in ("une", "deux", "trois"):
        synthese.synthetiser(phrase)

    assert len(chargements) == 1, f"{len(chargements)} chargements pour trois phrases"


# ══════════════════════════════════════════════════════════════════════════
#  LE POINT D'ENTREE — /v1/audio/speech
#
#  C'est lui que l'application appelle a la place d'ElevenLabs, une fois par
#  phrase, pendant que le modele ecrit les suivantes.
# ══════════════════════════════════════════════════════════════════════════
def _client():
    from fastapi.testclient import TestClient

    from nova.api.app import app

    return TestClient(app)


def test_le_point_d_entree_rend_un_wav_jouable(monkeypatch):
    _kokoro_double(monkeypatch, [0.0, 0.3, -0.3])

    reponse = _client().post("/v1/audio/speech", json={"input": "Il est deux heures."})

    assert reponse.status_code == 200
    assert reponse.headers["content-type"] == "audio/wav"
    # `RIFF....WAVE` : l'en-tete, pas seulement « des octets sont arrives ».
    assert reponse.content[:4] == b"RIFF" and reponse.content[8:12] == b"WAVE"


def test_le_champ_text_de_l_application_est_accepte(monkeypatch):
    """L'app de bureau envoyait deja `text` a ElevenLabs.

    Le nom OpenAI est `input`. Exiger le renommage casserait l'appelant pour
    une raison de vocabulaire — on accepte les deux.
    """
    _kokoro_double(monkeypatch, [0.1])

    reponse = _client().post("/v1/audio/speech", json={"text": "bonjour"})

    assert reponse.status_code == 200


def test_un_texte_absent_est_une_erreur_de_l_appelant(monkeypatch):
    _kokoro_double(monkeypatch, [0.1])

    assert _client().post("/v1/audio/speech", json={}).status_code == 400


def test_la_brique_absente_rend_503_et_dit_quoi_installer(monkeypatch):
    """503 et non 500 : rien a deboguer, quelque chose a installer.

    Et le message doit porter le remede — c'est la lecon directe de `tts.js`,
    qui resumait trois causes distinctes en une phrase inutile.
    """
    monkeypatch.setitem(sys.modules, "kokoro", None)
    synthese._pipeline.cache_clear()

    reponse = _client().post("/v1/audio/speech", json={"input": "bonjour"})

    assert reponse.status_code == 503
    assert "espeak-ng" in reponse.json()["detail"]


# ══════════════════════════════════════════════════════════════════════════
#  PIPER — le moteur de soixante megaoctets
#
#  Kokoro est generaliste : 350 Mo plus torch, environ un gigaoctet resident.
#  Sur 8 Go deja occupes par un modele de langue de 3,3 Go, ce gigaoctet se
#  paie deux fois — en memoire, puis en lenteur de tout le reste.
#
#  Un modele Piper ne connait qu'une voix : 60 Mo sur onnx, sans torch. C'est
#  aussi le format d'un modele AFFINE, donc le chemin par lequel un clone
#  arrivera. Ces bancs verifient qu'il arrivera sans une ligne de code a ecrire.
# ══════════════════════════════════════════════════════════════════════════
def _piper_double(monkeypatch, taux=22050, echantillons=2205):
    """Un faux `piper` qui ecrit un WAV a SON propre taux."""
    charges = []

    class FausseVoix:
        def synthesize_wav(self, texte, fichier, **kw):
            fichier.setnchannels(1)
            fichier.setsampwidth(2)
            fichier.setframerate(taux)
            fichier.writeframes(b"\x00\x01" * echantillons)

        @staticmethod
        def load(chemin, **kw):
            charges.append(str(chemin))
            return FausseVoix()

    module = types.ModuleType("piper")
    module.PiperVoice = FausseVoix
    monkeypatch.setitem(sys.modules, "piper", module)
    synthese._voix_piper.cache_clear()
    return charges


def test_piper_rend_un_wav_au_taux_de_son_modele(monkeypatch):
    """⚠️ LE TAUX VIENT DU MODELE, IL N'EST PAS SUPPOSE.

    Kokoro rend du 24 kHz, Piper « medium » du 22 050, et rien ne garantit
    qu'un modele affine sur mesure suive l'un ou l'autre. Laisser Piper ecrire
    son propre en-tete supprime la classe entiere des bugs de frequence —
    celle qui donne une voix trop lente sans qu'aucun fichier ne soit invalide.
    """
    _piper_double(monkeypatch, taux=22050)
    monkeypatch.setattr(synthese.get_settings(), "voix_moteur", "piper", raising=False)

    _, _, taux, _ = _lire(synthese.synthetiser("bonjour"))

    assert taux == 22050 != synthese.ECHANTILLONNAGE


def test_un_chemin_onnx_est_charge_tel_quel(monkeypatch, tmp_path):
    """C'est ce qui rend un clone branchable sans publier le modele nulle part.

    Un modele affine n'existe que sur une machine. S'il fallait un nom du
    catalogue, il faudrait le publier pour que Piper le telecharge — pour un
    fichier qui ne concerne personne d'autre.
    """
    charges = _piper_double(monkeypatch)
    modele = tmp_path / "nova.onnx"
    modele.write_bytes(b"faux modele")
    monkeypatch.setattr(synthese.get_settings(), "voix_moteur", "piper", raising=False)

    synthese.synthetiser("bonjour", voix=str(modele))

    assert charges == [str(modele)]


def test_un_onnx_absent_le_dit_au_lieu_de_planter(monkeypatch):
    _piper_double(monkeypatch)
    monkeypatch.setattr(synthese.get_settings(), "voix_moteur", "piper", raising=False)

    with pytest.raises(synthese.SyntheseIndisponible) as erreur:
        synthese.synthetiser("bonjour", voix="/nulle/part/nova.onnx")

    assert "introuvable" in str(erreur.value)


def test_piper_absent_ne_parle_pas_d_espeak(monkeypatch):
    """⚠️ CHAQUE MOTEUR A SON PROPRE REMEDE.

    Kokoro exige `brew install espeak-ng`, que sa documentation ne mentionne
    nulle part. Piper embarque le sien. Afficher le remede de l'un pour la
    panne de l'autre enverrait installer une dependance sans rapport — c'est
    exactement le defaut de `tts.js`, transpose d'un etage.
    """
    monkeypatch.setitem(sys.modules, "piper", None)
    synthese._voix_piper.cache_clear()
    monkeypatch.setattr(synthese.get_settings(), "voix_moteur", "piper", raising=False)

    with pytest.raises(synthese.SyntheseIndisponible) as erreur:
        synthese.synthetiser("bonjour")

    assert "[piper]" in str(erreur.value)
    assert "espeak" not in str(erreur.value).lower()


def test_le_modele_piper_n_est_charge_qu_une_fois(monkeypatch, tmp_path):
    charges = _piper_double(monkeypatch)
    modele = tmp_path / "nova.onnx"
    modele.write_bytes(b"faux modele")
    monkeypatch.setattr(synthese.get_settings(), "voix_moteur", "piper", raising=False)

    for phrase in ("une", "deux", "trois"):
        synthese.synthetiser(phrase, voix=str(modele))

    assert len(charges) == 1
