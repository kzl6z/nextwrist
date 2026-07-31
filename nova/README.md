# Nova

Assistant personnel local et evolutif. Tout tourne chez toi.

Documentation complete : `../docs/nova/`

## Demarrage

```bash
cp .env.example .env        # puis edite le mot de passe et le modele
ollama pull qwen3:8b        # sur la machine hote
ollama pull bge-m3
make up                     # Postgres + Nova + interface
```

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

## Architecture en une phrase

L'interface croit parler a un modele nomme `nova` ; en realite elle parle a Nova
Core, qui charge ta memoire, cherche dans tes documents, puis interroge Ollama.
Voir `../docs/nova/11-architecture-v1.md`.
