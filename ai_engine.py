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
            if "reminder" in med_columns
            else "NULL"
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

        source_column = (
            "event_source"
            if "event_source" in event_columns
            else "'unknown'"
        )

        events = conn.execute(f"""
            SELECT
                medication_name,
                event_type,
                event_time,
                {source_column}
            FROM events
            ORDER BY event_time DESC
        """).fetchall()

    return medications, events



# ==========================================
# EVENT ANALYTICS
# ==========================================


def analyse_events(days=30):

    if not isinstance(days, int) or days < 1:
        raise ValueError("days must be a positive integer.")

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

    source_counts = Counter(
        event[3] if len(event) > 3 and event[3] else "unknown"
        for event in recent
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

        "source_counts": dict(source_counts),

        "medications": medications,
        "events": recent
    }



def medication_patterns(days=30):

    data = analyse_events(days)

    results = {}

    for med in data["medications"]:

        med_id, name, dosage, compartment, reminders = med

        if not name:
            continue

        med_events = [
            event for event in data["events"]
            if event[0]
            and event[0].strip().casefold() == name.strip().casefold()
        ]

        counts = Counter(
            event[1] for event in med_events
        )

        source_counts = Counter(
            event[3] if len(event) > 3 and event[3] else "unknown"
            for event in med_events
        )

        openings = counts["compartment_opened"]
        reported_taken = counts["patient_reported_taken"]
        reported_missed = counts["patient_reported_missed"]

        total_patient_reports = reported_taken + reported_missed

        if total_patient_reports:
            reported_taken_percentage = round(
                reported_taken / total_patient_reports * 100,
                1
            )
        else:
            reported_taken_percentage = None

        results[name] = {
            "medication_id": med_id,
            "openings": openings,
            "reported_taken": reported_taken,
            "reported_missed": reported_missed,

            "reminders_sent": counts["reminder_sent"],
            "reminders_dismissed": counts["reminder_dismissed"],

            "total_patient_reports": total_patient_reports,
            "reported_taken_percentage": reported_taken_percentage,

            "event_sources": dict(source_counts),

            "interpretation": (
                "Based on patient-reported events only. "
                "Compartment openings are recorded separately "
                "and do not confirm medication ingestion."
            )
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

    text = (question or "").lower().strip()

    if not text:
        return "unknown"

    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Greeting
    if re.search(
        r"\b(hello|hi|hey|good morning|good afternoon)\b",
        text
    ):
        return "greeting"

    # CAREPULSE features
    if any(phrase in text for phrase in [
        "what can carepulse do",
        "what does carepulse do",
        "what is carepulse",
        "how does carepulse work",
        "carepulse features",
        "what can you do"
    ]):
        return "about"

    # Medication interactions
    if any(word in text for word in [
        "interaction", "interactions",
        "interact", "interacting",
        "drug combination",
        "medicine combination"
    ]):
        return "interactions"

    # Medication warnings
    if any(word in text for word in [
        "warning", "warnings",
        "side effect", "side effects",
        "precaution", "precautions",
        "contraindication", "contraindications"
    ]):
        return "warnings"

    # Reminders
    if any(word in text for word in [
        "reminder", "reminders", "schedule",
        "scheduled", "next dose", "upcoming dose",
        "medication time", "medicine time"
    ]):
        return "reminders"

    # Compartment openings
    if any(word in text for word in [
        "compartment opening",
        "compartment opened",
        "opened compartment"
    ]):
        return "openings"

    # Patient-reported taken
    if any(word in text for word in [
        "reported taken", "patient reported",
        "recorded taken", "medication taken"
    ]):
        return "taken"

    # Patient-reported missed
    if any(word in text for word in [
        "reported missed", "missed events",
        "missed medication"
    ]):
        return "missed"

    # Event history
    if any(word in text for word in [
        "history", "event history",
        "my events", "activity", "past events"
    ]):
        return "events"

    # Adherence and patterns
    if any(word in text for word in [
        "adherence", "adherent", "patterns",
        "pattern", "trend", "trends",
        "analyse my data", "analyze my data",
        "monthly report", "weekly report",
        "last 30 days", "consistency"
    ]):
        return "patterns"

    # Saved medications
    if any(word in text for word in [
        "medication", "medications",
        "medicine", "medicines", "drug"
    ]):
        return "medications"

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

    source_counts = data.get("source_counts", {})

    source_lines = []

    for source, count in sorted(source_counts.items()):
        source_lines.append(
            f"- {source}: **{count}**"
        )

    if not source_lines:
        source_lines.append("- No event-source data available.")

    return f"""
### Your last 30 days

- Total recorded events: **{data['total_events']}**
- Compartment openings: **{data['openings']}**
- Patient-reported taken: **{data['patient_reported_taken']}**
- Patient-reported missed: **{data['patient_reported_missed']}**
- Reminders sent: **{data['reminders_sent']}**
- Reminders dismissed: **{data['reminders_dismissed']}**

### Event sources

{chr(10).join(source_lines)}

These are different event categories. They are not interchangeable.

A compartment opening does not confirm that medication was swallowed.
"""




def pattern_response():

    patterns = medication_patterns(30)

    if not patterns:
        return "No medication records are available for analysis."

    output = ["### Medication event analysis – last 30 days"]

    for name, stats in patterns.items():

        output.append(f"\n**{name}**\n")

        output.append(
            f"- Compartment openings: {stats['openings']}"
        )

        output.append(
            f"- Patient-reported taken: {stats['reported_taken']}"
        )

        output.append(
            f"- Patient-reported missed: {stats['reported_missed']}"
        )

        output.append(
            f"- Reminders sent: {stats['reminders_sent']}"
        )

        output.append(
            f"- Reminders dismissed: {stats['reminders_dismissed']}"
        )

        percentage = stats.get("reported_taken_percentage")

        if percentage is not None:
            output.append(
                f"- Taken reports among patient reports: {percentage}%"
            )
        else:
            output.append(
                "- Taken-report percentage: Insufficient patient reports"
            )

        sources = stats.get("event_sources", {})

        if sources:
            output.append("- Event sources:")

            for source, count in sorted(sources.items()):
                output.append(f"  - {source}: {count}")

        if (
            stats["openings"] > 0
            and stats["reported_taken"] == 0
        ):
            output.append(
                "- Observation: Compartment openings were recorded, "
                "but no patient-reported taken events were recorded."
            )

    output.append(
        "\nThese observations describe database records. "
        "Compartment openings do not prove medication ingestion. "
        "Patient-reported events are not independently verified."
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
