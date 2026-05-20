import { createFileRoute, Link } from "@tanstack/react-router";
import { XCircle } from "lucide-react";
import { SiteLayout } from "@/components/SiteLayout";

export const Route = createFileRoute("/checkout/cancel")({
  head: () => ({ meta: [{ title: "Payment cancelled — NextWrist" }] }),
  component: CheckoutCancelPage,
});

function CheckoutCancelPage() {
  return (
    <SiteLayout>
      <section className="max-w-2xl mx-auto px-6 py-24 text-center">
        <XCircle className="size-12 mx-auto text-muted-foreground" />
        <h1 className="mt-6 font-black tracking-tighter text-4xl">Payment cancelled.</h1>
        <p className="mt-4 text-muted-foreground">No charge was made. Your cart is still saved.</p>
        <div className="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            to="/checkout"
            className="inline-flex items-center justify-center bg-foreground text-background px-6 py-3.5 rounded-full text-sm font-semibold"
          >
            Try again
          </Link>
          <Link to="/cart" className="inline-flex items-center justify-center underline text-sm">
            View cart
          </Link>
        </div>
      </section>
    </SiteLayout>
  );
}
