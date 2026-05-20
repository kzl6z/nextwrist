import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { getStripe } from "@/lib/stripe";

export const getStripeCheckoutSession = createServerFn({ method: "GET" })
  .inputValidator(z.object({ sessionId: z.string().min(1) }))
  .handler(async ({ data }) => {
    const stripe = getStripe();
    const session = await stripe.checkout.sessions.retrieve(data.sessionId);

    if (session.payment_status !== "paid") {
      throw new Error("Payment not completed");
    }

    return {
      email: session.customer_details?.email ?? session.customer_email ?? "",
      name: session.metadata?.customer_name ?? "",
      amountTotal: session.amount_total ?? 0,
      currency: session.currency ?? "eur",
    };
  });
