"""Vérifie tous les fichiers questions/*.json. À lancer avant chaque commit :

    python tools/check_questions.py

Affiche les erreurs et un résumé par thème. Code de sortie 1 s'il y a une erreur
(utilisé aussi par GitHub Actions avant de compiler).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ortho import content  # noqa: E402


def main() -> int:
    folder = ROOT / "questions"
    files = sorted(folder.glob("*.json"))
    if not files:
        print("Aucun fichier dans questions/")
        return 1
    problems, ids = 0, {}
    print(f"{'thème':28} {'niv.1':>6} {'niv.2':>6} {'niv.3':>6} {'QCM':>5} {'saisie':>7}")
    for p in files:
        theme, errors = content.parse_theme_bytes(p.read_bytes())
        for e in errors:
            print(f"  ERREUR {p.name} : {e}")
            problems += 1
        if theme is None:
            continue
        if theme.id in ids:
            print(f"  ERREUR {p.name} : l'id « {theme.id} » existe déjà dans {ids[theme.id]}")
            problems += 1
        ids[theme.id] = p.name
        counts = [len(theme.by_level(n)) for n in content.LEVELS]
        qcm = sum(1 for q in theme.questions if q.is_qcm)
        print(f"{theme.title[:28]:28} {counts[0]:>6} {counts[1]:>6} {counts[2]:>6} {qcm:>5} {len(theme.questions) - qcm:>7}")
        for n, c in zip(content.LEVELS, counts):
            if c < 8:
                print(f"  attention : {p.name} n'a que {c} question(s) au niveau {n} (8 recommandées)")
    print("\nOK" if not problems else f"\n{problems} problème(s) à corriger.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
