# NextWrist — Stripe + mise en ligne + Google

## 1. Clé API Stripe (panier montre + bracelet)

### Étape A — Créer la clé

1. Ouvre [https://dashboard.stripe.com/apikeys](https://dashboard.stripe.com/apikeys)
2. Mode **Test** (interrupteur en haut) pour commencer
3. Clique **Créer une clé secrète** → copie `sk_test_...`

### Étape B — Fichier local `.env`

```bash
cd /chemin/vers/nextwrist-site
cp .env.example .env
```

Édite `.env` :

```env
STRIPE_SECRET_KEY=sk_test_xxxxxxxx
SITE_URL=http://localhost:5173
```

### Étape C — Tester en local

```bash
npm run dev
```

1. Ajoute une montre + un bracelet au panier
2. Checkout → tu dois arriver sur une page Stripe avec **2 lignes** et total **84,98 €**

### Étape D — Production (Cloudflare)

```bash
npx wrangler login
npx wrangler secret put STRIPE_SECRET_KEY
# Colle sk_live_... quand tu passes en mode Live sur Stripe
```

`SITE_URL` est déjà dans `wrangler.jsonc` → `https://nextwrist.shop`

---

## 2. Payment Links (montre / bracelet seuls)

Dans [Stripe → Payment Links](https://dashboard.stripe.com/payment-links) :

Pour **chaque** lien → **Après le paiement** → URL de redirection :

```
https://nextwrist.shop/checkout/success?from=stripe
```

---

## 3. Mettre le site en ligne (hébergement)

Ce projet est fait pour **Cloudflare** (pas Google Cloud).

```bash
npm run deploy
```

Première fois :

```bash
npx wrangler login
```

Cloudflare te donne une URL du type `https://nextwrist.xxx.workers.dev`.

### Domaine nextwrist.shop

1. [Cloudflare Dashboard](https://dash.cloudflare.com) → **Workers & Pages** → ton worker **nextwrist**
2. **Settings** → **Domains & Routes** → ajoute `nextwrist.shop` et `www.nextwrist.shop`
3. DNS : si le domaine est sur Cloudflare, les enregistrements se créent souvent automatiquement

---

## 4. Apparaître sur Google (recherche)

Ce n’est **pas** le même hébergeur : Google **indexe** ton site, il ne l’héberge pas.

### A — Google Search Console

1. [https://search.google.com/search-console](https://search.google.com/search-console)
2. **Ajouter une propriété** → `https://nextwrist.shop`
3. Vérification : balise HTML ou DNS (Cloudflare → enregistrement TXT Google)
4. **Sitemaps** → soumettre `https://nextwrist.shop/sitemap.xml` (si tu en ajoutes un plus tard)

### B — Indexation plus rapide

- Liens depuis Instagram, TikTok, bio Linktree
- Page « À propos » / contact avec texte clair (montres, bracelets, livraison)

### C — SEO de base (déjà partiellement fait)

- Titres de pages (`NextWrist`, noms produits)
- Descriptions dans les meta tags des routes

---

## 5. Passer Stripe en « Live » (vrais paiements)

1. Stripe Dashboard → compléter **activation du compte** (identité, IBAN)
2. Basculer en mode **Live**
3. Nouvelle clé `sk_live_...` → `wrangler secret put STRIPE_SECRET_KEY`
4. Vérifier que les Payment Links sont aussi en mode Live

---

## Récap des commandes

| Action | Commande |
|--------|----------|
| Dev local | `npm run dev` |
| Build | `npm run build` |
| Déployer | `npm run deploy` |
| Secret Stripe prod | `npx wrangler secret put STRIPE_SECRET_KEY` |
