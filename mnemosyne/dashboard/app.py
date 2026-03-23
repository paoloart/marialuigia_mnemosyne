import os

import streamlit as st

st.set_page_config(
    page_title="Mnemosyne — Maria Luigia",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Inject custom CSS ─────────────────────────────────────────────────
_css_path = os.path.join(os.path.dirname(__file__), "style.css")
with open(_css_path) as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ── Sidebar branding ─────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        """
        <div style="text-align:center; padding: 1rem 0 0.5rem 0;">
            <span style="font-size: 2.2rem;">🏥</span>
            <h2 style="margin: 0.3rem 0 0 0; font-size: 1.3rem; font-weight: 800;
                        letter-spacing: -0.03em; color: #e6edf3;">
                Mnemosyne
            </h2>
            <p style="margin: 0; font-size: 0.75rem; color: #8b949e;
                       letter-spacing: 0.05em; text-transform: uppercase;">
                Maria Luigia SEO
            </p>
        </div>
        <hr style="border-color: rgba(45,51,59,0.4); margin: 0.8rem 0;">
        """,
        unsafe_allow_html=True,
    )

# ── Navigation ────────────────────────────────────────────────────────
overview = st.Page("pages/1_overview.py", title="Overview", icon="📊", default=True)
seo_audit = st.Page("pages/2_seo_audit.py", title="SEO Audit", icon="🔍")
live_canvas = st.Page("pages/3_live_canvas.py", title="Live Canvas", icon="🎨")
rtms = st.Page("pages/5_rtms.py", title="rTMS Analytics", icon="🧲")
crawler = st.Page("pages/6_site_crawler.py", title="Site Crawler", icon="🕷️")
piano = st.Page("pages/7_piano_editoriale.py", title="Piano Editoriale", icon="📋")
comandi = st.Page("pages/8_comandi.py", title="Comandi", icon="⚡")
ricerca = st.Page("pages/9_ricerca_semantica.py", title="Ricerca Semantica", icon="🔮")

pg = st.navigation([overview, seo_audit, live_canvas, rtms, crawler, piano, comandi, ricerca])
pg.run()
