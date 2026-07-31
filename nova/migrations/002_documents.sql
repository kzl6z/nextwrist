-- 002 — Base documentaire : ce que Nova a lu.

CREATE TABLE documents (
    id           BIGSERIAL PRIMARY KEY,
    source_path  TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    -- Empreinte du contenu : permet de re-ingerer un dossier entier sans
    -- retraiter les fichiers inchanges (la vectorisation coute cher).
    content_hash TEXT NOT NULL,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    meta         JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE chunks (
    id          BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal     INT    NOT NULL,               -- position dans le document
    heading     TEXT,                          -- titre de section : sert a citer
    content     TEXT   NOT NULL,
    -- 1024 = dimension de bge-m3. CHANGER DE MODELE D'EMBEDDINGS IMPOSE
    -- UNE NOUVELLE MIGRATION ET UNE RE-VECTORISATION COMPLETE.
    embedding   vector(1024),
    -- Colonne generee : Postgres maintient l'index plein texte tout seul.
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('french', content)) STORED
);

-- HNSW : index de recherche vectorielle approximative. Sans lui la recherche
-- fonctionne quand meme, mais devient lente sans lever la moindre erreur —
-- piege classique.
CREATE INDEX chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_tsv_idx       ON chunks USING gin (tsv);
CREATE INDEX chunks_document_idx  ON chunks (document_id, ordinal);
