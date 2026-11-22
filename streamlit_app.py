
import streamlit as st
import sqlite3
from datetime import datetime

# -----------------------------
# PAGE CONFIGURATION
# -----------------------------

st.set_page_config(
    page_title="CAREPULSE",
    page_icon="💊",
    layout="wide"
)

# -----------------------------
# DATABASE
# -----------------------------

conn = sqlite3.connect("carepulse.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS medications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    dosage TEXT,
    compartment INTEGER,
    reminder TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    medication_id INTEGER,
    medication_name TEXT,
    event_type TEXT,
    event_time TEXT
)
""")

conn.commit()


def record_event(med_id, name, event_type):
    cursor.execute("""
    INSERT INTO events
    (medication_id, medication_name, event_type, event_time)
    VALUES (?, ?, ?, ?)
    """, (
        med_id,
        name,
        event_type,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()


# -----------------------------
# SIDEBAR
# -----------------------------

st.sidebar.title("💊 CAREPULSE")

page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Add Medication",
        "Medication History",
        "AI Assistant",
        "About"
    ]
)

# -----------------------------
# DASHBOARD
# -----------------------------

if page == "Dashboard":

    st.title("💊 CAREPULSE")
    st.subheader("Your Personal Medication Companion")

    st.write("Welcome to your patient dashboard.")

    cursor.execute("SELECT * FROM medications")
    medications = cursor.fetchall()

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Active Medications", len(medications))

    with col2:
        st.metric("Recorded Events", cursor.execute(
            "SELECT COUNT(*) FROM events"
        ).fetchone()[0])

    st.divider()

    st.header("Your Medication Schedule")

    if medications:

        for med in medications:

            med_id, name, dosage, compartment, reminder = med

            with st.container(border=True):

                st.subheader(name)

                st.write("Dosage label:", dosage or "Not specified")
                st.write("Compartment:", compartment)
                st.write("Reminder:", reminder)

                col1, col2 = st.columns(2)

                with col1:
                    if st.button(
                        "Record Compartment Opening",
                        key=f"open_{med_id}"
                    ):
                        record_event(
                            med_id,
                            name,
                            "compartment_opened"
                        )
                        st.success("Opening event recorded.")
                        st.rerun()

                with col2:
                    if st.button(
                        "I Report Medication Taken",
                        key=f"taken_{med_id}"
                    ):
                        record_event(
                            med_id,
                            name,
                            "patient_reported_taken"
                        )
                        st.success("Patient report recorded.")
                        st.rerun()

    else:
        st.info("No medications added yet. Use Add Medication.")

    st.caption(
        "A compartment opening does not prove medication ingestion."
    )


# -----------------------------
# ADD MEDICATION
# -----------------------------

elif page == "Add Medication":

    st.title("Add New Medication")

    with st.form("medication_form"):

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

        reminder = st.time_input(
            "Scheduled Reminder"
        )

        submit = st.form_submit_button("Save Medication")

        if submit:

            if name.strip():

                cursor.execute("""
                INSERT INTO medications
                (name, dosage, compartment, reminder)
                VALUES (?, ?, ?, ?)
                """, (
                    name.strip(),
                    dosage,
                    compartment,
                    reminder.strftime("%H:%M")
                ))

                conn.commit()

                st.success("Medication added successfully!")

            else:
                st.error("Please enter a medication name.")


# -----------------------------
# MEDICATION HISTORY
# -----------------------------

elif page == "Medication History":

    st.title("Medication Event History")

    cursor.execute("""
    SELECT medication_name, event_type, event_time
    FROM events
    ORDER BY id DESC
    """)

    events = cursor.fetchall()

    if events:

        for name, event, event_time in events:

            with st.container(border=True):

                st.write("**Medication:**", name)
                st.write("**Event:**", event)
                st.caption(event_time)

    else:
        st.info("No events recorded yet.")


# -----------------------------
# AI ASSISTANT
# -----------------------------

elif page == "AI Assistant":

    st.title("🤖 CAREPULSE AI Assistant")

    st.write(
        "Ask general questions about medication terminology "
        "and medication information."
    )

    st.warning(
        "AI integration is not connected yet. "
        "This section is currently a prototype."
    )

    question = st.text_area(
        "Enter your question"
    )

    if st.button("Submit Question"):

        if question.strip():
            st.info(
                "Your question has been received. "
                "The AI response engine will be integrated "
                "in a later development stage."
            )

        else:
            st.error("Please enter a question.")


# -----------------------------
# ABOUT
# -----------------------------

elif page == "About":

    st.title("About CAREPULSE")

    st.write(
        "CAREPULSE is a medication reminder and "
        "event-monitoring system combining software, "
        "AI-assisted analysis and a future physical device."
    )

    st.subheader("Core Features")

    st.write("- Medication management")
    st.write("- Medication event history")
    st.write("- Compartment opening records")
    st.write("- Patient-reported medication records")
    st.write("- AI medical information assistant (planned)")
    st.write("- Smart physical reminder device (planned)")

    st.info(
        "Opening a compartment is not proof that "
        "medication was swallowed."
    )
