import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Mail, MessageCircle, CheckCircle2 } from "lucide-react";
import { SiteLayout } from "@/components/SiteLayout";

export const Route = createFileRoute("/contact")({
  head: () => ({ meta: [{ title: "Contact — NextWrist" }, { name: "description", content: "Get in touch with the NextWrist team." }] }),
  component: ContactPage,
});

function ContactPage() {
  const [sent, setSent] = useState(false);

  return (
    <SiteLayout>
      <section className="max-w-5xl mx-auto px-6 py-16 grid md:grid-cols-2 gap-12">
        <div>
          <p className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">SUPPORT</p>
          <h1 className="mt-4 font-black tracking-tighter text-[clamp(2rem,5vw,3.5rem)] leading-[0.95]">CONTACT US.</h1>
          <p className="mt-6 text-muted-foreground max-w-md">
            Questions about your order, shipping, or anything else —
            we usually respond within 24 hours.
          </p>
          <ul className="mt-8 space-y-4 text-sm">
            <li className="flex items-center gap-3"><Mail className="size-4" /> <a href="mailto:support@nextwrist.online" className="underline">support@nextwrist.online</a></li>
            <li className="flex items-center gap-3"><MessageCircle className="size-4" /> Average reply time: under 24h</li>
          </ul>
        </div>

        {sent ? (
          <div className="border border-border rounded-2xl bg-card p-8 text-center self-start">
            <CheckCircle2 className="size-10 mx-auto" />
            <p className="mt-4 font-semibold">Message received.</p>
            <p className="mt-2 text-sm text-muted-foreground">We'll reply to you by email shortly.</p>
          </div>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); setSent(true); }} className="border border-border rounded-2xl bg-card p-6 space-y-4">
            <label className="block">
              <span className="text-xs font-semibold">Your email</span>
              <input required type="email" className="mt-1 w-full border border-border rounded-lg px-3 py-2.5 bg-background" />
            </label>
            <label className="block">
              <span className="text-xs font-semibold">Order number (optional)</span>
              <input className="mt-1 w-full border border-border rounded-lg px-3 py-2.5 bg-background" />
            </label>
            <label className="block">
              <span className="text-xs font-semibold">Message</span>
              <textarea required rows={5} className="mt-1 w-full border border-border rounded-lg px-3 py-2.5 bg-background" />
            </label>
            <button type="submit" className="w-full bg-foreground text-background px-6 py-3.5 rounded-full text-sm font-semibold hover:opacity-90 transition">Send message</button>
          </form>
        )}
      </section>
    </SiteLayout>
  );
}
