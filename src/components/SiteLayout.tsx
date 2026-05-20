import { Link } from "@tanstack/react-router";
import { ShoppingBag } from "lucide-react";
import type { ReactNode } from "react";
import { useCart } from "@/context/cart";

export const Logo = ({ className = "" }: { className?: string }) => (
  <span className={`font-black tracking-tight ${className}`}>
    NEXT<span className="text-muted-foreground font-light">WRIST</span>
  </span>
);

export function SiteHeader() {
  const { count } = useCart();
  return (
    <header className="sticky top-0 z-50 bg-background/80 backdrop-blur border-b border-border">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between px-4 md:px-6">
        <Link to="/" aria-label="NextWrist home"><Logo className="text-lg" /></Link>
        <nav className="hidden md:flex items-center gap-10 text-xs font-semibold tracking-widest text-muted-foreground">
          <Link to="/" className="hover:text-foreground transition" activeOptions={{ exact: true }} activeProps={{ className: "text-foreground" }}>HOME</Link>
          <Link to="/" hash="watches" className="hover:text-foreground transition">WATCHES</Link>
          <Link to="/" hash="straps" className="hover:text-foreground transition">STRAPS</Link>
          <Link to="/contact" className="hover:text-foreground transition" activeProps={{ className: "text-foreground" }}>CONTACT</Link>
        </nav>
        <Link to="/cart" aria-label="Cart" className="relative p-2 rounded-full hover:bg-muted transition">
          <ShoppingBag className="size-5" />
          <span className="absolute -top-0.5 -right-0.5 size-4 rounded-full bg-foreground text-background text-[10px] font-bold flex items-center justify-center">{count}</span>
        </Link>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-card mt-auto">
      <div className="max-w-7xl mx-auto px-6 py-12 grid gap-10 md:grid-cols-4">
        <div>
          <Logo className="text-lg" />
          <p className="mt-3 text-xs text-muted-foreground max-w-xs">
            Premium pocket watches. Eight signature colorways, shipped worldwide.
          </p>
        </div>
        <div>
          <p className="text-xs font-semibold tracking-widest mb-3">SHOP</p>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><Link to="/" hash="watches" className="hover:text-foreground">Watches</Link></li>
            <li><Link to="/" hash="straps" className="hover:text-foreground">Straps</Link></li>
            <li><Link to="/cart" className="hover:text-foreground">Cart</Link></li>
          </ul>
        </div>
        <div>
          <p className="text-xs font-semibold tracking-widest mb-3">POLICIES</p>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><Link to="/policies/delivery" className="hover:text-foreground">Shipping & Delivery</Link></li>
            <li><Link to="/policies/refund" className="hover:text-foreground">Refund Policy</Link></li>
            <li><Link to="/policies/terms" className="hover:text-foreground">Terms of Service</Link></li>
            <li><Link to="/policies/privacy" className="hover:text-foreground">Privacy Policy</Link></li>
            <li><Link to="/policies/legal" className="hover:text-foreground">Legal Notice</Link></li>
          </ul>
        </div>
        <div>
          <p className="text-xs font-semibold tracking-widest mb-3">SUPPORT</p>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><Link to="/contact" className="hover:text-foreground">Contact us</Link></li>
            <li><a href="mailto:support@nextwrist.online" className="hover:text-foreground">support@nextwrist.online</a></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-border">
        <div className="max-w-7xl mx-auto px-6 py-5 flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
          <p>© {new Date().getFullYear()} NextWrist. All rights reserved.</p>
          <p>Free worldwide shipping · 30-day returns</p>
        </div>
      </div>
    </footer>
  );
}

export function SiteLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground font-sans antialiased">
      <SiteHeader />
      <main className="flex-1">{children}</main>
      <SiteFooter />
    </div>
  );
}
