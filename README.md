# Inbox Copilot

Inbox Copilot scans opportunity-related emails, extracts relevant application details, ranks them for a student profile, and generates a practical checklist.

## Included

- FastAPI backend in [app.py](app.py)
- Deterministic classifier, extractor, and scorer
- Streamlit demo in [streamlit_app.py](streamlit_app.py)
- Optional LLM-assisted extraction in [llm_wrapper.py](llm_wrapper.py)
- Tests in [tests/](tests)

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run tests

```bash
pytest -q
```

## Run the FastAPI app

```bash
uvicorn app:app --reload
```

## Run the Streamlit demo

```bash
streamlit run streamlit_app.py
```

## Optional LLM extraction

Set one provider before launching the app:

```bash
# OpenAI
export LLM_PROVIDER="openai"
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"

# Gemini
export LLM_PROVIDER="gemini"
export GEMINI_API_KEY="your-gemini-key"
export GEMINI_MODEL="gemini-1.5-flash"

# Groq
export LLM_PROVIDER="groq"
export GROQ_API_KEY="your-groq-key"
export GROQ_MODEL="llama-3.1-8b-instant"

streamlit run streamlit_app.py
```

If provider config is missing or invalid, the app falls back to the deterministic extractor.

## Quick demo script (60 seconds)

1. Open the app locally: `streamlit run streamlit_app.py`.
2. Click Analyze Inbox to run the pipeline on demo emails.
3. Expand the top result to show extracted fields, score breakdown, and checklist.
4. Download the checklist and inspect the audit records in `llm_audit/` if LLM mode is enabled.

## Deploy to Streamlit Cloud

1. Push the repo to GitHub.
2. Create a new app in Streamlit Cloud and set the main file to `streamlit_app.py`.
3. Add provider secrets in Streamlit Cloud: `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `GROQ_API_KEY`.
4. Launch and share the URL.

## Deploy to Render

1. Create a new Web Service and connect the GitHub repo.
2. Build command: `pip install -r requirements.txt`
3. Start command: `streamlit run streamlit_app.py --server.port $PORT`
4. Add environment variables for selected provider if needed.

## Deployment notes

### Streamlit Cloud

1. Push the repository to GitHub.
2. Create a new Streamlit Cloud app from the repo.
3. Set the main file path to `streamlit_app.py`.
4. Add `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `GROQ_API_KEY` in Secrets if using the LLM wrapper.

### Render

1. Create a new Web Service connected to the repo.
2. Build command: `pip install -r requirements.txt`
3. Start command: `streamlit run streamlit_app.py --server.port $PORT`
4. Add environment variables for selected provider if needed.

## Demo flow

1. Open the Streamlit app.
2. Load the demo emails and demo profile.
3. Click Analyze inbox.
4. Expand the top-ranked items.
5. Download or copy the generated checklist.

## Scoring rubric

Inbox Copilot computes a final score from four deterministic signals:

- Profile fit: 40%
- Urgency: 30%
- Effort to apply: 15%
- Impact: 15%

Interpretation:

- Higher profile fit means the opportunity matches the student's degree, CGPA, skills, and preferred opportunity types.
- Higher urgency means the deadline is sooner, or the item has no deadline but still looks relevant.
- Lower effort means fewer required documents and less friction to apply.
- Higher impact means the opportunity is paid, stipend-based, or especially career-relevant.

The classifier and scorer stay deterministic even when the optional LLM extractor is enabled. If the LLM fails, the system falls back to the rule-based extractor.

## 60-second demo script

1. Open the Streamlit app and point out the LLM status and latest audit timestamp.
2. Click Analyze inbox with the demo emails loaded.
3. Show the ranked opportunities and the score breakdown on the top item.
4. Expand the checklist, point out the next steps, and download the text file.
5. Open the sidebar audit preview if LLM mode is active.
6. Close by explaining that the deterministic fallback keeps the ranking stable even without the LLM.

## Notes

- Keep demo emails free of personal data.
- Classifier and scoring remain deterministic.
- LLM usage is limited to extraction only.
- The deterministic extractor remains the fallback if the LLM is unavailable.