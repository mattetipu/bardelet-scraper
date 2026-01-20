import re
import time
from datetime import timedelta
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://reservation.secureholiday.net/fr/231/search/product-list"


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


def parse_price(text: str):
    text = text.replace("\xa0", " ").strip()
    m = re.search(r"([\d\s]+(?:[.,]\d+)?)\s*€", text)
    if not m:
        return None
    raw = m.group(1).replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def detect_category(name: str) -> str:
    n = name.lower()
    if "mobil" in n or "mobile home" in n:
        return "Mobil-home"
    if "chalet" in n:
        return "Chalet"
    if "emplacement" in n:
        return "Emplacement"
    if "forfait" in n:
        return "Forfait"
    return "Autre"


def detect_bedrooms(name: str):
    # Ex: "3 chambres", "2 ch"
    m = re.search(r"(\d+)\s*(?:chambre|chambres|ch)\b", name.lower())
    return int(m.group(1)) if m else None


def extract_cards(page):
    """
    Extraction robuste sans dépendre de sélecteurs fragiles.
    On récupère des blocs parents contenant "€", puis on en déduit titre + prix.
    """
    page.wait_for_timeout(1200)

    # Scroll pour charger le lazy-load
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
              .filter(el => el && el.innerText && el.innerText.includes("€"));
            const blocks = new Set();

            for (const el of nodes) {
                let p = el;
                for (let i=0; i<7 && p; i++) {
                    const cls = (p.className || "").toString().toLowerCase();
                    if (p.tagName === "ARTICLE" || p.tagName === "LI" || cls.includes("product")) {
                        blocks.add(p.innerText);
                        break;
                    }
                    p = p.parentElement;
                }
            }
            return Array.from(blocks).slice(0, 300);
        }"""
    )

    # title -> prix le plus bas (si promo + prix barré)
    results = {}
    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue

        # titre = première ligne "logique"
        title = None
        for l in lines[:8]:
            if "€" in l:
                continue
            if len(l) < 6:
                continue
            if "à partir" in l.lower():
                continue
            title = l
            break

        # prix = premier "€" parseable
        price = None
        for l in lines:
            if "€" not in l:
                continue
            p = parse_price(l)
            if p is not None:
                price = p
                break

        if title and price is not None:
            if title not in results or price < results[title]:
                results[title] = price

    return results


def run_scrape(start_sat, end_sat, adults_list):
    rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        current = start_sat
        while current <= end_sat:
            week_end = current + timedelta(days=7)

            for adults in adults_list:
                url = build_url(current, week_end, adults)

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=90000)
                except PlaywrightTimeoutError:
                    # retry 1 fois
                    page.goto(url, wait_until="domcontentloaded", timeout=120000)

                cards = extract_cards(page)

                if not cards:
                    rows.append({
                        "Date_début": current.isoformat(),
                        "Date_fin": week_end.isoformat(),
                        "Semaine": f"{current.strftime('%d/%m/%Y')} - {week_end.strftime('%d/%m/%Y')}",
                        "Adultes": adults,
                        "Hébergement": None,
                        "Catégorie": None,
                        "Chambres": None,
                        "Prix (€)": None,
                        "Statut": "Aucun résultat / Complet",
                        "URL": url
                    })
                else:
                    for name, price in cards.items():
                        rows.append({
                            "Date_début": current.isoformat(),
                            "Date_fin": week_end.isoformat(),
                            "Semaine": f"{current.strftime('%d/%m/%Y')} - {week_end.strftime('%d/%m/%Y')}",
                            "Adultes": adults,
                            "Hébergement": name,
                            "Catégorie": detect_category(name),
                            "Chambres": detect_bedrooms(name),
                            "Prix (€)": price,
                            "Statut": "OK",
                            "URL": url
                        })

                # pause anti-blocage
                time.sleep(1.2)

            current += timedelta(days=7)

        browser.close()

    return pd.DataFrame(rows)

