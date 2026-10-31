"""Automatic updates (Qt-free; the GUI side is ``lyridan/gui/update_ui.py``).

How it works
  * On launch the app downloads the ``update.json`` manifest of the branch it follows
    (``update_channels.manifest_url``; plain release-download URLs, no API rate limit).
  * A build is offered when its commit differs from the running one and it is newer
    (higher CI run number) - or when it comes from a different branch than the running
    build (switching branches in Options).
  * With "install automatically" on, the installer is downloaded in the background,
    checked against the manifest's SHA-256 and recorded as *pending*. The next time
    Lyridan starts, the pending update is installed before the window opens and
    Lyridan starts again on the new version.
  * Windows (installed): the Inno Setup installer runs silently into the same folder and
    for the same scope (per user / all users) as the existing install, waits for this
    process to exit (app mutex) and relaunches Lyridan.
    Windows (portable zip) and macOS (.app from the DMG): a small helper script waits for
    this process to exit, swaps the files and relaunches.
  * A failed install is never retried automatically; a build you installed by hand that is
    older than the newest one is not overwritten without asking ("pinned").
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import platform
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from . import buildinfo
from .settings import config_dir
from .update_channels import (API_URL, APP_MUTEX, BRANCH_MARKER, DEV_BRANCH, GITHUB_URL, MANIFEST_NAME,
                              MANIFEST_SCHEMA, STABLE_BRANCH, WINDOWS_APP_ID, asset_url, is_excluded_branch,
                              manifest_url, release_page)


class UpdateError(Exception):
    pass


# ------------------------------------------------------------------ paths / network
def updates_dir() -> str:
    path = os.path.join(config_dir(), "updates")
    os.makedirs(path, exist_ok=True)
    return path


def _contexts():
    yield ssl.create_default_context()
    try:
        import certifi
        yield ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        pass


def _open(url: str, timeout: float = 20, accept: str = ""):
    last: Optional[Exception] = None
    headers = {"User-Agent": f"Lyridan/{buildinfo.info().get('label', '')}"}
    if accept:
        headers["Accept"] = accept
    for ctx in _contexts():
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=headers), context=ctx,
                                          timeout=timeout)
        except urllib.error.URLError as e:
            last = e
            if not isinstance(getattr(e, "reason", None), ssl.SSLError):
                raise
    raise last  # type: ignore[misc]


def _get_json(url: str, timeout: float = 20, accept: str = ""):
    with _open(url, timeout, accept) as r:
        return json.loads(r.read().decode("utf-8"))


# ------------------------------------------------------------------ local build
def track_of(info: Dict) -> str:
    """Branch a build belongs to for updates (stable builds - main or a v* tag - follow main)."""
    if info.get("channel") == "stable":
        return STABLE_BRANCH
    return info.get("branch") or ""


def target_track(setting: str, info: Optional[Dict] = None) -> str:
    """Branch to update from: the Options setting, or "" = the branch this build came from."""
    info = info if info is not None else buildinfo.info()
    s = (setting or "").strip()
    if s and not is_excluded_branch(s):
        return s
    t = track_of(info)
    return t if t and not is_excluded_branch(t) and t not in ("HEAD", "unknown") else STABLE_BRANCH


def is_ci_build(info: Dict) -> bool:
    return info.get("builder") == "GitHub Actions" and str(info.get("build_number", "")).isdigit()


def _num(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return -1


# ------------------------------------------------------------------ what can be updated here
@dataclass
class InstallTarget:
    kind: str = ""          # windows-installer | windows-portable | macos-app | "" (not supported)
    asset_key: str = ""
    path: str = ""          # app folder (Windows) / .app bundle (macOS)
    reason: str = ""        # why automatic install is unavailable


def _mac_arch() -> str:
    if platform.machine() == "arm64":
        return "arm64"
    try:   # Intel build running under Rosetta on Apple Silicon -> offer the native build
        out = subprocess.run(["sysctl", "-n", "sysctl.proc_translated"], capture_output=True, text=True,
                             timeout=3).stdout.strip()
        if out == "1":
            return "arm64"
    except Exception:  # noqa: BLE001
        pass
    return "x86_64"


def _dir_writable(path: str) -> bool:
    probe = os.path.join(path, f".lyridan-write-test-{os.getpid()}")
    try:
        with open(probe, "w") as fh:
            fh.write("x")
        os.remove(probe)
        return True
    except OSError:
        return False


def install_target() -> InstallTarget:
    if not getattr(sys, "frozen", False):
        return InstallTarget(reason="Lyridan is running from source - update it with git.")
    if sys.platform == "win32":
        app_dir = os.path.dirname(os.path.abspath(sys.executable))
        if glob.glob(os.path.join(app_dir, "unins*.exe")):
            return InstallTarget("windows-installer", "windows-x64-setup", app_dir)
        if _dir_writable(app_dir):
            return InstallTarget("windows-portable", "windows-x64-portable", app_dir)
        return InstallTarget(path=app_dir, reason=f"Lyridan can't write to its folder ({app_dir}).")
    if sys.platform == "darwin":
        bundle = os.path.abspath(os.path.join(os.path.dirname(sys.executable), "..", ".."))
        if not bundle.endswith(".app"):
            return InstallTarget(reason="Lyridan is not running from an app bundle.")
        if "/AppTranslocation/" in bundle or bundle.startswith("/Volumes/"):
            return InstallTarget(path=bundle, reason="Move Lyridan to the Applications folder (and open it "
                                                     "from there) to get automatic updates.")
        return InstallTarget("macos-app", f"macos-{_mac_arch()}-dmg", bundle)
    return InstallTarget(reason="Automatic updates are available for the Windows and macOS builds only.")


# ------------------------------------------------------------------ persistent state
class UpdateState:
    """``<config>/updates/state.json`` - what the updater has done between launches."""

    def __init__(self, data: Optional[Dict] = None):
        d = dict(data or {})
        self.pending: Optional[Dict] = d.get("pending") or None
        self.failed: List[str] = list(d.get("failed") or [])
        self.skipped: str = d.get("skipped") or ""
        self.pinned: str = d.get("pinned") or ""
        self.switch_requested: str = d.get("switch_requested") or ""
        self.last_run_commit: str = d.get("last_run_commit") or ""
        self.last_run_build: str = str(d.get("last_run_build") or "")
        self.last_run_track: str = d.get("last_run_track") or ""

    @staticmethod
    def path() -> str:
        return os.path.join(updates_dir(), "state.json")

    @classmethod
    def load(cls) -> "UpdateState":
        try:
            with open(cls.path(), encoding="utf-8") as fh:
                return cls(json.load(fh))
        except (OSError, ValueError):
            return cls()

    def save(self) -> None:
        tmp = self.path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.__dict__, fh, indent=2)
        os.replace(tmp, self.path())


# ------------------------------------------------------------------ manifest / offer
def fetch_manifest(track: str, timeout: float = 20) -> Optional[Dict]:
    """Newest build of a branch, or None when that branch has no published build."""
    try:
        m = _get_json(manifest_url(track), timeout)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise UpdateError(f"GitHub answered {e.code} {e.reason}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise UpdateError(f"Couldn't reach GitHub ({getattr(e, 'reason', e)})") from e
    if not isinstance(m, dict) or m.get("app") != "Lyridan" or _num(m.get("schema")) < 1:
        return None
    if _num(m.get("schema")) > MANIFEST_SCHEMA and not m.get("assets"):
        return None
    return m


@dataclass
class Offer:
    manifest: Dict
    track: str
    kind: str                       # update | switch | rebuild (different build, order unknown)
    asset: Optional[Dict] = None    # installer for this platform (None = manual download only)
    auto: bool = True               # may be downloaded / installed without asking
    why_not_auto: str = ""

    @property
    def commit(self) -> str:
        return self.manifest.get("commit", "")

    @property
    def label(self) -> str:
        return self.manifest.get("label") or self.manifest.get("version", "")

    @property
    def tag(self) -> str:
        return self.manifest.get("tag", "")

    def page_url(self) -> str:
        return self.manifest.get("release_url") or (release_page(self.tag) if self.tag else f"{GITHUB_URL}/releases")

    def changes_url(self, info: Dict) -> str:
        if self.kind == "update" and info.get("commit") and self.commit:
            return f"{GITHUB_URL}/compare/{info['commit'][:12]}...{self.commit[:12]}"
        return self.page_url()


def evaluate(info: Dict, manifest: Optional[Dict], track: str, state: UpdateState, target: InstallTarget,
             manual: bool = False) -> Optional[Offer]:
    if not manifest or not manifest.get("commit") or manifest.get("commit") == info.get("commit"):
        return None
    if (manifest.get("track") or manifest.get("branch")) != track:
        return None
    if track_of(info) != track:
        kind = "switch"
    elif is_ci_build(info) and _num(manifest.get("build_number")) >= 0:
        if _num(manifest.get("build_number")) <= _num(info.get("build_number")):
            return None                                   # same or older build
        kind = "update"
    elif manual:
        kind = "rebuild"                                  # local build: can't tell which is newer
    else:
        return None
    if state.skipped == manifest["commit"] and not manual:
        return None
    asset = (manifest.get("assets") or {}).get(target.asset_key) if target.kind else None
    offer = Offer(manifest, track, kind, asset)
    reasons = []
    if not target.kind:
        reasons.append(target.reason)
    elif not asset:
        reasons.append("This build has no installer for your system.")
    if kind == "switch" and state.switch_requested != track:
        reasons.append("This build comes from a different branch.")
    if kind == "rebuild":
        reasons.append("This is a local build.")
    if state.pinned and state.pinned == info.get("commit"):
        reasons.append("You installed this version yourself.")
    if manifest["commit"] in state.failed:
        reasons.append("Installing this build failed before.")
    offer.auto = not reasons
    offer.why_not_auto = " ".join(reasons)
    return offer


def check(setting_branch: str, state: Optional[UpdateState] = None, manual: bool = False,
          timeout: float = 20) -> Tuple[Optional[Offer], Optional[Dict], str]:
    """Returns (offer, manifest, track). Raises UpdateError when GitHub can't be reached."""
    info = buildinfo.info()
    track = target_track(setting_branch, info)
    manifest = fetch_manifest(track, timeout)
    offer = evaluate(info, manifest, track, state or UpdateState.load(), install_target(), manual)
    return offer, manifest, track


# ------------------------------------------------------------------ download
def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verified(path: str, asset: Dict) -> bool:
    try:
        if asset.get("size") and os.path.getsize(path) != int(asset["size"]):
            return False
        return bool(asset.get("sha256")) and _sha256(path) == asset["sha256"].lower()
    except OSError:
        return False


def download(offer: Offer, progress: Optional[Callable[[int, int], None]] = None,
             cancelled: Optional[Callable[[], bool]] = None, url: Optional[str] = None) -> str:
    asset = offer.asset
    if not asset or not asset.get("name") or not asset.get("sha256"):
        raise UpdateError("No installer for this system in that build.")
    folder = os.path.join(updates_dir(), "downloads")
    os.makedirs(folder, exist_ok=True)
    name = os.path.basename(asset["name"])
    dest = os.path.join(folder, name)
    if not (os.path.exists(dest) and _verified(dest, asset)):
        part = dest + ".part"
        h = hashlib.sha256()
        try:
            with _open(url or asset_url(offer.tag, name), timeout=60) as r, open(part, "wb") as out:
                total = int(r.headers.get("Content-Length") or asset.get("size") or 0)
                done = 0
                while True:
                    if cancelled and cancelled():
                        raise InterruptedError("Download cancelled")
                    chunk = r.read(1 << 18)
                    if not chunk:
                        break
                    out.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        except (urllib.error.URLError, OSError) as e:
            _remove(part)
            if isinstance(e, InterruptedError):
                raise
            raise UpdateError(f"Download failed ({getattr(e, 'reason', e)})") from e
        except BaseException:
            _remove(part)
            raise
        if h.hexdigest() != asset["sha256"].lower():
            _remove(part)
            raise UpdateError("The downloaded file is damaged (checksum mismatch). It will be downloaded again "
                              "next time.")
        os.replace(part, dest)
    for old in glob.glob(os.path.join(folder, "*")):     # keep only the newest download
        if os.path.abspath(old) != os.path.abspath(dest):
            _remove(old)
    return dest


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def make_pending(offer: Offer, path: str, target: Optional[InstallTarget] = None,
                 state: Optional[UpdateState] = None) -> Dict:
    target = target or install_target()
    st = state or UpdateState.load()
    info = buildinfo.info()
    st.pending = {
        "commit": offer.commit, "label": offer.label, "branch": offer.manifest.get("branch", ""),
        "track": offer.track, "kind": target.kind, "target": target.path, "path": path,
        "sha256": (offer.asset or {}).get("sha256", ""), "size": (offer.asset or {}).get("size", 0),
        "from_commit": info.get("commit", ""), "attempts": 0, "tag": offer.tag,
        "downloaded": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    st.save()
    return st.pending


# ------------------------------------------------------------------ launch bookkeeping
@dataclass
class Startup:
    install: Optional[Dict] = None     # pending update to install right now (before the window opens)
    message: str = ""
    level: str = "info"                # info | warning
    events: List[str] = field(default_factory=list)


def on_startup(update_check: bool, auto_install: bool, setting_branch: str, has_file_args: bool = False,
               first_instance: bool = True, info: Optional[Dict] = None,
               state: Optional[UpdateState] = None, target: Optional[InstallTarget] = None) -> Startup:
    info = info if info is not None else buildinfo.info()
    st = state if state is not None else UpdateState.load()
    out = Startup()
    commit = info.get("commit", "")
    p = st.pending
    via_updater = False
    if p:
        if p.get("commit") == commit:
            via_updater = True
            out.message = f"Lyridan was updated to {p.get('label', '')}."
            out.events.append("updated")
            _remove(p.get("path", ""))
            st.pending = None
            st.switch_requested = ""
            st.pinned = ""
        elif p.get("from_commit") != commit:
            out.events.append("stale")                    # a different version was installed meanwhile
            _remove(p.get("path", ""))
            st.pending = None
        elif _num(p.get("attempts")) >= 1:
            out.events.append("failed")
            out.level = "warning"
            out.message = (f"The update to Lyridan {p.get('label', '')} could not be installed. "
                           "Use Help → Check for updates to try again, or install it from the download page.")
            if p.get("commit") and p["commit"] not in st.failed:
                st.failed = (st.failed + [p["commit"]])[-20:]
            _remove(p.get("path", ""))
            st.pending = None
    if st.last_run_commit and st.last_run_commit != commit and not via_updater:
        out.events.append("manual")                       # installed by hand (setup.exe / DMG / zip)
        st.switch_requested = ""
        if (track_of(info) == st.last_run_track and is_ci_build(info)
                and _num(info.get("build_number")) < _num(st.last_run_build)):
            st.pinned = commit                            # deliberate downgrade: don't undo it silently
            out.events.append("pinned")
    if st.pinned and st.pinned != commit:
        st.pinned = ""
    st.last_run_commit = commit
    st.last_run_build = str(info.get("build_number", ""))
    st.last_run_track = track_of(info)

    p = st.pending
    if p and update_check and auto_install and not has_file_args and first_instance:
        target = target or install_target()
        ok = (p.get("kind") == target.kind and target.kind
              and os.path.normcase(p.get("target", "")) == os.path.normcase(target.path)
              and p.get("track") == target_track(setting_branch, info)
              and p.get("commit") not in st.failed
              and _verified(p.get("path", ""), {"sha256": p.get("sha256"), "size": p.get("size")}))
        if ok:
            p["attempts"] = _num(p.get("attempts")) + 1
            out.install = dict(p)
        else:                                             # wrong branch / install moved / file damaged
            _remove(p.get("path", ""))
            st.pending = None
    st.save()
    return out


def mark_attempt(state: Optional[UpdateState] = None) -> Optional[Dict]:
    st = state or UpdateState.load()
    if st.pending:
        st.pending["attempts"] = _num(st.pending.get("attempts")) + 1
        st.save()
    return st.pending


# ------------------------------------------------------------------ single instance
_INSTANCE_HANDLE = None


def claim_instance() -> bool:
    """Hold the app mutex (Windows) / lock file (macOS). False = another Lyridan is running.
    The Windows installer waits for this mutex to disappear before replacing files."""
    global _INSTANCE_HANDLE
    if _INSTANCE_HANDLE is not None:
        return True
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateMutexW.restype = wintypes.HANDLE
            k32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
            h = k32.CreateMutexW(None, False, APP_MUTEX)
            err = ctypes.get_last_error()
            _INSTANCE_HANDLE = h
            return err != 183                              # ERROR_ALREADY_EXISTS
        import fcntl
        fh = open(os.path.join(updates_dir(), "instance.lock"), "w")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            _INSTANCE_HANDLE = fh
            return False
        _INSTANCE_HANDLE = fh
        return True
    except Exception:  # noqa: BLE001
        return True


# ------------------------------------------------------------------ install
def launch_install(pending: Dict) -> None:
    """Start the installer / helper for a downloaded update. The caller must quit right after."""
    path = pending.get("path", "")
    if not _verified(path, {"sha256": pending.get("sha256"), "size": pending.get("size")}):
        raise UpdateError("The downloaded update is missing or damaged.")
    kind = pending.get("kind")
    log = os.path.join(updates_dir(), "install.log")
    if kind == "windows-installer":
        _launch_inno(path, pending.get("target") or os.path.dirname(sys.executable), log)
    elif kind == "windows-portable":
        _launch_portable(path, pending.get("target") or os.path.dirname(sys.executable), log)
    elif kind == "macos-app":
        _launch_macos(path, pending["target"], log)
    else:
        raise UpdateError("Automatic install isn't supported for this copy of Lyridan.")


def _windows_scope(app_dir: str) -> str:
    """/ALLUSERS or /CURRENTUSER - whichever the existing install in app_dir used."""
    want = os.path.normcase(os.path.abspath(app_dir)).rstrip("\\/")
    try:
        import winreg
        key = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{WINDOWS_APP_ID}_is1"
        for root, view, scope in ((winreg.HKEY_CURRENT_USER, 0, "/CURRENTUSER"),
                                  (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY, "/ALLUSERS"),
                                  (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY, "/ALLUSERS")):
            try:
                with winreg.OpenKey(root, key, 0, winreg.KEY_READ | view) as k:
                    loc = winreg.QueryValueEx(k, "InstallLocation")[0]
            except OSError:
                continue
            if os.path.normcase(os.path.abspath(loc)).rstrip("\\/") == want:
                return scope
    except Exception:  # noqa: BLE001
        pass
    return "/CURRENTUSER" if _dir_writable(app_dir) else "/ALLUSERS"


def inno_arguments(app_dir: str, log: str, scope: str) -> str:
    return " ".join([
        "/SP-", "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCANCEL", "/CLOSEAPPLICATIONS",
        "/NORESTARTAPPLICATIONS", "/LYRIDANUPDATE=1", scope, f'/DIR="{app_dir}"', f'/LOG="{log}"'])


def _launch_inno(setup: str, app_dir: str, log: str) -> None:
    import ctypes
    params = inno_arguments(app_dir, log, _windows_scope(app_dir))
    # ShellExecute (not CreateProcess) so Windows can show the UAC prompt for an all-users install.
    r = ctypes.windll.shell32.ShellExecuteW(None, "open", setup, params, os.path.dirname(setup), 1)
    if r <= 32:
        raise UpdateError(f"Couldn't start the installer (error {r}).")


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


PORTABLE_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$zip = {zip}; $app = {app}; $log = {log}; $waitPid = {pid}
Start-Transcript -Path $log -Append | Out-Null
try {{
  Wait-Process -Id $waitPid -Timeout 60 -ErrorAction SilentlyContinue
  $tmp = Join-Path $env:TEMP ('lyridan-update-' + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $tmp | Out-Null
  & tar.exe -xf $zip -C $tmp 2>$null
  if (-not (Test-Path (Join-Path $tmp 'Lyridan.exe'))) {{ Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force }}
  if (-not (Test-Path (Join-Path $tmp 'Lyridan.exe'))) {{ throw 'Lyridan.exe not found in the update' }}
  $internal = Join-Path $app '_internal'; $old = Join-Path $app '_internal.old'
  if (Test-Path $old) {{ Remove-Item -LiteralPath $old -Recurse -Force }}
  for ($i = 0; $i -lt 20; $i++) {{ try {{ if (Test-Path $internal) {{ Rename-Item -LiteralPath $internal -NewName '_internal.old' }}; break }} catch {{ Start-Sleep -Milliseconds 500 }} }}
  try {{
    Copy-Item -Path (Join-Path $tmp '*') -Destination $app -Recurse -Force
  }} catch {{
    if (Test-Path $old) {{ if (Test-Path $internal) {{ Remove-Item -LiteralPath $internal -Recurse -Force }}; Rename-Item -LiteralPath $old -NewName '_internal' }}
    throw
  }}
  if (Test-Path $old) {{ Remove-Item -LiteralPath $old -Recurse -Force -ErrorAction SilentlyContinue }}
  Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}} catch {{ Write-Output ('Update failed: ' + $_) }}
Start-Process -FilePath (Join-Path $app 'Lyridan.exe')
Stop-Transcript | Out-Null
"""


def _launch_portable(zip_path: str, app_dir: str, log: str) -> None:
    script = os.path.join(updates_dir(), "apply_portable_update.ps1")
    with open(script, "w", encoding="utf-8-sig") as fh:
        fh.write(PORTABLE_SCRIPT.format(zip=_ps_quote(zip_path), app=_ps_quote(app_dir), log=_ps_quote(log),
                                        pid=os.getpid()))
    flags = 0x08000000 | 0x00000200                        # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                      "-File", script], creationflags=flags, close_fds=True, cwd=updates_dir())


MAC_SCRIPT = r"""#!/bin/bash
# Lyridan updater: replace the app bundle once Lyridan has quit, then start it again.
DMG={dmg}; DEST={dest}; PID={pid}; LOG={log}; SWAP={swap}
exec >>"$LOG" 2>&1
echo "=== $(date) update $DEST from $DMG"
for i in $(seq 1 120); do kill -0 "$PID" 2>/dev/null || break; sleep 0.5; done
MNT="$(mktemp -d /tmp/lyridan-update.XXXXXX)"
if hdiutil attach -nobrowse -readonly -noautoopen -mountpoint "$MNT" "$DMG"; then
  if [ -w "$(dirname "$DEST")" ] && [ -w "$DEST" ]; then
    /bin/bash "$SWAP" "$MNT/Lyridan.app" "$DEST"
  else
    /usr/bin/osascript -e "do shell script \"/bin/bash \" & quoted form of \"$SWAP\" & \" \" & quoted form of \"$MNT/Lyridan.app\" & \" \" & quoted form of \"$DEST\" with prompt \"Lyridan needs your password to install the update.\" with administrator privileges"
  fi
  echo "swap exit: $?"
  hdiutil detach "$MNT" -quiet || hdiutil detach "$MNT" -force -quiet
else
  echo "could not mount the disk image"
fi
rmdir "$MNT" 2>/dev/null
open "$DEST"
"""

MAC_SWAP = r"""#!/bin/bash
SRC="$1"; DEST="$2"
[ -d "$SRC" ] || { echo "missing $SRC"; exit 1; }
rm -rf "$DEST.new" "$DEST.old"
ditto "$SRC" "$DEST.new" || { rm -rf "$DEST.new"; exit 1; }
xattr -dr com.apple.quarantine "$DEST.new" 2>/dev/null
mv "$DEST" "$DEST.old" || { rm -rf "$DEST.new"; exit 1; }
if mv "$DEST.new" "$DEST"; then rm -rf "$DEST.old"; else mv "$DEST.old" "$DEST"; exit 1; fi
"""


def _sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def _launch_macos(dmg: str, bundle: str, log: str) -> None:
    folder = updates_dir()
    swap = os.path.join(folder, "swap_app.sh")
    with open(swap, "w", encoding="utf-8") as fh:
        fh.write(MAC_SWAP)
    script = os.path.join(folder, "apply_mac_update.sh")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(MAC_SCRIPT.format(dmg=_sh_quote(dmg), dest=_sh_quote(bundle), pid=os.getpid(),
                                   log=_sh_quote(log), swap=_sh_quote(swap)))
    subprocess.Popen(["/bin/bash", script], start_new_session=True, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ------------------------------------------------------------------ branches (Options dialog)
def list_branches(timeout: float = 15) -> List[Tuple[str, bool]]:
    """[(branch, has_published_build)], main and dev first. Uses the GitHub API (2-6 calls)."""
    accept = "application/vnd.github+json"
    names: List[str] = []
    for page in range(1, 6):
        batch = _get_json(f"{API_URL}/branches?per_page=100&page={page}", timeout, accept)
        names += [b.get("name", "") for b in batch if isinstance(b, dict)]
        if len(batch) < 100:
            break
    built = set()
    try:
        for r in _get_json(f"{API_URL}/releases?per_page=100", timeout, accept):
            if not any(a.get("name") == MANIFEST_NAME for a in r.get("assets") or []):
                continue
            if r.get("tag_name") == "dev-latest":
                built.add(DEV_BRANCH)
            elif not r.get("prerelease"):
                built.add(STABLE_BRANCH)
            body = r.get("body") or ""
            if BRANCH_MARKER in body:
                built.add(body.split(BRANCH_MARKER, 1)[1].split("-->", 1)[0].strip())
    except Exception:  # noqa: BLE001
        pass
    seen, out = set(), []
    order = [STABLE_BRANCH, DEV_BRANCH] + sorted((n for n in names if n not in (STABLE_BRANCH, DEV_BRANCH)),
                                                  key=str.lower)
    for n in order:
        if n in seen or is_excluded_branch(n) or (n not in names and n not in built):
            continue
        seen.add(n)
        out.append((n, n in built))
    return out
