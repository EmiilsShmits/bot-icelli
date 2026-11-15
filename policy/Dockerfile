# bot-icelli submission image. Based on Aalto's aaltonomous/docker/baseline.Dockerfile (the reference submission).
# Contract (docs/research/aalto-humanoid.md §6): linux/amd64, CUDA >= 12.8 (finals GPU = RTX 5090), server on :8000
# within 120 s, weights inside the image (policy/weights/, git-ignored), <= 32 GB VRAM, <= 40 GB image.
#
# Build from the repo root:  bash policy/get_urdf.sh && make docker-build POLICY=v1
# Test:                      make docker-check
# Context allowlist:         .dockerignore
#
# Need torch? Add it to policy/requirements.txt (cu128 wheels bring their own CUDA). Need system cuDNN/TensorRT?
# Switch the base to nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04 (+~3 GB).
FROM nvidia/cuda:12.8.0-base-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONPATH=/app
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip libgomp1 && rm -rf /var/lib/apt/lists/*

COPY policy/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

ARG POLICY=hold
# v1.6g only: CPU-only torch + transformers for the offline Gemma 3 1B instruction parser (policy/instruction_gemma.py).
# Its weights come in with policy/ below: policy/weights/gemma-parser-1b/ (git-ignored, 2.0 GB; any image built from a
# checkout that has them carries them, only v1.6g loads them).
COPY policy/requirements-gemma.txt /tmp/requirements-gemma.txt
RUN if [ "$POLICY" = "v1.6g" ]; then pip3 install --no-cache-dir -r /tmp/requirements-gemma.txt; fi

WORKDIR /app
# G1 URDF (IK + safety filter): where Aalto's safety.py DEFAULT_URDF looks for it. Fetched by policy/get_urdf.sh.
COPY artifacts/urdf/g1_body29_hand14.urdf third_party/xr_teleoperate/assets/g1/
# Aalto's code: only the files the policy server needs (same set as their reference image, plus tasks.py).
ARG A=third_party/aaltonomous-humanoid/aaltonomous
COPY ${A}/__init__.py aaltonomous/
COPY ${A}/deploy/__init__.py ${A}/deploy/protocol.py ${A}/deploy/policy_server.py aaltonomous/deploy/
COPY ${A}/interface/__init__.py ${A}/interface/safety.py ${A}/interface/calibration.py ${A}/interface/tasks.py \
     ${A}/interface/joint_spec.yaml ${A}/interface/calibration.yaml aaltonomous/interface/
COPY ${A}/scene/__init__.py ${A}/scene/scene.py ${A}/scene/scene.yaml aaltonomous/scene/
COPY ${A}/baselines/__init__.py aaltonomous/baselines/
COPY ${A}/baselines/classical/*.py ${A}/baselines/classical/config.yaml aaltonomous/baselines/classical/
# v1.5: Aalto's oracle planner (pure numpy + the classical planner; no Isaac) and the home pose it uses.
COPY ${A}/sim/oracle.py aaltonomous/sim/
COPY ${A}/sim/aalto_task/__init__.py ${A}/sim/aalto_task/layout.py aaltonomous/sim/aalto_task/
# Emīls's instruction parser (rule stage; offline, no weights). v1.6's Decision stage is policy/instruction_d1.py.
COPY training/instruction_parser/rule_parser.py training/instruction_parser/spec.py training/instruction_parser/
# v1.6g's Gemma stage uses the training prompt itself (prompts.ft_messages).
COPY training/instruction_parser/prompts.py training/instruction_parser/
COPY policy/ policy/

# v1.6 only: the Gemini key, from a BuildKit secret (never in the repo or the build context). Without it v1.6 runs as
# v1.5 (offline). The key ends up readable inside the image (team decision for the ADK image, Sat 14 Nov):
#   make docker-build POLICY=v1.6 GEMINI_KEY_FILE=~/adk_key.env      (a file with GEMINI_API_KEY=... or just the key)
RUN --mount=type=secret,id=gemini,required=false \
    if [ -s /run/secrets/gemini ]; then python3 -c "import re; t = open('/run/secrets/gemini').read(); \
m = re.search(r'GEMINI_API_KEY=[\"\']?([^\s\"\']+)', t); open('/root/.decision_key', 'w').write(m.group(1) if m else t.strip())" \
    && chmod 600 /root/.decision_key && echo "Gemini key baked in"; fi

ENV POLICY=${POLICY}
# Load-time check at build: the chosen policy constructs (config, URDF, calibration, parser all load). v1.5/v1.6/v1.6g
# also import task 3's module, which their reset() imports on every episode (.dockerignore must let it in).
RUN python3 -c "import os, sys; sys.path.insert(0, '/app/policy'); import server; server.POLICIES[os.environ['POLICY']](); \
p = os.environ['POLICY']; p.startswith(('v1.5', 'v1.6')) and __import__('decision_oracle.insert')"
# v1.6g: fail the build if the Gemma weights are missing or fail their self-test (else the image would run as v1.6).
RUN if [ "$POLICY" = "v1.6g" ]; then python3 -c "import sys; sys.path.insert(0, '/app/policy'); \
from instruction_gemma import GemmaInstruction; g = GemmaInstruction(); assert g.enabled, g.why_off; \
print('Gemma parser OK: load', g.load_s, 's, self-test', g.self_test_s, 's')"; fi

EXPOSE 8000
CMD ["python3", "/app/policy/server.py", "--port", "8000"]
