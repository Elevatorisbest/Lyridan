"""Build / version information.

Packaged builds carry ``lyridan/_build.py`` written by ``tools/write_build_info.py``.
  * stable channel (built from ``main`` or a ``v*`` tag): only the version is shown
  * dev channel (``dev`` branch, other branches, local builds): detailed build info
Running from source without ``_build.py`` data counts as a local dev build and
reads the git state at runtime.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from functools import lru_cache
from typing import Dict, List, Tuple

from . import APP_NAME, VERSION

try:  # generated at build time, git-ignored
    from ._build import BUILD_INFO as _RAW  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    _RAW = {}


def _git(*args: str) -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isdir(os.path.join(root, ".git")):
        return ""
    try:
        return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL, text=True,
                                       timeout=3).strip()
    except Exception:  # noqa: BLE001
        return ""


@lru_cache(maxsize=1)
def info() -> Dict:
    if _RAW:
        return dict(_RAW)
    commit = _git("rev-parse", "HEAD")
    return {
        "channel": "dev", "version": VERSION, "label": f"{VERSION}-dev.local", "build_number": "local",
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown", "commit": commit,
        "commit_short": commit[:7], "commit_date": _git("log", "-1", "--format=%cI"),
        "commit_subject": _git("log", "-1", "--format=%s"), "commit_author": _git("log", "-1", "--format=%an"),
        "commit_count": _git("rev-list", "--count", "HEAD"),
        "dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
        "build_date": "", "builder": "running from source", "repo_url": "", "commit_url": "", "run_url": "",
    }


def is_dev() -> bool:
    return info().get("channel", "dev") != "stable"


def display_version() -> str:
    """Short version for the window title."""
    i = info()
    if not is_dev():
        return VERSION
    commit = i.get("commit_short") or ""
    dirty = "*" if i.get("dirty") else ""
    return f"{i.get('label', VERSION)} ({commit}{dirty})" if commit else i.get("label", VERSION)


def _module_version(name: str) -> str:
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:  # noqa: BLE001
        mod = sys.modules.get(name)
        return getattr(mod, "__version__", "") if mod else ""


def runtime_details() -> List[Tuple[str, str]]:
    out = [("Python", f"{platform.python_version()} ({platform.python_implementation()})")]
    try:
        import PySide6
        from PySide6.QtCore import qVersion
        out.append(("Qt / PySide6", f"{qVersion()} / {PySide6.__version__}"))
    except Exception:  # noqa: BLE001
        pass
    for label, mod in (("fugashi (MeCab)", "fugashi"), ("UniDic-lite", "unidic-lite")):
        v = _module_version(mod)
        if v:
            out.append((label, v))
    mac = platform.mac_ver()[0]
    os_name = f"macOS {mac}" if mac else f"{platform.system()} {platform.release()} ({platform.version()})"
    out.append(("Operating system", os_name))
    out.append(("CPU architecture", platform.machine()))
    out.append(("Packaged app", "yes (PyInstaller)" if getattr(sys, "frozen", False) else "no (source)"))
    return out


def details() -> List[Tuple[str, str]]:
    """Rows for the build-info panel. Stable builds get the short form."""
    i = info()
    if not is_dev():
        return [("Version", f"{APP_NAME} {VERSION}"), ("Channel", "Stable release")]
    rows: List[Tuple[str, str]] = [
        ("Version", f"{APP_NAME} {i.get('label', VERSION)}"),
        ("Channel", "Development build" + (" - local" if i.get("build_number") == "local" else "")),
        ("Branch", f"{i.get('branch', '')}" + (f" ({i['ref_type']})" if i.get("ref_type") == "tag" else "")),
        ("Commit", (i.get("commit") or "unknown") + (" (uncommitted changes)" if i.get("dirty") else "")),
        ("Commit message", i.get("commit_subject", "")),
        ("Commit author / date", " · ".join(x for x in (i.get("commit_author"), i.get("commit_date")) if x)),
        ("Commits on branch", i.get("commit_count", "")),
        ("Build number", "#" + str(i.get("build_number")) + (f" (attempt {i['run_attempt']})"
                                                               if i.get("run_attempt") not in ("", "1", None) else "")),
        ("Built", " · ".join(x for x in (i.get("build_date"), i.get("builder")) if x)),
        ("Build machine", " ".join(x for x in (i.get("builder_os"), i.get("builder_arch"),
                                                i.get("builder_image")) if x)),
        ("Build Python", i.get("build_python", "")),
        ("Workflow", " · ".join(x for x in (i.get("workflow"), i.get("event")) if x)),
    ]
    rows += runtime_details()
    return [(k, v) for k, v in rows if v]


def links() -> List[Tuple[str, str]]:
    i = info()
    if not is_dev():
        return []
    return [(k, i[u]) for k, u in (("Commit on GitHub", "commit_url"), ("Build log", "run_url"),
                                   ("Repository", "repo_url")) if i.get(u)]


def as_text() -> str:
    lines = [f"{k}: {v}" for k, v in details()] + [f"{k}: {v}" for k, v in links()]
    return "\n".join(lines)
