import os
import logging
import streamlit as st
from google import genai
from google.genai import types
from google.cloud import firestore

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB limit
MAX_DAILY_ANALYSES = 5                  # Per-user daily quota

# Initialize Firestore for user usage counting
# (Uses Cloud Run's default service account authentication)
db = firestore.Client()

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

# Require Authentication
if not st.user.is_logged_in:
    st.title("Automatizovaná zpětná vazba pro skautské plány")
    st.write("Pro použití této aplikace se prosím přihlaste pomocí účtu "
             "Google.")
    if st.button("Přihlásit se přes Google"):
        st.login("google")
    st.stop()

# User is authenticated
user_email = st.user.email


def get_user_usage_today(email: str) -> int:
    """Fetch total analyses run by the user today."""
    today_str = firestore.SERVER_TIMESTAMP  # or date string YYYY-MM-DD
    doc_ref = db.collection("usage_limits").document(email)
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        if data.get("last_reset_date") == today_str:
            return data.get("count", 0)
    return 0


def increment_user_usage(email: str):
    """Increment user analysis count in Firestore."""
    today_str = firestore.SERVER_TIMESTAMP
    doc_ref = db.collection("usage_limits").document(email)
    doc_ref.set({
        "count": firestore.Increment(1),
        "last_reset_date": today_str,
        "email": email
    }, merge=True)


# Header
st.title("Automatizovaná zpětná vazba pro skautské plány")
st.write(f"Přihlášen jako: **{user_email}**")
if st.button("Odhlásit se"):
    st.logout()

st.divider()

# Display Current Usage
current_usage = get_user_usage_today(user_email)
st.caption(f"Využité analýzy pro dnešní den: {current_usage} "
           f"z {MAX_DAILY_ANALYSES}")

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
    if current_usage >= MAX_DAILY_ANALYSES:
        st.error("Dosáhli jste maximálního denního limitu "
                 f"({MAX_DAILY_ANALYSES} analýz). Zkuste to prosím zítra.")
    elif not plan_bytes and not plan_text.strip():
        st.warning("Pro pokračování prosím nahraj soubor PDF nebo vlož text "
                   "plánu.")
    else:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        with st.spinner("Analýza plánu..."):
            try:
                contents = []
                if plan_bytes:
                    contents.append(
                        types.Part.from_bytes(data=plan_bytes,
                                              mime_type="application/pdf")
                    )
                if plan_text.strip():
                    contents.append(f"Text dokumentu plánu:\n{plan_text}")
                contents.append("Prosím zkontroluj tento skautský plán podle "
                                "okresních metodických standardů.")

                response = client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.3,
                    )
                )

                # Increment usage after successful response
                increment_user_usage(user_email)

                st.success("Analýza a zpětná vazba je dokončena.")
                st.markdown(response.text)

            except Exception as e:
                logger.error("Error during plan evaluation: %s", e,
                             exc_info=True)
                st.error("Při zpracování plánu došlo k chybě. "
                         "Zkuste to prosím znovu.")
