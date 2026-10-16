export type Outcome = "home" | "draw" | "away";

export interface FeedEvent {
  id: string;
  sport: string;
  league: string;
  home: string;
  away: string;
  startsAt: number;
  /** Clé de la compétition chez le fournisseur (ex. "soccer_epl"). */
  feedKey?: string;
  /** Pronostics proposés : clé (voir markets.ts) → cote et probabilité estimée. */
  selections: Record<string, { price: number; prob: number }>;
}

export interface FeedResult {
  id: string;
  homeScore: number;
  awayScore: number;
}
