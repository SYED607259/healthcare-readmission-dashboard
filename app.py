from __future__ import annotations

from datetime import date, timedelta
from html import escape

import numpy as np
import pandas as pd
import streamlit as st

from database import authenticate_user, create_database, create_user
from data_loader import load_dashboard_data


st.set_page_config(
    page_title="CareSignal | Readmission Analytics",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data
def build_demo_data(rows: int = 720, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    diagnoses = np.array(
        ["Heart Failure", "COPD", "Diabetes", "Pneumonia", "Renal Disease", "Hypertension"]
    )
    diagnosis_weights = np.array([0.18, 0.15, 0.22, 0.16, 0.12, 0.17])
    payers = np.array(["Medicare", "Medicaid", "Commercial", "Self-pay"])
    discharge_types = np.array(["Home", "Home Health", "Skilled Nursing", "Rehabilitation"])
    facilities = np.array(["North Medical", "Central Hospital", "West Community"])

    end = date.today()
    start = end - timedelta(days=364)
    encounter_dates = pd.to_datetime(
        [start + timedelta(days=int(x)) for x in rng.integers(0, 365, rows)]
    )
    age = np.clip(rng.normal(64, 15, rows).round(), 18, 94).astype(int)
    diagnosis = rng.choice(diagnoses, rows, p=diagnosis_weights)
    previous_admissions = np.clip(rng.poisson(1.15, rows), 0, 7)
    chronic_conditions = np.clip(rng.poisson(2.3, rows) + 1, 1, 8)
    length_of_stay = np.clip(
        rng.gamma(2.2, 2.1, rows) + (diagnosis == "Heart Failure") * 1.3, 1, 21
    ).round().astype(int)
    emergency_admit = rng.random(rows) < 0.57
    missed_followup = rng.random(rows) < (
        0.12 + 0.05 * previous_admissions + 0.04 * (rng.choice(payers, rows) == "Self-pay")
    )
    discharge = rng.choice(discharge_types, rows, p=[0.56, 0.18, 0.17, 0.09])

    logit = (
        -4.15
        + 0.022 * (age - 50)
        + 0.42 * previous_admissions
        + 0.22 * (chronic_conditions - 1)
        + 0.055 * length_of_stay
        + 0.50 * emergency_admit
        + 0.88 * missed_followup
        + 0.32 * np.isin(diagnosis, ["Heart Failure", "COPD", "Renal Disease"])
        + 0.30 * np.isin(discharge, ["Skilled Nursing", "Rehabilitation"])
    )
    risk_probability = 1 / (1 + np.exp(-logit))
    readmitted = rng.random(rows) < risk_probability

    risk_score = np.clip(
        (
            100
            * (
                1
                / (
                    1
                    + np.exp(
                        -(
                            logit
                            + 0.35 * rng.normal(size=rows)
                            + 0.35
                        )
                    )
                )
            )
        ).round(),
        3,
        98,
    ).astype(int)
    risk_band = pd.cut(
        risk_score,
        bins=[-1, 34, 64, 100],
        labels=["Low", "Medium", "High"],
    ).astype(str)

    return (
        pd.DataFrame(
            {
                "patient_id": [f"PT-{10001 + i}" for i in range(rows)],
                "encounter_date": encounter_dates,
                "facility": rng.choice(facilities, rows, p=[0.39, 0.36, 0.25]),
                "age": age,
                "sex": rng.choice(["Female", "Male"], rows, p=[0.52, 0.48]),
                "payer": rng.choice(payers, rows, p=[0.46, 0.23, 0.26, 0.05]),
                "primary_diagnosis": diagnosis,
                "length_of_stay": length_of_stay,
                "previous_admissions": previous_admissions,
                "chronic_conditions": chronic_conditions,
                "emergency_admit": emergency_admit,
                "missed_followup": missed_followup,
                "discharge_disposition": discharge,
                "risk_score": risk_score,
                "risk_band": risk_band,
                "readmitted_30d": readmitted,
            }
        )
        .sort_values("encounter_date")
        .reset_index(drop=True)
    )


def pct(value: float) -> str:
    return f"{value:.1%}"


def risk_badge(value: str) -> str:
    return {"High": "🔴 High", "Medium": "🟠 Medium", "Low": "🟢 Low"}[value]


def render_bar_chart(
    values: pd.Series,
    *,
    percent: bool = False,
    color: str = "#167d8d",
) -> None:
    """Render a dependency-free horizontal bar chart that survives browser cache changes."""
    clean = values.astype(float)
    maximum = max(float(clean.max()), 0.001)
    rows = []
    for label, value in clean.items():
        width = max(2, (float(value) / maximum) * 100)
        shown = f"{value:.1%}" if percent else f"{value:,.0f}"
        rows.append(
            f"""
            <div class="bar-row">
              <div class="bar-meta"><span>{escape(str(label))}</span><b>{shown}</b></div>
              <div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%;background:{color}"></div></div>
            </div>
            """
        )
    st.markdown(f'<div class="viz-card">{"".join(rows)}</div>', unsafe_allow_html=True)


def render_line_chart(
    values: pd.Series,
    *,
    percent: bool = False,
    color: str = "#167d8d",
) -> None:
    """Render an accessible responsive SVG line chart without a dynamic JS chart bundle."""
    clean = values.astype(float)
    if clean.empty:
        st.info("No chart data is available for the selected filters.")
        return
    width, height = 760, 255
    left, right, top, bottom = 48, 18, 20, 42
    plot_w, plot_h = width - left - right, height - top - bottom
    low = min(0.0, float(clean.min()) * 0.85)
    high = max(float(clean.max()) * 1.12, 0.01)
    span = high - low
    count = len(clean)
    points = []
    labels = []
    circles = []
    for i, (label, value) in enumerate(clean.items()):
        x = left + (plot_w * i / max(count - 1, 1))
        y = top + plot_h - ((float(value) - low) / span * plot_h)
        points.append(f"{x:.1f},{y:.1f}")
        if i == 0 or i == count - 1 or i % max(1, count // 5) == 0:
            if isinstance(label, (pd.Timestamp, date)):
                label_text = pd.Timestamp(label).strftime("%b %y")
            else:
                label_text = str(label)
            labels.append(
                f'<text x="{x:.1f}" y="{height - 13}" text-anchor="middle">{escape(label_text)}</text>'
            )
        shown = f"{value:.1%}" if percent else f"{value:.1f}"
        circles.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4"><title>{escape(str(label))}: {shown}</title></circle>'
        )
    grid = []
    for i in range(5):
        y = top + (plot_h * i / 4)
        value = high - (span * i / 4)
        shown = f"{value:.0%}" if percent else f"{value:.0f}"
        grid.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" />'
            f'<text x="{left-9}" y="{y+4:.1f}" text-anchor="end">{shown}</text>'
        )
    st.markdown(
        f"""
        <div class="viz-card line-viz">
          <svg viewBox="0 0 {width} {height}" role="img" aria-label="Trend chart">
            <g class="chart-grid">{"".join(grid)}</g>
            <polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="4"
              stroke-linecap="round" stroke-linejoin="round"/>
            <g class="chart-points" fill="{color}">{"".join(circles)}</g>
            <g class="chart-labels">{"".join(labels)}</g>
          </svg>
        </div>
        """,
        unsafe_allow_html=True,
    )


def login_screen() -> None:
    left, center, right = st.columns([1, 1.25, 1])
    with center:
        st.markdown(
            """
            <div class="auth-brand">
              <div class="auth-icon">✚</div>
              <div class="auth-eyebrow">HEALTHCARE INTELLIGENCE</div>
              <div class="auth-title">CareSignal Analytics</div>
              <div class="auth-subtitle">Secure readmission risk and population insights</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        sign_in, register = st.tabs(["Sign in", "Create account"])
        with sign_in:
            with st.form("login_form"):
                username = st.text_input("Username", placeholder="Enter your username")
                password = st.text_input("Password", type="password", placeholder="Enter your password")
                submitted = st.form_submit_button("Sign in securely", width="stretch")
            if submitted:
                user = authenticate_user(username, password)
                if user:
                    st.session_state.user = user
                    st.rerun()
                st.error("Incorrect username or password.")
            st.markdown(
                """
                <div class="demo-access">
                  <span>DEMO ACCESS</span>
                  <b>admin</b> &nbsp; / &nbsp; <b>CareSignal2026!</b>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with register:
            with st.form("register_form"):
                display_name = st.text_input("Full name", placeholder="Your full name")
                new_username = st.text_input("Choose a username", placeholder="Minimum 3 characters")
                new_password = st.text_input(
                    "Choose a password", type="password", help="Minimum 8 characters"
                )
                confirm_password = st.text_input("Confirm password", type="password")
                submitted = st.form_submit_button("Create secure account", width="stretch")
            if submitted:
                if new_password != confirm_password:
                    st.error("Passwords do not match.")
                else:
                    ok, message = create_user(new_username, display_name, new_password)
                    (st.success if ok else st.error)(message)


st.markdown(
    """
    <style>
      html, body, .stApp, [data-testid="stAppViewContainer"] {
        background: #f4f7fb !important; color: #17334f !important;
      }
      [data-testid="stAppViewContainer"] .main .block-container {
        padding-top: 4.5rem; padding-bottom: 3rem; max-width: 1280px;
      }
      [data-testid="stAppViewContainer"] p,
      [data-testid="stAppViewContainer"] label,
      [data-testid="stAppViewContainer"] h1,
      [data-testid="stAppViewContainer"] h2,
      [data-testid="stAppViewContainer"] h3,
      [data-testid="stAppViewContainer"] [data-testid="stMetricLabel"],
      [data-testid="stAppViewContainer"] [data-testid="stMetricValue"] {
        color: #17334f !important;
      }
      [data-testid="stSidebar"] { background: #10243e; }
      [data-testid="stSidebar"] h1,
      [data-testid="stSidebar"] h2,
      [data-testid="stSidebar"] h3,
      [data-testid="stSidebar"] p,
      [data-testid="stSidebar"] label,
      [data-testid="stSidebar"] span {
        color: #f4f8ff !important;
      }
      [data-testid="stSidebar"] [data-baseweb="select"] > div {
        background: #17304f !important; border-color: #36516e !important;
        border-radius: 10px !important; min-height: 44px;
      }
      [data-testid="stSidebar"] [data-baseweb="tag"] {
        background: #167d8d !important; border-radius: 6px !important;
      }
      [data-testid="stSidebar"] [data-baseweb="tag"] span {
        color: white !important; font-size: .82rem !important;
      }
      [data-testid="stSidebar"] [data-baseweb="slider"] div[role="slider"] {
        background: #39b8c3 !important; border-color: white !important;
      }
      [data-testid="stSidebar"] hr { border-color: #294662; }
      .sidebar-user {
        background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.12);
        border-radius: 12px; padding: .85rem .9rem; margin: .4rem 0 .8rem;
      }
      .sidebar-user .name { color: white; font-weight: 700; font-size: .95rem; }
      .sidebar-user .role { color: #a9c6d5 !important; font-size: .78rem; margin-top: .15rem; }
      .hero {
        padding: 1.5rem 1.7rem; border-radius: 18px;
        background: linear-gradient(120deg, #123c69, #167d8d);
        color: white; margin-bottom: 1rem;
        box-shadow: 0 10px 28px rgba(18,60,105,.16);
      }
      .hero h1 { margin: 0; font-size: 2.05rem; color: white !important; }
      .hero p { margin: .42rem 0 0; color: #dceff4 !important; }
      div[data-testid="stMetric"] {
        background: white; border: 1px solid #e4eaf2; border-radius: 14px;
        padding: 1rem 1.05rem; box-shadow: 0 4px 14px rgba(18,36,62,.05);
      }
      div[data-testid="stMetricLabel"] { color: #52657a; }
      div[data-testid="stMetricValue"] { color: #153450; font-weight: 750; }
      .section-note {
        background: #e9f4f7; border-left: 4px solid #167d8d;
        padding: .75rem 1rem; border-radius: 6px; color: #24485a;
      }
      .patient-card {
        background: white; border: 1px solid #e3eaf1; border-radius: 14px;
        padding: 1rem 1.1rem; margin-bottom: .6rem;
      }
      h2, h3 { color: #17334f !important; }
      .stTabs [data-baseweb="tab-list"] { gap: .5rem; }
      .stTabs [data-baseweb="tab"] {
        background: white; border: 1px solid #e0e7ef; border-radius: 9px;
        padding: .55rem 1rem; color: #405a72 !important;
      }
      .stTabs [aria-selected="true"] { color: #c43d4f !important; font-weight: 700; }
      .viz-card {
        background: #fff; border: 1px solid #e2e9f0; border-radius: 14px;
        padding: 1.1rem 1.2rem; min-height: 255px;
        box-shadow: 0 4px 14px rgba(18,36,62,.05);
      }
      .bar-row { margin: .58rem 0 1rem; }
      .bar-meta { display: flex; justify-content: space-between; color: #294760; font-size: .92rem; }
      .bar-track { height: 12px; background: #edf1f5; border-radius: 10px; overflow: hidden; margin-top: .4rem; }
      .bar-fill { height: 100%; border-radius: 10px; }
      .line-viz { padding: .6rem .8rem; }
      .line-viz svg { display: block; width: 100%; height: 270px; }
      .chart-grid line { stroke: #e5ebf1; stroke-width: 1; }
      .chart-grid text, .chart-labels text { fill: #657b8f; font: 12px sans-serif; }
      button, [data-testid="stDownloadButton"] button { border-radius: 9px !important; }
      .auth-brand { text-align: center; margin: 1rem 0 1.3rem; }
      .auth-icon {
        width: 58px; height: 58px; margin: 0 auto .8rem; display: grid; place-items: center;
        border-radius: 16px; background: linear-gradient(135deg,#174a75,#168899);
        color: white; font-size: 1.8rem; box-shadow: 0 10px 24px rgba(23,74,117,.2);
      }
      .auth-eyebrow { color: #167d8d; font-size: .7rem; letter-spacing: .16em; font-weight: 800; }
      .auth-title { color: #17334f; font-size: 1.85rem; font-weight: 780; margin-top: .25rem; }
      .auth-subtitle { color: #667d90; font-size: .92rem; margin-top: .2rem; }
      .demo-access {
        background: #e9f4f7; color: #365568; border: 1px solid #d2e8ed;
        padding: .8rem; text-align: center; border-radius: 9px; margin-top: .7rem;
      }
      .demo-access span { color: #167d8d; font-size: .68rem; font-weight: 800; margin-right: .7rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

create_database()
if "user" not in st.session_state:
    login_screen()
    st.stop()

data = load_dashboard_data(build_demo_data())

with st.sidebar:
    st.title("CareSignal")
    st.caption("30-Day Readmission Intelligence")
    st.divider()
    user = st.session_state.user
    st.markdown(
        f"""
        <div class="sidebar-user">
          <div class="name">{escape(user['display_name'])}</div>
          <div class="role">{escape(user['role'])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Sign out", icon=":material/logout:", width="stretch"):
        del st.session_state.user
        st.rerun()
    st.divider()
    st.subheader("Population filters")
    selected_facilities = st.multiselect(
        "Facility", sorted(data["facility"].unique()), default=sorted(data["facility"].unique())
    )
    selected_diagnoses = st.multiselect(
        "Primary diagnosis",
        sorted(data["primary_diagnosis"].unique()),
        default=sorted(data["primary_diagnosis"].unique()),
    )
    selected_bands = st.multiselect(
        "Risk band", ["High", "Medium", "Low"], default=["High", "Medium", "Low"]
    )
    age_range = st.slider("Patient age", 18, 94, (18, 94))
    st.divider()
    st.caption("Portfolio demonstration using synthetic patient data. Not for clinical use.")

filtered = data[
    data["facility"].isin(selected_facilities)
    & data["primary_diagnosis"].isin(selected_diagnoses)
    & data["risk_band"].isin(selected_bands)
    & data["age"].between(*age_range)
].copy()

st.markdown(
    """
    <div class="hero">
      <h1>Healthcare Patient Risk & Readmission Analysis</h1>
      <p>Population surveillance, risk stratification, and care-management prioritization in one operational view.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if filtered.empty:
    st.warning("No encounters match the selected filters. Broaden the filters in the sidebar.")
    st.stop()

readmission_rate = filtered["readmitted_30d"].mean()
high_risk = (filtered["risk_band"] == "High").sum()
avg_los = filtered["length_of_stay"].mean()
followup_gap = filtered["missed_followup"].mean()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Encounters", f"{len(filtered):,}", help="Filtered inpatient encounters")
col2.metric("30-day readmission", pct(readmission_rate), help="Observed synthetic outcome rate")
col3.metric("High-risk patients", f"{high_risk:,}", help="Risk score of 65 or greater")
col4.metric("Average length of stay", f"{avg_los:.1f} days")

overview, risk_queue, population, patient_view, methodology = st.tabs(
    ["Executive overview", "Risk queue", "Population analysis", "Patient explorer", "Methodology"]
)

with overview:
    left, right = st.columns([1.55, 1])
    with left:
        st.subheader("Monthly readmission trend")
        monthly = (
            filtered.assign(month=filtered["encounter_date"].dt.to_period("M").dt.to_timestamp())
            .groupby("month", as_index=False)
            .agg(encounters=("patient_id", "size"), readmissions=("readmitted_30d", "sum"))
        )
        monthly["readmission_rate"] = monthly["readmissions"] / monthly["encounters"]
        render_line_chart(monthly.set_index("month")["readmission_rate"], percent=True)
    with right:
        st.subheader("Risk distribution")
        distribution = (
            filtered["risk_band"]
            .value_counts()
            .reindex(["High", "Medium", "Low"], fill_value=0)
            .rename("Patients")
        )
        render_bar_chart(distribution)

    left, right = st.columns(2)
    with left:
        st.subheader("Readmission rate by diagnosis")
        diagnosis_summary = (
            filtered.groupby("primary_diagnosis")
            .agg(
                Encounters=("patient_id", "size"),
                Readmission_Rate=("readmitted_30d", "mean"),
                Average_Risk=("risk_score", "mean"),
            )
            .sort_values("Readmission_Rate", ascending=False)
        )
        st.dataframe(
            diagnosis_summary.style.format(
                {"Readmission_Rate": "{:.1%}", "Average_Risk": "{:.1f}"}
            ),
            width="stretch",
        )
    with right:
        st.subheader("Operational signals")
        st.metric("Missed follow-up", pct(followup_gap))
        st.metric(
            "Emergency admissions",
            pct(filtered["emergency_admit"].mean()),
        )
        top_diagnosis = diagnosis_summary.index[0]
        st.markdown(
            f'<div class="section-note"><b>Priority signal:</b> {top_diagnosis} has the '
            f'highest observed readmission rate in the filtered population. Review high-risk '
            f'patients with missed follow-up first.</div>',
            unsafe_allow_html=True,
        )

with risk_queue:
    st.subheader("Care-management priority queue")
    st.caption("Ranked by risk score. Use filters to focus the worklist by facility or diagnosis.")
    queue = filtered.sort_values(
        ["risk_score", "previous_admissions", "missed_followup"], ascending=False
    ).copy()
    queue["Risk"] = queue["risk_band"].map(risk_badge)
    queue["Follow-up"] = queue["missed_followup"].map({True: "Missed", False: "Scheduled"})
    display_queue = queue[
        [
            "patient_id",
            "Risk",
            "risk_score",
            "primary_diagnosis",
            "age",
            "previous_admissions",
            "length_of_stay",
            "Follow-up",
            "facility",
        ]
    ].rename(
        columns={
            "patient_id": "Patient",
            "risk_score": "Risk score",
            "primary_diagnosis": "Diagnosis",
            "age": "Age",
            "previous_admissions": "Prior admits",
            "length_of_stay": "LOS",
            "facility": "Facility",
        }
    )
    st.dataframe(display_queue, width="stretch", hide_index=True, height=460)
    st.download_button(
        "Download filtered risk queue",
        display_queue.to_csv(index=False).encode("utf-8"),
        "readmission_risk_queue.csv",
        "text/csv",
    )

with population:
    left, right = st.columns(2)
    with left:
        st.subheader("Readmission by discharge disposition")
        discharge_summary = (
            filtered.groupby("discharge_disposition")["readmitted_30d"]
            .mean()
            .sort_values(ascending=False)
            .rename("Readmission rate")
        )
        render_bar_chart(discharge_summary, percent=True, color="#235b91")
    with right:
        st.subheader("Risk by prior admission count")
        prior_summary = (
            filtered.groupby("previous_admissions")["risk_score"].mean().rename("Average risk score")
        )
        render_line_chart(prior_summary, color="#235b91")

    st.subheader("Facility performance comparison")
    facility_summary = (
        filtered.groupby("facility")
        .agg(
            Encounters=("patient_id", "size"),
            Readmissions=("readmitted_30d", "sum"),
            Readmission_Rate=("readmitted_30d", "mean"),
            High_Risk=("risk_band", lambda s: (s == "High").sum()),
            Average_LOS=("length_of_stay", "mean"),
        )
        .sort_values("Readmission_Rate", ascending=False)
    )
    st.dataframe(
        facility_summary.style.format(
            {"Readmission_Rate": "{:.1%}", "Average_LOS": "{:.1f}"}
        ),
        width="stretch",
    )

with patient_view:
    st.subheader("Patient risk profile")
    patient_ids = (
        filtered.sort_values("risk_score", ascending=False)["patient_id"]
        .drop_duplicates()
        .tolist()
    )
    selected_patient = st.selectbox("Select patient", patient_ids)
    patient = filtered.loc[filtered["patient_id"] == selected_patient].iloc[0]
    st.markdown(
        f"""
        <div class="patient-card">
          <b>{patient['patient_id']}</b> &nbsp; • &nbsp; {patient['age']} years &nbsp; • &nbsp;
          {patient['sex']} &nbsp; • &nbsp; {patient['facility']}<br>
          <span style="color:#587087">{patient['primary_diagnosis']} ·
          Discharged to {patient['discharge_disposition']}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Risk score", f"{patient['risk_score']}/100")
    p2.metric("Risk band", risk_badge(patient["risk_band"]))
    p3.metric("Prior admissions", int(patient["previous_admissions"]))
    p4.metric("Length of stay", f"{patient['length_of_stay']} days")

    factors = pd.DataFrame(
        {
            "Risk factor": [
                "Age 70+",
                "Two or more prior admissions",
                "Three or more chronic conditions",
                "Emergency admission",
                "Missed follow-up",
                "Length of stay 7+ days",
            ],
            "Present": [
                patient["age"] >= 70,
                patient["previous_admissions"] >= 2,
                patient["chronic_conditions"] >= 3,
                patient["emergency_admit"],
                patient["missed_followup"],
                patient["length_of_stay"] >= 7,
            ],
        }
    )
    factors["Status"] = factors["Present"].map({True: "⚠️ Present", False: "✓ Not present"})
    st.dataframe(factors[["Risk factor", "Status"]], width="stretch", hide_index=True)

with methodology:
    st.subheader("Analytical approach")
    st.markdown(
        """
        This portfolio dashboard loads the Data Engineering pipeline's Gold extract when it is
        available and otherwise uses a reproducible synthetic fallback. The risk score is generated
        from clinically plausible operational factors: age, previous
        admissions, chronic-condition count, length of stay, emergency admission, follow-up
        status, diagnosis group, and discharge disposition.

        **Workflow demonstrated**

        1. Generate a deterministic synthetic Bronze extract with Python and pandas.
        2. Validate and transform records into Silver Parquet with PySpark.
        3. Build Gold fact, dimension, mart, and dashboard tables.
        4. Segment patients into low, medium, and high-risk cohorts.
        5. Monitor trends, compare facilities, and export the filtered work queue.

        **Important:** All records are synthetic. The score is an educational demonstration,
        not a validated clinical model and not intended to guide patient care.
        """
    )
    st.download_button(
        "Download complete synthetic dataset",
        data.to_csv(index=False).encode("utf-8"),
        "synthetic_readmission_encounters.csv",
        "text/csv",
    )
