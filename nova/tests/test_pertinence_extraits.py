"""Le plus proche voisin n'est pas forcement proche.

LE DEFAUT QUE CES TESTS PROTEGENT

Une recherche vectorielle rend TOUJOURS ses k plus proches voisins. Sur une
question sans rapport avec le corpus, elle rend donc les moins mauvais — et
le score de fusion (RRF) ne peut pas le detecter, puisqu'il mesure un RANG :
le premier reste premier, avec le meme score, qu'il soit pertinent ou non.

Releve en conditions reelles sur « qu'est-ce que la relativite », question
qui n'a aucun rapport avec les documents personnels :

    Prompt systeme : contrat 1337 + memoire 260 + instant 184
                     + documents 1562
    prompt 3376 car. -> premier mot 5,1 s

46 % du prompt, et environ deux secondes d'attente A CHAQUE QUESTION, pour
des extraits sans rapport. Aucune erreur, aucun journal — juste une Nova
plus lente qu'elle ne devrait l'etre, sur exactement les questions ou elle
n'a besoin de rien.

LA MESURE QUI MANQUAIT

La distance cosinus etait CALCULEE par pgvector (`embedding <=> vector`)
puis jetee : la requete ne selectionnait que l'`id`. C'est le meme defaut
que l'`avg_logprob` de Whisper — le signal existait, personne ne le lisait.
"""

import pytest

from nova.documents import search as recherche


class FausseConnexion:
    """Une base documentaire simulee, avec des distances choisies."""

    def __init__(self, distances: dict[int, float], mots: list[int]) -> None:
        self.distances = distances
        self.mots = mots
        self.requetes: list[str] = []

    def execute(self, sql: str, params=None):
        self.requetes.append(sql)
        if "SELECT 1 FROM chunks" in sql:
            return _Resultat([{"un": 1}])
        if "distance" in sql:
            ordonnes = sorted(self.distances.items(), key=lambda kv: kv[1])
            return _Resultat([{"id": cid, "distance": d} for cid, d in ordonnes])
        if "tsv @@" in sql:
            return _Resultat([{"id": cid} for cid in self.mots])
        # Detail des morceaux retenus.
        return _Resultat([
            {"id": cid, "heading": None, "content": f"contenu {cid}",
             "title": f"doc {cid}", "source_path": f"/d/{cid}.md"}
            for cid in (params[0] if params else [])
        ])

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Resultat:
    def __init__(self, lignes):
        self.lignes = lignes

    def fetchall(self):
        return self.lignes

    def fetchone(self):
        return self.lignes[0] if self.lignes else None


@pytest.fixture
def base(monkeypatch):
    """Installe une base simulee.

    `toujours` force la vectorisation meme sans mot commun : les tests qui
    portent sur le SEUIL DE DISTANCE ont besoin d'atteindre cette etape,
    alors que le filtre plein texte les arreterait avant. Deux garde-fous
    successifs se testent separement, sinon on ne sait plus lequel a agi.
    """

    def installer(distances, mots=(), toujours=True):
        fausse = FausseConnexion(distances, list(mots))
        monkeypatch.setattr(recherche, "connection", lambda: fausse)
        monkeypatch.setattr(recherche, "embed_one", lambda texte: [0.0] * 8)
        monkeypatch.setattr(
            type(recherche.get_tuning()), "semantique_toujours",
            property(lambda self: toujours), raising=False,
        )
        return fausse

    return installer


# ── Le cas releve en conditions reelles ───────────────────────────────────


def test_une_question_sans_rapport_n_injecte_rien(base):
    """« qu'est-ce que la relativite » face a des documents personnels.

    Les extraits existent, ils sont les plus proches — mais loin. Les
    injecter coutait 46 % du prompt et deux secondes, pour rien.
    """
    base({1: 0.82, 2: 0.88, 3: 0.91})
    assert recherche.search("qu'est-ce que la relativite") == []


def test_une_question_couverte_recoit_ses_extraits(base):
    """Le seuil ne doit pas rendre Nova amnesique sur ses propres documents."""
    base({1: 0.21, 2: 0.33})
    trouves = recherche.search("mon projet Sentinel")
    assert len(trouves) == 2


def test_seuls_les_extraits_assez_proches_passent(base):
    """Un lot mixte : on garde les proches, on jette les autres."""
    base({1: 0.20, 2: 0.50, 3: 0.75, 4: 0.95})
    trouves = recherche.search("une question")
    assert {h.chunk_id for h in trouves} == {1, 2}


# ── Les mots exacts sont une preuve, pas une estimation ───────────────────


def test_un_extrait_trouve_par_les_mots_est_garde_meme_loin(base):
    """Si la question contient litteralement les mots du document, la
    pertinence est ETABLIE, pas estimee.

    C'est le cas des noms propres et des references : « Sentinel » n'a pas de
    voisinage semantique, donc une distance vectorielle mediocre — alors que
    la correspondance est parfaite.
    """
    base({7: 0.93}, mots=[7])
    trouves = recherche.search("Sentinel")
    assert [h.chunk_id for h in trouves] == [7]


def test_sans_correspondance_de_mots_le_seuil_s_applique(base):
    base({7: 0.93}, mots=[], toujours=True)
    assert recherche.search("Sentinel") == []


# ── Les garde-fous existants tiennent toujours ────────────────────────────


def test_un_corpus_vide_ne_charge_pas_le_modele_d_embeddings(monkeypatch):
    """Le garde-fou d'origine : sans documents, ne pas charger bge-m3 (1,2 Go)."""
    appels = {"embed": 0}

    class Vide(FausseConnexion):
        def execute(self, sql, params=None):
            if "SELECT 1 FROM chunks" in sql:
                return _Resultat([])
            return _Resultat([])

    monkeypatch.setattr(recherche, "connection", lambda: Vide({}, []))
    monkeypatch.setattr(
        recherche, "embed_one",
        lambda t: appels.__setitem__("embed", appels["embed"] + 1) or [0.0] * 8,
    )
    assert recherche.search("peu importe") == []
    assert appels["embed"] == 0


def test_le_nombre_d_extraits_reste_borne(base, monkeypatch):
    """Le seuil s'ajoute a la limite, il ne la remplace pas."""
    base({cid: 0.10 for cid in range(1, 21)})
    trouves = recherche.search("une question")
    assert len(trouves) <= recherche.get_tuning().extraits_max


def test_le_seuil_est_configurable():
    """Le bon seuil depend du modele d'embeddings et des documents : il doit
    se regler sans toucher au code."""
    seuil = recherche.get_tuning().distance_max
    assert 0.0 < seuil < 1.0


# ── Les mots d'abord : ils sont gratuits, le sens ne l'est pas ────────────
#
# Vectoriser demande bge-m3, un SECOND modele de 1,2 Go. Sur 8 Go, Ollama ne
# garde pas toujours les deux residents : la vectorisation decharge alors le
# modele de conversation, qu'il faut recharger juste apres. Mesure sur la
# machine reelle, question « qu'est-ce que la relativite » :
#
#     recherche documentaire 2343 ms — pour ZERO extrait retenu
#     premier mot 4,7 s
#
# La recherche plein texte, elle, est un index GIN : quelques millisecondes,
# aucun modele. Elle sert donc de test de pertinence GRATUIT.


def test_sans_mot_commun_on_ne_vectorise_pas(base, monkeypatch):
    """Le cas qui coutait 2,3 secondes pour rien.

    C'est la verification la plus importante du fichier : elle ne porte pas
    sur le resultat — qui etait deja vide — mais sur le fait qu'on n'a PAS
    paye pour l'obtenir.
    """
    base({1: 0.82, 2: 0.88}, mots=[], toujours=False)
    appels = {"embed": 0}
    monkeypatch.setattr(
        recherche, "embed_one",
        lambda t: appels.__setitem__("embed", appels["embed"] + 1) or [0.0] * 8,
    )

    assert recherche.search("qu'est-ce que la relativite") == []
    assert appels["embed"] == 0, "bge-m3 a ete appele alors qu'aucun mot ne correspondait"


def test_un_seul_mot_commun_declenche_le_sens(base, monkeypatch):
    """Un mot suffit : c'est ce qui garde la recherche semantique utile.

    « comment financer le projet » trouve « budget » des que « projet »
    figure quelque part — seule une reformulation TOTALE echappe au filet.
    """
    base({1: 0.30, 5: 0.72}, mots=[5], toujours=False)
    appels = {"embed": 0}
    original = recherche.embed_one
    monkeypatch.setattr(
        recherche, "embed_one",
        lambda t: appels.__setitem__("embed", appels["embed"] + 1) or original(t),
    )

    trouves = recherche.search("comment financer le projet")
    assert appels["embed"] == 1, "le mot commun aurait du declencher la vectorisation"
    # Le chunk 1, trouve seulement par le sens, doit remonter avec le 5.
    assert {h.chunk_id for h in trouves} == {1, 5}


def test_le_reglage_permet_de_toujours_vectoriser(base, monkeypatch):
    """Qui prefere ses documents aux deux secondes doit pouvoir le dire."""
    base({1: 0.30}, mots=[], toujours=True)
    assert len(recherche.search("une reformulation totale")) == 1
