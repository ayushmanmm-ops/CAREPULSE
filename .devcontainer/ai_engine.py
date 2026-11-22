
import sqlite3
import re
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter


# ==========================================
# CAREPULSE INTELLIGENCE ENGINE
# ==========================================

DB_PATH = Path(__file__).resolve().parent / "carepulse.db"


# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_connection():
    return sqlite3.connect(DB_PATH)

def search_medication_reference(query, limit=5):

    query = (query or "").strip()

    if len(query) < 2:
        return []

    search_term = f"%{query}%"

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

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

    if len(query) < 2:
        return []

    search_term = f"%{query}%"

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

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

def get_medication_warnings(medication_id):

    if not isinstance(medication_id, int) or medication_id <= 0:
        return []

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

        results = conn.execute("""
        SELECT
            w.id,
            w.medication_id,
            w.warning_type,
            w.description,
            w.last_reviewed,
            s.source_name,
            s.organisation,
            s.source_url
        FROM medication_warnings AS w
        LEFT JOIN knowledge_sources AS s
            ON w.source_id = s.id
        WHERE w.medication_id = ?
        ORDER BY w.last_reviewed DESC
        """, (medication_id,)).fetchall()

        return [dict(row) for row in results]

def get_verified_medication_warnings(medication_id):

    if not isinstance(medication_id, int) or medication_id <= 0:
        return []

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

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

def get_verified_medication_interactions(medication_a, medication_b):

    medication_a = (medication_a or "").strip()
    medication_b = (medication_b or "").strip()

    if not medication_a or not medication_b:
        return []

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

        results = conn.execute("""
        SELECT
            i.id,
            i.medication_a,
            i.medication_b,
            i.severity,
            i.description,
            i.last_reviewed,
            i.verification_status,
            s.source_name,
            s.organisation,
            s.source_url
        FROM medication_interactions AS i
        LEFT JOIN knowledge_sources AS s
            ON i.source_id = s.id
        WHERE
            i.verification_status = 'verified'
            AND (
                (
                    LOWER(i.medication_a) = LOWER(?)
                    AND LOWER(i.medication_b) = LOWER(?)
                )
                OR
                (
                    LOWER(i.medication_a) = LOWER(?)
                    AND LOWER(i.medication_b) = LOWER(?)
                )
            )
        ORDER BY i.last_reviewed DESC
        """, (
            medication_a,
            medication_b,
            medication_b,
            medication_a
        )).fetchall()

        return [dict(row) for row in results]

def add_medication_warning(
    medication_id,
    warning_type,
    description,
    source_id
):

    warning_type = (warning_type or "").strip()
    description = (description or "").strip()

    if not isinstance(medication_id, int) or medication_id <= 0:
        raise ValueError("A valid medication ID is required.")

    if not warning_type or not description:
        raise ValueError("Warning type and description are required.")

    if not isinstance(source_id, int) or source_id <= 0:
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
        INSERT INTO medication_warnings
        (
            medication_id,
            warning_type,
            description,
            source_id,
            last_reviewed
        )
        VALUES (?, ?, ?, ?, ?)
        """, (
            medication_id,
            warning_type,
            description,
            source_id,
            datetime.now().date().isoformat()
        ))

        conn.commit()

        return cursor.lastrowid

def add_medication_interaction(
    medication_a,
    medication_b,
    severity,
    description,
    source_id
):

    medication_a = (medication_a or "").strip()
    medication_b = (medication_b or "").strip()
    severity = (severity or "").strip()
    description = (description or "").strip()

    if not medication_a or not medication_b:
        raise ValueError("Both medication names are required.")

    if medication_a.lower() == medication_b.lower():
        raise ValueError("The two medications must be different.")

    if not severity or not description:
        raise ValueError("Severity and description are required.")

    if not isinstance(source_id, int) or source_id <= 0:
        raise ValueError("A valid source ID is required.")

    with get_connection() as conn:

        source = conn.execute("""
        SELECT id
        FROM knowledge_sources
        WHERE id = ?
        """, (source_id,)).fetchone()

        if not source:
            raise ValueError("Knowledge source not found.")

        cursor = conn.execute("""
        INSERT INTO medication_interactions (
            medication_a,
            medication_b,
            severity,
            description,
            source_id,
            last_reviewed,
            verification_status
        )
        VALUES (?, ?, ?, ?, ?, NULL, 'unverified')
        """, (
            medication_a,
            medication_b,
            severity,
            description,
            source_id
        ))

        conn.commit()

        return cursor.lastrowid

def review_medication_interaction(
    interaction_id,
    reviewer,
    decision,
    review_notes=""
):

    reviewer = (reviewer or "").strip()
    decision = (decision or "").strip().lower()
    review_notes = (review_notes or "").strip()

    if not isinstance(interaction_id, int) or interaction_id <= 0:
        raise ValueError("A valid interaction ID is required.")

    if not reviewer:
        raise ValueError("Reviewer name is required.")

    if decision not in ("approved", "rejected"):
        raise ValueError("Decision must be approved or rejected.")

    with get_connection() as conn:

        interaction = conn.execute("""
        SELECT id, source_id
        FROM medication_interactions
        WHERE id = ?
        """, (interaction_id,)).fetchone()

        if not interaction:
            raise ValueError("Interaction record not found.")

        if decision == "approved" and not interaction[1]:
            raise ValueError("A source is required before approval.")

        status = "verified" if decision == "approved" else "rejected"

        conn.execute("""
        UPDATE medication_interactions
        SET
            verification_status = ?,
            last_reviewed = ?
        WHERE id = ?
        """, (
            status,
            datetime.now().date().isoformat(),
            interaction_id
        ))

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

        conn.execute("""
        INSERT INTO medication_interaction_reviews (
            interaction_id,
            reviewer,
            review_decision,
            review_notes,
            reviewed_at
        )
        VALUES (?, ?, ?, ?, ?)
        """, (
            interaction_id,
            reviewer,
            decision,
            review_notes,
            datetime.now().isoformat(timespec="seconds")
        ))

        conn.commit()

        return True


def review_medication_warning(
    warning_id,
    reviewer,
    decision,
    review_notes=""
):

    reviewer = (reviewer or "").strip()
    decision = (decision or "").strip().lower()
    review_notes = (review_notes or "").strip()

    if not isinstance(warning_id, int) or warning_id <= 0:
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

        if decision == "approved" and not warning[1]:
            raise ValueError("A source is required before approval.")

        if decision == "approved":
            status = "verified"
        else:
            status = "rejected"

        conn.execute("""
        UPDATE medication_warnings
        SET
            last_reviewed = ?,
            verification_status = ?
        WHERE id = ?
        """, (
            datetime.now().date().isoformat(),
            status,
            warning_id
        ))

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
            datetime.now().isoformat(timespec="seconds")
        ))

        conn.commit()

        return True


def add_knowledge_source(
    source_name,
    organisation,
    source_url,
    source_type
):

    if not source_name or not source_name.strip():
        raise ValueError("Source name is required")

    with get_connection() as conn:

        existing = conn.execute("""
        SELECT id FROM knowledge_sources
        WHERE source_url = ?
        """, (source_url,)).fetchone()

        if existing:
            return existing[0]

        cursor = conn.execute("""
        INSERT INTO knowledge_sources
        (
            source_name,
            organisation,
            source_url,
            source_type,
            accessed_date
        )
        VALUES (?, ?, ?, ?, ?)
        """, (
            source_name.strip(),
            organisation,
            source_url,
            source_type,
            datetime.now().date().isoformat()
        ))

        return cursor.lastrowid


def add_medication_reference(
    generic_name,
    brand_names=None,
    drug_class=None,
    approved_uses=None,
    dosage_forms=None,
    storage_guidance=None,
    source_id=None
):

    if not generic_name or not generic_name.strip():
        raise ValueError("Generic medication name is required")

    with get_connection() as conn:

        if source_id is not None:
            source = conn.execute("""
                SELECT id FROM knowledge_sources
                WHERE id = ?
            """, (source_id,)).fetchone()

            if not source:
                raise ValueError("Knowledge source does not exist")

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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            generic_name.strip(),
            brand_names,
            drug_class,
            approved_uses,
            dosage_forms,
            storage_guidance,
            source_id,
            None,
            "unverified"
        ))

        return cursor.lastrowid

def review_medication_reference(
    medication_id,
    reviewer,
    decision,
    review_notes="",
    source_id=None
):

    if not reviewer or not reviewer.strip():
        raise ValueError("Reviewer identity is required")

    if decision not in ("approved", "rejected"):
        raise ValueError("Invalid review decision")

    with get_connection() as conn:

        medication = conn.execute("""
            SELECT id, source_id
            FROM medication_reference
            WHERE id = ?
        """, (medication_id,)).fetchone()

        if not medication:
            raise ValueError("Medication record not found")

        final_source_id = source_id or medication[1]

        if decision == "approved" and not final_source_id:
            raise ValueError(
                "An approved entry must have a supporting source"
            )

        if final_source_id is not None:
            source = conn.execute("""
                SELECT id FROM knowledge_sources
                WHERE id = ?
            """, (final_source_id,)).fetchone()

            if not source:
                raise ValueError("Knowledge source not found")

        status = (
            "verified" if decision == "approved"
            else "rejected"
        )

        conn.execute("""
            UPDATE medication_reference
            SET verification_status = ?,
                last_reviewed = ?
            WHERE id = ?
        """, (
            status,
            datetime.now().date().isoformat(),
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
            reviewer.strip(),
            decision,
            review_notes,
            final_source_id,
            datetime.now().isoformat(timespec="seconds")
        ))

    return status

def get_database_data():

    if not DB_PATH.exists():
        return [], []

    with get_connection() as conn:

        med_columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(medications)"
            )
        }

        event_columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(events)"
            )
        }

        if not {"id", "name"}.issubset(med_columns):
            return [], []

        reminder_column = (
            "reminder_times"
            if "reminder_times" in med_columns
            else "reminder"
        )

        dosage_column = (
            "dosage" if "dosage" in med_columns else "NULL"
        )

        compartment_column = (
            "compartment"
            if "compartment" in med_columns
            else "NULL"
        )

        medications = conn.execute(f"""
            SELECT
                id,
                name,
                {dosage_column},
                {compartment_column},
                {reminder_column}
            FROM medications
            ORDER BY name
        """).fetchall()

        required_events = {
            "medication_name",
            "event_type",
            "event_time"
        }

        if not required_events.issubset(event_columns):
            return medications, []

        events = conn.execute("""
            SELECT
                medication_name,
                event_type,
                event_time
            FROM events
            ORDER BY event_time DESC
        """).fetchall()

    return medications, events


# ==========================================
# EVENT ANALYTICS
# ==========================================

def analyse_events(days=30):

    medications, events = get_database_data()

    cutoff = datetime.now() - timedelta(days=days)

    recent = []

    for event in events:

        try:
            event_time = datetime.fromisoformat(event[2])

            if event_time >= cutoff:
                recent.append(event)

        except (ValueError, TypeError):
            continue

    counts = Counter(
        event[1] for event in recent
    )

    return {
        "period_days": days,
        "total_events": len(recent),
        "openings": counts["compartment_opened"],
        "patient_reported_taken":
            counts["patient_reported_taken"],
        "patient_reported_missed":
            counts["patient_reported_missed"],
        "reminders_sent":
            counts["reminder_sent"],
        "reminders_dismissed":
            counts["reminder_dismissed"],
        "medications": medications,
        "events": recent
    }


def medication_patterns(days=30):

    data = analyse_events(days)

    results = {}

    for med in data["medications"]:

        med_id, name, dosage, compartment, reminders = med

        med_events = [
            event for event in data["events"]
            if event[0].lower() == name.lower()
        ]

        counts = Counter(
            event[1] for event in med_events
        )

        results[name] = {
            "openings": counts["compartment_opened"],
            "reported_taken":
                counts["patient_reported_taken"],
            "reported_missed":
                counts["patient_reported_missed"],
            "reminders_sent":
                counts["reminder_sent"],
            "reminders_dismissed":
                counts["reminder_dismissed"]
        }

    return results


# ==========================================
# NEXT REMINDER ANALYSIS
# ==========================================

def get_next_reminders():

    medications, _ = get_database_data()

    now = datetime.now()
    upcoming = []

    for med in medications:

        med_id, name, dosage, compartment, times = med

        if not times:
            continue

        for time_string in str(times).split(","):

            try:

                reminder_time = datetime.strptime(
                    time_string.strip(),
                    "%H:%M"
                ).time()

                reminder = datetime.combine(
                    now.date(),
                    reminder_time
                )

                if reminder <= now:
                    reminder += timedelta(days=1)

                upcoming.append({
                    "name": name,
                    "time": reminder,
                    "compartment": compartment
                })

            except ValueError:
                continue

    return sorted(
        upcoming,
        key=lambda item: item["time"]
    )


# ==========================================
# SAFETY CLASSIFICATION
# ==========================================

MEDICAL_ADVICE_PATTERNS = [
    r"\bhow much should i take\b",
    r"\bwhat dose should i take\b",
    r"\bcan i increase my dose\b",
    r"\bcan i stop taking\b",
    r"\bshould i stop taking\b",
    r"\bwhat if i missed my dose\b",
    r"\bcan i mix\b",
    r"\bdrug interaction\b",
    r"\bside effects\b",
    r"\bdiagnose\b",
    r"\bwhat disease\b",
    r"\bchest pain\b",
    r"\bbreathing difficulty\b",
    r"\boverdose\b"
]


def check_safety(question):

    question = question.lower()

    for pattern in MEDICAL_ADVICE_PATTERNS:

        if re.search(pattern, question):

            return {
                "blocked": True,
                "message": (
                    "I can help explain CAREPULSE features "
                    "and organise your recorded information, "
                    "but I cannot determine medication doses, "
                    "recommend treatment changes, diagnose "
                    "conditions or assess drug interactions. "
                    "Please contact a qualified healthcare "
                    "professional for personalised guidance. "
                    "For a medical emergency, seek immediate "
                    "local emergency assistance."
                )
            }

    return {
        "blocked": False,
        "message": None
    }


# ==========================================
# INTENT DETECTION
# ==========================================

INTENTS = {

    "greeting": [
        "hello", "hi", "hey", "good morning",
        "good afternoon"
    ],

    "medications": [
        "my medications", "list medications",
        "show medications", "what medicines",
        "my medicine"
    ],

    "events": [
        "event history", "my events",
        "show events", "event summary",
        "activity summary", "my activity"
    ],

    "patterns": [
        "patterns", "analyse my data",
        "analyze my data", "trend analysis",
        "medication patterns", "monthly report",
        "weekly report", "last 30 days"
    ],

    "openings": [
        "compartment opening", "compartment opened",
        "opened compartment", "opening event"
    ],

    "taken": [
        "reported taken", "patient reported",
        "recorded taken", "medication taken"
    ],

    "missed": [
        "reported missed", "missed events",
        "missed medication records"
    ],

    "reminders": [
        "next reminder", "upcoming reminder",
        "reminder schedule", "reminder time"
    ],

    "about": [
        "what is carepulse", "how does carepulse work",
        "what can you do", "your features"
    ]
}


def detect_intent(question):

    text = question.lower().strip()

    for intent, phrases in INTENTS.items():

        if any(phrase in text for phrase in phrases):
            return intent

    return "unknown"


# ==========================================
# RESPONSE GENERATION
# ==========================================

def medication_response():

    medications, _ = get_database_data()

    if not medications:
        return "There are no medications saved in CAREPULSE yet."

    lines = ["Here are your saved medication records:\n"]

    for med in medications:

        med_id, name, dosage, compartment, reminders = med

        lines.append(
            f"**{name}**\n"
            f"- Dosage label: {dosage or 'Not entered'}\n"
            f"- Compartment: {compartment}\n"
            f"- Reminder times: {reminders or 'Not set'}"
        )

    return "\n\n".join(lines)


def event_response():

    data = analyse_events(30)

    return f"""
### Your last 30 days

- Total recorded events: **{data['total_events']}**
- Compartment openings: **{data['openings']}**
- Patient-reported taken: **{data['patient_reported_taken']}**
- Patient-reported missed: **{data['patient_reported_missed']}**
- Reminders sent: **{data['reminders_sent']}**
- Reminders dismissed: **{data['reminders_dismissed']}**

These are different event categories. They are not interchangeable.
"""


def pattern_response():

    patterns = medication_patterns(30)

    if not patterns:
        return "No medication records are available for analysis."

    output = ["### Medication event analysis — last 30 days"]

    for name, stats in patterns.items():

        output.append(
            f"""
**{name}**

- Compartment openings: {stats['openings']}
- Patient-reported taken: {stats['reported_taken']}
- Patient-reported missed: {stats['reported_missed']}
- Reminders sent: {stats['reminders_sent']}
- Reminders dismissed: {stats['reminders_dismissed']}
"""
        )

        if (
            stats["openings"] > 0
            and stats["reported_taken"] == 0
        ):
            output.append(
                "Observation: Openings were recorded, "
                "but no patient-reported intake events "
                "were recorded in this period."
            )

    output.append(
        "\nThese observations describe database records, "
        "not proof of medication ingestion or non-ingestion."
    )

    return "\n".join(output)


def reminder_response():

    reminders = get_next_reminders()

    if not reminders:
        return "No upcoming reminder times are configured."

    output = ["### Upcoming scheduled reminders"]

    for item in reminders[:8]:

        output.append(
            f"- **{item['name']}** — "
            f"{item['time'].strftime('%d %b, %I:%M %p')} "
            f"(Compartment {item['compartment']})"
        )

    return "\n".join(output)


# ==========================================
# MAIN INTELLIGENCE ORCHESTRATOR
# ==========================================

def answer_question(question, history=None):

    if not question or not question.strip():

        return "Please enter a question."

    safety = check_safety(question)

    if safety["blocked"]:
        return safety["message"]

    intent = detect_intent(question)

    if intent == "greeting":

        return (
            "Hello! I'm CAREPULSE Intelligence. "
            "I can help you explore medication records, "
            "event history, scheduled reminders and "
            "recorded activity patterns."
        )

    if intent == "medications":
        return medication_response()

    if intent == "events":
        return event_response()

    if intent == "patterns":
        return pattern_response()

    if intent == "reminders":
        return reminder_response()

    if intent == "openings":

        return (
            "A compartment opening is a sensor or "
            "user-recorded event showing that a compartment "
            "was opened. It does not establish that medication "
            "was removed or swallowed."
        )

    if intent == "taken":

        return (
            "A patient-reported taken event means the patient "
            "reported taking the medication. It is a separate "
            "record from a compartment opening and is not "
            "independent proof of swallowing."
        )

    if intent == "missed":

        return (
            "A patient-reported missed event records that "
            "the patient reported a missed medication event. "
            "It does not independently establish what happened "
            "to the medication."
        )

    if intent == "about":

        return """
### CAREPULSE Intelligence

I can currently:

1. Retrieve saved medication records.
2. Summarise recorded events.
3. Compare event categories.
4. Identify differences between opening and patient reports.
5. Display upcoming scheduled reminder times.
6. Analyse records over a selected time period.

I cannot diagnose, prescribe, or confirm medication ingestion.
"""

    return (
        "I couldn't confidently classify that question. "
        "I can currently answer questions about your saved "
        "medication records, event history, reminder schedule "
        "and CAREPULSE features. I cannot provide personalised "
        "medical advice."
    )
