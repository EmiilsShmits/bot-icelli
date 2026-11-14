#!/usr/bin/env bash
# Runs on a fresh Verda Ubuntu 24.04 GPU machine as root. Usage: bash remote_setup.sh <hours-until-deadline-minutes>
# Installs a venv with the packages in requirements.txt and arms the shutdown backstop.
set -euo pipefail
MIN=${1:-340}
shutdown -h +"$MIN" "gemma-parser-exp backstop" || true
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq python3-venv python3-dev tmux build-essential >/dev/null
cd /root/ip
python3 -m venv /root/venv
. /root/venv/bin/activate
pip install -q --upgrade pip
pip install -q torch --index-url https://download.pytorch.org/whl/cu128
pip install -q -r requirements.txt
python -c "import torch, transformers; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0)); print('transformers', transformers.__version__)"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
df -h /root | tail -1
echo SETUP_DONE
