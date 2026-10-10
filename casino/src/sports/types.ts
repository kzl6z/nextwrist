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
  odds: Partial<Record<Outcome, number>>;
}

export interface FeedResult {
  id: string;
  homeScore: number;
  awayScore: number;
}
