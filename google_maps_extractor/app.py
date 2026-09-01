import os
import sys
import time
import shutil
import threading
import pandas as pd
import streamlit as st

# Ensure workspace packages are in import path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_maps_extractor.database import (
    init_db, create_job, update_job_status, get_job_status,
    get_job_results, get_job_history, clear_job_history
)
from google_maps_extractor.scraper import run_scraper
from google_maps_extractor.exporter import export_results, COLUMN_MAPPING
from google_maps_extractor.utils import LOGS_DIR, setup_directories

# Initialize paths and database
setup_directories()
init_db()

# Hide deploy button & toolbar items
st.set_option("client.toolbarMode", "minimal")

# Page configuration
st.set_page_config(
    page_title="G-Maps Business Extractor",
    page_icon="📍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium CSS styling
st.markdown("""
<style>
    /* Main title custom typography */
    h1 {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        font-weight: 800;
        letter-spacing: -0.025em;
        background: linear-gradient(135deg, #3b82f6, #1d4ed8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    h3 {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        font-weight: 600;
        color: #1e293b;
    }

    /* Code logs area design */
    .stCodeBlock {
        background-color: #0f172a !important;
        border: 1px solid #1e293b;
        border-radius: 0.5rem;
    }
    .stCodeBlock pre {
        color: #38bdf8 !important;
        font-family: 'Courier New', Courier, monospace;
        font-size: 0.85rem !important;
        max-height: 300px;
        overflow-y: auto;
    }

    /* Metric styling */
    [data-testid="stMetricValue"] {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1e3a8a;
    }

    /* Hide Deploy button, Print option, Record screen, and Streamlit footer/menu items */
    .stAppDeployButton,
    .stDeployButton,
    button[data-testid="stHeaderDeployButton"],
    footer,
    ul[data-testid="main-menu-list"] li:nth-child(2),
    ul[data-testid="main-menu-list"] li:nth-child(3),
    [data-testid="stStatusWidget"],
    #MainMenu ul li:has(span:contains("Print")),
    #MainMenu ul li:has(span:contains("Record screen")) {
        display: none !important;
    }

    /* Hide Print & Record Screen menu items in Streamlit dropdown */
    ul[data-testid="main-menu-list"] > div:nth-child(2),
    ul[data-testid="main-menu-list"] > div:nth-child(3) {
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)


# ── Session State & Active Job Synchronization ────────────────────────────────
# Check database for any job with 'running' or 'pending' status
history_jobs = get_job_history()
active_job = next((j for j in history_jobs if j["status"] in ["running", "pending"]), None)

if active_job:
    st.session_state.extraction_active = True
    st.session_state.active_job_id = active_job["id"]
else:
    if "extraction_active" not in st.session_state or not (st.session_state.scraper_thread and st.session_state.scraper_thread.is_alive()):
        st.session_state.extraction_active = False
        st.session_state.active_job_id = None

if "stop_event" not in st.session_state:
    st.session_state.stop_event = None
if "scraper_thread" not in st.session_state:
    st.session_state.scraper_thread = None
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()


# ── Sidebar Control Panel ─────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📍 Extractor Parameters")

    query = st.text_input(
        "Search Query",
        placeholder="e.g., Dentists in Seattle",
        help="Type search terms exactly as you would search on Google Maps."
    )

    max_results = st.number_input(
        "Maximum Results",
        min_value=1,
        max_value=1000,
        value=30,
        step=5,
        help="Set maximum number of businesses to scrape."
    )

    st.selectbox(
        "Default Export Format",
        options=["CSV", "Excel"],
        index=0
    )

    headless = st.checkbox(
        "Run in Headless Mode",
        value=True,
        help="Run chromium browser in the background without UI window."
    )

    auto_linkedin = st.checkbox(
        "Auto-Extract LinkedIn Profiles",
        value=True,
        help="Automatically crawl company websites for official LinkedIn profiles after Google Maps extraction finishes."
    )

    st.markdown("---")

    # Run Buttons
    col_start, col_stop = st.columns(2)
    with col_start:
        start_btn = st.button(
            "▶ Start",
            disabled=st.session_state.extraction_active,
            use_container_width=True,
            type="primary"
        )
    with col_stop:
        stop_btn = st.button(
            "■ Stop",
            disabled=not st.session_state.extraction_active,
            use_container_width=True
        )

    st.markdown("---")

    clear_history_btn = st.button(
        "🗑 Clear Job History",
        use_container_width=True,
        type="secondary"
    )

# ── Button Handlers ───────────────────────────────────────────────────────────
if start_btn:
    if not query.strip():
        st.sidebar.error("Please enter a search query first.")
    else:
        job_id = create_job(query.strip(), max_results)

        stop_event = threading.Event()
        scraper_thread = threading.Thread(
            target=run_scraper,
            args=(job_id, query.strip(), max_results, stop_event, headless, auto_linkedin),
            daemon=True
        )

        st.session_state.extraction_active = True
        st.session_state.active_job_id = job_id
        st.session_state.stop_event = stop_event
        st.session_state.scraper_thread = scraper_thread
        st.session_state.start_time = time.time()

        scraper_thread.start()
        st.rerun()


if stop_btn:
    if st.session_state.stop_event:
        st.session_state.stop_event.set()
        st.sidebar.warning("Stop requested — finishing current listing...")
    elif st.session_state.active_job_id:
        update_job_status(st.session_state.active_job_id, "stopped")
        st.session_state.extraction_active = False
        st.session_state.active_job_id = None
        st.rerun()

if clear_history_btn:
    clear_job_history()
    for f in os.listdir(LOGS_DIR):
        if f.startswith("job_") or f == "app.log":
            try:
                os.remove(os.path.join(LOGS_DIR, f))
            except Exception:
                pass
    st.sidebar.success("Cleared all logs and job history.")
    time.sleep(0.8)
    st.rerun()

# ── Main Viewport ─────────────────────────────────────────────────────────────
st.title("📍 Google Maps Information Extractor")

if st.session_state.extraction_active and st.session_state.active_job_id:
    # ── Active Extraction UI ──────────────────────────────────────────────────
    job_id = st.session_state.active_job_id
    job_details = get_job_status(job_id)

    if job_details and job_details["status"] in ["running", "pending"]:
        status    = job_details["status"]
        phase     = job_details.get("phase", "google_maps")
        processed = job_details["total_results"]
        current_biz = job_details["current_business"]


        phase_label = "📍 Phase 1: Google Maps" if phase == "google_maps" else "🔗 Phase 2: LinkedIn Discovery"
        st.markdown(f"#### Active Job: **{job_details['query']}** ({phase_label})")

        # Metric cards
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Status", status.upper())
        with m2:
            st.metric("Phase", "Google Maps" if phase == "google_maps" else "LinkedIn Crawler")
        with m3:
            st.metric("Total Listings", f"{processed} / {job_details['max_results']}")
        with m4:
            st.metric("Current Target", current_biz or "Starting browser...")

        # Progress bar
        st.progress(min(1.0, processed / max(job_details["max_results"], 1)))

        # Logs + live preview
        col_logs, col_table = st.columns([2, 3])

        with col_logs:
            st.subheader("Live Process Logs")
            log_path = os.path.join(LOGS_DIR, f"job_{job_id}.log")
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as lf:
                    lines = lf.readlines()
                st.code("".join(lines[-30:]), language="text")
            else:
                st.info("Waiting for log file...")

        with col_table:
            st.subheader("Extracted Results Preview")
            results = get_job_results(job_id)
            if results:
                df = pd.DataFrame(results)
                preview_cols = ["name", "website", "linkedin_url", "linkedin_status", "phone"]
                existing = [c for c in preview_cols if c in df.columns]
                st.dataframe(df[existing], height=270, hide_index=True)
            else:
                st.info("No results yet — waiting for browser to load search results...")

        # Check thread or DB status completion
        if job_details["status"] in ["completed", "stopped", "failed"]:
            st.session_state.extraction_active = False
            st.session_state.active_job_id    = None
            st.session_state.stop_event       = None
            st.session_state.scraper_thread   = None
            st.toast(f"Scraping finished with status: {job_details['status'].upper()}", icon="✅")
            st.rerun()


        time.sleep(1.5)
        st.rerun()
    else:
        st.session_state.extraction_active = False
        st.session_state.active_job_id = None
        st.rerun()



else:
    # ── History / Export Viewport ─────────────────────────────────────────────
    history = get_job_history()

    if not history:
        st.info("Welcome! Configure the **Extractor Parameters** in the sidebar, then click **▶ Start**.")
        st.markdown("""
### How it works
* **Playwright Scraping** — Opens Google Maps, scrolls the results list, and extracts full details for each listing.
* **Incremental Saving** — Results are written to a local SQLite database in real-time, protecting against interruptions.
* **Export** — Download any previous run as a clean CSV or Excel spreadsheet.
* **Background Threading** — The UI stays responsive throughout so you can monitor progress or stop at any time.
        """)
    else:
        st.subheader("Previous Extraction Runs")

        df_hist = pd.DataFrame(history).rename(columns={
            "id":            "Job ID",
            "query":         "Search Query",
            "max_results":   "Max Requested",
            "status":        "Status",
            "total_results": "Extracted",
            "created_at":    "Date"
        })
        st.dataframe(
            df_hist[["Job ID", "Search Query", "Max Requested", "Status", "Extracted", "Date"]],
            hide_index=True
        )

        st.markdown("### 📥 Export & Download")

        job_ids = [j["id"] for j in history]
        selected_id = st.selectbox(
            "Select Run",
            options=job_ids,
            format_func=lambda x: (
                f"Job #{x}: '{next(j['query'] for j in history if j['id'] == x)}'"
                f" — {next(j['total_results'] for j in history if j['id'] == x)} results"
            )
        )

        if selected_id:
            col_fmt, col_dl, col_re = st.columns([1, 1, 1], vertical_alignment="bottom")

            with col_fmt:
                fmt = st.selectbox("Format", options=["CSV", "Excel"], key="dl_format")

            with col_dl:
                try:
                    filepath, filename = export_results(selected_id, fmt)
                    save_btn = st.button(
                        f"📥 Save {filename}",
                        use_container_width=True,
                        type="primary",
                        key=f"save_{selected_id}_{fmt}"
                    )
                    if save_btn:
                        dest_dir = os.path.expanduser("~/Downloads")
                        os.makedirs(dest_dir, exist_ok=True)
                        dest_path = os.path.join(dest_dir, filename)
                        shutil.copy2(filepath, dest_path)
                        st.toast(f"Saved to {dest_path}", icon="✅")
                except Exception as e:
                    st.error(f"Export failed: {e}")


            with col_re:
                run_li_btn = st.button(
                    "🔗 Run LinkedIn Extraction",
                    disabled=st.session_state.extraction_active,
                    use_container_width=True,
                    key=f"run_li_{selected_id}"
                )
                if run_li_btn:
                    stop_event = threading.Event()
                    from google_maps_extractor.linkedin_extractor import run_linkedin_pipeline
                    from google_maps_extractor.utils import get_logger

                    def _run_linkedin_task(j_id, s_event, h_less):
                        lg = get_logger(j_id)
                        run_linkedin_pipeline(j_id, s_event, headless=h_less, logger=lg)
                        update_job_status(j_id, "completed")

                    scraper_thread = threading.Thread(
                        target=_run_linkedin_task,
                        args=(selected_id, stop_event, headless),
                        daemon=True
                    )

                    st.session_state.extraction_active = True
                    st.session_state.active_job_id = selected_id
                    st.session_state.stop_event = stop_event
                    st.session_state.scraper_thread = scraper_thread
                    st.session_state.start_time = time.time()

                    scraper_thread.start()
                    st.rerun()


            # Full data preview
            st.markdown("#### Data Preview")
            results = get_job_results(selected_id)
            if results:
                df_res = (
                    pd.DataFrame(results)
                    .drop(columns=["id", "job_id", "created_at"], errors="ignore")
                    .rename(columns=COLUMN_MAPPING)
                )
                st.dataframe(df_res, hide_index=True)
            else:
                st.warning("No records found for this run.")
