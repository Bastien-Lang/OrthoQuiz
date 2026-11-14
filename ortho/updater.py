"""Mise à jour des questions depuis un dépôt GitHub public (dossier « questions/ »).

Principe : on liste les fichiers du dossier via l'API GitHub (qui fournit le « sha » de chaque
fichier), on compare avec les copies locales et on ne télécharge que ce qui a changé.
Tout échec (hors-ligne, limite de l'API, fichier invalide) est silencieux : le jeu continue
avec les questions déjà présentes.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import APP_NAME, content
from .paths import resource, user_dir

API_URL = "https://api.github.com/repos/{repo}/contents/questions?ref={branch}"
RAW_URL = "https://raw.githubusercontent.com/{repo}/{branch}/questions/{name}"
TIMEOUT = 6


@dataclass
class SyncResult:
    status: str                       # disabled | uptodate | updated | offline | error
    updated: list = field(default_factory=list)
    message: str = ""


def git_blob_sha(data: bytes) -> str:
    """Empreinte d'un fichier telle que Git la calcule (identique au « sha » de l'API GitHub)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _sha_of(path: Path):
    try:
        return git_blob_sha(path.read_bytes())
    except OSError:
        return None


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": APP_NAME, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def load_config() -> dict:
    """config.json embarqué (écrit par GitHub Actions), surchargeable dans le dossier utilisateur."""
    cfg = {"repo": "", "branch": "main"}
    for p in (resource("config.json"), user_dir() / "config.json"):
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return cfg


def sync(repo: str, branch: str, bundled_dir: Path, cache_dir: Path, http_get=_http_get) -> SyncResult:
    if not repo:
        return SyncResult("disabled", message="Mises à jour en ligne non configurées.")
    try:
        listing = json.loads(http_get(API_URL.format(repo=repo, branch=branch)))
        if not isinstance(listing, list):
            return SyncResult("error", message="Réponse inattendue de GitHub.")
    except (urllib.error.URLError, OSError, TimeoutError):
        return SyncResult("offline", message="Hors ligne : questions locales utilisées.")
    except ValueError:
        return SyncResult("error", message="Réponse illisible de GitHub.")

    cache_dir.mkdir(parents=True, exist_ok=True)
    updated, failures = [], 0
    for item in listing:
        name = str(item.get("name", ""))
        if item.get("type") != "file" or not name.endswith(".json") or "/" in name or "\\" in name:
            continue
        remote = item.get("sha")
        bundled, cached = bundled_dir / name, cache_dir / name
        if remote and remote == _sha_of(bundled):
            if cached.exists():                       # la copie embarquée est déjà à jour
                cached.unlink()
            continue
        if remote and remote == _sha_of(cached):
            continue
        try:
            raw = http_get(RAW_URL.format(repo=repo, branch=branch, name=name))
        except (urllib.error.URLError, OSError, TimeoutError):
            failures += 1
            continue
        theme, errors = content.parse_theme_bytes(raw)
        if theme is None or errors:
            failures += 1
            continue
        tmp = cached.with_suffix(".tmp")
        tmp.write_bytes(raw)
        os.replace(tmp, cached)
        updated.append(name)

    if updated:
        return SyncResult("updated", updated, f"{len(updated)} thème(s) mis à jour.")
    if failures:
        return SyncResult("error", message="Mise à jour partielle impossible pour le moment.")
    return SyncResult("uptodate", message="Questions à jour.")
