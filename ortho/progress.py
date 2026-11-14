"""Progression du joueur : XP, niveaux, paliers par thème, statistiques, succès."""
from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .badges import BADGES

PASS_RATIO = 0.8          # 80 % de bonnes réponses pour passer au niveau suivant
MIN_QUESTIONS_TO_PASS = 5

TITLES = [
    "Apprenti", "Curieux", "Lecteur", "Écrivain", "Correcteur",
    "Grammairien", "Érudit", "Académicien", "Maître des mots", "Légende",
]


@dataclass
class LevelInfo:
    level: int
    title: str
    into: int
    needed: int

    @property
    def ratio(self) -> float:
        return self.into / self.needed if self.needed else 1.0


def xp_for_level(n: int) -> int:
    """XP cumulée nécessaire pour atteindre le niveau n (niveau 1 = 0)."""
    return 50 * n * (n - 1)


def level_from_xp(xp: int) -> LevelInfo:
    n = 1
    while xp >= xp_for_level(n + 1):
        n += 1
    lo, hi = xp_for_level(n), xp_for_level(n + 1)
    return LevelInfo(n, TITLES[min(n, len(TITLES)) - 1], xp - lo, hi - lo)


@dataclass
class Outcome:
    xp_gained: int = 0
    level_before: int = 1
    level_after: int = 1
    tier_cleared: int | None = None
    mastered_now: bool = False
    new_badges: list = field(default_factory=list)
    accuracy: float = 0.0

    @property
    def leveled_up(self) -> bool:
        return self.level_after > self.level_before


def _defaults() -> dict:
    return {
        "version": 1, "xp": 0, "sessions": 0, "answered": 0, "correct": 0,
        "typed_correct": 0, "best_streak": 0, "level": 1,
        "themes": {}, "questions": {}, "badges": {},
        "last_day": "", "day_streak": 0,
    }


class Progress:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = self._load()

    # ------------------------------------------------------------ fichier
    def _load(self) -> dict:
        data = _defaults()
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except (OSError, ValueError):
            pass
        return data

    def save(self) -> None:
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass  # on ne bloque jamais le jeu pour une sauvegarde

    # --------------------------------------------------------------- accès
    @property
    def xp(self) -> int:
        return self.data["xp"]

    def level_info(self) -> LevelInfo:
        return level_from_xp(self.xp)

    def theme_state(self, tid: str) -> dict:
        return self.data["themes"].setdefault(
            tid, {"tier": 1, "cleared": [], "sessions": 0, "best": 0.0})

    def is_mastered(self, tid: str) -> bool:
        return 3 in self.theme_state(tid)["cleared"]

    def needs_review(self, qid: str) -> bool:
        st = self.data["questions"].get(qid)
        return bool(st) and st["ko"] > 0 and st["streak"] < 2

    def count_review(self, themes) -> int:
        return sum(1 for t in themes for q in t.questions if self.needs_review(q.id))

    # ------------------------------------------------------------ réponses
    def record_answer(self, q, correct: bool, xp: int = 0) -> None:
        d = self.data
        st = d["questions"].setdefault(q.id, {"ok": 0, "ko": 0, "streak": 0})
        d["answered"] += 1
        if correct:
            st["ok"] += 1
            st["streak"] += 1
            d["correct"] += 1
            d["xp"] += xp
            if not q.is_qcm:
                d["typed_correct"] += 1
        else:
            st["ko"] += 1
            st["streak"] = 0

    def _touch_day(self) -> None:
        d = self.data
        today = dt.date.today()
        if d["last_day"] == today.isoformat():
            return
        yesterday = (today - dt.timedelta(days=1)).isoformat()
        d["day_streak"] = d["day_streak"] + 1 if d["last_day"] == yesterday else 1
        d["last_day"] = today.isoformat()

    # ------------------------------------------------------------- séries
    def apply_session(self, s) -> Outcome:
        """Termine une série : paliers, bonus d'XP, jours consécutifs, succès."""
        d = self.data
        out = Outcome(level_before=level_from_xp(s.xp_start).level, accuracy=s.accuracy)
        d["sessions"] += 1
        d["best_streak"] = max(d["best_streak"], s.best_streak)
        self._touch_day()

        bonus = 0
        if s.total >= MIN_QUESTIONS_TO_PASS and s.correct == s.total:
            bonus += 20

        if s.mode == "theme" and s.theme_id:
            st = self.theme_state(s.theme_id)
            st["sessions"] += 1
            st["best"] = max(st["best"], round(s.accuracy, 3))
            passed = s.accuracy >= PASS_RATIO and s.total >= MIN_QUESTIONS_TO_PASS
            if passed and s.tier == st["tier"] and s.tier not in st["cleared"]:
                st["cleared"].append(s.tier)
                st["cleared"].sort()
                out.tier_cleared = s.tier
                out.mastered_now = s.tier == 3
                bonus += 50 * s.tier
                if st["tier"] < 3:
                    st["tier"] += 1

        d["xp"] += bonus
        out.xp_gained = s.xp + bonus
        d["level"] = level_from_xp(d["xp"]).level
        out.level_after = d["level"]

        today = dt.date.today().isoformat()
        for b in BADGES:
            if b.id not in d["badges"] and b.test(d, s):
                d["badges"][b.id] = today
                out.new_badges.append(b)
        return out
