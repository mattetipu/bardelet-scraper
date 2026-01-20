import streamlit as st
import pandas as pd
from datetime import date
from scraper import run_scrape
import io

# ---------------------------
# CONFIG
# ---------------------------
st.set_page_config(
    page_title="Bardelet Scraper",
    layout="wide"
)

st.title("Extraction des prix – Les Bois du Bardelet")
st.caption("SecureHoliday • Samedi → Samedi • 2 / 4 / 6 / 8 adultes • Export Excel")

st.warning(
    "⚠️ Le scraping peut prendre plusieurs minutes. "
    "Ne relance pas plusieurs fois d'affilée."
)

# ---------------------------
# PARAMÈTRES
# ---------------------------
col1, col2 = st.columns(2)

with col1:
    start_sat = st.date_input(
        "Premier samedi",
        value=date(2026, 4, 4)
    )

with col2:
    end_sat = st.date_input(
        "Dernier samedi (inclus)",
        value=date(2026, 9, 26)
    )

adults_list = st.multiselect(
    "Nombre d'adultes",
    [2, 4, 6, 8],
    default=[2, 4, 6, 8]
)

# ---------------------------
# LANCEMENT SCRAPING
# ---------------------------
if st.button("🚀 Lancer l'extraction"):
    with st.spinner("Extraction en cours..."):
        df = run_scrape(start_sat, end_sat, adults_list)

        # DEBUG VISUEL (IMPORTANT)
        st.subheader("🔎 DEBUG – Vérification des données")
        st.write("Nombre total de lignes :", len(df))
        st.dataframe(df.head(20), use_container_width=True)

        # Sauvegarde en session
        st.session_state["df"] = df

# ---------------------------
# AFFICHAGE + EXPORT
# ---------------------------
if "df" in st.session_state:
    df = st.session_state["df"]

    if df.empty:
        st.error("❌ Aucune donnée récupérée (site bloqué ou aucune disponibilité).")
    else:
        st.success(f"✅ Extraction terminée — {len(df)} lignes")

        st.subheader("📊 Données complètes")
        st.dataframe(df, use_container_width=True)

        # Création Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Tarifs")

        st.download_button(
            label="📥 Télécharger l'Excel",
            data=output.getvalue(),
            file_name="bardelet_secureholiday_avril_septembre.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
