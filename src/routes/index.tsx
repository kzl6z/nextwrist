import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { ArrowRight, Star, Shield, Truck, RotateCcw, Lock, Sparkles, Factory } from "lucide-react";
import { SiteLayout } from "@/components/SiteLayout";
import { colorways, straps, WATCH_PRICE, STRAP_PRICE, formatPrice } from "@/data/catalog";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "NextWrist — Time Redefined" },
      { name: "description", content: "Premium pocket watches with 8 colorways and 11 straps. Free shipping, 30-day returns, 12-month warranty." },
      { property: "og:title", content: "NextWrist — Time Redefined" },
      { property: "og:description", content: "Premium pocket watches. 8 colorways. 11 straps." },
    ],
  }),
  component: Index,
});

function Index() {
  const [selectedIdx, setSelectedIdx] = useState(0);
  const selected = colorways[selectedIdx];

  return (
    <SiteLayout>
      {/* HERO */}
      <section id="home" className="relative overflow-hidden">
        <div
          aria-hidden
          key={selected.name + "-bg"}
          className="absolute inset-0 -z-10 transition-[background] duration-700"
          style={{
            background: `radial-gradient(60% 60% at 70% 50%, ${selected.glow} 0%, rgba(255,255,255,0) 60%), linear-gradient(180deg, #fff, #fafafa)`,
          }}
        />
        <div className="max-w-7xl mx-auto px-6 py-20 md:py-28 grid md:grid-cols-2 gap-12 items-center">
          <div>
            <p className="text-xs font-semibold tracking-[0.2em] text-muted-foreground mb-6">
              8 COLORWAYS · 11 STRAPS · FREE SHIPPING
            </p>
            <h1 className="font-black tracking-tighter leading-[0.95] text-[clamp(3rem,8vw,6.5rem)]">
              TIME<br />REDEFINED.
            </h1>
            <p className="mt-8 text-lg text-muted-foreground max-w-md">
              Premium pocket watches engineered for everyday wear.<br />
              Eight signature colorways. Built to last.
            </p>
            <div className="mt-10 flex flex-wrap gap-3">
              <Link to="/products/$slug" params={{ slug: selected.slug }} className="inline-flex items-center gap-2 bg-foreground text-background px-6 py-3.5 rounded-full text-sm font-semibold hover:opacity-90 transition">
                Get this watch — {formatPrice(WATCH_PRICE)} <ArrowRight className="size-4" />
              </Link>
              <Link to="/" hash="straps" className="inline-flex items-center gap-2 border border-border bg-card px-6 py-3.5 rounded-full text-sm font-semibold hover:bg-muted transition">
                View Straps
              </Link>
            </div>
            <div className="mt-10">
              <p className="text-xs font-semibold tracking-widest text-muted-foreground mb-3">
                COLOR: <span className="text-foreground">{selected.name.toUpperCase()}</span>
              </p>
              <div className="flex gap-3 flex-wrap">
                {colorways.map((c, i) => (
                  <button
                    key={c.slug}
                    onClick={() => setSelectedIdx(i)}
                    aria-label={c.name}
                    aria-pressed={i === selectedIdx}
                    className={`size-8 rounded-full border-2 transition ${i === selectedIdx ? "border-foreground scale-110 ring-2 ring-foreground/10 ring-offset-2" : "border-border hover:scale-110"}`}
                    style={{ background: c.hex }}
                  />
                ))}
              </div>
            </div>
          </div>

          <div className="relative flex items-center justify-center min-h-[420px] md:min-h-[560px]">
            <div
              aria-hidden
              key={selected.name + "-glow"}
              className="absolute inset-0 rounded-full blur-3xl opacity-70 transition-opacity duration-700"
              style={{ background: `radial-gradient(circle, ${selected.glow}, transparent 60%)` }}
            />
            <img
              key={selected.img}
              src={selected.img}
              alt={selected.name}
              className="relative max-h-[520px] object-contain drop-shadow-2xl animate-in fade-in zoom-in-95 duration-500"
            />
            <div className="absolute top-6 left-2 md:left-12 bg-card border border-border rounded-2xl shadow-lg px-4 py-3 text-sm">
              <p className="font-semibold flex items-center gap-1.5"><Factory className="size-3.5" /> Direct from factory</p>
              <p className="text-xs text-muted-foreground">No middlemen</p>
            </div>
            <div className="absolute bottom-10 right-2 md:right-8 bg-card border border-border rounded-2xl shadow-lg px-4 py-3">
              <p className="text-sm font-semibold flex items-center gap-1"><Star className="size-3.5 fill-foreground" /> 4.9 / 5.0</p>
              <p className="text-xs text-muted-foreground">52 verified</p>
            </div>
          </div>
        </div>

        <div className="border-y border-border bg-card">
          <div className="max-w-7xl mx-auto px-6 py-4 flex flex-wrap items-center justify-center gap-x-10 gap-y-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-2"><Star className="size-3.5 fill-foreground text-foreground" /> 4.8 — 19 verified reviews</span>
            <span>Free worldwide shipping</span>
            <span>30-day returns</span>
            <span>12-month warranty</span>
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section className="max-w-7xl mx-auto px-6 py-20 grid sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {[
          { icon: Truck, title: "Free Shipping", sub: "Worldwide delivery" },
          { icon: Factory, title: "Manufacturer-Direct", sub: "Better quality, better price" },
          { icon: Lock, title: "Secure Checkout", sub: "SSL encrypted" },
          { icon: RotateCcw, title: "30-Day Returns", sub: "Hassle-free" },
          { icon: Shield, title: "12-Month Warranty", sub: "We've got you covered" },
        ].map((f) => (
          <div key={f.title} className="border border-border rounded-2xl p-5 bg-card hover:shadow-md hover:-translate-y-0.5 transition">
            <f.icon className="size-5 mb-3" />
            <p className="font-semibold text-sm">{f.title}</p>
            <p className="text-xs text-muted-foreground mt-1">{f.sub}</p>
          </div>
        ))}
      </section>

      {/* CRAFTSMANSHIP */}
      <section className="bg-muted/40 border-y border-border">
        <div className="max-w-7xl mx-auto px-6 py-24">
          <p className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">CRAFTSMANSHIP</p>
          <h2 className="mt-4 font-black tracking-tighter text-[clamp(2rem,5vw,4rem)] leading-[0.95] max-w-3xl">
            BUILT TO LAST.<br />DESIGNED TO STAND OUT.
          </h2>
          <p className="mt-6 max-w-2xl text-muted-foreground">
            Every NextWrist is assembled in our partner factory and inspected piece by piece
            before it ships. Premium materials, precision movement, and a finish you can feel.
          </p>

          <div className="mt-14 grid md:grid-cols-3 gap-6">
            {[
              { n: "01", title: "Premium materials", body: "Bioceramic case, stainless steel back, sapphire-coated glass." },
              { n: "02", title: "Precision movement", body: "Quartz movement engineered for reliability and battery life." },
              { n: "03", title: "Quality controlled", body: "Each piece is individually inspected before being packed and shipped." },
            ].map((c) => (
              <div key={c.n} className="bg-card border border-border rounded-3xl p-7">
                <p className="text-xs font-mono text-muted-foreground">{c.n}</p>
                <p className="mt-3 font-semibold text-lg">{c.title}</p>
                <p className="mt-2 text-sm text-muted-foreground">{c.body}</p>
              </div>
            ))}
          </div>

          <div className="mt-12 grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
            {[
              ["100%", "Inspected"],
              ["10K+", "Happy Customers"],
              ["4.9★", "Verified Rating"],
              ["12 mo", "Warranty"],
            ].map(([k, v]) => (
              <div key={v}>
                <p className="text-3xl md:text-4xl font-black tracking-tight">{k}</p>
                <p className="text-xs uppercase tracking-widest text-muted-foreground mt-1">{v}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* STRAPS */}
      <section id="straps" className="max-w-7xl mx-auto px-6 py-24 scroll-mt-20">
        <p className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">ACCESSORIES</p>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
          <h2 className="font-black tracking-tighter text-[clamp(2rem,5vw,4rem)] leading-[0.95]">PREMIUM STRAPS.</h2>
          <p className="text-sm text-muted-foreground">
            Each strap <span className="font-bold text-foreground">{formatPrice(STRAP_PRICE)}</span>
          </p>
        </div>

        <div className="mt-12 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
          {straps.map((s) => (
            <Link
              key={s.slug}
              to="/straps/$slug"
              params={{ slug: s.slug }}
              className="group border border-border rounded-2xl bg-card overflow-hidden hover:shadow-lg hover:-translate-y-0.5 transition"
            >
              <div className="aspect-square bg-muted/40 flex items-center justify-center overflow-hidden">
                <img src={s.img} alt={s.name} className="w-full h-full object-cover group-hover:scale-105 transition duration-500" />
              </div>
              <div className="p-4 flex items-center justify-between">
                <p className="font-semibold text-sm">{s.name}</p>
                <p className="text-xs font-semibold text-foreground">{formatPrice(STRAP_PRICE)}</p>
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* COLLECTION GRID */}
      <section id="watches" className="max-w-7xl mx-auto px-6 py-24 scroll-mt-20">
        <p className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">THE COLLECTION</p>
        <h2 className="mt-3 font-black tracking-tighter text-[clamp(2rem,5vw,4rem)] leading-[0.95]">
          YOUR COLOR.<br />YOUR WATCH.
        </h2>
        <p className="mt-5 text-muted-foreground max-w-lg">
          Eight signature colorways. Each one {formatPrice(WATCH_PRICE)}. Free worldwide shipping.
        </p>

        <div className="mt-14 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
          {colorways.map((c) => (
            <Link
              key={c.slug}
              to="/products/$slug"
              params={{ slug: c.slug }}
              className="group text-left border border-border rounded-3xl bg-card p-5 flex flex-col items-center hover:shadow-xl hover:-translate-y-1 transition"
            >
              <div className="relative w-full aspect-square flex items-center justify-center">
                <div aria-hidden className="absolute inset-6 rounded-full blur-2xl opacity-50" style={{ background: `radial-gradient(circle, ${c.glow}, transparent 70%)` }} />
                <img src={c.img} alt={c.name} className="relative max-h-full object-contain group-hover:scale-105 transition duration-500" />
              </div>
              <div className="mt-3 flex items-center justify-between w-full">
                <div>
                  <p className="font-semibold text-sm">{c.name}</p>
                  <p className="text-xs text-muted-foreground">{formatPrice(WATCH_PRICE)}</p>
                </div>
                <span className="size-4 rounded-full border border-border" style={{ background: c.hex }} />
              </div>
            </Link>
          ))}
        </div>

        <div className="mt-14 rounded-3xl border border-border bg-card p-8 md:p-10 flex flex-wrap items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <Sparkles className="size-6" />
            <div>
              <p className="text-xs font-semibold tracking-widest text-muted-foreground">JOIN THE CLUB</p>
              <p className="mt-1 font-bold text-lg max-w-lg">Free worldwide shipping, 30-day returns and a 12-month warranty on every order.</p>
            </div>
          </div>
          <Link to="/cart" className="inline-flex items-center gap-2 bg-foreground text-background px-6 py-3.5 rounded-full text-sm font-semibold hover:opacity-90 transition">
            View Cart <ArrowRight className="size-4" />
          </Link>
        </div>
      </section>
    </SiteLayout>
  );
}
