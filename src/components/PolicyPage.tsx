import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { SiteLayout } from "@/components/SiteLayout";

export function PolicyPage({ title, updated, children }: { title: string; updated?: string; children: ReactNode }) {
  return (
    <SiteLayout>
      <article className="max-w-3xl mx-auto px-6 py-16">
        <p className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">POLICY</p>
        <h1 className="mt-4 font-black tracking-tighter text-[clamp(2rem,5vw,3.5rem)] leading-[0.95]">{title}</h1>
        {updated && <p className="mt-3 text-xs text-muted-foreground">Last updated: {updated}</p>}
        <div className="mt-10 prose prose-neutral max-w-none text-sm leading-7 space-y-5 [&_h2]:font-bold [&_h2]:text-base [&_h2]:mt-8 [&_h2]:mb-2 [&_ul]:list-disc [&_ul]:pl-5 [&_a]:underline">
          {children}
        </div>
        <div className="mt-12 pt-8 border-t border-border text-sm text-muted-foreground">
          Questions? <Link to="/contact" className="underline text-foreground">Contact us</Link>.
        </div>
      </article>
    </SiteLayout>
  );
}
