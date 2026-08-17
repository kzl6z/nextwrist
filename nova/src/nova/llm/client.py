"""Client vers le moteur d'inference.

Ce module est le SEUL de tout Nova qui sait qu'Ollama existe. Le reste du code
ne connait que `LLMClient`. Le jour ou tu passes a vLLM ou llama.cpp, tu ne
modifies que ce fichier — c'est la premiere des deux frontieres stables decrites
dans docs/nova/01-architecture.md.

On parle a Ollama via son API compatible OpenAI (/v1) et non son API native :
c'est le standard de fait, donc ce qui garantit l'interchangeabilite.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator

import httpx

from nova.logging_setup import get_logger
from nova.settings import get_settings

log = get_logger(__name__)

Message = dict[str, str]  # {"role": "user", "content": "..."}

OPEN, CLOSE = "<think>", "</think>"


class FinDeJson:
    """Detecte la fermeture du premier objet JSON de premier niveau.

    POURQUOI CETTE CLASSE EXISTE

    Le decodage contraint garantit que la sortie EST du JSON valide. Il ne
    garantit pas que le moteur s'arrete une fois l'objet ecrit : Ollama
    continue d'emettre du remplissage jusqu'au plafond de jetons. Mesure sur
    la machine reelle, pour une reponse dont le texte utile faisait six
    caracteres (« samedi ») :

        max_tokens 300  ->  24 431 ms

    Presque tout ce temps partait apres l'accolade fermante. On coupe donc le
    flux nous-memes : fermer la connexion interrompt la generation cote
    moteur, et la reponse arrive des qu'elle est complete plutot qu'a
    l'epuisement du quota.

    L'analyse suit les regles du JSON — une accolade dans une chaine de
    caracteres ne compte pas, et un guillemet echappe ne ferme pas la chaine.
    """

    def __init__(self) -> None:
        self.profondeur = 0
        self.dans_chaine = False
        self.echappe = False
        self.commence = False
        self.termine = False

    def feed(self, morceau: str) -> str:
        """Renvoie la portion a conserver ; positionne `termine` a la fermeture."""
        if self.termine:
            return ""
        for i, caractere in enumerate(morceau):
            if self.dans_chaine:
                if self.echappe:
                    self.echappe = False
                elif caractere == "\\":
                    self.echappe = True
                elif caractere == '"':
                    self.dans_chaine = False
                continue
            if caractere == '"':
                self.dans_chaine = True
            elif caractere in "{[":
                self.profondeur += 1
                self.commence = True
            elif caractere in "}]":
                self.profondeur -= 1
                if self.commence and self.profondeur <= 0:
                    self.termine = True
                    return morceau[: i + 1]
        return morceau


class ThinkFilter:
    """Retire les blocs <think>...</think> d'un flux de texte.

    Pourquoi c'est necessaire : certains modeles "raisonneurs" ecrivent leur
    reflexion directement dans la reponse. Constate en conditions reelles avec
    qwen3:4b — 2600 caracteres de raisonnement pour repondre "Bonjour !".

    Ce filtre ne rend pas le modele plus rapide : le temps est deja depense.
    Il evite simplement d'infliger le monologue a l'utilisateur. Le vrai
    remede est de choisir un modele sans phase de reflexion (scripts/bench_models.py).

    La difficulte : en flux, une balise peut etre coupee entre deux fragments.
    On conserve donc une petite queue tampon plutot que de tester chaque fragment.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._inside = False

    def feed(self, piece: str) -> str:
        self._buffer += piece
        out: list[str] = []
        while True:
            if not self._inside:
                index = self._buffer.find(OPEN)
                if index == -1:
                    # On garde de quoi reconstituer une balise coupee en deux.
                    keep = max(0, len(self._buffer) - len(OPEN) + 1)
                    out.append(self._buffer[:keep])
                    self._buffer = self._buffer[keep:]
                    break
                out.append(self._buffer[:index])
                self._buffer = self._buffer[index + len(OPEN) :]
                self._inside = True
            else:
                index = self._buffer.find(CLOSE)
                if index == -1:
                    keep = max(0, len(self._buffer) - len(CLOSE) + 1)
                    self._buffer = self._buffer[keep:]  # le raisonnement est jete
                    break
                self._buffer = self._buffer[index + len(CLOSE) :]
                self._inside = False
        return "".join(out)

    def flush(self) -> str:
        """Ce qui reste en tampon a la fin du flux."""
        return "" if self._inside else self._buffer


class LLMError(RuntimeError):
    """Erreur remontee par le moteur d'inference, presentable a l'utilisateur."""


def _explique(exc: httpx.HTTPError, modele: str) -> str:
    """Traduit une erreur HTTP en message actionnable.

    Un message d'erreur doit dire QUOI FAIRE, pas seulement ce qui a echoue.
    `Client error '404 Not Found'` est exact et inutile : il n'indique ni la
    cause (le modele n'est pas installe) ni le remede (`ollama pull`).

    ⚠️ ET LE REMEDE AFFICHE POUVAIT ETRE FAUX — SUR LE MODELE DU PROJET.

    Il disait « ollama pull {modele} », toujours. Or `nova` ne se pull pas :
    il se CONSTRUIT depuis un Modelfile. `ollama pull nova` echoue avec une
    erreur de depot introuvable, c'est-a-dire qu'on envoyait quelqu'un dont
    le modele manquait vers une commande qui ne pouvait pas le lui rendre.

    Un remede faux coute plus cher qu'une absence de remede : on le suit, il
    echoue, et on cherche desormais deux pannes au lieu d'une. Les modeles
    construits localement n'ont pas de « / » dans leur nom (un modele du
    catalogue s'ecrit `huihui_ai/qwen3.5-abliterated:4b`) — ca ne prouve
    rien, donc on ne devine pas : on donne les DEUX chemins.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 404:
            return (
                f"le modele « {modele} » n'existe pas dans Ollama.\n"
                f"S'il vient du catalogue :  ollama pull {modele}\n"
                f"S'il est construit ici    :  ollama create {modele} -f Modelfile\n"
                f"Ou change NOVA_CHAT_MODEL dans .env — modeles disponibles : ollama list"
            )
        return f"le moteur a repondu {exc.response.status_code}."
    if isinstance(exc, httpx.ConnectError):
        return (
            "impossible de joindre Ollama.\n"
            "Verifie que l'application est lancee (icone dans la barre de menus)."
        )
    if isinstance(exc, httpx.ReadTimeout):
        return "le moteur n'a pas repondu a temps (modele trop lourd pour la machine ?)."
    return str(exc)


#: Delai d'ETABLISSEMENT de la connexion, en secondes.
#:
#: CONNECTER N'EST PAS REPONDRE, ET LES CONFONDRE COUTE CINQ MINUTES
#:
#: Un service local repond a la poignee de main en quelques millisecondes, ou
#: n'est pas la. Il n'existe aucun cas ou etablir une connexion vers
#: `localhost` demande trois secondes. En revanche, ECRIRE une reponse peut
#: legitimement en demander soixante.
#:
#: Un delai unique pour les deux oblige a choisir le plus grand — et donc a
#: attendre une minute entiere pour apprendre qu'un service est eteint. En les
#: separant, l'absence se constate en deux secondes et la lenteur reste
#: tolerée. C'est la meme distinction que « la porte est fermee » et « on met
#: du temps a m'ouvrir » : le second demande de la patience, le premier non.
CONNEXION_S = 2.0

#: Delai d'ECRITURE de la requete. Court : le corps tient en quelques kilo-octets.
ENVOI_S = 10.0


def _delais(lecture: float) -> httpx.Timeout:
    """Les quatre delais d'un appel, separes.

    `lecture` est le seul qui doive etre genereux : c'est le temps que le
    modele passe a produire. Les trois autres mesurent de la plomberie, et une
    plomberie qui tarde est une plomberie cassee.
    """
    return httpx.Timeout(connect=CONNEXION_S, read=lecture, write=ENVOI_S, pool=CONNEXION_S)


class LLMClient:
    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.model = model or settings.chat_model
        self.timeout = settings.request_timeout
        self.default_temperature = settings.temperature
        self.max_tokens = settings.max_tokens

    # -- appel simple -------------------------------------------------------
    def _payload(
        self,
        messages: list[Message],
        temperature: float | None,
        max_tokens: int | None,
        json_mode: bool,
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.default_temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.max_tokens,
            # ⚠️ Envoye, mais SANS GARANTIE — et c'est un piege coûteux.
            #
            # `keep_alive` est une option de l'API NATIVE d'Ollama. Ce point
            # d'entree est le point d'entree OpenAI-compatible : les champs
            # qu'il ne connait pas sont ignores en silence. On le laisse parce
            # qu'il ne coute rien et qu'il servira le jour ou Ollama l'y
            # acceptera, mais il ne faut pas compter dessus.
            #
            # Le seul reglage qui fasse foi est cote SERVEUR :
            #
            #     launchctl setenv OLLAMA_KEEP_ALIVE -1
            #
            # Sans lui, le modele est decharge et RECHARGE DEPUIS LE DISQUE
            # avant la reponse. Mesure sur la machine reelle : un cout fixe de
            # 21 secondes, identique pour un prompt de 880 et de 6573
            # caracteres — ce qui l'a longtemps fait passer pour de la lecture.
            "keep_alive": "30m",
        }
        # ── COUPER LE RAISONNEMENT — ET LE FAIRE AVEC LE BON CHAMP ────────
        #
        # ⚠️ `/no_think` NE SUFFIT PLUS, ET SON ECHEC EST INVISIBLE.
        #
        # C'est un interrupteur de Qwen 3, glisse dans le prompt systeme. Sur
        # la base Qwen 3.5 du modele `nova`, il est purement ignore : releve en
        # conditions reelles, le modele raisonnait alors que `/no_think` etait
        # le message systeme ENTIER.
        #
        # Ce qui rendait la panne indechiffrable, c'est ou passe ce
        # raisonnement. Ollama ne l'ecrit PAS dans `content` (donc `ThinkFilter`
        # ne le voit jamais) : il le range dans un champ `reasoning` separe.
        # Le flux ressemblait donc a ceci, du premier fragment au dernier :
        #
        #     "delta":{"content":"","reasoning":"The"}
        #     "delta":{"content":"","reasoning":" user"}
        #
        # Les 500 jetons du plafond partaient integralement dans `reasoning`,
        # `content` restait vide, et Nova rendait « Aucune reponse » apres
        # 39 secondes de travail bien reel.
        #
        # Trois interrupteurs ont ete essayes sur la machine, contre le vrai
        # Ollama. Un seul marche sur ce point d'entree :
        #
        #     /v1  + "think": false              -> ignore, content vide
        #     /v1  + "reasoning_effort": "none"  -> ✅ content rempli des le 1er
        #     /api/chat + "think": false         -> marche, mais API NATIVE
        #
        # On prend le deuxieme. Le troisieme marche aussi et couterait la
        # frontiere du projet : `/v1` est le seul endroit qui sait qu'Ollama
        # existe, et en sortir pour un reglage rendrait le moteur non
        # remplacable.
        #
        # `reasoning_effort` est un champ OpenAI standard. Un moteur qui ne le
        # connait pas l'ignore, comme il ignore deja `keep_alive` et `format`.
        if not get_settings().thinking:
            payload["reasoning_effort"] = "none"
        if json_mode:
            # Sortie JSON garantie par le moteur : il contraint le decodage token
            # par token, ce qui rend une sortie invalide IMPOSSIBLE plutot
            # qu'improbable. Sans cela, un petit modele produit regulierement du
            # JSON casse — et une application qui fait JSON.parse() se replie
            # silencieusement sur autre chose, sans que personne ne le voie.
            payload["response_format"] = {"type": "json_object"}
            payload["format"] = "json"  # champ natif Ollama, ignore ailleurs
        return payload

    def chat(self, messages: list[Message], *, temperature: float | None = None) -> str:
        """Reponse complete, en un bloc. Pour la CLI et les traitements de fond."""
        payload = self._payload(messages, temperature, None, False) | {"stream": False}
        try:
            with httpx.Client(timeout=_delais(self.timeout)) as client:
                resp = client.post(f"{self.base_url}/chat/completions", json=payload)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except httpx.HTTPError as exc:
            raise LLMError(_explique(exc, self.model)) from exc

    # -- appel en flux ------------------------------------------------------
    def stream(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> Iterator[str]:
        """Reponse morceau par morceau, pour l'interface.

        Le flux n'est pas cosmetique : sur un modele local, la premiere phrase
        arrive en ~1 s alors que la reponse complete peut prendre 30 s. C'est la
        difference entre "ca repond" et "c'est fige".

        Format SSE renvoye par l'API : des lignes `data: {json}`, terminees par
        `data: [DONE]`.
        """
        # keep_alive garde le modele en memoire entre deux questions ; sans lui,
        # chaque appel rechargerait plusieurs Go depuis le disque.
        payload = self._payload(messages, temperature, max_tokens, json_mode) | {"stream": True}
        try:
            with httpx.Client(timeout=_delais(self.timeout)) as client:
                with client.stream(
                    "POST", f"{self.base_url}/chat/completions", json=payload
                ) as resp:
                    resp.raise_for_status()
                    filtre = ThinkFilter()
                    # En mode contraint, on coupe des que l'objet est ferme :
                    # tout ce qui suit est du remplissage jusqu'au plafond.
                    fin = FinDeJson() if json_mode else None
                    # ── DE QUOI EXPLIQUER UN SILENCE ─────────────────────
                    #
                    # ⚠️ CE COMPTEUR EXISTE PARCE QUE NOVA A DEJA RENDU
                    # « Aucune reponse » APRES 39 SECONDES DE TRAVAIL REEL.
                    #
                    # Le modele raisonnait, Ollama envoyait ce raisonnement
                    # dans un champ `reasoning` separe, et cette boucle ne lit
                    # que `content`. Elle recevait donc des milliers de
                    # caracteres, n'en gardait aucun, et se terminait
                    # normalement — sans erreur, sans avertissement, sans la
                    # moindre trace de ce qui venait de se passer.
                    #
                    # C'est le pire mode de panne possible : celui ou tout le
                    # monde a l'air d'avoir bien fait son travail. On a cherche
                    # du cote du modele, du prompt et de la machine avant de
                    # penser a regarder le flux brut.
                    #
                    # Compter ce qu'on jette coute deux entiers, et transforme
                    # une enquete en une phrase.
                    vus = 0
                    raisonnes = 0
                    for line in resp.iter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            break
                        try:
                            delta = json.loads(data)["choices"][0]["delta"]
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue  # fragment malforme : on ignore, on ne casse pas
                        # Champ separe, jamais present dans `content` : c'est
                        # tout l'interet de le compter ici plutot que d'esperer
                        # que `ThinkFilter` le voie passer.
                        raisonnes += len(delta.get("reasoning") or "")
                        if content := delta.get("content"):
                            vus += len(content)
                            visible = filtre.feed(content)
                            if fin is not None:
                                visible = fin.feed(visible)
                                if visible:
                                    yield visible
                                if fin.termine:
                                    log.info("Objet JSON complet : flux interrompu.")
                                    return
                            elif visible:
                                yield visible
                    if reste := filtre.flush():
                        yield reste
                    # Un silence complet n'est jamais normal. S'il y avait du
                    # raisonnement derriere, on nomme la cause ET le remede —
                    # c'est exactement ce qui manquait le jour ou c'est arrive.
                    if vus == 0 and raisonnes > 0:
                        raise LLMError(
                            f"le modele « {self.model} » a produit "
                            f"{raisonnes} caracteres de RAISONNEMENT et aucune reponse.\n"
                            f"Il a epuise son plafond de jetons a reflechir avant "
                            f"d'ecrire le premier mot.\n"
                            f"Remede : verifie que NOVA_THINKING reste faux "
                            f"(Nova envoie alors reasoning_effort=none),\n"
                            f"ou releve NOVA_MAX_TOKENS si tu veux garder le raisonnement."
                        )
                    if vus == 0:
                        log.warning(
                            "Le modele %s n'a produit aucun caractere. Ni reponse, "
                            "ni raisonnement : le plafond, le prompt ou le modele.",
                            self.model,
                        )
        except httpx.HTTPError as exc:
            raise LLMError(_explique(exc, self.model)) from exc

    def chauffer(self) -> float | None:
        """Force le modele a etre resident. Retourne le temps que ca a pris.

        POURQUOI C'EST NECESSAIRE

        Un modele decharge doit etre relu depuis le disque avant de repondre.
        Mesure sur l'iMac M1 : un cout FIXE de 21 secondes, identique pour un
        prompt de 880 et de 6573 caracteres. C'est cette independance a la
        taille de l'entree qui trahit un chargement — un vrai temps de lecture
        aurait ete sept fois moindre sur le petit prompt.

        Ollama decharge par defaut apres cinq minutes d'inactivite, et plus tot
        encore quand la machine manque de memoire. Le champ `keep_alive` de
        l'API OpenAI-compatible est ignore en silence.

        On ne demande donc rien a personne : on entretient nous-memes. Un seul
        jeton suffit a remettre le compteur a zero, et ca coute quelques
        centaines de millisecondes.
        """
        depart = time.perf_counter()
        try:
            with httpx.Client(timeout=_delais(180.0)) as client:
                reponse = client.post(
                    f"{self.base_url}/chat/completions",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": "ok"}],
                        "max_tokens": 1,
                        "keep_alive": "30m",
                    },
                )
                reponse.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("Modele %s : mise en chauffe impossible (%s)", self.model, exc)
            return None
        return time.perf_counter() - depart

    def health(self) -> bool:
        """Le moteur repond-il ? Utilise par /health."""
        try:
            with httpx.Client(timeout=_delais(5.0)) as client:
                return client.get(f"{self.base_url}/models").status_code == 200
        except httpx.HTTPError:
            return False
