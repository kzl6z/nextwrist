// Sports virtuels : calendrier de matchs simulés entre de vraies équipes, joués en
// direct (score, horloge, cotes recalculées à chaque pas) puis réglés automatiquement.
import { db } from "../db";
import { randomFloat, randomInt } from "../rng";
import { priceOf } from "./markets";
import { detailOf, MODELS, type Sim, type SportId } from "./models";

interface League {
  name: string;
  sport: SportId;
  teams: string[];
}

const LEAGUES: League[] = [
  { name: "Ligue 1", sport: "football", teams: ["PSG", "Marseille", "Lyon", "Monaco", "Lille", "Lens", "Rennes", "Nice", "Nantes", "Strasbourg", "Toulouse", "Brest"] },
  { name: "Premier League", sport: "football", teams: ["Arsenal", "Liverpool", "Man City", "Chelsea", "Tottenham", "Man United", "Newcastle", "Aston Villa", "Brighton", "West Ham"] },
  { name: "LaLiga", sport: "football", teams: ["Real Madrid", "Barcelone", "Atlético", "Séville", "Betis", "Villarreal", "Real Sociedad", "Valence", "Athletic Bilbao", "Gérone"] },
  { name: "Serie A", sport: "football", teams: ["Inter", "Milan", "Juventus", "Naples", "Rome", "Lazio", "Atalanta", "Fiorentina", "Bologne", "Turin"] },
  { name: "Bundesliga", sport: "football", teams: ["Bayern", "Dortmund", "Leverkusen", "Leipzig", "Francfort", "Stuttgart", "Fribourg", "Wolfsburg", "Mayence", "Brême"] },
  { name: "NBA", sport: "basketball", teams: ["Celtics", "Lakers", "Warriors", "Nuggets", "Bucks", "Knicks", "Heat", "Thunder", "Mavericks", "Suns", "Cavaliers", "Timberwolves", "Spurs", "76ers"] },
  { name: "Euroligue", sport: "basketball", teams: ["Real Madrid", "Fenerbahçe", "Olympiakos", "Panathinaikos", "Monaco", "Paris Basketball", "Barcelone", "Partizan", "Maccabi Tel-Aviv", "ASVEL"] },
  { name: "ATP", sport: "tennis", teams: ["J. Sinner", "C. Alcaraz", "N. Djokovic", "A. Zverev", "T. Fritz", "J. Draper", "D. Medvedev", "C. Ruud", "A. de Minaur", "U. Humbert", "A. Fils", "J. Mensik", "H. Rune", "B. Shelton", "G. Mpetshi Perricard", "L. Musetti"] },
  { name: "WTA", sport: "tennis", teams: ["A. Sabalenka", "I. Swiatek", "C. Gauff", "J. Pegula", "E. Rybakina", "J. Paolini", "M. Andreeva", "M. Keys", "L. Boisson", "Q. Zheng", "E. Navarro", "C. Garcia"] },
  { name: "Top 14", sport: "rugby", teams: ["Toulouse", "La Rochelle", "Bordeaux-Bègles", "Toulon", "Racing 92", "Stade Français", "Clermont", "Castres", "Pau", "Bayonne", "Montpellier", "Lyon OU"] },
  { name: "NHL", sport: "hockey", teams: ["Panthers", "Oilers", "Rangers", "Stars", "Avalanche", "Golden Knights", "Maple Leafs", "Bruins", "Hurricanes", "Jets", "Canadiens", "Lightning"] },
  { name: "UFC", sport: "mma", teams: ["C. Gane", "T. Aspinall", "B. Saint-Denis", "I. Makhachev", "A. Pereira", "M. Dvalishvili", "I. Topuria", "A. Pantoja", "D. du Plessis", "K. Chimaev", "J. Della Maddalena", "N. Imavov", "M. Nicolau", "F. Lapilus"] },
];

/** Nombre de matchs à venir maintenus par sport. */
const TARGET: Record<SportId, number> = { football: 22, basketball: 8, tennis: 8, rugby: 5, hockey: 5, mma: 4 };
/** Fenêtre des coups d'envoi (minutes). */
const HORIZON_MIN = 120;
/** Marchés suspendus quelques secondes après un but / un essai. */
const SUSPEND_MS = 7_000;
const SUSPEND_SPORTS = new Set<SportId>(["football", "hockey", "rugby"]);

export const matchMs = () => Math.max(0.1, Number(process.env.DEMO_MATCH_MINUTES) || 10) * 60_000;

type SimState = Sim & { at: number };

const upsertSel = db.query(
  `INSERT INTO selections (event_id, key, price, prob) VALUES (?, ?, ?, ?)
   ON CONFLICT(event_id, key) DO UPDATE SET price = excluded.price, prob = excluded.prob`,
);

function writeSelections(eventId: string, sim: Sim, open: boolean) {
  for (const [key, prob] of MODELS[sim.sport].probs(sim)) {
    const p = Math.min(1, Math.max(0, prob));
    upsertSel.run(eventId, key, open ? priceOf(key, p) : null, p);
  }
}

/** Joue la simulation jusqu'à l'instant `now`, par petits pas. */
function catchUp(sim: SimState, now: number): boolean {
  const model = MODELS[sim.sport];
  let total = ((now - sim.at) / matchMs()) * model.len;
  sim.at = now;
  let scored = false;
  const step = model.len / 120;
  while (total > 1e-9 && !sim.done) {
    const dt = Math.min(step, total);
    total -= dt;
    if (model.advance(sim, dt)) scored = true;
  }
  return scored;
}

function createFixture(league: League, busy: Set<string>, startsAt: number, label: (l: string) => string): boolean {
  const teams = league.teams.filter((t) => !busy.has(`${league.sport}:${t}`));
  if (teams.length < 2) return false;
  const i = randomInt(teams.length);
  let j = randomInt(teams.length - 1);
  if (j >= i) j++;
  const home = teams[i]!;
  const away = teams[j]!;
  busy.add(`${league.sport}:${home}`).add(`${league.sport}:${away}`);

  const sim: SimState = { ...MODELS[league.sport].create(randomFloat() * 2 - 1), at: startsAt };
  const id = `v-${Buffer.from(crypto.getRandomValues(new Uint8Array(8))).toString("hex")}`;
  const now = Date.now();
  db.query(
    `INSERT INTO events (id, sport, league, home, away, starts_at, status, virtual, sim, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, 'scheduled', 1, ?, ?)`,
  ).run(id, league.sport, label(league.name), home, away, startsAt, JSON.stringify(sim), now);
  writeSelections(id, sim, true);
  return true;
}

const busyTeams = () =>
  new Set(
    (
      db.query("SELECT sport, home, away FROM events WHERE virtual = 1 AND status IN ('scheduled', 'live')").all() as {
        sport: string;
        home: string;
        away: string;
      }[]
    ).flatMap((e) => [`${e.sport}:${e.home}`, `${e.sport}:${e.away}`]),
  );

/** Complète le calendrier ; au premier lancement, quelques matchs démarrent déjà commencés. */
function replenish(label: (l: string) => string) {
  const busy = busyTeams();
  const now = Date.now();
  const counts = new Map(
    (
      db.query("SELECT sport, COUNT(*) AS n FROM events WHERE virtual = 1 AND status = 'scheduled' GROUP BY sport").all() as {
        sport: SportId;
        n: number;
      }[]
    ).map((r) => [r.sport, r.n]),
  );
  const anyLive = db.query("SELECT 1 FROM events WHERE virtual = 1 AND status = 'live' LIMIT 1").get();
  for (const sport of Object.keys(TARGET) as SportId[]) {
    const leagues = LEAGUES.filter((l) => l.sport === sport);
    // Premier lancement : un ou deux matchs déjà en cours par sport.
    if (!anyLive) {
      for (let k = 0; k < (sport === "football" ? 3 : 1); k++)
        createFixture(leagues[randomInt(leagues.length)]!, busy, now - (0.15 + randomFloat() * 0.6) * matchMs(), label);
    }
    let missing = TARGET[sport] - (counts.get(sport) ?? 0);
    for (let tries = 0; missing > 0 && tries < 60; tries++) {
      const startsAt = now + (1 + randomInt(HORIZON_MIN)) * 60_000;
      if (createFixture(leagues[randomInt(leagues.length)]!, busy, startsAt, label)) missing--;
    }
  }
}

/** Un pas du moteur : coups d'envoi, déroulé des matchs en cours, fins de match. */
export function tickVirtual(label: (l: string) => string = (l) => l): number {
  const now = Date.now();
  let finished = 0;
  db.transaction(() => {
    const rows = db
      .query("SELECT id, status, sim FROM events WHERE virtual = 1 AND status IN ('scheduled', 'live') AND starts_at <= ?")
      .all(now) as { id: string; status: string; sim: string }[];
    const update = db.query(
      `UPDATE events SET status = ?, home_score = ?, away_score = ?, clock = ?, detail = ?, sim = ?,
       suspended_until = COALESCE(?, suspended_until), updated_at = ? WHERE id = ?`,
    );
    for (const row of rows) {
      const sim = JSON.parse(row.sim) as SimState;
      // Pas de suspension pour un rattrapage (premier lancement, serveur relancé).
      const catchingUp = now - sim.at > 10_000;
      const scored = catchUp(sim, now) && !catchingUp;
      const model = MODELS[sim.sport];
      const status = sim.done ? "finished" : "live";
      if (sim.done) finished++;
      update.run(
        status,
        sim.h,
        sim.a,
        model.clock(sim),
        JSON.stringify(detailOf(sim)),
        JSON.stringify(sim),
        scored && SUSPEND_SPORTS.has(sim.sport) && !sim.done ? now + SUSPEND_MS : null,
        now,
        row.id,
      );
      writeSelections(row.id, sim, !sim.done);
    }
    replenish(label);
  })();
  return finished;
}
