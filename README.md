# Factory Audit Scoring — POC

A self-contained, single-page Streamlit tool for scoring a factory audit. No
database, no external APIs, no authentication — all data lives in
`st.session_state`.

## What it does

- **Assign each question a point value from 0 to 20.**
- **Each section's total is the sum of its question points** (you don't set a
  separate section budget — it adds up automatically).
- **Each question receives a score** (0 up to the question's point value).
- **Red / Yellow / Green indicators** at both the section and overall level:

  | Score % | Result |
  |---------|--------|
  | 0–33%   | Red    |
  | 34–66%  | Yellow |
  | 67%+    | Green  |

- **Critical (Auto-Fail) checkbox** on every question. If a question marked
  Critical receives a **score of 0**, the **entire audit fails immediately**
  (shown as `AUTO-FAIL`), regardless of the calculated percentage.

## How to run

```bash
pip install -r requirements.txt
streamlit run app.py
```

(If your machine has no `pip`/`streamlit` on the PATH, a local virtual
environment is already set up in `.venv`, so you can run
`.venv/bin/streamlit run app.py` instead.)

## Scoring rules

```
section_total   = sum(question max_points)            # per section
section_earned  = sum(min(received_score, max_points))
section_percent = section_earned / section_total * 100

audit_total     = sum(all question max_points)
audit_earned    = sum(all min(received_score, max_points))
audit_percent   = audit_earned / audit_total * 100

result(percent):
    Green  if percent >= 67
    Yellow if percent >= 34
    Red    otherwise

# Override: if any Critical question has received_score == 0:
#     the whole audit is AUTO-FAIL (Red), regardless of audit_percent.
```

Notes:

- A score entered above a question's point value is counted as full points and
  flagged with a warning.
- If no points are assigned (total = 0), the percentage shows `N/A`.
- Use **Reset demo data** to restore the seeded example.

## Seed data

Two sections, all questions scored full marks by default (a Green, passing
audit), with question 7 pre-flagged as Critical:

- **Section 2 — Quality policy and quality objectives** (8 questions)
- **Section 3 — Internal audit and management review** (2 questions)
