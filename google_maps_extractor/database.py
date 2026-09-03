import os
import sqlite3
from contextlib import contextmanager
from typing import List, Dict, Any, Optional
from datetime import datetime

from .utils import DB_DIR

DB_PATH = os.path.join(DB_DIR, "extractor.db")

@contextmanager
def get_db_conn():
    """Context manager for thread-safe SQLite connection in WAL mode."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for high concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db():
    """Initialize SQLite database tables and apply migrations for existing databases."""
    os.makedirs(DB_DIR, exist_ok=True)
    with get_db_conn() as conn:
        # Create jobs table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS extraction_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                max_results INTEGER NOT NULL,
                status TEXT NOT NULL, -- 'pending', 'running', 'completed', 'stopped', 'failed'
                phase TEXT DEFAULT 'google_maps', -- 'google_maps', 'linkedin'
                total_results INTEGER DEFAULT 0,
                current_business TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create business results table with LinkedIn enrichment fields
        conn.execute("""
            CREATE TABLE IF NOT EXISTS business_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                category TEXT,
                rating REAL,
                reviews INTEGER,
                phone TEXT,
                website TEXT,
                address TEXT,
                maps_url TEXT,
                latitude REAL,
                longitude REAL,
                opening_hours TEXT,
                linkedin_url TEXT,
                linkedin_status TEXT DEFAULT 'pending', -- 'pending', 'completed', 'failed', 'skipped'
                linkedin_error TEXT,
                linkedin_processed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(job_id) REFERENCES extraction_jobs(id)
            )
        """)

        # Create persistent cache for website -> LinkedIn URL lookup
        conn.execute("""
            CREATE TABLE IF NOT EXISTS linkedin_cache (
                url TEXT PRIMARY KEY,
                linkedin_url TEXT,
                status TEXT,
                error TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Auto-migration for existing databases created before the phase/linkedin schema update
        try:
            conn.execute("ALTER TABLE extraction_jobs ADD COLUMN phase TEXT DEFAULT 'google_maps'")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            conn.execute("ALTER TABLE business_results ADD COLUMN linkedin_url TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE business_results ADD COLUMN linkedin_status TEXT DEFAULT 'pending'")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE business_results ADD COLUMN linkedin_error TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE business_results ADD COLUMN linkedin_processed_at TIMESTAMP")
        except sqlite3.OperationalError:
            pass


def create_job(query: str, max_results: int) -> int:
    """Create a new extraction job and return its ID."""
    with get_db_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO extraction_jobs (query, max_results, status, phase) VALUES (?, ?, 'pending', 'google_maps')",
            (query, max_results)
        )
        return cursor.lastrowid

def update_job_status(job_id: int, status: str, total_results: Optional[int] = None, phase: Optional[str] = None) -> None:
    """Update status, updated_at time, total processed results, and optionally phase of a job."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db_conn() as conn:
        query_parts = ["status = ?", "updated_at = ?"]
        params = [status, now]

        if total_results is not None:
            query_parts.append("total_results = ?")
            params.append(total_results)
        if phase is not None:
            query_parts.append("phase = ?")
            params.append(phase)

        params.append(job_id)
        sql = f"UPDATE extraction_jobs SET {', '.join(query_parts)} WHERE id = ?"
        conn.execute(sql, tuple(params))

def update_job_current_business(job_id: int, business_name: str) -> None:
    """Update the name of the current business being processed."""
    with get_db_conn() as conn:
        conn.execute(
            "UPDATE extraction_jobs SET current_business = ? WHERE id = ?",
            (business_name, job_id)
        )

def get_job_status(job_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve current details and status of a specific job."""
    with get_db_conn() as conn:
        row = conn.execute("SELECT * FROM extraction_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

def insert_business(job_id: int, business: Dict[str, Any]) -> int:
    """Insert a single business result record incrementally."""
    with get_db_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO business_results (
                job_id, name, category, rating, reviews, phone, website, address, maps_url, latitude, longitude, opening_hours
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                business.get("name"),
                business.get("category"),
                business.get("rating"),
                business.get("reviews"),
                business.get("phone"),
                business.get("website"),
                business.get("address"),
                business.get("maps_url"),
                business.get("latitude"),
                business.get("longitude"),
                business.get("opening_hours")
            )
        )
        # Update the job's total_results count
        count_row = conn.execute("SELECT COUNT(*) as count FROM business_results WHERE job_id = ?", (job_id,)).fetchone()
        count = count_row["count"] if count_row else 0
        conn.execute("UPDATE extraction_jobs SET total_results = ? WHERE id = ?", (count, job_id))
        return cursor.lastrowid

def get_cached_linkedin(url: str) -> Optional[Dict[str, Any]]:
    """Query persistent cache for a given normalized website URL."""
    if not url:
        return None
    with get_db_conn() as conn:
        row = conn.execute("SELECT * FROM linkedin_cache WHERE url = ?", (url,)).fetchone()
        return dict(row) if row else None

def set_cached_linkedin(url: str, linkedin_url: Optional[str], status: str, error: Optional[str] = None) -> None:
    """Save/update persistent LinkedIn extraction result into cache."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO linkedin_cache (url, linkedin_url, status, error, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (url, linkedin_url, status, error, now)
        )

def update_business_linkedin(record_id: int, linkedin_url: Optional[str], status: str, error: Optional[str] = None) -> None:
    """Incrementally update business record with discovered LinkedIn info to prevent data loss."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db_conn() as conn:
        conn.execute(
            """
            UPDATE business_results
            SET linkedin_url = ?, linkedin_status = ?, linkedin_error = ?, linkedin_processed_at = ?
            WHERE id = ?
            """,
            (linkedin_url, status, error, now, record_id)
        )

def get_job_results(job_id: int) -> List[Dict[str, Any]]:
    """Get all business results for a specific job."""
    with get_db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM business_results WHERE job_id = ? ORDER BY id ASC",
            (job_id,)
        ).fetchall()
        return [dict(row) for row in rows]

def get_job_history() -> List[Dict[str, Any]]:
    """Retrieve all past extraction jobs ordered by start date desc."""
    with get_db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM extraction_jobs ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

def clear_job_history() -> None:
    """Clear all jobs and business results from database."""
    with get_db_conn() as conn:
        conn.execute("DELETE FROM business_results")
        conn.execute("DELETE FROM extraction_jobs")
        conn.execute("DELETE FROM linkedin_cache")

