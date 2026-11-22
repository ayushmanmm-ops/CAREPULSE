
import sqlite3
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse


# ============================================================
# CAREPULSE INTELLIGENCE ENGINE
# ============================================================

DB_PATH = Path(__file__).resolve().parent / "carepulse.db"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn, table_name):
    result = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    ).fetchone()
    return result is not None


def get_columns(conn, table_name):
    if not table_exists(conn, table_name):
        return set()

    return {
        row["name"]
        for row in conn.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
    }


# ============================================================
# DATABASE FOUNDATION
# ============================================================

def initialise_engine_tables():

    with get_connection() as conn:

        conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            organisation TEXT,
            source_url TEXT,
            source_type TEXT,
            publication_date TEXT,
            accessed_date TEXT
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS medication_reference (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generic_name TEXT NOT NULL,
            brand_names TEXT,
            drug_class TEXT,
            approved_uses TEXT,
            dosage_forms TEXT,
            storage_guidance TEXT,
            source_id INTEGER,
            last_reviewed TEXT,
            verification_status TEXT DEFAULT 'unverified'
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS medication_warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medication_id INTEGER NOT NULL,
            warning_type TEXT NOT NULL,
            description TEXT NOT NULL,
            source_id INTEGER,
            last_reviewed TEXT,
            verification_status TEXT DEFAULT 'unverified'
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS medication_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medication_a TEXT NOT NULL,
            medication_b TEXT NOT NULL,
            severity TEXT,
            description TEXT,
            source_id INTEGER,
            last_reviewed TEXT,
            verification_status TEXT DEFAULT 'unverified'
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS medication_reference_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medication_id INTEGER NOT NULL,
            reviewer TEXT NOT NULL,
            review_decision TEXT NOT NULL,
            review_notes TEXT,
            source_id INTEGER,
            reviewed_at TEXT NOT NULL
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS medication_warning_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            warning_id INTEGER NOT NULL,
            reviewer TEXT NOT NULL,
            review_decision TEXT NOT NULL,
            review_notes TEXT,
            reviewed_at TEXT NOT NULL
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS medication_interaction_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interaction_id INTEGER NOT NULL,
            reviewer TEXT NOT NULL,
            review_decision TEXT NOT NULL,
            review_notes TEXT,
            reviewed_at TEXT NOT NULL
        )
        """)

        # Safe database migrations

        warning_columns = get_columns(conn, "medication_warnings")

        if "verification_status" not in warning_columns:
            conn.execute("""
                ALTER TABLE medication_warnings
                ADD COLUMN verification_status TEXT DEFAULT 'unverified'
            """)

        medication_columns = get_columns(conn, "medication_reference")

        if "verification_status" not in medication_columns:
            conn.execute("""
                ALTER TABLE medication_reference
                ADD COLUMN verification_status TEXT DEFAULT 'unverified'
            """)

        interaction_columns = get_columns(
            conn, "medication_interactions"
        )

        if "verification_status" not in interaction_columns:
            conn.execute("""
                ALTER TABLE medication_interactions
                ADD COLUMN verification_status TEXT DEFAULT 'unverified'
            """)

        conn.commit()


# ============================================================
# INPUT VALIDATION
# ============================================================

def valid_positive_id(value):
    return type(value) is int and value > 0


def validate_limit(limit):
    if type(limit) is not int or limit < 1:
        return 5
    return min(limit, 50)


# ============================================================
# KNOWLEDGE SOURCE MANAGEMENT
# ============================================================

def add_knowledge_source(
    source_name,
    organisation,
    source_url,
    source_type
):

    source_name = (source_name or "").strip()
    organisation = (organisation or "").strip()
    source_url = (source_url or "").strip()
    source_type = (source_type or "").strip()

    if not source_name:
        raise ValueError("Source name is required.")

    if not source_url:
        raise ValueError("Source URL is required.")

    parsed = urlparse(source_url)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("A valid HTTP or HTTPS source URL is required.")

    with get_connection() as conn:

        existing = conn.execute("""
            SELECT id
            FROM knowledge_sources
            WHERE source_url = ?
        """, (source_url,)).fetchone()

        if existing:
            return existing["id"]

        cursor = conn.execute("""
            INSERT INTO knowledge_sources (
                source_name,
                organisation,
                source_url,
                source_type,
                accessed_date
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            source_name,
            organisation,
            source_url,
            source_type,
            datetime.now().date().isoformat()
        ))

        return cursor.lastrowid


def validate_knowledge_source(source_id):

    if not valid_positive_id(source_id):
        return {
            "valid": False,
            "reason": "Invalid source ID."
        }

    with get_connection() as conn:

        source = conn.execute("""
            SELECT *
            FROM knowledge_sources
            WHERE id = ?
        """, (source_id,)).fetchone()

        if not source:
            return {
                "valid": False,
                "reason": "Source not found."
            }

        source = dict(source)

        required = (
            "source_name",
            "organisation",
            "source_url",
            "source_type"
        )

        missing = [
            field for field in required
            if not source.get(field)
            or not str(source[field]).strip()
        ]

        if missing:
            return {
                "valid": False,
                "reason": "Missing source information: "
                          + ", ".join(missing),
                "source": source
            }

        parsed = urlparse(source["source_url"])

        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return {
                "valid": False,
                "reason": "Source URL is invalid.",
                "source": source
            }

        return {
            "valid": True,
            "reason": "Required source metadata is present.",
            "source": source
        }


# ============================================================
# MEDICATION REFERENCE DATABASE
# ============================================================

def add_medication_reference(
    generic_name,
    brand_names=None,
    drug_class=None,
    approved_uses=None,
    dosage_forms=None,
    storage_guidance=None,
    source_id=None
):

    generic_name = (generic_name or "").strip()

    if not generic_name:
        raise ValueError("Generic medication name is required.")

    if source_id is not None and not valid_positive_id(source_id):
        raise ValueError("Invalid source ID.")

    with get_connection() as conn:

        if source_id is not None:

            source = conn.execute("""
                SELECT id
                FROM knowledge_sources
                WHERE id = ?
            """, (source_id,)).fetchone()

            if not source:
                raise ValueError("Knowledge source does not exist.")

        cursor = conn.execute("""
            INSERT INTO medication_reference (
                generic_name,
                brand_names,
                drug_class,
                approved_uses,
                dosage_forms,
                storage_guidance,
                source_id,
                last_reviewed,
                verification_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'unverified')
        """, (
            generic_name,
            brand_names,
            drug_class,
            approved_uses,
            dosage_forms,
            storage_guidance,
            source_id
        ))

        return cursor.lastrowid


def search_medication_reference(query, limit=5):

    query = (query or "").strip()
    limit = validate_limit(limit)

    if len(query) < 2:
        return []

    search_term = f"%{query}%"

    with get_connection() as conn:

        if not table_exists(conn, "medication_reference"):
            return []

        results = conn.execute("""
            SELECT
                m.id,
                m.generic_name,
                m.brand_names,
                m.drug_class,
                m.approved_uses,
                m.dosage_forms,
                m.storage_guidance,
                m.last_reviewed,
                m.verification_status,
                s.source_name,
                s.organisation,
                s.source_url
            FROM medication_reference AS m
            LEFT JOIN knowledge_sources AS s
                ON m.source_id = s.id
            WHERE
                m.generic_name LIKE ?
                OR m.brand_names LIKE ?
                OR m.drug_class LIKE ?
            ORDER BY m.generic_name
            LIMIT ?
        """, (
            search_term,
            search_term,
            search_term,
            limit
        )).fetchall()

        return [dict(row) for row in results]


def search_verified_medications(query, limit=5):

    query = (query or "").strip()
    limit = validate_limit(limit)

    if len(query) < 2:
        return []

    search_term = f"%{query}%"

    with get_connection() as conn:

        if not table_exists(conn, "medication_reference"):
            return []

        results = conn.execute("""
            SELECT
                m.id,
                m.generic_name,
                m.brand_names,
                m.drug_class,
                m.approved_uses,
                m.dosage_forms,
                m.storage_guidance,
                m.last_reviewed,
                m.verification_status,
                s.source_name,
                s.organisation,
                s.source_url
            FROM medication_reference AS m
            LEFT JOIN knowledge_sources AS s
                ON m.source_id = s.id
            WHERE
                m.verification_status = 'verified'
                AND (
                    m.generic_name LIKE ?
                    OR m.brand_names LIKE ?
                    OR m.drug_class LIKE ?
                )
            ORDER BY m.generic_name
            LIMIT ?
        """, (
            search_term,
            search_term,
            search_term,
            limit
        )).fetchall()

        return [dict(row) for row in results]


def review_medication_reference(
    medication_id,
    reviewer,
    decision,
    review_notes="",
    source_id=None
):

    reviewer = (reviewer or "").strip()
    decision = (decision or "").strip().lower()
    review_notes = (review_notes or "").strip()

    if not valid_positive_id(medication_id):
        raise ValueError("A valid medication ID is required.")

    if not reviewer:
        raise ValueError("Reviewer name is required.")

    if decision not in ("approved", "rejected"):
        raise ValueError("Decision must be approved or rejected.")

    with get_connection() as conn:

        medication = conn.execute("""
            SELECT id, source_id
            FROM medication_reference
            WHERE id = ?
        """, (medication_id,)).fetchone()

        if not medication:
            raise ValueError("Medication record not found.")

        final_source_id = (
            source_id if source_id is not None
            else medication["source_id"]
        )

        if decision == "approved":

            if not valid_positive_id(final_source_id):
                raise ValueError(
                    "An approved entry must have a supporting source."
                )

            source_check = validate_knowledge_source(final_source_id)

            if not source_check["valid"]:
                raise ValueError(source_check["reason"])

        elif final_source_id is not None:

            source = conn.execute("""
                SELECT id
                FROM knowledge_sources
                WHERE id = ?
            """, (final_source_id,)).fetchone()

            if not source:
                raise ValueError("Knowledge source not found.")

        status = (
            "verified" if decision == "approved"
            else "rejected"
        )

        conn.execute("""
            UPDATE medication_reference
            SET
                verification_status = ?,
                last_reviewed = ?,
                source_id = ?
            WHERE id = ?
        """, (
            status,
            datetime.now().date().isoformat(),
            final_source_id,
            medication_id
        ))

        conn.execute("""
            INSERT INTO medication_reference_reviews (
                medication_id,
                reviewer,
                review_decision,
                review_notes,
                source_id,
                reviewed_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            medication_id,
            reviewer,
            decision,
            review_notes,
            final_source_id,
            datetime.now().isoformat(timespec="seconds")
        ))

        return status


# ============================================================
# MEDICATION WARNINGS
# ============================================================

def add_medication_warning(
    medication_id,
    warning_type,
    description,
    source_id
):

    warning_type = (warning_type or "").strip()
    description = (description or "").strip()

    if not valid_positive_id(medication_id):
        raise ValueError("A valid medication ID is required.")

    if not warning_type or not description:
        raise ValueError("Warning type and description are required.")

    if not valid_positive_id(source_id):
        raise ValueError("A valid source ID is required.")

    with get_connection() as conn:

        medication = conn.execute("""
            SELECT id
            FROM medication_reference
            WHERE id = ?
        """, (medication_id,)).fetchone()

        source = conn.execute("""
            SELECT id
            FROM knowledge_sources
            WHERE id = ?
        """, (source_id,)).fetchone()

        if not medication:
            raise ValueError("Medication reference not found.")

        if not source:
            raise ValueError("Knowledge source not found.")

        cursor = conn.execute("""
            INSERT INTO medication_warnings (
                medication_id,
                warning_type,
                description,
                source_id,
                last_reviewed,
                verification_status
            )
            VALUES (?, ?, ?, ?, NULL, 'unverified')
        """, (
            medication_id,
            warning_type,
            description,
            source_id
        ))

        return cursor.lastrowid


def get_medication_warnings(medication_id):

    if not valid_positive_id(medication_id):
        return []

    with get_connection() as conn:

        if not table_exists(conn, "medication_warnings"):
            return []

        results = conn.execute("""
            SELECT
                w.id,
                w.medication_id,
                w.warning_type,
                w.description,
                w.last_reviewed,
                w.verification_status,
                s.source_name,
                s.organisation,
                s.source_url
            FROM medication_warnings AS w
            LEFT JOIN knowledge_sources AS s
                ON w.source_id = s.id
            WHERE w.medication_id = ?
            ORDER BY w.id DESC
        """, (medication_id,)).fetchall()

        return [dict(row) for row in results]


def get_verified_medication_warnings(medication_id):

    if not valid_positive_id(medication_id):
        return []

    with get_connection() as conn:

        if not table_exists(conn, "medication_warnings"):
            return []

        results = conn.execute("""
            SELECT
                w.id,
                w.medication_id,
                w.warning_type,
                w.description,
                w.last_reviewed,
                w.verification_status,
                s.source_name,
                s.organisation,
                s.source_url
            FROM medication_warnings AS w
            LEFT JOIN knowledge_sources AS s
                ON w.source_id = s.id
            WHERE
                w.medication_id = ?
                AND w.verification_status = 'verified'
            ORDER BY w.last_reviewed DESC
        """, (medication_id,)).fetchall()

        return [dict(row) for row in results]

        
def review_medication_warning(
    warning_id,
    reviewer,
    decision,
    review_notes=""
):
    reviewer = (reviewer or "").strip()
    decision = (decision or "").strip().lower()
    review_notes = (review_notes or "").strip()

    if not valid_positive_id(warning_id):
        raise ValueError("A valid warning ID is required.")

    if not reviewer:
        raise ValueError("Reviewer name is required.")

    if decision not in ("approved", "rejected"):
        raise ValueError("Decision must be approved or rejected.")

    with get_connection() as conn:

        warning = conn.execute("""
            SELECT id, source_id
            FROM medication_warnings
            WHERE id = ?
        """, (warning_id,)).fetchone()

        if not warning:
            raise ValueError("Medication warning not found.")

        if decision == "approved":

            if not valid_positive_id(warning["source_id"]):
                raise ValueError("A source is required before approval.")

            source_check = validate_knowledge_source(
                warning["source_id"]
            )

            if not source_check["valid"]:
                raise ValueError(source_check["reason"])

        status = (
            "verified"
            if decision == "approved"
            else "rejected"
        )

        reviewed_at = datetime.now().isoformat(
            timespec="seconds"
        )

        conn.execute("""
            UPDATE medication_warnings
            SET
                verification_status = ?,
                last_reviewed = ?
            WHERE id = ?
        """, (
            status,
            reviewed_at,
            warning_id
        ))

        conn.execute("""
            INSERT INTO medication_warning_reviews (
                warning_id,
                reviewer,
                review_decision,
                review_notes,
                reviewed_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            warning_id,
            reviewer,
            decision,
            review_notes,
            reviewed_at
        ))

        return status 