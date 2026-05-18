"""
Klonowanie i wstępna inspekcja repozytoriów Git.

Moduł zajmuje się:
- walidacją URL,
- shallow-clone do ``data/repos/<slug>``,
- wykrywaniem podstawowych metadanych: język, licencja, README,
- mapowaniem drzewa plików.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from . import config

logger = logging.getLogger(__name__)


_GIT_URL_RE = re.compile(
    r"^(?:https?://|git@)"               # http(s) lub ssh
    r"[A-Za-z0-9._-]+"                    # host
    r"[:/][A-Za-z0-9._/-]+?"              # ścieżka
    r"(?:\.git)?/?$"
)


def is_valid_git_url(url: str) -> bool:
    """Bardzo prosta walidacja URL repozytorium."""
    if not url or not isinstance(url, str):
        return False
    return bool(_GIT_URL_RE.match(url.strip()))


def slug_from_url(url: str) -> str:
    """
    Generuje krótki, bezpieczny identyfikator katalogu z URL.

    ``https://github.com/foo/bar.git`` -> ``github.com_foo_bar``
    """
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parsed = urlparse(url if "://" in url else f"ssh://{url}")
    host = parsed.hostname or "repo"
    path = (parsed.path or "").strip("/").replace("/", "_") or "unknown"
    slug = f"{host}_{path}"
    # Sanityzacja - tylko bezpieczne znaki
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", slug)
    return slug[:120]  # bezpieczne ograniczenie długości


@dataclass
class RepoInfo:
    """Metadane sklonowanego repozytorium."""

    url: str
    slug: str
    path: Path
    size_kb: int = 0
    file_count: int = 0
    languages: Dict[str, int] = field(default_factory=dict)
    has_readme: bool = False
    has_license: bool = False
    has_tests: bool = False
    has_ci: bool = False
    has_dockerfile: bool = False
    main_files: List[str] = field(default_factory=list)
    branch: Optional[str] = None
    head_commit: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "slug": self.slug,
            "path": str(self.path),
            "size_kb": self.size_kb,
            "file_count": self.file_count,
            "languages": self.languages,
            "has_readme": self.has_readme,
            "has_license": self.has_license,
            "has_tests": self.has_tests,
            "has_ci": self.has_ci,
            "has_dockerfile": self.has_dockerfile,
            "main_files": self.main_files,
            "branch": self.branch,
            "head_commit": self.head_commit,
        }


class RepoFetcher:
    """Klonuje repozytoria i zbiera o nich podstawowe informacje."""

    def __init__(self, base_dir: Path = config.REPOS_DIR, depth: int = config.CLONE_DEPTH) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.depth = depth

    # ---------------------------------------------------------- klonowanie
    def clone(self, url: str, *, force: bool = False) -> RepoInfo:
        """
        Sklonuj repozytorium do ``base_dir/<slug>``.

        Parameters
        ----------
        url : str
            Pełny URL repozytorium.
        force : bool
            Jeśli True, usuwa wcześniejszą kopię.
        """
        if not is_valid_git_url(url):
            raise ValueError(f"Nieprawidłowy URL repozytorium: {url!r}")

        slug = slug_from_url(url)
        target = self.base_dir / slug

        if target.exists():
            if force:
                logger.info("Usuwam wcześniejszą kopię %s", target)
                shutil.rmtree(target)
            else:
                logger.info("Repozytorium już sklonowane: %s", target)
                return self.inspect(target, url=url)

        cmd = ["git", "clone", "--depth", str(self.depth), url, str(target)]
        logger.info("Klonuję: %s", " ".join(cmd))
        try:
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=config.CLONE_TIMEOUT,
            )
        except FileNotFoundError as e:
            raise RuntimeError("Brak komendy 'git' w systemie. Zainstaluj git.") from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"Klonowanie przekroczyło limit czasu ({config.CLONE_TIMEOUT}s).") from e
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Klonowanie nieudane: {e.stderr.strip() or e.stdout.strip()}") from e

        return self.inspect(target, url=url)

    # ------------------------------------------------------------ inspekcja
    def inspect(self, repo_path: Path, *, url: Optional[str] = None) -> RepoInfo:
        """Skanuje sklonowane repozytorium i zwraca podstawowe statystyki."""
        repo_path = Path(repo_path)
        if not repo_path.exists():
            raise FileNotFoundError(f"Brak katalogu repozytorium: {repo_path}")

        info = RepoInfo(
            url=url or "",
            slug=repo_path.name,
            path=repo_path,
        )

        size_bytes = 0
        file_count = 0
        languages: Dict[str, int] = {}
        main_files: List[str] = []

        for p in repo_path.rglob("*"):
            # Pomiń ignorowane katalogi
            if any(part in config.IGNORE_DIRS for part in p.parts):
                continue
            if p.is_dir():
                continue
            try:
                stat = p.stat()
            except OSError:
                continue

            size_bytes += stat.st_size
            file_count += 1

            ext = p.suffix.lower()
            if ext in config.CODE_EXTENSIONS:
                languages[ext] = languages.get(ext, 0) + 1

            name = p.name.lower()
            rel = p.relative_to(repo_path)

            if name == "readme.md" or name.startswith("readme"):
                info.has_readme = True
                main_files.append(str(rel))
            if name == "license" or name.startswith("license") or name == "copying":
                info.has_license = True
                main_files.append(str(rel))
            if name == "dockerfile" or ext == ".dockerfile":
                info.has_dockerfile = True
            if "test" in name or "spec" in name:
                info.has_tests = True
            if ".github" in p.parts or ".gitlab-ci.yml" in p.parts:
                info.has_ci = True
            if name in {"main.py", "app.py", "index.js", "index.ts", "main.go", "main.rs", "main.java"}:
                main_files.append(str(rel))
            if name in {"package.json", "pyproject.toml", "requirements.txt", "go.mod", "cargo.toml", "build.gradle", "pom.xml"}:
                main_files.append(str(rel))

        info.size_kb = int(size_bytes / 1024)
        info.file_count = file_count
        info.languages = dict(sorted(languages.items(), key=lambda kv: kv[1], reverse=True))
        info.main_files = sorted(set(main_files))

        info.branch, info.head_commit = self._git_meta(repo_path)
        return info

    def _git_meta(self, repo_path: Path) -> tuple[Optional[str], Optional[str]]:
        """Aktualna gałąź + skrót commita HEAD."""
        try:
            branch = subprocess.run(
                ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
                check=True, capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            commit = subprocess.run(
                ["git", "-C", str(repo_path), "rev-parse", "--short", "HEAD"],
                check=True, capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            return branch or None, commit or None
        except Exception as e:  # noqa: BLE001
            logger.debug("Brak metadanych git: %s", e)
            return None, None

    # ------------------------------------------------------------- drzewo
    def file_tree(self, repo_path: Path, max_entries: int = 500) -> List[str]:
        """Lista ścieżek względnych, wstępnie posortowana."""
        repo_path = Path(repo_path)
        entries: List[str] = []
        for p in sorted(repo_path.rglob("*")):
            if any(part in config.IGNORE_DIRS for part in p.parts):
                continue
            if p.is_dir():
                continue
            entries.append(str(p.relative_to(repo_path)))
            if len(entries) >= max_entries:
                break
        return entries

    def cleanup(self, slug: str) -> bool:
        """Usuń sklonowane repozytorium z dysku."""
        target = self.base_dir / slug
        if target.exists():
            shutil.rmtree(target)
            return True
        return False
