import { createFileRoute } from "@tanstack/react-router";
import { PolicyPage } from "@/components/PolicyPage";

export const Route = createFileRoute("/policies/legal")({
  head: () => ({ meta: [{ title: "Legal Notice — NextWrist" }] }),
  component: () => (
    <PolicyPage title="Legal Notice" updated="May 2026">
      <h2>Publisher</h2>
      <p>
        Site published by <strong>NextWrist</strong>.<br />
        Contact: <a href="mailto:support@nextwrist.online">support@nextwrist.online</a>
      </p>
      <h2>Activity</h2>
      <p>
        NextWrist sells digital editions (high-resolution image files) of pocket watches and
        straps, delivered by email. No physical goods are shipped.
      </p>
      <h2>Hosting</h2>
      <p>
        The site is hosted on Cloudflare global edge network. For details, see the Cloudflare
        privacy policy.
      </p>
      <h2>Intellectual property</h2>
      <p>
        All elements of this site (texts, images, graphics, logo, brand) are protected by
        applicable intellectual property laws and remain the property of NextWrist or its
        licensors.
      </p>
      <h2>Mediation</h2>
      <p>
        In case of dispute, EU consumers may use the European Commission's online dispute
        resolution platform: <a href="https://ec.europa.eu/consumers/odr" target="_blank" rel="noopener">https://ec.europa.eu/consumers/odr</a>.
      </p>
    </PolicyPage>
  ),
});
