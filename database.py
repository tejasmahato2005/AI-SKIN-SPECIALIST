import os
import sqlite3
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import httpx

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "consultations.db"

INSFORGE_URL = os.environ.get("INSFORGE_URL", "").strip().rstrip("/")
INSFORGE_ANON_KEY = os.environ.get("INSFORGE_ANON_KEY", "").strip()


def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes the local SQLite database table if it doesn't exist."""
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS consultations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_name TEXT NOT NULL,
                patient_age INTEGER,
                patient_gender TEXT,
                patient_transcript TEXT,
                doctor_guidance TEXT,
                image_path TEXT,
                audio_path TEXT,
                insforge_id TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
    # Try syncing any pending records that were created offline
    sync_pending_to_insforge()


def sync_pending_to_insforge():
    """Background-friendly sync of any local records that haven't reached InsForge yet."""
    if not INSFORGE_URL or not INSFORGE_ANON_KEY:
        return
    try:
        with get_db_connection() as conn:
            pending = conn.execute(
                "SELECT * FROM consultations WHERE insforge_id IS NULL OR insforge_id = '' LIMIT 20"
            ).fetchall()
            for r in pending:
                payload = {
                    "patient_name": r["patient_name"],
                    "patient_age": r["patient_age"],
                    "patient_gender": r["patient_gender"],
                    "patient_transcript": r["patient_transcript"],
                    "doctor_guidance": r["doctor_guidance"],
                    "image_path": r["image_path"],
                    "audio_path": r["audio_path"],
                }
                remote_id, _ = save_to_insforge(payload)
                if remote_id:
                    conn.execute(
                        "UPDATE consultations SET insforge_id = ? WHERE id = ?",
                        (str(remote_id), r["id"]),
                    )
            conn.commit()
    except Exception:
        pass


def save_to_insforge(payload):
    """Sends consultation payload to InsForge endpoint if configured."""
    if not INSFORGE_URL or not INSFORGE_ANON_KEY:
        return None, "InsForge not configured (using local DB)"

    headers = {
        "apikey": INSFORGE_ANON_KEY,
        "Authorization": f"Bearer {INSFORGE_ANON_KEY}",
        "Content-Type": "application/json",
    }

    try:
        # InsForge OSS database endpoint
        url = f"{INSFORGE_URL}/api/database/records/consultations"
        response = httpx.post(url, headers=headers, json=payload, timeout=8.0)
        if response.status_code in (200, 201):
            try:
                data = response.json()
                remote_id = data[0].get("id") if isinstance(data, list) and data else None
            except Exception:
                remote_id = None
            return remote_id or "OK", "Synced to InsForge Cloud"
        elif response.status_code == 404:
            # Fallback for standard PostgREST deployments
            alt_url = f"{INSFORGE_URL}/rest/v1/consultations"
            alt_resp = httpx.post(
                alt_url,
                headers={**headers, "Prefer": "return=representation"},
                json=payload,
                timeout=8.0,
            )
            if alt_resp.status_code in (200, 201):
                try:
                    data = alt_resp.json()
                    remote_id = data[0].get("id") if isinstance(data, list) and data else None
                except Exception:
                    remote_id = None
                return remote_id or "OK", "Synced to InsForge Cloud"
            return None, f"InsForge HTTP {response.status_code}: {response.text[:80]}"
        else:
            return None, f"InsForge HTTP {response.status_code}: {response.text[:80]}"
    except Exception as e:
        return None, f"InsForge sync error: {e}"


def save_consultation(
    patient_name,
    patient_age,
    patient_gender,
    patient_transcript,
    doctor_guidance,
    image_path=None,
    audio_path=None,
):
    """
    Saves consultation record to local SQLite and syncs to InsForge if configured.
    Returns (record_id, status_message).
    """
    init_db()
    name = (patient_name or "").strip() or "Anonymous Patient"
    age = int(patient_age) if patient_age and str(patient_age).isdigit() else None
    gender = (patient_gender or "").strip() or "Not specified"
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Sync to InsForge if configured
    insforge_payload = {
        "patient_name": name,
        "patient_age": age,
        "patient_gender": gender,
        "patient_transcript": patient_transcript,
        "doctor_guidance": doctor_guidance,
        "image_path": str(image_path) if image_path else None,
        "audio_path": str(audio_path) if audio_path else None,
    }
    insforge_id, insforge_msg = save_to_insforge(insforge_payload)

    # Save to local SQLite
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO consultations (
                patient_name, patient_age, patient_gender,
                patient_transcript, doctor_guidance,
                image_path, audio_path, insforge_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                age,
                gender,
                patient_transcript,
                doctor_guidance,
                str(image_path) if image_path else None,
                str(audio_path) if audio_path else None,
                str(insforge_id) if insforge_id else None,
                created_at,
            ),
        )
        conn.commit()
        local_id = cursor.lastrowid

    if insforge_id:
        status = f"Saved locally (ID #{local_id}) & Synced to InsForge (Remote ID #{insforge_id})"
    else:
        status = f"Saved to Database (ID #{local_id}) · {insforge_msg}"

    return local_id, status


def get_consultations(search_name=None, limit=20):
    """Fetches recent consultations from the database, optionally filtered by patient name."""
    init_db()
    with get_db_connection() as conn:
        if search_name and search_name.strip():
            query = """
                SELECT id, created_at, patient_name, patient_age, patient_gender,
                       patient_transcript, doctor_guidance
                FROM consultations
                WHERE patient_name LIKE ?
                ORDER BY id DESC
                LIMIT ?
            """
            rows = conn.execute(query, (f"%{search_name.strip()}%", limit)).fetchall()
        else:
            query = """
                SELECT id, created_at, patient_name, patient_age, patient_gender,
                       patient_transcript, doctor_guidance
                FROM consultations
                ORDER BY id DESC
                LIMIT ?
            """
            rows = conn.execute(query, (limit,)).fetchall()

        records = []
        for r in rows:
            records.append(
                [
                    r["id"],
                    r["created_at"],
                    r["patient_name"],
                    r["patient_age"] if r["patient_age"] is not None else "-",
                    r["patient_gender"],
                    (r["patient_transcript"][:70] + "...") if len(r["patient_transcript"] or "") > 70 else (r["patient_transcript"] or "-"),
                    (r["doctor_guidance"][:85] + "...") if len(r["doctor_guidance"] or "") > 85 else (r["doctor_guidance"] or "-"),
                ]
            )
        return records
