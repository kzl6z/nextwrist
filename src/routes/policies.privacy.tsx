import { createFileRoute } from "@tanstack/react-router";
import { PolicyPage } from "@/components/PolicyPage";

export const Route = createFileRoute("/policies/privacy")({
  head: () => ({ meta: [{ title: "Privacy Policy — NextWrist" }] }),
  component: () => (
    <PolicyPage title="Privacy Policy" updated="May 2026">
      <p>
        This policy explains how NextWrist collects and uses your personal data, in
        accordance with the EU General Data Protection Regulation (GDPR).
      </p>
      <h2>Data we collect</h2>
      <ul>
        <li><strong>Order data:</strong> name, email address, items purchased, order amount.</li>
        <li><strong>Payment data:</strong> handled by our payment processor — we never store your full card number.</li>
        <li><strong>Technical data:</strong> IP address, browser, anonymized usage statistics.</li>
      </ul>
      <h2>How we use it</h2>
      <ul>
        <li>To deliver your digital files to the email address you provide.</li>
        <li>To process payments and prevent fraud.</li>
        <li>To respond to support requests.</li>
        <li>With your consent, to send occasional product updates. You can unsubscribe at any time.</li>
      </ul>
      <h2>Data sharing</h2>
      <p>
        We share data only with the strict minimum of service providers needed to operate the
        store (payment processing, email delivery, hosting). We never sell your personal data.
      </p>
      <h2>Your rights</h2>
      <p>
        You may request access, correction, deletion, or portability of your personal data, and
        object to processing, by writing to <a href="mailto:privacy@nextwrist.online">privacy@nextwrist.online</a>.
        You also have the right to lodge a complaint with your local data protection authority
        (in France: CNIL).
      </p>
      <h2>Retention</h2>
      <p>Order records are kept for the legal accounting period (10 years in France). Marketing data is kept until you withdraw consent.</p>
    </PolicyPage>
  ),
});
