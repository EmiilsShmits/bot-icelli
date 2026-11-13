# bot-icelli submission image. Based on Aalto's aaltonomous/docker/submission.Dockerfile.
# Contract (docs/research/aalto-humanoid.md §6): linux/amd64, CUDA >= 12.8 (finals GPU = RTX 5090), server on :8000 within 120 s,
# weights inside the image (policy/weights/, git-ignored), <= 32 GB VRAM, <= 40 GB image.
#
# Build from the repo root:  make docker-build             (POLICY=hold by default)
# Test:                      make docker-check
# Context allowlist:         .dockerignore (only policy/ and Aalto's deploy package go in)
#
# Need torch? Add it to policy/requirements.txt (cu128 wheels bring their own CUDA). Need system cuDNN/TensorRT?
# Switch the base to nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04 (+~3 GB).
FROM nvidia/cuda:12.8.0-base-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONPATH=/app
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip && rm -rf /var/lib/apt/lists/*

COPY policy/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app
COPY third_party/aaltonomous-humanoid/aaltonomous/__init__.py aaltonomous/__init__.py
COPY third_party/aaltonomous-humanoid/aaltonomous/deploy aaltonomous/deploy
COPY policy/ policy/

ARG POLICY=hold
ENV POLICY=${POLICY}
EXPOSE 8000
CMD ["python3", "/app/policy/server.py", "--port", "8000"]
