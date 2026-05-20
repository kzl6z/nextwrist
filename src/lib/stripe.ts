import Stripe from "stripe";

let stripeClient: Stripe | undefined;

export function getStripe(): Stripe {
  const key = process.env.STRIPE_SECRET_KEY;
  if (!key) {
    throw new Error("STRIPE_SECRET_KEY is not configured");
  }
  if (!stripeClient) {
    stripeClient = new Stripe(key, { typescript: true });
  }
  return stripeClient;
}

export function getSiteOrigin(request: Request): string {
  if (process.env.SITE_URL) return process.env.SITE_URL.replace(/\/$/, "");
  return new URL(request.url).origin;
}

export function toAbsoluteImageUrl(origin: string, img: string): string | undefined {
  if (!img) return undefined;
  if (img.startsWith("http://") || img.startsWith("https://")) return img;
  if (!canStripeFetchImages(origin)) return undefined;
  return `${origin}${img.startsWith("/") ? img : `/${img}`}`;
}

/** Stripe doit pouvoir télécharger les images (pas localhost). */
export function canStripeFetchImages(origin: string): boolean {
  try {
    const { protocol, hostname } = new URL(origin);
    if (protocol !== "https:") return false;
    if (hostname === "localhost" || hostname === "127.0.0.1") return false;
    return true;
  } catch {
    return false;
  }
}
