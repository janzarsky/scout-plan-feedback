import os
import logging
import streamlit as st
from datetime import datetime, timezone
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


# Require Authentication
if not st.user or "email" not in st.user:
    st.title("Automatizovaná zpětná vazba pro skautské plány")
    st.write("Pro použití této aplikace se prosím přihlaste pomocí účtu "
             "Google.")
    if st.button("Přihlásit se přes Google"):
        st.login("google")
    st.stop()

# User is authenticated
user_email = st.user["email"]


def get_today_str() -> str:
    """Returns today's date in YYYY-MM-DD format (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_user_usage_today(email: str) -> int:
    """Fetch total analyses run by the user today."""
    today_str = get_today_str()
    doc_ref = db.collection("usage_limits").document(email)
    doc = doc_ref.get()

    if doc.exists:
        data = doc.to_dict() or {}
        # If the recorded date matches today's date, return the stored count
        if data.get("last_reset_date") == today_str:
            return data.get("count", 0)

    return 0


def increment_user_usage(email: str):
    """Increment user analysis count in Firestore for today."""
    today_str = get_today_str()
    doc_ref = db.collection("usage_limits").document(email)
    doc = doc_ref.get()

    current_count = 0
    if doc.exists:
        data = doc.to_dict() or {}
        # If it's still today, keep existing count to increment
        if data.get("last_reset_date") == today_str:
            current_count = data.get("count", 0)

    # Overwrite/Set with new incremented count and today's date
    doc_ref.set({
        "count": current_count + 1,
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


BASE_SYSTEM_PROMPT = """
Jsi okresní skautský výchovný zpravodaj vyhodnocující celoroční plány
skautských oddílů. Tvou úlohou je poskytovat konstruktivní, podporující a
věcnou zpětnou vazbu, která pomáhá vedoucím vyjasňovat myšlenky, provázanost
plánu a jeho reálný dopad.

METODIKA A PRAVIDLA HODNOCENÍ:
1. KLÍČOVÝ ROZDÍL (CÍLE VS. PROSTŘEDKY): Důsledně rozlišuj mezi cíli (Cíl =
požadovaný STAV, kam se chceme dostat) a prostředky (Prostředek = AKTIVITA, jak
se tam dostaneme). Pokud uživatel uvádí jako cíl aktivitu (např. "uspořádat 3
výpravy"), oceň jasnost aktivity, ale pomoz mu otázkami definovat zamýšlený
dopad.
2. HIERARCHIE A PROVÁZANOST: Sleduj logickou linii plánovacího cyklu: Analýza
-> Vize -> Prioritní oblasti -> Cíle -> Prostředky -> Vyhodnocení.
   - Analýza: Upozorni na zaměňování příčin za následky a předčasné skákání do
     řešení.
   - Vize a Prioritní oblasti: Doporuč prioritizaci, pokud plán obsahuje více
     než 2–5 prioritních oblastí.
   - Vyhodnotitelnost: Upozorňuj na prázdná slovesa a komparativy (např.
     "zlepšíme", "lépe"). Pomáhej formulovat konkrétní indikátory naplnění
     cílů.
3. TÓN A PRISTUP: Empatický, povzbudivý a mentorský. Vyhni se dogmatismu,
korporátnímu jargonu i odtažité kritice. Místo diktování změn nabízej varianty,
návodné otázky a příklady dobré praxe.
4. JAZYK: Odpovídaj výhradně v českém jazyce s využitím přirozené české
skautské terminologie (vize, prioritní oblasti, cíle, prostředky, indikátory,
oddíl, družina, rádce, družinový systém).

STRUKTURA VÝSTUPU:
Vygeneruj strukturovaný Markdown s následujícími sekcemi:
- **Silné stránky a ocenění** (Vyzdvihni 2-3 konkrétní pozitiva, jako např.
  jasnou vizi, návaznost na potřeby dětí nebo dobré vymezení priorit)
- **Hierarchie a provázanost plánu** (Zhodnocení logické návaznosti od analýzy
  přes vizi a prioritní oblasti až po konkrétní cíle)
- **Rozlišení cílů a prostředků** (Konkrétní místa, kde jsou cíle zaměňovány za
  aktivity, s návodnými otázkami pro formulaci cílového stavu)
- **Příležitosti ke zpřesnění a vyhodnotitelnost** (3-4 doporučení k formulaci
  cílů, doporučení indikátorů a ověření naplnění stavu)
"""

KNOWLEDGE_BASE_PATH = "knowledge_base.md"


def load_system_instruction():
    system_prompt = BASE_SYSTEM_PROMPT
    if os.path.exists(KNOWLEDGE_BASE_PATH):
        with open(KNOWLEDGE_BASE_PATH, "r", encoding="utf-8") as f:
            kb_content = f.read()
        system_prompt += f"\n\n--- METODICKÁ ZNALOSTNÍ BÁZE ---\n{kb_content}"
    return system_prompt


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

                system_instruction = load_system_instruction()

                response = client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
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
