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
    m = re.search(r"(\d+)\s*(?:chambre|chambres|ch)\b", name.lower())
    return int(m.group(1)) if m else None

def extract_cards(page):
    page.wait_for_timeout(800)

    # scroll léger (moins de charge => moins de crash)
    for _ in range(10):
        page.mouse.wheel(0, 1200)
        page.wait_for_timeout(350)

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
            return Array.from(blocks).slice(0, 400);
        }"""
    )

    results = {}
    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue

        title = None
        for l in lines[:10]:
            if "€" in l:
                continue
            if len(l) < 6:
                continue
            if "à partir" in l.lower():
                continue
            title = l
            break

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

def scrape_batch(start_sat, end_sat, adults_list, batch_weeks=2, progress_cb=None):
    """
    Scrape seulement batch_weeks semaines, puis renvoie :
    - rows (nouvelles lignes)
    - next_cursor (prochaine date à scraper)
    """
    rows = []
    current = start_sat
    weeks_done = 0

    def cb(p, msg):
        if progress_cb:
            progress_cb(p, msg)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        while current <= end_sat and weeks_done < batch_weeks:
            week_end = current + timedelta(days=7)

            mois_label = current.strftime("%Y-%m")
            semaine_no = int(current.isocalendar().week)
            semaine_txt = f"{current.strftime('%d/%m/%Y')} - {week_end.strftime('%d/%m/%Y')}"

            for idx, adults in enumerate(adults_list, start=1):
                # contexte/page “propres” à chaque URL => moins de fuite mémoire
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = context.new_page()

                url = build_url(current, week_end, adults)
                cb(
                    0.05,
                    f"Semaine {current.strftime('%d/%m')} • Adultes {adults} • Chargement…"
                )

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=90000)
                except PlaywrightTimeoutError:
                    page.goto(url, wait_until="domcontentloaded", timeout=120000)

                cards = extract_cards(page)

                if not cards:
                    rows.append({
                        "Catégorie": None,
                        "Hébergement": None,
                        "Chambres": None,
                        "Date_début": current.strftime("%Y-%m-%d"),
                        "Date_fin": week_end.strftime("%Y-%m-%d"),
                        "Semaine": semaine_txt,
                        "Mois_label": mois_label,
                        "Semaine_n°": semaine_no,
                        "Prix (€)": None,
                        "Adultes": adults,
                        "Statut": "Aucun résultat / Complet",
                        "URL": url
                    })
                else:
                    for name, price in cards.items():
                        rows.append({
                            "Catégorie": detect_category(name),
                            "Hébergement": name,
                            "Chambres": detect_bedrooms(name),
                            "Date_début": current.strftime("%Y-%m-%d"),
                            "Date_fin": week_end.strftime("%Y-%m-%d"),
                            "Semaine": semaine_txt,
                            "Mois_label": mois_label,
                            "Semaine_n°": semaine_no,
                            "Prix (€)": price,
                            "Adultes": adults,
                            "Statut": "OK",
                            "URL": url
                        })

                page.close()
                context.close()

                # pause anti-blocage (important)
                time.sleep(1.0)

            weeks_done += 1
            # progression approx
            cb(min(0.95, weeks_done / max(1, batch_weeks)), f"✅ Semaine terminée : {semaine_txt}")
            current += timedelta(days=7)

        browser.close()

    # ordre de colonnes stable
    df = pd.DataFrame(rows)
    ordered = [
        "Catégorie", "Hébergement", "Chambres",
        "Date_début", "Date_fin", "Semaine", "Mois_label", "Semaine_n°",
        "Prix (€)", "Adultes", "Statut", "URL"
    ]
    if not df.empty:
        df = df.reindex(columns=[c for c in ordered if c in df.columns])

    next_cursor = current  # prochaine semaine à traiter
    return df.to_dict("records"), next_cursor
