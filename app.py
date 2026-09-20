import os
import streamlit as st
from pypdf import PdfReader
from google import genai
from google.genai import types

# Page setup
st.set_page_config(
    page_title="Scout Plan Feedback Tool",
    page_icon="⚜️",
    layout="centered"
)

# Custom Scout Styling
st.markdown("""
    <style>
    .main-header { font-family: 'Outfit', sans-serif; color: #1c3625; }
    .stButton>button { background-color: #2d573a; color: white; border-radius: 8px; }
    </style>
""", unsafe_allow_html=True)

SYSTEM_PROMPT = """
You are a District Scout Advisor evaluating annual scout unit plans. Your role is to provide supportive, 
constructive, and actionable feedback to unit leaders (often ~20 years old).

EVALUATION METHODOLOGY & RULES:
1. SILENT MATURITY EVALUATION: Silently assess if the unit is Beginner, Intermediate, or Advanced based on 
   plan complexity, goal setting, safety considerations, and activity progression.
   - For Beginner units: Focus on core safety, essential calendar dates, and basic troop engagement.
   - For Advanced units: Focus on scout progression, leadership delegation, and outdoor variety.
2. TONE: Empathetic, encouraging, and mentoring. Avoid corporate jargon or overly harsh criticism.
3. CITATIONS & RULES: Ground advice in district planning standards. Point out missing safety/water plans, 
   unbalanced meeting structures, or unrealistic event pacing.

OUTPUT FORMAT:
Generate structured Markdown with the following sections:
- 🌟 **Overall Strengths** (Highlight 2-3 specific positives)
- 🎯 **Growth Opportunities & Recommendations** (3-4 prioritized improvements)
- ⚠️ **Safety & Compliance Check** (Required safety plans, missing dates, risk areas)
- 💡 **Advisor's Direct Coaching Note** (A personal, encouraging summary note)
"""

def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        st.error("⚠️ GEMINI_API_KEY environment variable is missing!")
        st.stop()
    return genai.Client(api_key=api_key)

# Header
st.title("⚜️ Scout Plan Automated Feedback Tool")
st.caption("Upload your annual unit plan to receive instant, constructive, and private advisor coaching.")

st.divider()

# Input Options Tab
tab1, tab2 = st.tabs(["📄 Upload PDF Plan", "📝 Paste Raw Text / Plan Outline"])

plan_bytes = None
plan_text = ""

with tab1:
    uploaded_file = st.file_uploader("Upload unit plan (PDF)", type=["pdf"])
    if uploaded_file:
        plan_bytes = uploaded_file.getvalue()

with tab2:
    plan_text = st.text_area("Paste your plan or Google Doc text here:", height=250)

st.divider()

if st.button("🚀 Analyze Plan & Generate Feedback", use_container_width=True):
    if not plan_bytes and not plan_text.strip():
        st.warning("Please upload a PDF plan or paste plan text to continue.")
    else:
        client = get_gemini_client()

        with st.spinner("🤖 Evaluating plan against district guidelines..."):
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
                    contents.append(f"Plan Document Text:\n{plan_text}")

                contents.append("Please review this scout plan against district standards and generate structured feedback.")

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
                st.success("✅ Feedback analysis complete!")
                st.markdown(response.text)

                # Download button for the output
                st.download_button(
                    label="📥 Download Feedback (.md)",
                    data=response.text,
                    file_name="scout_plan_feedback.md",
                    mime="text/markdown"
                )

            except Exception as e:
                st.error(f"❌ An error occurred during processing: {e}")