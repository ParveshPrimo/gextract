import json
import os
import time

import streamlit as st
from dotenv import load_dotenv

from google_maps_extractor.utils import DB_DIR, setup_directories

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

LOCKS_FILE = os.path.join(DB_DIR, "auth_locks.json")


def _load_env() -> None:
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)
    load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)


def _get_max_attempts() -> int:
    _load_env()
    return int(os.getenv("MAX_LOGIN_ATTEMPTS", "3"))


def _get_lockout_seconds() -> int:
    _load_env()
    return int(os.getenv("LOCKOUT_DURATION_SECONDS", "3600"))


_load_env()
MAX_ATTEMPTS = _get_max_attempts()
LOCKOUT_SECONDS = _get_lockout_seconds()


def get_app_password() -> str | None:
    _load_env()
    return os.getenv("APP_PASSWORD")


def get_client_ip() -> str:
    try:
        headers = st.context.headers
        forwarded = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return headers.get("Remote-Addr") or headers.get("remote-addr", "unknown")
    except Exception:
        pass

    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        from streamlit.web.server.websocket_headers import _get_websocket_headers

        ctx = get_script_run_ctx()
        if ctx:
            headers = _get_websocket_headers(ctx.session_id)
            if headers:
                forwarded = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
                if forwarded:
                    return forwarded.split(",")[0].strip()
                return headers.get("Remote-Addr") or headers.get("remote-addr", "unknown")
    except Exception:
        pass

    return "unknown"


def _load_locks() -> dict:
    setup_directories()
    if not os.path.exists(LOCKS_FILE):
        return {}
    try:
        with open(LOCKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_locks(data: dict) -> None:
    setup_directories()
    with open(LOCKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _prune_expired(data: dict) -> dict:
    now = time.time()
    cleaned = {}
    for ip, entry in data.items():
        locked_until = entry.get("locked_until", 0)
        if locked_until and locked_until <= now:
            continue
        cleaned[ip] = entry
    return cleaned


def is_ip_locked(ip: str) -> tuple[bool, int]:
    data = _prune_expired(_load_locks())
    _save_locks(data)

    entry = data.get(ip, {})
    locked_until = entry.get("locked_until", 0)
    if locked_until and locked_until > time.time():
        return True, int(locked_until - time.time())
    return False, 0


def record_failed_attempt(ip: str) -> tuple[int, bool]:
    data = _prune_expired(_load_locks())
    entry = data.get(ip, {"attempts": 0, "locked_until": 0})
    entry["attempts"] = entry.get("attempts", 0) + 1

    if entry["attempts"] >= MAX_ATTEMPTS:
        entry["locked_until"] = time.time() + LOCKOUT_SECONDS
        data[ip] = entry
        _save_locks(data)
        return 0, True

    data[ip] = entry
    _save_locks(data)
    return MAX_ATTEMPTS - entry["attempts"], False


def clear_attempts(ip: str) -> None:
    data = _prune_expired(_load_locks())
    if ip in data:
        del data[ip]
        _save_locks(data)


def verify_password(password: str) -> bool:
    app_password = get_app_password()
    if not app_password:
        return False
    return password == app_password


def _format_duration(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def render_lock_screen() -> None:
    st.markdown(
        """
        <style>
            section[data-testid="stSidebar"],
            header[data-testid="stHeader"],
            #MainMenu,
            footer {
                display: none !important;
            }

            .main .block-container {
                max-width: 380px;
                padding: 10vh 1.5rem 2rem;
            }

            .lock-card-header {
                text-align: center;
                margin-bottom: 1.75rem;
            }

            .lock-icon-ring {
                width: 56px;
                height: 56px;
                margin: 0 auto 1rem;
                border-radius: 50%;
                background: #ff4b4b;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.5rem;
                box-shadow: 0 8px 24px rgba(255, 75, 75, 0.25);
            }

            .lock-title {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                font-size: 1.35rem;
                font-weight: 700;
                color: #f8fafc;
                margin: 0 0 0.35rem;
                letter-spacing: -0.02em;
            }

            .lock-subtitle {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                color: #94a3b8;
                font-size: 0.875rem;
                margin: 0;
                line-height: 1.5;
            }

            .lock-panel {
                background: #1e293b;
                border: 1px solid #334155;
                border-bottom: none;
                border-radius: 14px 14px 0 0;
                padding: 1.75rem 1.5rem 0.75rem;
                box-shadow: 0 16px 40px rgba(0, 0, 0, 0.35);
            }

            div[data-testid="stForm"] {
                background: #1e293b;
                border: 1px solid #334155;
                border-top: none;
                border-radius: 0 0 14px 14px;
                padding: 0 1.5rem 1.25rem;
                margin: 0 0 1rem;
            }

            div[data-testid="stForm"] label[data-testid="stWidgetLabel"] {
                display: none;
            }

            div[data-testid="stForm"] input {
                background: #0f172a !important;
                border: 1px solid #475569 !important;
                border-radius: 8px !important;
                color: #f1f5f9 !important;
                font-size: 0.9rem !important;
                padding: 0.65rem 0.85rem !important;
            }

            div[data-testid="stForm"] input:focus {
                border-color: #ff4b4b !important;
                box-shadow: 0 0 0 2px rgba(255, 75, 75, 0.2) !important;
            }

            div[data-testid="stFormSubmitButton"] {
                display: flex;
                justify-content: center;
                margin-top: 0.75rem;
            }

            div[data-testid="stFormSubmitButton"] button {
                width: auto !important;
                min-width: 132px;
                padding: 0.5rem 1.75rem !important;
                border-radius: 8px !important;
                font-weight: 600 !important;
                font-size: 0.875rem !important;
                background: #ff4b4b !important;
                border: none !important;
            }

            div[data-testid="stFormSubmitButton"] button:hover {
                background: #ff3333 !important;
                border: none !important;
            }

            .lock-blocked {
                background: #1e293b;
                border: 1px solid #334155;
                border-top: none;
                border-radius: 0 0 14px 14px;
                padding: 0 1.5rem 1.25rem;
                margin: 0 0 1rem;
            }

            .lock-blocked-inner {
                background: rgba(127, 29, 29, 0.35);
                border: 1px solid #991b1b;
                border-radius: 8px;
                padding: 0.85rem 1rem;
                color: #fecaca;
                font-size: 0.875rem;
                text-align: center;
                line-height: 1.5;
            }

            div[data-testid="stAlert"] {
                margin-top: 0.75rem;
                font-size: 0.85rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    left, center, right = st.columns([1, 1.4, 1])
    with center:
        st.markdown(
            """
            <div class="lock-panel">
                <div class="lock-card-header">
                    <div class="lock-icon-ring">🔒</div>
                    <p class="lock-title">Access Required</p>
                    <p class="lock-subtitle">Enter the application password to continue</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        ip = get_client_ip()
        locked, remaining = is_ip_locked(ip)

        if locked:
            st.markdown(
                f"""
                <div class="lock-blocked">
                    <div class="lock-blocked-inner">
                        <strong>Too many failed attempts.</strong><br>
                        Access from your IP is locked for {_format_duration(remaining)}.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            return

        with st.form("login_form", clear_on_submit=True):
            password = st.text_input(
                "Password",
                type="password",
                placeholder="Enter password",
                label_visibility="collapsed",
            )
            submitted = st.form_submit_button("Unlock", type="primary")

        if submitted:
            if not password:
                st.error("Please enter a password.")
            elif verify_password(password):
                st.session_state.authenticated = True
                clear_attempts(ip)
                st.rerun()
            else:
                remaining_attempts, now_locked = record_failed_attempt(ip)
                if now_locked:
                    st.error(
                        f"Incorrect password. Maximum attempts ({MAX_ATTEMPTS}) reached. "
                        f"Access locked for 1 hour."
                    )
                    st.rerun()
                else:
                    st.error(
                        f"Incorrect password. {remaining_attempts} attempt"
                        f"{'s' if remaining_attempts != 1 else ''} remaining."
                    )


def require_auth() -> None:
    if st.session_state.get("authenticated"):
        return

    app_password = get_app_password()
    if not app_password:
        st.error(
            "APP_PASSWORD is not configured. Set it in your `.env` file before running the application."
        )
        st.stop()

    render_lock_screen()
    st.stop()
