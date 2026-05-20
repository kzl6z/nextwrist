import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { Mail, Lock, Loader2 } from "lucide-react";
import { useServerFn } from "@tanstack/react-start";
import { SiteLayout } from "@/components/SiteLayout";
import { useCart } from "@/context/cart";
import { formatPrice } from "@/data/catalog";
import { createStripeCheckout } from "@/functions/stripe-checkout";
import { getCartSummary } from "@/lib/stripe-payment";
import { goToStripeCheckout, needsApiCheckout } from "@/lib/checkout";

export const Route = createFileRoute("/checkout")({
  head: () => ({ meta: [{ title: "Checkout — NextWrist" }] }),
  component: CheckoutPage,
});

function CheckoutPage() {
  const { items, total } = useCart();
  const createCheckout = useServerFn(createStripeCheckout);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const summary = getCartSummary(items);
  const usesApi = needsApiCheckout(items);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    if (!usesApi && goToStripeCheckout(items, email)) {
      return;
    }

    try {
      const { url } = await createCheckout({
        data: {
          email,
          name,
          items: items.map((i) => ({
            name: i.name,
            slug: i.slug,
            type: i.type,
            price: i.price,
            qty: i.qty,
            img: i.img,
          })),
        },
      });
      window.location.href = url;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Impossible de démarrer le paiement.";
      setError(msg);
      setLoading(false);
    }
  };

  if (items.length === 0) {
    return (
      <SiteLayout>
        <section className="max-w-2xl mx-auto px-6 py-24 text-center">
          <h1 className="font-black tracking-tighter text-3xl">Your cart is empty.</h1>
          <Link to="/" hash="watches" className="mt-6 inline-block underline">
            Browse watches
          </Link>
        </section>
      </SiteLayout>
    );
  }

  return (
    <SiteLayout>
      <section className="max-w-5xl mx-auto px-6 py-16 grid lg:grid-cols-[1fr_360px] gap-10">
        <form onSubmit={onSubmit} className="space-y-6">
          <h1 className="font-black tracking-tighter text-[clamp(2rem,5vw,3rem)] leading-[0.95]">CHECKOUT.</h1>

          {summary.isStandardBundle && (
            <p className="text-sm border border-border rounded-xl px-4 py-3 bg-muted/30">
              Pack montre + bracelet : redirection vers votre lien Stripe ({formatPrice(total)}).
            </p>
          )}
          {usesApi && summary.isCombo && (
            <p className="text-sm border border-border rounded-xl px-4 py-3 bg-muted/30">
              Panier personnalisé (ex. plusieurs bracelets) : un seul paiement Stripe pour{" "}
              <strong>{formatPrice(total)}</strong>, calculé selon les quantités.
            </p>
          )}

          <fieldset className="border border-border rounded-2xl p-6 bg-card space-y-4">
            <legend className="px-2 text-xs font-semibold tracking-widest text-muted-foreground">CONTACT & SHIPPING</legend>
            <p className="text-sm text-muted-foreground flex items-center gap-2">
              <Mail className="size-4" /> We'll send your order confirmation and tracking to this email.
            </p>
            <label className="block">
              <span className="text-xs font-semibold">Full name</span>
              <input
                required={usesApi}
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 w-full border border-border rounded-lg px-3 py-2.5 bg-background"
              />
            </label>
            <label className="block">
              <span className="text-xs font-semibold">Email address</span>
              <input
                required
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full border border-border rounded-lg px-3 py-2.5 bg-background"
                placeholder="you@example.com"
              />
            </label>
          </fieldset>

          <fieldset className="border border-border rounded-2xl p-6 bg-card space-y-3">
            <legend className="px-2 text-xs font-semibold tracking-widest text-muted-foreground">PAYMENT</legend>
            <p className="text-sm text-muted-foreground flex items-center gap-2">
              <Lock className="size-3.5" /> Secure payment via Stripe.
            </p>
            <p className="text-xs text-muted-foreground">
              {usesApi
                ? "Total du panier envoyé à Stripe (quantités et articles multiples)."
                : summary.isStandardBundle
                  ? "Redirection vers le lien pack montre + bracelet."
                  : "Redirection vers votre lien de paiement Stripe."}
            </p>
          </fieldset>

          <label className="flex items-start gap-2 text-xs text-muted-foreground">
            <input required type="checkbox" className="mt-0.5" />
            <span>
              I agree to the <Link to="/policies/terms" className="underline">Terms</Link>,{" "}
              <Link to="/policies/refund" className="underline">Refund</Link> and{" "}
              <Link to="/policies/privacy" className="underline">Privacy</Link> policies.
            </span>
          </label>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-foreground text-background px-6 py-4 rounded-full text-sm font-semibold hover:opacity-90 transition disabled:opacity-60 inline-flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="size-4 animate-spin" /> Redirecting to Stripe…
              </>
            ) : (
              <>Pay {formatPrice(total)} with Stripe</>
            )}
          </button>
        </form>

        <aside className="h-fit border border-border rounded-2xl bg-card p-6 sticky top-24">
          <p className="font-semibold">Order</p>
          <ul className="mt-4 space-y-3">
            {items.map((i) => (
              <li key={i.id} className="flex gap-3 items-center text-sm">
                <div className="size-12 rounded-lg bg-muted/40 overflow-hidden shrink-0">
                  <img src={i.img} alt={i.name} className="w-full h-full object-cover" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold truncate">{i.name}</p>
                  <p className="text-xs text-muted-foreground">Qty {i.qty}</p>
                </div>
                <p className="font-semibold">{formatPrice(i.price * i.qty)}</p>
              </li>
            ))}
          </ul>
          <div className="mt-4 pt-4 border-t border-border text-sm space-y-1">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Shipping</span>
              <span>Free</span>
            </div>
            <div className="flex justify-between font-bold text-base mt-2">
              <span>Total</span>
              <span>{formatPrice(total)}</span>
            </div>
          </div>
        </aside>
      </section>
    </SiteLayout>
  );
}
