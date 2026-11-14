"""v1.6g: run_v16g_retrain.sh on one Modal H100 (Sun 15 Nov ~01:00 Verda had no free GPU in any location). The 14 Nov
checkpoint s1b-full was kept on one laptop only, so the Gemma 3 1B student is trained again with the same recipe.

    # from the repo root, once: the deterministic data (stdlib only; gen_templates.py needs Aalto's tasks.py)
    cd training/instruction_parser
    python gen_train.py --n 16000 --seed 0 --out ../../artifacts/instruction_parser/data_train/prog_raw.jsonl
    python gen_templates.py --n 1200 --out ../../artifacts/instruction_parser/data_train/templates.jsonl
    modal run --detach modal_retrain.py
    modal volume get v16g-retrain ckpt/s1b-full <dest>     # -> policy/weights/gemma-parser-1b for the v1.6g image

Out (Modal volume `v16g-retrain`): ckpt/s1b-full (the student), logs/ (retrain, teacher, fine-tune, eval lines),
data_train/ (the exact training data, incl. the teacher paraphrases).
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import modal

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE.parents[1] / "artifacts" / "instruction_parser" / "data_train"

app = modal.App("bot-icelli-v16g-retrain")
vol = modal.Volume.from_name("v16g-retrain", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch==2.11.0", index_url="https://download.pytorch.org/whl/cu128")
    .pip_install("transformers==5.23.0", "accelerate", "peft", "datasets", "huggingface_hub", "sentencepiece",
                 "protobuf")
    .add_local_dir(str(HERE), "/root/ip", ignore=["results/**", "**/__pycache__/**", "*.pyc", "data_train/**"])
    .add_local_dir(str(DATA), "/root/ip/data_train")
)


@app.function(gpu="H100", image=image, volumes={"/out": vol}, timeout=3 * 3600, cpu=8, memory=65536)
def retrain() -> int:
    os.makedirs("/out/logs", exist_ok=True)
    env = dict(os.environ, PY="python", CKPT="/out/ckpt", LOGS="/out/logs", IP_DIR="/root/ip")
    with open("/out/logs/retrain.log", "w") as log:
        p = subprocess.Popen(["bash", "run_v16g_retrain.sh"], cwd="/root/ip", env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
            if line.startswith(("teacher done", "ft 1b start")):
                vol.commit()
        rc = p.wait()
    shutil.copytree("/root/ip/data_train", "/out/data_train", dirs_exist_ok=True)
    vol.commit()
    return rc


@app.local_entrypoint()
def main():
    print("retrain exit code:", retrain.remote())
