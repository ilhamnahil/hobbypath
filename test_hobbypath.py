from datetime import date, timedelta

import pytest

from hobbypath import db, planner, stats


# ---------------------------------------------------------------- planner
def req(**kw):
    base = dict(hobby="Guitar", goal="Play 3 songs", hours_per_week=2, weeks=4)
    base.update(kw)
    return planner.PlanRequest(**base)


def test_offline_plan_has_requested_weeks_and_respects_budget():
    r = req(weeks=6, hours_per_week=1.5)
    plan = planner.generate_offline(r)
    assert len(plan["weeks"]) == 6
    for wk in plan["weeks"]:
        assert sum(t["minutes"] for t in wk["tasks"]) <= r.minutes_per_week
        assert sum(t["milestone"] for t in wk["tasks"]) >= 1


def test_extract_json_handles_fences_and_prose():
    raw = 'Sure! ```json\n{"summary": "x", "weeks": []}\n```'
    assert planner.extract_json(raw)["summary"] == "x"
    assert planner.extract_json('Here: {"a": 1} thanks')["a"] == 1
    with pytest.raises(planner.PlanError):
        planner.extract_json("no json here")


def test_validate_scales_overbudget_week_and_adds_milestone():
    r = req(hours_per_week=1, weeks=1)  # 60 min budget
    plan = {"weeks": [{"week": 1, "tasks": [{"title": "a", "minutes": 60}, {"title": "b", "minutes": 60}]}]}
    out = planner.validate_plan(plan, r)
    tasks = out["weeks"][0]["tasks"]
    assert sum(t["minutes"] for t in tasks) <= 60
    assert tasks[-1]["milestone"] is True


def test_validate_rejects_empty_plan():
    with pytest.raises(planner.PlanError):
        planner.validate_plan({"weeks": []}, req())


def test_generate_plan_without_key_is_offline(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _, source = planner.generate_plan(req())
    assert source == "offline"


# ---------------------------------------------------------------- stats
def test_streaks():
    t = date(2026, 10, 16)
    days = [t, t - timedelta(1), t - timedelta(2), t - timedelta(5)]
    assert stats.current_streak(days, today=t) == 3
    # streak survives until you practise today
    assert stats.current_streak([t - timedelta(1)], today=t) == 1
    assert stats.current_streak([t - timedelta(2)], today=t) == 0
    assert stats.longest_streak(days) == 3


def test_completion_and_current_week():
    tasks = [{"week": 1, "done": 1}, {"week": 1, "done": 1}, {"week": 2, "done": 0}]
    assert stats.completion(tasks) == pytest.approx(2 / 3)
    assert stats.current_week(tasks) == 2
    assert stats.earned_badges(7)[-1].endswith("One full week")


# ---------------------------------------------------------------- db
def test_store_roundtrip(tmp_path):
    s = db.Store(tmp_path / "t.db")
    plan = planner.generate_offline(req(weeks=2))
    hid = s.add_hobby("Guitar", "Play 3 songs", "Complete beginner", 2, 2, plan)
    tasks = s.tasks(hid)
    assert len(tasks) == sum(len(w["tasks"]) for w in plan["weeks"])
    s.set_task_done(tasks[0]["id"], True)
    assert s.tasks(hid)[0]["done"] == 1
    s.log_session(hid, date.today(), 25, "chords")
    assert s.sessions(hid)[0]["minutes"] == 25
    s.delete_hobby(hid)
    assert s.hobby(hid) is None and s.tasks(hid) == []


# ---------------------------------------------------------------- LLM path (mocked)
def test_llm_retries_once_after_bad_json(monkeypatch):
    import sys, types, json as _json

    good = {"summary": "s", "weeks": [{"week": 1, "focus": "f",
             "tasks": [{"title": "t", "details": "d", "minutes": 30, "milestone": True}]}]}
    answers = iter(["sorry, no json", "```json\n" + _json.dumps(good) + "\n```"])
    calls = []

    class Block:
        type = "text"
        def __init__(self, text): self.text = text

    class Messages:
        def create(self, **kw):
            calls.append(kw)
            return types.SimpleNamespace(content=[Block(next(answers))])

    class FakeClient:
        def __init__(self, api_key): self.messages = Messages()

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=FakeClient))
    plan = planner.generate_with_llm(req(weeks=1), api_key="test")
    assert plan["weeks"][0]["tasks"][0]["title"] == "t"
    assert len(calls) == 2 and "not valid" in calls[1]["messages"][-1]["content"]
