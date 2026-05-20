import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { ArrowRight, Truck, ShieldCheck, ArrowLeft } from "lucide-react";
import { SiteLayout } from "@/components/SiteLayout";
import { straps, STRAP_PRICE, formatPrice } from "@/data/catalog";
import { useCart } from "@/context/cart";
import { getStripePaymentLinkUrl } from "@/lib/stripe-payment";

export const Route = createFileRoute("/straps/$slug")({
  head: ({ params }) => {
    const s = straps.find((x) => x.slug === params.slug);
    const title = s ? `${s.name} Strap — NextWrist` : "Strap — NextWrist";
    return {
      meta: [
        { title },
        { name: "description", content: `${s?.name ?? "NextWrist"} strap. ${formatPrice(STRAP_PRICE)}. Free worldwide shipping.` },
        { property: "og:title", content: title },
        { property: "og:image", content: s?.img },
      ],
    };
  },
  loader: ({ params }) => {
    const s = straps.find((x) => x.slug === params.slug);
    if (!s) throw notFound();
    return { strap: s };
  },
  component: StrapPage,
  notFoundComponent: () => (
    <SiteLayout>
      <div className="max-w-3xl mx-auto px-6 py-24 text-center">
        <h1 className="text-3xl font-black">Strap not found</h1>
        <Link to="/" hash="straps" className="mt-6 inline-block underline">Back to straps</Link>
      </div>
    </SiteLayout>
  ),
});

function StrapPage() {
  const { strap: s } = Route.useLoaderData();
  const { add } = useCart();

  return (
    <SiteLayout>
      <div className="max-w-7xl mx-auto px-6 pt-10">
        <Link to="/" hash="straps" className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Back to straps</Link>
      </div>
      <section className="max-w-7xl mx-auto px-6 py-12 grid md:grid-cols-2 gap-12 items-center">
        <div className="rounded-3xl border border-border bg-card overflow-hidden">
          <img src={s.img} alt={s.name} className="w-full h-auto object-cover" />
        </div>
        <div>
          <p className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">PREMIUM STRAP</p>
          <h1 className="mt-4 font-black tracking-tighter text-[clamp(2.5rem,6vw,4.5rem)] leading-[0.95]">{s.name}</h1>
          <p className="mt-6 text-3xl font-black tracking-tight">{formatPrice(STRAP_PRICE)}</p>
          <p className="mt-4 text-muted-foreground max-w-md">
            The {s.name} strap. Premium materials, comfortable fit, and quick-release pins
            for easy swaps.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <a
              href={getStripePaymentLinkUrl("strap")}
              className="inline-flex items-center gap-2 bg-foreground text-background px-7 py-4 rounded-full text-sm font-semibold hover:opacity-90 transition"
            >
              Buy now — {formatPrice(STRAP_PRICE)} <ArrowRight className="size-4" />
            </a>
            <button
              onClick={() => add({ type: "strap", slug: s.slug, name: `${s.name} Strap`, price: STRAP_PRICE, img: s.img })}
              className="inline-flex items-center gap-2 border border-border bg-card px-7 py-4 rounded-full text-sm font-semibold hover:bg-muted transition"
            >
              Add to cart
            </button>
          </div>

          <ul className="mt-10 space-y-3 text-sm">
            <li className="flex items-start gap-3"><Truck className="size-4 mt-0.5" /> <span>Free worldwide shipping.</span></li>
            <li className="flex items-start gap-3"><ShieldCheck className="size-4 mt-0.5" /> <span>Secure checkout. 30-day returns.</span></li>
          </ul>
        </div>
      </section>
    </SiteLayout>
  );
}
