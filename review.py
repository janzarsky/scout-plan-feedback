import os
import glob
from pathlib import Path
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# System Prompt & Methodology Rules (Distilled 20-Page Guide & Persona)
# ---------------------------------------------------------------------------
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

def process_single_plan(client: genai.Client, pdf_path: Path, output_dir: Path):
    """Processes a single PDF plan and saves the Markdown review."""
    markdown_path = output_dir / f"{pdf_path.stem}_feedback.md"
    
    if markdown_path.exists():
        print(f"⏩ Skipping {pdf_path.name} (Feedback already exists)")
        return

    print(f"📄 Processing: {pdf_path.name}...")

    # Upload PDF file via Google GenAI SDK File API
    uploaded_file = client.files.upload(file=pdf_path)

    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[
                uploaded_file,
                "Please review this attached scout unit plan against district standards and generate structured feedback."
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.3,
            )
        )

        # Write generated feedback to Markdown file
        with open(markdown_path, "w", encoding="utf-8") as f:
            f.write(f"# Scout Plan Feedback: {pdf_path.stem}\n\n")
            f.write(response.text)

        print(f"✅ Saved feedback to: {markdown_path.name}")

    except Exception as e:
        print(f"❌ Error processing {pdf_path.name}: {e}")
    finally:
        # Clean up remote file resource
        client.files.delete(name=uploaded_file.name)


def main():
    plans_dir = Path("./input_plans")
    output_dir = Path("./output_reviews")

    plans_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)

    pdf_files = list(plans_dir.glob("*.pdf"))

    if not pdf_files:
        print(f"⚠️ No PDF files found in '{plans_dir.resolve()}'. Place PDF plans there and re-run.")
        return

    print(f"🚀 Found {len(pdf_files)} plan(s) to process.\n")
    
    client = genai.Client()

    for pdf_path in pdf_files:
        process_single_plan(client, pdf_path, output_dir)

    print("\n🎉 Batch processing complete!")

if __name__ == "__main__":
    main()