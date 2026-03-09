# trainer_app.py
# Club 24 - Multi-Club PT Score Dashboard
# One shared app for all 7 locations.
# Host this once, and every club uses the same link.

from datetime import datetime, date
import os
from typing import Dict, Tuple

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


# -------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------
st.set_page_config(
    page_title="Club 24 PT Dashboard",
    page_icon="🏋️",
    layout="wide",
)
# Initialize login session state
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

# Define credentials (use hashed password)
AUTHORIZED_USERNAME = "admin"
AUTHORIZED_PASSWORD_HASH = hashlib.sha256("adminpass".encode()).hexdigest()

def check_login(username, password):
    return username == AUTHORIZED_USERNAME and hashlib.sha256(password.encode()).hexdigest() == AUTHORIZED_PASSWORD_HASH

# Login form
if not st.session_state["logged_in"]:
    st.title("Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_submit = st.form_submit_button("Login")
        if login_submit:
            if check_login(username, password):
                st.session_state["logged_in"] = True
                st.success("Logged in successfully!")
                st.experimental_rerun()
            else:
                st.error("Invalid credentials")
    st.stop()


# -------------------------------------------------
# CONSTANTS
# -------------------------------------------------
CLUBS = [
    "New Milford",
    "Brookfield",
    "Ridgefield",
    "Torrington",
    "Newtown",
    "Wallingford",
    "Middletown",
]

DEFAULT_DIRECTOR_PASSWORD = "club24director"


def get_database_url() -> str:
    """
    Supports both local environment variables and hosted Streamlit secrets.
    Local:
        DATABASE_URL=postgresql+psycopg2://...
    Streamlit Cloud secrets:
        st.secrets["DATABASE_URL"]
    """
    database_url = os.getenv("DATABASE_URL", "")

    if not database_url:
        try:
            database_url = st.secrets["DATABASE_URL"]
        except Exception:
            database_url = ""

    return database_url.strip()


DATABASE_URL = get_database_url()


# -------------------------------------------------
# DATABASE
# -------------------------------------------------
@st.cache_resource
def get_engine():
    if not DATABASE_URL:
        raise ValueError(
            "DATABASE_URL is not set. Add it as an environment variable or Streamlit secret."
        )
    return create_engine(DATABASE_URL, pool_pre_ping=True)


def init_db():
    engine = get_engine()

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS submissions (
                    id SERIAL PRIMARY KEY,
                    week_start DATE NOT NULL,
                    trainer_name VARCHAR(100) NOT NULL,
                    club VARCHAR(50) NOT NULL,
                    hours_worked NUMERIC(10,2) NOT NULL,
                    kickoffs_booked INTEGER NOT NULL,
                    kickoffs_completed INTEGER NOT NULL,
                    pt_sold NUMERIC(12,2) NOT NULL,
                    submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS scoring_settings (
                    id INTEGER PRIMARY KEY,
                    target_hours NUMERIC(10,2) NOT NULL,
                    target_booked INTEGER NOT NULL,
                    target_completed INTEGER NOT NULL,
                    target_pt_sold NUMERIC(12,2) NOT NULL,
                    weight_hours NUMERIC(10,2) NOT NULL,
                    weight_booked NUMERIC(10,2) NOT NULL,
                    weight_completed NUMERIC(10,2) NOT NULL,
                    weight_pt_sold NUMERIC(10,2) NOT NULL,
                    director_password VARCHAR(100) NOT NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

        existing = conn.execute(
            text("SELECT COUNT(*) FROM scoring_settings WHERE id = 1")
        ).scalar()

        if existing == 0:
            conn.execute(
                text(
                    """
                    INSERT INTO scoring_settings (
                        id,
                        target_hours,
                        target_booked,
                        target_completed,
                        target_pt_sold,
                        weight_hours,
                        weight_booked,
                        weight_completed,
                        weight_pt_sold,
                        director_password,
                        updated_at
                    )
                    VALUES (
                        1,
                        :target_hours,
                        :target_booked,
                        :target_completed,
                        :target_pt_sold,
                        :weight_hours,
                        :weight_booked,
                        :weight_completed,
                        :weight_pt_sold,
                        :director_password,
                        :updated_at
                    )
                    """
                ),
                {
                    "target_hours": 25,
                    "target_booked": 8,
                    "target_completed": 6,
                    "target_pt_sold": 1000,
                    "weight_hours": 20,
                    "weight_booked": 25,
                    "weight_completed": 25,
                    "weight_pt_sold": 30,
                    "director_password": DEFAULT_DIRECTOR_PASSWORD,
                    "updated_at": datetime.now(),
                },
            )


def get_settings() -> Dict:
    engine = get_engine()
    df = pd.read_sql("SELECT * FROM scoring_settings WHERE id = 1", engine)

    if df.empty:
        raise ValueError("Scoring settings not found.")

    return df.iloc[0].to_dict()


def update_settings(
    target_hours: float,
    target_booked: int,
    target_completed: int,
    target_pt_sold: float,
    weight_hours: float,
    weight_booked: float,
    weight_completed: float,
    weight_pt_sold: float,
    director_password: str,
):
    engine = get_engine()

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE scoring_settings
                SET target_hours = :target_hours,
                    target_booked = :target_booked,
                    target_completed = :target_completed,
                    target_pt_sold = :target_pt_sold,
                    weight_hours = :weight_hours,
                    weight_booked = :weight_booked,
                    weight_completed = :weight_completed,
                    weight_pt_sold = :weight_pt_sold,
                    director_password = :director_password,
                    updated_at = :updated_at
                WHERE id = 1
                """
            ),
            {
                "target_hours": target_hours,
                "target_booked": target_booked,
                "target_completed": target_completed,
                "target_pt_sold": target_pt_sold,
                "weight_hours": weight_hours,
                "weight_booked": weight_booked,
                "weight_completed": weight_completed,
                "weight_pt_sold": weight_pt_sold,
                "director_password": director_password,
                "updated_at": datetime.now(),
            },
        )


def add_submission(
    week_start: date,
    trainer_name: str,
    club: str,
    hours_worked: float,
    kickoffs_booked: int,
    kickoffs_completed: int,
    pt_sold: float,
):
    engine = get_engine()

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO submissions (
                    week_start,
                    trainer_name,
                    club,
                    hours_worked,
                    kickoffs_booked,
                    kickoffs_completed,
                    pt_sold,
                    submitted_at
                )
                VALUES (
                    :week_start,
                    :trainer_name,
                    :club,
                    :hours_worked,
                    :kickoffs_booked,
                    :kickoffs_completed,
                    :pt_sold,
                    :submitted_at
                )
                """
            ),
            {
                "week_start": week_start,
                "trainer_name": trainer_name.strip(),
                "club": club,
                "hours_worked": hours_worked,
                "kickoffs_booked": kickoffs_booked,
                "kickoffs_completed": kickoffs_completed,
                "pt_sold": pt_sold,
                "submitted_at": datetime.now(),
            },
        )


def get_submissions() -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql(
        "SELECT * FROM submissions ORDER BY week_start DESC, submitted_at DESC",
        engine,
    )


# -------------------------------------------------
# SCORING
# -------------------------------------------------
def metric_score(actual: float, target: float, weight: float) -> float:
    if float(target) <= 0:
        return 0.0
    ratio = min(float(actual) / float(target), 1.0)
    return round(ratio * float(weight), 2)


def calculate_score(row: pd.Series, settings: Dict) -> Tuple[float, Dict[str, float]]:
    parts = {
        "Hours Score": metric_score(row["hours_worked"], settings["target_hours"], settings["weight_hours"]),
        "Booked Score": metric_score(row["kickoffs_booked"], settings["target_booked"], settings["weight_booked"]),
        "Completed Score": metric_score(row["kickoffs_completed"], settings["target_completed"], settings["weight_completed"]),
        "PT Sold Score": metric_score(row["pt_sold"], settings["target_pt_sold"], settings["weight_pt_sold"]),
    }
    total = round(sum(parts.values()), 2)
    return total, parts


def build_scored_df(df: pd.DataFrame, settings: Dict) -> pd.DataFrame:
    if df.empty:
        return df

    rows = []
    for _, row in df.iterrows():
        total, parts = calculate_score(row, settings)
        item = row.to_dict()
        item.update(parts)
        item["Trainer Score"] = total
        rows.append(item)

    scored = pd.DataFrame(rows)
    return scored[
        [
            "week_start",
            "trainer_name",
            "club",
            "hours_worked",
            "kickoffs_booked",
            "kickoffs_completed",
            "pt_sold",
            "Trainer Score",
            "Hours Score",
            "Booked Score",
            "Completed Score",
            "PT Sold Score",
            "submitted_at",
        ]
    ]


# -------------------------------------------------
# APP STARTUP
# -------------------------------------------------
st.title("Club 24 PT Score Dashboard")
st.caption("Better Clubs. Better Price. Always Open.")

try:
    init_db()
    settings = get_settings()
except (ValueError, SQLAlchemyError) as e:
    st.error(f"Database connection failed: {e}")
    st.info("Set DATABASE_URL first, then restart the app.")
    st.stop()

mode = st.sidebar.radio(
    "Choose view",
    ["Trainer Input", "PT Director Dashboard"],
)


# -------------------------------------------------
# TRAINER VIEW
# -------------------------------------------------
if mode == "Trainer Input":
    st.subheader("Weekly Trainer Submission")
    st.write("Use this once per week for each trainer.")

    with st.form("trainer_form", clear_on_submit=True):
        week_start = st.date_input("Week Starting", value=date.today())
        trainer_name = st.text_input("Trainer Name")
        club = st.selectbox("Club", CLUBS)

        col1, col2 = st.columns(2)
        with col1:
            hours_worked = st.number_input("Hours Worked", min_value=0.0, step=0.5)
            kickoffs_booked = st.number_input("Kickoffs Booked", min_value=0, step=1)
        with col2:
            kickoffs_completed = st.number_input("Kickoffs Completed", min_value=0, step=1)
            pt_sold = st.number_input("PT Sold ($)", min_value=0.0, step=50.0)

        submit = st.form_submit_button("Submit Weekly Numbers")

        if submit:
            if not trainer_name.strip():
                st.error("Trainer Name is required.")
            elif kickoffs_completed > kickoffs_booked:
                st.error("Kickoffs Completed cannot be greater than Kickoffs Booked.")
            else:
                try:
                    add_submission(
                        week_start=week_start,
                        trainer_name=trainer_name,
                        club=club,
                        hours_worked=float(hours_worked),
                        kickoffs_booked=int(kickoffs_booked),
                        kickoffs_completed=int(kickoffs_completed),
                        pt_sold=float(pt_sold),
                    )
                    st.success("Weekly submission saved.")
                except SQLAlchemyError as e:
                    st.error(f"Could not save submission: {e}")

    st.divider()
    st.caption("Trainer view only shows data entry. Trainer score stays hidden from trainers.")


# -------------------------------------------------
# DIRECTOR VIEW
# -------------------------------------------------
else:
    st.subheader("PT Director Dashboard")
    password = st.text_input("Director Password", type="password")

    if password != str(settings["director_password"]):
        st.warning("Enter the director password to access the dashboard.")
    else:
        tab1, tab2, tab3 = st.tabs(["Dashboard", "Scoring Setup", "Exports"])

        with tab1:
            try:
                df = get_submissions()
            except SQLAlchemyError as e:
                st.error(f"Could not load submissions: {e}")
                st.stop()

            scored_df = build_scored_df(df, settings)

            if scored_df.empty:
                st.info("No submissions yet.")
            else:
                weeks = ["All"] + sorted(
                    scored_df["week_start"].astype(str).unique().tolist(),
                    reverse=True,
                )
                selected_week = st.selectbox("Filter by Week", weeks)

                clubs = ["All"] + CLUBS
                selected_club = st.selectbox("Filter by Club", clubs)

                filtered = scored_df.copy()
                if selected_week != "All":
                    filtered = filtered[filtered["week_start"].astype(str) == selected_week]
                if selected_club != "All":
                    filtered = filtered[filtered["club"] == selected_club]

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total Submissions", len(filtered))
                c2.metric("Avg Trainer Score", round(filtered["Trainer Score"].mean(), 2))
                c3.metric("Kickoffs Completed", int(filtered["kickoffs_completed"].sum()))
                c4.metric("PT Sold", f"${filtered['pt_sold'].sum():,.2f}")

                st.write("### Trainer Leaderboard")
                leaderboard = filtered.sort_values(by="Trainer Score", ascending=False).reset_index(drop=True)
                st.dataframe(
                    leaderboard[
                        [
                            "week_start",
                            "trainer_name",
                            "club",
                            "hours_worked",
                            "kickoffs_booked",
                            "kickoffs_completed",
                            "pt_sold",
                            "Trainer Score",
                        ]
                    ],
                    use_container_width=True,
                )

                st.write("### Club Scoreboard")
                club_summary = (
                    filtered.groupby("club", as_index=False)
                    .agg(
                        submissions=("trainer_name", "count"),
                        total_hours=("hours_worked", "sum"),
                        total_booked=("kickoffs_booked", "sum"),
                        total_completed=("kickoffs_completed", "sum"),
                        total_pt_sold=("pt_sold", "sum"),
                        avg_score=("Trainer Score", "mean"),
                    )
                    .sort_values(by="avg_score", ascending=False)
                )
                club_summary["avg_score"] = club_summary["avg_score"].round(2)
                st.dataframe(club_summary, use_container_width=True)

                st.write("### Full Director View")
                st.dataframe(filtered, use_container_width=True)

        with tab2:
            st.write("Adjust the targets and score weights here.")
            st.caption("Weights must total 100.")

            with st.form("settings_form"):
                col1, col2 = st.columns(2)
                with col1:
                    target_hours = st.number_input(
                        "Target Hours Worked",
                        min_value=0.0,
                        value=float(settings["target_hours"]),
                        step=1.0,
                    )
                    target_booked = st.number_input(
                        "Target Kickoffs Booked",
                        min_value=0,
                        value=int(settings["target_booked"]),
                        step=1,
                    )
                    target_completed = st.number_input(
                        "Target Kickoffs Completed",
                        min_value=0,
                        value=int(settings["target_completed"]),
                        step=1,
                    )
                    target_pt_sold = st.number_input(
                        "Target PT Sold ($)",
                        min_value=0.0,
                        value=float(settings["target_pt_sold"]),
                        step=50.0,
                    )
                with col2:
                    weight_hours = st.number_input(
                        "Weight: Hours",
                        min_value=0.0,
                        value=float(settings["weight_hours"]),
                        step=1.0,
                    )
                    weight_booked = st.number_input(
                        "Weight: Booked",
                        min_value=0.0,
                        value=float(settings["weight_booked"]),
                        step=1.0,
                    )
                    weight_completed = st.number_input(
                        "Weight: Completed",
                        min_value=0.0,
                        value=float(settings["weight_completed"]),
                        step=1.0,
                    )
                    weight_pt_sold = st.number_input(
                        "Weight: PT Sold",
                        min_value=0.0,
                        value=float(settings["weight_pt_sold"]),
                        step=1.0,
                    )

                new_password = st.text_input(
                    "Director Password",
                    value=str(settings["director_password"]),
                    type="password",
                )

                save = st.form_submit_button("Save Scoring Settings")

                if save:
                    total_weight = (
                        weight_hours + weight_booked + weight_completed + weight_pt_sold
                    )
                    if round(total_weight, 2) != 100.0:
                        st.error("Weights must total exactly 100.")
                    else:
                        try:
                            update_settings(
                                target_hours=float(target_hours),
                                target_booked=int(target_booked),
                                target_completed=int(target_completed),
                                target_pt_sold=float(target_pt_sold),
                                weight_hours=float(weight_hours),
                                weight_booked=float(weight_booked),
                                weight_completed=float(weight_completed),
                                weight_pt_sold=float(weight_pt_sold),
                                director_password=new_password,
                            )
                            st.success("Scoring settings updated.")
                            st.rerun()
                        except SQLAlchemyError as e:
                            st.error(f"Could not update settings: {e}")

        with tab3:
            try:
                df = get_submissions()
                scored_df = build_scored_df(df, settings)
            except SQLAlchemyError as e:
                st.error(f"Could not generate exports: {e}")
                st.stop()

            if scored_df.empty:
                st.info("No export data yet.")
            else:
                director_csv = scored_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Download Director CSV",
                    data=director_csv,
                    file_name="club24_pt_director_dashboard.csv",
                    mime="text/csv",
                )

                trainer_csv = scored_df[
                    [
                        "week_start",
                        "trainer_name",
                        "club",
                        "hours_worked",
                        "kickoffs_booked",
                        "kickoffs_completed",
                        "pt_sold",
                        "submitted_at",
                    ]
                ].to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Download Trainer Input CSV",
                    data=trainer_csv,
                    file_name="club24_trainer_inputs.csv",
                    mime="text/csv",
                )

st.divider()
st.caption("Real Gyms. Real Goals. Real Results.")
