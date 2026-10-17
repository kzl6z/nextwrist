import { db } from "./db";
import { HttpError } from "./http";
import { applyTx } from "./wallet";

export const WELCOME_BONUS = 1000;
const SESSION_MS = 30 * 86_400_000;

export interface User {
  id: number;
  username: string;
  balance: number;
  last_bonus_at: number | null;
}

function createSession(userId: number): string {
  const token = Buffer.from(crypto.getRandomValues(new Uint8Array(32))).toString("hex");
  db.query("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)").run(token, userId, Date.now() + SESSION_MS);
  return token;
}

export async function register(username: unknown, password: unknown): Promise<string> {
  if (typeof username !== "string" || !/^[a-zA-Z0-9_]{3,20}$/.test(username))
    throw new HttpError(400, "Pseudo : 3 à 20 caractères (lettres, chiffres, _)");
  if (typeof password !== "string" || password.length < 8)
    throw new HttpError(400, "Mot de passe : 8 caractères minimum");
  const hash = await Bun.password.hash(password);
  const userId = db.transaction(() => {
    if (db.query("SELECT 1 FROM users WHERE username = ?").get(username))
      throw new HttpError(409, "Ce pseudo est déjà pris");
    const { id } = db
      .query("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?) RETURNING id")
      .get(username, hash, Date.now()) as { id: number };
    applyTx(id, WELCOME_BONUS, "welcome_bonus");
    return id;
  })();
  return createSession(userId);
}

export async function login(username: unknown, password: unknown): Promise<string> {
  const row =
    typeof username === "string"
      ? (db.query("SELECT id, password_hash FROM users WHERE username = ?").get(username) as
          | { id: number; password_hash: string }
          | null)
      : null;
  if (!row || typeof password !== "string" || !(await Bun.password.verify(password, row.password_hash)))
    throw new HttpError(401, "Pseudo ou mot de passe incorrect");
  return createSession(row.id);
}

function tokenFrom(req: Request): string | null {
  return req.headers.get("cookie")?.match(/(?:^|;\s*)session=([a-f0-9]{64})/)?.[1] ?? null;
}

export function userFrom(req: Request): User | null {
  const token = tokenFrom(req);
  if (!token) return null;
  return db
    .query(
      `SELECT u.id, u.username, u.balance, u.last_bonus_at FROM sessions s
       JOIN users u ON u.id = s.user_id WHERE s.token = ? AND s.expires_at > ?`,
    )
    .get(token, Date.now()) as User | null;
}

export function logout(req: Request) {
  const token = tokenFrom(req);
  if (token) db.query("DELETE FROM sessions WHERE token = ?").run(token);
}

export function sessionCookie(token: string | null): string {
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  return token
    ? `session=${token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=${SESSION_MS / 1000}${secure}`
    : `session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0${secure}`;
}
