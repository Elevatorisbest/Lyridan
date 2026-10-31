"""Export Meta's MMS forced-alignment model (torchaudio MMS_FA) to an int8 ONNX file.

  pip install torch torchaudio onnx onnxruntime --index-url https://download.pytorch.org/whl/cpu
  python tools/export_alignment_model.py [out_dir]

Produces ``mms_fa_int8.onnx`` (~320 MB) + ``mms_fa_int8.json`` (labels, sha256).
The CI workflow ``alignment-model.yml`` runs this and publishes the files as the
``alignment-model-v1`` GitHub release, from which Lyridan downloads on first use.

Model: MMS-300M CTC aligner trained by Meta on 23k hours / 1100+ languages
(uroman-romanized text). Licence: CC-BY-NC 4.0 (non-commercial) - see README.
"""
import hashlib
import json
import os
import sys

import numpy as np
import torch
import torchaudio

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build",
                                                          "model")
os.makedirs(OUT, exist_ok=True)
fp32 = os.path.join(OUT, "mms_fa_fp32.onnx")
int8 = os.path.join(OUT, "mms_fa_int8.onnx")

bundle = torchaudio.pipelines.MMS_FA
model = bundle.get_model(with_star=False).eval()
labels = list(bundle.get_labels(star=None))


class Wrapper(torch.nn.Module):
    """Inner wav2vec2 model + log-softmax.

    The torchaudio wrapper layer-normalises the waveform with a dynamic shape, which
    ONNX cannot export, so Lyridan normalises the audio itself before inference
    ((x - mean) / sqrt(var + 1e-5)).
    """

    def __init__(self, m):
        super().__init__()
        self.m = m.model

    def forward(self, wav):  # (1, samples) float32 @16 kHz, normalised -> (1, frames, 28) log-probs
        em, _ = self.m(wav)
        return torch.log_softmax(em, dim=-1)


def normalise(x):
    return (x - x.mean()) / torch.sqrt(x.var(unbiased=False) + 1e-5)


w = Wrapper(model)
dummy = normalise(torch.randn(1, 16000 * 4))
torch.onnx.export(w, (dummy,), fp32, input_names=["audio"], output_names=["log_probs"],
                  dynamic_axes={"audio": {1: "samples"}, "log_probs": {1: "frames"}},
                  opset_version=17, do_constant_folding=True, dynamo=False)

from onnxruntime.quantization import QuantType, quantize_dynamic  # noqa: E402

quantize_dynamic(fp32, int8, weight_type=QuantType.QInt8, op_types_to_quantize=["MatMul", "Gemm"])

# parity check fp32 torch vs int8 onnx
import onnxruntime as ort  # noqa: E402

x = normalise(torch.randn(1, 16000 * 6) * 0.1)
with torch.no_grad():
    ref = torch.log_softmax(model(x)[0], dim=-1).numpy()
sess = ort.InferenceSession(int8, providers=["CPUExecutionProvider"])
got = sess.run(None, {"audio": x.numpy()})[0]
agree = float((ref.argmax(-1) == got.argmax(-1)).mean())
print("frames", ref.shape, "argmax agreement int8 vs fp32:", agree)

sha = hashlib.sha256(open(int8, "rb").read()).hexdigest()
meta = {"name": "mms_fa_int8", "labels": labels, "blank": 0, "sample_rate": bundle.sample_rate,
        "frame_seconds": 320 / bundle.sample_rate, "sha256": sha, "size": os.path.getsize(int8),
        "source": "torchaudio.pipelines.MMS_FA", "license": "CC-BY-NC-4.0"}
json.dump(meta, open(os.path.join(OUT, "mms_fa_int8.json"), "w"), indent=2)
os.remove(fp32)
print(json.dumps({k: v for k, v in meta.items() if k != "labels"}, indent=2))
