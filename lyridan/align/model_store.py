"""Download-on-first-use storage for the alignment model."""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import urllib.error
import urllib.request
from typing import Callable, Optional

from ..settings import config_dir

RELEASE = "https://github.com/Elevatorisbest/Lyridan/releases/download/alignment-model-v1"
MODEL_INFO = {
    "name": "MMS forced aligner (Meta), int8 ONNX",
    "file": "mms_fa_int8.onnx",
    "meta": "mms_fa_int8.json",
    "url": f"{RELEASE}/mms_fa_int8.onnx",
    "meta_url": f"{RELEASE}/mms_fa_int8.json",
    "approx_mb": 340,
    "license": "CC-BY-NC 4.0 (non-commercial use only)",
    "license_url": "https://github.com/facebookresearch/fairseq/blob/main/examples/mms/LICENSE",
}


def _contexts():
    """System certificate store first (works behind company proxies / custom CAs),
    then the bundled certifi list (needed by some macOS Python builds)."""
    yield ssl.create_default_context()
    try:
        import certifi
        yield ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        pass


def _open(url: str, timeout: int = 60):
    last = None
    for ctx in _contexts():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Lyridan"})
            return urllib.request.urlopen(req, context=ctx, timeout=timeout)
        except urllib.error.URLError as e:
            last = e
            if not isinstance(getattr(e, "reason", None), ssl.SSLError):
                raise
    raise last


class ModelStore:
    def __init__(self, folder: Optional[str] = None):
        self.folder = folder or os.path.join(config_dir(), "models")
        os.makedirs(self.folder, exist_ok=True)
        override = os.environ.get("LYRIDAN_ALIGN_MODEL")
        self.model_path = override or os.path.join(self.folder, MODEL_INFO["file"])
        self.meta_path = (os.path.splitext(override)[0] + ".json") if override else \
            os.path.join(self.folder, MODEL_INFO["meta"])

    def is_installed(self) -> bool:
        return os.path.exists(self.model_path) and os.path.exists(self.meta_path)

    def meta(self) -> dict:
        with open(self.meta_path, encoding="utf-8") as fh:
            return json.load(fh)

    def remove(self):
        for p in (self.model_path, self.meta_path):
            try:
                os.remove(p)
            except OSError:
                pass

    def download(self, progress: Optional[Callable[[int, int], bool]] = None) -> None:
        """Download model + metadata. ``progress(done, total)`` may return False to cancel."""
        with _open(MODEL_INFO["meta_url"]) as r:
            meta = json.loads(r.read().decode("utf-8"))
        part = self.model_path + ".part"
        h = hashlib.sha256()
        with _open(MODEL_INFO["url"]) as r, open(part, "wb") as out:
            total = int(r.headers.get("Content-Length") or meta.get("size") or 0)
            done = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress and progress(done, total) is False:
                    out.close()
                    os.remove(part)
                    raise InterruptedError("Download cancelled")
        if meta.get("sha256") and h.hexdigest() != meta["sha256"]:
            os.remove(part)
            raise IOError("Downloaded model is corrupted (checksum mismatch). Please try again.")
        os.replace(part, self.model_path)
        with open(self.meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh)
