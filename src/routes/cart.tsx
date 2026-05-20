import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Trash2, Plus, Minus, ArrowRight, ShoppingBag } from "lucide-react";
import { SiteLayout } from "@/components/SiteLayout";
import { useCart } from "@/context/cart";
import { formatPrice, BUNDLE_PRICE } from "@/data/catalog";
import { getCartSummary } from "@/lib/stripe-payment";
import { goToStripeCheckout, needsApiCheckout } from "@/lib/checkout";

export const Route = createFileRoute("/cart")({
  head: () => ({ meta: [{ title: "Your Cart — NextWrist" }, { name: "description", content: "Review your NextWrist order before checkout." }] }),
  component: CartPage,
});

function CartPage() {
  const { items, remove, setQty, total } = useCart();
  const navigate = useNavigate();
  const [checkoutEmail, setCheckoutEmail] = useState("");
  const summary = getCartSummary(items);
  const usesApi = needsApiCheckout(items);

  const handleCheckout = () => {
    if (!usesApi && goToStripeCheckout(items, checkoutEmail)) return;
    navigate({ to: "/checkout" });
  };

  return (
    <SiteLayout>
      <section className="max-w-5xl mx-auto px-6 py-16">
        <h1 className="font-black tracking-tighter text-[clamp(2rem,5vw,3.5rem)] leading-[0.95]">YOUR CART.</h1>
        <p className="mt-3 text-muted-foreground">Free worldwide shipping on every order.</p>

        {items.length === 0 ? (
          <div className="mt-16 text-center border border-dashed border-border rounded-3xl p-16">
            <ShoppingBag className="size-10 mx-auto text-muted-foreground" />
            <p className="mt-4 font-semibold">Your cart is empty.</p>
            <Link to="/" hash="watches" className="mt-6 inline-flex items-center gap-2 bg-foreground text-background px-6 py-3 rounded-full text-sm font-semibold">
              Browse watches <ArrowRight className="size-4" />
            </Link>
          </div>
        ) : (
          <div className="mt-10 grid lg:grid-cols-[1fr_360px] gap-10">
            <ul className="space-y-4">
              {items.map((i) => (
                <li key={i.id} className="flex gap-4 border border-border rounded-2xl p-4 bg-card">
                  <div className="size-24 rounded-xl bg-muted/40 flex items-center justify-center overflow-hidden shrink-0">
                    <img src={i.img} alt={i.name} className="w-full h-full object-cover" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold">{i.name}</p>
                    <p className="text-xs text-muted-foreground capitalize">{i.type}</p>
                    <div className="mt-3 flex items-center gap-2">
                      <button onClick={() => setQty(i.id, i.qty - 1)} className="size-7 rounded-full border border-border hover:bg-muted flex items-center justify-center" aria-label="Decrease"><Minus className="size-3.5" /></button>
                      <span className="w-6 text-center text-sm font-semibold">{i.qty}</span>
                      <button onClick={() => setQty(i.id, i.qty + 1)} className="size-7 rounded-full border border-border hover:bg-muted flex items-center justify-center" aria-label="Increase"><Plus className="size-3.5" /></button>
                    </div>
                  </div>
                  <div className="flex flex-col items-end justify-between">
                    <button onClick={() => remove(i.id)} aria-label="Remove" className="text-muted-foreground hover:text-foreground"><Trash2 className="size-4" /></button>
                    <p className="font-semibold">{formatPrice(i.price * i.qty)}</p>
                  </div>
                </li>
              ))}
            </ul>

            <aside className="h-fit border border-border rounded-2xl bg-card p-6 sticky top-24">
              <p className="font-semibold">Order summary</p>
              <div className="mt-4 space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">Subtotal</span><span>{formatPrice(total)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Shipping</span><span>Free</span></div>
              </div>
              <div className="mt-4 pt-4 border-t border-border flex justify-between font-bold">
                <span>Total</span><span>{formatPrice(total)}</span>
              </div>
              {summary.hasWatch && !summary.hasStrap && (
                <p className="mt-4 text-xs text-muted-foreground">
                  <Link to="/" hash="straps" className="underline">
                    Add a strap
                  </Link>{" "}
                  to pay {formatPrice(BUNDLE_PRICE)} for both in one checkout.
                </p>
              )}
              {summary.isStandardBundle && (
                <p className="mt-4 text-xs text-muted-foreground">
                  Pack 1 montre + 1 bracelet → lien Stripe {formatPrice(BUNDLE_PRICE)}.
                </p>
              )}
              {usesApi && summary.isCombo && (
                <p className="mt-4 text-xs text-muted-foreground">
                  Plusieurs articles ou quantités : total {formatPrice(total)} calculé au paiement.
                </p>
              )}
              {!usesApi && (
                <label className="mt-4 block">
                  <span className="text-xs font-semibold">Email (optional)</span>
                  <input
                    type="email"
                    value={checkoutEmail}
                    onChange={(e) => setCheckoutEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="mt-1 w-full border border-border rounded-lg px-3 py-2.5 bg-background text-sm"
                  />
                </label>
              )}
              <button
                type="button"
                onClick={handleCheckout}
                className="mt-4 w-full inline-flex items-center justify-center gap-2 bg-foreground text-background px-6 py-3.5 rounded-full text-sm font-semibold hover:opacity-90 transition"
              >
                Checkout <ArrowRight className="size-4" />
              </button>
              <p className="mt-4 text-xs text-muted-foreground">
                By checking out you accept our <Link to="/policies/terms" className="underline">Terms</Link> and <Link to="/policies/refund" className="underline">Refund policy</Link>.
              </p>
            </aside>
          </div>
        )}
      </section>
    </SiteLayout>
  );
}
