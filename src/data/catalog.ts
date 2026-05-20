import watch1 from "@/assets/watch-1.avif";
import watch2 from "@/assets/watch-2.avif";
import watch3 from "@/assets/watch-3.avif";
import watch4 from "@/assets/watch-4.avif";
import watch5 from "@/assets/watch-5.png";
import watch6 from "@/assets/watch-6.avif";
import watch7 from "@/assets/watch-7.avif";
import watch8 from "@/assets/watch-8.avif";

export const WATCH_PRICE = 54.99;
export const STRAP_PRICE = 29.99;
export const BUNDLE_PRICE = WATCH_PRICE + STRAP_PRICE;
export const CDN = "https://media.base44.com/images/public/6a073b0cba0fa27185a0b7aa";

export type Colorway = {
  slug: string;
  name: string;
  hex: string;
  glow: string;
  img: string;
};

export const colorways: Colorway[] = [
  { slug: "emerald-eight", name: "Emerald Eight",   hex: "#007b35", glow: "rgba(0,123,53,0.35)",   img: watch1 },
  { slug: "coral-pink",    name: "Coral Pink",      hex: "#d98b96", glow: "rgba(217,139,150,0.45)", img: watch2 },
  { slug: "steel-blue",    name: "Steel Blue",      hex: "#445f82", glow: "rgba(68,95,130,0.4)",   img: watch3 },
  { slug: "sage-mint",     name: "Sage Mint",       hex: "#a8b97d", glow: "rgba(168,185,125,0.4)", img: watch4 },
  { slug: "navy-blaze",    name: "Navy Blaze",      hex: "#233a6e", glow: "rgba(255,90,30,0.35)",  img: watch5 },
  { slug: "blush-rose",    name: "Blush Rose",      hex: "#e2bcb9", glow: "rgba(226,188,185,0.5)", img: watch6 },
  { slug: "arctic-white",  name: "Arctic White",    hex: "#efefef", glow: "rgba(220,220,220,0.5)", img: watch7 },
  { slug: "stealth-black", name: "Stealth Black",   hex: "#1a1a1c", glow: "rgba(0,0,0,0.25)",      img: watch8 },
];

export type Strap = { slug: string; name: string; img: string };

export const straps: Strap[] = [
  { slug: "hot-pink",        name: "Hot Pink",        img: `${CDN}/3babd49c7_IMG_0019.webp` },
  { slug: "baby-pink",       name: "Baby Pink",       img: `${CDN}/90f7454d5_IMG_0024.webp` },
  { slug: "emerald",         name: "Emerald",         img: `${CDN}/458f27432_IMG_0021.webp` },
  { slug: "lime-green",      name: "Lime Green",      img: `${CDN}/593e2b2fb_IMG_0022.webp` },
  { slug: "rainbow-crystal", name: "Rainbow Crystal", img: `${CDN}/760929093_IMG_0025.webp` },
  { slug: "stealth-black",   name: "Stealth Black",   img: `${CDN}/cdc5afb2f_IMG_0026.webp` },
  { slug: "midnight-black",  name: "Midnight Black",  img: `${CDN}/6da1f6e42_IMG_0016.webp` },
  { slug: "midnight-navy",   name: "Midnight Navy",   img: `${CDN}/6e2fce8f6_IMG_0028.webp` },
  { slug: "ice-blue",        name: "Ice Blue",        img: `${CDN}/8e0ab8705_IMG_0027.webp` },
  { slug: "orange-navy",     name: "Orange & Navy",   img: `${CDN}/0dab15901_IMG_0018.webp` },
  { slug: "deep-navy",       name: "Deep Navy",       img: `${CDN}/0817fed28_IMG_0017.webp` },
];

export const formatPrice = (n: number) =>
  new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(n);
