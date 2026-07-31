-- 001 — Socle : ce que Nova sait de toi, et ce que vous vous etes dit.
-- RAPPEL : ce fichier ne doit JAMAIS etre modifie une fois applique.

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- MEMOIRE SEMANTIQUE : les faits stables te concernant.
-- Petite table (quelques centaines de lignes), injectee TELLE QUELLE dans le
-- prompt systeme. C'est ce qui fait que Nova te connait des le premier mot.
-- ---------------------------------------------------------------------------
CREATE TYPE fact_status AS ENUM ('proposed', 'confirmed', 'archived');
CREATE TYPE fact_origin AS ENUM ('user', 'inferred');

CREATE TABLE facts (
    id          BIGSERIAL PRIMARY KEY,
    category    TEXT        NOT NULL,          -- profil | projet | preference | contrainte | objectif
    content     TEXT        NOT NULL,
    status      fact_status NOT NULL DEFAULT 'proposed',
    -- origin distingue ce que TU as declare de ce que le modele a DEDUIT.
    -- Les melanger est la premiere cause de pourrissement de la memoire (risque R5).
    origin      fact_origin NOT NULL DEFAULT 'user',
    confidence  REAL        NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    source      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ
);

CREATE INDEX facts_active_idx ON facts (status, category) WHERE status <> 'archived';

-- ---------------------------------------------------------------------------
-- JOURNAL DES ECHANGES
-- L'interface garde deja un historique — mais l'interface est jetable.
-- La memoire durable doit vivre ICI. C'est cette table que la consolidation
-- nocturne (V0.3) lira pour produire les resumes.
-- ---------------------------------------------------------------------------
CREATE TABLE conversations (
    id              BIGSERIAL PRIMARY KEY,
    external_id     TEXT UNIQUE,               -- identifiant fourni par l'interface
    title           TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_message_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE messages (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT   NOT NULL CHECK (role IN ('system', 'user', 'assistant')),
    content         TEXT   NOT NULL,
    model           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    meta            JSONB  NOT NULL DEFAULT '{}'::jsonb   -- sources citees, duree, etc.
);

CREATE INDEX messages_conversation_idx ON messages (conversation_id, created_at);
