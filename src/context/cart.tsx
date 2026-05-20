import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type CartItem = {
  id: string;
  type: "watch" | "strap";
  slug: string;
  name: string;
  price: number;
  img: string;
  qty: number;
};

type CartCtx = {
  items: CartItem[];
  add: (item: Omit<CartItem, "id" | "qty">, qty?: number) => void;
  remove: (id: string) => void;
  setQty: (id: string, qty: number) => void;
  clear: () => void;
  count: number;
  total: number;
};

const Ctx = createContext<CartCtx | null>(null);
const STORAGE_KEY = "nextwrist.cart.v1";

export function CartProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<CartItem[]>([]);

  useEffect(() => {
    try {
      const raw = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
      if (raw) setItems(JSON.parse(raw));
    } catch {}
  }, []);

  useEffect(() => {
    try {
      if (typeof window !== "undefined")
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    } catch {}
  }, [items]);

  const value = useMemo<CartCtx>(() => {
    const add: CartCtx["add"] = (item, qty = 1) => {
      setItems((curr) => {
        const id = `${item.type}:${item.slug}`;
        const existing = curr.find((i) => i.id === id);
        if (existing) return curr.map((i) => (i.id === id ? { ...i, qty: i.qty + qty } : i));
        return [...curr, { ...item, id, qty }];
      });
    };
    const remove: CartCtx["remove"] = (id) => setItems((c) => c.filter((i) => i.id !== id));
    const setQty: CartCtx["setQty"] = (id, qty) =>
      setItems((c) => c.map((i) => (i.id === id ? { ...i, qty: Math.max(1, qty) } : i)));
    const clear = () => setItems([]);
    const count = items.reduce((s, i) => s + i.qty, 0);
    const total = items.reduce((s, i) => s + i.qty * i.price, 0);
    return { items, add, remove, setQty, clear, count, total };
  }, [items]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCart() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useCart must be used within CartProvider");
  return v;
}
