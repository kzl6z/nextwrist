#!/bin/bash
# Configure Stripe en local (.env + .dev.vars)
set -e
cd "$(dirname "$0")"

if [ -f .env ]; then
  echo "⚠️  .env existe déjà. Édite-le à la main si besoin."
else
  cp .env.example .env
  echo "✅ Fichier .env créé depuis .env.example"
fi

echo ""
echo "Ouvre .env et remplace STRIPE_SECRET_KEY par ta clé sk_live_..."
echo "Puis lance : npm run dev"
echo ""
read -r -p "Colle ta clé Stripe (sk_live_ ou sk_test_) et Entrée : " KEY

if [ -z "$KEY" ]; then
  echo "Annulé."
  exit 1
fi

# Met à jour .env
if grep -q '^STRIPE_SECRET_KEY=' .env 2>/dev/null; then
  sed -i.bak "s|^STRIPE_SECRET_KEY=.*|STRIPE_SECRET_KEY=$KEY|" .env && rm -f .env.bak
else
  echo "STRIPE_SECRET_KEY=$KEY" >> .env
fi

# Copie pour wrangler dev (Cloudflare)
echo "STRIPE_SECRET_KEY=$KEY" > .dev.vars
echo "SITE_URL=http://localhost:8080" >> .dev.vars

echo "✅ .env et .dev.vars configurés."
echo "Lance : npm run dev  puis ouvre http://localhost:8080"
