"""Succès à débloquer. Chaque test reçoit les données de progression et le résumé de session."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Badge:
    id: str
    name: str
    desc: str
    test: Callable


def _themes(d: dict):
    return d["themes"].values()


def _mastered(d: dict) -> int:
    return sum(1 for t in _themes(d) if 3 in t["cleared"])


BADGES = [
    Badge("first_steps", "Premiers pas", "Terminer ta première série.",
          lambda d, s: d["sessions"] >= 1),
    Badge("perfect", "Sans faute", "Réussir une série parfaite.",
          lambda d, s: s is not None and s.total >= 5 and s.correct == s.total),
    Badge("streak10", "Série de 10", "Enchaîner 10 bonnes réponses d'affilée.",
          lambda d, s: d["best_streak"] >= 10),
    Badge("tier_up", "Montée en grade", "Réussir un niveau et débloquer le suivant.",
          lambda d, s: any(t["cleared"] for t in _themes(d))),
    Badge("master", "Maître d'un thème", "Réussir le niveau 3 d'un thème.",
          lambda d, s: _mastered(d) >= 1),
    Badge("explorer", "Explorateur", "Jouer dans 5 thèmes différents.",
          lambda d, s: sum(1 for t in _themes(d) if t["sessions"] > 0) >= 5),
    Badge("writer", "Plume d'or", "25 bonnes réponses écrites au clavier.",
          lambda d, s: d["typed_correct"] >= 25),
    Badge("regular", "Assidu", "Jouer 3 jours de suite.",
          lambda d, s: d["day_streak"] >= 3),
    Badge("centurion", "Centurion", "100 bonnes réponses au total.",
          lambda d, s: d["correct"] >= 100),
    Badge("review", "Je m'améliore", "Réussir une série de révision des erreurs.",
          lambda d, s: s is not None and s.mode == "review" and s.total >= 3
          and s.correct / s.total >= 0.8),
    Badge("academician", "Académicien", "Maîtriser 5 thèmes.",
          lambda d, s: _mastered(d) >= 5),
    Badge("level5", "Niveau 5", "Atteindre le niveau 5.",
          lambda d, s: d["level"] >= 5),
]

BADGES_BY_ID = {b.id: b for b in BADGES}
