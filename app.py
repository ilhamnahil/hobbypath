"""HobbyPath – learn a new hobby as an adult, one small step at a time.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import os
from datetime import date, datetime

import pandas as pd
import streamlit as st

from hobbypath import db, planner, stats

st.set_page_config(page_title="HobbyPath", page_icon="🌱", layout="wide")

store = db.Store(os.getenv("HOBBYPATH_DB", "hobbypath.db"))

LEVELS = ["Complete beginner", "Tried it a few times", "Returning after a break", "Some experience"]
IDEAS = ["Guitar", "Watercolour painting", "Bouldering", "Spanish", "Sourdough baking",
         "Chess", "Photography", "Running", "Pottery", "Knitting"]


# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------
with st.sidebar:
    st.title("🌱 HobbyPath")
    st.caption("Small steps, real progress.")

    hobbies = store.hobbies()
    options = {f"{h['name']}": h["id"] for h in hobbies}
    if "selected" not in st.session_state:
        st.session_state.selected = hobbies[0]["id"] if hobbies else None

    if st.button("➕ Start a new hobby", use_container_width=True):
        st.session_state.selected = None
        st.rerun()

    if options:
        st.subheader("My hobbies")
        for name, hid in options.items():
            kind = "primary" if st.session_state.selected == hid else "secondary"
            if st.button(name, key=f"h{hid}", use_container_width=True, type=kind):
                st.session_state.selected = hid
                st.rerun()

    st.divider()
    with st.expander("AI settings"):
        api_key = st.text_input("Anthropic API key (optional)", type="password",
                                value=os.getenv("ANTHROPIC_API_KEY", ""),
                                help="Without a key HobbyPath uses its built-in offline planner.")
        st.caption("AI mode: **on**" if api_key else "AI mode: **offline planner**")


# --------------------------------------------------------------------------
# New hobby
# --------------------------------------------------------------------------
def new_hobby_page() -> None:
    st.header("What do you want to learn?")
    st.write("Tell HobbyPath your goal and how much time you really have. "
             "You'll get a week-by-week plan with one milestone per week.")

    with st.form("new"):
        c1, c2 = st.columns(2)
        hobby = c1.text_input("Hobby", placeholder="e.g. " + ", ".join(IDEAS[:3]))
        level = c2.selectbox("Your level", LEVELS)
        goal = st.text_input("Goal", placeholder="e.g. Play three songs at a friend's birthday")
        c3, c4 = st.columns(2)
        hours = c3.slider("Hours per week", 0.5, 10.0, 2.5, 0.5)
        weeks = c4.slider("Plan length (weeks)", 2, 12, 4)
        notes = st.text_area("Anything else? (optional)",
                             placeholder="Budget, equipment you already own, evenings only…")
        submitted = st.form_submit_button("Create my plan", type="primary")

    if submitted:
        if not hobby.strip() or not goal.strip():
            st.error("Please enter a hobby and a goal.")
            return
        req = planner.PlanRequest(hobby.strip(), goal.strip(), level, hours, weeks, notes.strip())
        with st.spinner("Building your plan…"):
            try:
                plan, source = planner.generate_plan(req, api_key or None)
            except Exception as e:  # network/model errors -> offline fallback
                st.warning(f"AI planner unavailable ({e}). Using the offline planner instead.")
                plan, source = planner.generate_offline(req), "offline"
        hid = store.add_hobby(req.hobby, req.goal, level, hours, weeks, plan, source)
        st.session_state.selected = hid
        st.rerun()


# --------------------------------------------------------------------------
# Hobby dashboard
# --------------------------------------------------------------------------
def hobby_page(hid: int) -> None:
    hobby = store.hobby(hid)
    if hobby is None:
        st.session_state.selected = None
        st.rerun()
    tasks = [dict(t) for t in store.tasks(hid)]
    sessions = [dict(s) for s in store.sessions(hid)]
    days = [date.fromisoformat(s["day"]) for s in sessions]
    start = datetime.fromisoformat(hobby["created_at"]).date()

    st.header(f"{hobby['name']}")
    st.caption(f"🎯 {hobby['goal']}  ·  {hobby['level']}  ·  {hobby['hours_per_week']:g} h/week  ·  "
               f"plan by {'AI' if hobby['source'] == 'ai' else 'offline planner'}")
    if hobby["summary"]:
        st.write(hobby["summary"])

    progress = stats.completion(tasks)
    cur, longest = stats.current_streak(days), stats.longest_streak(days)
    week_now = stats.current_week(tasks)
    mins = stats.minutes_per_week(sessions, start)
    this_week = mins.get(max(1, (date.today() - start).days // 7 + 1), 0)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Plan completed", f"{progress:.0%}")
    m2.metric("Current streak", f"{cur} day{'s' if cur != 1 else ''}")
    m3.metric("Longest streak", f"{longest} day{'s' if longest != 1 else ''}")
    goal_min = int(hobby["hours_per_week"] * 60)
    m4.metric(f"This week (goal {goal_min} min)", f"{this_week} min")
    st.progress(progress)

    badges = stats.earned_badges(longest)
    if badges:
        st.write("**Badges:** " + "  ".join(badges))

    plan_tab, log_tab = st.tabs(["📋 Plan", "⏱️ Practice log"])

    with plan_tab:
        n_weeks = max(t["week"] for t in tasks)
        labels = {w: f"Week {w}" + (" ✓" if all(t["done"] for t in tasks if t["week"] == w) else "")
                  for w in range(1, n_weeks + 1)}
        w = st.segmented_control("Week", list(labels), default=week_now, format_func=labels.get,
                                 key=f"week_{hid}", label_visibility="collapsed") or week_now
        wk = [t for t in tasks if t["week"] == w]
        done = sum(t["done"] for t in wk)
        st.caption(f"{done}/{len(wk)} done · {sum(t['minutes'] for t in wk)} min planned · 🏁 = weekly milestone")
        for t in wk:
            label = ("🏁 " if t["is_milestone"] else "") + f"**{t['title']}** · {t['minutes']} min"
            checked = st.checkbox(label, value=bool(t["done"]), key=f"t{t['id']}")
            if t["details"]:
                st.caption(t["details"])
            if checked != bool(t["done"]):
                store.set_task_done(t["id"], checked)
                if checked and t["is_milestone"]:
                    st.session_state.celebrate = True
                st.rerun()
        if st.session_state.pop("celebrate", False):
            st.balloons()
            st.success("Milestone reached! 🎉")

    with log_tab:
        with st.form("log", clear_on_submit=True):
            c1, c2 = st.columns([1, 1])
            day = c1.date_input("Day", value=date.today(), max_value=date.today())
            minutes = c2.number_input("Minutes", 5, 600, 30, 5)
            note = st.text_input("What did you do? (optional)")
            if st.form_submit_button("Log practice", type="primary"):
                store.log_session(hid, day, int(minutes), note)
                st.toast("Practice logged. Nice work!")
                st.rerun()

        if sessions:
            df = pd.DataFrame(sessions)
            df["day"] = pd.to_datetime(df["day"])
            daily = df.groupby(df["day"].dt.strftime("%d %b"), sort=False)["minutes"].sum().iloc[::-1]
            st.bar_chart(daily, y_label="minutes", x_label="", color="#2E8B57")
            st.dataframe(df[["day", "minutes", "note"]].assign(day=df["day"].dt.date),
                         hide_index=True, use_container_width=True)
        else:
            st.info("No practice logged yet. Even 10 minutes counts.")

    with st.expander("Danger zone"):
        if st.button("Delete this hobby", type="secondary"):
            store.delete_hobby(hid)
            st.session_state.selected = None
            st.rerun()


if st.session_state.selected is None:
    new_hobby_page()
else:
    hobby_page(st.session_state.selected)
