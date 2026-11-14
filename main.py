"""Point d'entrée d'OrthoQuiz."""
import traceback


def main() -> None:
    try:
        from ortho.ui import run
        run()
    except Exception:
        details = traceback.format_exc()
        try:
            from ortho.paths import user_dir
            (user_dir() / "crash.log").write_text(details, encoding="utf-8")
        except Exception:
            pass
        try:  # l'exe n'a pas de console : on affiche l'erreur dans une fenêtre
            import tkinter
            from tkinter import messagebox
            root = tkinter.Tk()
            root.withdraw()
            messagebox.showerror("OrthoQuiz", "Une erreur est survenue :\n\n" + details[-1200:])
        except Exception:
            pass
        raise SystemExit(1)


if __name__ == "__main__":
    main()
