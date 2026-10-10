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
