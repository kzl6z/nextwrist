# Nova

Assistant personnel local et evolutif. Tout tourne chez toi.

Documentation complete : `../docs/nova/`

## Demarrage

```bash
cp .env.example .env        # puis edite le mot de passe et le modele
ollama create nova -f Modelfile   # le modele du projet, construit localement
ollama pull bge-m3
make up                     # Postgres + Nova + interface
```

> `nova` est bati sur `huihui_ai/qwen3.5-abliterated:4b` (3,3 Go) et ne
> s'obtient **pas** par `ollama pull` — il se construit. Sur une machine ou tu
> ne veux pas le construire : `NOVA_CHAT_MODEL=llama3.2:3b` et
> `ollama pull llama3.2:3b`. Le poids doit tenir dans ~45 % de la RAM, sinon la
> machine pagine sans qu'aucune erreur ne le dise.

Interface : http://localhost:3000 — le modele `nova` apparait dans la liste.

## Commandes utiles

```bash
uv run nova db migrate           # TOUJOURS en premier : cree le schema
uv run nova health               # base + moteur d'inference
uv run pytest -q                 # apres migrate, sinon les tests d'integration sautent
uv run nova facts add "..."      # ajoute un fait
uv run nova ingest ./data/documents
uv run nova search "ma question"
uv run nova ask "ma question"    # sans interface
```

## Parler a Nova (optionnel)

```bash
uv pip install -e ".[voice]"
```

Ajoute la transcription locale (Whisper) sur `/v1/audio/transcriptions`.
Sans clé, sans quota, sans réseau : la voix ne quitte pas la machine.
Le premier appel télécharge le modèle (~500 Mo).

## Architecture en une phrase

L'interface croit parler a un modele nomme `nova` ; en realite elle parle a Nova
Core, qui charge ta memoire, cherche dans tes documents, puis interroge Ollama.
Voir `../docs/nova/11-architecture-v1.md`.
