// Notre propre classement des équipes de football, pour coter les matchs qu'aucun bookmaker
// ne couvre. Chaque équipe a une force offensive et une force défensive, apprises match après
// match sur les résultats (modèle de Poisson mis à jour en ligne) :
//
//   buts attendus de A contre B = moyenne × exp(attaque A − défense B [+ avantage du terrain])
//
// Les forces sont relatives au championnat de l'équipe : on n'apprend et on ne cote que les
// matchs de championnat entre deux équipes du même championnat (pas les coupes, où deux
// divisions se rencontrent et où les forces ne sont pas comparables).
import { db } from "../db";

/** Buts marqués par équipe et par match, en moyenne. */
export const BASE_GOALS = 1.3;
/** Avantage du terrain (échelle logarithmique : +25 % de buts environ). */
export const HOME_ADV = 0.22;
const CLAMP = 2.2;

export interface Rating {
  attack: number;
  defense: number;
  games: number;
  /** Championnat de l'équipe (dernier championnat joué). */
  league: string | null;
}

const NEW_TEAM: Rating = { attack: 0, defense: 0, games: 0, league: null };

/** Pas d'apprentissage : rapide au début, plus stable ensuite. */
const rate = (games: number) => (games < 6 ? 0.12 : games < 20 ? 0.07 : 0.045);
const clamp = (x: number) => Math.max(-CLAMP, Math.min(CLAMP, x));

export function expectedGoals(home: Rating, away: Rating, neutral = false): [number, number] {
  return [
    BASE_GOALS * Math.exp(home.attack - away.defense + (neutral ? 0 : HOME_ADV)),
    BASE_GOALS * Math.exp(away.attack - home.defense),
  ];
}

/** Nouvelles forces après un match (descente de gradient sur la vraisemblance de Poisson). */
export function update(home: Rating, away: Rating, gh: number, ga: number): [Rating, Rating] {
  const [lh, la] = expectedGoals(home, away);
  const rh = gh - lh;
  const ra = ga - la;
  // Les écarts extrêmes (7-0) ne doivent pas tout emporter.
  const ch = Math.max(-3, Math.min(3, rh));
  const ca = Math.max(-3, Math.min(3, ra));
  const kh = rate(home.games);
  const ka = rate(away.games);
  return [
    { attack: clamp(home.attack + kh * ch * 0.5), defense: clamp(home.defense - kh * ca * 0.5), games: home.games + 1, league: home.league },
    { attack: clamp(away.attack + ka * ca * 0.5), defense: clamp(away.defense - ka * ch * 0.5), games: away.games + 1, league: away.league },
  ];
}

/** Manche de championnat (et non de coupe, de barrage ou de match amical). */
export const isLeagueRound = (round: string | null | undefined) =>
  !!round && /regular season|apertura|clausura|league stage|matchday|journée/i.test(round) && !/relegation|play-?off|final/i.test(round);

/* ---------- Stockage ---------- */
export function getRating(team: string): Rating | null {
  const r = db.query("SELECT attack, defense, games, league FROM team_ratings WHERE team = ?").get(team) as Rating | null;
  return r;
}

export interface PlayedMatch {
  id: string;
  playedAt: number;
  league: string;
  round: string | null;
  home: { key: string; name: string };
  away: { key: string; name: string };
  goals: [number, number];
}

/** Apprend des matchs terminés (dans l'ordre chronologique). Renvoie le nombre de matchs appris. */
export const learn = db.transaction((matches: PlayedMatch[]) => {
  const seen = db.query("SELECT 1 FROM rated_matches WHERE id = ?");
  const mark = db.query("INSERT INTO rated_matches (id, played_at) VALUES (?, ?)");
  const save = db.query(
    `INSERT INTO team_ratings (team, name, attack, defense, games, league, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(team) DO UPDATE SET name = excluded.name, attack = excluded.attack, defense = excluded.defense,
       games = excluded.games, league = excluded.league, updated_at = excluded.updated_at`,
  );
  let n = 0;
  for (const m of [...matches].sort((a, b) => a.playedAt - b.playedAt)) {
    if (!isLeagueRound(m.round) || seen.get(m.id)) continue;
    const h = getRating(m.home.key) ?? NEW_TEAM;
    const a = getRating(m.away.key) ?? NEW_TEAM;
    const [nh, na] = update(h, a, m.goals[0], m.goals[1]);
    const now = Date.now();
    save.run(m.home.key, m.home.name, nh.attack, nh.defense, nh.games, m.league, now);
    save.run(m.away.key, m.away.name, na.attack, na.defense, na.games, m.league, now);
    mark.run(m.id, m.playedAt);
    n++;
  }
  return n;
});

/**
 * Buts attendus pour un match de championnat, ou null si l'une des équipes n'est pas encore assez
 * connue, ou si elles ne jouent pas dans le même championnat.
 */
export function rateFixture(home: string, away: string, league: string, round: string | null, minGames: number): [number, number] | null {
  if (!isLeagueRound(round)) return null;
  const h = getRating(home);
  const a = getRating(away);
  if (!h || !a || h.games < minGames || a.games < minGames) return null;
  if (h.league !== league || a.league !== league) return null;
  return expectedGoals(h, a);
}
