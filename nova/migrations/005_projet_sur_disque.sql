-- 005 — Le projet a une place sur le disque, et Nova s'en souvient.
-- RAPPEL : ce fichier ne doit JAMAIS etre modifie une fois applique.

-- ---------------------------------------------------------------------------
-- ⚠️ SANS CES DEUX COLONNES, NOVA REPROPOSERAIT LE MEME DOSSIER SANS FIN.
--
-- Elle propose d'ecrire le projet sur le disque quand la conversation en a
-- dit assez. Cette proposition arrive derriere une phrase qu'elle prononce
-- deja — « Decision notee : … » — et elle ne doit arriver QU'UNE FOIS.
--
-- Sans trace, la question reviendrait a chaque decision notee. Une
-- proposition qu'on a refusee et qui revient trente secondes plus tard n'est
-- plus une proposition : c'est un harcelement, et l'on finit par ne plus rien
-- dicter.
--
-- Les deux colonnes repondent a deux questions differentes, et il faut les
-- deux :
--
--     dossier              ou est-ce, quand ca existe
--     document_propose_le  a-t-on DEJA pose la question
--
-- Un refus laisse la seconde remplie et la premiere vide. C'est exactement
-- l'etat « je lui ai demande, il a dit non » — qu'aucune des deux ne dit
-- toute seule.
-- ---------------------------------------------------------------------------
ALTER TABLE projets ADD COLUMN dossier             TEXT;
ALTER TABLE projets ADD COLUMN document_propose_le TIMESTAMPTZ;
