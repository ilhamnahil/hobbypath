# 🌱 HobbyPath

**Learn a new hobby as an adult, one small step at a time.**

Most adults who want to pick up guitar, painting or a new language stop after two weeks, not because they lack talent,
but because they have no plan that fits around a job and a family. HobbyPath turns a goal like
*"play three songs at a friend's birthday"* and *"2.5 hours a week"* into a realistic week-by-week plan, then keeps you
going with streaks, milestones and a practice log.

![Dashboard](docs/dashboard.png)

## Features

- **AI learning plans**: an LLM (Claude) builds a personalised plan from your hobby, goal, level and weekly time budget.
- **Works offline too**: without an API key a rule-based planner creates a sensible starter plan, so the app always runs.
- **Weekly milestones** 🏁: one visible result per week to build confidence.
- **Streaks and badges**: consecutive practice days, longest streak and badges from *First step* to *30-day legend*.
- **Practice log**: log minutes and notes, see daily practice in a chart and track progress against your weekly goal.
- **Local and private**: everything is stored in a local SQLite file.

| New hobby | Practice log |
|---|---|
| ![New hobby](docs/new-hobby.png) | ![Practice log](docs/practice-log.png) |

## Quick start

```bash
git clone https://github.com/ilhamnahil/hobbypath.git
cd hobbypath
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501.

### Turn on AI plans (optional)

Create an API key at [console.anthropic.com](https://console.anthropic.com), then either paste it into
**AI settings** in the sidebar or set it before starting:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."      # Windows PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
export HOBBYPATH_MODEL="claude-sonnet-5-5"  # optional, choose another model
```

## How it works

```
app.py                Streamlit UI (new hobby form, dashboard, plan, practice log)
hobbypath/planner.py  Prompt, LLM call, JSON parsing/validation, offline fallback
hobbypath/stats.py    Streaks, completion, weekly minutes, badges (pure functions)
hobbypath/db.py       SQLite storage for hobbies, tasks and practice sessions
tests/                pytest suite (planner, stats, storage, mocked LLM)
```

**Prompt engineering in `planner.py`**

- A system prompt sets the coach persona and hard rules: respect the weekly time budget, 2–4 tasks per week,
  exactly one milestone per week, and no expensive gear up front.
- The model must answer in a fixed **JSON schema**. The response is parsed robustly, even when wrapped in markdown fences.
- **Validation and self-repair**: the plan is checked. If the JSON is invalid, the error is sent back to the model
  for one retry. Weeks over the time budget are scaled down instead of rejected.
- If the API is unavailable, the app falls back to the offline planner, so the user is never stuck.

## Tests

```bash
pip install pytest
pytest
```

## Roadmap

- [ ] Regenerate or adapt a week when you fall behind
- [ ] Reminders (email or calendar export)
- [ ] Resource suggestions per task (videos, articles)
- [ ] Multi-user deployment on Streamlit Community Cloud

## License

MIT, see [LICENSE](LICENSE).
