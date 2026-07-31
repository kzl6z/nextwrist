"""Faux moteur d'inference, compatible OpenAI.

A quoi ca sert : tester TOUTE la chaine Nova (ingestion, recherche, passerelle,
flux SSE) sans GPU, sans modele telecharge, et en quelques millisecondes.

C'est un outil de developpement, pas un composant de Nova. Il vit donc dans
scripts/ et n'est jamais importe par src/nova/.

  python scripts/fake_ollama.py 11435
  NOVA_OLLAMA_URL=http://localhost:11435/v1 nova ask "..."

Les embeddings sont deterministes (derives d'un hachage des mots) : deux textes
partageant du vocabulaire obtiennent des vecteurs proches. Assez pour verifier
que la plomberie fonctionne — pas pour juger la qualite semantique.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

DIM = 1024


def fake_embedding(text: str) -> list[float]:
    """Sac de mots projete sur DIM dimensions, puis normalise."""
    vector = [0.0] * DIM
    for word in re.findall(r"\w+", text.lower()):
        index = int(hashlib.md5(word.encode()).hexdigest()[:8], 16) % DIM
        vector[index] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.endswith("/models"):
            self._json({"object": "list", "data": [{"id": "fake", "object": "model"}]})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        request = json.loads(self.rfile.read(length) or b"{}")

        if self.path.endswith("/embeddings"):
            inputs = request.get("input", [])
            if isinstance(inputs, str):
                inputs = [inputs]
            self._json(
                {
                    "object": "list",
                    "data": [
                        {"object": "embedding", "index": i, "embedding": fake_embedding(t)}
                        for i, t in enumerate(inputs)
                    ],
                }
            )
            return

        if self.path.endswith("/chat/completions"):
            system = next((m["content"] for m in request["messages"] if m["role"] == "system"), "")
            # La reponse decrit ce que le faux modele a RECU : c'est ce qui rend
            # l'outil utile pour verifier que le contexte est bien assemble.
            reply = (
                f"[faux modele] prompt systeme de {len(system)} caracteres, "
                f"{system.count('- ')} faits, "
                f"{'avec' if 'Extraits de tes documents' in system else 'sans'} extraits."
            )
            if request.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for word in reply.split(" "):
                    chunk = {"choices": [{"index": 0, "delta": {"content": word + " "}}]}
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                    self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")
            else:
                self._json(
                    {"choices": [{"index": 0, "message": {"role": "assistant", "content": reply}}]}
                )
            return

        self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 11435
    print(f"faux Ollama sur http://localhost:{port}/v1", flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
