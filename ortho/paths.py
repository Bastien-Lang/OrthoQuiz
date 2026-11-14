"""Chemins : ressources embarquées (dans l'exe) et dossier de données de l'utilisateur."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import APP_NAME


def base_dir() -> Path:
    """Dossier racine du projet (ou dossier temporaire de PyInstaller dans l'exe)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def resource(*parts: str) -> Path:
    return base_dir().joinpath(*parts)


def user_dir() -> Path:
    """Dossier où sont stockés la progression et les questions mises à jour."""
    override = os.environ.get("ORTHOQUIZ_HOME")
    if override:
        root = Path(override)
    else:
        root = Path(os.environ.get("APPDATA") or Path.home() / ".local" / "share") / APP_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def updates_dir() -> Path:
    p = user_dir() / "questions_updates"
    p.mkdir(parents=True, exist_ok=True)
    return p
