# bot-icelli: Marcus's ADK agent (github.com/marcusoberg/junction2026: adk_agents/robot_sorter + agent/) as a submission
# image. Same packages as the agent's environment in his sim/modal_sim.py (/opt/adk), Python 3.12, CPU only: the model
# runs in Google's cloud, so the robot PC needs internet. Starts the policy server on :8000 by itself.
# Built by policy/adk/build.sh from an assembled context (never by hand: the context holds the Gemini key as
# adk_agents/robot_sorter/.env, which the agent reads at start).
FROM nvidia/cuda:12.8.0-base-ubuntu24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
        libglib2.0-0t64 libgomp1 && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/adk && /opt/adk/bin/pip install --no-cache-dir google-adk==2.14.1 numpy==2.2.6 scipy==1.15.2 \
        opencv-python-headless==4.10.0.84 pyyaml msgpack "websockets>=12" pin==3.3.1 python-dotenv
WORKDIR /app
# Aalto's package (policy server, safety filter, scene, calibration, classical planner, oracle) and the G1 URDF at the
# path aaltonomous.interface.safety.DEFAULT_URDF expects.
COPY aaltonomous/ /app/aaltonomous/
COPY g1_body29_hand14.urdf /app/third_party/xr_teleoperate/assets/g1/g1_body29_hand14.urdf
COPY agent/ /app/agent_pkg/agent/
COPY adk_agents/ /app/adk_agents/
COPY smooth_motion.py cfg_overrides.py runtime.py lean.py gravity_ff.py /app/
ENV PYTHONPATH=/app:/app/agent_pkg:/app/adk_agents PORT=8000
EXPOSE 8000
CMD ["/opt/adk/bin/python", "-m", "robot_sorter.serve"]
