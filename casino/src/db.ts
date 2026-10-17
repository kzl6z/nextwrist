import { Database } from "bun:sqlite";

export const db = new Database(process.env.DB_PATH ?? "casino.sqlite", { create: true });

db.exec("PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;");

db.exec(`
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
  last_bonus_at INTEGER,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  expires_at INTEGER NOT NULL
);

-- Grand livre : chaque mouvement de solde est tracé ici.
CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  amount INTEGER NOT NULL,
  balance_after INTEGER NOT NULL,
  kind TEXT NOT NULL,
  ref TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS transactions_user ON transactions(user_id, id);

CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  sport TEXT NOT NULL,
  league TEXT NOT NULL,
  home TEXT NOT NULL,
  away TEXT NOT NULL,
  starts_at INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'scheduled', -- scheduled | finished | cancelled
  home_score INTEGER,
  away_score INTEGER,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS events_status ON events(status, starts_at);

CREATE TABLE IF NOT EXISTS odds (
  event_id TEXT NOT NULL REFERENCES events(id),
  outcome TEXT NOT NULL, -- home | draw | away
  price REAL NOT NULL,
  PRIMARY KEY (event_id, outcome)
);

CREATE TABLE IF NOT EXISTS bets (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  stake INTEGER NOT NULL,
  total_odds REAL NOT NULL,
  potential_win INTEGER NOT NULL,
  payout INTEGER,
  status TEXT NOT NULL DEFAULT 'open', -- open | won | lost | void
  created_at INTEGER NOT NULL,
  settled_at INTEGER
);
CREATE INDEX IF NOT EXISTS bets_user ON bets(user_id, id);

CREATE TABLE IF NOT EXISTS bet_legs (
  bet_id INTEGER NOT NULL REFERENCES bets(id),
  event_id TEXT NOT NULL REFERENCES events(id),
  outcome TEXT NOT NULL,
  price REAL NOT NULL,
  result TEXT NOT NULL DEFAULT 'pending' -- pending | won | lost | void
);
CREATE INDEX IF NOT EXISTS bet_legs_event ON bet_legs(event_id, result);

CREATE TABLE IF NOT EXISTS blackjack_hands (
  user_id INTEGER PRIMARY KEY REFERENCES users(id),
  state TEXT NOT NULL
);
`);

db.exec(`
CREATE TABLE IF NOT EXISTS crash_rounds (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  bet INTEGER NOT NULL,
  crash_point REAL NOT NULL,
  auto_cashout REAL,
  started_at INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'playing', -- playing | won | lost
  cashout_at REAL,
  payout INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS crash_rounds_user ON crash_rounds(user_id, id);
`);

const hasColumn = (table: string, column: string) =>
  !!db.query(`SELECT 1 FROM pragma_table_info('${table}') WHERE name = ?`).get(column);
const addColumn = (table: string, column: string, def: string) => {
  if (!hasColumn(table, column)) db.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${def}`);
};

// Migration : clé du flux (ex. "soccer_epl") pour savoir quels scores demander.
addColumn("events", "feed_key", "TEXT");
// Direct et sports virtuels : horloge, détails (frise, sets…), état de simulation.
addColumn("events", "clock", "TEXT");
addColumn("events", "detail", "TEXT");
addColumn("events", "sim", "TEXT");
addColumn("events", "virtual", "INTEGER NOT NULL DEFAULT 0");
addColumn("events", "suspended_until", "INTEGER");
// Flux réel : fraîcheur des cotes (direct) et marchés supplémentaires mis en cache.
addColumn("events", "odds_at", "INTEGER");
addColumn("events", "deep", "TEXT");
addColumn("events", "deep_at", "INTEGER");
// Direct des vrais matchs : durée de validité de la dernière mise à jour de la source.
addColumn("events", "live_ttl", "INTEGER");
// Paris en direct : mise à jour de la source sur laquelle la cote était basée (voir engine.ts).
addColumn("bet_legs", "seen_at", "INTEGER");

db.exec(`
-- Notre propre classement des équipes (cotes maison avant-match), voir sports/ratings.ts.
CREATE TABLE IF NOT EXISTS team_ratings (
  team TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  attack REAL NOT NULL DEFAULT 0,
  defense REAL NOT NULL DEFAULT 0,
  games INTEGER NOT NULL DEFAULT 0,
  league TEXT,
  updated_at INTEGER NOT NULL
);
-- Matchs déjà pris en compte dans le classement.
CREATE TABLE IF NOT EXISTS rated_matches (
  id TEXT PRIMARY KEY,
  played_at INTEGER NOT NULL
);
-- Correspondance entre les matchs d'un fournisseur et nos matchs.
CREATE TABLE IF NOT EXISTS ext_links (
  provider TEXT NOT NULL,
  ext_id TEXT NOT NULL,
  event_id TEXT NOT NULL REFERENCES events(id),
  PRIMARY KEY (provider, ext_id)
);
-- Petits réglages persistants (quota du jour, amorçage déjà fait…).
CREATE TABLE IF NOT EXISTS kv (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL
);
`);

db.exec(`
-- Tous les pronostics d'un match (clé décrite dans sports/markets.ts).
-- price NULL = pronostic fermé ; prob = probabilité actuelle (sert au cash out).
CREATE TABLE IF NOT EXISTS selections (
  event_id TEXT NOT NULL REFERENCES events(id),
  key TEXT NOT NULL,
  price REAL,
  prob REAL NOT NULL,
  PRIMARY KEY (event_id, key)
);

-- Parties de casino (historique et fil des gains).
CREATE TABLE IF NOT EXISTS game_rounds (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  game TEXT NOT NULL,
  bet INTEGER NOT NULL,
  payout INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS game_rounds_user ON game_rounds(user_id, id);
CREATE INDEX IF NOT EXISTS game_rounds_recent ON game_rounds(id, payout);

-- Parties en plusieurs étapes (Mines, Hi-Lo, Tower, Pile ou face, Video poker).
CREATE TABLE IF NOT EXISTS game_sessions (
  user_id INTEGER NOT NULL REFERENCES users(id),
  game TEXT NOT NULL,
  state TEXT NOT NULL,
  PRIMARY KEY (user_id, game)
);
`);

// Migration des anciennes cotes 1N2 vers la table des pronostics.
if (!db.query("SELECT 1 FROM selections LIMIT 1").get() && db.query("SELECT 1 FROM odds LIMIT 1").get()) {
  db.exec(`
    INSERT INTO selections (event_id, key, price, prob)
    SELECT o.event_id, o.outcome, o.price,
      (1.0 / o.price) / (SELECT SUM(1.0 / o2.price) FROM odds o2 WHERE o2.event_id = o.event_id)
    FROM odds o`);
}
// Les anciens matchs de démo n'ont pas d'état de simulation : annulés (paris remboursés).
db.query(
  "UPDATE events SET status = 'cancelled', updated_at = ? WHERE id LIKE 'demo-%' AND status = 'scheduled' AND sim IS NULL",
).run(Date.now());
