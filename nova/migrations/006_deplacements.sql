-- 006 — D'ou venait chaque fichier que Nova a range.
-- RAPPEL : ce fichier ne doit JAMAIS etre modifie une fois applique.

-- ---------------------------------------------------------------------------
-- ⚠️ SANS CETTE TABLE, DEPLACER SERAIT LA SEULE ACTION VRAIMENT DANGEREUSE.
--
-- Le bareme range « supprimer » dans IRREVERSIBLE et « ecrire dans un fichier
-- existant » dans CONSEQUENT. Deplacer n'est ni l'un ni l'autre sur le
-- papier : le fichier existe toujours, entier, ailleurs.
--
-- En pratique c'est pire que ca en a l'air. On ne retrouve pas ce qu'on ne
-- sait pas nommer : si Nova range trois photos au mauvais endroit, on ne sait
-- ni lesquelles, ni d'ou elles venaient. Le fichier n'est pas detruit, il est
-- PERDU — et la difference n'interesse que les informaticiens.
--
-- Retenir l'origine change la nature de l'action. « remets-les ou ils
-- etaient » redevient possible, et un deplacement redevient ce que le bareme
-- appelle « se defait mal » plutot que « ne se defait pas ».
--
-- C'est le meme raisonnement que la copie gardee avant de remplacer un
-- document : le portillon protege du oui distrait, pas de celui qu'on
-- regrette une seconde apres.
-- ---------------------------------------------------------------------------
CREATE TABLE deplacements (
    id          BIGSERIAL PRIMARY KEY,
    projet_id   BIGINT REFERENCES projets(id) ON DELETE SET NULL,
    -- ⚠️ CE QUI GROUPE UN RANGEMENT, ET POURQUOI L'HORLOGE NE SUFFIT PAS.
    --
    -- « remets-les ou ils etaient » defait LE GESTE qu'on vient de faire, pas
    -- tous les rangements du projet. Il faut donc savoir quelles lignes ont
    -- ete ecrites ensemble.
    --
    -- J'ai d'abord groupe par `fait_le`. C'etait faux : `now()` rend l'heure
    -- de la TRANSACTION, et chaque fichier est enregistre dans la sienne.
    -- Trois photos rangees d'un coup portaient trois instants differents, et
    -- l'annulation n'en ramenait qu'une. Le banc l'a vu ; la relecture, non.
    salve       UUID NOT NULL,
    venait_de   TEXT NOT NULL,
    est_alle_a  TEXT NOT NULL,
    fait_le     TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- ⚠️ ON MARQUE, ON NE SUPPRIME PAS.
    --
    -- Meme regle que la memoire, et pour la meme raison : effacer la trace
    -- d'un retour en arriere empecherait de comprendre, trois jours plus
    -- tard, pourquoi un fichier a bouge deux fois.
    annule      BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX deplacements_projet_idx ON deplacements (projet_id, fait_le DESC);
