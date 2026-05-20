import { createFileRoute } from "@tanstack/react-router";
import { PolicyPage } from "@/components/PolicyPage";

export const Route = createFileRoute("/policies/terms")({
  head: () => ({ meta: [{ title: "Terms of Service — NextWrist" }] }),
  component: () => (
    <PolicyPage title="Terms of Service" updated="May 2026">
      <p>
        These Terms govern your use of the NextWrist website and the purchase of our digital
        products. By using the site or placing an order, you accept these Terms.
      </p>
      <h2>1. Products</h2>
      <p>
        NextWrist sells digital editions of pocket watches and straps. Each product is a
        high-resolution image file delivered by email. <strong>No physical goods are
        shipped.</strong> Prices are shown in euros (EUR) and include applicable taxes where
        required.
      </p>
      <h2>2. Orders and payment</h2>
      <ul>
        <li>Watches are sold at €54.99 per digital edition. Straps are sold at €29.99 per digital edition.</li>
        <li>Payment is taken at the time of order via secure third-party processors.</li>
        <li>We reserve the right to refuse or cancel an order in case of suspected fraud or error.</li>
      </ul>
      <h2>3. License of use</h2>
      <p>
        Files are licensed, not sold. You receive a non-exclusive, non-transferable license for
        personal, non-commercial use. You may not redistribute, resell, sublicense or use the
        files commercially without our prior written consent.
      </p>
      <h2>4. Intellectual property</h2>
      <p>
        All content on this site — including images, designs, text, and the NextWrist brand —
        remains the exclusive property of NextWrist or its licensors.
      </p>
      <h2>5. Liability</h2>
      <p>
        To the maximum extent permitted by law, NextWrist's liability is limited to the amount
        you paid for the affected order. We are not liable for indirect or consequential damages.
      </p>
      <h2>6. Governing law</h2>
      <p>
        These Terms are governed by French law. Any dispute will be brought before the competent
        courts, without prejudice to consumer protection rules of your country of residence.
      </p>
    </PolicyPage>
  ),
});
