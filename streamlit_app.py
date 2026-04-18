import json
from collections import Counter
from io import StringIO
from pathlib import Path
from statistics import mean

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


def compute_priority(score_value: float) -> str:
    if score_value >= 75:
        return "High"
    if score_value >= 50:
        return "Medium"
    return "Low"


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


def build_analysis(emails, profile):
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
                    "body": email_item.get("body", ""),
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
                "priority": compute_priority(score["final_score"]),
                "evidence": evidence_line,
            }
        )

    scored_results.sort(key=lambda item: item["score"]["final_score"], reverse=True)
    return scored_results, ignored_results


def export_all_checklists(items):
    chunks = []
    for item in items:
        header = f"\n{'=' * 60}\n{item['subject']}\n{'=' * 60}\n"
        checklist_text = render_checklist_text(item["checklist"], item["extracted"], item["score"])
        chunks.append(header + checklist_text)
    return "\n".join(chunks)


def export_results_csv(items):
    buffer = StringIO()
    headers = [
        "rank",
        "subject",
        "score",
        "priority",
        "type",
        "deadline",
        "applied",
    ]
    buffer.write(",".join(headers) + "\n")
    for rank, item in enumerate(items, start=1):
        deadline = (item.get("checklist") or {}).get("deadline_line", "")
        row = [
            str(rank),
            (item.get("subject") or "").replace(",", " "),
            str(item.get("score", {}).get("final_score", "")),
            item.get("priority", ""),
            item.get("extracted", {}).get("opportunity_type", ""),
            str(deadline).replace(",", " "),
            "yes" if st.session_state.get(f"applied-{item['index']}") else "no",
        ]
        buffer.write(",".join(row) + "\n")
    return buffer.getvalue()


def export_results_json(items):
    payload = []
    for item in items:
        payload.append(
            {
                "index": item.get("index"),
                "subject": item.get("subject"),
                "priority": item.get("priority"),
                "score": item.get("score", {}).get("final_score"),
                "type": item.get("extracted", {}).get("opportunity_type", "unknown"),
                "deadline": (item.get("checklist") or {}).get("deadline_line", ""),
                "applied": bool(st.session_state.get(f"applied-{item['index']}")),
            }
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_count_frame(items, field_name, fallback="unknown"):
    counter = Counter()
    for item in items:
        if field_name == "priority":
            value = item.get("priority", fallback)
        else:
            value = item.get("extracted", {}).get(field_name, fallback)
        counter[str(value or fallback)] += 1
    ordered = counter.most_common()
    return ordered


def priority_accent(priority: str) -> str:
    mapping = {
        "High": "#ef4444",
        "Medium": "#f59e0b",
        "Low": "#10b981",
    }
    return mapping.get(priority, "#3f51b5")


def priority_tone(priority: str) -> str:
    mapping = {
        "High": "rgba(239, 68, 68, 0.12)",
        "Medium": "rgba(245, 158, 11, 0.12)",
        "Low": "rgba(16, 185, 129, 0.12)",
    }
    return mapping.get(priority, "rgba(63, 81, 181, 0.12)")


st.set_page_config(page_title="ZYNEX", page_icon="📬", layout="wide")

st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        :root {
            --bg: radial-gradient(circle at top, rgba(63, 81, 181, 0.08), transparent 26%), linear-gradient(180deg, #f7f3eb 0%, #f2ecdf 100%);
            --surface: rgba(255, 255, 255, 0.88);
            --surface-strong: rgba(255, 255, 255, 0.98);
            --text: #16181d;
            --muted: #5c6475;
            --brand: #3f51b5;
            --brand-strong: #27358a;
            --accent: #10b981;
            --warning: #d97706;
            --danger: #ef4444;
            --shadow: 0 18px 40px rgba(20, 27, 40, 0.08);
        }
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }
        .stApp {
            background: var(--bg);
            color: var(--text);
        }
        .stApp * {
            box-sizing: border-box;
        }
        #MainMenu, footer, header {
            visibility: hidden;
        }
        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2rem;
            max-width: 1400px;
        }
        [data-testid="stButton"] button,
        [data-testid="stDownloadButton"] button,
        [data-testid="stFormSubmitButton"] button {
            border-radius: 999px !important;
            border: 1px solid rgba(63, 81, 181, 0.14) !important;
            transition: transform 160ms ease, box-shadow 160ms ease, background 160ms ease;
        }
        [data-testid="stButton"] button:hover,
        [data-testid="stDownloadButton"] button:hover,
        [data-testid="stFormSubmitButton"] button:hover {
            transform: translateY(-1px);
            box-shadow: 0 10px 26px rgba(20, 27, 40, 0.12);
        }
        [data-baseweb="tab-list"] {
            gap: 0.5rem;
        }
        [data-baseweb="tab"] {
            border-radius: 999px !important;
            padding: 0.45rem 0.85rem !important;
            background: rgba(255, 255, 255, 0.6);
            border: 1px solid rgba(71, 85, 105, 0.12);
        }
        .hero {
            padding: 1.4rem 1.5rem;
            border-radius: 1.4rem;
            background:
                radial-gradient(circle at top right, rgba(255,255,255,0.18), transparent 30%),
                linear-gradient(135deg, #162034 0%, #25304e 48%, #3f4f84 100%);
            color: white;
            margin-bottom: 1rem;
            box-shadow: 0 24px 60px rgba(15, 23, 42, 0.22);
            border: 1px solid rgba(255, 255, 255, 0.12);
        }
        .hero-grid {
            display: grid;
            grid-template-columns: 1.8fr 1fr;
            gap: 1rem;
            align-items: end;
        }
        .hero-mini {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.6rem;
        }
        .hero-mini .mini {
            padding: 0.85rem 0.9rem;
            border-radius: 1rem;
            background: rgba(255, 255, 255, 0.12);
            border: 1px solid rgba(255, 255, 255, 0.12);
            backdrop-filter: blur(12px);
        }
        .hero-mini .mini .label {
            display: block;
            font-size: 0.8rem;
            color: rgba(255, 255, 255, 0.72);
            margin-bottom: 0.2rem;
        }
        .hero-mini .mini .value {
            font-size: 1.05rem;
            font-weight: 700;
            color: white;
        }
        .card {
            padding: 1rem 1rem 0.8rem 1rem;
            border-radius: 1rem;
            background: var(--surface);
            border: 1px solid rgba(71, 85, 105, 0.12);
            box-shadow: var(--shadow);
            margin-bottom: 1rem;
            backdrop-filter: blur(12px);
        }
        .meta {
            color: var(--muted);
            font-size: 0.95rem;
        }
        .card-title-row {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: flex-start;
            margin-bottom: 0.7rem;
        }
        .badge-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin: 0.55rem 0 0.65rem 0;
        }
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.28rem 0.65rem;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 600;
            border: 1px solid rgba(71, 85, 105, 0.14);
            color: #243043;
            background: rgba(255, 255, 255, 0.9);
        }
        .eyebrow {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.25rem 0.6rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.16);
            border: 1px solid rgba(255, 255, 255, 0.2);
            font-size: 0.85rem;
            color: rgba(255, 255, 255, 0.92);
        }
        .metric-shell {
            border-radius: 1rem;
            padding: 0.9rem 1rem;
            background: var(--surface-strong);
            border: 1px solid rgba(71, 85, 105, 0.12);
            box-shadow: var(--shadow);
        }
        .section-title {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 0.7rem;
        }
        .section-title h3 {
            margin: 0;
        }
        .subtle {
            color: var(--muted);
            font-size: 0.92rem;
        }
        .pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.3rem 0.7rem;
            border-radius: 999px;
            background: rgba(63, 81, 181, 0.12);
            color: var(--brand-strong);
            border: 1px solid rgba(63, 81, 181, 0.18);
            font-size: 0.84rem;
            font-weight: 600;
        }
        .glass-panel {
            background: var(--surface-strong);
            border-radius: 1rem;
            border: 1px solid rgba(71, 85, 105, 0.12);
            box-shadow: var(--shadow);
            padding: 1rem;
            margin-bottom: 1rem;
        }
        .kpi-shell {
            border-radius: 1.05rem;
            border: 1px solid rgba(71, 85, 105, 0.12);
            background: rgba(255, 255, 255, 0.92);
            box-shadow: var(--shadow);
            padding: 0.9rem 1rem;
        }
        .kpi-shell .label {
            color: var(--muted);
            font-size: 0.84rem;
            margin-bottom: 0.25rem;
        }
        .kpi-shell .value {
            font-size: 1.25rem;
            font-weight: 800;
            color: var(--text);
        }
        .sidebar-panel {
            padding: 1rem;
            border-radius: 1.15rem;
            background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(246, 241, 232, 0.9));
            border: 1px solid rgba(71, 85, 105, 0.12);
            box-shadow: var(--shadow);
        }
        .sidebar-brand {
            font-size: 1.1rem;
            font-weight: 800;
            margin-bottom: 0.2rem;
        }
        .sidebar-subtitle {
            color: var(--muted);
            font-size: 0.88rem;
            line-height: 1.45;
        }
        .sidebar-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin-top: 0.85rem;
        }
        .sidebar-chip {
            padding: 0.28rem 0.6rem;
            border-radius: 999px;
            font-size: 0.8rem;
            font-weight: 700;
            color: var(--brand-strong);
            background: rgba(63, 81, 181, 0.1);
            border: 1px solid rgba(63, 81, 181, 0.12);
        }
        .fade-in {
            animation: fadeIn 280ms ease-out both;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <div class="hero-grid">
            <div>
                <div class="eyebrow">Opportunity ranking workspace</div>
                <h1 style="margin:0.55rem 0 0.35rem 0; font-size:2.25rem; line-height:1.05;">ZYNEX</h1>
                <p style="margin:0; max-width: 60rem; line-height: 1.55; color: rgba(255,255,255,0.84); font-size: 1.02rem;">
                    Paste or upload opportunity emails, rank them against a student profile, and export a concise application checklist. Use the filters, sorting, and export tools to move faster from inbox to action.
                </p>
            </div>
            <div class="hero-mini">
                <div class="mini"><span class="label">View</span><span class="value">Split-pane triage</span></div>
                <div class="mini"><span class="label">Workflow</span><span class="value">Apply faster</span></div>
                <div class="mini"><span class="label">Exports</span><span class="value">TXT · CSV · JSON</span></div>
                <div class="mini"><span class="label">Mode</span><span class="value">Deterministic fallback</span></div>
            </div>
        </div>
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

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-panel fade-in">
            <div class="sidebar-brand">ZYNEX</div>
            <div class="sidebar-subtitle">
                Clean triage workspace for student opportunities with deterministic ranking, structured exports, and quick apply tracking.
            </div>
            <div class="sidebar-chip-row">
                <span class="sidebar-chip">Ranked triage</span>
                <span class="sidebar-chip">Fast exports</span>
                <span class="sidebar-chip">Audit trail</span>
                <span class="sidebar-chip">LLM fallback</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("#### Workspace")
    st.write("- Filters and sorting for fast review")
    st.write("- Applied-state tracking per item")
    st.write("- CSV, JSON, and checklist downloads")
    st.write("- Friendly fallback when the LLM is unavailable")
    st.divider()
    st.markdown("#### Tips")
    st.caption("Use the summary tab to export filtered results, then review the top items in ranked order.")

if "analysis_results" not in st.session_state:
    st.session_state.analysis_results = []
if "ignored_results" not in st.session_state:
    st.session_state.ignored_results = []

with left:
    st.subheader("Inputs")
    st.caption("Use the demo data to explore the flow quickly, or swap in your own inbox and profile JSON.")
    helper_col_1, helper_col_2 = st.columns(2)
    with helper_col_1:
        st.download_button(
            label="Download demo profile template",
            data=json.dumps(load_json(PROFILE_PATH), ensure_ascii=False, indent=2),
            file_name="profile-template.json",
            mime="application/json",
            use_container_width=True,
        )
    with helper_col_2:
        st.download_button(
            label="Download demo emails template",
            data=json.dumps(load_json(DEMO_EMAILS_PATH), ensure_ascii=False, indent=2),
            file_name="emails-template.json",
            mime="application/json",
            use_container_width=True,
        )

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
    clear_results = st.button("Clear current results", use_container_width=True)
    st.caption("Tip: use the filters on the right to focus on high-priority items.")

with right:
    st.subheader("Results")

if clear_results:
    st.session_state.analysis_results = []
    st.session_state.ignored_results = []

if analyze:
    scored_results, ignored_results = build_analysis(emails, profile)
    st.session_state.analysis_results = scored_results
    st.session_state.ignored_results = ignored_results

scored_results = st.session_state.analysis_results
ignored_results = st.session_state.ignored_results

if scored_results:
    all_types = sorted({item["extracted"].get("opportunity_type", "unknown") for item in scored_results})
    all_priorities = ["High", "Medium", "Low"]
    priority_counts = build_count_frame(scored_results, "priority")
    type_counts = build_count_frame(scored_results, "opportunity_type")

    filter_col_1, filter_col_2, filter_col_3 = st.columns(3)
    with filter_col_1:
        min_score = st.slider("Minimum score", min_value=0, max_value=100, value=0, step=5)
        selected_priorities = st.multiselect("Priority", options=all_priorities, default=all_priorities)
    with filter_col_2:
        selected_types = st.multiselect("Opportunity type", options=all_types, default=all_types)
        search_term = st.text_input("Search title/evidence", value="").strip().lower()
    with filter_col_3:
        sort_by = st.selectbox("Sort by", options=["Score", "Subject", "Type"], index=0)
        sort_desc = st.toggle("Descending", value=True)

    show_applied = st.toggle("Show applied only", value=False)

    filtered_results = []
    for item in scored_results:
        score_value = item["score"]["final_score"]
        subject = item["subject"].lower()
        evidence = (item["extracted"].get("evidence", "") or "").lower()
        applied_key = f"applied-{item['index']}"
        is_applied = bool(st.session_state.get(applied_key))

        if score_value < min_score:
            continue
        if item["priority"] not in selected_priorities:
            continue
        if item["extracted"].get("opportunity_type", "unknown") not in selected_types:
            continue
        if search_term and search_term not in subject and search_term not in evidence:
            continue
        if show_applied and not is_applied:
            continue
        filtered_results.append(item)

    if sort_by == "Subject":
        filtered_results.sort(key=lambda item: item["subject"].lower(), reverse=sort_desc)
    elif sort_by == "Type":
        filtered_results.sort(
            key=lambda item: item["extracted"].get("opportunity_type", "unknown").lower(),
            reverse=sort_desc,
        )
    else:
        filtered_results.sort(key=lambda item: item["score"]["final_score"], reverse=sort_desc)

    applied_count = sum(1 for item in scored_results if st.session_state.get(f"applied-{item['index']}"))
    average_score = round(mean([item["score"]["final_score"] for item in scored_results]), 1)
    high_count = sum(1 for item in scored_results if item["priority"] == "High")

    with right:
        metric_col_1, metric_col_2, metric_col_3, metric_col_4 = st.columns(4)
        metric_cards = [
            (metric_col_1, "Top score", f"{scored_results[0]['score']['final_score']}"),
            (metric_col_2, "Average", f"{average_score}"),
            (metric_col_3, "High priority", f"{high_count}"),
            (metric_col_4, "Applied", f"{applied_count}"),
        ]
        for column, label, value in metric_cards:
            with column:
                st.markdown(
                    f'<div class="kpi-shell"><div class="label">{label}</div><div class="value">{value}</div></div>',
                    unsafe_allow_html=True,
                )

        st.info(f"Detected {len(scored_results)} opportunities, filtered view shows {len(filtered_results)}.")
        if ignored_results:
            st.caption(f"Ignored {len(ignored_results)} non-opportunity email(s).")

        chart_col_1, chart_col_2 = st.columns(2)
        with chart_col_1:
            st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
            st.subheader("Priority mix")
            if priority_counts:
                chart_data = {label: count for label, count in priority_counts}
                st.bar_chart(chart_data)
            else:
                st.caption("No priority data yet.")
            st.markdown("</div>", unsafe_allow_html=True)
        with chart_col_2:
            st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
            st.subheader("Opportunity types")
            if type_counts:
                chart_data = {label: count for label, count in type_counts}
                st.bar_chart(chart_data)
            else:
                st.caption("No type data yet.")
            st.markdown("</div>", unsafe_allow_html=True)

        tab_ranked, tab_ignored, tab_summary = st.tabs(["Ranked", "Ignored", "Summary"])

        with tab_ranked:
            if not filtered_results:
                st.warning("No opportunities match the selected filters.")
                st.write("Try lowering the minimum score, clearing search terms, or switching type filters.")
            else:
                total_filtered = len(filtered_results)
                for item in filtered_results:
                    score = item["score"]
                    extracted = item["extracted"]
                    checklist = item["checklist"]
                    applied_key = f"applied-{item['index']}"
                    is_applied = bool(st.session_state.get(applied_key))
                    accent = priority_accent(item["priority"])
                    tone = priority_tone(item["priority"])
                    rank = filtered_results.index(item) + 1
                    deadline_text = checklist["deadline_line"]
                    opportunity_type = extracted.get("opportunity_type", "unknown")
                    tags = [
                        f"Score {score['final_score']}",
                        item["priority"],
                        opportunity_type,
                        deadline_text,
                    ]

                    with st.container(border=True):
                        st.markdown(
                            f"""
                            <div class="card" style="border-left: 6px solid {accent}; background: linear-gradient(90deg, {tone} 0%, rgba(255,255,255,0.96) 18%, rgba(255,255,255,0.9) 100%);">
                                <div class="card-title-row">
                                    <div>
                                        <h3 style="margin:0 0 0.3rem 0;">{item['subject']}</h3>
                                        <div class="meta">Rank #{rank} of {total_filtered} · {'Applied' if is_applied else 'Not applied yet'}</div>
                                    </div>
                                    <div class="meta" style="text-align:right; min-width: 8rem;">
                                        <strong>Deadline</strong><br/>
                                        <span>{deadline_text}</span>
                                    </div>
                                </div>
                                <div class="badge-row">
                                    <span class="badge">Score {score['final_score']}</span>
                                    <span class="badge">{item['priority']} priority</span>
                                    <span class="badge">{opportunity_type}</span>
                                    <span class="badge">{deadline_text}</span>
                                </div>
                                <div class="meta" style="margin-bottom:0.65rem; line-height:1.55;">{extracted.get('evidence', '')[:220]}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        details_col, actions_col = st.columns([1.15, 0.85])

                        with details_col:
                            with st.expander("View extracted fields", expanded=False):
                                st.json(extracted)
                                st.json(score)
                            st.progress(min(score["final_score"] / 100, 1.0))
                            st.caption("Score reflects fit, urgency, effort, and impact signals.")

                        with actions_col:
                            checklist_text = render_checklist_text(checklist, extracted, score)
                            quick_cols = st.columns(2)
                            with quick_cols[0]:
                                st.download_button(
                                    label="Checklist TXT",
                                    data=checklist_text,
                                    file_name=f"checklist-{item['index']}.txt",
                                    mime="text/plain",
                                    use_container_width=True,
                                )
                            with quick_cols[1]:
                                st.download_button(
                                    label="Item JSON",
                                    data=json.dumps(
                                        {
                                            "subject": item["subject"],
                                            "score": score,
                                            "extracted": extracted,
                                            "checklist": checklist,
                                        },
                                        ensure_ascii=False,
                                        indent=2,
                                    ),
                                    file_name=f"opportunity-{item['index']}.json",
                                    mime="application/json",
                                    use_container_width=True,
                                )
                            st.text_area(
                                "Checklist preview",
                                value=checklist_text,
                                height=220,
                                key=f"checklist-preview-{item['index']}",
                            )

                        button_label = "Mark as unapplied" if is_applied else "Mark as applied"
                        if st.button(button_label, key=f"apply-{item['index']}", use_container_width=True):
                            st.session_state[applied_key] = not is_applied
                            st.rerun()
                        if st.session_state.get(applied_key):
                            st.success("Marked as applied")

        with tab_ignored:
            if not ignored_results:
                st.info("No non-opportunity emails were filtered out.")
            else:
                for item in ignored_results:
                    with st.expander(f"{item['subject']} (#{item['index']})", expanded=False):
                        st.write(item["body"][:500] or "No body text provided")
                        st.caption(f"Evidence line used for filter: {item['evidence']}")

        with tab_summary:
            st.markdown('<div class="section-title"><h3>Bulk actions</h3><span class="subtle">Exports and shortcuts</span></div>', unsafe_allow_html=True)
            summary_cols = st.columns(3)
            with summary_cols[0]:
                st.markdown('<div class="glass-panel"><div class="subtle">Filtered count</div><div style="font-size:1.6rem; font-weight:800;">' + str(len(filtered_results)) + '</div></div>', unsafe_allow_html=True)
            with summary_cols[1]:
                st.markdown('<div class="glass-panel"><div class="subtle">Applied count</div><div style="font-size:1.6rem; font-weight:800;">' + str(applied_count) + '</div></div>', unsafe_allow_html=True)
            with summary_cols[2]:
                best_subject = filtered_results[0]["subject"] if filtered_results else "None yet"
                st.markdown(f'<div class="glass-panel"><div class="subtle">Top opportunity</div><div style="font-size:1.1rem; font-weight:800; line-height:1.3;">{best_subject}</div></div>', unsafe_allow_html=True)
            action_col_1, action_col_2 = st.columns(2)
            with action_col_1:
                st.download_button(
                    label="Download all filtered checklists",
                    data=export_all_checklists(filtered_results) if filtered_results else "No filtered opportunities available.",
                    file_name="all-checklists.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
            with action_col_2:
                st.download_button(
                    label="Download filtered results CSV",
                    data=export_results_csv(filtered_results) if filtered_results else "rank,subject,score,priority,type,deadline,applied\n",
                    file_name="filtered-results.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            st.download_button(
                label="Download filtered results JSON",
                data=export_results_json(filtered_results) if filtered_results else "[]",
                file_name="filtered-results.json",
                mime="application/json",
                use_container_width=True,
            )
            st.divider()
            st.write("Top opportunities")
            for item in filtered_results[:5]:
                st.write(f"- {item['subject']} | Score {item['score']['final_score']} | Priority {item['priority']}")
            if filtered_results:
                st.caption(f"Showing top {min(5, len(filtered_results))} of {len(filtered_results)} filtered opportunities.")
                st.caption("Use the JSON export if you want to feed this ranking into another workflow.")
else:
    st.subheader("What you can do here")
    st.write("Load the demo inbox, upload your own JSON, or paste emails and a profile to see ranked opportunities.")
    st.write("The app keeps the classifier and scorer deterministic, so the ranking is repeatable across runs.")