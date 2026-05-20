import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { CheckCircle2, Loader2 } from "lucide-react";
import { z } from "zod";
import { useServerFn } from "@tanstack/react-start";
import { SiteLayout } from "@/components/SiteLayout";
import { useCart } from "@/context/cart";
import { formatPrice } from "@/data/catalog";
import { getStripeCheckoutSession } from "@/functions/stripe-session";

const searchSchema = z.object({
  session_id: z.string().optional(),
  /** Retour après un Stripe Payment Link (configurer l’URL de succès dans Stripe) */
  from: z.enum(["stripe"]).optional(),
});

export const Route = createFileRoute("/checkout/success")({
  validateSearch: searchSchema,
  head: () => ({ meta: [{ title: "Order confirmed — NextWrist" }] }),
  component: CheckoutSuccessPage,
});

function CheckoutSuccessPage() {
  const { session_id, from } = Route.useSearch();
  const { clear } = useCart();
  const navigate = useNavigate();
  const getSession = useServerFn(getStripeCheckoutSession);
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [order, setOrder] = useState<{ email: string; name: string; total: number } | null>(null);

  useEffect(() => {
    if (from === "stripe" && !session_id) {
      setStatus("ok");
      setOrder({ email: "", name: "", total: 0 });
      clear();
      return;
    }

    if (!session_id) {
      setStatus("error");
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        const session = await getSession({ data: { sessionId: session_id } });
        if (cancelled) return;
        setOrder({
          email: session.email,
          name: session.name,
          total: session.amountTotal / 100,
        });
        setStatus("ok");
        clear();
      } catch {
        if (!cancelled) setStatus("error");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [session_id, from, getSession, clear]);

  if (status === "loading") {
    return (
      <SiteLayout>
        <section className="max-w-2xl mx-auto px-6 py-24 text-center">
          <Loader2 className="size-10 mx-auto animate-spin" />
          <p className="mt-4 text-muted-foreground">Confirming your payment…</p>
        </section>
      </SiteLayout>
    );
  }

  if (status === "error" || !order) {
    return (
      <SiteLayout>
        <section className="max-w-2xl mx-auto px-6 py-24 text-center">
          <h1 className="font-black tracking-tighter text-3xl">Payment not confirmed.</h1>
          <p className="mt-4 text-muted-foreground">
            We could not verify your payment. If you were charged, contact{" "}
            <a href="mailto:support@nextwrist.online" className="underline">
              support@nextwrist.online
            </a>{" "}
            with your order details.
          </p>
          <Link to="/checkout" className="mt-8 inline-block underline">
            Return to checkout
          </Link>
        </section>
      </SiteLayout>
    );
  }

  return (
    <SiteLayout>
      <section className="max-w-2xl mx-auto px-6 py-24 text-center">
        <CheckCircle2 className="size-12 mx-auto text-foreground" />
        <h1 className="mt-6 font-black tracking-tighter text-4xl">Order confirmed.</h1>
        <p className="mt-4 text-muted-foreground">
          {order.email ? (
            <>
              Thanks {order.name || "for your order"}. A confirmation has been sent to{" "}
              <strong className="text-foreground">{order.email}</strong>.
            </>
          ) : (
            <>Thanks for your order. Stripe has sent you a confirmation email.</>
          )}
        </p>
        {order.total > 0 && (
          <p className="mt-2 text-sm text-muted-foreground">
            Total paid: <strong className="text-foreground">{formatPrice(order.total)}</strong>
          </p>
        )}
        <p className="mt-2 text-xs text-muted-foreground">
          We&apos;ll email you tracking details once your order ships.
        </p>
        <button
          onClick={() => navigate({ to: "/" })}
          className="mt-8 inline-flex items-center gap-2 bg-foreground text-background px-6 py-3.5 rounded-full text-sm font-semibold"
        >
          Back to home
        </button>
      </section>
    </SiteLayout>
  );
}
