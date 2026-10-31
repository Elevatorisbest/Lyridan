"""Auto-updater logic (no network, no Qt)."""
import hashlib
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from lyridan import update_channels as ch  # noqa: E402
from lyridan import updater as up  # noqa: E402


@pytest.fixture(autouse=True)
def _cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "cfg"))
    monkeypatch.setattr(sys, "platform", "linux")


def info(branch="dev", build=27, commit="a" * 40, channel="dev", ci=True):
    return {"channel": channel, "branch": branch, "build_number": str(build), "commit": commit,
            "label": f"2.0.0-dev.{build}", "builder": "GitHub Actions" if ci else "local (pc)"}


def manifest(branch="dev", build=28, commit="b" * 40, channel="dev"):
    return {"schema": 1, "app": "Lyridan", "branch": branch, "channel": channel,
            "track": "main" if channel == "stable" else branch, "build_number": str(build), "commit": commit,
            "label": f"2.0.0-dev.{build}", "tag": ch.release_tag(branch) or "v2.0.0",
            "assets": {"windows-x64-setup": {"name": "L-Setup.exe", "size": 3, "sha256": "x"}}}


WIN = up.InstallTarget("windows-installer", "windows-x64-setup", "C:/Lyridan")
NONE = up.InstallTarget(reason="source")


# ----------------------------------------------------------------- channels
def test_tags_and_urls():
    assert ch.release_tag("main") is None
    assert ch.manifest_url("main").endswith("/releases/latest/download/update.json")
    assert ch.release_tag("dev") == "dev-latest"
    assert ch.release_tag("some-feature") == "some-feature-latest"
    assert ch.release_tag("feature/x").startswith("feature-x-")
    assert ch.release_tag("feature/x") != ch.release_tag("feature-x")
    assert ch.release_tag("Dev") != "dev-latest" and ch.release_tag("MAIN") != "MAIN-latest"


@pytest.mark.parametrize("name,excluded", [("v1.1.1", True), ("1.1", True), ("v1.0.0", True), ("", True),
                                           ("workflowtest", True), ("digitalstudiothemetest", True),
                                           ("main", False), ("dev", False), ("v2.0", False), ("feature", False)])
def test_excluded(name, excluded):
    assert ch.is_excluded_branch(name) is excluded


def test_asset_keys():
    assert ch.asset_key("Lyridan-2.0.0-dev.27-Windows-x64-Setup.exe") == "windows-x64-setup"
    assert ch.asset_key("Lyridan-2.0.0-macOS-AppleSilicon.dmg") == "macos-arm64-dmg"
    assert ch.asset_key("Lyridan-2.0.0-macOS-Intel-Installer.pkg") == "macos-x86_64-pkg"
    assert ch.asset_key("Lyridan.exe") is None


def test_target_track():
    assert up.target_track("", info("dev")) == "dev"
    assert up.target_track("", info("v2.0.1", channel="stable")) == "main"
    assert up.target_track("v1.1.1", info("dev")) == "dev"          # never v1.1.1
    assert up.target_track("feature", info("dev")) == "feature"
    assert up.target_track("", info("HEAD")) == "main"


# ----------------------------------------------------------------- evaluate
def test_newer_build_same_branch_is_automatic():
    o = up.evaluate(info(), manifest(), "dev", up.UpdateState(), WIN)
    assert o and o.kind == "update" and o.auto and o.asset["name"] == "L-Setup.exe"


@pytest.mark.parametrize("build,commit", [(27, "b" * 40), (26, "b" * 40), (40, "a" * 40)])
def test_same_or_older_not_offered(build, commit):
    assert up.evaluate(info(), manifest(build=build, commit=commit), "dev", up.UpdateState(), WIN) is None


def test_stable_manifest_on_dev_track_ignored():
    assert up.evaluate(info(), manifest("main", channel="stable"), "dev", up.UpdateState(), WIN) is None


def test_branch_switch_needs_request():
    m = manifest("main", build=5, channel="stable")                    # older run number - still offered
    o = up.evaluate(info(), m, "main", up.UpdateState(), WIN)
    assert o.kind == "switch" and not o.auto
    o = up.evaluate(info(), m, "main", up.UpdateState({"switch_requested": "main"}), WIN)
    assert o.kind == "switch" and o.auto


def test_skip_pin_failed_and_unsupported():
    m = manifest()
    assert up.evaluate(info(), m, "dev", up.UpdateState({"skipped": m["commit"]}), WIN) is None
    assert up.evaluate(info(), m, "dev", up.UpdateState({"skipped": m["commit"]}), WIN, manual=True)
    assert not up.evaluate(info(), m, "dev", up.UpdateState({"pinned": "a" * 40}), WIN).auto
    assert not up.evaluate(info(), m, "dev", up.UpdateState({"failed": [m["commit"]]}), WIN).auto
    o = up.evaluate(info(), m, "dev", up.UpdateState(), NONE)
    assert not o.auto and o.asset is None
    mac = up.InstallTarget("macos-app", "macos-arm64-dmg", "/Applications/Lyridan.app")
    assert not up.evaluate(info(), m, "dev", up.UpdateState(), mac).auto          # no DMG in that build


def test_local_build_only_on_manual_check():
    m = manifest()
    assert up.evaluate(info(ci=False), m, "dev", up.UpdateState(), WIN) is None
    o = up.evaluate(info(ci=False), m, "dev", up.UpdateState(), WIN, manual=True)
    assert o.kind == "rebuild" and not o.auto


# ----------------------------------------------------------------- launch bookkeeping
def _pending(tmp_path, **kw):
    f = tmp_path / "L-Setup.exe"
    f.write_bytes(b"abc")
    p = {"commit": "b" * 40, "label": "2.0.0-dev.28", "track": "dev", "kind": WIN.kind, "target": WIN.path,
         "path": str(f), "sha256": hashlib.sha256(b"abc").hexdigest(), "size": 3, "from_commit": "a" * 40,
         "attempts": 0}
    p.update(kw)
    return p


def test_pending_installs_on_next_start(tmp_path):
    st = up.UpdateState({"pending": _pending(tmp_path), "last_run_commit": "a" * 40})
    out = up.on_startup(True, True, "", info=info(), state=st, target=WIN)
    assert out.install and out.install["attempts"] == 1
    assert up.UpdateState.load().pending["attempts"] == 1


@pytest.mark.parametrize("kw", [dict(has_file_args=True), dict(first_instance=False)])
def test_pending_waits_when_busy(tmp_path, kw):
    st = up.UpdateState({"pending": _pending(tmp_path)})
    out = up.on_startup(True, True, "", info=info(), state=st, target=WIN, **kw)
    assert out.install is None and st.pending is not None


def test_pending_dropped_when_damaged_or_branch_changed(tmp_path):
    st = up.UpdateState({"pending": _pending(tmp_path, sha256="0" * 64)})
    assert up.on_startup(True, True, "", info=info(), state=st, target=WIN).install is None
    assert st.pending is None
    st = up.UpdateState({"pending": _pending(tmp_path)})
    assert up.on_startup(True, True, "main", info=info(), state=st, target=WIN).install is None
    assert st.pending is None


def test_update_succeeded(tmp_path):
    st = up.UpdateState({"pending": _pending(tmp_path, attempts=1), "last_run_commit": "a" * 40,
                         "switch_requested": "dev"})
    out = up.on_startup(True, True, "", info=info(build=28, commit="b" * 40), state=st, target=WIN)
    assert "updated" in out.events and "manual" not in out.events and st.pending is None
    assert st.switch_requested == "" and not os.path.exists(tmp_path / "L-Setup.exe")


def test_update_failed_is_not_retried(tmp_path):
    st = up.UpdateState({"pending": _pending(tmp_path, attempts=1), "last_run_commit": "a" * 40})
    out = up.on_startup(True, True, "", info=info(), state=st, target=WIN)
    assert "failed" in out.events and out.level == "warning" and st.failed == ["b" * 40]
    assert out.install is None and st.pending is None
    o = up.evaluate(info(), manifest(), "dev", st, WIN)
    assert o and not o.auto


def test_manual_install_of_other_version(tmp_path):
    st = up.UpdateState({"pending": _pending(tmp_path), "last_run_commit": "a" * 40, "last_run_build": "27",
                         "last_run_track": "dev"})
    out = up.on_startup(True, True, "", info=info(build=30, commit="c" * 40), state=st, target=WIN)
    assert "stale" in out.events and "manual" in out.events and st.pending is None and not st.pinned
    out = up.on_startup(True, True, "", info=info(build=20, commit="d" * 40), state=st, target=WIN)
    assert "pinned" in out.events and st.pinned == "d" * 40          # downgrade by hand: keep it
    assert not up.evaluate(info(build=20, commit="d" * 40), manifest(), "dev", st, WIN).auto
    up.on_startup(True, True, "", info=info(build=29, commit="e" * 40), state=st, target=WIN)
    assert st.pinned == ""


# ----------------------------------------------------------------- download
def test_download_verifies_checksum(tmp_path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"installer-bytes")
    good = hashlib.sha256(b"installer-bytes").hexdigest()
    m = manifest()
    m["assets"]["windows-x64-setup"] = {"name": "L-Setup.exe", "size": 15, "sha256": good}
    o = up.evaluate(info(), m, "dev", up.UpdateState(), WIN)
    seen = []
    path = up.download(o, progress=lambda d, t: seen.append(d), url=src.as_uri())
    assert open(path, "rb").read() == b"installer-bytes" and seen[-1] == 15
    assert up.download(o, url="file:///does/not/matter") == path       # already downloaded + verified
    o.asset = dict(o.asset, name="Other-Setup.exe", sha256="0" * 64)
    with pytest.raises(up.UpdateError):
        up.download(o, url=src.as_uri())
    assert not os.path.exists(path + ".part")
    p = up.make_pending(up.evaluate(info(), m, "dev", up.UpdateState(), WIN), path, WIN)
    assert up.UpdateState.load().pending["path"] == path == p["path"]


def test_inno_arguments():
    a = up.inno_arguments(r"C:\Program Files\Lyridan", r"C:\log.txt", "/ALLUSERS")
    for part in ("/SILENT", "/LYRIDANUPDATE=1", "/ALLUSERS", '/DIR="C:\\Program Files\\Lyridan"',
                 "/NORESTARTAPPLICATIONS"):
        assert part in a


def test_scripts_format():
    up.PORTABLE_SCRIPT.format(zip="'z'", app="'a'", log="'l'", pid=1)
    s = up.MAC_SCRIPT.format(dmg="'d'", dest="'/Applications/Lyridan.app'", pid=1, log="'l'", swap="'s'")
    assert "hdiutil attach" in s and "with administrator privileges" in s


# ----------------------------------------------------------------- CI manifest
def test_make_update_manifest(tmp_path):
    import make_update_manifest as mk
    for n in ("Lyridan-2.0.0-dev.30-Windows-x64-Setup.exe", "Lyridan-2.0.0-dev.30-macOS-Intel.dmg", "notes.txt"):
        (tmp_path / n).write_bytes(n.encode())
    bi = {"channel": "dev", "branch": "feature/x", "version": "2.0.0", "label": "2.0.0-dev.30",
          "build_number": "30", "commit": "f" * 40, "build_time": "2026-10-31T01:00:00Z"}
    m = mk.build_manifest(bi, str(tmp_path), ch.release_tag("feature/x"))
    assert set(m["assets"]) == {"windows-x64-setup", "macos-x86_64-dmg"}
    assert m["track"] == "feature/x" and m["tag"] == ch.release_tag("feature/x")
    assert m["assets"]["windows-x64-setup"]["sha256"] == hashlib.sha256(
        b"Lyridan-2.0.0-dev.30-Windows-x64-Setup.exe").hexdigest()
    st = mk.build_manifest(dict(bi, channel="stable", branch="v2.0.1"), str(tmp_path), "v2.0.1")
    assert st["track"] == "main"
    o = up.evaluate(info("v2.0.0", 10, channel="stable"), json.loads(json.dumps(st)), "main",
                    up.UpdateState(), WIN)
    assert o and o.kind == "update"


def test_settings_roundtrip():
    from lyridan.settings import Settings
    s = Settings.from_json({"update_branch": "dev", "update_auto_install": False})
    assert s.update_branch == "dev" and not s.update_auto_install and s.update_check
    assert not Settings().update_auto_install                                     # off by default
    assert not Settings.from_json({"update_auto_install": True}).update_auto_install   # dev.29-31 default reset
    s = Settings.from_json({"update_auto_install": True, "update_prefs_rev": 1})     # chosen in Options: kept
    assert s.update_auto_install and Settings.from_json(s.to_json()).update_auto_install


def test_dev_build_number_restarts_for_each_version(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("wbi", os.path.join(ROOT, "tools", "write_build_info.py"))
    wbi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wbi)
    calls = []

    def fake_git(*args):
        calls.append(args)
        if args[0] == "log":
            return "abc123" if 'VERSION = "2.0.1"' in args else ""
        if args[:2] == ("rev-list", "--count"):
            return {"abc123..HEAD": "0"}.get(args[2], "")
        return ""
    monkeypatch.setattr(wbi, "git", fake_git)
    assert wbi.version_build("2.0.1") == "1"          # the version-bump commit itself
    monkeypatch.setattr(wbi, "git", lambda *a: "abc123" if a[0] == "log" else "4")
    assert wbi.version_build("2.0.1") == "5"
    monkeypatch.setattr(wbi, "git", lambda *a: "")
    assert wbi.version_build("2.0.1") == ""           # shallow clone: caller falls back to the run number
