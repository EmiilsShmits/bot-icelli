"""Download model weights into the HF cache (run with HF_TOKEN in the environment, never saved).
  python download.py google/gemma-3-270m-it google/gemma-3-1b-it ...
"""
import sys
import time

from huggingface_hub import snapshot_download

for m in sys.argv[1:]:
    t = time.time()
    try:
        p = snapshot_download(m, allow_patterns=["*.json", "*.safetensors", "*.model", "*.txt", "*.jinja", "tokenizer*"])
        print(f"OK {m} {time.time() - t:.0f}s {p}", flush=True)
    except Exception as e:
        print(f"FAIL {m}: {type(e).__name__}: {str(e)[:200]}", flush=True)
print("DOWNLOADS_DONE", flush=True)
