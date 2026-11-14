# Runbook: Verda machine + Aalto Isaac sim

Condensed from Aalto's `third_party/aaltonomous-humanoid/aaltonomous/cloud/QUICKSTART.md`. If they disagree, Aalto's file wins.

## 1. Get credits and a machine
1. **Each member claims their own €200 credits and gets their own API credentials** (personal, not shared). Steps from Verda staff in the #verda Discord channel, Fri 13 Nov:
   1. Submit the claim form linked on the Verda hackerpack card. **The credits arrive by email.**
   2. Log in at https://console.verda.com and claim them there.
   3. **Verda asks for your own payment card.** Verda staff say it's "for security reasons": you won't be charged and can remove the card immediately.
      - **Unanswered in the channel:** can usage go beyond the credit balance and hit the card? Until that's confirmed, stop machines when idle and keep an eye on the balance.
      - Several people reported trouble claiming. Ask Verda at booth #6 (floor 3) or in #verda.
      - **Sat 14 Nov ~02:15:** `verda.com`, `console.verda.com` and `api.verda.com` all served a Cloudflare "suspended domain" page. The same API still worked under Verda's old name, **`https://api.datacrunch.io/v1`** (same credentials, same endpoints).
   4. Your API credentials (Keys / API credentials in the console) are personal. Put them in your own local `.env`, never in the team chat.
   5. To let a teammate onto your machine, add their SSH public key to it. Each machine bills to the account that created it.
2. Create an instance:
   - **RTX-class GPU, ≥ 24 GB:** RTX Pro 6000 / L40S / A6000 / RTX 4090/5090. **Not A100/H100**: no RT cores, so the cameras won't render.
   - **On-demand, not spot.** Spot instances can vanish in seconds.
   - ≥ 8 CPU cores, ≥ 32 GB RAM, ≥ 80 GB disk. Driver ≥ 580.65.06; Ubuntu 22.04/24.04 x86_64.
   - **Attach a persistent volume at `/data`.** Checkpoints, datasets and logs go there.
   - **Image:** `24.04.cuda13.0.docker` (Ubuntu 24.04 + CUDA 13.0 + Docker) gave driver **580.178.04**, which passes. Avoid the `cuda12.9` images (driver too old), and the `.cc` (confidential computing) types and images.
   - **What we ran (Sat 14 Nov):** `1RTX6000ADA.10V` (RTX 6000 Ada 48 GB, 10 vCPU, 58 GB RAM) at **$1.59/h** in FIN-03, 200 GB OS disk. The single `1RTXPRO6000.30V` ($2.81/h) appeared and vanished within the hour, so availability changes fast.
3. Work over SSH inside `tmux`, so the sim keeps running if SSH drops.

### Creating the machine through the API (no console needed)
Put your own `VERDA_CLIENT_ID` / `VERDA_CLIENT_SECRET` in `.env` first.
```bash
API=https://api.datacrunch.io/v1          # api.verda.com was down on Sat 14 Nov
set -a; . ./.env; set +a
TOKEN=$(curl -s -X POST $API/oauth2/token -H 'Content-Type: application/json' \
  -d "{\"grant_type\":\"client_credentials\",\"client_id\":\"$VERDA_CLIENT_ID\",\"client_secret\":\"$VERDA_CLIENT_SECRET\"}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')   # expires after ~10 min
H="Authorization: Bearer $TOKEN"

curl -s -H "$H" $API/instance-availability          # which types are free, per location
curl -s -H "$H" $API/balance

ssh-keygen -t ed25519 -f ~/.ssh/verda_ed25519 -N ""   # once
curl -s -X POST -H "$H" -H 'Content-Type: application/json' $API/ssh-keys \
  -d "{\"name\":\"my-laptop\",\"key\":\"$(cat ~/.ssh/verda_ed25519.pub)\"}"   # prints the key id

curl -s -X POST -H "$H" -H 'Content-Type: application/json' $API/instances -d '{
  "instance_type": "1RTX6000ADA.10V", "image": "24.04.cuda13.0.docker",
  "hostname": "my-sim", "location_code": "FIN-03", "ssh_key_ids": ["<key id>"],
  "os_volume": {"name": "my-sim-os", "size": 200}, "is_spot": false, "contract": "PAY_AS_YOU_GO"}'
curl -s -H "$H" $API/instances                       # status + ip; "running" after ~30 s
ssh -i ~/.ssh/verda_ed25519 root@<ip>
```
The full API schema is at `$API/openapi.json`. **The machine bills until you delete it.**

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

## 2b. Bare metal (what we actually ran, since the Docker image link is only on Discord)
Takes ~30–40 min on the RTX 6000 Ada (downloads are fast: ~300 MB/s). Run as root on a fresh Verda machine:
```bash
apt-get update && apt-get install -y --no-install-recommends git curl unzip cmake build-essential \
  libturbojpeg libglu1-mesa libxt6 libvulkan1 libegl1 libgl1 libxrandr2 libxi6 libsm6 libice6 libxkbcommon0 libglib2.0-0t64
git clone https://github.com/zupermiez/aaltonomous-humanoid.git && cd aaltonomous-humanoid
git checkout "$(git -C <our repo> rev-parse HEAD:third_party/aaltonomous-humanoid)"   # same commit as our submodule (36daf5b on Sat 14 Nov)
```
**Fix Aalto's package pins first (bug on Aalto's side, still present on their `main` on Sat 14 Nov).** `aaltonomous/cloud/isaac-constraints.txt` pins newer versions of 5 packages than Isaac Sim 6.2 allows, so `setup_instance.sh` dies at the `isaacsim` step with `ResolutionImpossible`:

| Aalto pins | Isaac Sim 6.2 needs |
|---|---|
| `click==8.5.1` | `click==8.3.3` |
| `urllib3==2.8.0` | `urllib3==2.7.0` |
| `psutil==7.2.2` | `psutil==5.9.8` |
| `llvmlite==0.50.0` | `llvmlite==0.46.0` |
| `fsspec==2026.9.0` | `fsspec==2026.2.0` |

Comment those 5 lines out on the machine (not in our submodule), then install:
```bash
C=aaltonomous/cloud/isaac-constraints.txt
for p in click==8.5.1 urllib3==2.8.0 psutil==7.2.2 llvmlite==0.50.0 fsspec==2026.9.0; do
  sed -i "s/^${p//./\\.}\$/# $p  (conflicts with isaacsim 6.2)/" $C; done
tmux new -s setup
bash aaltonomous/cloud/setup_instance.sh 2>&1 | tee ~/setup.log   # re-running resumes; done steps are skipped
```
If a later step fails the same way, `pip install --dry-run "isaacsim[all,extscache]==6.2.0.0" --extra-index-url https://pypi.nvidia.com` (inside `conda activate isaac`, with `PIP_CONSTRAINT=$C`) names the next conflicting pin.

**Second conflict, at the `isaaclab` step:** Isaac Lab's optional `rerun` visualizer wants `rerun-sdk>=0.29.0`, while Aalto (and Unitree's `tools/rerun_visualizer.py`) pin `rerun-sdk==0.23.4`. Keep the pin. Install Isaac Lab with the same set as its default "all", minus the rerun visualizer, then let the script carry on:
```bash
source ~/miniforge3/etc/profile.d/conda.sh && conda activate isaac
export PIP_CONSTRAINT=$PWD/$C PIP_NO_CACHE_DIR=1 OMNI_KIT_ACCEPT_EULA=YES CYCLONEDDS_HOME=$PWD/third_party/cyclonedds/install
(cd third_party/IsaacLab && ./isaaclab.sh --install "mimic,teleop,newton,rl,visualizer[viser]")
touch third_party/.setup_done_isaaclab && unset PIP_CONSTRAINT
bash aaltonomous/cloud/setup_instance.sh                      # resumes with the aalto + verify steps
```
Isaac Lab's install upgrades `click`, `urllib3` and `llvmlite` back to the versions Aalto pinned (pip prints "dependency conflicts" with isaacsim's exact pins). That matches Aalto's tested environment, so leave it.

- **License:** the script sets `OMNI_KIT_ACCEPT_EULA=YES`, so running it accepts NVIDIA's Isaac Sim / Omniverse EULA. Whoever runs it is agreeing to that.
- Then the same commands as above, through the wrapper: `bash aaltonomous/cloud/aalto.sh sim`, then `check`, `snap`, `baseline` (`aalto.sh` with no arguments lists them).
- `make eval` in our Makefile uses `docker exec aalto ...`, so it only works with the Docker path. On bare metal use `bash aaltonomous/cloud/aalto.sh eval --policy ws://localhost:8000 ...`.

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
| `ResolutionImpossible` at the `isaacsim` step | Aalto's pins conflict with Isaac Sim; see §2b |
| `isaaclab` step fails on `rerun-sdk>=0.29.0` | Install Isaac Lab without the rerun visualizer; see §2b |
| `verify` fails only `test_cubes_and_bins_visible` | Aalto's own test fails at commit 36daf5b (also on a laptop): 4 far-edge corner points of the cube area fall outside the head camera's view. Not an install problem; go on to `aalto.sh sim` |
| Sim slower than Aalto's ~0.7× real time | We measured 0.31× on 10 vCPU (sim at ~5 cores, GPU 8 %). Probably CPU-bound; a machine with more cores may help (unverified) |
| `verda.com` shows a "suspended" page | Use `https://api.datacrunch.io/v1` for the API (§1) |
| Wanted machine type gone | `GET /instance-availability` again; single RTX PRO 6000s come and go within the hour |
