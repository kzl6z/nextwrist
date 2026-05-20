import { createFileRoute } from "@tanstack/react-router";
import { PolicyPage } from "@/components/PolicyPage";

export const Route = createFileRoute("/policies/delivery")({
  head: () => ({ meta: [{ title: "Digital Delivery Policy — NextWrist" }, { name: "description", content: "How NextWrist delivers digital watch editions by email." }] }),
  component: () => (
    <PolicyPage title="Digital Delivery Policy" updated="May 2026">
      <p>
        NextWrist sells <strong>digital products</strong>. After your purchase, you receive a
        high-resolution image of your chosen watch (and any straps in your order) sent
        directly to the email address you provide at checkout.
      </p>
      <h2>What you receive</h2>
      <ul>
        <li>One high-resolution image file per watch or strap purchased.</li>
        <li>Print-ready quality, suitable for personal use, viewing, and printing.</li>
        <li>No physical item is shipped. No tracking number is generated.</li>
      </ul>
      <h2>Delivery time</h2>
      <p>
        Files are typically delivered within 5 minutes of successful payment. In rare cases
        (technical issues, payment review), delivery may take up to 24 hours.
      </p>
      <h2>Didn't receive your file?</h2>
      <ul>
        <li>Check your spam, promotions, and junk folders.</li>
        <li>Verify the email address used at checkout is correct.</li>
        <li>If you still haven't received it after 24h, contact us at <a href="mailto:support@nextwrist.online">support@nextwrist.online</a> with your order number.</li>
      </ul>
      <h2>License</h2>
      <p>
        Files are licensed for <strong>personal, non-commercial use</strong>. Redistribution,
        resale, or commercial use is prohibited without written permission.
      </p>
    </PolicyPage>
  ),
});
