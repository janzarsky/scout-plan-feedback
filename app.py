import os
import logging
import streamlit as st
from google import genai
from google.genai import types

# Configure logging for server-side error capture
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB limit

# Page setup
st.set_page_config(
    page_title="Automatizovaná zpětná vazba pro skautské plány",
    layout="centered"
)

# Custom Scout Styling
st.markdown("""
    <style>
    .main-header { font-family: 'Outfit', sans-serif; color: #1c3625; }
    .stButton>button {
        background-color: #2d573a; color: white; border-radius: 8px;
    }
    </style>
""", unsafe_allow_html=True)

SYSTEM_PROMPT = """
Jsi okresní skautský výchovný zpravodaj vyhodnocující celoroční plány
skautských oddílů.  Tvou rolí je poskytovat podporující, konstruktivní a
praktickou zpětnou vazbu vedoucím oddílů.

METODIKA A PRAVIDLA HODNOCENÍ:
1. SKRYTÉ VYHODNOCENÍ ZKUŠENOSTÍ: V duchu (bez uvádění nálepky ve výstupu)
posuď, zda je oddíl Začátečník, Středně pokročilý, nebo Pokročilý na základě
složitosti plánu, stanovených cílů, řešení bezpečnosti a gradace programu.
   - Pro začínající oddíly: Zaměř se na základní bezpečnost, klíčové termíny
     výprav a základní zapojení družin.
   - Pro pokročilé oddíly: Zaměř se na plnění stezek/vítězek, skautskou
     výchovnou metodu, delegaci na rádce a pestrost programu.
2. TÓN: Empatický, povzbudivý a mentorský. Vyhni se korporátnímu jargonu,
odtažité kritice nebo přehnané přísnosti.
3. METODIKA A ODKAZY: Vycházej ze standardů okresního plánování. Upozorni na
chybějící bezpečnostní plány (voda, hory), nevyváženou strukturu schůzek nebo
nereálné tempo akcí.
4. JAZYK: Odpovídaj výhradně v českém jazyce s využitím přirozené české
skautské terminologie (oddíl, družina, schůzka, výprava, tábor, skautská
výchovná metoda, družinový systém, rádce).

STRUKTURA VÝSTUPU:
Vygeneruj strukturovaný Markdown s následujícími sekcemi:
- **Hlavní silné stránky** (Vyzdvihni 2-3 konkrétní pozitiva plánu)
- **Příležitosti k růstu a doporučení** (3-4 prioritní oblasti pro zlepšení)
- **Kontrola bezpečnosti a metodiky** (Vyžadované bezpečnostní plány, chybějící
  klíčové termíny, rizikové oblasti)
- **Osobní vzkaz zpravodaje** (Osobní, povzbudivé závěrečné slovo pro vedení
  oddílu)
"""


def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        st.error("GEMINI_API_KEY environment variable is missing.")
        st.stop()
    return genai.Client(api_key=api_key)


# Header
st.title("Automatizovaná zpětná vazba pro skautské plány")
st.caption("Nahraj celoroční plán svého oddílu a získej okamžitou zpětnou"
           " vazbu")

st.divider()

# Input Options Tab
tab1, tab2 = st.tabs(["Nahrát plán v PDF", "Vložit text plánu"])

plan_bytes = None
plan_text = ""

with tab1:
    uploaded_file = st.file_uploader("Nahrát plán oddílu (PDF)", type=["pdf"])
    if uploaded_file:
        if uploaded_file.size > MAX_FILE_SIZE_BYTES:
            st.error("Velikost souboru přesahuje povolený limit 2 MB.")
        else:
            plan_bytes = uploaded_file.getvalue()

with tab2:
    plan_text = st.text_area("Vlož text plánu nebo obsah z Google Docs zde:",
                             height=250)

st.divider()

if st.button("Analýza plánu a vygenerování zpětné vazby",
             use_container_width=True):
    if not plan_bytes and not plan_text.strip():
        st.warning("Pro pokračování prosím nahraj soubor PDF nebo vlož text"
                   " plánu.")
    else:
        client = get_gemini_client()

        with st.spinner("Analýza plánu..."):
            try:
                # Prepare payload
                contents = []
                if plan_bytes:
                    pdf_part = types.Part.from_bytes(
                        data=plan_bytes,
                        mime_type="application/pdf"
                    )
                    contents.append(pdf_part)

                if plan_text.strip():
                    contents.append(f"Text dokumentu plánu:\n{plan_text}")

                contents.append(
                    "Prosím zkontroluj tento skautský plán podle okresních"
                    " metodických standardů a vygeneruj strukturovanou zpětnou"
                    " vazbu v češtině.")

                # Call Gemini API
                response = client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.3,
                    )
                )

                # Render Results
                st.success("Analýza a zpětná vazba je dokončena.")
                st.markdown(response.text)

                # Download button for the output
                st.download_button(
                    label="Stáhnout zpětnou vazbu (.md)",
                    data=response.text,
                    file_name="zpetna_vazba_plan_oddilu.md",
                    mime="text/markdown"
                )

            except Exception as e:
                logger.error("Error during plan evaluation: %s", e,
                             exc_info=True)
                st.error("Při zpracování plánu došlo k chybě. "
                         "Zkuste to prosím znovu.")
