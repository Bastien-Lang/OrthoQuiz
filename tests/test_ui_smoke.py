"""Test de fumée de l'interface avec un FAUX Tkinter (aucune fenêtre n'est ouverte).

Il vérifie que tout le code des écrans s'exécute sans erreur (accès à des attributs
inexistants, mauvais arguments, etc.). L'apparence réelle ne peut pas être testée ainsi.
"""
import importlib
import os
import random
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class W:
    """Widget factice : accepte tout, mémorise les options et les enfants."""

    def __init__(self, parent=None, **kw):
        self.parent, self.kw, self.kids = parent, dict(kw), []
        if isinstance(parent, W):
            parent.kids.append(self)

    def __getitem__(self, k):
        return self.kw.get(k, "normal")

    def __setitem__(self, k, v):
        self.kw[k] = v

    def configure(self, **kw):
        self.kw.update(kw)

    config = configure

    def cget(self, k):
        return self.kw.get(k, "")

    def get(self):
        return self.kw.get("_text", "")

    def winfo_children(self):
        return list(self.kids)

    def destroy(self):
        if isinstance(self.parent, W) and self in self.parent.kids:
            self.parent.kids.remove(self)

    def winfo_width(self):
        return 900

    def winfo_height(self):
        return 220

    def winfo_fpixels(self, _):
        return 96.0

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: None


class FakeFont:
    def __init__(self, family=None, size=12, weight="normal"):
        self.size = size

    def measure(self, text):
        return len(text) * self.size // 2 + 1

    def metrics(self, key):
        return {"linespace": 32, "ascent": 24, "descent": 8}[key]

    def actual(self, key):
        return "Arial"


def install_fake_tk():
    tk = types.ModuleType("tkinter")
    for name in ("Tk", "Frame", "Label", "Button", "Canvas", "Entry", "Scrollbar"):
        setattr(tk, name, type(name, (W,), {}))
    tk.TclError = Exception
    font = types.ModuleType("tkinter.font")
    font.Font = FakeFont
    font.families = lambda root=None: ["Georgia", "Segoe UI"]
    font.nametofont = lambda name: FakeFont()
    mb = types.ModuleType("tkinter.messagebox")
    mb.askyesno = lambda *a, **k: True
    mb.showinfo = lambda *a, **k: None
    tk.font, tk.messagebox = font, mb
    saved = {k: sys.modules.get(k) for k in ("tkinter", "tkinter.font", "tkinter.messagebox")}
    sys.modules.update({"tkinter": tk, "tkinter.font": font, "tkinter.messagebox": mb})
    return saved


class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["ORTHOQUIZ_HOME"] = cls.tmp.name
        cls.saved = install_fake_tk()
        for mod in [m for m in sys.modules if m.startswith("ortho.ui")]:
            del sys.modules[mod]
        cls.ui = importlib.import_module("ortho.ui")

    @classmethod
    def tearDownClass(cls):
        for k, v in cls.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        sys.modules.pop("ortho.ui", None)
        os.environ.pop("ORTHOQUIZ_HOME", None)
        cls.tmp.cleanup()

    def play(self, app, wrong_every=0):
        quiz = app.screens["quiz"]
        s = quiz.session
        i = 0
        while not s.finished:
            q = s.current
            wrong = wrong_every and i % wrong_every == 0
            if q.is_qcm:
                target = next(c for c in s.choices if (c != q.expected) == bool(wrong))
                quiz.choose(s.choices.index(target))
            else:
                quiz.entry.kw["_text"] = "faux" if wrong else q.expected
                quiz.on_key(types.SimpleNamespace(keysym="Return", char="\r"))
            self.assertTrue(quiz.answered)
            quiz.on_key(types.SimpleNamespace(keysym="space", char=" "))
            i += 1

    def test_full_run_through_every_screen(self):
        app = self.ui.App()
        self.assertEqual(len(app.themes), 11)
        for theme in app.themes:                       # une série dans chaque thème
            app.start_theme(theme)
            self.assertIs(app.current, app.screens["quiz"])
            self.play(app, wrong_every=4)
            self.assertIs(app.current, app.screens["result"])
            app.show("home")
        app.start_review()                             # des erreurs existent maintenant
        self.assertIs(app.current, app.screens["quiz"])
        self.play(app)
        app.replay()
        app.start_mix()
        self.play(app)
        app.show("badges")
        app.show("home")
        app._on_close()

    def test_typed_answer_without_accents_is_flagged(self):
        app = self.ui.App()
        theme = next(t for t in app.themes if t.id == "orthographe_mots")
        app.progress.theme_state(theme.id)["tier"] = 2
        app.start_theme(theme)
        quiz, s = app.screens["quiz"], app.screens["quiz"].session
        while s.current.is_qcm:
            quiz.choose(0)
            quiz.on_next()
        quiz.entry.kw["_text"] = "bibliotheque"
        s.questions[s.index] = next(q for t in app.themes for q in t.questions if q.expected == "bibliothèque")
        quiz._show_question()
        quiz.entry.kw["_text"] = "bibliotheque"
        quiz.validate()
        self.assertIn("accents", quiz.fb_title.kw["text"])

    def test_notebook_wraps_long_sentences(self):
        nb = self.ui.Notebook(W(), 1.0)
        nb.text = "Les enfants du village voisin ont rangé tous leurs jouets ___ dans la grande armoire du couloir."
        lines = nb._layout(300)
        self.assertGreater(len(lines), 1)
        flat = " ".join("".join(t for t, _ in word) for line in lines for word, _ in line)
        self.assertEqual(flat.replace("_____", "___"), nb.text)
        nb.redraw()


if __name__ == "__main__":
    unittest.main()
