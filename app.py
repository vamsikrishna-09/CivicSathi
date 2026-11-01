"""CivicSathi - Streamlit front end.  Run with:  streamlit run app.py"""
import csv
import html
import io
import logging

import streamlit as st

import agents
import ai_service
import config
import database
from models import AUTO_DETECT, CATEGORIES, STATUSES, validate_complaint, validate_image
from utils import format_time, normalize_tracking_id

log = logging.getLogger("civicsathi")
PAGES = ["Report an Issue", "Track Complaint", "Admin Dashboard", "About / How it works"]

st.set_page_config(page_title="CivicSathi", page_icon="🏛️", layout="wide")
st.markdown("""
<style>
.cs-badge{display:inline-block;padding:.15rem .6rem;border-radius:4px;font-weight:600;font-size:.9rem}
.cs-high{background:#8a1c1c;color:#fff}
.cs-medium{background:#ffe3a3;color:#5c3b00}
.cs-low{background:#d3ecdc;color:#17492e}
.cs-info{background:#dbe7f5;color:#12365f}
.cs-demo{background:#e8e8ee;color:#2b2b3a;border:1px solid #9a9ab0}
.cs-label{font-size:.85rem;opacity:.75;margin-bottom:.15rem}
.cs-id{font-size:1.8rem;font-weight:700;letter-spacing:.04em}
</style>""", unsafe_allow_html=True)

for key, default in {"pending": None, "registered": None, "form_n": 0, "flash": None}.items():
    st.session_state.setdefault(key, default)


def badge(text, kind):
    return f'<span class="cs-badge cs-{kind}">{html.escape(str(text))}</span>'


def priority_badge(priority):  # text label is always shown, never colour alone
    return badge(f"{priority} priority", priority.lower())


def field(label, value_html):
    st.markdown(f'<div class="cs-label">{label}</div>{value_html}', unsafe_allow_html=True)


def ensure_db():
    try:
        database.init_db(config.DB_PATH)
        return None
    except Exception:
        log.exception("Database initialisation failed")
        return ("The local database is unavailable, so complaints cannot be saved or loaded. "
                "Check CIVICSATHI_DB_PATH and the folder permissions.")


db_error = ensure_db()


# ---------- navigation callbacks ----------

def go_track(tracking_id):
    st.session_state.nav = "Track Complaint"
    st.session_state.track_input = tracking_id
    st.session_state.auto_track = True


def reset_report():
    st.session_state.pending = None
    st.session_state.registered = None
    st.session_state.form_n += 1  # a new form key gives empty widgets


# ---------- sidebar ----------

with st.sidebar:
    st.title("CivicSathi")
    page = st.radio("Go to", PAGES, key="nav")
    mode = ai_service.current_mode()
    st.markdown(f"Analysis mode {badge(mode, 'demo')}", unsafe_allow_html=True)
    if mode == "DEMO":
        st.caption("Built-in keyword rules are used. No API key is needed.")
    if ai_service.is_configured() and not ai_service.AI_INTEGRATION_IMPLEMENTED:
        st.caption("A Gemini key is set, but the AI integration is not implemented yet, so demo rules are used.")
    st.caption("Database: ready" if not db_error else "Database: unavailable")
    st.caption("Prototype only. Not an official government service or an emergency channel.")


# ---------- Report an Issue ----------

def trace_table(rows, pending_registration=False):
    rows = list(rows)
    if pending_registration:
        rows.append({"Stage": "Complaint Registration", "Mode": "-", "Status": "waiting for your confirmation",
                     "Input": "-", "Output": "-", "Time (ms)": None})
    st.dataframe(rows, hide_index=True)


def render_analysis(p):
    a, r = p["analysis"], p["routing"]
    st.subheader("Review the proposed result")
    st.caption(f"Analysed report: \"{p['description'][:120]}\" at {p['location']}")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        field("Suggested category", f"<b>{html.escape(a.category)}</b>")
    with c2:
        field("Priority", priority_badge(r.priority))
    with c3:
        field("Suggested department", f"<b>{html.escape(r.department)}</b>")
    with c4:
        field("Analysis mode", badge(a.analysis_mode if a.analysis_mode == r.analysis_mode else "DEMO + AI", "demo"))
    st.write(a.summary)
    st.markdown(f"**Why this priority:** {r.priority_reason}")
    st.markdown(f"**Why this department:** {r.department_reason}")
    if a.evidence_notes:
        st.markdown("**Evidence:** " + "; ".join(a.evidence_notes))
    if a.uncertainty:
        st.info(a.uncertainty)
    if a.confidence is not None:
        st.caption(f"Confidence: {a.confidence:.0%}")
    if a.image_note:
        st.info(a.image_note)
    if r.human_review:
        st.warning("Human review is recommended: this result is uncertain or may be serious.")
    st.caption("Routing is a recommendation only. Registering saves the complaint in this prototype; "
               "it is not sent to any municipal authority.")
    with st.expander("Workflow trace", expanded=False):
        trace_table(p["trace"], pending_registration=True)


def do_register(p):
    try:
        complaint, extra = agents.register_complaint(config.DB_PATH, p, config.UPLOAD_DIR)
    except Exception:
        log.exception("Registration failed")
        st.error("The complaint could not be saved, so no tracking ID was created. Please try again.")
        return
    st.session_state.registered = {"complaint": complaint, "trace": p["trace"] + extra}
    st.session_state.pending = None  # prevents a second click from creating a duplicate
    st.rerun()


def render_registered(reg):
    c = reg["complaint"]
    st.success("Your complaint is registered in this prototype.")
    field("Your tracking ID", f'<div class="cs-id">{html.escape(c["tracking_id"])}</div>')
    st.markdown(f"Status: {badge(c['status'], 'info')}", unsafe_allow_html=True)
    st.caption("Keep this ID to check progress. The record is stored locally in this prototype "
               "and has not been sent to a municipal authority.")
    b1, b2, _ = st.columns([1, 1, 3])
    b1.button("Track this complaint", type="primary", on_click=go_track, args=(c["tracking_id"],))
    b2.button("Report another issue", on_click=reset_report)
    with st.expander("Workflow trace"):
        trace_table(reg["trace"])


def report_page():
    st.header("Report a civic issue")
    reg = st.session_state.registered
    if reg:
        render_registered(reg)
        return
    st.info("This is a prototype. Reports are stored locally in this app and are not sent to any authority. "
            "Please do not include names, phone numbers or home addresses.")
    with st.form(f"report_form_{st.session_state.form_n}"):
        description = st.text_area("What is the problem?", height=130,
                                   placeholder="Example: There is a large pothole near the main bus stop. "
                                               "Vehicles are swerving to avoid it.")
        location = st.text_input("Approximate public location",
                                 placeholder="Road, landmark, junction or locality (not a home address)")
        category = st.selectbox("Category", [AUTO_DETECT] + CATEGORIES)
        photo = st.file_uploader("Photo (optional)", type=["jpg", "jpeg", "png"],
                                 help="JPG or PNG, up to 5 MB. Avoid faces and vehicle number plates.")
        st.caption("JPG or PNG, up to 5 MB. Please avoid faces and vehicle number plates.")
        consent = st.checkbox("I agree that these details are stored in this local prototype.")
        submitted = st.form_submit_button("Analyse complaint", type="primary")

    if submitted:
        st.session_state.pending = None
        clean, errors = validate_complaint(description, location, category, consent)
        image = None
        if photo is not None:
            data = photo.getvalue()
            image_error = validate_image(photo.name, data)
            if image_error:
                errors.append(image_error)
            else:
                image = {"name": photo.name, "data": data}
        if errors:
            for message in errors:
                st.error(message)
        else:
            with st.spinner("Analysing your report..."):
                result = agents.run_analysis(clean["description"], clean["location"], clean["category"],
                                             has_image=image is not None)
            st.session_state.pending = {**clean, **result, "image": image}

    pending = st.session_state.pending
    if pending:
        render_analysis(pending)
        if db_error:
            st.error(db_error)
        elif st.button("Register complaint", type="primary"):
            do_register(pending)
    else:
        st.caption("Complete the form and choose Analyse complaint to see a suggested category, priority and department.")


# ---------- Track Complaint ----------

def track_page():
    st.header("Track a complaint")
    if db_error:
        st.error(db_error)
        return
    raw = st.text_input("Tracking ID", key="track_input", placeholder="CS-2026-AB12CD")
    clicked = st.button("Track complaint", type="primary")
    auto = st.session_state.pop("auto_track", False)
    if not (clicked or auto):
        st.info("Enter a tracking ID to view a complaint.")
        return
    tracking_id = normalize_tracking_id(raw)
    if tracking_id is None:
        st.error("That tracking ID is not in the expected format (for example CS-2026-AB12CD). Check it and try again.")
        return
    c = database.get_by_tracking_id(config.DB_PATH, tracking_id)
    if c is None:
        st.warning("No complaint was found for that tracking ID. Check the ID and try again.")
        return
    field("Tracking ID", f'<div class="cs-id">{html.escape(c["tracking_id"])}</div>')
    a, b, d = st.columns(3)
    with a:
        field("Status", badge(c["status"], "info"), )
        field("Priority", priority_badge(c["priority"]))
    with b:
        field("Category", f"<b>{html.escape(c['category'])}</b>")
        field("Suggested department", f"<b>{html.escape(c['department'])}</b>")
    with d:
        field("Approximate location", f"<b>{html.escape(c['location'])}</b>")
        field("Submitted", f"<b>{format_time(c['created_at'])}</b>")
    st.caption("This record lives only in this prototype. It has not been sent to a municipal authority.")


# ---------- Admin Dashboard ----------

def admin_page():
    if not config.ADMIN_PASSWORD:
        st.error("Admin login is not configured. Set CIVICSATHI_ADMIN_PASSWORD in your secrets.")
        return

    if not st.session_state.get("admin_authenticated", False):
        st.header("Admin Login")
        with st.form("admin_login_form"):
            password = st.text_input("Admin password", type="password")
            submitted = st.form_submit_button("Log in")

        if submitted:
            import hmac
            if hmac.compare_digest(password, config.ADMIN_PASSWORD):
                st.session_state.admin_authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password. Please try again.")
        return

    st.header("Admin Dashboard")


    if st.button("Logout"):
        st.session_state.admin_authenticated = False
        st.rerun()
    if db_error:
        st.error(db_error)
        return
    if st.session_state.flash:
        st.success(st.session_state.flash)
        st.session_state.flash = None

    counts = database.status_counts(config.DB_PATH)
    cols = st.columns(len(STATUSES) + 1)
    cols[0].metric("Total", sum(counts.values()))
    for col, status in zip(cols[1:], STATUSES):
        col.metric(status, counts[status])

    f1, f2, f3 = st.columns(3)
    category = f1.selectbox("Category", ["All"] + CATEGORIES)
    priority = f2.selectbox("Priority", ["All", "High", "Medium", "Low"])
    status = f3.selectbox("Status", ["All"] + list(STATUSES))
    rows = database.list_complaints(config.DB_PATH, category, priority, status)

    if not rows:
        st.info("No complaints have been registered yet. Submit a demo complaint to see it here.")
    else:
        table = [{"Tracking ID": r["tracking_id"], "Category": r["category"], "Priority": r["priority"],
                  "Department": r["department"], "Location": r["location"],
                  "Submitted": format_time(r["created_at"]), "Status": r["status"],
                  "Sample data": "Yes" if r["is_demo"] else ""} for r in rows]
        st.dataframe(table, hide_index=True)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(table[0].keys()))
        writer.writeheader()
        writer.writerows(table)
        st.download_button("Download CSV", buf.getvalue(), "civicsathi_complaints.csv", "text/csv")

        st.subheader("Complaint details")
        chosen = st.selectbox("Open a complaint", [r["tracking_id"] for r in rows])
        c = next(r for r in rows if r["tracking_id"] == chosen)
        st.markdown(f"{priority_badge(c['priority'])} &nbsp; {badge(c['status'], 'info')} &nbsp; {badge(c['analysis_mode'], 'demo')}",
                    unsafe_allow_html=True)
        st.markdown("**Description**")
        st.write(c["description"])
        st.markdown(f"**Location:** {c['location']}")
        st.markdown(f"**Category:** {c['category']}  \n**Department:** {c['department']}")
        st.markdown(f"**Summary:** {c['summary']}")
        st.markdown(f"**Priority reason:** {c['priority_reason']}  \n**Department reason:** {c['department_reason']}")
        if c["human_review"]:
            st.warning("Flagged for human review.")
        new_status = st.selectbox("New status", list(STATUSES), index=list(STATUSES).index(c["status"]),
                                  key=f"status_{chosen}")
        if st.button("Update status"):
            try:
                database.update_status(config.DB_PATH, chosen, new_status)
            except ValueError as exc:
                st.error(str(exc))
            except Exception:
                log.exception("Status update failed")
                st.error("The status could not be updated. Please try again.")
            else:
                st.session_state.flash = f"{chosen} is now {new_status}."
                st.rerun()

    st.divider()
    st.subheader("Delete complaint")

    if c["is_demo"]:
            confirm_delete = st.checkbox(
                "I confirm I want to delete this demo complaint",
                key=f"delete_confirm_{chosen}"
            )

            if st.button("Delete demo complaint", type="secondary"):
                if confirm_delete:
                    database.delete_complaint(config.DB_PATH, chosen)
                    st.session_state.flash = f"{chosen} deleted successfully."
                    st.rerun()
                else:
                    st.warning("Please confirm deletion first.")
    else:
        st.info("Only demo complaints can be deleted from this dashboard.")

    with st.expander("Sample data for demos"):
        st.caption("Adds five fictional complaints, labelled as demo data. Delete the database file to start fresh.")
        if st.button("Add sample complaints"):
            added = database.seed_demo_data(config.DB_PATH)
            st.session_state.flash = f"Added {added} sample complaints." if added else "Sample complaints were already added."
            st.rerun()


# ---------- About ----------

def about_page():
    st.header("How CivicSathi works")
    st.markdown("""
CivicSathi helps you report everyday civic problems and follow what happens next.

1. **Issue Analysis** suggests a category (pothole, garbage, water leakage, blocked drain, broken streetlight, or other) from your description.
2. **Severity & Department Routing** suggests a priority (Low, Medium or High) and a likely department, with a short reason for each.
3. **Complaint Registration** happens only when you click *Register complaint*. You then get a tracking ID.

**Demo and AI modes.** Without an API key the app uses simple keyword rules and labels every result *DEMO*. A result is only labelled *AI* after a real, successful AI call. In demo mode a photo is accepted but not looked at.

**Privacy.** Complaints are stored in a local SQLite file on the machine running this app. We ask for no names, phone numbers, emails or home addresses. Please avoid photos with faces or number plates.

**Limits.** This is a hackathon prototype, not an official government service or an emergency channel. Complaints are not sent to any municipal authority, department suggestions are advisory, and the admin dashboard has no login.
""")


{"Report an Issue": report_page, "Track Complaint": track_page,
 "Admin Dashboard": admin_page, "About / How it works": about_page}[page]()
