"""
Factory Audit Scoring - Streamlit POC (split-screen)

Two audit types live in sibling tabs, each with its own independent state:

  - "Hard Goods Factory Audits": the point-based model described below.
  - "Consumables Factory Audits": a deduction model. Every audit starts at 100
    points; each question is answered with a single dropdown (Meets
    Requirements / Minor / Major / Critical Non-Conformance / N/A). Minor
    deducts 1, major 5, critical 50; Meets Requirements and N/A deduct 0. The
    final score is floored at 0. Indicators: <64 Red · 64-89 Yellow · 90+ Green.
  - A shared "Photos" tab attaches reference photos at the question level.

Hard goods layout:
  - TOP   : a locally-generated "AI Summary" of the audit.
  - LEFT  : audit roll-up, a Critical-question tally, a manual Pass/Fail
            decision, per-section roll-ups, and a Quick Find search/filter.
  - RIGHT : the selected section's questions in a scrollable column, each with
            a points value, an N/A toggle, a Critical flag, and a score slider
            that is intentionally NOT pre-populated.

Hard goods scoring:
  - Assign each question a point value from 0 to 20.
  - Score each question with a slider (0 to that question's points). Scores are
    blank by default; unscored questions are flagged with a caution.
  - N/A questions are excluded from the score entirely.
  - Indicators (question, section, audit) use the same thresholds:
        0-33%  = Red   ·  34-66% = Yellow  ·  67%+ = Green
  - "Critical" is just a flag (with a counter and a Quick Find filter). It does
    NOT auto-fail the audit.
  - The auditor decides the final outcome with the Pass/Fail control.

All data lives in ``st.session_state``. No database, APIs, or authentication.
"""

import copy

import numpy as np
import streamlit as st
import streamlit.components.v1 as components

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_QUESTION_POINTS = 20
UNSCORED = "—"

YELLOW_MIN = 34   # 34-66 = Yellow
GREEN_MIN = 67    # 67+   = Green

BADGE_STYLES = {
    "Excellent": ("#047857", "#ffffff"),
    "Green": ("#d1fae5", "#065f46"),
    "Yellow": ("#fef3c7", "#92400e"),
    "Orange": ("#ffedd5", "#9a3412"),
    "Red": ("#fee2e2", "#991b1b"),
    "N/A": ("#e5e7eb", "#374151"),
}

COLOR_DOT = {"Green": "🟢", "Yellow": "🟡", "Orange": "🟠", "Red": "🔴", "N/A": "⚪"}

WIDGET_PREFIXES = ("pts_", "score_", "crit_", "na_", "photos_")

# ---------------------------------------------------------------------------
# Consumables audit scoring (deduction model)
#   Every audit begins at 100 points. Each non-conformance deducts points:
#     Minor -1 · Major -5 · Critical -50. "Meets Requirements" and "N/A" = 0.
#   The final score is floored at 0. Each question is answered with a single
#   dropdown (no per-question points, no slider, no separate critical flag).
# ---------------------------------------------------------------------------

CONS_START = 100

RESP_UNANSWERED = "—"
RESP_MEETS = "Meets Requirements"
RESP_MINOR = "Minor Non-Conformance"
RESP_MAJOR = "Major Non-Conformance"
RESP_CRITICAL = "Critical Non-Conformance"
RESP_NA = "N/A"

CONS_RESPONSES = [
    RESP_UNANSWERED,
    RESP_MEETS,
    RESP_MINOR,
    RESP_MAJOR,
    RESP_CRITICAL,
    RESP_NA,
]

CONS_DEDUCTION = {
    RESP_MEETS: 0,
    RESP_MINOR: 1,
    RESP_MAJOR: 5,
    RESP_CRITICAL: 50,
    RESP_NA: 0,
}

CONS_RESP_COLOR = {
    RESP_MEETS: "Green",
    RESP_MINOR: "Yellow",
    RESP_MAJOR: "Orange",
    RESP_CRITICAL: "Red",
    RESP_NA: "N/A",
}

# Color thresholds for the 100-point consumables score.
CONS_GREEN_MIN = 90   # 90+    = Green
CONS_YELLOW_MIN = 64  # 64-89  = Yellow  ·  <64 = Red

# ---------------------------------------------------------------------------
# Seed data (4 sections: 1 & 2, then duplicated as 3 & 4)
# ---------------------------------------------------------------------------

BASE_QUESTIONS = [
    {"question_id": "S2_Q1", "section_id": "S2", "question_number": 1,
     "question_text": "Is there any quality policy? 是否有质量方针?",
     "max_points": 10, "critical": False},
    {"question_id": "S2_Q2", "section_id": "S2", "question_number": 2,
     "question_text": "Is there any measurable objective and evaluated periodically? 是否建立可测量的质量目标并定期评估?",
     "max_points": 10, "critical": False},
    {"question_id": "S2_Q3", "section_id": "S2", "question_number": 3,
     "question_text": "Are responsible persons aware of their quality goal? 相关负责人是否清楚自己的质量目标?",
     "max_points": 8, "critical": False},
    {"question_id": "S2_Q4", "section_id": "S2", "question_number": 4,
     "question_text": "Is there any objective of punctual delivery ratio? 是否有准时交货率的目标?",
     "max_points": 8, "critical": False},
    {"question_id": "S2_Q5", "section_id": "S2", "question_number": 5,
     "question_text": "Does factory define the punctual delivery ratio method reasonably? 是否合理界定准时交货率统计方法?",
     "max_points": 8, "critical": False},
    {"question_id": "S2_Q6", "section_id": "S2", "question_number": 6,
     "question_text": "Could this objective meet? If not, what actions are taken? 质量目标是否达成？未达成时是否采取措施?",
     "max_points": 12, "critical": False},
    {"question_id": "S2_Q7", "section_id": "S2", "question_number": 7,
     "question_text": "Is there an internal policy/SOP for managing PFAS-containing materials? 是否有管理含PFAS材料的内部政策或SOP?",
     "max_points": 15, "critical": True},
    {"question_id": "S2_Q8", "section_id": "S2", "question_number": 8,
     "question_text": "Documented awareness of PFAS regulations and restrictions? 是否有记录表明了解PFAS法规和限制?",
     "max_points": 8, "critical": False},
    {"question_id": "S3_Q1", "section_id": "S3", "question_number": 1,
     "question_text": "Does top management conduct management review at least once a year? 管理层是否至少每年进行管理评审?",
     "max_points": 12, "critical": False},
    {"question_id": "S3_Q2", "section_id": "S3", "question_number": 2,
     "question_text": "Is a routine internal audit planned and implemented at least once a year? 是否至少每年计划并实施内审?",
     "max_points": 10, "critical": True},
]

DUP_SECTION = {"S2": "S4", "S3": "S5"}


def build_seed():
    """Return (sections, questions). Scores start blank (unscored)."""
    sections = [
        {"section_id": "S2", "section_name": "Quality policy and quality objectives", "display_order": 1},
        {"section_id": "S3", "section_name": "Internal audit and management review", "display_order": 2},
        {"section_id": "S4", "section_name": "Quality policy and quality objectives", "display_order": 3},
        {"section_id": "S5", "section_name": "Internal audit and management review", "display_order": 4},
    ]
    base = []
    for q in BASE_QUESTIONS:
        item = copy.deepcopy(q)
        item["received_score"] = None
        item["scored"] = False
        item["is_na"] = False
        base.append(item)

    questions = copy.deepcopy(base)
    for q in copy.deepcopy(base):
        new_sec = DUP_SECTION[q["section_id"]]
        q["section_id"] = new_sec
        q["question_id"] = q["question_id"].replace(q["question_id"].split("_")[0], new_sec)
        questions.append(q)
    return sections, questions


def build_seed_cons():
    """Return (sections, questions) for the consumables audit.

    Same questions/layout as hard goods, but each question carries a single
    ``response`` (unanswered by default) instead of points/score fields.
    """
    sections = [
        {"section_id": "S2", "section_name": "Quality policy and quality objectives", "display_order": 1},
        {"section_id": "S3", "section_name": "Internal audit and management review", "display_order": 2},
        {"section_id": "S4", "section_name": "Quality policy and quality objectives", "display_order": 3},
        {"section_id": "S5", "section_name": "Internal audit and management review", "display_order": 4},
    ]
    base = []
    for q in BASE_QUESTIONS:
        item = copy.deepcopy(q)
        item["response"] = RESP_UNANSWERED
        base.append(item)

    questions = copy.deepcopy(base)
    for q in copy.deepcopy(base):
        new_sec = DUP_SECTION[q["section_id"]]
        q["section_id"] = new_sec
        q["question_id"] = q["question_id"].replace(q["question_id"].split("_")[0], new_sec)
        questions.append(q)
    return sections, questions


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def initialize_state():
    if "initialized" not in st.session_state:
        sections, questions = build_seed()
        st.session_state.sections = sections
        st.session_state.questions = questions
        st.session_state.selected_section_id = sections[0]["section_id"]

        cons_sections, cons_questions = build_seed_cons()
        st.session_state.cons_sections = cons_sections
        st.session_state.cons_questions = cons_questions
        st.session_state.cons_selected_section_id = cons_sections[0]["section_id"]

        st.session_state.initialized = True


def reset_hard_goods():
    for key in list(st.session_state.keys()):
        if key.startswith(("pts_", "score_", "crit_", "na_")) or key == "audit_decision":
            del st.session_state[key]
    sections, questions = build_seed()
    st.session_state.sections = sections
    st.session_state.questions = questions
    st.session_state.selected_section_id = sections[0]["section_id"]


def reset_consumables():
    for key in list(st.session_state.keys()):
        if key.startswith("cresp_") or key == "cons_audit_decision":
            del st.session_state[key]
    sections, questions = build_seed_cons()
    st.session_state.cons_sections = sections
    st.session_state.cons_questions = questions
    st.session_state.cons_selected_section_id = sections[0]["section_id"]


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def color_for_percent(pct):
    if pct is None or (isinstance(pct, float) and np.isnan(pct)):
        return "N/A"
    if pct >= GREEN_MIN:
        return "Green"
    if pct >= YELLOW_MIN:
        return "Yellow"
    return "Red"


def is_scored(q):
    return (not q["is_na"]) and q["scored"] and q["received_score"] is not None


def question_percent(q):
    if not is_scored(q):
        return None
    mp = float(q["max_points"])
    rec = max(0.0, min(float(q["received_score"]), mp))
    return (rec / mp * 100) if mp > 0 else None


def question_status(q):
    """Return (color, label) for a single question."""
    if q["is_na"]:
        return "N/A", "N/A"
    if not is_scored(q):
        return "N/A", "Not scored"
    pct = question_percent(q)
    return color_for_percent(pct), fmt_pct(pct)


def section_summary(section_questions):
    """Return (total_points, earned_points, percent) over scored, applicable questions."""
    total = 0.0
    earned = 0.0
    for q in section_questions:
        if not is_scored(q):
            continue
        mp = float(q["max_points"])
        rec = max(0.0, min(float(q["received_score"]), mp))
        total += mp
        earned += rec
    pct = (earned / total * 100) if total > 0 else None
    return total, earned, pct


def section_questions(section_id):
    qs = [q for q in st.session_state.questions if q["section_id"] == section_id]
    return sorted(qs, key=lambda q: q["question_number"])


# ---------------------------------------------------------------------------
# Consumables scoring helpers (deduction model, 100-point start)
# ---------------------------------------------------------------------------

def cons_section_questions(section_id):
    qs = [q for q in st.session_state.cons_questions if q["section_id"] == section_id]
    return sorted(qs, key=lambda q: q["question_number"])


def cons_is_answered(q):
    return q["response"] != RESP_UNANSWERED


def cons_deduction(q):
    return CONS_DEDUCTION.get(q["response"], 0)


def cons_total_deduction(questions):
    return sum(cons_deduction(q) for q in questions)


def cons_audit_score(questions):
    """Final audit score: 100 minus all deductions, floored at 0."""
    return max(0, CONS_START - cons_total_deduction(questions))


def cons_color(score):
    if score is None:
        return "N/A"
    if score >= CONS_GREEN_MIN:
        return "Green"
    if score >= CONS_YELLOW_MIN:
        return "Yellow"
    return "Red"


# Overall rating tiers for the final consumables score. Each tier maps a
# minimum score to an audit rating, approval status, and re-audit frequency.
#   96-100 → E - Excellent (Pass)  · Approved     · Every 24 months
#   86-95  → G - Good (Pass)       · Approved     · Every 18 months
#   70-85  → C - Complies (Pass)   · Approved     · Every 12 months
#    0-69  → F - Fail              · Not Approved · Not Applicable
CONS_RATING_TIERS = [
    (96, "E - Excellent (Pass)", "Approved", "Every 24 months", "Excellent"),
    (86, "G - Good (Pass)", "Approved", "Every 18 months", "Green"),
    (70, "C - Complies (Pass)", "Approved", "Every 12 months", "Yellow"),
    (0, "F - Fail", "Not Approved", "Not Applicable", "Red"),
]


def cons_rating(score):
    """Map a final consumables score to its rating tier.

    Returns a dict with ``rating``, ``approval``, ``frequency``, and ``color``.
    """
    for threshold, rating, approval, frequency, color in CONS_RATING_TIERS:
        if score >= threshold:
            return {
                "rating": rating,
                "approval": approval,
                "frequency": frequency,
                "color": color,
            }
    threshold, rating, approval, frequency, color = CONS_RATING_TIERS[-1]
    return {"rating": rating, "approval": approval,
            "frequency": frequency, "color": color}


def cons_section_color(questions):
    """Color a section by treating its deductions against the 100 baseline."""
    if any(not cons_is_answered(q) for q in questions):
        return "N/A"
    return cons_color(max(0, CONS_START - cons_total_deduction(questions)))


def cons_question_status(q):
    """Return (color, label) for a single consumables question."""
    r = q["response"]
    if r == RESP_UNANSWERED:
        return "N/A", "Not answered"
    ded = CONS_DEDUCTION[r]
    color = CONS_RESP_COLOR[r]
    label = f"{r} (\u2212{ded})" if ded > 0 else r
    return color, label


def cons_counts(questions):
    counts = {
        RESP_MEETS: 0, RESP_MINOR: 0, RESP_MAJOR: 0,
        RESP_CRITICAL: 0, RESP_NA: 0, "unanswered": 0,
    }
    for q in questions:
        r = q["response"]
        if r == RESP_UNANSWERED:
            counts["unanswered"] += 1
        else:
            counts[r] += 1
    return counts


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------

def render_badge(label, color):
    bg, fg = BADGE_STYLES.get(color, BADGE_STYLES["N/A"])
    return (
        f"<span style='background-color:{bg};color:{fg};"
        f"padding:3px 10px;border-radius:12px;font-weight:700;"
        f"font-size:0.85rem;white-space:nowrap;'>{label}</span>"
    )


def fmt_pct(pct):
    if pct is None or (isinstance(pct, float) and np.isnan(pct)):
        return "N/A"
    return f"{pct:.1f}%"


def inject_css():
    st.markdown(
        """
        <style>
        html { scroll-behavior: smooth; }
        .roll-card {
            background-color: #f9fafb; border: 1px solid #e5e7eb;
            border-radius: 10px; padding: 12px 14px; margin-bottom: 10px;
        }
        .roll-card .label { font-size: 0.8rem; color: #6b7280; }
        .roll-card .value { font-size: 1.6rem; font-weight: 800; color: #111827; }
        .ai-card {
            background: #f5f7ff; border: 1px solid #c7d2fe; border-radius: 10px;
            padding: 14px 18px; margin-bottom: 6px;
        }
        .ai-card h4 { margin: 0 0 6px 0; color: #3730a3; }
        .q-title { font-weight: 600; color: #111827; margin-bottom: 4px; }
        .q-jump-list { margin: 2px 0 12px 0; }
        .qlink {
            display: flex; align-items: center; gap: 8px;
            padding: 5px 10px; border-radius: 6px; margin-left: 6px;
            color: #111827; text-decoration: none; font-size: 0.85rem;
            border-left: 2px solid #e5e7eb;
        }
        .qlink:hover { background: #f3f4f6; }
        .qlink .qnum { font-weight: 600; min-width: 28px; }
        .qlink .qtxt {
            flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
            color: #4b5563;
        }
        .q-anchor { scroll-margin-top: 8px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# AI Summary (locally generated, no external API)
# ---------------------------------------------------------------------------

def generate_ai_summary(sections):
    all_q = st.session_state.questions
    n_total = len(all_q)
    n_na = sum(1 for q in all_q if q["is_na"])
    n_unscored = sum(1 for q in all_q if (not q["is_na"]) and not is_scored(q))
    n_scored = n_total - n_na - n_unscored
    n_critical = sum(1 for q in all_q if q["critical"])
    crit_unscored = sum(1 for q in all_q if q["critical"] and (not q["is_na"]) and not is_scored(q))

    _, _, overall_pct = section_summary(all_q)
    overall_color = color_for_percent(overall_pct)

    reds = sum(1 for q in all_q if question_status(q)[0] == "Red")
    yellows = sum(1 for q in all_q if is_scored(q) and question_status(q)[0] == "Yellow")

    sec_lines = []
    worst = None
    for sec in sections:
        qs = section_questions(sec["section_id"])
        _, _, s_pct = section_summary(qs)
        sec_lines.append(f"{int(sec['display_order'])}) {sec['section_name']}: {fmt_pct(s_pct)}")
        if s_pct is not None and (worst is None or s_pct < worst[1]):
            worst = (sec, s_pct)

    decision = st.session_state.get("audit_decision")

    lines = []
    lines.append(
        f"This audit spans **{len(sections)} sections** and **{n_total} questions**, "
        f"of which **{n_critical}** are flagged as critical."
    )
    lines.append(
        f"Progress: **{n_scored} scored**, **{n_unscored} not yet scored**, "
        f"and **{n_na} marked N/A**."
    )

    if overall_pct is None:
        lines.append("No questions have been scored yet, so an overall score is not available.")
    else:
        if overall_color == "Green":
            interp = "indicating strong overall conformance."
        elif overall_color == "Yellow":
            interp = "indicating moderate conformance with room for improvement."
        else:
            interp = "indicating significant gaps that need attention."
        lines.append(f"The overall score is **{fmt_pct(overall_pct)} ({overall_color})**, {interp}")
        if reds or yellows:
            lines.append(
                f"Attention areas: **{reds}** question(s) in the red range and "
                f"**{yellows}** in the yellow range."
            )
        if worst is not None:
            lines.append(
                f"The weakest section so far is **{worst[0]['section_name']}** "
                f"at **{fmt_pct(worst[1])}**."
            )

    if crit_unscored:
        lines.append(f"⚠ **{crit_unscored} critical** question(s) still need to be scored.")
    if n_unscored:
        lines.append(f"⚠ Scoring is incomplete — **{n_unscored}** question(s) remain unscored.")

    if decision == "Pass":
        lines.append("Auditor decision: **PASS**.")
    elif decision == "Fail":
        lines.append("Auditor decision: **FAIL**.")
    else:
        lines.append("No pass/fail decision has been recorded yet.")

    return "  \n".join(f"- {ln}" for ln in lines)


def render_ai_summary(sections):
    st.markdown(
        "<div class='ai-card'><h4>🧠 AI Summary</h4>"
        "<div style='font-size:0.78rem;color:#6b7280;margin-bottom:6px'>"
        "Generated locally from the current audit data — no external API.</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(generate_ai_summary(sections))


# ---------------------------------------------------------------------------
# LEFT: roll-ups + navigation + quick find
# ---------------------------------------------------------------------------

def render_left(sections):
    all_q = st.session_state.questions
    total_possible, earned_total, pct = section_summary(all_q)
    a_color = color_for_percent(pct)
    n_critical = sum(1 for q in all_q if q["critical"])

    st.markdown("### Audit Score")
    sc_col, cr_col = st.columns([3, 2])
    with sc_col:
        st.markdown(
            f"<div class='roll-card'>"
            f"<div class='label'>Overall (scored: {earned_total:.0f} / {total_possible:.0f} pts)</div>"
            f"<div class='value'>{fmt_pct(pct)}</div>"
            f"{render_badge(a_color, a_color)}</div>",
            unsafe_allow_html=True,
        )
    with cr_col:
        st.markdown(
            f"<div class='roll-card'>"
            f"<div class='label'>Critical Questions</div>"
            f"<div class='value'>{n_critical}</div>"
            f"{render_badge('flag only', 'N/A')}</div>",
            unsafe_allow_html=True,
        )

    # Manual Pass/Fail decision.
    st.segmented_control("Pass/Fail Audit", ["Pass", "Fail"], key="audit_decision")
    decision = st.session_state.get("audit_decision")
    if decision == "Pass":
        st.markdown("Final decision: " + render_badge("PASS", "Green"), unsafe_allow_html=True)
    elif decision == "Fail":
        st.markdown("Final decision: " + render_badge("FAIL", "Red"), unsafe_allow_html=True)
    else:
        st.markdown("Final decision: " + render_badge("Undecided", "N/A"), unsafe_allow_html=True)

    st.markdown("### Sections")
    selected = st.session_state.selected_section_id
    for sec in sections:
        sec_id = sec["section_id"]
        qs = section_questions(sec_id)
        _, _, s_pct = section_summary(qs)
        color = color_for_percent(s_pct)
        dot = COLOR_DOT[color]
        marker = "▶ " if sec_id == selected else ""
        label = f"{dot} {marker}{int(sec['display_order'])}) {sec['section_name']} — {fmt_pct(s_pct)}"
        if st.button(
            label,
            key=f"navsec_{sec_id}",
            use_container_width=True,
            type="primary" if sec_id == selected else "secondary",
        ):
            st.session_state.selected_section_id = sec_id
            st.rerun()

        if sec_id == selected:
            rows = []
            for q in qs:
                q_color, q_label = question_status(q)
                crit = "⚠ " if q["critical"] else ""
                rows.append(
                    f"<a class='qlink' href='#q_{q['question_id']}'>"
                    f"<span>{COLOR_DOT[q_color]}</span>"
                    f"<span class='qnum'>{crit}Q{int(q['question_number'])}</span>"
                    f"<span class='qtxt'>{q['question_text']}</span>"
                    f"{render_badge(q_label, q_color)}</a>"
                )
            st.markdown(f"<div class='q-jump-list'>{''.join(rows)}</div>", unsafe_allow_html=True)

    st.markdown("---")
    render_quick_find(sections)


def render_quick_find(sections):
    st.markdown("### Quick Find")
    term = st.text_input("Search question text", key="qf_search", placeholder="Type to search…")
    filter_colors = st.multiselect(
        "Filter by result color", ["Green", "Yellow", "Red", "N/A"], key="qf_colors"
    )
    critical_only = st.checkbox("Critical questions only", key="qf_critical")

    order_map = {s["section_id"]: s["display_order"] for s in sections}
    term_l = (term or "").strip().lower()

    if not term_l and not filter_colors and not critical_only:
        st.caption("Enter a search term, pick a color, or filter to critical questions.")
        return

    results = []
    for q in st.session_state.questions:
        color, label = question_status(q)
        haystack = f"{q['question_text']} q{q['question_number']}".lower()
        if term_l and term_l not in haystack:
            continue
        if filter_colors and color not in filter_colors:
            continue
        if critical_only and not q["critical"]:
            continue
        results.append((q, color, label))

    if not results:
        st.caption("No matching questions.")
        return

    results.sort(key=lambda r: (order_map.get(r[0]["section_id"], 0), r[0]["question_number"]))
    st.caption(f"{len(results)} match(es)")
    for q, color, label in results:
        dot = COLOR_DOT[color]
        sec_ord = order_map.get(q["section_id"], 0)
        text = q["question_text"]
        short = text[:44] + ("…" if len(text) > 44 else "")
        crit_flag = "⚠ " if q["critical"] else ""
        btn_label = f"{dot} {crit_flag}S{int(sec_ord)}·Q{int(q['question_number'])} — {short}"
        if st.button(btn_label, key=f"qf_{q['question_id']}", use_container_width=True):
            st.session_state.selected_section_id = q["section_id"]
            st.session_state.scroll_to = q["question_id"]
            st.rerun()


# ---------------------------------------------------------------------------
# RIGHT: question editor for the selected section
# ---------------------------------------------------------------------------

def render_question(q):
    qid = q["question_id"]
    st.markdown(f"<div id='q_{qid}' class='q-anchor'></div>", unsafe_allow_html=True)

    pts_key, score_key, crit_key, na_key = f"pts_{qid}", f"score_{qid}", f"crit_{qid}", f"na_{qid}"
    if pts_key not in st.session_state:
        st.session_state[pts_key] = int(q["max_points"])
    if crit_key not in st.session_state:
        st.session_state[crit_key] = bool(q["critical"])
    if na_key not in st.session_state:
        st.session_state[na_key] = bool(q["is_na"])
    if score_key not in st.session_state:
        st.session_state[score_key] = (
            int(q["received_score"]) if (q["scored"] and q["received_score"] is not None) else UNSCORED
        )

    st.markdown(
        f"<div class='q-title'>Q{int(q['question_number'])}. {q['question_text']}</div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        st.number_input("Points (0-20)", min_value=0, max_value=MAX_QUESTION_POINTS,
                        step=1, key=pts_key)
    with c2:
        st.checkbox("N/A (not applicable)", key=na_key)
    with c3:
        st.checkbox("Critical (flag)", key=crit_key)

    max_pts = int(st.session_state[pts_key])
    is_na = bool(st.session_state[na_key])

    # Keep any stored numeric score within the current point range.
    cur = st.session_state[score_key]
    if cur != UNSCORED and isinstance(cur, (int, float)) and int(cur) > max_pts:
        st.session_state[score_key] = max_pts

    if is_na:
        st.markdown("_Marked N/A — excluded from scoring._")
        scored = False
        received = None
    elif max_pts <= 0:
        st.markdown("_0 points assigned — nothing to score._")
        scored = False
        received = None
    else:
        options = [UNSCORED] + list(range(0, max_pts + 1))
        st.select_slider(f"Score (0–{max_pts})", options=options, key=score_key)
        val = st.session_state[score_key]
        scored = val != UNSCORED
        received = int(val) if scored else None

    # Persist back to the question record.
    q["max_points"] = max_pts
    q["is_na"] = is_na
    q["critical"] = bool(st.session_state[crit_key])
    q["scored"] = scored
    q["received_score"] = received

    color, label = question_status(q)
    badge_html = render_badge(label, color)
    if (not is_na) and (not scored) and max_pts > 0:
        badge_html += " &nbsp; " + render_badge("⚠ Not scored yet", "Yellow")
    st.markdown("Result: " + badge_html, unsafe_allow_html=True)
    st.markdown("---")


def render_right(sections):
    selected = st.session_state.selected_section_id
    sec = next((s for s in sections if s["section_id"] == selected), sections[0])
    qs = section_questions(sec["section_id"])

    total, earned, pct = section_summary(qs)
    color = color_for_percent(pct)
    n_unscored = sum(1 for q in qs if (not q["is_na"]) and not is_scored(q))

    head_l, head_r = st.columns([3, 1])
    with head_l:
        st.markdown(f"### {int(sec['display_order'])}) {sec['section_name']}")
        caption = f"{len(qs)} questions · scored {earned:.0f} / {total:.0f} points"
        if n_unscored:
            caption += f" · ⚠ {n_unscored} unscored"
        st.caption(caption)
    with head_r:
        st.markdown(
            f"<div style='text-align:right'>"
            f"<div style='font-size:1.4rem;font-weight:800'>{fmt_pct(pct)}</div>"
            f"{render_badge(color, color)}</div>",
            unsafe_allow_html=True,
        )

    with st.container(height=540):
        for q in qs:
            render_question(q)


# ---------------------------------------------------------------------------
# CONSUMABLES: AI summary (locally generated)
# ---------------------------------------------------------------------------

def generate_cons_ai_summary(sections):
    all_q = st.session_state.cons_questions
    n_total = len(all_q)
    counts = cons_counts(all_q)
    total_ded = cons_total_deduction(all_q)
    score = cons_audit_score(all_q)
    color = cons_color(score)
    n_unanswered = counts["unanswered"]

    worst = None
    for sec in sections:
        qs = cons_section_questions(sec["section_id"])
        ded = cons_total_deduction(qs)
        if ded > 0 and (worst is None or ded > worst[1]):
            worst = (sec, ded)

    decision = st.session_state.get("cons_audit_decision")

    lines = []
    lines.append(
        f"This consumables audit spans **{len(sections)} sections** and "
        f"**{n_total} questions**, each starting from a **{CONS_START}-point** baseline."
    )
    lines.append(
        f"Responses: **{counts[RESP_MEETS]} meets requirements**, "
        f"**{counts[RESP_MINOR]} minor**, **{counts[RESP_MAJOR]} major**, "
        f"**{counts[RESP_CRITICAL]} critical** non-conformance(s), "
        f"**{counts[RESP_NA]} N/A**, and **{n_unanswered} not yet answered**."
    )

    if total_ded == 0 and n_unanswered == n_total:
        lines.append("No questions have been answered yet, so the score remains at the full baseline.")
    else:
        if color == "Green":
            interp = "indicating strong overall conformance."
        elif color == "Yellow":
            interp = "indicating moderate conformance with room for improvement."
        else:
            interp = "indicating significant gaps that need attention."
        rating = cons_rating(score)
        lines.append(
            f"Starting at {CONS_START}, **{total_ded} point(s)** were deducted, "
            f"for a final score of **{score} / {CONS_START} ({color})**, {interp}"
        )
        lines.append(
            f"This score earns a rating of **{rating['rating']}** — "
            f"**{rating['approval']}**, re-audit **{rating['frequency']}**."
        )
        if counts[RESP_CRITICAL]:
            lines.append(
                f"\u26a0 **{counts[RESP_CRITICAL]} critical** non-conformance(s) "
                f"(\u221250 each) drove the largest deductions."
            )
        if worst is not None:
            lines.append(
                f"The weakest section so far is **{worst[0]['section_name']}** "
                f"with **\u2212{worst[1]} point(s)** deducted."
            )

    if n_unanswered:
        lines.append(f"\u26a0 Scoring is incomplete \u2014 **{n_unanswered}** question(s) remain unanswered.")

    if decision == "Pass":
        lines.append("Auditor decision: **PASS**.")
    elif decision == "Fail":
        lines.append("Auditor decision: **FAIL**.")
    else:
        lines.append("No pass/fail decision has been recorded yet.")

    return "  \n".join(f"- {ln}" for ln in lines)


def render_cons_ai_summary(sections):
    st.markdown(
        "<div class='ai-card'><h4>🧠 AI Summary</h4>"
        "<div style='font-size:0.78rem;color:#6b7280;margin-bottom:6px'>"
        "Generated locally from the current audit data — no external API.</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(generate_cons_ai_summary(sections))


# ---------------------------------------------------------------------------
# CONSUMABLES: LEFT (roll-ups + navigation + quick find)
# ---------------------------------------------------------------------------

def render_cons_left(sections):
    all_q = st.session_state.cons_questions
    score = cons_audit_score(all_q)
    color = cons_color(score)
    counts = cons_counts(all_q)
    total_ded = cons_total_deduction(all_q)
    rating = cons_rating(score)

    st.markdown("### Audit Score")
    sc_col, nc_col = st.columns([3, 2])
    with sc_col:
        st.markdown(
            f"<div class='roll-card'>"
            f"<div class='label'>Score (start {CONS_START} · \u2212{total_ded} deducted)</div>"
            f"<div class='value'>{score} / {CONS_START}</div>"
            f"{render_badge(rating['rating'], rating['color'])}</div>",
            unsafe_allow_html=True,
        )
    with nc_col:
        st.markdown(
            f"<div class='roll-card'>"
            f"<div class='label'>Non-Conformances</div>"
            f"<div class='value'>"
            f"{counts[RESP_MINOR]} / {counts[RESP_MAJOR]} / {counts[RESP_CRITICAL]}</div>"
            f"{render_badge('minor / major / critical', 'N/A')}</div>",
            unsafe_allow_html=True,
        )

    ap_col, fq_col = st.columns(2)
    with ap_col:
        st.markdown(
            f"<div class='roll-card'>"
            f"<div class='label'>Approval Status</div>"
            f"<div class='value' style='font-size:1.1rem'>{rating['approval']}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with fq_col:
        st.markdown(
            f"<div class='roll-card'>"
            f"<div class='label'>Audit Frequency</div>"
            f"<div class='value' style='font-size:1.1rem'>{rating['frequency']}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.segmented_control("Pass/Fail Audit", ["Pass", "Fail"], key="cons_audit_decision")
    decision = st.session_state.get("cons_audit_decision")
    if decision == "Pass":
        st.markdown("Final decision: " + render_badge("PASS", "Green"), unsafe_allow_html=True)
    elif decision == "Fail":
        st.markdown("Final decision: " + render_badge("FAIL", "Red"), unsafe_allow_html=True)
    else:
        st.markdown("Final decision: " + render_badge("Undecided", "N/A"), unsafe_allow_html=True)

    st.markdown("### Sections")
    selected = st.session_state.cons_selected_section_id
    for sec in sections:
        sec_id = sec["section_id"]
        qs = cons_section_questions(sec_id)
        ded = cons_total_deduction(qs)
        color = cons_section_color(qs)
        dot = COLOR_DOT[color]
        marker = "▶ " if sec_id == selected else ""
        label = f"{dot} {marker}{int(sec['display_order'])}) {sec['section_name']} — \u2212{ded} pts"
        if st.button(
            label,
            key=f"navcsec_{sec_id}",
            use_container_width=True,
            type="primary" if sec_id == selected else "secondary",
        ):
            st.session_state.cons_selected_section_id = sec_id
            st.rerun()

        if sec_id == selected:
            rows = []
            for q in qs:
                q_color, q_label = cons_question_status(q)
                rows.append(
                    f"<a class='qlink' href='#cq_{q['question_id']}'>"
                    f"<span>{COLOR_DOT[q_color]}</span>"
                    f"<span class='qnum'>Q{int(q['question_number'])}</span>"
                    f"<span class='qtxt'>{q['question_text']}</span>"
                    f"{render_badge(q_label, q_color)}</a>"
                )
            st.markdown(f"<div class='q-jump-list'>{''.join(rows)}</div>", unsafe_allow_html=True)

    st.markdown("---")
    render_cons_quick_find(sections)


def render_cons_quick_find(sections):
    st.markdown("### Quick Find")
    term = st.text_input("Search question text", key="cqf_search", placeholder="Type to search…")
    resp_filter = st.multiselect(
        "Filter by response",
        [RESP_MEETS, RESP_MINOR, RESP_MAJOR, RESP_CRITICAL, RESP_NA, "Not answered"],
        key="cqf_resp",
    )

    order_map = {s["section_id"]: s["display_order"] for s in sections}
    term_l = (term or "").strip().lower()

    if not term_l and not resp_filter:
        st.caption("Enter a search term or filter by response.")
        return

    results = []
    for q in st.session_state.cons_questions:
        color, label = cons_question_status(q)
        haystack = f"{q['question_text']} q{q['question_number']}".lower()
        if term_l and term_l not in haystack:
            continue
        if resp_filter:
            answered = cons_is_answered(q)
            match = (q["response"] in resp_filter) or ("Not answered" in resp_filter and not answered)
            if not match:
                continue
        results.append((q, color, label))

    if not results:
        st.caption("No matching questions.")
        return

    results.sort(key=lambda r: (order_map.get(r[0]["section_id"], 0), r[0]["question_number"]))
    st.caption(f"{len(results)} match(es)")
    for q, color, label in results:
        dot = COLOR_DOT[color]
        sec_ord = order_map.get(q["section_id"], 0)
        text = q["question_text"]
        short = text[:44] + ("…" if len(text) > 44 else "")
        btn_label = f"{dot} S{int(sec_ord)}·Q{int(q['question_number'])} — {short}"
        if st.button(btn_label, key=f"cqf_{q['question_id']}", use_container_width=True):
            st.session_state.cons_selected_section_id = q["section_id"]
            st.session_state.cons_scroll_to = q["question_id"]
            st.rerun()


# ---------------------------------------------------------------------------
# CONSUMABLES: RIGHT (dropdown response editor)
# ---------------------------------------------------------------------------

def render_cons_question(q):
    qid = q["question_id"]
    st.markdown(f"<div id='cq_{qid}' class='q-anchor'></div>", unsafe_allow_html=True)

    resp_key = f"cresp_{qid}"
    if resp_key not in st.session_state:
        st.session_state[resp_key] = q["response"]

    st.markdown(
        f"<div class='q-title'>Q{int(q['question_number'])}. {q['question_text']}</div>",
        unsafe_allow_html=True,
    )

    st.selectbox(
        "Response", options=CONS_RESPONSES, key=resp_key, label_visibility="collapsed"
    )
    q["response"] = st.session_state[resp_key]

    color, label = cons_question_status(q)
    st.markdown("Result: " + render_badge(label, color), unsafe_allow_html=True)
    st.markdown("---")


def render_cons_right(sections):
    selected = st.session_state.cons_selected_section_id
    sec = next((s for s in sections if s["section_id"] == selected), sections[0])
    qs = cons_section_questions(sec["section_id"])

    ded = cons_total_deduction(qs)
    color = cons_section_color(qs)
    n_unanswered = sum(1 for q in qs if not cons_is_answered(q))

    head_l, head_r = st.columns([3, 1])
    with head_l:
        st.markdown(f"### {int(sec['display_order'])}) {sec['section_name']}")
        caption = f"{len(qs)} questions · \u2212{ded} points deducted in this section"
        if n_unanswered:
            caption += f" · ⚠ {n_unanswered} unanswered"
        st.caption(caption)
    with head_r:
        st.markdown(
            f"<div style='text-align:right'>"
            f"<div style='font-size:1.4rem;font-weight:800'>\u2212{ded} pts</div>"
            f"{render_badge(color, color)}</div>",
            unsafe_allow_html=True,
        )

    with st.container(height=540):
        for q in qs:
            render_cons_question(q)


# ---------------------------------------------------------------------------
# PHOTOS tab (mock photo-upload at the question level)
# ---------------------------------------------------------------------------

def render_photos_tab(sections):
    st.markdown("### Photos")
    st.caption(
        "Mock-up: attach reference photos to each question. Demo only — uploaded "
        "files are held in session memory and are not saved anywhere."
    )

    for sec in sections:
        qs = section_questions(sec["section_id"])
        photo_count = sum(
            len(st.session_state.get(f"photos_{q['question_id']}") or []) for q in qs
        )
        title = (
            f"{int(sec['display_order'])}) {sec['section_name']} "
            f"— {photo_count} photo(s)"
        )
        with st.expander(title, expanded=(sec["section_id"] == st.session_state.selected_section_id)):
            for q in qs:
                st.markdown(
                    f"<div class='q-title'>Q{int(q['question_number'])}. {q['question_text']}</div>",
                    unsafe_allow_html=True,
                )
                files = st.file_uploader(
                    "Upload photos",
                    type=["png", "jpg", "jpeg", "webp", "gif"],
                    accept_multiple_files=True,
                    key=f"photos_{q['question_id']}",
                    label_visibility="collapsed",
                )
                if files:
                    cols = st.columns(4)
                    for i, f in enumerate(files):
                        with cols[i % 4]:
                            st.image(f, caption=f.name, use_container_width=True)
                    st.caption(f"📷 {len(files)} photo(s) attached.")
                else:
                    st.caption("No photos attached.")
                st.markdown("---")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def scroll_to_anchor(anchor_id):
    """Smooth-scroll the parent document to the given element id."""
    components.html(
        f"""
        <script>
          setTimeout(function() {{
            const el = window.parent.document.getElementById('{anchor_id}');
            if (el) {{ el.scrollIntoView({{behavior: 'smooth', block: 'start'}}); }}
          }}, 200);
        </script>
        """,
        height=0,
    )


def render_hard_goods_tab(sections):
    head_l, head_r = st.columns([4, 1])
    with head_l:
        st.subheader("Hard Goods Factory Audit — Audit Run")
        st.caption(
            "Point-based scoring. Indicators: 0-33% Red · 34-66% Yellow · 67%+ "
            "Green. Critical is a flag only. Scores start blank; the auditor sets "
            "Pass/Fail."
        )
    with head_r:
        st.write("")
        if st.button("Reset hard goods", use_container_width=True, key="reset_hg"):
            reset_hard_goods()
            st.rerun()

    # Reserve the top slot for the AI Summary; fill it after the editors run so
    # it reflects edits made in the same interaction.
    ai_placeholder = st.container()

    left_col, right_col = st.columns([1, 2], gap="large")
    # Render the editor (right) first so edits are captured into session_state
    # before the left-side roll-ups and summary are computed.
    with right_col:
        render_right(sections)
    with left_col:
        render_left(sections)

    with ai_placeholder:
        render_ai_summary(sections)
        st.markdown("---")

    target = st.session_state.pop("scroll_to", None)
    if target:
        scroll_to_anchor(f"q_{target}")


def render_consumables_tab(sections):
    head_l, head_r = st.columns([4, 1])
    with head_l:
        st.subheader("Consumables Factory Audit — Audit Run")
        st.caption(
            f"Deduction-based scoring. Every audit starts at {CONS_START} points: "
            "minor \u22121 · major \u22125 · critical \u221250; Meets Requirements & "
            "N/A = 0 (floored at 0). Rating: 96-100 E - Excellent · 86-95 G - Good · "
            "70-85 C - Complies · 0-69 F - Fail. The final score sets the rating, "
            "approval status, and audit frequency automatically."
        )
    with head_r:
        st.write("")
        if st.button("Reset consumables", use_container_width=True, key="reset_cons"):
            reset_consumables()
            st.rerun()

    ai_placeholder = st.container()

    left_col, right_col = st.columns([1, 2], gap="large")
    with right_col:
        render_cons_right(sections)
    with left_col:
        render_cons_left(sections)

    with ai_placeholder:
        render_cons_ai_summary(sections)
        st.markdown("---")

    target = st.session_state.pop("cons_scroll_to", None)
    if target:
        scroll_to_anchor(f"cq_{target}")


def main():
    st.set_page_config(layout="wide", page_title="Factory Audit Scoring POC")
    initialize_state()
    inject_css()

    st.title("Factory Audit Scoring POC")
    st.caption("Separate scoring models for hard goods and consumables audits.")

    sections = sorted(st.session_state.sections, key=lambda s: s["display_order"])
    cons_sections = sorted(st.session_state.cons_sections, key=lambda s: s["display_order"])

    tab_hard, tab_cons, tab_photos = st.tabs(
        ["Hard Goods Factory Audits", "Consumables Factory Audits", "Photos"]
    )

    with tab_hard:
        render_hard_goods_tab(sections)

    with tab_cons:
        render_consumables_tab(cons_sections)

    with tab_photos:
        render_photos_tab(sections)


if __name__ == "__main__":
    main()
