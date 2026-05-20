import { createFileRoute } from "@tanstack/react-router";
import { PolicyPage } from "@/components/PolicyPage";

export const Route = createFileRoute("/policies/refund")({
  head: () => ({ meta: [{ title: "Refund Policy — NextWrist" }, { name: "description", content: "Refund terms for NextWrist digital products." }] }),
  component: () => (
    <PolicyPage title="Refund Policy" updated="May 2026">
      <p>
        Because NextWrist products are <strong>digital files delivered by email</strong>, our
        refund policy is specific to digital goods and applies in addition to your statutory
        consumer rights where applicable.
      </p>
      <h2>14-day satisfaction guarantee</h2>
      <p>
        If your file was never delivered, was corrupted, or does not match the product
        purchased, you are entitled to a <strong>full refund or a redelivery</strong> within 14
        days of your purchase date.
      </p>
      <h2>EU right of withdrawal</h2>
      <p>
        In accordance with EU Directive 2011/83/EU, the right of withdrawal does not apply to
        digital content that has been delivered after the consumer's express consent and
        acknowledgement that the right is lost upon delivery. By checking the acknowledgement
        box at checkout, you accept that your file is delivered immediately and you waive your
        14-day right of withdrawal for already-delivered files.
      </p>
      <h2>How to request a refund</h2>
      <ul>
        <li>Email <a href="mailto:support@nextwrist.online">support@nextwrist.online</a> within 14 days.</li>
        <li>Include your order number and the reason for the request.</li>
        <li>We respond within 2 business days and process approved refunds within 5–10 business days to the original payment method.</li>
      </ul>
    </PolicyPage>
  ),
});
