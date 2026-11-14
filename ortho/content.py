"""Chargement et validation des thèmes / questions (fichiers JSON)."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

BLANK = "___"
LEVELS = (1, 2, 3)


@dataclass(frozen=True)
class Question:
    id: str
    theme_id: str
    lvl: int
    text: str
    answers: tuple          # réponses acceptées ; answers[0] = réponse affichée
    choices: tuple = ()     # vide => question à saisir au clavier
    why: str = ""

    @property
    def is_qcm(self) -> bool:
        return len(self.choices) > 0

    @property
    def expected(self) -> str:
        return self.answers[0]

    def solution_line(self) -> str:
        """Phrase corrigée, pour le récapitulatif de fin de session."""
        if BLANK in self.text:
            return self.text.replace(BLANK, self.expected, 1)
        return f"{self.text}  →  {self.expected}"


@dataclass
class Theme:
    id: str
    title: str
    subtitle: str = ""
    rule: str = ""
    version: int = 1
    order: int = 100
    questions: list = field(default_factory=list)

    def by_level(self, lvl: int) -> list:
        return [q for q in self.questions if q.lvl == lvl]


# ----------------------------------------------------------------- texte

def normalize(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("`", "'")
    return re.sub(r"\s+", " ", s.strip()).casefold()


def strip_accents(s: str) -> str:
    s = s.replace("œ", "oe").replace("æ", "ae")
    d = unicodedata.normalize("NFD", s)
    return "".join(c for c in d if unicodedata.category(c) != "Mn")


def check_answer(q: Question, given: str) -> str:
    """Retourne 'ok', 'almost' (bon mot mais accents faux, saisie seulement) ou 'ko'."""
    if q.is_qcm:
        return "ok" if given == q.expected else "ko"
    g = normalize(given)
    if not g:
        return "ko"
    targets = [normalize(a) for a in q.answers]
    if g in targets:
        return "ok"
    if strip_accents(g) in [strip_accents(t) for t in targets]:
        return "almost"
    return "ko"


# ------------------------------------------------------------- validation

def question_id(theme_id: str, text: str, answer: str) -> str:
    return hashlib.md5(f"{theme_id}|{text}|{answer}".encode("utf-8")).hexdigest()[:10]


def _to_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_theme(data) -> tuple:
    """Retourne (Theme | None, [erreurs]). Les questions invalides sont ignorées."""
    errors: list = []
    if not isinstance(data, dict):
        return None, ["Le fichier doit contenir un objet JSON."]
    tid, title = data.get("id"), data.get("title")
    if not isinstance(tid, str) or not re.fullmatch(r"[a-z0-9_]+", tid):
        errors.append("« id » manquant ou invalide (minuscules, chiffres et _ seulement).")
    if not isinstance(title, str) or not title.strip():
        errors.append("« title » manquant.")
    raw = data.get("questions")
    if not isinstance(raw, list) or not raw:
        errors.append("« questions » doit être une liste non vide.")
    if errors:
        return None, errors

    theme = Theme(
        id=tid,
        title=title.strip(),
        subtitle=str(data.get("subtitle", "")),
        rule=str(data.get("rule", "")),
        version=_to_int(data.get("version"), 1),
        order=_to_int(data.get("order"), 100),
    )
    seen = set()
    for i, r in enumerate(raw, 1):
        where = f"question n°{i}"
        if not isinstance(r, dict):
            errors.append(f"{where} : doit être un objet.")
            continue
        text, lvl, ans = r.get("q"), r.get("lvl"), r.get("answer")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{where} : « q » manquant.")
            continue
        where = f"question n°{i} ({text[:30]}…)"
        if lvl not in LEVELS:
            errors.append(f"{where} : « lvl » doit valoir 1, 2 ou 3.")
            continue
        answers = [ans] if isinstance(ans, str) else ans
        if (not isinstance(answers, list) or not answers
                or not all(isinstance(a, str) and a.strip() for a in answers)):
            errors.append(f"{where} : « answer » doit être un texte ou une liste de textes.")
            continue
        choices = r.get("choices") or []
        if choices:
            if (not isinstance(choices, list) or not all(isinstance(c, str) for c in choices)
                    or not 2 <= len(choices) <= 6):
                errors.append(f"{where} : « choices » doit contenir 2 à 6 textes.")
                continue
            if len(set(choices)) != len(choices):
                errors.append(f"{where} : « choices » contient des doublons.")
                continue
            if answers[0] not in choices:
                errors.append(f"{where} : la réponse « {answers[0]} » n'est pas dans « choices ».")
                continue
        elif BLANK not in text and "(" not in text:
            errors.append(f"{where} : question à saisir sans trou (___) ni consigne entre parenthèses.")
            continue
        qid = question_id(tid, text, answers[0])
        if qid in seen:
            errors.append(f"{where} : doublon.")
            continue
        seen.add(qid)
        theme.questions.append(Question(
            id=qid, theme_id=tid, lvl=lvl, text=text.strip(), answers=tuple(answers),
            choices=tuple(choices), why=str(r.get("why", "")),
        ))
    if not theme.questions:
        return None, errors or ["Aucune question valide."]
    return theme, errors


def parse_theme_bytes(raw: bytes) -> tuple:
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        return None, [f"JSON invalide : {exc}"]
    return parse_theme(data)


def _read_dir(folder) -> list:
    out = []
    if folder and Path(folder).is_dir():
        for p in sorted(Path(folder).glob("*.json")):
            theme, _errors = parse_theme_bytes(p.read_bytes())
            if theme:
                out.append(theme)
    return out


def load_themes(bundled_dir, cache_dir=None) -> list:
    """Thèmes embarqués + thèmes mis à jour. À version égale, la mise à jour gagne."""
    chosen: dict = {t.id: t for t in _read_dir(bundled_dir)}
    for t in _read_dir(cache_dir):
        cur = chosen.get(t.id)
        if cur is None or t.version >= cur.version:
            chosen[t.id] = t
    return sorted(chosen.values(), key=lambda t: (t.order, t.title.casefold()))
