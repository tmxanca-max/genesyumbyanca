#!/usr/bin/env python3
"""Raport săptămânal pentru cursanți: Shopify + Google Ads -> analiză -> Telegram.

Rulare:
  python monitor/weekly_report.py --demo            # date inventate, fără rețea
  python monitor/weekly_report.py --dry-run         # date reale, tipărește în consolă
  python monitor/weekly_report.py                   # date reale, trimite pe Telegram

Config: monitor/students.json (nu se comite) sau env STUDENTS_JSON.
Doar biblioteca standard; nu are nevoie de pip install.
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2025-07")
# Versiunile Google Ads API expiră; verifică cea curentă și setează env dacă e nevoie.
GADS_API_VERSION = os.environ.get("GOOGLE_ADS_API_VERSION", "v22")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")


def http_json(url, data=None, headers=None, method=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


# ---------- Shopify ----------

def shopify_gql(student, query, variables=None):
    shop = student["shopify_domain"]
    token = student["shopify_token"]
    out = http_json(
        f"https://{shop}/admin/api/{SHOPIFY_API_VERSION}/graphql.json",
        {"query": query, "variables": variables or {}},
        {"X-Shopify-Access-Token": token},
    )
    if out.get("errors"):
        raise RuntimeError(f"Shopify: {out['errors']}")
    return out["data"]


ORDERS_Q = """
query($q: String!, $after: String) {
  orders(first: 100, query: $q, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      createdAt cancelledAt displayFinancialStatus displayFulfillmentStatus
      totalPriceSet { shopMoney { amount currencyCode } }
    }
  }
}"""

COUNTS_Q = """
{
  active: productsCount(query: "status:active") { count }
  draft: productsCount(query: "status:draft") { count }
  unfulfilled: orders(first: 100, query: "fulfillment_status:unfulfilled status:open") {
    nodes { createdAt }
  }
}"""


def fetch_shopify(student, since):
    orders, after = [], None
    q = f"created_at:>={since.strftime('%Y-%m-%d')}"
    while True:
        d = shopify_gql(student, ORDERS_Q, {"q": q, "after": after})["orders"]
        orders += d["nodes"]
        if not d["pageInfo"]["hasNextPage"]:
            break
        after = d["pageInfo"]["endCursor"]
    orders = [o for o in orders if not o["cancelledAt"]]
    c = shopify_gql(student, COUNTS_Q)
    now = datetime.now(timezone.utc)
    stale = [
        o for o in c["unfulfilled"]["nodes"]
        if now - datetime.fromisoformat(o["createdAt"].replace("Z", "+00:00")) > timedelta(hours=48)
    ]
    revenue = sum(float(o["totalPriceSet"]["shopMoney"]["amount"]) for o in orders)
    cur = orders[0]["totalPriceSet"]["shopMoney"]["currencyCode"] if orders else None
    return {
        "orders_7d": len(orders),
        "revenue_7d": round(revenue, 2),
        "currency": cur,
        "products_active": c["active"]["count"],
        "products_draft": c["draft"]["count"],
        "unfulfilled_over_48h": len(stale),
    }


# ---------- Google Ads ----------

def gads_token(client_id, client_secret, refresh_token):
    data = urllib.parse.urlencode({
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())["access_token"]


def fetch_gads(student, gads):
    cid = student["google_ads_customer_id"].replace("-", "")
    token = gads_token(gads["client_id"], gads["client_secret"], gads["refresh_token"])
    gaql = (
        "SELECT metrics.cost_micros, metrics.clicks, metrics.impressions, "
        "metrics.conversions, metrics.conversions_value "
        "FROM customer WHERE segments.date DURING LAST_7_DAYS"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "developer-token": gads["developer_token"],
        "login-customer-id": gads["mcc_id"].replace("-", ""),
    }
    out = http_json(
        f"https://googleads.googleapis.com/{GADS_API_VERSION}/customers/{cid}/googleAds:search",
        {"query": gaql}, headers,
    )
    cost = clicks = impr = conv = val = 0.0
    for row in out.get("results", []):
        m = row["metrics"]
        cost += int(m.get("costMicros", 0)) / 1e6
        clicks += int(m.get("clicks", 0))
        impr += int(m.get("impressions", 0))
        conv += float(m.get("conversions", 0))
        val += float(m.get("conversionsValue", 0))
    return {
        "spend_7d": round(cost, 2), "clicks_7d": int(clicks), "impressions_7d": int(impr),
        "conversions_7d": round(conv, 1), "conv_value_7d": round(val, 2),
        "roas_7d": round(val / cost, 2) if cost else None,
        "cpc_7d": round(cost / clicks, 2) if clicks else None,
    }


# ---------- reguli (fără AI) ----------

def assess(student, shop, ads):
    flags = []  # (nivel, text)  nivel: 🔴 🟠 🟢
    be = student.get("breakeven_roas", 2.0)
    if shop["products_active"] == 0 and shop["products_draft"] == 0:
        stage = "Magazin gol"
    elif shop["products_active"] == 0:
        stage = "Produse în draft"
        flags.append(("🟠", f"{shop['products_draft']} produse draft, niciunul activ"))
    elif not ads or ads["spend_7d"] == 0:
        stage = "Pre-ads" if shop["orders_7d"] == 0 else "Vânzări organice"
        if shop["orders_7d"] == 0:
            flags.append(("🟠", "Fără reclame și fără comenzi"))
    else:
        stage = "Ads active"
    if ads and ads["spend_7d"] > 0:
        if ads["conversions_7d"] == 0 and ads["spend_7d"] >= student.get("kill_spend", 50):
            flags.append(("🔴", f"Cheltuit {ads['spend_7d']} fără nicio conversie"))
        elif ads["roas_7d"] is not None and ads["roas_7d"] < be:
            flags.append(("🟠", f"ROAS {ads['roas_7d']} sub break-even {be}"))
        elif ads["roas_7d"] is not None:
            flags.append(("🟢", f"ROAS {ads['roas_7d']} peste break-even {be}"))
    if shop["unfulfilled_over_48h"]:
        flags.append(("🔴", f"{shop['unfulfilled_over_48h']} comenzi netrimise de peste 48h"))
    return stage, flags


# ---------- Claude (opțional) ----------

def claude_summary(results):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    prompt = (
        "Ești mentor de dropshipping Google Shopping. Mai jos sunt datele ultimelor 7 zile pentru "
        "cursanții mei. Scrie în română, scurt: (1) 3 priorități pentru mine luni dimineața, "
        "în ordine, cu numele cursantului; (2) pentru fiecare cursant o singură recomandare concretă. "
        "Nu inventa cifre care nu apar în date. Date:\n" + json.dumps(results, ensure_ascii=False)
    )
    out = http_json(
        "https://api.anthropic.com/v1/messages",
        {"model": CLAUDE_MODEL, "max_tokens": 1500, "messages": [{"role": "user", "content": prompt}]},
        {"x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    return "".join(b.get("text", "") for b in out["content"])


# ---------- raport + Telegram ----------

def render(results, ai):
    today = datetime.now().strftime("%d.%m.%Y")
    lines = [f"📊 Raport săptămânal cursanți — {today}", ""]
    for r in results:
        lines.append(f"▪ {r['name']} — {r['stage']}")
        if r.get("error"):
            lines.append(f"   ⚠ Eroare date: {r['error']}")
            continue
        s, a = r["shop"], r.get("ads")
        cur = s["currency"] or ""
        lines.append(f"   Shopify: {s['orders_7d']} comenzi, {s['revenue_7d']} {cur} | "
                     f"produse active {s['products_active']}, draft {s['products_draft']}")
        if a:
            lines.append(f"   Ads: {a['spend_7d']} cheltuit, {a['conversions_7d']} conv, ROAS {a['roas_7d']}, CPC {a['cpc_7d']}")
        for lvl, txt in r["flags"]:
            lines.append(f"   {lvl} {txt}")
        lines.append("")
    if ai:
        lines += ["— Analiză —", ai]
    return "\n".join(lines)


def telegram_send(text):
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    for i in range(0, len(text), 3900):
        http_json(f"https://api.telegram.org/bot{token}/sendMessage",
                  {"chat_id": chat, "text": text[i:i + 3900]})


DEMO = [
    {"name": "Ana", "shop": {"orders_7d": 6, "revenue_7d": 412.5, "currency": "USD", "products_active": 24,
                              "products_draft": 3, "unfulfilled_over_48h": 1},
     "ads": {"spend_7d": 180.0, "clicks_7d": 210, "impressions_7d": 9000, "conversions_7d": 6,
             "conv_value_7d": 412.5, "roas_7d": 2.29, "cpc_7d": 0.86}, "be": 2.0},
    {"name": "Mihai", "shop": {"orders_7d": 0, "revenue_7d": 0, "currency": None, "products_active": 12,
                                "products_draft": 0, "unfulfilled_over_48h": 0},
     "ads": {"spend_7d": 95.0, "clicks_7d": 80, "impressions_7d": 4000, "conversions_7d": 0,
             "conv_value_7d": 0, "roas_7d": 0.0, "cpc_7d": 1.19}, "be": 2.0},
    {"name": "Ioana", "shop": {"orders_7d": 0, "revenue_7d": 0, "currency": None, "products_active": 0,
                                 "products_draft": 15, "unfulfilled_over_48h": 0},
     "ads": None, "be": 2.0},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "students.json"))
    args = ap.parse_args()

    results = []
    if args.demo:
        for d in DEMO:
            st = {"breakeven_roas": d["be"]}
            stage, flags = assess(st, d["shop"], d["ads"])
            results.append({"name": d["name"], "stage": stage, "shop": d["shop"], "ads": d["ads"], "flags": flags})
    else:
        raw = os.environ.get("STUDENTS_JSON")
        cfg = json.loads(raw) if raw else json.load(open(args.config))
        since = datetime.now(timezone.utc) - timedelta(days=7)
        for st in cfg["students"]:
            r = {"name": st["name"]}
            try:
                shop = fetch_shopify(st, since)
                ads = fetch_gads(st, cfg["google_ads"]) if st.get("google_ads_customer_id") else None
                r["stage"], r["flags"] = assess(st, shop, ads)
                r["shop"], r["ads"] = shop, ads
            except Exception as e:  # un cursant căzut nu oprește raportul
                r["stage"], r["error"], r["flags"] = "Date indisponibile", str(e)[:200], []
            results.append(r)

    ai = None if args.demo else claude_summary(results)
    text = render(results, ai)
    if args.demo or args.dry_run:
        print(text)
    else:
        telegram_send(text)


if __name__ == "__main__":
    sys.exit(main())
