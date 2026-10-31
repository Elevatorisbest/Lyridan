"""Write the update.json manifest for a release (run by the publish job in build.yml).

  python tools/make_update_manifest.py --info build_info.json --dir artifacts --tag dev-latest \
      [--out artifacts/update.json]
  python tools/make_update_manifest.py --tag-for <branch>     # prints the release tag for a branch

The app (lyridan/updater.py) reads it to decide whether to update and which file to download.
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lyridan.update_channels import (MANIFEST_SCHEMA, STABLE_BRANCH, asset_key, is_excluded_branch,  # noqa: E402
                                     release_page, release_tag)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(info: dict, folder: str, tag: str) -> dict:
    assets = {}
    for name in sorted(os.listdir(folder)):
        key = asset_key(name)
        path = os.path.join(folder, name)
        if key and os.path.isfile(path):
            assets[key] = {"name": name, "size": os.path.getsize(path), "sha256": sha256(path)}
    channel = info.get("channel", "dev")
    branch = info.get("branch", "")
    return {
        "schema": MANIFEST_SCHEMA,
        "app": "Lyridan",
        "channel": channel,
        "branch": branch,
        "track": STABLE_BRANCH if channel == "stable" else branch,
        "version": info.get("version", ""),
        "label": info.get("label", ""),
        "build_number": info.get("build_number", ""),
        "commit": info.get("commit", ""),
        "commit_short": info.get("commit_short", ""),
        "commit_date": info.get("commit_date", ""),
        "commit_subject": info.get("commit_subject", ""),
        "build_time": info.get("build_time") or info.get("build_date", ""),
        "published": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tag": tag,
        "release_url": release_page(tag),
        "run_url": info.get("run_url", ""),
        "assets": assets,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--info")
    p.add_argument("--dir")
    p.add_argument("--tag")
    p.add_argument("--out")
    p.add_argument("--tag-for", dest="tag_for", metavar="BRANCH")
    a = p.parse_args()
    if a.tag_for is not None:
        if is_excluded_branch(a.tag_for):
            sys.exit(f"branch {a.tag_for!r} is excluded from builds")
        print(release_tag(a.tag_for) or "")
        return
    with open(a.info, encoding="utf-8") as fh:
        info = json.load(fh)
    m = build_manifest(info, a.dir, a.tag)
    if not m["assets"]:
        sys.exit("no installers found in " + a.dir)
    text = json.dumps(m, indent=2, ensure_ascii=False)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
