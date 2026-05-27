from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional, List, Iterator, Tuple

import pandas as pd

# pyrefly: ignore [missing-import]
import streamlit as st

# -----------------------------
# Import your compiled LangGraph app
# -----------------------------
from backend import app


# -----------------------------
# Helpers
# -----------------------------
def safe_slug(title: str) -> str:
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9 _-]+", "", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s or "blog"


def try_stream(graph_app, inputs: Dict[str, Any]) -> Iterator[Tuple[str, Any]]:
    """
    Stream graph progress if available; else invoke.
    Yields ("updates"/"values"/"final", payload).
    """
    try:
        for step in graph_app.stream(inputs, stream_mode="updates"):
            yield ("updates", step)
        out = graph_app.invoke(inputs)
        yield ("final", out)
        return
    except Exception:
        pass

    try:
        for step in graph_app.stream(inputs, stream_mode="values"):
            yield ("values", step)
        out = graph_app.invoke(inputs)
        yield ("final", out)
        return
    except Exception:
        pass

    out = graph_app.invoke(inputs)
    yield ("final", out)


def extract_latest_state(current_state: Dict[str, Any], step_payload: Any) -> Dict[str, Any]:
    if isinstance(step_payload, dict):
        if len(step_payload) == 1 and isinstance(next(iter(step_payload.values())), dict):
            inner = next(iter(step_payload.values()))
            current_state.update(inner)
        else:
            current_state.update(step_payload)
    return current_state


# -----------------------------
# Past blogs helpers
# -----------------------------
def list_past_blogs() -> List[Path]:
    """
    Returns .md files in current working directory, newest first.
    Filters out obvious non-blog markdown files if needed.
    """
    cwd = Path(".")
    files = [p for p in cwd.glob("*.md") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def read_md_file(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def extract_title_from_md(md: str, fallback: str) -> str:
    """
    Use first '# ' heading as title if present.
    """
    for line in md.splitlines():
        if line.startswith("# "):
            t = line[2:].strip()
            return t or fallback
    return fallback


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="LangGraph Blog Writer", layout="wide")

# -----------------------------
# Custom CSS Styling Injection
# -----------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&family=Fira+Code:wght@400;500&display=swap');

    /* Global Font Overrides */
    html, body, .stApp, .stMarkdown, p, li, td, th, button, input, textarea, select, label {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    }

    h1, h2, h3, h4, h5, h6, [data-testid="stWidgetLabel"] p {
        font-family: 'Space Grotesk', sans-serif !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em !important;
    }

    /* Base App Theme Styling (Cinematic Dark Mode) */
    .stApp {
        background-color: #05070c !important;
        background-image: 
            radial-gradient(circle at 10% 20%, rgba(99, 102, 241, 0.08) 0%, transparent 45%),
            radial-gradient(circle at 90% 80%, rgba(6, 182, 212, 0.08) 0%, transparent 50%),
            radial-gradient(circle at 50% 50%, rgba(0, 0, 0, 0) 0%, #05070c 100%) !important;
        background-attachment: fixed !important;
    }

    /* Hide Default Streamlit Header & Footer */
    [data-testid="stHeader"] {
        background: transparent !important;
        display: none !important;
    }
    [data-testid="stDecoration"] {
        background: transparent !important;
        display: none !important;
    }
    footer {
        visibility: hidden !important;
        display: none !important;
    }

    /* Main margins adjustment */
    .block-container, [data-testid="stAppViewBlockContainer"] {
        padding-top: 1.5rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 2.5rem !important;
        padding-right: 2.5rem !important;
        max-width: 1400px;
        margin: 0 auto;
    }

    /* Floating Cards / Containers (Glassmorphism) */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(13, 17, 28, 0.45) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border: 1px solid rgba(255, 255, 255, 0.07) !important;
        border-radius: 16px !important;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4) !important;
        padding: 1.8rem !important;
        margin-bottom: 1.5rem !important;
        transition: border-color 0.3s ease, box-shadow 0.3s ease !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: rgba(99, 102, 241, 0.25) !important;
        box-shadow: 0 8px 32px 0 rgba(99, 102, 241, 0.08) !important;
    }

    /* Typography styles */
    h1 {
        font-size: 2.8rem !important;
        font-weight: 700 !important;
        background: linear-gradient(135deg, #00f2fe 0%, #6366f1 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    h2, h3 {
        color: #f8fafc !important;
    }
    p, li, td, th {
        color: #cbd5e1 !important;
    }
    strong {
        color: #f1f5f9 !important;
    }

    /* Inputs & Forms */
    .stTextArea textarea {
        background-color: rgba(7, 10, 19, 0.6) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 10px !important;
        color: #f1f5f9 !important;
        font-size: 0.95rem !important;
        line-height: 1.5 !important;
        padding: 12px !important;
        transition: all 0.3s ease !important;
    }
    .stTextArea textarea:focus {
        border-color: #6366f1 !important;
        box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2) !important;
        background-color: rgba(7, 10, 19, 0.8) !important;
    }

    .stDateInput input {
        background-color: rgba(7, 10, 19, 0.6) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 10px !important;
        color: #f1f5f9 !important;
        padding: 10px !important;
        transition: all 0.3s ease !important;
    }
    .stDateInput input:focus {
        border-color: #6366f1 !important;
        box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2) !important;
    }

    /* Buttons Override */
    /* Primary (Generate Blog) */
    div.stButton > button[kind="primary"] {
        width: 100% !important;
        background: linear-gradient(135deg, #6366f1 0%, #3b82f6 100%) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.7rem 1.5rem !important;
        font-weight: 600 !important;
        font-size: 1.05rem !important;
        letter-spacing: 0.025em !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 4px 14px 0 rgba(99, 102, 241, 0.35) !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #4f46e5 0%, #2563eb 100%) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px 0 rgba(99, 102, 241, 0.5) !important;
    }
    div.stButton > button[kind="primary"]:active {
        transform: translateY(0) !important;
    }

    /* Secondary (Load selected blog) */
    div.stButton > button[kind="secondary"] {
        width: 100% !important;
        background: rgba(255, 255, 255, 0.04) !important;
        color: #e2e8f0 !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 10px !important;
        padding: 0.6rem 1.2rem !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
    }
    div.stButton > button[kind="secondary"]:hover {
        background: rgba(255, 255, 255, 0.08) !important;
        border-color: rgba(255, 255, 255, 0.15) !important;
        color: #ffffff !important;
        transform: translateY(-1px) !important;
    }

    /* Download Button */
    div.stDownloadButton > button {
        background: linear-gradient(135deg, #059669 0%, #10b981 100%) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.7rem 1.5rem !important;
        font-weight: 600 !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 4px 14px 0 rgba(16, 185, 129, 0.3) !important;
    }
    div.stDownloadButton > button:hover {
        background: linear-gradient(135deg, #047857 0%, #059669 100%) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 20px 0 rgba(16, 185, 129, 0.4) !important;
    }

    /* Tabs styling */
    div[data-testid="stTabs"] {
        border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
        margin-bottom: 1.5rem !important;
    }
    div[data-testid="stTabs"] button {
        font-family: 'Space Grotesk', sans-serif !important;
        font-size: 1rem !important;
        font-weight: 500 !important;
        color: #94a3b8 !important;
        transition: all 0.2s ease !important;
        border-bottom: 2px solid transparent !important;
        background: transparent !important;
    }
    div[data-testid="stTabs"] button:hover {
        color: #f1f5f9 !important;
    }
    div[data-testid="stTabs"] button[aria-selected="true"] {
        color: #00f2fe !important;
        border-bottom: 2px solid #00f2fe !important;
        font-weight: 600 !important;
    }

    /* Radio button library cards styling */
    div[data-testid="stRadio"] div[role="radiogroup"] {
        gap: 0.5rem !important;
    }
    div[data-testid="stRadio"] label[data-baseweb="radio"] {
        background: rgba(255, 255, 255, 0.02) !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-radius: 8px !important;
        padding: 0.6rem 1rem !important;
        margin-bottom: 0px !important;
        transition: all 0.2s ease !important;
        width: 100% !important;
    }
    div[data-testid="stRadio"] label[data-baseweb="radio"]:hover {
        background: rgba(255, 255, 255, 0.05) !important;
        border-color: rgba(255, 255, 255, 0.1) !important;
    }
    div[data-testid="stRadio"] label[data-baseweb="radio"] div:first-child {
        border-color: rgba(255, 255, 255, 0.3) !important;
    }
    div[data-testid="stRadio"] label[data-baseweb="radio"] div[role="presentation"] {
        background-color: transparent !important;
    }

    /* Expanders */
    div[data-testid="stExpander"] {
        background: rgba(15, 23, 42, 0.3) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 10px !important;
        box-shadow: none !important;
    }
    div[data-testid="stExpander"] details summary {
        font-family: 'Space Grotesk', sans-serif !important;
        font-weight: 500 !important;
        color: #cbd5e1 !important;
    }

    /* Alerts */
    div[data-testid="stAlert"] {
        background: rgba(15, 23, 42, 0.65) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 10px !important;
        backdrop-filter: blur(8px) !important;
    }
    div[data-testid="stAlert"] div[data-testid="stMarkdownContainer"] p {
        color: #e2e8f0 !important;
    }

    /* Dataframe wrapper styling */
    div[data-testid="stDataFrame"] {
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px !important;
        overflow: hidden !important;
        background: rgba(15, 23, 42, 0.4) !important;
    }

    /* Custom terminal log textarea styling */
    div.stTextArea textarea[aria-label="Event log"] {
        font-family: 'Fira Code', 'Courier New', Courier, monospace !important;
        background-color: #020408 !important;
        border: 1px solid rgba(0, 242, 254, 0.25) !important;
        color: #38bdf8 !important;
        box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.8), 0 0 15px rgba(0, 242, 254, 0.05) !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Storage for latest run
if "last_out" not in st.session_state:
    st.session_state["last_out"] = None

# Keep topic input as-is; optionally prefill for next run after loading a blog
if "topic_prefill" in st.session_state and isinstance(st.session_state["topic_prefill"], str):
    pass

logs: List[str] = []

def log(msg: str):
    logs.append(msg)

# -----------------------------
# Dual Column Workspace Layout
# -----------------------------
col_left, col_right = st.columns([1, 2], gap="large")

with col_left:
    # Generator Settings Card
    with st.container(border=True):
        st.subheader("✍️ Create Blog")
        topic = st.text_area(
            "Topic",
            value=st.session_state.get("topic_prefill", ""),
            height=120,
        )
        as_of = st.date_input("As-of date", value=date.today())
        run_btn = st.button("🚀 Generate Blog", type="primary")

    # Library / Past Blogs Card
    with st.container(border=True):
        st.subheader("📚 Library")
        past_files = list_past_blogs()
        if not past_files:
            st.caption("No saved blogs found (*.md in current folder).")
            selected_md_file = None
        else:
            options: List[str] = []
            file_by_label: Dict[str, Path] = {}
            for p in past_files[:50]:
                try:
                    md_text = read_md_file(p)
                    title = extract_title_from_md(md_text, p.stem)
                except Exception:
                    title = p.stem
                label = f"{title}  ·  {p.name}"
                options.append(label)
                file_by_label[label] = p

            selected_label = st.radio(
                "Select a blog to load",
                options=options,
                index=0,
                label_visibility="collapsed",
            )
            selected_md_file = file_by_label.get(selected_label)

            if st.button("📂 Load selected blog"):
                if selected_md_file:
                    md_text = read_md_file(selected_md_file)
                    st.session_state["last_out"] = {
                        "plan": None,
                        "evidence": [],
                        "final": md_text,
                    }
                    st.session_state["topic_prefill"] = extract_title_from_md(md_text, selected_md_file.stem)
                    st.rerun()

with col_right:
    # Branding Header
    st.markdown(
        """
        <div style="margin-bottom: 2rem;">
            <h1 style="margin: 0; font-family: 'Space Grotesk', sans-serif; font-size: 2.6rem; font-weight: 700; background: linear-gradient(135deg, #00f2fe 0%, #6366f1 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">BlogGenius</h1>
            <p style="margin: 0.2rem 0 0 0; color: #94a3b8; font-size: 1rem;">LangGraph Multi-Agent Blog Writing System</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Executing Agent Pipeline
    if run_btn:
        if not topic.strip():
            st.warning("Please enter a topic.")
            st.stop()

        inputs: Dict[str, Any] = {
            "topic": topic.strip(),
            "mode": "",
            "needs_research": False,
            "queries": [],
            "evidence": [],
            "plan": None,
            "as_of": as_of.isoformat(),
            "recency_days": 7,
            "sections": [],
            "final": "",
        }

        with st.container(border=True):
            status = st.status("Running agent graph...", expanded=True)
            progress_area = st.empty()

            current_state: Dict[str, Any] = {}
            last_node = None

            for kind, payload in try_stream(app, inputs):
                if kind in ("updates", "values"):
                    node_name = None
                    if isinstance(payload, dict) and len(payload) == 1 and isinstance(next(iter(payload.values())), dict):
                        node_name = next(iter(payload.keys()))
                    if node_name and node_name != last_node:
                        status.write(f"➡️ Node: `{node_name}`")
                        last_node = node_name

                    current_state = extract_latest_state(current_state, payload)

                    summary = {
                        "mode": current_state.get("mode"),
                        "needs_research": current_state.get("needs_research"),
                        "queries": current_state.get("queries", [])[:5] if isinstance(current_state.get("queries"), list) else [],
                        "evidence_count": len(current_state.get("evidence", []) or []),
                        "tasks": len((current_state.get("plan") or {}).get("tasks", [])) if isinstance(current_state.get("plan"), dict) else None,
                        "sections_done": len(current_state.get("sections", []) or []),
                    }
                    progress_area.json(summary)

                    log(f"[{kind}] {json.dumps(payload, default=str)[:1200]}")

                elif kind == "final":
                    out = payload
                    st.session_state["last_out"] = out
                    status.update(label="✅ Generation Complete!", state="complete", expanded=False)
                    log("[final] received final state")

    # Render Result Tabs
    out = st.session_state.get("last_out")
    if out:
        tab_plan, tab_evidence, tab_preview, tab_logs = st.tabs(
            ["🧩 Plan", "🔎 Evidence", "📝 Markdown Preview", "🧾 Logs"]
        )

        # --- Plan tab ---
        with tab_plan:
            with st.container(border=True):
                st.subheader("Execution Plan")
                plan_obj = out.get("plan")
                if not plan_obj:
                    st.info("No plan found in output.")
                else:
                    if hasattr(plan_obj, "model_dump"):
                        plan_dict = plan_obj.model_dump()
                    elif isinstance(plan_obj, dict):
                        plan_dict = plan_obj
                    else:
                        plan_dict = json.loads(json.dumps(plan_obj, default=str))

                    st.markdown(f"### **Title:** {plan_dict.get('blog_title')}")
                    cols = st.columns(3)
                    with cols[0]:
                        st.markdown(f"**Audience:**\n{plan_dict.get('audience')}")
                    with cols[1]:
                        st.markdown(f"**Tone:**\n{plan_dict.get('tone')}")
                    with cols[2]:
                        st.markdown(f"**Blog Kind:**\n{plan_dict.get('blog_kind', '')}")

                    st.markdown("---")
                    st.markdown("#### **Tasks Outline**")
                    tasks = plan_dict.get("tasks", [])
                    if tasks:
                        df = pd.DataFrame(
                            [
                                {
                                    "id": t.get("id"),
                                    "title": t.get("title"),
                                    "target_words": t.get("target_words"),
                                    "requires_research": t.get("requires_research"),
                                    "requires_citations": t.get("requires_citations"),
                                    "requires_code": t.get("requires_code"),
                                    "tags": ", ".join(t.get("tags") or []),
                                }
                                for t in tasks
                            ]
                        ).sort_values("id")
                        st.dataframe(df, use_container_width=True, hide_index=True)

                        with st.expander("🔍 Task Details (JSON)"):
                            st.json(tasks)

        # --- Evidence tab ---
        with tab_evidence:
            with st.container(border=True):
                st.subheader("Gathered Evidence")
                evidence = out.get("evidence") or []
                if not evidence:
                    st.info("No evidence returned (maybe closed_book mode or no Tavily key/results).")
                else:
                    rows = []
                    for e in evidence:
                        if hasattr(e, "model_dump"):
                            e = e.model_dump()
                        rows.append(
                            {
                                "title": e.get("title"),
                                "published_at": e.get("published_at"),
                                "source": e.get("source"),
                                "url": e.get("url"),
                            }
                        )
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # --- Preview tab ---
        with tab_preview:
            with st.container(border=True):
                st.subheader("Markdown Preview")
                final_md = out.get("final") or ""
                if not final_md:
                    st.warning("No final markdown found.")
                else:
                    st.markdown(final_md, unsafe_allow_html=False)

                    plan_obj = out.get("plan")
                    if hasattr(plan_obj, "blog_title"):
                        blog_title = plan_obj.blog_title
                    elif isinstance(plan_obj, dict):
                        blog_title = plan_obj.get("blog_title", "blog")
                    else:
                        blog_title = extract_title_from_md(final_md, "blog")

                    md_filename = f"{safe_slug(blog_title)}.md"
                    
                    st.markdown("---")
                    st.download_button(
                        "⬇️ Download Markdown File",
                        data=final_md.encode("utf-8"),
                        file_name=md_filename,
                        mime="text/markdown",
                    )

        # --- Logs tab ---
        with tab_logs:
            with st.container(border=True):
                st.subheader("System Logs")
                if "logs" not in st.session_state:
                    st.session_state["logs"] = []
                if logs:
                    st.session_state["logs"].extend(logs)

                st.text_area(
                    "Event log", 
                    value="\n\n".join(st.session_state["logs"][-80:]), 
                    height=520,
                    label_visibility="collapsed"
                )
    else:
        st.info("Enter a topic on the left and click **Generate Blog** to begin, or select a past blog from the library.")