# scraper.py
import re, time
from datetime import date, timedelta
import pandas as pd
from playwright.sync_api import sync_playwright

BASE_URL = "https://reservation.secureholiday.net/fr/231/search/product-list"

def build_url(start, end, adults):
    ds = start.strftime("%d/%m/%Y")
    de = end.strftime("%d/%m/%Y")
    return (f"{BASE_URL}?searchType=exact&productType=all&filterStatus=hideFilters"
            f"&dateStart={ds}&dateEnd={de}&travelers={adults}%40")

def parse_price(txt: str):
    txt = txt.replace("\xa0", " ").strip()
    m = re.search(r"([\d\s]+(?:[.,]\d+)?)\s*€", txt)
    if not m:
        return None
    raw = m.group(1).replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except:
        return None

def extract_cards(page):
    page.wait_for_timeout(1200)
    # scroll pour charger
    last_h = 0
    for _ in range(25):
        page.mouse.wheel(0, 1200)
        page.wait_for_timeout(600)
        h = page.evaluate("() => document.body.scrollHeight")
        if h == last_h:
            break
        last_h = h

    blocks = page.evaluate(
        """() => {
            const nodes = Array.from(document.querySelectorAll("*"))
              .filter(el => el.innerText && el.innerText.includes("€"));
            const blocks = new Set();
            for (const el of nodes) {
              let p = el;
              for (let i=0; i<6 && p; i++) {
                if (p.tagName === "ARTICLE" || p.tagName === "LI" || (p.className||"").toString().toLowerCase().includes("product")) {
                  blocks.add(p);
                  break;
                }
                p = p.parentElement;
              }
            }
            return Array.from(blocks).slice(0, 250).map(b => b.innerText);
        }"""
    )

    out = []
    for btxt in blocks:
        lines = [l.strip() for l in btxt.split("\n") if l.strip()]
        if not lines:
            continue
        title = None
        for l in lines[:6]:
            if len(l) >= 6 and "€" not in l and "à partir" not in l.lower():
                title = l
                break
        price = None
        for l in lines:
            if "€" in l:
                price = parse_price(l)
                if price is not None:
                    break
        if title and price is not None:
            out.append((title, price))

    # dédup
    uniq = {}
    for t, p in out:
        if t not in uniq or p < uniq[t]:
            uniq[t] = p
    return [{"name": k, "price": v} for k, v in uniq.items()]

def run_scrape(start_sat: date, end_sat: date, adults_list):
    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        d = start_sat
        while d <= end_sat:
            end = d + timedelta(days=7)
            for adults in adults_list:
                url = build_url(d, end, adults)
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
                cards = extract_cards(page)

                if not cards:
                    rows.append({
                        "Adultes": adults,
                        "Date_début": d.isoformat(),
                        "Date_fin": end.isoformat(),
                        "Hébergement": None,
                        "Prix (€)": None,
                        "Statut": "Aucun résultat / Complet",
                        "URL": url,
                    })
                else:
                    for c in cards:
                        rows.append({
                            "Adultes": adults,
                            "Date_début": d.isoformat(),
                            "Date_fin": end.isoformat(),
                            "Hébergement": c["name"],
                            "Prix (€)": c["price"],
                            "Statut": "OK",
                            "URL": url,
                        })
                time.sleep(1.0)

            d += timedelta(days=7)

        browser.close()

    return pd.DataFrame(rows)
