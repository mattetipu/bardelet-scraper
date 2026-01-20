import re
import time
from datetime import timedelta
import pandas as pd
from playwright.sync_api import sync_playwright

BASE_URL = "https://reservation.secureholiday.net/fr/231/search/product-list"

# ==============================
# HELPERS
# ==============================
def build_url(start, end, adults):
    ds = start.strftime("%d/%m/%Y")
    de = end.strftime("%d/%m/%Y")
    return (
        f"{BASE_URL}"
        f"?searchType=exact&productType=all"
        f"&filterStatus=hideFilters"
        f"&dateStart={ds}&dateEnd={de}"
        f"&travelers={adults}%40"
    )

def parse_price(text):
    text = text.replace("\xa0", " ").strip()
    m = re.search(r"([\d\s]+(?:[.,]\d+)?)\s*€", text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(" ", "").replace(",", "."))
    except:
        return None

def detect_category(name):
    n = name.lower()
    if "mobil" in n:
        return "Mobil-home"
    if "chalet" in n:
        return "Chalet"
    if "emplacement" in n:
        return "Emplacement"
    if "forfait" in n:
        return "Forfait"
    return "Autre"

def detect_bedrooms(name):
    m = re.search(r"(\d+)\s*(?:chambre|chambres|ch)", name.lower())
    return int(m.group(1)) if m else None

# ==============================
# SCRAPER CORE
# ==============================
def extract_cards(page):
    page.wait_for_timeout(1200)

    # Scroll lazy-load
    last_height = 0
    for _ in range(25):
        page.mouse.wheel(0, 1200)
        page.wait_for_timeout(600)
        height = page.evaluate("() => document.body.scrollHeight")
        if height == last_height:
            break
        last_height = height

    blocks = page.evaluate(
        """() => {
            const nodes = Array.from(document.querySelectorAll("*"))
              .filter(el => el.innerText && el.innerText.includes("€"));
            const blocks = new Set();
            for (const el of nodes) {
                let p = el;
                for (let i = 0; i < 6 && p; i++) {
                    if (
                        p.tagName === "ARTICLE" ||
                        p.tagName === "LI" ||
                        (p.className || "").toLowerCase().includes("product")
                    ) {
                        blocks.add(p.innerText);
                        break;
                    }
                    p = p.parentElement;
                }
            }
            return Array.from(blocks);
        }"""
    )

    results = {}
    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue

        title = next(
            (l for l in lines[:6] if "€" not in l and len(l) > 6),
            None
        )

        price = next(
            (parse_price(l) for l in lines if "€" in l and parse_price(l)),
            None
        )

        if title and price is not None:
            if title not in results or price < results[title]:
                results[title] = price

    return results

# ==============================
# MAIN ENTRY
# ==============================
def run_scrape(start_sat, end_sat, adults_list):
    rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context()
        page = context.new_page()

        current = start_sat
        while current <= end_sat:
            week_end = current + timedelta(days=7)

            for adults in adults_list:
                url = build_url(current, week_end, adults)
                page.goto(url, wait_until="domcontentloaded", timeout=90000)

                cards = extract_cards(page)

                if not cards:
                    rows.append({
                        "Date_début": current,
                        "Date_fin": week_end,
                        "Adultes": adults,
                        "Hébergement": None,
                        "Catégorie": None,
                        "Chambres": None,
                        "Prix (€)": None,
                        "Statut": "Aucun résultat",
                        "URL": url
                    })
                else:
                    for name, price in cards.items():
                        rows.append({
                            "Date_début": current,
                            "Date_fin": week_end,
                            "Adultes": adults,
                            "Hébergement": name,
                            "Catégorie": detect_category(name),
                            "Chambres": detect_bedrooms(name),
                            "Prix (€)": price,
                            "Statut": "OK",
                            "URL": url
                        })

                time.sleep(1.2)

            current += timedelta(days=7)

        browser.close()

    return pd.DataFrame(rows)

