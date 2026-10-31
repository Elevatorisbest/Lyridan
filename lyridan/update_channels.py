"""Update channels: which GitHub release holds the newest build of each branch.

Shared by the app (``lyridan/updater.py``) and by CI (``tools/make_update_manifest.py``),
so it only uses the standard library.

Every CI build publishes an ``update.json`` manifest next to its installers:
  * ``main`` (and ``v*`` tags)  -> stable release ``v<VERSION>``, marked "latest"
                                   (found through ``releases/latest/download/update.json``)
  * ``dev``                     -> rolling pre-release ``dev-latest``
  * any other branch            -> rolling pre-release ``<branch>-latest``
Releases without a manifest (the old v1 releases, the alignment model) are never offered.
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional
from urllib.parse import quote

REPO = "Elevatorisbest/Lyridan"
GITHUB_URL = f"https://github.com/{REPO}"
API_URL = f"https://api.github.com/repos/{REPO}"

MANIFEST_NAME = "update.json"
MANIFEST_SCHEMA = 1
STABLE_BRANCH = "main"
DEV_BRANCH = "dev"
BRANCH_MARKER = "lyridan-branch:"          # <!-- lyridan-branch: NAME --> in a release body

# v1.1.1 is the old (pre-2.0) app: it has no updater and can't be updated from.
# workflowtest / digitalstudiothemetest are experiment branches: never built or offered.
EXCLUDED_BRANCHES = ("v1.1.1", "workflowtest", "digitalstudiothemetest")
_LEGACY = re.compile(r"^v?1\.\d+(\.\d+)*$")

# Inno Setup AppId (packaging/windows/lyridan.iss) and the mutex the running app holds.
WINDOWS_APP_ID = "{6F1B7C2E-5A43-4C8E-9C1E-7E1D2B5A9F31}"
APP_MUTEX = "LyridanAppMutex"


def is_excluded_branch(name: str) -> bool:
    n = (name or "").strip()
    return not n or n in EXCLUDED_BRANCHES or bool(_LEGACY.match(n))


def branch_slug(name: str) -> str:
    """Tag-safe, collision-free name for a branch ("feature/x" -> "feature-x-1a2b3c")."""
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
    clean = re.sub(r"\.{2,}", ".", clean) or "branch"
    if clean != name or clean.lower() in (STABLE_BRANCH, DEV_BRANCH):
        clean = f"{clean}-{hashlib.sha1(name.encode('utf-8')).hexdigest()[:6]}"
    return clean


def release_tag(branch: str) -> Optional[str]:
    """Release tag that holds a branch's newest build (None = the "latest" stable release)."""
    if branch == STABLE_BRANCH:
        return None
    if branch == DEV_BRANCH:
        return "dev-latest"
    return f"{branch_slug(branch)}-latest"


def manifest_url(branch: str) -> str:
    tag = release_tag(branch)
    if tag is None:
        return f"{GITHUB_URL}/releases/latest/download/{MANIFEST_NAME}"
    return f"{GITHUB_URL}/releases/download/{quote(tag)}/{MANIFEST_NAME}"


def asset_url(tag: str, name: str) -> str:
    return f"{GITHUB_URL}/releases/download/{quote(tag)}/{quote(name)}"


def release_page(tag: str) -> str:
    return f"{GITHUB_URL}/releases/tag/{quote(tag)}"


_ASSET_PATTERNS = (
    (re.compile(r"-Windows-x64-Setup\.exe$"), "windows-x64-setup"),
    (re.compile(r"-Windows-x64-portable\.zip$"), "windows-x64-portable"),
    (re.compile(r"-macOS-AppleSilicon\.dmg$"), "macos-arm64-dmg"),
    (re.compile(r"-macOS-Intel\.dmg$"), "macos-x86_64-dmg"),
    (re.compile(r"-macOS-AppleSilicon-Installer\.pkg$"), "macos-arm64-pkg"),
    (re.compile(r"-macOS-Intel-Installer\.pkg$"), "macos-x86_64-pkg"),
)


def asset_key(filename: str) -> Optional[str]:
    for rx, key in _ASSET_PATTERNS:
        if rx.search(filename):
            return key
    return None
