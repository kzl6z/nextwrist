import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { ArrowRight, Truck, ShieldCheck, RotateCcw, ArrowLeft } from "lucide-react";
import { SiteLayout } from "@/components/SiteLayout";
import { colorways, WATCH_PRICE, formatPrice } from "@/data/catalog";
import { useCart } from "@/context/cart";
import { getStripePaymentLinkUrl } from "@/lib/stripe-payment";

export const Route = createFileRoute("/products/$slug")({
  head: ({ params }) => {
    const c = colorways.find((x) => x.slug === params.slug);
    const title = c ? `${c.name} — NextWrist` : "Watch — NextWrist";
    return {
      meta: [
        { title },
        { name: "description", content: `${c?.name ?? "NextWrist"} pocket watch. ${formatPrice(WATCH_PRICE)}. Free worldwide shipping.` },
        { property: "og:title", content: title },
        { property: "og:image", content: c?.img },
      ],
    };
  },
  loader: ({ params }) => {
    const c = colorways.find((x) => x.slug === params.slug);
    if (!c) throw notFound();
    return { colorway: c };
  },
  component: ProductPage,
  notFoundComponent: () => (
    <SiteLayout>
      <div className="max-w-3xl mx-auto px-6 py-24 text-center">
        <h1 className="text-3xl font-black">Watch not found</h1>
        <Link to="/" className="mt-6 inline-block underline">Back to collection</Link>
      </div>
    </SiteLayout>
  ),
});

function ProductPage() {
  const { colorway: c } = Route.useLoaderData();
  const { add } = useCart();

  return (
    <SiteLayout>
      <section className="relative overflow-hidden">
        <div
          aria-hidden
          className="absolute inset-0 -z-10"
          style={{
            background: `radial-gradient(60% 60% at 50% 40%, ${c.glow} 0%, rgba(255,255,255,0) 60%), #fafafa`,
          }}
        />
        <div className="max-w-7xl mx-auto px-6 py-10">
          <Link to="/" hash="watches" className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Back to collection</Link>
        </div>
        <div className="max-w-7xl mx-auto px-6 pb-20 grid md:grid-cols-2 gap-12 items-center">
          
          <div>
            <p className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">POCKET WATCH</p>
            <h1 className="mt-4 font-black tracking-tighter text-[clamp(2.5rem,6vw,4.5rem)] leading-[0.95]">{c.name}</h1>
            <p className="mt-6 text-3xl font-black tracking-tight">{formatPrice(WATCH_PRICE)}</p>
            <p className="mt-4 text-muted-foreground max-w-md">
              The {c.name} pocket watch. Bioceramic case, precision quartz movement,
              and a finish that's built to last.
            </p>

            <div className="mt-8 flex flex-wrap gap-3">
              <a
                href={getStripePaymentLinkUrl("watch")}
                className="inline-flex items-center gap-2 bg-foreground text-background px-7 py-4 rounded-full text-sm font-semibold hover:opacity-90 transition"
              >
                Buy now — {formatPrice(WATCH_PRICE)} <ArrowRight className="size-4" />
              </a>
              <button
                onClick={() => add({ type: "watch", slug: c.slug, name: c.name, price: WATCH_PRICE, img: c.img })}
                className="inline-flex items-center gap-2 border border-border bg-card px-7 py-4 rounded-full text-sm font-semibold hover:bg-muted transition"
              >
                Add to cart
              </button>
            </div>

            <ul className="mt-10 space-y-3 text-sm">
              <li className="flex items-start gap-3"><Truck className="size-4 mt-0.5" /> <span>Free worldwide shipping.</span></li>
              <li className="flex items-start gap-3"><RotateCcw className="size-4 mt-0.5" /> <span>30-day hassle-free returns.</span></li>
              <li className="flex items-start gap-3"><ShieldCheck className="size-4 mt-0.5" /> <span>12-month manufacturer warranty.</span></li>
            </ul>

            <p className="mt-10 text-xs text-muted-foreground">
              By purchasing, you agree to our <Link to="/policies/terms" className="underline">Terms</Link>, <Link to="/policies/delivery" className="underline">Shipping</Link> and <Link to="/policies/refund" className="underline">Refund</Link> policies.
            </p>
          </div>
          <div className="relative flex items-center justify-center min-h-[420px]">
            <div aria-hidden className="absolute inset-0 rounded-full blur-3xl opacity-70" style={{ background: `radial-gradient(circle, ${c.glow}, transparent 60%)` }} />
            <img src={c.img} alt={c.name} className="relative max-h-[520px] object-contain drop-shadow-2xl" />
          </div>
        </div>
      </section>

      <section className="max-w-7xl mx-auto px-6 py-20 border-t border-border">
        <p className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">OTHER COLORWAYS</p>
        <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
          {colorways.filter((x) => x.slug !== c.slug).slice(0, 4).map((other) => (
            <Link key={other.slug} to="/products/$slug" params={{ slug: other.slug }} className="group border border-border rounded-2xl bg-card p-4 hover:shadow-md transition">
              <div className="aspect-square flex items-center justify-center">
                <img src={other.img} alt={other.name} className="max-h-full object-contain group-hover:scale-105 transition" />
              </div>
              <p className="mt-2 font-semibold text-sm">{other.name}</p>
              <p className="text-xs text-muted-foreground">{formatPrice(WATCH_PRICE)}</p>
            </Link>
          ))}
        </div>
      </section>
    </SiteLayout>
  );
}
