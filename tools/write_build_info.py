"""Write build metadata before packaging (run by CI and by the local build scripts).

  python tools/write_build_info.py [--channel dev|stable] [--print json|version] [--json-out FILE]

Channel detection (when --channel is not given):
  * GitHub Actions on branch "main" or on a "v*" tag  -> stable
  * any other branch / pull request / local build      -> dev

Outputs
  * lyridan/_build.py                    BUILD_INFO dict read by lyridan/buildinfo.py
  * packaging/windows/version_info.txt   Windows file-version resource
Prints the version label used in file names, e.g. "2.0.0" or "2.0.0-dev.37".

Dev build numbers ("-dev.N") start again at 1 for every new VERSION: N counts the commits since the
commit that set the current VERSION in lyridan/__init__.py (that commit itself is dev.1). The
internal "build_number" (the CI run number) keeps counting up across versions, because the
auto-updater of already-installed builds uses it to tell which build is newer.
"""
import argparse
import datetime
import json
import os
import platform
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lyridan import VERSION  # noqa: E402


def git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL,
                                       text=True).strip()
    except Exception:  # noqa: BLE001
        return ""


def version_build(version: str) -> str:
    """Dev build number within ``version``: 1 for the commit that set it, +1 for every commit after."""
    bump = git("log", "-1", "--format=%H", "-S", f'VERSION = "{version}"', "--", "lyridan/__init__.py")
    if not bump:
        return ""                     # shallow clone / not a git checkout
    since = git("rev-list", "--count", f"{bump}..HEAD")
    return str(int(since) + 1) if since.isdigit() else ""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--channel", choices=["dev", "stable"])
    p.add_argument("--print", dest="out", choices=["version", "json"], default="version")
    p.add_argument("--json-out", dest="json_out", help="also write BUILD_INFO as JSON to this file")
    a = p.parse_args()
    env = os.environ

    ref_type = env.get("GITHUB_REF_TYPE", "")
    ref_name = env.get("GITHUB_REF_NAME", "")
    if env.get("GITHUB_EVENT_NAME") == "pull_request":
        branch = env.get("GITHUB_HEAD_REF", "") or ref_name
    elif ref_type == "tag":
        branch = ref_name
    else:
        branch = ref_name or git("rev-parse", "--abbrev-ref", "HEAD")
    if a.channel:
        channel = a.channel
    elif env.get("GITHUB_ACTIONS") == "true" and (
            (ref_type == "branch" and ref_name == "main") or (ref_type == "tag" and ref_name.startswith("v"))):
        channel = "stable"
    else:
        channel = "dev"

    commit = env.get("GITHUB_SHA") or git("rev-parse", "HEAD")
    run_number = env.get("GITHUB_RUN_NUMBER", "")
    run_id = env.get("GITHUB_RUN_ID", "")
    repo = env.get("GITHUB_REPOSITORY", "")
    server = env.get("GITHUB_SERVER_URL", "https://github.com")
    build_no = run_number or git("rev-list", "--count", "HEAD") or "0"
    dev_build = version_build(VERSION) or build_no

    now = datetime.datetime.now(datetime.timezone.utc)
    label = VERSION if channel == "stable" else f"{VERSION}-dev.{dev_build}"
    info = {
        "channel": channel,
        "version": VERSION,
        "label": label,
        "build_number": build_no,          # CI run number: only ever goes up (the updater compares it)
        "dev_build": dev_build,            # the N in "-dev.N": starts at 1 for each VERSION
        "run_attempt": env.get("GITHUB_RUN_ATTEMPT", ""),
        "branch": branch,
        "ref_type": ref_type or "branch",
        "commit": commit,
        "commit_short": commit[:7],
        "commit_count": git("rev-list", "--count", "HEAD"),
        "commit_date": git("log", "-1", "--format=%cI"),
        "commit_subject": git("log", "-1", "--format=%s")[:200],
        "commit_author": git("log", "-1", "--format=%an"),
        "dirty": bool(git("status", "--porcelain", "--untracked-files=no")) and not env.get("GITHUB_ACTIONS"),
        "build_date": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "build_time": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "builder": "GitHub Actions" if env.get("GITHUB_ACTIONS") == "true" else f"local ({platform.node()})",
        "builder_os": env.get("RUNNER_OS") or platform.system(),
        "builder_arch": env.get("RUNNER_ARCH") or platform.machine(),
        "builder_image": env.get("ImageOS", "") or env.get("RUNNER_NAME", ""),
        "build_python": platform.python_version(),
        "workflow": env.get("GITHUB_WORKFLOW", ""),
        "event": env.get("GITHUB_EVENT_NAME", ""),
        "repo_url": f"{server}/{repo}" if repo else "",
        "commit_url": f"{server}/{repo}/commit/{commit}" if repo and commit else "",
        "run_url": f"{server}/{repo}/actions/runs/{run_id}" if repo and run_id else "",
    }

    with open(os.path.join(ROOT, "lyridan", "_build.py"), "w", encoding="utf-8") as fh:
        fh.write("# Generated by tools/write_build_info.py - do not edit.\n")
        fh.write("BUILD_INFO = " + json.dumps(info, indent=4, ensure_ascii=False)
                 .replace(": true", ": True").replace(": false", ": False") + "\n")

    nums = [int(x) for x in VERSION.split(".")[:3]] + [int(dev_build) if channel == "dev" and dev_build.isdigit() else 0]
    tup = ", ".join(str(min(n, 65535)) for n in nums)
    desc = "Lyridan - lyrics to Rocksmith vocals" + (" (development build)" if channel == "dev" else "")
    vi = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({tup}), prodvers=({tup}), mask=0x3f, flags={'0x2' if channel == 'dev' else '0x0'},
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Elevatorisbest'),
      StringStruct('FileDescription', '{desc}'),
      StringStruct('FileVersion', '{label}'),
      StringStruct('InternalName', 'Lyridan'),
      StringStruct('LegalCopyright', 'GPL-2.0'),
      StringStruct('OriginalFilename', 'Lyridan.exe'),
      StringStruct('ProductName', 'Lyridan'),
      StringStruct('ProductVersion', '{label}{('+' + commit[:7]) if channel == 'dev' and commit else ''}'),
      StringStruct('Comments', '{channel} build from {branch or "unknown"}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    os.makedirs(os.path.join(ROOT, "packaging", "windows"), exist_ok=True)
    with open(os.path.join(ROOT, "packaging", "windows", "version_info.txt"), "w", encoding="utf-8") as fh:
        fh.write(vi)
    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as fh:
            json.dump(info, fh, indent=2, ensure_ascii=False)
    print(json.dumps(info, indent=2) if a.out == "json" else label)


if __name__ == "__main__":
    main()
