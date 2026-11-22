import streamlit as st
import sqlite3
from datetime import datetime, timedelta

import os
import sys


from ai_engine import answer_question

# ==========================================
# CAREPULSE V2
# ==========================================

st.set_page_config(
    page_title="CAREPULSE",
    page_icon="💊",
    layout="wide"
)

DB = "carepulse.db"


# ==========================================
# DATABASE
# ==========================================

def connect():
    return sqlite3.connect(DB, check_same_thread=False)


def initialise_database():

    with connect() as conn:

        conn.execute("""
        CREATE TABLE IF NOT EXISTS medications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            dosage TEXT,
            compartment INTEGER,
            reminder TEXT
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medication_id INTEGER,
            medication_name TEXT,
            event_type TEXT,
            event_time TEXT
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS patient_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            name TEXT,
            age INTEGER,
            emergency_contact TEXT
        )
        """)

        # ==========================================
        # CAREPULSE INTELLIGENCE DATABASE
        # ==========================================

        # Preserve the source of every recorded event.
        event_columns = [
            row[1] for row in
            conn.execute("PRAGMA table_info(events)")
        ]

        if "event_source" not in event_columns:
            conn.execute("""
                ALTER TABLE events
                ADD COLUMN event_source TEXT DEFAULT 'unknown'
            """)

        # Medication knowledge reference library.
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

        # Documented medication warnings.
        conn.execute("""
        CREATE TABLE IF NOT EXISTS medication_warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medication_id INTEGER,
            warning_type TEXT,
            description TEXT NOT NULL,
            source_id INTEGER,
            last_reviewed TEXT
        )
        """)

        # Reference-based medication interaction records.
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

        # Sources used by the knowledge engine.
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

        # Curated clinical guidelines.
        conn.execute("""
        CREATE TABLE IF NOT EXISTS clinical_guidelines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            organisation TEXT,
            topic TEXT,
            source_url TEXT,
            publication_date TEXT,
            last_reviewed TEXT,
            verification_status TEXT DEFAULT 'unverified'
        )
        """)

        columns = [
            row[1] for row in
            conn.execute("PRAGMA table_info(medications)")
        ]

        if "reminder_times" not in columns:
            conn.execute(
                "ALTER TABLE medications ADD COLUMN reminder_times TEXT"
            )

        # Preserve existing medication reminder times.
        conn.execute("""
        UPDATE medications
        SET reminder_times = reminder
        WHERE reminder_times IS NULL
        """)

        conn.commit()


initialise_database()


# ==========================================
# DATABASE FUNCTIONS
# ==========================================

def get_medications():

    with connect() as conn:
        return conn.execute("""
        SELECT id, name, dosage, compartment, reminder_times
        FROM medications
        ORDER BY name
        """).fetchall()


def add_medication(name, dosage, compartment, times):

    with connect() as conn:
        conn.execute("""
        INSERT INTO medications
        (name, dosage, compartment, reminder, reminder_times)
        VALUES (?, ?, ?, ?, ?)
        """, (
            name,
            dosage,
            compartment,
            times,
            times
        ))


def update_medication(med_id, name, dosage, compartment, times):

    with connect() as conn:
        conn.execute("""
        UPDATE medications
        SET name = ?,
            dosage = ?,
            compartment = ?,
            reminder = ?,
            reminder_times = ?
        WHERE id = ?
        """, (
            name,
            dosage,
            compartment,
            times,
            times,
            med_id
        ))


def delete_medication(med_id):

    with connect() as conn:
        conn.execute(
            "DELETE FROM medications WHERE id = ?",
            (med_id,)
        )


def record_event(med_id, name, event_type, source="patient_app"):

    allowed = [
        "compartment_opened",
        "patient_reported_taken",
        "patient_reported_missed",
        "reminder_sent",
        "reminder_dismissed"
    ]

    if event_type not in allowed:
        raise ValueError("Invalid event type")

    with connect() as conn:
        conn.execute("""
        INSERT INTO events
        (medication_id, medication_name, event_type,
         event_time, event_source)
        VALUES (?, ?, ?, ?, ?)
        """, (
            med_id,
            name,
            event_type,
            datetime.now().isoformat(timespec="seconds"),
            source
        ))


        return conn.execute("""
        SELECT medication_name, event_type, event_time, event_source
        FROM events
        ORDER BY id DESC
        """).fetchall()

    with connect() as conn:
        return conn.execute("""
        SELECT medication_name, event_type, event_time
        FROM events
        ORDER BY id DESC
        """).fetchall()


def get_profile():

    with connect() as conn:
        return conn.execute("""
        SELECT name, age, emergency_contact
        FROM patient_profile
        WHERE id = 1
        """).fetchone()


# ==========================================
# REMINDER FUNCTIONS
# ==========================================

def validate_times(value):

    times = [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]

    if not times:
        return False, []

    try:
        parsed = [
            datetime.strptime(item, "%H:%M").time()
            for item in times
        ]

        if len(set(times)) != len(times):
            return False, []

        return True, sorted(
            [item.strftime("%H:%M") for item in parsed]
        )

    except ValueError:
        return False, []


def next_reminder(medications):

    now = datetime.now()
    upcoming = []

    for med in medications:

        med_id, name, dosage, compartment, times = med

        if not times:
            continue

        for time_string in times.split(","):

            try:
                reminder_time = datetime.strptime(
                    time_string.strip(),
                    "%H:%M"
                ).time()

                reminder = datetime.combine(
                    now.date(),
                    reminder_time
                )

                if reminder < now:
                    reminder += timedelta(days=1)

                upcoming.append((reminder, name))

            except ValueError:
                continue

    if not upcoming:
        return None

    return min(upcoming, key=lambda x: x[0])


# ==========================================
# SIDEBAR
# ==========================================

st.sidebar.title("💊 CAREPULSE")
st.sidebar.caption("Smart Medication Management")

page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Add Medication",
        "Manage Medications",
        "Medication History",
        "Patient Profile",
        "AI Assistant"
    ]
)

medications = get_medications()


# ==========================================
# DASHBOARD
# ==========================================

if page == "Dashboard":

    st.title("💊 CAREPULSE")
    st.subheader("Your Personal Medication Companion")

    st.write("Welcome to your medication dashboard.")

    upcoming = next_reminder(medications)

    total_events = len(get_events())

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Active Medications",
            len(medications)
        )

    with col2:
        st.metric(
            "Recorded Events",
            total_events
        )

    with col3:
        st.metric(
            "Scheduled Reminders",
            sum(
                len(med[4].split(","))
                for med in medications if med[4]
            )
        )

    st.divider()

    st.header("⏰ Next Scheduled Reminder")

    if upcoming:

        reminder_time, medication_name = upcoming

        st.success(
            f"{medication_name} — "
            f"{reminder_time.strftime('%d %b %Y, %I:%M %p')}"
        )

    else:
        st.info("Add a medication schedule to see reminders.")

    st.divider()

    st.header("Your Medication Schedule")

    if medications:

        for med in medications:

            med_id, name, dosage, compartment, times = med

            with st.container(border=True):

                st.subheader(name)

                c1, c2 = st.columns(2)

                with c1:
                    st.write("**Dosage label:**", dosage or "Not specified")
                    st.write("**Compartment:**", compartment)

                with c2:
                    st.write("**Reminder times:**", times)
                    st.write("**Medication ID:**", med_id)

                st.write("**Record an event:**")

                a, b, c = st.columns(3)

                with a:
                    if st.button(
                        "Compartment Opened",
                        key=f"open_{med_id}"
                    ):
                        record_event(
                            med_id,
                            name,
                            "compartment_opened"
                        )
                        st.success("Opening event saved.")
                        st.rerun()

                with b:
                    if st.button(
                        "Patient Reports Taken",
                        key=f"taken_{med_id}"
                    ):
                        record_event(
                            med_id,
                            name,
                            "patient_reported_taken"
                        )
                        st.success("Patient report saved.")
                        st.rerun()

                with c:
                    if st.button(
                        "Patient Reports Missed",
                        key=f"missed_{med_id}"
                    ):
                        record_event(
                            med_id,
                            name,
                            "patient_reported_missed"
                        )
                        st.success("Patient report saved.")
                        st.rerun()

    else:
        st.info("No medications added yet.")

    st.caption(
        "Important: A compartment opening does not prove "
        "that medication was swallowed."
    )


# ==========================================
# ADD MEDICATION
# ==========================================

elif page == "Add Medication":

    st.title("➕ Add Medication")

    st.write(
        "Enter medication details and the scheduled reminder times."
    )

    with st.form("add_medication_form"):

        name = st.text_input("Medication Name")

        dosage = st.text_input(
            "Dosage label (as prescribed)"
        )

        compartment = st.number_input(
            "Compartment Number",
            min_value=1,
            max_value=12,
            value=1
        )

        times = st.text_input(
            "Reminder Times",
            placeholder="09:00, 14:00, 21:00"
        )

        st.caption(
            "Use 24-hour format. Separate multiple times with commas."
        )

        submit = st.form_submit_button("Save Medication")

        if submit:

            valid, parsed_times = validate_times(times)

            if not name.strip():
                st.error("Enter a medication name.")

            elif not valid:
                st.error(
                    "Enter valid times such as 09:00, 14:00, 21:00."
                )

            else:

                add_medication(
                    name.strip(),
                    dosage.strip(),
                    compartment,
                    ", ".join(parsed_times)
                )

                st.success("Medication saved!")
                st.rerun()


# ==========================================
# MANAGE MEDICATIONS
# ==========================================

elif page == "Manage Medications":

    st.title("⚙️ Manage Medications")

    if not medications:

        st.info("No medications available.")

    else:

        choices = {
            f"{med[1]} (ID: {med[0]})": med
            for med in medications
        }

        selected = st.selectbox(
            "Select medication",
            list(choices.keys())
        )

        med = choices[selected]

        med_id, name, dosage, compartment, times = med

        st.subheader("Edit Medication")

        with st.form("edit_medication_form"):

            new_name = st.text_input(
                "Medication Name",
                value=name
            )

            new_dosage = st.text_input(
                "Dosage Label",
                value=dosage or ""
            )

            new_compartment = st.number_input(
                "Compartment",
                min_value=1,
                max_value=12,
                value=int(compartment)
            )

            new_times = st.text_input(
                "Reminder Times",
                value=times or ""
            )

            save = st.form_submit_button("Update Medication")

            if save:

                valid, parsed_times = validate_times(new_times)

                if not new_name.strip():
                    st.error("Enter a medication name.")

                elif not valid:
                    st.error("Check the reminder time format.")

                else:

                    update_medication(
                        med_id,
                        new_name.strip(),
                        new_dosage.strip(),
                        new_compartment,
                        ", ".join(parsed_times)
                    )

                    st.success("Medication updated.")
                    st.rerun()

        st.divider()

        st.subheader("Delete Medication")

        st.warning(
            "Deleting a medication does not erase its existing event history."
        )

        confirm = st.checkbox(
            f"Confirm deletion of {name}"
        )

        if st.button(
            "Delete Selected Medication",
            disabled=not confirm
        ):

            delete_medication(med_id)

            st.success("Medication deleted.")
            st.rerun()


# ==========================================
# MEDICATION HISTORY
# ==========================================

elif page == "Medication History":

    st.title("📊 Medication Event History")

    events = get_events()

    if events:

        filter_type = st.selectbox(
            "Filter events",
            [
                "All Events",
                "compartment_opened",
                "patient_reported_taken",
                "patient_reported_missed",
                "reminder_sent",
                "reminder_dismissed"
            ]
        )

        for name, event_type, event_time, event_source in events:

            if (
                filter_type != "All Events"
                and filter_type != event_type
            ):
                continue

            with st.container(border=True):

                st.write(f"**Medication:** {name}")
                st.write(f"**Event:** {event_type}")
                st.caption(f"{event_time} | Source: {event_source}")

    else:
        st.info("No recorded events yet.")


# ==========================================
# PATIENT PROFILE
# ==========================================

elif page == "Patient Profile":

    st.title("👤 Patient Profile")

    profile = get_profile()

    current_name = profile[0] if profile else ""
    current_age = profile[1] if profile else 18
    current_contact = profile[2] if profile else ""

    with st.form("profile_form"):

        patient_name = st.text_input(
            "Display Name",
            value=current_name or ""
        )

        age = st.number_input(
            "Age",
            min_value=1,
            max_value=120,
            value=int(current_age or 18)
        )

        contact = st.text_input(
            "Emergency Contact",
            value=current_contact or ""
        )

        save_profile = st.form_submit_button("Save Profile")

        if save_profile:

            with connect() as conn:

                conn.execute("""
                INSERT INTO patient_profile
                (id, name, age, emergency_contact)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    age = excluded.age,
                    emergency_contact = excluded.emergency_contact
                """, (
                    patient_name,
                    age,
                    contact
                ))

            st.success("Profile saved.")


# ==========================================
# AI ASSISTANT
# ==========================================


elif page == "AI Assistant":

    st.title("🧠 CAREPULSE Intelligence")
    st.caption("Medication Event Intelligence Assistant")

    st.info(
        "This prototype analyses CAREPULSE records "
        "and explains application features. It does not "
        "provide medical diagnosis or treatment recommendations."
    )

    if "carepulse_chat_history" not in st.session_state:
        st.session_state.carepulse_chat_history = []

    with st.expander("Conversation controls"):
        if st.button("Clear conversation"):
            st.session_state.carepulse_chat_history = []
            st.rerun()

    st.subheader("Explore your CAREPULSE data")

    examples = [
        "Show my medications",
        "Give me my event summary",
        "Analyse my medication patterns",
        "What is my next reminder?",
        "Explain compartment openings"
    ]

    cols = st.columns(2)

    for i, example in enumerate(examples):
        with cols[i % 2]:
            if st.button(example, key=f"example_{i}"):
                st.session_state.carepulse_pending_question = example

    for message in st.session_state.carepulse_chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input(
        "Ask CAREPULSE Intelligence..."
    )

    if not prompt and "carepulse_pending_question" in st.session_state:
        prompt = st.session_state.pop(
            "carepulse_pending_question"
        )

    if prompt:

        st.session_state.carepulse_chat_history.append({
            "role": "user",
            "content": prompt
        })

        with st.chat_message("user"):
            st.markdown(prompt)

        response = answer_question(
            prompt,
            st.session_state.carepulse_chat_history
        )

        st.session_state.carepulse_chat_history.append({
            "role": "assistant",
            "content": response
        })

        with st.chat_message("assistant"):
            st.markdown(response)

    st.divider()

    st.caption(
        "CAREPULSE Intelligence | "
        "Database-connected analytical assistant"
    )


# ==========================================
# FOOTER
# ==========================================

st.divider()

st.caption(
    "CAREPULSE V2 | Smart Medication Management | "
    "Prototype — not for clinical use"
)
