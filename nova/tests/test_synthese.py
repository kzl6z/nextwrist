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
    # Piper a son propre reglage de modele depuis qu'un reglage partage avait
    # fait passer un chemin .onnx pour un nom de voix Kokoro. Les bancs qui ne
    # precisent pas de modele en ont donc besoin d'un.
    monkeypatch.setattr(
        synthese.get_settings(), "voix_modele_piper", "fr_FR-siwis-medium", raising=False
    )
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
    monkeypatch.setattr(
        synthese.get_settings(), "voix_modele_piper", "fr_FR-siwis-medium", raising=False
    )

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


# ══════════════════════════════════════════════════════════════════════════
#  LE NETTOYAGE DES BORDS
#
#  Le modele affine reproduit l'inspiration qui precedait chaque prise du
#  corpus : ce n'est pas un defaut du moteur mais un motif APPRIS, donc aucun
#  reglage de synthese ne l'enleve. On le coupe apres coup, ou c'est
#  deterministe — et ou un banc peut le prouver.
# ══════════════════════════════════════════════════════════════════════════
def _wav(echantillons, taux=22050, canaux=1, largeur=2) -> bytes:
    import io
    from array import array

    pcm = array("h", echantillons)
    if sys.byteorder == "big":
        pcm.byteswap()
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as f:
        f.setnchannels(canaux)
        f.setsampwidth(largeur)
        f.setframerate(taux)
        f.writeframes(pcm.tobytes())
    return tampon.getvalue()


def _echantillons(wav: bytes):
    import io
    from array import array

    with wave.open(io.BytesIO(wav), "rb") as f:
        pcm = array("h")
        pcm.frombytes(f.readframes(f.getnframes()))
    if sys.byteorder == "big":
        pcm.byteswap()
    return pcm


def _souffle_parole_souffle(taux=22050):
    """Ce que rend le modele : un souffle, la phrase, un souffle."""
    souffle = [200 if i % 2 else -200 for i in range(int(taux * 0.25))]
    parole = [12000 if i % 2 else -12000 for i in range(int(taux * 0.60))]
    return souffle + parole + list(souffle), len(souffle), len(parole)


def test_le_souffle_des_extremites_disparait():
    """⚠️ C'EST LE DEFAUT QUI A MOTIVE TOUT CE BLOC.

    Chaque prise du corpus commencait par une inspiration ; le modele a appris
    qu'un enonce commence ainsi et le reproduit a chaque phrase.
    """
    brut, souffle, parole = _souffle_parole_souffle()
    taux = 22050

    net = _echantillons(synthese._nettoyer_bords(_wav(brut, taux)))

    # La parole est gardee, les deux souffles de 250 ms sont partis — a deux
    # choses pres, qui sont voulues : la marge, et la granularite du balayage.
    # Le debut detecte se cale sur une frontiere de fenetre, donc jusqu'a
    # 10 ms de souffle survivent de chaque cote. Le fondu les recouvre.
    marge = int(taux * synthese._MARGE_S)
    fenetre = int(taux * synthese._FENETRE_S)
    assert parole <= len(net) <= parole + 2 * (marge + fenetre)
    assert max(abs(v) for v in net) >= 11000, "la parole a ete abimee"


def test_les_extremites_sont_fondues_et_pas_coupees_net():
    """Une coupe franche fabrique le claquement qu'on voulait supprimer."""
    brut, _, _ = _souffle_parole_souffle()

    net = _echantillons(synthese._nettoyer_bords(_wav(brut)))

    assert abs(net[0]) < 500, "debut coupe net"
    assert abs(net[-1]) < 500, "fin coupee net"


def test_un_second_passage_ne_ronge_pas_l_audio():
    """⚠️ UN NETTOYAGE QUI S'APPLIQUE DEUX FOIS DOIT RESTER STABLE.

    Le fondu laisse des extremites faibles. Si le seuil les prenait pour du
    souffle, chaque passage raccourcirait un peu plus la phrase — une erreur
    qui ne se verrait qu'apres coup, sur une voix devenue trop breve.

    On n'exige pas l'egalite stricte : le balayage par fenetres perd un
    echantillon d'alignement par passage. Ce qu'on exige est que ca ne
    s'emballe pas — cinq passages doivent couter moins d'une milliseconde.
    """
    taux = 22050
    brut, _, _ = _souffle_parole_souffle(taux)

    wav = synthese._nettoyer_bords(_wav(brut, taux))
    depart = len(_echantillons(wav))
    for _ in range(5):
        wav = synthese._nettoyer_bords(wav)

    perdu = depart - len(_echantillons(wav))
    assert 0 <= perdu < taux * 0.001, f"{perdu} echantillons ronges en cinq passages"


def test_un_fichier_entierement_silencieux_est_rendu_tel_quel():
    """Mieux vaut un WAV muet qu'un WAV vide : c'est une reponse valide."""
    muet = _wav([0] * 22050)

    assert synthese._nettoyer_bords(muet) == muet


def test_un_format_inattendu_traverse_sans_dommage():
    """⚠️ ON NE REECRIT PAS CE QU'ON NE SAIT PAS LIRE.

    Un jour un moteur rendra du stereo ou du 24 bits. Le nettoyage doit alors
    s'abstenir, pas produire un fichier abime que rien ne signalera.
    """
    stereo = _wav([1000] * 44100, canaux=2)
    pas_un_wav = b"ceci n'est pas un WAV"

    assert synthese._nettoyer_bords(stereo) == stereo
    assert synthese._nettoyer_bords(pas_un_wav) == pas_un_wav


def test_un_enonce_trop_court_n_est_pas_touche():
    """Sous 0,1 s, le fondu recouvrirait tout le fichier."""
    court = _wav([12000, -12000] * 100)

    assert synthese._nettoyer_bords(court) == court


def test_le_taux_du_fichier_est_conserve():
    """Reecrire a un taux suppose donnerait une voix trop lente, sans erreur."""
    brut, _, _ = _souffle_parole_souffle(taux=16000)

    net = synthese._nettoyer_bords(_wav(brut, taux=16000))

    import io

    with wave.open(io.BytesIO(net), "rb") as f:
        assert f.getframerate() == 16000


def test_le_nettoyage_peut_etre_desactive(monkeypatch):
    """Pour comparer a l'oreille avec et sans, comme on a compare les voix."""
    brut, _, _ = _souffle_parole_souffle()
    taux = 22050
    _piper_double(monkeypatch, taux=taux, echantillons=0)

    class VoixSoufflante:
        def synthesize_wav(self, texte, fichier, **kw):
            from array import array

            fichier.setnchannels(1)
            fichier.setsampwidth(2)
            fichier.setframerate(taux)
            fichier.writeframes(array("h", brut).tobytes())

        @staticmethod
        def load(chemin, **kw):
            return VoixSoufflante()

    module = types.ModuleType("piper")
    module.PiperVoice = VoixSoufflante
    monkeypatch.setitem(sys.modules, "piper", module)
    synthese._voix_piper.cache_clear()
    monkeypatch.setattr(synthese.get_settings(), "voix_moteur", "piper", raising=False)

    monkeypatch.setattr(synthese.get_settings(), "voix_nettoyer_bords", False, raising=False)
    sans = len(_echantillons(synthese.synthetiser("bonjour")))

    monkeypatch.setattr(synthese.get_settings(), "voix_nettoyer_bords", True, raising=False)
    avec = len(_echantillons(synthese.synthetiser("bonjour")))

    assert sans == len(brut)
    assert avec < sans


def test_chaque_moteur_a_son_propre_reglage_de_modele(monkeypatch, tmp_path):
    """⚠️ UN REGLAGE PARTAGE FAISAIT PASSER UN CHEMIN .ONNX A KOKORO.

    Il a suffi de basculer `NOVA_VOIX_MOTEUR` de `piper` a `kokoro` pour que
    le nom de voix devienne « /Users/.../nova.onnx ». Le reglage restait
    renseigne, correctement, pour l'autre moteur — et rien ne rappelait qu'il
    fallait le changer aussi.
    """
    modele = tmp_path / "nova.onnx"
    modele.write_bytes(b"faux modele")
    charges = _piper_double(monkeypatch)
    vues = {}

    class FauxPipeline:
        def __init__(self, lang_code):
            pass

        def __call__(self, texte, voice=None):
            vues["voix"] = voice
            yield (None, None, [0.1])

    module = types.ModuleType("kokoro")
    module.KPipeline = FauxPipeline
    monkeypatch.setitem(sys.modules, "kokoro", module)
    synthese._pipeline.cache_clear()

    reglages = synthese.get_settings()
    monkeypatch.setattr(reglages, "voix_modele", "ff_siwis", raising=False)
    monkeypatch.setattr(reglages, "voix_modele_piper", str(modele), raising=False)

    monkeypatch.setattr(reglages, "voix_moteur", "piper", raising=False)
    synthese.synthetiser("bonjour")
    monkeypatch.setattr(reglages, "voix_moteur", "kokoro", raising=False)
    synthese.synthetiser("bonjour")

    assert charges == [str(modele)], "piper n'a pas recu son .onnx"
    assert vues["voix"] == "ff_siwis", f"kokoro a recu « {vues['voix']} »"


def test_piper_sans_modele_dit_quoi_ajouter(monkeypatch):
    """Un reglage manquant n'est pas une panne : il y a une ligne a ecrire."""
    _piper_double(monkeypatch)
    reglages = synthese.get_settings()
    monkeypatch.setattr(reglages, "voix_moteur", "piper", raising=False)
    monkeypatch.setattr(reglages, "voix_modele_piper", "", raising=False)

    with pytest.raises(synthese.SyntheseIndisponible) as erreur:
        synthese.synthetiser("bonjour")

    assert "NOVA_VOIX_MODELE_PIPER" in str(erreur.value)


def test_une_voix_de_catalogue_absente_dit_quoi_telecharger(monkeypatch):
    """⚠️ CE DEFAUT SE PRESENTAIT COMME « NOVA A CHANGE DE VOIX ».

    Piper 1.7 ne telecharge pas les voix du catalogue : `PiperVoice.load`
    attend un fichier local. Un nom de catalogue produisait donc

        [Errno 2] No such file or directory: 'fr_FR-siwis-medium.json'

    remonte en 500. L'application, voyant la synthese echouer, se rabattait
    sur la voix du systeme — masculine. Le symptome visible n'avait plus
    aucun rapport avec la cause, et envoyait chercher la panne du cote de la
    voix plutot que du cote du fichier manquant.
    """
    class VoixQuiNeTelechargePas:
        @staticmethod
        def load(chemin, **kw):
            raise FileNotFoundError(2, "No such file or directory", f"{chemin}.json")

    module = types.ModuleType("piper")
    module.PiperVoice = VoixQuiNeTelechargePas
    monkeypatch.setitem(sys.modules, "piper", module)
    synthese._voix_piper.cache_clear()
    reglages = synthese.get_settings()
    monkeypatch.setattr(reglages, "voix_moteur", "piper", raising=False)
    monkeypatch.setattr(reglages, "voix_modele_piper", "fr_FR-siwis-medium", raising=False)

    with pytest.raises(synthese.SyntheseIndisponible) as erreur:
        synthese.synthetiser("bonjour")

    message = str(erreur.value)
    assert "download_voices" in message, "il faut donner la commande, pas le constat"
    assert "fr_FR-siwis-medium" in message
