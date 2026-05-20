import type { CartItem } from "@/context/cart";

/** Liens Stripe Payment Link (dashboard Stripe) */
export const STRIPE_PAYMENT_LINK_WATCH = "https://buy.stripe.com/7sY4gB0NSeQDfYC6kS0gw03";
export const STRIPE_PAYMENT_LINK_STRAP = "https://buy.stripe.com/9B64gBgMQ8sf6o238G0gw04";
/** 1 montre + 1 bracelet exactement */
export const STRIPE_PAYMENT_LINK_BUNDLE = "https://buy.stripe.com/aFa8wR8gkbEr8wa10y0gw05";

export type CartSummary = {
  watchQty: number;
  strapQty: number;
  hasWatch: boolean;
  hasStrap: boolean;
  lineCount: number;
  isCombo: boolean;
  isStandardBundle: boolean;
};

function withPrefilledEmail(base: string, email?: string): string {
  if (!email?.trim()) return base;
  const url = new URL(base);
  url.searchParams.set("prefilled_email", email.trim());
  return url.toString();
}

export function getCartSummary(items: CartItem[]): CartSummary {
  const watchQty = items.filter((i) => i.type === "watch").reduce((s, i) => s + i.qty, 0);
  const strapQty = items.filter((i) => i.type === "strap").reduce((s, i) => s + i.qty, 0);
  const isCombo = watchQty > 0 && strapQty > 0;
  return {
    watchQty,
    strapQty,
    hasWatch: watchQty > 0,
    hasStrap: strapQty > 0,
    lineCount: items.length,
    isCombo,
    isStandardBundle: isCombo && watchQty === 1 && strapQty === 1,
  };
}

/** 1 montre + 1 bracelet → lien pack Stripe */
export function isStandardBundle(items: CartItem[]): boolean {
  return getCartSummary(items).isStandardBundle;
}

/**
 * Panier « complexe » : quantités > 1, plusieurs montres/bracelets, etc.
 * → checkout dynamique (API) avec le total exact du panier.
 */
export function needsApiCheckout(items: CartItem[]): boolean {
  if (items.length === 0) return false;
  return getCheckoutPaymentUrl(items) === null;
}

export function getStripePaymentLinkUrl(type: "watch" | "strap", email?: string): string {
  const base = type === "watch" ? STRIPE_PAYMENT_LINK_WATCH : STRIPE_PAYMENT_LINK_STRAP;
  return withPrefilledEmail(base, email);
}

/** Lien Payment Link si le panier correspond à un lien fixe, sinon null (= API) */
export function getCheckoutPaymentUrl(items: CartItem[], email?: string): string | null {
  const summary = getCartSummary(items);

  if (summary.isStandardBundle) {
    return withPrefilledEmail(STRIPE_PAYMENT_LINK_BUNDLE, email);
  }

  if (items.length === 1 && items[0].qty === 1) {
    return getStripePaymentLinkUrl(items[0].type, email);
  }

  return null;
}

/** @deprecated Utiliser needsApiCheckout */
export function needsCombinedCheckout(items: CartItem[]): boolean {
  return needsApiCheckout(items);
}
