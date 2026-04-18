import json
from pathlib import Path

import streamlit as st

from classifier import is_opportunity
from extractor import extract_fields
from scorer import compute_score, generate_checklist
from streamlit_status_panel import latest_audit_file, llm_is_active, read_audit_preview, render_status_panel

BASE_DIR = Path(__file__).resolve().parent
DEMO_EMAILS_PATH = BASE_DIR / "demo_emails.json"
PROFILE_PATH = BASE_DIR / "student_profile.json"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_emails(payload):
    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict):
            return [
                {
                    "subject": item.get("subject", ""),
                    "body": item.get("body", item.get("text", "")),
                }
                for item in payload
            ]
        return [{"subject": "", "body": str(item)} for item in payload]
    return []


def combine_email_text(email_item):
    subject = email_item.get("subject", "").strip()
    body = email_item.get("body", "").strip()
    return "\n".join(part for part in [subject, body] if part)


def render_checklist_text(checklist, opportunity, score):
    lines = [
        f"Priority: {checklist['priority']}",
        f"Score: {score['final_score']}",
        f"Type: {opportunity.get('opportunity_type', 'unknown')}",
        f"Deadline: {checklist['deadline_line']}",
        "",
        "Why this matters:",
        checklist.get("why", ""),
        "",
        "Required documents:",
    ]
    docs = checklist.get("required_documents") or []
    if docs:
        lines.extend(f"- {doc}" for doc in docs)
    else:
        lines.append("- None detected")
    lines.extend(["", "Next steps:"])
    lines.extend(f"- {step}" for step in checklist.get("next_steps", []))
    contacts = checklist.get("contact") or []
    links = checklist.get("apply_link") or []
    if contacts:
        lines.extend(["", "Contact:"])
        lines.extend(f"- {contact}" for contact in contacts)
    if links:
        lines.extend(["", "Apply link:"])
        lines.extend(f"- {link}" for link in links)
    return "\n".join(lines)


st.set_page_config(page_title="Inbox Copilot Demo", page_icon="📬", layout="wide")

st.markdown(
    """
    <style>
        .stApp {
            background: linear-gradient(180deg, #faf7f2 0%, #f4efe6 100%);
        }
        .hero {
            padding: 1.2rem 1.4rem;
            border-radius: 1.25rem;
            background: linear-gradient(135deg, #1f2937 0%, #334155 100%);
            color: white;
            margin-bottom: 1rem;
            box-shadow: 0 16px 40px rgba(15, 23, 42, 0.18);
        }
        .card {
            padding: 1rem 1rem 0.8rem 1rem;
            border-radius: 1rem;
            background: rgba(255, 255, 255, 0.88);
            border: 1px solid rgba(148, 163, 184, 0.2);
            box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
            margin-bottom: 1rem;
        }
        .meta {
            color: #475569;
            font-size: 0.95rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <h1 style="margin:0 0 0.35rem 0;">Inbox Copilot</h1>
        <p style="margin:0; max-width: 60rem; line-height: 1.5;">
            Paste or upload opportunity emails, rank them against a student profile, and export a concise application checklist.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

active, model_name = llm_is_active()
recent_audit = latest_audit_file()
if recent_audit:
    audit_preview, _ = read_audit_preview(recent_audit)
    audit_timestamp = audit_preview.get("timestamp", "unknown")
else:
    audit_timestamp = "No audit records yet"

status_col, audit_col = st.columns(2)
with status_col:
    st.metric("LLM mode", "Active" if active else "Disabled")
    st.caption(f"Model: {model_name}")
with audit_col:
    st.metric("Latest audit", recent_audit.name if recent_audit else "None")
    st.caption(f"Timestamp: {audit_timestamp}")

left, right = st.columns([1.05, 1])

render_status_panel()

with left:
    st.subheader("Inputs")
    profile_mode = st.radio("Profile source", ["Demo profile", "Upload profile JSON", "Paste profile JSON"], horizontal=True)

    profile = load_json(PROFILE_PATH)
    if profile_mode == "Upload profile JSON":
        uploaded_profile = st.file_uploader("Upload student_profile.json", type="json", key="profile_upload")
        if uploaded_profile:
            profile = json.load(uploaded_profile)
    elif profile_mode == "Paste profile JSON":
        profile_text = st.text_area("Paste profile JSON", value=json.dumps(profile, indent=2), height=220)
        try:
            profile = json.loads(profile_text)
        except json.JSONDecodeError:
            st.warning("Profile JSON is invalid; using demo profile until it parses.")

    email_mode = st.radio("Email source", ["Demo emails", "Upload JSON", "Paste emails"], horizontal=True)
    emails = normalize_emails(load_json(DEMO_EMAILS_PATH))

    if email_mode == "Upload JSON":
        uploaded_emails = st.file_uploader("Upload emails JSON", type="json", key="emails_upload")
        if uploaded_emails:
            emails = normalize_emails(json.load(uploaded_emails))
    elif email_mode == "Paste emails":
        pasted = st.text_area(
            "Paste emails JSON",
            value=json.dumps(load_json(DEMO_EMAILS_PATH), indent=2),
            height=320,
        )
        try:
            emails = normalize_emails(json.loads(pasted))
        except json.JSONDecodeError:
            st.warning("Emails JSON is invalid; using demo emails until it parses.")

    st.caption("Input format supports either a list of raw email strings or a list of {subject, body} objects.")
    analyze = st.button("Analyze inbox", type="primary", use_container_width=True)

with right:
    st.subheader("Results")

if analyze:
    scored_results = []
    ignored_results = []

    for index, email_item in enumerate(emails, start=1):
        text = combine_email_text(email_item)
        is_match, evidence_line = is_opportunity(text)
        extracted = extract_fields(text)

        if not is_match:
            ignored_results.append(
                {
                    "index": index,
                    "subject": email_item.get("subject", f"Email {index}"),
                    "evidence": evidence_line,
                }
            )
            continue

        score = compute_score(extracted, profile)
        checklist = generate_checklist(extracted, score, profile)
        scored_results.append(
            {
                "index": index,
                "subject": email_item.get("subject", f"Opportunity {index}"),
                "text": text,
                "extracted": extracted,
                "score": score,
                "checklist": checklist,
                "evidence": evidence_line,
            }
        )

    scored_results.sort(key=lambda item: item["score"]["final_score"], reverse=True)

    with right:
        if scored_results:
            top_score = scored_results[0]["score"]["final_score"]
            st.metric("Top opportunity score", f"{top_score}")
        else:
            st.metric("Top opportunity score", "N/A")

        if ignored_results:
            st.info(f"Filtered out {len(ignored_results)} non-opportunity email(s).")
        else:
            st.info("No non-opportunity emails were filtered out.")

        if not scored_results:
            st.warning("No opportunities detected in the current inbox.")
        else:
            for item in scored_results:
                score = item["score"]
                extracted = item["extracted"]
                checklist = item["checklist"]
                with st.container(border=True):
                    st.markdown(
                        f"""
                        <div class="card">
                            <h3 style="margin:0 0 0.3rem 0;">{item['subject']}</h3>
                            <div class="meta">Score: <strong>{score['final_score']}</strong> | Priority: <strong>{checklist['priority']}</strong> | Type: {extracted.get('opportunity_type', 'unknown')}</div>
                            <div class="meta">Deadline: {checklist['deadline_line']}</div>
                            <p style="margin-bottom:0;">{extracted.get('evidence', '')[:220]}</p>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    details_col, actions_col = st.columns([1.15, 0.85])

                    with details_col:
                        with st.expander("View extracted fields", expanded=False):
                            st.json(extracted)
                            st.json(score)

                    with actions_col:
                        checklist_text = render_checklist_text(checklist, extracted, score)
                        st.download_button(
                            label="Download checklist",
                            data=checklist_text,
                            file_name=f"checklist-{item['index']}.txt",
                            mime="text/plain",
                            use_container_width=True,
                        )
                        st.text_area(
                            "Checklist preview",
                            value=checklist_text,
                            height=220,
                            key=f"checklist-preview-{item['index']}",
                        )

                    applied_key = f"applied-{item['index']}"
                    if st.button("Mark as applied", key=f"apply-{item['index']}", use_container_width=True):
                        st.session_state[applied_key] = True
                    if st.session_state.get(applied_key):
                        st.success("Marked as applied")
else:
    st.subheader("What you can do here")
    st.write("Load the demo inbox, upload your own JSON, or paste emails and a profile to see ranked opportunities.")
    st.write("The app keeps the classifier and scorer deterministic, so the ranking is repeatable across runs.")