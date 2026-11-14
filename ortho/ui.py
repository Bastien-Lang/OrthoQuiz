"""Interface graphique (Tkinter). Direction visuelle : le cahier d'école.

- la phrase à compléter est écrite sur du papier Seyès (lignes bleutées + marge rouge),
- chaque thème est un cahier à couverture colorée,
- le mot correct est surligné au « surligneur » après chaque réponse.
"""
from __future__ import annotations

import queue
import re
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox

from . import APP_NAME, APP_VERSION, content, updater
from . import session as sess
from .badges import BADGES
from .content import BLANK
from .paths import resource, updates_dir, user_dir
from .progress import PASS_RATIO, Progress, level_from_xp

C = dict(
    bg="#E8EBF6", card="#FFFFFF", border="#C8CDE8", paper="#FDFDFF", rule="#D9DDF3",
    margin="#E58A98", ink="#1A1F3D", muted="#5F6788", primary="#24348F",
    primary_dark="#1B2870", highlight="#FFE66D", gold="#E0A800", good="#17744B",
    good_bg="#D8F3E4", bad="#C2283D", bad_bg="#FBE1E5", warn_bg="#FFF1C2", warn="#8A5A00",
    track="#D9DDF3", hover="#F1F3FC", disabled="#B9BFE0",
)
COVERS = ["#2B4BC2", "#C8323F", "#17794F", "#6B46C1", "#0E7490", "#B45309"]

SERIF = SANS = "TkDefaultFont"


def init_fonts(root) -> None:
    global SERIF, SANS
    families = set(tkfont.families(root))
    default = tkfont.nametofont("TkDefaultFont").actual("family")
    SERIF = next((f for f in ("Georgia", "Cambria", "Times New Roman") if f in families), default)
    SANS = next((f for f in ("Segoe UI", "Calibri", "Arial") if f in families), default)


def sans(size: int, weight: str = "normal"):
    return (SANS, size, weight)


def serif(size: int, weight: str = "normal"):
    return (SERIF, size, weight)


# ============================================================ widgets

class Btn(tk.Button):
    KINDS = {
        "primary": (C["primary"], "#FFFFFF", C["primary_dark"], C["disabled"]),
        "ghost": (C["card"], C["ink"], C["hover"], C["hover"]),
    }

    def __init__(self, parent, text, command, kind="primary", size=12, **kw):
        bg, fg, hover, off = self.KINDS[kind]
        super().__init__(
            parent, text=text, command=command, bg=bg, fg=fg, activebackground=hover,
            activeforeground=fg, disabledforeground="#FFFFFF" if kind == "primary" else C["disabled"],
            relief="flat", bd=0, padx=18, pady=9, font=sans(size, "bold"), cursor="hand2",
            takefocus=0, highlightthickness=1, highlightbackground=C["border"] if kind == "ghost" else bg,
            **kw)
        self._bg, self._hover, self._off = bg, hover, off
        self.bind("<Enter>", lambda e: self._tint(self._hover))
        self.bind("<Leave>", lambda e: self._tint(self._bg))

    def _tint(self, color):
        if str(self["state"]) == "normal":
            self.configure(bg=color)

    def set_enabled(self, on: bool) -> None:
        self.configure(state="normal" if on else "disabled", bg=self._bg if on else self._off,
                       cursor="hand2" if on else "arrow")


class Bar(tk.Canvas):
    def __init__(self, parent, height=10, fill=None, track=None):
        super().__init__(parent, height=height, highlightthickness=0, bd=0, bg=parent["bg"])
        self.value = 0.0
        self.fill = fill or C["primary"]
        self.track = track or C["track"]
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, value: float) -> None:
        self.value = max(0.0, min(1.0, value))
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        self.create_rectangle(0, 0, w, h, fill=self.track, outline="")
        if self.value > 0:
            self.create_rectangle(0, 0, int(w * self.value), h, fill=self.fill, outline="")


class ScrollFrame(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=C["bg"])
        self.canvas = tk.Canvas(self, bg=C["bg"], highlightthickness=0, bd=0)
        self.vsb = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=C["bg"])
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))

    def bind_wheel(self) -> None:
        self.bind_all("<MouseWheel>", self._wheel)
        self.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))

    def unbind_wheel(self) -> None:
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.unbind_all(ev)

    def _wheel(self, e) -> None:
        if self.inner.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")


class Notebook(tk.Canvas):
    """Page de cahier Seyès sur laquelle la phrase est écrite, mot après mot, sur les lignes."""

    def __init__(self, parent, scale: float):
        self.scale = scale
        self.font = tkfont.Font(family=SERIF, size=24)
        self.bold = tkfont.Font(family=SERIF, size=24, weight="bold")
        self.step = self.font.metrics("linespace") + int(12 * scale)
        super().__init__(parent, bg=C["paper"], bd=0, highlightthickness=1,
                         highlightbackground=C["border"], height=self.step * 5)
        self.text, self.fill = "", None
        self.bind("<Configure>", lambda e: self.redraw())

    def set_sentence(self, text: str, fill=None) -> None:
        self.text, self.fill = text, fill
        self.redraw()

    def _segments(self):
        if BLANK in self.text:
            before, after = self.text.split(BLANK, 1)
            mid = (self.fill, "good") if self.fill else ("_____", "blank")
            return [(before, "n"), mid, (after, "n")]
        return [(self.text, "n")]

    def _style(self, st):
        if st == "n":
            return self.font, C["ink"]
        if st == "blank":
            return self.bold, C["primary"]
        return self.bold, C["good"]

    def _layout(self, maxw: int):
        words: list = [[]]
        for text, st in self._segments():
            for part in re.split(r"(\s+)", text):
                if not part:
                    continue
                if part.isspace():
                    if words[-1]:
                        words.append([])
                else:
                    words[-1].append((part, st))
        words = [w for w in words if w]
        space = self.font.measure(" ")
        lines: list = [[]]
        used = 0
        for w in words:
            ww = sum(self._style(st)[0].measure(t) for t, st in w)
            add = ww if not lines[-1] else space + ww
            if lines[-1] and used + add > maxw:
                lines.append([])
                used, add = 0, ww
            lines[-1].append((w, ww))
            used += add
        return lines

    def redraw(self) -> None:
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 80 or not self.text:
            return
        step = self.step
        for y in range(step, h, step):
            self.create_line(0, y, w, y, fill=C["rule"])
        mx = int(64 * self.scale)
        self.create_line(mx, 0, mx, h, fill=C["margin"], width=2)
        maxw = w - mx - int(40 * self.scale)
        lines = self._layout(maxw)
        usable = max(1, h // step - 1)
        lines = lines[:usable]
        first = 1 + (usable - len(lines)) // 2
        desc, asc = self.font.metrics("descent"), self.font.metrics("ascent")
        space = self.font.measure(" ")
        for k, line in enumerate(lines):
            base = (first + k) * step - 2
            total = sum(ww for _, ww in line) + space * (len(line) - 1)
            x = mx + int(20 * self.scale) + max(0, maxw - total) / 2
            for wi, (word, _ww) in enumerate(line):
                for text, st in word:
                    font, color = self._style(st)
                    tw = font.measure(text)
                    if st == "good":
                        self.create_rectangle(x - 4, base - asc - 2, x + tw + 4, base + desc + 2,
                                              fill=C["good_bg"], outline="")
                    self.create_text(x, base + desc, text=text, anchor="sw", font=font, fill=color)
                    x += tw
                x += space


def _bind_click(widget, fn) -> None:
    widget.bind("<Button-1>", lambda e: fn())
    for child in widget.winfo_children():
        _bind_click(child, fn)


# ============================================================ écrans

class HomeScreen(tk.Frame):
    def __init__(self, app):
        super().__init__(app.container, bg=C["bg"])
        self.app = app

        header = tk.Frame(self, bg=C["bg"])
        header.pack(fill="x", padx=28, pady=(22, 6))
        left = tk.Frame(header, bg=C["bg"])
        left.pack(side="left")
        tk.Label(left, text=APP_NAME, font=serif(30, "bold"), fg=C["primary"], bg=C["bg"]).pack(anchor="w")
        tk.Label(left, text="Entraîne-toi à l'orthographe, un niveau après l'autre.",
                 font=sans(11), fg=C["muted"], bg=C["bg"]).pack(anchor="w")

        card = tk.Frame(header, bg=C["card"], highlightbackground=C["border"], highlightthickness=1)
        card.pack(side="right")
        inner = tk.Frame(card, bg=C["card"])
        inner.pack(padx=16, pady=10)
        self.level_lbl = tk.Label(inner, font=sans(13, "bold"), fg=C["ink"], bg=C["card"])
        self.level_lbl.pack(anchor="w")
        self.xp_bar = Bar(inner, height=10, fill=C["gold"])
        self.xp_bar.pack(fill="x", pady=(6, 3))
        self.xp_lbl = tk.Label(inner, font=sans(9), fg=C["muted"], bg=C["card"])
        self.xp_lbl.pack(anchor="w")
        self.day_lbl = tk.Label(inner, font=sans(9), fg=C["muted"], bg=C["card"])
        self.day_lbl.pack(anchor="w")

        actions = tk.Frame(self, bg=C["bg"])
        actions.pack(fill="x", padx=28, pady=(14, 4))
        Btn(actions, "Défi mixte", app.start_mix).pack(side="left")
        self.review_btn = Btn(actions, "Revoir mes erreurs", app.start_review, "ghost")
        self.review_btn.pack(side="left", padx=10)
        self.badges_btn = Btn(actions, "Succès", lambda: app.show("badges"), "ghost")
        self.badges_btn.pack(side="left")

        tk.Label(self, text="Choisis un cahier", font=serif(15, "bold"), fg=C["ink"],
                 bg=C["bg"]).pack(anchor="w", padx=28, pady=(12, 0))
        self.status = tk.Label(self, text="", font=sans(9), fg=C["muted"], bg=C["bg"], anchor="w")
        self.status.pack(side="bottom", fill="x", padx=28, pady=(0, 8))
        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=20, pady=(4, 4))

    def set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def on_show(self) -> None:
        self.refresh()
        self.scroll.bind_wheel()

    def on_hide(self) -> None:
        self.scroll.unbind_wheel()

    def refresh(self) -> None:
        p = self.app.progress
        info = p.level_info()
        self.level_lbl.configure(text=f"Niveau {info.level} · {info.title}")
        self.xp_bar.set(info.ratio)
        self.xp_lbl.configure(text=f"{info.into} / {info.needed} XP pour le niveau suivant")
        days = p.data["day_streak"]
        self.day_lbl.configure(text=f"{days} jour{'s' if days > 1 else ''} de suite" if days else "")
        n = p.count_review(self.app.themes)
        self.review_btn.configure(text=f"Revoir mes erreurs ({n})")
        self.badges_btn.configure(text=f"Succès ({len(p.data['badges'])}/{len(BADGES)})")

        for child in self.scroll.inner.winfo_children():
            child.destroy()
        cols = 3
        for c in range(cols):
            self.scroll.inner.columnconfigure(c, weight=1, uniform="cols")
        for i, theme in enumerate(self.app.themes):
            self._card(theme, i).grid(row=i // cols, column=i % cols, sticky="nsew", padx=8, pady=8)

    def _card(self, theme, idx: int):
        st = self.app.progress.theme_state(theme.id)
        cover = COVERS[idx % len(COVERS)]
        card = tk.Frame(self.scroll.inner, bg=C["card"], highlightbackground=C["border"],
                        highlightthickness=1, cursor="hand2")
        top = tk.Frame(card, bg=cover)
        top.pack(fill="x")
        tk.Label(top, text=theme.title, bg=cover, fg="#FFFFFF", font=serif(16, "bold"),
                 anchor="w", justify="left", wraplength=230).pack(fill="x", padx=14, pady=12)
        body = tk.Frame(card, bg=C["card"])
        body.pack(fill="both", expand=True)
        tk.Label(body, text=theme.subtitle, bg=C["card"], fg=C["muted"], font=sans(10),
                 anchor="w", justify="left", wraplength=230).pack(fill="x", padx=14, pady=(10, 4))
        row = tk.Frame(body, bg=C["card"])
        row.pack(fill="x", padx=14, pady=(2, 12))
        cleared = st["cleared"]
        stars = "".join("★" if t in cleared else "☆" for t in (1, 2, 3))
        tk.Label(row, text=stars, fg=C["gold"], bg=C["card"], font=sans(16)).pack(side="left")
        label = "Maîtrisé" if 3 in cleared else f"Niveau {st['tier']}"
        tk.Label(row, text=label, fg=C["muted"], bg=C["card"], font=sans(10, "bold")).pack(side="right")
        _bind_click(card, lambda t=theme: self.app.start_theme(t))
        card.bind("<Enter>", lambda e: card.configure(highlightbackground=C["primary"]))
        card.bind("<Leave>", lambda e: card.configure(highlightbackground=C["border"]))
        return card


class QuizScreen(tk.Frame):
    def __init__(self, app):
        super().__init__(app.container, bg=C["bg"])
        self.app = app
        self.session = None
        self.entry = None
        self.choice_buttons: list = []
        self.answered = False

        top = tk.Frame(self, bg=C["bg"])
        top.pack(fill="x", padx=28, pady=(18, 6))
        Btn(top, "‹ Menu", self.on_back, "ghost", size=10).pack(side="left")
        self.title_lbl = tk.Label(top, font=serif(15, "bold"), fg=C["ink"], bg=C["bg"])
        self.title_lbl.pack(side="left", padx=14)
        self.stats_lbl = tk.Label(top, font=sans(12, "bold"), fg=C["muted"], bg=C["bg"])
        self.stats_lbl.pack(side="right")

        prog = tk.Frame(self, bg=C["bg"])
        prog.pack(fill="x", padx=28)
        self.bar = Bar(prog, height=10)
        self.bar.pack(fill="x")
        self.count_lbl = tk.Label(prog, font=sans(10), fg=C["muted"], bg=C["bg"])
        self.count_lbl.pack(anchor="w", pady=(4, 0))

        self.next_btn = Btn(self, "Suivant  ➜", self.on_next, "primary", size=13)
        self.next_btn.pack(side="bottom", pady=(4, 20))

        self.notebook = Notebook(self, app.scale)
        self.notebook.pack(fill="x", padx=28, pady=(12, 10))
        self.answer_area = tk.Frame(self, bg=C["bg"])
        self.answer_area.pack(fill="x", padx=28)
        self.fb = tk.Frame(self, bg=C["bg"])
        self.fb.pack(fill="x", padx=28, pady=12)
        self.fb_title = tk.Label(self.fb, font=sans(14, "bold"), bg=C["bg"], anchor="w", justify="left")
        self.fb_title.pack(fill="x", padx=14, pady=(10, 0))
        self.fb_text = tk.Label(self.fb, font=sans(11), bg=C["bg"], anchor="w", justify="left")
        self.fb_text.pack(fill="x", padx=14, pady=(2, 10))
        self.fb.bind("<Configure>", lambda e: (self.fb_title.configure(wraplength=e.width - 30),
                                               self.fb_text.configure(wraplength=e.width - 30)))

    # ------------------------------------------------------------ cycle
    def on_show(self, session) -> None:
        self.session = session
        s = session.summary
        suffix = f" · niveau {s.tier}" if s.mode == "theme" and not self.app.progress.is_mastered(s.theme_id) else ""
        self.title_lbl.configure(text=s.title + suffix)
        self._show_question()

    def on_hide(self) -> None:
        pass

    def _show_question(self) -> None:
        s = self.session
        q = s.current
        self.answered = False
        self.count_lbl.configure(text=f"Question {s.index + 1} sur {s.total}")
        self.bar.set(s.index / s.total)
        self.notebook.set_sentence(q.text)
        self._set_feedback(C["bg"], C["bg"], "", "")
        for w in self.answer_area.winfo_children():
            w.destroy()
        self.choice_buttons, self.entry = [], None
        if q.is_qcm:
            self._build_choices()
        else:
            self._build_entry()
        self.next_btn.set_enabled(False)
        self.next_btn.configure(text="Terminer" if s.index == s.total - 1 else "Suivant  ➜")
        self._update_stats()

    def _update_stats(self) -> None:
        s = self.session
        text = f"✓ {s.summary.correct}"
        if s.streak >= 2:
            text += f"    ⚡ {s.streak}"
        self.stats_lbl.configure(text=text)

    # --------------------------------------------------------- questions
    def _build_choices(self) -> None:
        area = self.answer_area
        area.columnconfigure((0, 1), weight=1, uniform="ch")
        for i, choice in enumerate(self.session.choices):
            b = tk.Button(
                area, text=f"{i + 1}    {choice}", font=serif(19, "bold"), bg=C["card"], fg=C["ink"],
                activebackground=C["hover"], activeforeground=C["ink"], relief="flat", bd=0,
                highlightthickness=2, highlightbackground=C["border"], padx=10, pady=14,
                cursor="hand2", takefocus=0, command=lambda i=i: self.choose(i))
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=6, pady=6)
            b.bind("<Enter>", lambda e, b=b: None if self.answered else b.configure(bg=C["hover"]))
            b.bind("<Leave>", lambda e, b=b: None if self.answered else b.configure(bg=C["card"]))
            self.choice_buttons.append(b)

    def _build_entry(self) -> None:
        wrap = tk.Frame(self.answer_area, bg=C["bg"])
        wrap.pack(pady=4)
        self.entry = tk.Entry(
            wrap, font=serif(22), justify="center", width=22, relief="flat", bg=C["card"],
            fg=C["ink"], insertbackground=C["ink"], highlightthickness=2,
            highlightbackground=C["border"], highlightcolor=C["primary"],
            readonlybackground=C["card"])
        self.entry.pack(ipady=8)
        buttons = tk.Frame(wrap, bg=C["bg"])
        buttons.pack(pady=(10, 0))
        Btn(buttons, "Valider", self.validate, "primary").pack(side="left", padx=6)
        self.hint_btn = Btn(buttons, "Indice (XP ÷ 2)", self.hint, "ghost", size=10)
        self.hint_btn.pack(side="left", padx=6)
        self.hint_lbl = tk.Label(wrap, text="", font=sans(11), fg=C["muted"], bg=C["bg"])
        self.hint_lbl.pack(pady=(8, 0))
        self.after(60, self.entry.focus_set)

    def hint(self) -> None:
        if not self.answered and self.entry is not None:
            self.hint_lbl.configure(text=self.session.hint_text())
            self.entry.focus_set()

    # ----------------------------------------------------------- réponses
    def choose(self, index: int) -> None:
        if self.answered:
            return
        res = self.session.answer(self.session.choices[index])
        self._after_answer(res, chosen=index)

    def validate(self) -> None:
        if self.answered or self.entry is None or not self.entry.get().strip():
            return
        res = self.session.answer(self.entry.get())
        self._after_answer(res)

    def _after_answer(self, res, chosen=None) -> None:
        self.answered = True
        q = self.session.current
        self.notebook.set_sentence(q.text, fill=res.expected)
        if q.is_qcm:
            for i, b in enumerate(self.choice_buttons):
                value = self.session.choices[i]
                if value == res.expected:
                    b.configure(bg=C["good_bg"], highlightbackground=C["good"], fg=C["good"])
                elif i == chosen:
                    b.configure(bg=C["bad_bg"], highlightbackground=C["bad"], fg=C["bad"])
                else:
                    b.configure(bg=C["card"], fg=C["muted"])
                b.configure(state="disabled", cursor="arrow", disabledforeground=b.cget("fg"))
        elif self.entry is not None:
            color = C["good_bg"] if res.correct else (C["warn_bg"] if res.almost else C["bad_bg"])
            self.entry.configure(state="readonly", readonlybackground=color)
            self.hint_btn.set_enabled(False)

        rule = q.why or self.app.theme_rule(q.theme_id)
        if res.correct:
            title = "✓ Bravo !" + (f"    +{res.xp} XP" if res.xp else "")
            self._set_feedback(C["good_bg"], C["good"], title, q.why)
        elif res.almost:
            self._set_feedback(C["warn_bg"], C["warn"], "Presque ! Attention aux accents.",
                               f"On écrit : {res.expected}.  {q.why}".strip())
        else:
            title = f"✗ La bonne réponse est : {res.expected}"
            if not q.is_qcm:
                title += f"      (tu as écrit : {res.given.strip()})"
            self._set_feedback(C["bad_bg"], C["bad"], title, rule)
        self.next_btn.set_enabled(True)
        self._update_stats()

    def _set_feedback(self, bg, fg, title, detail) -> None:
        self.fb.configure(bg=bg)
        self.fb_title.configure(bg=bg, fg=fg, text=title)
        self.fb_text.configure(bg=bg, fg=C["ink"], text=detail)

    # ------------------------------------------------------- navigation
    def on_next(self) -> None:
        if not self.answered:
            return
        s = self.session
        s.next()
        if s.finished:
            self.app.finish_session(s)
        else:
            self._show_question()

    def on_back(self) -> None:
        if messagebox.askyesno("Quitter la série ?",
                               "Tes réponses déjà données sont conservées.\nRetourner au menu ?"):
            self.app.progress.save()
            self.app.show("home")

    def on_key(self, e) -> None:
        if e.keysym in ("Return", "KP_Enter"):
            if self.answered:
                self.on_next()
            elif self.entry is not None:
                self.validate()
        elif self.answered and e.keysym == "space":
            self.on_next()
        elif not self.answered and self.entry is None and e.char and e.char in "123456":
            i = int(e.char) - 1
            if i < len(self.choice_buttons):
                self.choose(i)


class ResultScreen(tk.Frame):
    def __init__(self, app):
        super().__init__(app.container, bg=C["bg"])
        self.app = app
        self.body = tk.Frame(self, bg=C["bg"])
        self.body.pack(fill="both", expand=True, padx=40, pady=24)

    def on_hide(self) -> None:
        pass

    def on_show(self, session, outcome) -> None:
        for w in self.body.winfo_children():
            w.destroy()
        s = session.summary
        acc = s.accuracy
        headline = "Excellent !" if acc >= 0.9 else "Bien joué !" if acc >= 0.7 else "Continue, tu progresses !"
        tk.Label(self.body, text=headline, font=serif(28, "bold"), fg=C["primary"], bg=C["bg"]).pack()
        tk.Label(self.body, text=f"{s.correct} / {s.total}", font=serif(44, "bold"), fg=C["ink"],
                 bg=C["bg"]).pack(pady=(4, 0))
        stars = 3 if acc >= 1 else 2 if acc >= 0.8 else 1 if acc >= 0.6 else 0
        tk.Label(self.body, text="★" * stars + "☆" * (3 - stars), font=sans(26), fg=C["gold"],
                 bg=C["bg"]).pack()

        card = tk.Frame(self.body, bg=C["card"], highlightbackground=C["border"], highlightthickness=1)
        card.pack(fill="x", pady=14)
        inner = tk.Frame(card, bg=C["card"])
        inner.pack(fill="x", padx=20, pady=14)
        info = level_from_xp(self.app.progress.xp)
        tk.Label(inner, text=f"+{outcome.xp_gained} XP", font=sans(16, "bold"), fg=C["ink"],
                 bg=C["card"]).pack(anchor="w")
        bar = Bar(inner, height=10, fill=C["gold"])
        bar.pack(fill="x", pady=6)
        self.after(50, lambda: bar.set(info.ratio))
        tk.Label(inner, text=f"Niveau {info.level} · {info.title}   ({info.into} / {info.needed} XP)",
                 font=sans(10), fg=C["muted"], bg=C["card"]).pack(anchor="w")
        if outcome.leveled_up:
            self._note(inner, f"Niveau supérieur ! Tu es maintenant {info.title}.", C["good"])
        if outcome.mastered_now:
            self._note(inner, "Thème maîtrisé ! Tu as réussi le niveau 3.", C["good"])
        elif outcome.tier_cleared:
            self._note(inner, f"Niveau {outcome.tier_cleared} réussi ! Le niveau suivant est débloqué.", C["good"])
        elif s.mode == "theme" and not self.app.progress.is_mastered(s.theme_id):
            self._note(inner, f"Il faut {int(PASS_RATIO * 100)} % de bonnes réponses pour passer au niveau suivant.",
                       C["muted"])
        for b in outcome.new_badges:
            self._note(inner, f"Succès débloqué : {b.name} — {b.desc}", C["primary"])

        if s.wrong:
            tk.Label(self.body, text="À retenir", font=serif(14, "bold"), fg=C["ink"],
                     bg=C["bg"]).pack(anchor="w")
            for q in s.wrong[:6]:
                tk.Label(self.body, text="✗  " + q.solution_line(), font=sans(11), fg=C["bad"],
                         bg=C["bg"], anchor="w", justify="left", wraplength=800).pack(fill="x", pady=1)

        row = tk.Frame(self.body, bg=C["bg"])
        row.pack(side="bottom", pady=(14, 0))
        Btn(row, "Rejouer", self.app.replay, "primary", size=13).pack(side="left", padx=8)
        Btn(row, "Menu", lambda: self.app.show("home"), "ghost", size=13).pack(side="left", padx=8)

    @staticmethod
    def _note(parent, text, color) -> None:
        tk.Label(parent, text=text, font=sans(11, "bold"), fg=color, bg=C["card"], anchor="w",
                 justify="left", wraplength=760).pack(fill="x", pady=(6, 0))


class BadgesScreen(tk.Frame):
    def __init__(self, app):
        super().__init__(app.container, bg=C["bg"])
        self.app = app
        top = tk.Frame(self, bg=C["bg"])
        top.pack(fill="x", padx=28, pady=(18, 6))
        Btn(top, "‹ Menu", lambda: app.show("home"), "ghost", size=10).pack(side="left")
        tk.Label(top, text="Succès", font=serif(22, "bold"), fg=C["primary"], bg=C["bg"]).pack(side="left", padx=14)
        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=20, pady=8)

    def on_show(self) -> None:
        self.scroll.bind_wheel()
        for w in self.scroll.inner.winfo_children():
            w.destroy()
        got = self.app.progress.data["badges"]
        for b in BADGES:
            ok = b.id in got
            row = tk.Frame(self.scroll.inner, bg=C["card"], highlightbackground=C["border"], highlightthickness=1)
            row.pack(fill="x", padx=8, pady=5)
            tk.Label(row, text="★" if ok else "☆", font=sans(22), fg=C["gold"] if ok else C["disabled"],
                     bg=C["card"], width=3).pack(side="left", pady=8)
            text = tk.Frame(row, bg=C["card"])
            text.pack(side="left", fill="x", expand=True, pady=8)
            tk.Label(text, text=b.name, font=sans(13, "bold"), fg=C["ink"] if ok else C["muted"],
                     bg=C["card"], anchor="w").pack(fill="x")
            tk.Label(text, text=b.desc + (f"   (obtenu le {got[b.id]})" if ok else ""),
                     font=sans(10), fg=C["muted"], bg=C["card"], anchor="w").pack(fill="x")

    def on_hide(self) -> None:
        self.scroll.unbind_wheel()


# ============================================================ application

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        init_fonts(self)
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.configure(bg=C["bg"])
        self.scale = max(1.0, self.winfo_fpixels("1i") / 96)
        w, h = int(980 * self.scale), int(740 * self.scale)
        w, h = min(w, self.winfo_screenwidth() - 40), min(h, self.winfo_screenheight() - 80)
        self.geometry(f"{w}x{h}+{(self.winfo_screenwidth() - w) // 2}+{max(0, (self.winfo_screenheight() - h) // 3)}")
        self.minsize(int(820 * self.scale), int(640 * self.scale))
        try:
            self.iconbitmap(str(resource("assets", "icon.ico")))
        except tk.TclError:
            pass

        self.progress = Progress(user_dir() / "progress.json")
        self.themes: list = []
        self.reload_content()
        self.last_builder = None

        self.container = tk.Frame(self, bg=C["bg"])
        self.container.pack(fill="both", expand=True)
        self.screens = {
            "home": HomeScreen(self), "quiz": QuizScreen(self),
            "result": ResultScreen(self), "badges": BadgesScreen(self),
        }
        self.current = None
        self.bind("<Key>", self._on_key)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.show("home")
        self._start_update_check()

    # ---------------------------------------------------------- contenu
    def reload_content(self) -> None:
        self.themes = content.load_themes(resource("questions"), updates_dir())
        self._rules = {t.id: t.rule for t in self.themes}

    def theme_rule(self, theme_id: str) -> str:
        return self._rules.get(theme_id, "")

    # ------------------------------------------------------- navigation
    def show(self, name: str, **kw) -> None:
        if self.current is not None:
            hide = getattr(self.current, "on_hide", None)
            if hide:
                hide()
            self.current.pack_forget()
        self.current = self.screens[name]
        self.current.pack(fill="both", expand=True)
        self.current.on_show(**kw)

    def _on_key(self, event) -> None:
        handler = getattr(self.current, "on_key", None)
        if handler:
            handler(event)

    def _on_close(self) -> None:
        self.progress.save()
        self.destroy()

    # ---------------------------------------------------------- séries
    def _launch(self, builder) -> None:
        self.last_builder = builder
        session = builder()
        if session.total == 0:
            messagebox.showinfo("Rien à jouer", "Il n'y a pas de question disponible pour le moment.")
            return
        self.show("quiz", session=session)

    def start_theme(self, theme) -> None:
        self._launch(lambda: sess.build_theme_session(theme, self.progress))

    def start_mix(self) -> None:
        self._launch(lambda: sess.build_mix_session(self.themes, self.progress))

    def start_review(self) -> None:
        if self.progress.count_review(self.themes) == 0:
            messagebox.showinfo("Bravo !", "Aucune erreur à revoir pour le moment.")
            return
        self._launch(lambda: sess.build_review_session(self.themes, self.progress))

    def replay(self) -> None:
        if self.last_builder:
            self._launch(self.last_builder)
        else:
            self.show("home")

    def finish_session(self, session) -> None:
        outcome = self.progress.apply_session(session.summary)
        self.progress.save()
        self.show("result", session=session, outcome=outcome)

    # ------------------------------------------------------ mises à jour
    def _start_update_check(self) -> None:
        cfg = updater.load_config()
        if not cfg.get("repo"):
            self.screens["home"].set_status(f"Version {APP_VERSION}")
            return
        self.screens["home"].set_status("Recherche de nouvelles questions…")
        self._updates = queue.Queue()

        def work():
            self._updates.put(updater.sync(cfg["repo"], cfg.get("branch", "main"),
                                           resource("questions"), updates_dir()))
        threading.Thread(target=work, daemon=True).start()
        self.after(400, self._poll_updates)

    def _poll_updates(self) -> None:
        try:
            res = self._updates.get_nowait()
        except queue.Empty:
            self.after(400, self._poll_updates)
            return
        home = self.screens["home"]
        if res.status == "updated":
            self.reload_content()
            if self.current is home:
                home.refresh()
            home.set_status(f"Nouvelles questions installées ({res.message})  ·  Version {APP_VERSION}")
        elif res.status == "uptodate":
            home.set_status(f"Questions à jour  ·  Version {APP_VERSION}")
        else:
            home.set_status(f"{res.message}  ·  Version {APP_VERSION}")


def run() -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    App().mainloop()
