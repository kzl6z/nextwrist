// Client API-Football (api-sports.io), offre gratuite : 100 requêtes par jour, 10 par minute.
// Une requête suffit pour le calendrier mondial d'une journée, une autre pour tous les matchs en cours.

export const AF_BASE = "https://v3.football.api-sports.io";

/** Statuts du fournisseur. */
export const AF_LIVE = new Set(["1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"]);
export const AF_FINISHED = new Set(["FT", "AET", "PEN"]);
/** Match reporté, annulé, arrêté, sur tapis vert ou par forfait : paris remboursés. */
export const AF_VOID = new Set(["PST", "CANC", "ABD", "AWD", "WO"]);
export const AF_UPCOMING = new Set(["NS", "TBD"]);

export interface AfFixture {
  id: number;
  startsAt: number;
  status: string;
  elapsed: number | null;
  extra: number | null;
  leagueId: number;
  league: string;
  country: string;
  round: string | null;
  homeId: number;
  home: string;
  awayId: number;
  away: string;
  /** Score actuel (prolongation comprise). */
  goals: [number | null, number | null];
  /** Score à la fin du temps réglementaire (sert au règlement des paris). */
  fulltime: [number | null, number | null];
  /** Cartons rouges, si le fournisseur joint les faits de jeu. */
  red: [number, number] | null;
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** Convertit la réponse de /fixtures en matchs (les entrées incomplètes sont ignorées). */
export function parseFixtures(body: any): AfFixture[] {
  const out: AfFixture[] = [];
  for (const r of body?.response ?? []) {
    const f = r?.fixture;
    const homeId = num(r?.teams?.home?.id);
    const awayId = num(r?.teams?.away?.id);
    const startsAt = num(f?.timestamp) !== null ? f.timestamp * 1000 : Date.parse(f?.date);
    if (!f || num(f.id) === null || homeId === null || awayId === null || !Number.isFinite(startsAt)) continue;
    let red: [number, number] | null = null;
    if (Array.isArray(r.events)) {
      red = [0, 0];
      for (const e of r.events)
        if (e?.type === "Card" && /red/i.test(String(e?.detail))) red[e?.team?.id === homeId ? 0 : 1]++;
    }
    out.push({
      id: f.id,
      startsAt,
      status: String(f.status?.short ?? ""),
      elapsed: num(f.status?.elapsed),
      extra: num(f.status?.extra),
      leagueId: num(r.league?.id) ?? 0,
      league: String(r.league?.name ?? ""),
      country: String(r.league?.country ?? ""),
      round: r.league?.round ? String(r.league.round) : null,
      homeId,
      home: String(r.teams.home.name ?? ""),
      awayId,
      away: String(r.teams.away.name ?? ""),
      goals: [num(r.goals?.home), num(r.goals?.away)],
      fulltime: [num(r.score?.fulltime?.home), num(r.score?.fulltime?.away)],
      red,
    });
  }
  return out;
}

/** Message d'erreur renvoyé dans le corps de la réponse (clé invalide, quota atteint, saison non couverte…). */
export function bodyError(body: any): string | null {
  const e = body?.errors;
  if (!e) return null;
  if (Array.isArray(e)) return e.length ? e.map(String).join(" ; ") : null;
  if (typeof e === "object") {
    const parts = Object.entries(e).map(([k, v]) => `${k} : ${v}`);
    return parts.length ? parts.join(" ; ") : null;
  }
  return String(e);
}

export class AfClient {
  /** Requêtes restantes aujourd'hui, d'après le fournisseur. */
  remaining: number | null = null;
  constructor(
    private readonly key: string,
    private readonly fetcher: typeof fetch = fetch,
  ) {}

  async fixtures(query: string): Promise<AfFixture[]> {
    const res = await this.fetcher(`${AF_BASE}/fixtures?${query}`, { headers: { "x-apisports-key": this.key } });
    const left = Number(res.headers.get("x-ratelimit-requests-remaining"));
    if (res.headers.get("x-ratelimit-requests-remaining") !== null && Number.isFinite(left)) this.remaining = left;
    if (!res.ok) throw new Error(`API-Football ${res.status} sur /fixtures?${query}`);
    const body = await res.json();
    const err = bodyError(body);
    if (err) throw new AfError(err);
    return parseFixtures(body);
  }
}

/** Erreur signalée par le fournisseur (souvent : clé, quota ou saison non couverte par l'offre). */
export class AfError extends Error {}

/* ---------- Rapprochement des noms d'équipes entre fournisseurs ---------- */
const NOISE = new Set(["fc", "cf", "sc", "ac", "afc", "as", "ss", "us", "sv", "fk", "sk", "cd", "ud", "rc", "club", "de", "the", "calcio", "1", "04", "05", "07", "09", "1899", "1846", "1860", "1909", "1913"]);

export function teamTokens(name: string): string[] {
  return name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/saint/g, "st")
    .replace(/[^a-z0-9 ]/g, " ")
    .split(/\s+/)
    .filter((t) => t && !NOISE.has(t));
}

/** Ressemblance entre deux noms d'équipe (0 à 1). « Paris Saint Germain » ≈ « Paris SG ». */
export function nameSimilarity(a: string, b: string): number {
  const ta = teamTokens(a);
  const tb = teamTokens(b);
  if (!ta.length || !tb.length) return 0;
  const match = (x: string, y: string) => x === y || (x.length >= 3 && y.length >= 3 && (x.startsWith(y) || y.startsWith(x)));
  const hits = ta.filter((x) => tb.some((y) => match(x, y))).length;
  return hits / Math.min(ta.length, tb.length);
}
