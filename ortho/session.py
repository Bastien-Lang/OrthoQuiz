"""Une série de questions : choix des questions, correction, calcul de l'XP."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .content import check_answer

SESSION_SIZE = 10
XP_QCM = 10
XP_TYPED = 15


@dataclass
class AnswerResult:
    correct: bool
    almost: bool
    expected: str
    given: str
    xp: int
    streak: int
    hint_used: bool = False


@dataclass
class SessionSummary:
    mode: str                 # "theme" | "mix" | "review"
    theme_id: str | None
    title: str
    tier: int
    total: int
    xp_start: int = 0
    correct: int = 0
    xp: int = 0
    best_streak: int = 0
    wrong: list = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


class Session:
    def __init__(self, questions, progress, mode: str, theme_id=None, title="",
                 tier: int = 1, rng: random.Random | None = None):
        self.questions = list(questions)
        self.progress = progress
        self.rng = rng or random.Random()
        self.index = 0
        self.streak = 0
        self.answered = False
        self.hint_used = False
        self.choices: list = []
        self.summary = SessionSummary(mode=mode, theme_id=theme_id, title=title, tier=tier,
                                      total=len(self.questions), xp_start=progress.xp)
        self._prepare()

    # ------------------------------------------------------------ état
    @property
    def total(self) -> int:
        return len(self.questions)

    @property
    def finished(self) -> bool:
        return self.index >= self.total

    @property
    def current(self):
        return self.questions[self.index]

    def _prepare(self) -> None:
        self.answered = False
        self.hint_used = False
        if not self.finished and self.current.is_qcm:
            self.choices = list(self.current.choices)
            self.rng.shuffle(self.choices)
        else:
            self.choices = []

    # ------------------------------------------------------------- actions
    def hint_text(self) -> str:
        self.hint_used = True
        word = self.current.expected
        return f"Commence par « {word[0]} » · {len(word)} lettres"

    def answer(self, given: str) -> AnswerResult:
        q = self.current
        verdict = check_answer(q, given)
        correct = verdict == "ok"
        xp = 0
        if correct:
            self.streak += 1
            base = XP_QCM if q.is_qcm else XP_TYPED
            xp = round(base * (1 + 0.5 * (q.lvl - 1))) + min(self.streak // 2, 5)
            if self.hint_used:
                xp //= 2
            self.summary.correct += 1
            self.summary.xp += xp
            self.summary.best_streak = max(self.summary.best_streak, self.streak)
        else:
            self.streak = 0
            self.summary.wrong.append(q)
        self.progress.record_answer(q, correct, xp)
        self.answered = True
        return AnswerResult(correct, verdict == "almost", q.expected, given, xp,
                            self.streak, self.hint_used)

    def next(self) -> None:
        self.index += 1
        self._prepare()


# ------------------------------------------------------------ sélection

def _weight(progress, q) -> float:
    st = progress.data["questions"].get(q.id)
    if st is None:
        return 2.0                       # jamais vue
    if progress.needs_review(q.id):
        return 4.0                       # ratée récemment
    return 1.0


def weighted_sample(pool, k: int, progress, rng) -> list:
    pool, out = list(pool), []
    while pool and len(out) < k:
        pick = rng.choices(pool, weights=[_weight(progress, q) for q in pool], k=1)[0]
        out.append(pick)
        pool.remove(pick)
    return out


def _tier_for_mix(progress, theme) -> int:
    st = progress.theme_state(theme.id)
    return 3 if 3 in st["cleared"] else st["tier"]


def build_theme_session(theme, progress, rng=None, size: int = SESSION_SIZE) -> Session:
    rng = rng or random.Random()
    st = progress.theme_state(theme.id)
    tier, mastered = st["tier"], 3 in st["cleared"]
    allowed = [q for q in theme.questions if mastered or q.lvl <= tier]
    cur = [q for q in allowed if mastered or q.lvl == tier]
    low = [] if mastered else [q for q in allowed if q.lvl < tier]
    n_low = size // 3 if low else 0
    picked = weighted_sample(cur, size - n_low, progress, rng)
    picked += weighted_sample(low, n_low, progress, rng)
    if len(picked) < size:                      # complète si un niveau est peu fourni
        ids = {q.id for q in picked}
        rest = [q for q in allowed if q.id not in ids]
        picked += weighted_sample(rest, size - len(picked), progress, rng)
    rng.shuffle(picked)
    return Session(picked, progress, "theme", theme.id, theme.title, tier, rng)


def build_mix_session(themes, progress, rng=None, size: int = SESSION_SIZE) -> Session:
    rng = rng or random.Random()
    pool = [q for t in themes for q in t.questions if q.lvl <= _tier_for_mix(progress, t)]
    picked = weighted_sample(pool, size, progress, rng)
    return Session(picked, progress, "mix", None, "Défi mixte", 1, rng)


def build_review_session(themes, progress, rng=None, size: int = SESSION_SIZE) -> Session:
    rng = rng or random.Random()
    pool = [q for t in themes for q in t.questions if progress.needs_review(q.id)]
    picked = rng.sample(pool, min(size, len(pool)))
    return Session(picked, progress, "review", None, "Mes erreurs", 1, rng)
