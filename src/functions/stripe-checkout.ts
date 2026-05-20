import { createServerFn } from "@tanstack/react-start";
import { getRequest } from "@tanstack/react-start/server";
import { z } from "zod";
import { getSiteOrigin, getStripe, toAbsoluteImageUrl } from "@/lib/stripe";

const checkoutItemSchema = z.object({
  name: z.string().min(1),
  slug: z.string().min(1),
  type: z.enum(["watch", "strap"]),
  price: z.number().positive(),
  qty: z.number().int().positive(),
  img: z.string(),
});

const checkoutInputSchema = z.object({
  email: z.string().email(),
  name: z.string().min(1),
  items: z.array(checkoutItemSchema).min(1),
});

export const createStripeCheckout = createServerFn({ method: "POST" })
  .inputValidator(checkoutInputSchema)
  .handler(async ({ data }) => {
    try {
      const stripe = getStripe();
      const request = getRequest();
      const origin = getSiteOrigin(request);

      const line_items = data.items.map((item) => {
        const image = toAbsoluteImageUrl(origin, item.img);
        return {
          quantity: item.qty,
          price_data: {
            currency: "eur",
            unit_amount: Math.round(item.price * 100),
            product_data: {
              name: item.name,
              ...(image ? { images: [image] } : {}),
              metadata: { slug: item.slug, type: item.type },
            },
          },
        };
      });

      const session = await stripe.checkout.sessions.create({
        mode: "payment",
        customer_email: data.email,
        line_items,
        success_url: `${origin}/checkout/success?session_id={CHECKOUT_SESSION_ID}`,
        cancel_url: `${origin}/checkout/cancel`,
        metadata: { customer_name: data.name },
        shipping_address_collection: {
          allowed_countries: ["FR", "BE", "CH", "LU", "DE", "ES", "IT", "PT", "NL", "GB", "US", "CA"],
        },
      });

      if (!session.url) {
        throw new Error("Stripe did not return a checkout URL");
      }

      return { url: session.url };
    } catch (err) {
      if (err instanceof Error && err.message.includes("STRIPE_SECRET_KEY")) {
        throw new Error(
          "Clé Stripe manquante : crée un fichier .env avec STRIPE_SECRET_KEY=sk_live_... puis relance npm run dev",
        );
      }
      const stripeMsg =
        err && typeof err === "object" && "message" in err ? String((err as { message: string }).message) : null;
      console.error("[stripe-checkout]", err);
      throw new Error(stripeMsg ?? "Erreur Stripe lors de la création du paiement");
    }
  });
