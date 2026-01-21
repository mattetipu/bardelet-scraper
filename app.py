import streamlit as st
import pandas as pd
from datetime import date
import io
from scraper import scrape_batch

st.set_page_config(page_title="Bardelet Scraper", layout="wide")

st.title("Extraction des prix – Les Bois du Bardelet")
st.caption("SecureHoliday • Samedi → Samedi • 2/4/6/8 adultes • Export Excel")
st.warning("Astuce anti-502 : lance par lots (batch). Tu pourras reprendre et télécharger à tout moment.")

col1, col2 = st.columns(2)
with col1:
    start_sat = st.date_input("Premier samedi", value=date(2026, 4, 4))
with col2:
    end_sat = st.date_input("Dernier samedi (inclus)", value=date(2026, 9, 26))

adults_list = st.multiselect("Nombre d'adultes", [2, 4, 6, 8], default=[2, 4, 6, 8])
batch_weeks = st.slider("Taille d’un batch (semaines par lancement)", 1, 6, 2)

if "rows" not in st.session_state:
    st.session_state["rows"] = []
if "cursor" not in st.session_state:
    st.session_state["cursor"] = None  # prochaine date à traiter

c1, c2, c3 = st.columns(3)
if c1.button("🆕 Nouveau run (reset)"):
    st.session_state["rows"] = []
    st.session_state["cursor"] = start_sat
    st.rerun()

if st.session_state["cursor"] is None:
    st.session_state["cursor"] = start_sat

st.info(f"Prochaine semaine à traiter : **{st.session_state['cursor']}**")

run_btn = c2.button("▶️ Lancer / Continuer (batch)")
stop_btn = c3.button("🧹 Reset complet")

if stop_btn:
    st.session_state["rows"] = []
    st.session_state["cursor"] = start_sat
    st.rerun()

progress = st.progress(0)
status = st.empty()

if run_btn:
    status.write("Batch en cours…")
    new_rows, next_cursor = scrape_batch(
        start_sat=st.session_state["cursor"],
        end_sat=end_sat,
        adults_list=adults_list,
        batch_weeks=batch_weeks,
        progress_cb=lambda p, msg: (progress.progress(p), status.write(msg)),
    )
    st.session_state["rows"].extend(new_rows)
    st.session_state["cursor"] = next_cursor
    status.write("✅ Batch terminé.")
    progress.progress(1.0)

# Affichage dataframe
df = pd.DataFrame(st.session_state["rows"])
if not df.empty:
    st.success(f"Lignes cumulées : {len(df)}")
    st.dataframe(df, use_container_width=True)

    # Export Excel à tout moment
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Tarifs")

    st.download_button(
        "📥 Télécharger l'Excel (cumul)",
        data=output.getvalue(),
        file_name="bardelet_secureholiday.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    if st.session_state["cursor"] > end_sat:
        st.balloons()
        st.success("🎉 Tout est terminé (toutes les semaines ont été traitées).")
else:
    st.warning("Aucune donnée pour l’instant. Clique sur “Nouveau run (reset)” puis lance un batch.")
