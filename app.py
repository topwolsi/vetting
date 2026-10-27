"""Streamlit Cloud entry point.

The app itself is the static page index.html. Streamlit renders it inside an iframe
(st.components.v1.html), so everything the page loads by relative path must be inlined:
fleet-data.js goes into the <script> tag and the vessel images become data: URIs.
Data entered by users stays in each viewer's browser (IndexedDB), exactly as when
index.html is opened locally.

Run locally:  streamlit run app.py
"""
import base64
import mimetypes
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).parent
IMG_PREFIX = "Vetting_Test_Data_v1/images/"

st.set_page_config(page_title="현대제철 선박 Vetting 시스템", page_icon="⚓", layout="wide")
# Streamlit 기본 여백·헤더를 줄여 앱이 화면을 최대한 쓰도록 한다
st.markdown("""<style>
  .block-container{padding:0.6rem 0.6rem 0 0.6rem;max-width:100%}
  header[data-testid="stHeader"]{height:0;visibility:hidden}
  footer{visibility:hidden}
</style>""", unsafe_allow_html=True)


@st.cache_data
def build_page(mtimes: tuple) -> str:   # mtimes: cache key so edited files are picked up
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    data_file = ROOT / "fleet-data.js"
    if data_file.exists():
        data = data_file.read_text(encoding="utf-8")
        for img in sorted((ROOT / IMG_PREFIX).glob("*")):
            mime = mimetypes.guess_type(img.name)[0] or "image/png"
            uri = f"data:{mime};base64," + base64.b64encode(img.read_bytes()).decode()
            data = data.replace(f'"{IMG_PREFIX}{img.name}"', f'"{uri}"')
        data = data.replace("</", "<\\/")      # keep the inline script from being closed early
        html = html.replace('<script src="fleet-data.js"></script>', f"<script>{data}</script>", 1)
    return html


files = [ROOT / "index.html", ROOT / "fleet-data.js"]
page = build_page(tuple(f.stat().st_mtime if f.exists() else 0 for f in files))
height = st.sidebar.slider("화면 높이 (px)", 700, 2000, 1100, 50) if st.query_params.get("tune") else 1100
components.html(page, height=height, scrolling=True)
