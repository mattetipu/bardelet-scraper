import streamlit as st
import pandas as pd
from datetime import date
import io
import traceback
import time
import os
import subprocess
from pathlib import Path

from scraper import run_scrape

st.set_page_config(page_title="Bardelet Scraper", layout="wide")

st.title("Extraction des prix – Les Bois du Bardelet")
st.caption("SecureHoliday • Samedi → Samedi • 2/4/6/8 adultes • Export Excel")

st.warning("⚠️ Si ça ‘charge puis s’arrête’, c’est souvent Playwright (navigateurs non installés / blocage).")

# ---------------------------
# INSTALL PLAYWRIGHT BROWSERS (si manquants)
# ---------------------------
@st.cache_resource(show_spinner=False)
def ensure_playwright_browsers():
    """
    Sur Streamlit Cloud / env non-Docker, Playwright n'a PAS les navigateurs par défaut.
    On installe Chromium une fois, puis cache.
    """
    cache_dir = Path.home() / ".cache" / "ms-playwright"
    # Si le dossier n'existe pas ou ne contient pas chromium*, on installe
    has_chromium = cache_dir.exists() and any(cache_dir.glob("chromium*"))
    if not has_chromium:
        # Installation Chromium (plus robuste)
        subprocess.run(
            ["python", "-m", "playwright", "install", "chromium"],
            check=True
        )
    return True

# Lance l'installation si besoin
try:
    ensure_playwright_browsers()
except Exception as e:
    st.error("Impossible d’installer Chromium automatiquement.")
    st.code(str(e))
    st.stop()

# ---------------------------
# PARAMÈTRES
# ---------------------------
col1, col2 = st.columns(2)
with col1:
    start_sat = st.date_input("Premier samedi", value=date(2026, 4, 4))
with col2:
    end_sat = st.date_input("Dernier samedi (inclus)", value=date(2026, 9, 26))

adults_list = st.multiselect("Nombre d'adultes", [2, 4, 6, 8], default=[2, 4, 6, 8])

# état debug persistant
if "last_status" not in st.session_state:
    st.session_state["last_status"] = "Prêt"
if "last_error" not in st.session_state:
    st.session_state["last_error"] = ""
if "df" not in st.session_state:
    st.session_state["df"] = None

st.info(f"État actuel : **{st.session_state['last_status']}**")

# ---------------------------
# LANCEMENT
# ---------------------------
if st.button("🚀 Lancer l'extraction"):
    st.session_state["last_status"] = "Démarrage…"
    st.session_state["last_error"] = ""
    st.session_state["df"] = None
    st.rerun()

if st.session_state["last_status"].startswith("Démarrage"):
    with st.spinner("Extraction en cours…"):
        try:
            t0 = time.time()
            st.write("DEBUG: run_scrape(...)")
            df = run_scrape(start_sat, end_sat, adults_list)
            t1 = time.time()

            st.session_state["df"] = df
            st.session_state["last_status"] = f"Terminé ✅ en {t1 - t0:.1f}s — {len(df)} lignes"

        except Exception:
            st.session_state["last_status"] = "Erreur ❌"
            st.session_state["last_error"] = traceback.format_exc()

    st.rerun()

# ---------------------------
# AFFICHAGE ERREUR
# ---------------------------
if st.session_state["last_status"].startswith("Erreur"):
    st.error("Le scraper a planté. Copie/colle l’erreur ci-dessous et je corrige.")
    st.code(st.session_state["last_error"], language="text")

# ---------------------------
# AFFICHAGE + EXPORT
# ---------------------------
df = st.session_state["df"]
if isinstance(df, pd.DataFrame):
    if df.empty:
        st.warning("Aucune ligne retournée (complet / blocage / sélecteurs).")
    else:
        st.success(st.session_state["last_status"])
        st.dataframe(df.head(50), use_container_width=True)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Tarifs")

        st.download_button(
            "📥 Télécharger l'Excel",
            data=output.getvalue(),
            file_name="bardelet_secureholiday_avril_septembre.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
