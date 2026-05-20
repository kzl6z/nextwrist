import type { CartItem } from "@/context/cart";
import { getCheckoutPaymentUrl, needsApiCheckout } from "@/lib/stripe-payment";

export function goToStripeCheckout(items: CartItem[], email?: string): boolean {
  const paymentLink = getCheckoutPaymentUrl(items, email);
  if (paymentLink) {
    window.location.href = paymentLink;
    return true;
  }
  return false;
}

export { needsApiCheckout, needsApiCheckout as needsCombinedCheckout };
