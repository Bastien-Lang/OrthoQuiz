import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ortho import content, session as sess, updater  # noqa: E402
from ortho.progress import Progress, level_from_xp, xp_for_level  # noqa: E402

QDIR = ROOT / "questions"


def themes():
    return content.load_themes(QDIR)


def make_theme(tid="t", n=9):
    qs = []
    for lvl in (1, 2, 3):
        for i in range(n):
            qs.append({"lvl": lvl, "q": f"Phrase {lvl}-{i} ___.", "choices": ["x", "y"], "answer": "x"})
    return content.parse_theme({"id": tid, "title": "T", "questions": qs})[0]


class ContentTests(unittest.TestCase):
    def test_all_bundled_questions_are_valid(self):
        for p in QDIR.glob("*.json"):
            theme, errors = content.parse_theme_bytes(p.read_bytes())
            self.assertIsNotNone(theme, p.name)
            self.assertEqual(errors, [], p.name)

    def test_qcm_answer_is_in_choices_and_unique(self):
        for t in themes():
            for q in t.questions:
                if q.is_qcm:
                    self.assertIn(q.expected, q.choices)
                    self.assertEqual(len(set(q.choices)), len(q.choices))

    def test_qcm_is_strict_about_accents(self):
        q = content.Question("i", "t", 1, "Il ___ faim.", ("a",), ("a", "à"))
        self.assertEqual(content.check_answer(q, "à"), "ko")
        self.assertEqual(content.check_answer(q, "a"), "ok")

    def test_typed_answers(self):
        q = content.Question("i", "t", 1, "Écris : ___ (x)", ("bibliothèque",))
        self.assertEqual(content.check_answer(q, "  Bibliothèque "), "ok")
        self.assertEqual(content.check_answer(q, "bibliotheque"), "almost")
        self.assertEqual(content.check_answer(q, "bibliotèque"), "ko")
        self.assertEqual(content.check_answer(q, ""), "ko")
        q2 = content.Question("i", "t", 1, "___ (x)", ("c'est",))
        self.assertEqual(content.check_answer(q2, "c\u2019est"), "ok")

    def test_invalid_files_are_rejected(self):
        self.assertIsNone(content.parse_theme_bytes(b"{pas du json")[0])
        bad = {"id": "t", "title": "T", "questions": [
            {"lvl": 1, "q": "A ___", "choices": ["x", "y"], "answer": "z"},
            {"lvl": 9, "q": "B ___", "answer": "x"},
            {"lvl": 1, "q": "C ___", "choices": ["x", "x"], "answer": "x"},
            {"lvl": 1, "q": "D ___", "choices": ["x", "y"], "answer": "x"}]}
        theme, errors = content.parse_theme(bad)
        self.assertEqual(len(theme.questions), 1)
        self.assertEqual(len(errors), 3)

    def test_update_overrides_bundled_only_if_not_older(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            def write(folder, version, title):
                data = {"id": "t", "title": title, "version": version,
                        "questions": [{"lvl": 1, "q": "A ___", "choices": ["x", "y"], "answer": "x"}]}
                (Path(folder) / "t.json").write_text(json.dumps(data), encoding="utf-8")
            write(a, 2, "embarqué")
            write(b, 1, "ancien cache")
            self.assertEqual(content.load_themes(a, b)[0].title, "embarqué")
            write(b, 2, "cache")
            self.assertEqual(content.load_themes(a, b)[0].title, "cache")


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "p.json"
        self.p = Progress(self.path)
        self.theme = make_theme()

    def tearDown(self):
        self.tmp.cleanup()

    def play(self, s, correct_count):
        for i in range(s.total):
            q = s.current
            s.answer(q.expected if i < correct_count else "zzz-faux")
            s.next()
        return self.p.apply_session(s.summary)

    def test_levels(self):
        self.assertEqual(level_from_xp(0).level, 1)
        self.assertEqual(level_from_xp(xp_for_level(2)).level, 2)
        self.assertEqual(level_from_xp(xp_for_level(2) - 1).level, 1)
        self.assertEqual(level_from_xp(10 ** 6).title, "Légende")

    def test_tier_advances_on_80_percent(self):
        s = sess.build_theme_session(self.theme, self.p, random.Random(1))
        self.assertEqual(s.total, 9)          # le niveau 1 du thème de test contient 9 questions
        self.assertTrue(all(q.lvl == 1 for q in s.questions))
        out = self.play(s, 8)
        self.assertEqual(out.tier_cleared, 1)
        self.assertEqual(self.p.theme_state("t")["tier"], 2)
        self.assertGreater(out.xp_gained, 0)

    def test_tier_does_not_advance_below_80_percent(self):
        s = sess.build_theme_session(self.theme, self.p, random.Random(2))
        out = self.play(s, 7)
        self.assertIsNone(out.tier_cleared)
        self.assertEqual(self.p.theme_state("t")["tier"], 1)

    def test_full_progression_to_mastery(self):
        for expected_tier in (1, 2, 3):
            s = sess.build_theme_session(self.theme, self.p, random.Random(expected_tier))
            self.assertEqual(s.summary.tier, expected_tier)
            out = self.play(s, 10)
        self.assertTrue(out.mastered_now)
        self.assertTrue(self.p.is_mastered("t"))
        self.assertIn("master", self.p.data["badges"])
        self.assertIn("perfect", self.p.data["badges"])

    def test_higher_tiers_mix_in_lower_questions(self):
        self.p.theme_state("t")["tier"] = 3
        s = sess.build_theme_session(self.theme, self.p, random.Random(3))
        levels = [q.lvl for q in s.questions]
        self.assertEqual(levels.count(3), 7)
        self.assertEqual(sum(1 for l in levels if l < 3), 3)

    def test_wrong_answers_go_to_review_until_two_successes(self):
        s = sess.build_theme_session(self.theme, self.p, random.Random(4))
        q = s.current
        s.answer("zzz-faux")
        self.assertTrue(self.p.needs_review(q.id))
        self.p.record_answer(q, True)
        self.assertTrue(self.p.needs_review(q.id))
        self.p.record_answer(q, True)
        self.assertFalse(self.p.needs_review(q.id))

    def test_review_session_only_contains_missed_questions(self):
        s = sess.build_theme_session(self.theme, self.p, random.Random(5))
        missed = {s.current.id}
        s.answer("zzz-faux")
        r = sess.build_review_session([self.theme], self.p, random.Random(1))
        self.assertEqual({q.id for q in r.questions}, missed)

    def test_save_and_reload(self):
        s = sess.build_theme_session(self.theme, self.p, random.Random(6))
        self.play(s, 9)
        self.p.save()
        again = Progress(self.path)
        self.assertEqual(again.xp, self.p.xp)
        self.assertEqual(again.theme_state("t")["cleared"], [1])

    def test_corrupted_progress_file_does_not_crash(self):
        self.path.write_text("{ceci n'est pas du json", encoding="utf-8")
        self.assertEqual(Progress(self.path).xp, 0)

    def test_hint_halves_xp(self):
        s1 = sess.Session([self.theme.questions[0]], self.p, "mix")
        s1.answer("x")
        s2 = sess.Session([self.theme.questions[0]], self.p, "mix")
        s2.hint_text()
        s2.answer("x")
        self.assertEqual(s2.summary.xp, s1.summary.xp // 2)

    def test_real_themes_build_all_session_kinds(self):
        ts = themes()
        for t in ts:
            s = sess.build_theme_session(t, self.p, random.Random(7))
            self.assertTrue(8 <= s.total <= 10, t.id)
        self.assertEqual(sess.build_mix_session(ts, self.p, random.Random(8)).total, 10)


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bundled = Path(self.tmp.name) / "bundled"
        self.cache = Path(self.tmp.name) / "cache"
        self.bundled.mkdir()
        self.theme_new = json.dumps({"id": "nouveau", "title": "Nouveau", "version": 1, "questions": [
            {"lvl": 1, "q": "A ___", "choices": ["x", "y"], "answer": "x"}]}).encode()
        self.theme_old = json.dumps({"id": "a_a", "title": "a", "version": 1, "questions": [
            {"lvl": 1, "q": "B ___", "choices": ["x", "y"], "answer": "x"}]}).encode()
        (self.bundled / "a_a.json").write_bytes(self.theme_old)

    def tearDown(self):
        self.tmp.cleanup()

    def fake(self, files):
        listing = [{"name": n, "type": "file", "sha": updater.git_blob_sha(d)} for n, d in files.items()]

        def http_get(url):
            if "api.github.com" in url:
                return json.dumps(listing).encode()
            return files[url.rsplit("/", 1)[1]]
        return http_get

    def test_disabled_without_repo(self):
        self.assertEqual(updater.sync("", "main", self.bundled, self.cache).status, "disabled")

    def test_downloads_only_changed_files(self):
        http = self.fake({"a_a.json": self.theme_old, "nouveau.json": self.theme_new})
        res = updater.sync("o/r", "main", self.bundled, self.cache, http)
        self.assertEqual((res.status, res.updated), ("updated", ["nouveau.json"]))
        self.assertTrue((self.cache / "nouveau.json").exists())
        self.assertFalse((self.cache / "a_a.json").exists())
        res = updater.sync("o/r", "main", self.bundled, self.cache, http)
        self.assertEqual(res.status, "uptodate")

    def test_invalid_remote_file_is_ignored(self):
        http = self.fake({"a_a.json": self.theme_old, "casse.json": b"{pas du json"})
        res = updater.sync("o/r", "main", self.bundled, self.cache, http)
        self.assertNotEqual(res.status, "updated")
        self.assertFalse((self.cache / "casse.json").exists())

    def test_offline_is_silent(self):
        def boom(url):
            raise OSError("pas de réseau")
        self.assertEqual(updater.sync("o/r", "main", self.bundled, self.cache, boom).status, "offline")

    def test_stale_cache_removed_when_bundled_is_current(self):
        self.cache.mkdir()
        (self.cache / "a_a.json").write_bytes(self.theme_new)
        http = self.fake({"a_a.json": self.theme_old})
        updater.sync("o/r", "main", self.bundled, self.cache, http)
        self.assertFalse((self.cache / "a_a.json").exists())

    def test_git_sha_matches_git(self):
        self.assertEqual(updater.git_blob_sha(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")


if __name__ == "__main__":
    unittest.main()
