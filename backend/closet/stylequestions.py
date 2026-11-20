"""What the stylist cannot learn from the clothes and the wears, asked one question at a time (DESIGN, principle 6:
"Ask in conversation, not in forms"; the idea is Homestead's `questions.py`).

Each question says why it matters to the outfits and where the answer is kept. The style conversation (Settings,
Your style) asks the next one when it is opened with nothing said yet that day; the owner taps a choice, writes their
own answer, or skips it. An answer becomes a line of the style profile (marked as an answer, `styleprofile`), the
stylist's one place for what the owner says about their style; a skip is kept too, so no question is asked twice.
Taking an answer back (Undo) takes its line out and asks the question again. Nothing here asks Claude: the line is
the choice's own sentence, or the question's lead-in with the owner's words.

Not yet asked on Today (BACKLOG, "Style through conversation").
"""
from __future__ import annotations

from dataclasses import dataclass

from . import db, styleprofile

ANSWERED, SKIPPED = "answered", "skipped"
WHERE = "a line of Your style, which Claude reads every time it chooses your outfits"


@dataclass(frozen=True)
class Question:
    id: str
    ask: str                                   # the question, as the owner reads it
    why: str                                   # why it matters, in a sentence for the owner
    choices: tuple[tuple[str, str], ...]       # (what the button says, the line it becomes)
    lead: str                                  # the line for the owner's own words: lead + their words
    where: str = WHERE


QUESTIONS: tuple[Question, ...] = (
    Question("warmth", "Do you tend to feel the cold, or run warm?",
             "Claude dresses you for how the weather feels to you, not to most people.",
             (("I run warm", "I run warm, so dress me a little lighter than the weather suggests."),
              ("I feel the cold", "I feel the cold, so dress me a little warmer than the weather suggests."),
              ("Neither", "I feel the cold about as much as most people.")),
             "How I feel the cold: "),
    Question("work", "What do you wear for work?",
             "Claude can see your clothes but not your workplace, so it can't tell how dressed-up a work day is.",
             (("A suit", "For work I wear a suit."),
              ("Smart, no tie", "For work I dress smartly, without a tie."),
              ("Smart casual", "For work I wear smart casual."),
              ("Anything goes", "Work has no dress code: anything goes."),
              ("I don't go in", "I don't go in to a workplace, so I don't need work clothes.")),
             "For work I wear: "),
    Question("colours", "Are there colours you never wear?",
             "A colour you avoid is easy to miss: it may be in your closet as a gift, or close to one you like.",
             (("No, none", "There are no colours I avoid."),),
             "Colours I never wear: "),
    Question("weekends", "How dressed-up do you like to be at weekends?",
             "Most of the week is not work, and people dress very differently when it is up to them.",
             (("Relaxed", "At weekends I like to be relaxed and comfortable."),
              ("Smart casual", "At weekends I still like to look put together: smart casual."),
              ("As at work", "At weekends I dress much as I do for work.")),
             "At weekends I like to dress: "),
    Question("fit", "How do you like your clothes to fit?",
             "Two people with the same clothes wear them differently: closer to the body, or with room.",
             (("Close to the body", "I like my clothes to fit close to the body."),
              ("In between", "I like clothes that fit easily, neither tight nor loose."),
              ("Roomy", "I like my clothes roomy and relaxed.")),
             "How I like my clothes to fit: "),
    Question("never", "Is there anything you never wear?",
             "Some things never suit a person, whatever the day: shorts, ties, sandals, a hood.",
             (("No, nothing", "There is nothing I never wear."),),
             "I never wear: "),
)
BY_ID = {q.id: q for q in QUESTIONS}
MAX_ANSWER = 200   # the longest answer in the owner's own words (characters)


def public(q: Question) -> dict:
    """A question as the page is given it: {id, ask, why, choices: [what each button says]}."""
    return {"id": q.id, "ask": q.ask, "why": q.why, "choices": [c for c, _ in q.choices]}


def asked(conn) -> set[str]:
    """The questions answered or skipped already."""
    return {r["id"] for r in conn.execute("SELECT id FROM style_questions")}


def next_question(conn) -> dict | None:
    """The next question not yet answered or skipped, as the page is given it; None when every one has been."""
    done = asked(conn)
    return next((public(q) for q in QUESTIONS if q.id not in done), None)


def _question(qid: object) -> Question:
    q = BY_ID.get(qid) if isinstance(qid, str) else None
    if q is None:
        raise LookupError("That question is not known.")
    return q


def answer(conn, qid: str, choice: object = None, text: object = None) -> dict:
    """Answer a question with one of its choices (what the button says) or in the owner's own words. The answer is a
    new line of the style profile. Gives back {line, question}: the line kept and the next question. Raises
    LookupError for an unknown question, ValueError with a sentence for an answer that cannot be kept (or a question
    answered already)."""
    q = _question(qid)
    if choice is not None:
        line = dict(q.choices).get(choice) if isinstance(choice, str) else None
        if line is None:
            raise ValueError("Choose one of the answers, or write your own.")
        said = choice
    else:
        if not isinstance(text, str) or not " ".join(text.split()):
            raise ValueError("Write your answer, or choose one.")
        said = " ".join(text.split())
        if len(said) > MAX_ANSWER:
            raise ValueError(f"An answer can be at most {MAX_ANSWER} characters long; this is {len(said)}.")
        line = q.lead + said
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("SELECT 1 FROM style_questions WHERE id = ?", (q.id,)).fetchone():
            raise ValueError("You have answered that already.")
        kept = styleprofile.add_line(conn, line, "question")
        conn.execute("INSERT INTO style_questions (id, state, answer, line_id, at) VALUES (?, ?, ?, ?, ?)",
                     (q.id, ANSWERED, said, kept["id"], db.now()))
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return {"line": kept, "question": next_question(conn)}


def skip(conn, qid: str) -> dict:
    """Skip a question: it is not asked again. Gives back {line: None, question: the next one}. Skipping twice
    changes nothing."""
    q = _question(qid)
    conn.execute("INSERT OR IGNORE INTO style_questions (id, state, at) VALUES (?, ?, ?)", (q.id, SKIPPED, db.now()))
    return {"line": None, "question": next_question(conn)}


def undo(conn, qid: str) -> dict:
    """Take back the answer to a question (or a skip): its line comes out of the style profile when it is still
    there, and the question is asked again. Gives back {line: None, question: the next one}."""
    q = _question(qid)
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT line_id FROM style_questions WHERE id = ?", (q.id,)).fetchone()
        if row is not None and row["line_id"] is not None:
            try:
                styleprofile.remove_line(conn, row["line_id"])
            except LookupError:
                pass   # removed in Settings since
        conn.execute("DELETE FROM style_questions WHERE id = ?", (q.id,))
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return {"line": None, "question": next_question(conn)}
