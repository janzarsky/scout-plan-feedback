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
MAX_DAILY_ANALYSES = 50                  # Per-user daily quota

# MIME type mapping based on file extension
MIME_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# Initialize Firestore for user usage counting
# (Uses Cloud Run's default service account authentication)
db = firestore.Client()

# Page setup
st.set_page_config(
    page_title="Zkontroluj si svůj skautský oddílový plán",
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
    st.title("Zkontroluj si svůj skautský oddílový plán")
    st.write("Pro použití této aplikace se prosím přihlas pomocí účtu "
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
    """Increment user analysis count in Firestore for today atomically."""
    today_str = get_today_str()
    doc_ref = db.collection("usage_limits").document(email)
    doc = doc_ref.get()

    if doc.exists and doc.to_dict().get("last_reset_date") == today_str:
        doc_ref.update({
            "count": firestore.Increment(1)
        })
    else:
        doc_ref.set({
            "count": 1,
            "last_reset_date": today_str,
            "email": email
        }, merge=True)


# Header
st.title("Zkontroluj si svůj skautský oddílový plán")
st.write(f"Přihlášen jako: **{user_email}**. Vytvořil Walker (walker@skaut.cz)")
if st.button("Odhlásit se"):
    st.logout()

st.divider()

# Display Current Usage
current_usage = get_user_usage_today(user_email)
st.caption(f"Využité analýzy pro dnešní den: {current_usage} "
           f"z {MAX_DAILY_ANALYSES}")

# Input Options Tab
tab1, tab2 = st.tabs(["Nahrát plán (PDF, DOCX, XLSX)", "Vložit text plánu"])

plan_bytes = None
plan_mime_type = None
plan_text = ""

with tab1:
    uploaded_file = st.file_uploader("Nahrát plán oddílu (PDF, DOCX, XLSX)",
                                     type=["pdf", "docx", "xlsx"])
    if uploaded_file:
        if uploaded_file.size > MAX_FILE_SIZE_BYTES:
            st.error("Velikost souboru přesahuje povolený limit 2 MB.")
        else:
            file_ext = uploaded_file.name.split(".")[-1].lower()
            plan_mime_type = MIME_TYPES.get(file_ext)
            plan_bytes = uploaded_file.getvalue()

with tab2:
    plan_text = st.text_area("Vlož text plánu nebo obsah z Google Docs zde:",
                             height=250)

st.divider()


SYSTEM_PROMPT_PATH = "system_prompt.md"
KNOWLEDGE_BASE_PATH = "knowledge_base.md"
PAST_GUIDANCE_PATH = "past_guidance.md"


def load_system_instruction():
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    with open(KNOWLEDGE_BASE_PATH, "r", encoding="utf-8") as f:
        kb_content = f.read()
    system_prompt += f"\n\n--- METODICKÁ ZNALOSTNÍ BÁZE ---\n{kb_content}"

    with open(PAST_GUIDANCE_PATH, "r", encoding="utf-8") as f:
        kb_content = f.read()
    system_prompt += (
        "\n\n--- ZNALOSTNÍ BÁZE ZALOŽENÁ NA HISTORICKÝCH "
        f"ANALÝZÁCH ---\n{kb_content}"
    )
    return system_prompt


# Initialize session state for storing analysis result
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

if st.session_state.analysis_result:
    st.success("Analýza a zpětná vazba je dokončena.")
    st.markdown(st.session_state.analysis_result)

    st.divider()
    if st.button("Provést novou analýzu", use_container_width=True):
        st.session_state.analysis_result = None
        st.rerun()

else:
    if st.button("Analýza plánu a vygenerování zpětné vazby",
                 use_container_width=True):
        if current_usage >= MAX_DAILY_ANALYSES:
            st.error("Dosáhli jste maximálního denního limitu "
                     f"({MAX_DAILY_ANALYSES} analýz). Zkuste to prosím zítra.")
        elif not plan_bytes and not plan_text.strip():
            st.warning("Pro pokračování prosím nahraj soubor (PDF, DOCX, "
                       "XLSX) nebo vlož text plánu.")
        else:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

            with st.spinner("Analýza plánu..."):
                try:
                    contents = []
                    if plan_bytes and plan_mime_type:
                        contents.append(
                            types.Part.from_bytes(data=plan_bytes,
                                                  mime_type=plan_mime_type)
                        )
                    if plan_text.strip():
                        contents.append(f"Text dokumentu plánu:\n{plan_text}")
                    contents.append("Prosím zkontroluj tento skautský plán "
                                    "podle metodických standardů.")

                    system_instruction = load_system_instruction()

                    response = client.models.generate_content(
                        model="gemini-3.8-flash",
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.3,
                        )
                    )

                    # Store the generated output in session state
                    st.session_state.analysis_result = response.text

                    # Increment usage after successful response
                    increment_user_usage(user_email)

                    st.rerun()

                except Exception as e:
                    logger.error("Error during plan evaluation: %s", e,
                                 exc_info=True)
                    st.error("Při zpracování plánu došlo k chybě. "
                            "Zkuste to prosím znovu.")
