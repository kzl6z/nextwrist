-- 003 — Memory Engine : importance, peremption, mise a jour, oubli.
-- RAPPEL : ce fichier ne doit JAMAIS etre modifie une fois applique.

-- ---------------------------------------------------------------------------
-- IMPORTANCE
--
-- Toute la memoire n'a pas la meme valeur, et le prompt a un budget borne
-- (mesure sur l'iMac M1 : ~3,3 ms par caractere avant le premier mot). Sans
-- niveau, la troncature se fait par DATE : un fait critique vieux de six mois
-- disparait derriere trois preferences notees hier.
--
-- « critique » est reserve a ce qui ne doit jamais tomber du prompt, quel que
-- soit le budget — une contrainte de sante, une regle absolue.
-- ---------------------------------------------------------------------------
CREATE TYPE fact_importance AS ENUM ('basse', 'moyenne', 'haute', 'critique');

ALTER TABLE facts
    ADD COLUMN importance fact_importance NOT NULL DEFAULT 'moyenne',

    -- ------------------------------------------------------------------
    -- PEREMPTION
    --
    -- NULL = durable, et c'est le defaut. Une date = temporaire : « je suis a
    -- Paris jusqu'a vendredi » ne doit pas etre vrai en mars prochain.
    --
    -- On ne SUPPRIME pas a l'echeance : on cesse de s'en servir. Un fait
    -- perime reste lisible dans l'historique, et c'est ce qui distingue
    -- l'oubli de l'effacement.
    -- ------------------------------------------------------------------
    ADD COLUMN expires_at TIMESTAMPTZ,

    -- ------------------------------------------------------------------
    -- USAGE
    --
    -- Quand ce fait a-t-il servi pour la derniere fois ? C'est la seule
    -- mesure honnete de son utilite : un fait jamais rappele en six mois est
    -- un candidat a l'oubli, meme s'il est exact.
    -- ------------------------------------------------------------------
    ADD COLUMN last_used_at TIMESTAMPTZ,
    ADD COLUMN updated_at   TIMESTAMPTZ,

    -- ------------------------------------------------------------------
    -- ETIQUETTES
    --
    -- La categorie repond a « quel genre de fait » ; les etiquettes a « de
    -- quoi ca parle ». Un fait peut concerner deux sujets, une categorie ne
    -- le peut pas.
    -- ------------------------------------------------------------------
    ADD COLUMN tags TEXT[] NOT NULL DEFAULT '{}',

    -- ------------------------------------------------------------------
    -- MISE A JOUR ET CONTRADICTION
    --
    -- ⚠️ ON NE MODIFIE PAS UN FAIT SUR PLACE. ON EN ECRIT UN NOUVEAU.
    --
    -- « Le modele principal est X » puis « c'est maintenant Y » : ecraser la
    -- premiere ligne effacerait le fait qu'un changement a eu lieu — et
    -- l'historique de tes changements d'avis est une information, pas un
    -- dechet. C'est deja la raison pour laquelle `archive` existe plutot
    -- qu'un DELETE.
    --
    -- Le nouveau fait REMPLACE l'ancien, qui passe en 'archived'. Le lien dit
    -- lequel remplace lequel, donc quelle information est la plus recente
    -- quand deux se contredisent.
    -- ------------------------------------------------------------------
    ADD COLUMN supersedes BIGINT REFERENCES facts(id) ON DELETE SET NULL;

-- La balayage de peremption ne doit jamais parcourir toute la table.
CREATE INDEX facts_expiration_idx ON facts (expires_at)
    WHERE expires_at IS NOT NULL AND status <> 'archived';

-- Retrouver ce qu'un fait remplace, et par quoi il a ete remplace.
CREATE INDEX facts_supersedes_idx ON facts (supersedes) WHERE supersedes IS NOT NULL;
