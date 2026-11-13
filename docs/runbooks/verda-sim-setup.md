# Runbook: Verda machine + Aalto Isaac sim

Condensed from Aalto's `third_party/aaltonomous-humanoid/aaltonomous/cloud/QUICKSTART.md`. If they disagree, Aalto's file wins.

## 1. Get credits and a machine
1. Sign up at console.verda.com and claim the €200 team credits (form on the Verda hackerpack card; see `docs/research/apis-and-credits.md`). Share them with the team as described in the Verda docs.
2. Create an instance:
   - **RTX-class GPU, ≥ 24 GB:** RTX Pro 6000 / L40S / A6000 / RTX 4090/5090. **Not A100/H100**: no RT cores, so the cameras won't render.
   - **On-demand, not spot.** Spot instances can vanish in seconds.
   - ≥ 8 CPU cores, ≥ 32 GB RAM, ≥ 80 GB disk. Driver ≥ 580.65.06; Ubuntu 22.04/24.04 x86_64.
   - **Attach a persistent volume at `/data`.** Checkpoints, datasets and logs go there.
3. Work over SSH inside `tmux`, so the sim keeps running if SSH drops.

## 2. Start the sim
```bash
# image link: kickoff / Aalto Discord channel
docker load -i aalto-sim-v1.tar.zst
docker run -d --name aalto --gpus all --network host --ipc host \
  -v aalto-kitcache:/root/miniforge3/envs/isaac/lib/python3.12/site-packages/isaacsim/kit/cache \
  -v /data:/data aalto-sim:v1 sleep infinity
docker exec -it aalto bash
aalto sim        # first start compiles shaders: 5-10 min
aalto check      # expect 8 PASS / 0 FAIL
aalto snap       # one image per camera -> /tmp/aalto_snap
aalto baseline   # reference policy, prints a score table
```
- No NVIDIA container toolkit? Run `sudo apt-get install -y nvidia-container-toolkit && sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`.
- Domain randomisation: `AALTO_DR=train aalto sim`.

## 3. Our repo on the machine
```bash
cd /data && git clone --recurse-submodules https://github.com/EmiilsShmits/bot-icelli.git && cd bot-icelli
make setup && make serve              # our policy on :8000 (host)
make eval TASK=sort_fixed TRIALS=10   # runs `aalto eval` inside the container against it
```

## 4. Viewing cameras (no GUI)
- `aalto snap`, then `scp` the JPEGs to your laptop.
- Or tunnel: `ssh -L 55555:localhost:55555 <host>`. Head camera is on 55555, wrists on 55556/7, head RGB-D on 55560.

## Troubleshooting
| Symptom | Fix |
|---|---|
| Black images | Shader cache is cold. Wait 2–5 min or restart the sim |
| Gate fails on rate (< 27 Hz) | The machine is CPU-starved. One sim per machine; don't train on the same machine |
| "port in use" | Another sim is running: `aalto status`, `aalto stop` |
| Need to stop | `aalto stop` (never `pkill -f sim_main`) |
