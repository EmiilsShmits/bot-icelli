"""Phase 4: does a candidate fit the submission? Run one process per (method, device), page cache dropped first.

  python fitcheck.py hf:google/gemma-4-E2B-it:B --device cuda
  python fitcheck.py ft:/root/ckpt/s270m-full:B --device cpu --threads 8
Prints one JSON line: load_to_first_answer_s, peak_vram_gb, weights_gb, latency p50/p95 (warm, batch 1).
"""
from __future__ import annotations

import argparse
import json
import os
import time

T0 = time.time()


def dir_size_gb(path):
    tot = 0
    for root, _, files in os.walk(path):
        for f in files:
            if f.endswith((".safetensors", ".bin")):
                tot += os.path.getsize(os.path.realpath(os.path.join(root, f)))
    return tot / 1e9


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("method")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--n", type=int, default=30)
    a = ap.parse_args()
    import torch
    if a.threads:
        torch.set_num_threads(a.threads)
    from llm import HFMethod
    texts = [json.loads(l)["text"] for l in open("data/t2a.jsonl")][: a.n + 1]
    m = HFMethod(a.method, device=a.device)
    first = m.predict_batch([texts[0]])
    load_to_first = time.time() - T0
    lat = []
    for t in texts[1:]:
        s = time.time()
        m.predict_batch([t])
        lat.append(time.time() - s)
    lat.sort()
    model_id = m.model_id
    if os.path.isdir(model_id):
        wpath = model_id
    else:
        import glob
        snaps = glob.glob(os.path.expanduser(f"~/.cache/huggingface/hub/models--{model_id.replace('/', '--')}/snapshots/*"))
        wpath = snaps[0] if snaps else ""
    out = {"method": a.method, "device": a.device, "threads": a.threads or torch.get_num_threads(),
           "load_to_first_answer_s": round(load_to_first, 2), "model_load_s": round(m.load_s, 2),
           "weights_gb_on_disk": round(dir_size_gb(wpath), 3),
           "latency_p50_s": round(lat[len(lat) // 2], 4), "latency_p95_s": round(lat[int(0.95 * (len(lat) - 1))], 4),
           "first_answer": str(first[0].get("pred"))[:80]}
    if a.device == "cuda":
        out["peak_vram_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 3)
        out["gpu"] = torch.cuda.get_device_name(0)
    print(json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
