-- 004 — Le contexte actif : de quoi on parle, et depuis quand.
-- RAPPEL : ce fichier ne doit JAMAIS etre modifie une fois applique.

-- ---------------------------------------------------------------------------
-- PROJETS
--
-- ⚠️ UN PROJET N'EST PAS UN ESPACE.
--
-- `espaces/` classe une PHRASE dans un domaine — projet, etude, voyage. C'est
-- un classifieur sans etat : il ne retient rien d'une phrase a l'autre.
--
-- Un projet, lui, DURE. Il a un objectif, des decisions prises, des
-- hypotheses en cours, des taches. C'est ce qui permet de dire « revenons au
-- projet moteur » et que Nova sache ce que cela recouvre.
--
-- Un seul est actif a la fois : « de quoi parlons-nous maintenant » n'a
-- qu'une reponse.
-- ---------------------------------------------------------------------------
CREATE TABLE projets (
    id              BIGSERIAL PRIMARY KEY,
    nom             TEXT NOT NULL UNIQUE,
    objectif        TEXT,
    -- Le domaine, quand `espaces/` sait le dire. Facultatif : un projet peut
    -- n'appartenir a aucun.
    espace          TEXT,
    -- ⚠️ « Je veux garder ca pour moi » DOIT SE TRADUIRE QUELQUE PART.
    --
    -- Sans ce champ, la phrase est entendue et perdue. Avec, elle devient une
    -- propriete du projet, que les outils peuvent lire avant d'ecrire ou
    -- d'envoyer quoi que ce soit.
    confidentialite TEXT NOT NULL DEFAULT 'normal'
                    CHECK (confidentialite IN ('normal', 'personnel')),
    cree_le         TIMESTAMPTZ NOT NULL DEFAULT now(),
    dernier_contact TIMESTAMPTZ NOT NULL DEFAULT now(),
    actif           BOOLEAN NOT NULL DEFAULT false
);

-- Un seul projet actif : la contrainte le dit, plutot que le code.
CREATE UNIQUE INDEX projets_un_seul_actif ON projets ((actif)) WHERE actif;

-- ---------------------------------------------------------------------------
-- CE QUI COMPOSE UN CONTEXTE
--
-- ⚠️ `pourquoi` EST LA COLONNE QUI CHANGE TOUT.
--
-- « Rappelle-moi pourquoi on avait choisi cette approche » ne se repond pas
-- avec une liste de decisions : il faut la RAISON. Une decision sans son
-- motif est une contrainte qu'on subit six mois plus tard sans savoir
-- pourquoi.
-- ---------------------------------------------------------------------------
CREATE TYPE element_genre AS ENUM (
    'decision',    -- « on a decide d'utiliser X »
    'hypothese',   -- « ca chaufferait peut-etre trop »
    'tache',       -- « revoir le refroidissement »
    'entite',      -- « le moteur », « le fichier local » — les REFERENTS
    'question'     -- ce que Nova attend de savoir
);

CREATE TYPE element_statut AS ENUM ('ouvert', 'fait', 'abandonne');

CREATE TABLE elements (
    id            BIGSERIAL PRIMARY KEY,
    projet_id     BIGINT NOT NULL REFERENCES projets(id) ON DELETE CASCADE,
    genre         element_genre  NOT NULL,
    contenu       TEXT NOT NULL,
    pourquoi      TEXT,
    statut        element_statut NOT NULL DEFAULT 'ouvert',
    -- D'ou ca vient : la phrase prononcee. Sert a expliquer, jamais a decider.
    source        TEXT,
    cree_le       TIMESTAMPTZ NOT NULL DEFAULT now(),
    mis_a_jour_le TIMESTAMPTZ
);

CREATE INDEX elements_projet_idx ON elements (projet_id, genre, statut);

-- ---------------------------------------------------------------------------
-- RESUME DE SESSION
--
-- ⚠️ UNE CONVERSATION LONGUE NE TIENT PAS DANS 1200 CARACTERES.
--
-- L'historique est aujourd'hui tronque a un budget, en gardant les messages
-- RECENTS. Au bout d'une heure de travail, tout ce qui a ete etabli au debut
-- a disparu — sans un mot, ce qui est le pire.
--
-- Le resume vit ici plutot qu'en memoire vive : il doit survivre a un
-- redemarrage, comme le reste.
-- ---------------------------------------------------------------------------
CREATE TABLE resumes_de_session (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    projet_id       BIGINT REFERENCES projets(id) ON DELETE SET NULL,
    resume          TEXT NOT NULL,
    -- Jusqu'ou le resume couvre : les messages plus recents restent bruts.
    jusqu_au_message BIGINT,
    cree_le         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX resumes_conversation_idx ON resumes_de_session (conversation_id, cree_le DESC);
