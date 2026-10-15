"""Turns a hobby goal into a week-by-week learning plan.

Uses an LLM (Anthropic Claude) when an API key is available and falls back to a
rule-based planner otherwise, so the app always works offline too.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

DEFAULT_MODEL = os.getenv("HOBBYPATH_MODEL", "claude-sonnet-5-5")

SYSTEM_PROMPT = """You are HobbyPath, a patient coach who helps busy adults learn a new hobby.
Design realistic plans for people with jobs and families: short sessions, early wins,
no expensive gear up front, and clear milestones that build confidence.

Rules:
- Respect the weekly time budget. The sum of task minutes per week must not exceed it.
- 2 to 4 tasks per week. Each task is concrete and doable in one sitting.
- Mark exactly one task per week as the milestone: a small, visible result.
- Adapt to the learner's level. Beginners get fundamentals and free resources first.
- Write in plain, encouraging language. No filler.

Answer with JSON only, no markdown, matching exactly:
{"summary": str,
 "weeks": [{"week": int, "focus": str,
            "tasks": [{"title": str, "details": str, "minutes": int, "milestone": bool}]}]}"""

USER_TEMPLATE = """Hobby: {hobby}
Goal: {goal}
Current level: {level}
Time available: {hours} hours per week ({minutes} minutes)
Plan length: {weeks} weeks
Extra context: {notes}"""


class PlanError(ValueError):
    pass


@dataclass
class PlanRequest:
    hobby: str
    goal: str
    level: str = "Complete beginner"
    hours_per_week: float = 3.0
    weeks: int = 4
    notes: str = ""

    @property
    def minutes_per_week(self) -> int:
        return int(round(self.hours_per_week * 60))

    def to_prompt(self) -> str:
        return USER_TEMPLATE.format(hobby=self.hobby, goal=self.goal, level=self.level,
                                    hours=self.hours_per_week, minutes=self.minutes_per_week,
                                    weeks=self.weeks, notes=self.notes or "none")


# --------------------------------------------------------------------------
# Parsing & validation
# --------------------------------------------------------------------------
def extract_json(text: str) -> dict:
    """Parse the model's answer, tolerating stray ```json fences or prose."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise PlanError("No JSON object found in model output")
        text = text[start:end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise PlanError(f"Invalid JSON: {e}") from e


def validate_plan(plan: dict, req: PlanRequest) -> dict:
    """Normalise the plan and enforce the weekly time budget."""
    if not isinstance(plan, dict) or not isinstance(plan.get("weeks"), list) or not plan["weeks"]:
        raise PlanError("Plan must contain a non-empty 'weeks' list")
    budget = req.minutes_per_week
    weeks = []
    for i, wk in enumerate(plan["weeks"][: req.weeks], start=1):
        tasks = [t for t in wk.get("tasks", []) if isinstance(t, dict) and t.get("title")]
        if not tasks:
            raise PlanError(f"Week {i} has no tasks")
        for t in tasks:
            t["minutes"] = max(5, int(t.get("minutes") or 0))
            t["details"] = str(t.get("details", ""))
            t["milestone"] = bool(t.get("milestone", False))
        total = sum(t["minutes"] for t in tasks)
        if total > budget:  # scale down rather than reject
            for t in tasks:
                t["minutes"] = max(5, int(t["minutes"] * budget / total))
        if not any(t["milestone"] for t in tasks):
            tasks[-1]["milestone"] = True
        weeks.append({"week": i, "focus": str(wk.get("focus", f"Week {i}")), "tasks": tasks})
    return {"summary": str(plan.get("summary", "")), "weeks": weeks}


# --------------------------------------------------------------------------
# Generators
# --------------------------------------------------------------------------
def generate_with_llm(req: PlanRequest, api_key: str, model: str = DEFAULT_MODEL) -> dict:
    import anthropic  # imported lazily so the offline mode needs no SDK

    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": req.to_prompt()}]
    last_err: Exception | None = None
    for _ in range(2):  # one retry with the error fed back to the model
        resp = client.messages.create(model=model, max_tokens=4000, system=SYSTEM_PROMPT,
                                      messages=messages)
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        try:
            return validate_plan(extract_json(text), req)
        except PlanError as e:
            last_err = e
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": f"That was not valid: {e}. Reply with the JSON only."}]
    raise PlanError(f"Model did not return a valid plan: {last_err}")


PHASES = [
    ("Foundations", [
        ("Watch or read a beginner's introduction to {hobby}", "Pick one free, well-rated resource and note 3 things to try.", 0.30),
        ("Set up a simple practice space", "Gather only the basics you need for {hobby}; borrow before you buy.", 0.20),
        ("First hands-on session", "Try the most basic technique of {hobby} slowly. Mistakes are the point.", 0.50),
    ]),
    ("Core skills", [
        ("Drill one fundamental", "Repeat a single core skill of {hobby} in short focused rounds.", 0.40),
        ("Follow a guided exercise", "Use a tutorial or lesson that matches '{goal}'.", 0.35),
        ("Reflect and note progress", "Write down what felt easier than last week and what to fix next.", 0.25),
    ]),
    ("Build confidence", [
        ("Combine skills in a small project", "Make or perform something small that moves you toward '{goal}'.", 0.55),
        ("Get feedback", "Share with a friend or an online community for {hobby} and ask one question.", 0.20),
        ("Fix one weak spot", "Spend a session only on the part that felt hardest.", 0.25),
    ]),
    ("Show your progress", [
        ("Work on your showcase piece", "Pick a piece that shows your progress towards '{goal}'.", 0.60),
        ("Polish and record it", "Take a photo, video or recording so you can see how far you've come.", 0.25),
        ("Plan what's next", "Choose the next goal for {hobby} and a weekly rhythm you can keep.", 0.15),
    ]),
]


def generate_offline(req: PlanRequest) -> dict:
    """Deterministic fallback plan so the app works without an API key."""
    budget = req.minutes_per_week
    weeks = []
    for w in range(1, req.weeks + 1):
        phase_idx = min(len(PHASES) - 1, (w - 1) * len(PHASES) // req.weeks)
        focus, templates = PHASES[phase_idx]
        tasks = []
        for j, (title, details, share) in enumerate(templates):
            tasks.append({
                "title": title.format(hobby=req.hobby, goal=req.goal),
                "details": details.format(hobby=req.hobby, goal=req.goal),
                "minutes": max(10, int(budget * share)),
                "milestone": j == len(templates) - 1,
            })
        weeks.append({"week": w, "focus": focus, "tasks": tasks})
    summary = (f"A {req.weeks}-week starter path for {req.hobby}, built around "
               f"{req.hours_per_week:g} h per week, aimed at: {req.goal}.")
    return validate_plan({"summary": summary, "weeks": weeks}, req)


def generate_plan(req: PlanRequest, api_key: str | None = None) -> tuple[dict, str]:
    """Return (plan, source). Source is 'ai' or 'offline'."""
    key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if key:
        return generate_with_llm(req, key), "ai"
    return generate_offline(req), "offline"
