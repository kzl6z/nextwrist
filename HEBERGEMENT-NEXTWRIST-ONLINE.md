# Héberger nextwrist.online (gratuit avec Cloudflare)

Tu n’as **pas besoin** d’un hébergeur payant type OVH « hébergement web » en plus.
Ton site NextWrist est une app **Cloudflare Workers** — Cloudflare = hébergement + CDN + HTTPS.

Tu as déjà :
- le **nom de domaine** `nextwrist.online` (chez ton registrar)
- le **code** du site
- le worker **nextwrist** uploadé sur Cloudflare

Il reste à **relier le domaine au worker**.

---

## Étape 1 — Ajouter le domaine sur Cloudflare (gratuit)

1. Va sur [https://dash.cloudflare.com](https://dash.cloudflare.com) (compte `teamkozlo@gmail.com`).
2. Clique **Add a site** / **Ajouter un site**.
3. Entre : `nextwrist.online`
4. Choisis le plan **Free**.
5. Cloudflare te donne **2 nameservers** (ex. `ada.ns.cloudflare.com` et `bob.ns.cloudflare.com`).

---

## Étape 2 — Chez ton vendeur de domaine

Là où tu as acheté `nextwrist.online` (OVH, Namecheap, Google Domains, etc.) :

1. Ouvre la gestion DNS / nameservers du domaine.
2. Remplace les nameservers par ceux de Cloudflare (étape 1).
3. Attends **15 min à 48 h** (souvent < 2 h).

---

## Étape 3 — Brancher le site (Worker)

1. [Workers → nextwrist](https://dash.cloudflare.com/83e370e9083b74f393426b370e2e6c33/workers/services/view/nextwrist)
2. **Settings** → **Domains & Routes** → **Add** → **Custom Domain**
3. Ajoute :
   - `nextwrist.online`
   - `www.nextwrist.online` (optionnel)

Cloudflare active HTTPS automatiquement.

---

## Étape 4 — Redéployer le site

Dans le terminal :

```bash
cd ~/Desktop/projet/nextwrist/nextwrist-site
npm run deploy
```

(`SITE_URL` est configuré sur `https://nextwrist.online` dans `wrangler.jsonc`.)

---

## Étape 5 — Stripe

Sur **chaque** Payment Link (montre, bracelet, pack), URL après paiement :

```
https://nextwrist.online/checkout/success?from=stripe
```

---

## Étape 6 — Google (recherche)

[Google Search Console](https://search.google.com/search-console) → propriété `https://nextwrist.online` → vérification DNS (TXT dans Cloudflare).

---

## Résumé des coûts

| Service | Coût |
|---------|------|
| Domaine nextwrist.online | Déjà payé |
| Cloudflare Workers (hébergement) | **Gratuit** (plan Free) |
| Stripe | Commission par vente |

---

## Email (optionnel)

Pour `support@nextwrist.online` : Cloudflare **Email Routing** (gratuit) ou boîte chez ton registrar.
