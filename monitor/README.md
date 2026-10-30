# Monitor cursanți — raport de luni dimineața

Trage din fiecare magazin Shopify (comenzi, vânzări, produse, comenzi netrimise) și din Google Ads
(cost, conversii, ROAS) ultimele 7 zile, aplică reguli (🔴🟠🟢), cere opțional o analiză de la Claude
și trimite totul pe Telegram. Cursanții fără reclame apar doar cu partea de Shopify.

## Setup (o singură dată)

1. **Telegram**: @BotFather → `/newbot` → ia tokenul. Scrie-i botului un mesaj, apoi deschide
   `https://api.telegram.org/bot<TOKEN>/getUpdates` și copiază `chat.id`.
2. **Shopify** (magazinele din aceeași organizație): în Dev Dashboard creează O aplicație cu scope-uri
   `read_orders`, `read_products`; Release; instalează-o pe fiecare magazin (Stores → Install).
   Pune `client_id` și `client_secret` în `shopify_app` din students.json. Scriptul își ia singur
   tokenul la fiecare rulare (valabil 24h). Google Ads e opțional: se poate face separat, prin Chrome.
3. **Google Ads**: conturile cursanților legate la MCC-ul tău; ai nevoie de developer token (din MCC,
   API Center) și OAuth client + refresh token. Verifică versiunea API curentă (`GOOGLE_ADS_API_VERSION`).
4. Copiază `students.example.json` → `students.json`, completează (fișierul e în .gitignore).
5. Test: `python3 monitor/weekly_report.py --demo`, apoi `--dry-run`, apoi fără flag.

## Rulare automată (GitHub Actions, gratuit)

În repo: Settings → Secrets and variables → Actions, adaugă:
`STUDENTS_JSON` (tot conținutul din students.json), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
și opțional `ANTHROPIC_API_KEY` (analiza AI, costă câțiva cenți/rulare).
Workflow-ul rulează luni 06:00 UTC; îl poți porni și manual din tab-ul Actions.
Ideal ca repo-ul să fie **privat**; tokenurile stau doar în Secrets, nu în cod.
