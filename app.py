import streamlit as st
import pandas as pd
from datetime import date
from scraper import run_scrape

st.set_page_config(page_title="Bardelet Scraper", layout="wide")

st.title("Extraction des prix – Les Bois du Bardelet")
st.caption("SecureHoliday • Samedi → Samedi • 2/4/6/8 adultes • Export Excel")

st.warning(
    "⚠️ Le scraping peut prendre plusieurs minutes. "
    "Évite de relancer trop souvent pour ne pas te faire bloquer."
)

col1, col2 = st.columns(2)

with col1:
    start_sat = st.date_input("Premier samedi", value=date(2026, 4, 4))

with col2:
    end_sat = st.date_input("Dernier samedi (inclus)", value=date(2026, 9, 26))

adults_list = st.multiselect("Nombre d'adultes", [2, 4, 6, 8], default=[2, 4, 6, 8])

if st.button("🚀 Lancer l'extraction"):
    with st.spinner("Extraction en cours..."):
        df = run_scrape(start_sat, end_sat, adults_list)
        st.session_state["df"] = df

if "df" in st.session_state:
    df = st.session_state["df"]

    st.success(f"Terminé ✅  ({len(df)} lignes)")
    st.dataframe(df, use_container_width=True)

    # Export Excel
    import io
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Tarifs")

    st.download_button(
        "📥 Télécharger l'Excel",
        data=output.getvalue(),
        file_name="bardelet_secureholiday_avril_septembre.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
