# Runbook: Marcus's Modal sim from a Windows laptop

**Owner:** Samer. Written Sat 14 Nov ~20:50 (Samer + Claude), when it was set up on Samer's laptop. Marcus's own
instructions: `TEAM_HANDOVER.md` §4 and the docstring of `sim/modal_sim.py` in his repo
([github.com/marcusoberg/junction2026](https://github.com/marcusoberg/junction2026)).

What it gives us: Aalto's Isaac sim on Modal, one L40S per sim, **every seed in its own sim at the same time**
(`--action sweep`): 10 seeds take about as long as one (one sim start plus the longest episode, ~10–15 min), up to
the Modal workspace's GPU limit, against ~1 h for 10 seeds on `samer-v1-sim`.
Marcus's estimate of the price: 8 sims for 1 h ≈ $18, so roughly $2–2.5 per sim-hour.

## One-time setup (done on Samer's laptop, `D:\Samer\Hackathons\JUNCTION 2026\junction2026`)
PowerShell, in the folder that will hold Marcus's repo:
```powershell
git clone https://github.com/marcusoberg/junction2026        # 3 GB: sim_out/ (results, videos) is committed
cd junction2026
# Aalto's starter repo, next to sim/, WITH LINUX LINE ENDINGS (see Gotchas)
git -c core.autocrlf=false clone --depth 1 https://github.com/zupermiez/aaltonomous-humanoid.git aaltonomous-humanoid
py -3.13 -m venv .venv                                       # .venv/ and aaltonomous-humanoid/ are git-ignored there
.\.venv\Scripts\python.exe -m pip install modal              # client 1.6.4 on Sat 14 Nov
.\.venv\Scripts\modal.exe setup                              # browser sign-in to the Modal account with the credits
```
For Marcus's agent (`eval-adk`, `sweep`): a Gemini API key in `adk_agents\robot_sorter\.env`:
```powershell
Copy-Item adk_agents\robot_sorter\.env.example adk_agents\robot_sorter\.env
notepad adk_agents\robot_sorter\.env                         # paste the key after GOOGLE_API_KEY=; never commit .env
```
The key stays on the laptop: `modal_sim.py` reads it when a run starts and hands it to the sim container as a
temporary secret.

## Runs (from the `junction2026` folder)
```powershell
.\.venv\Scripts\modal.exe run sim/modal_sim.py --action boot                  # 1st time builds the sim image (long), then 9 checks
.\.venv\Scripts\modal.exe run sim/modal_sim.py --action baseline --trials 3   # Aalto's oracle
# Marcus's agent, every seed in its own sim; the table prints at the end (keep the laptop awake until then)
.\.venv\Scripts\modal.exe run --detach sim/modal_sim.py --action sweep --tag rand10 --sweep "nominal-dr:sort_fixed:1000-1009"
# outputs: aalto-sim-out volume, <tag>/<scene>-<task>-<seed>/ (eval.json, videos, traces)
mkdir sim_out; .\.venv\Scripts\modal.exe volume get aalto-sim-out rand10 sim_out
```
Scenes for `--sweep "<scene>:<task>:<seeds>, ..."` (Marcus's names, `SCENES` in `sim/modal_sim.py`):
| Scene | What it is | Compare with |
|---|---|---|
| `nominal` | Aalto's scene as shipped | our nominal runs (sim A) |
| `nominal-dr` | + Aalto's training randomisation (`AALTO_DR=train`) | our randomised runs (sims B, C): e-027, e-035 |
| `venue` | the blocks recoloured as the real head camera saw them, + randomisation. **Not our venue look**: camera, bins and layout stay Aalto's | nothing of ours yet |
| `venue-wide`, `venue-shape` | `venue` + objects anywhere / shape-naming instructions | — |
| `pastel`, `real-wide` | washed-out or real colours with wider randomisation | — |

Same seeds as our runs (1000–1009, sort_fixed) give a direct comparison: Aalto's evaluator places the same layouts.

## Our own policies on Modal
Our repo's `modal_pipeline/` (a copy of Marcus's pipeline from Sat 17:44, plus Emīls's `eval-policy` action, venue
look by default) runs `policy/server.py --policy <name>` next to the sim, e.g.
`modal run --detach sim/modal_sim.py --action eval-policy --policy v1.5 --eval-task sort_fixed --trials 2 --seed 1000 --background`
(`--look none` for Aalto's scene, `--dr train` for randomisation). It has no `sweep`. From Windows it needs the same
line-ending fix in our submodule first (see Gotchas).

## Gotchas
- **Line endings.** Windows Git converts LF to CRLF on checkout (`core.autocrlf=true` in Git for Windows' system
  config). `modal_sim.py` copies Aalto's shell scripts (`setup_instance.sh`, `aalto.sh`, `run_sim.sh`, …) from the
  local clone into the Linux image, and bash fails on CRLF. Hence `-c core.autocrlf=false` above. Our own checkout's
  submodule `third_party/aaltonomous-humanoid` has CRLF on this laptop; to fix it:
  `git -C third_party/aaltonomous-humanoid config core.autocrlf false`, then
  `git -C third_party/aaltonomous-humanoid rm -r -q --cached .` and `git -C third_party/aaltonomous-humanoid reset -q --hard`.
- `modal.exe` warns "The `modal` command was not found on your path": harmless when it's called by its full path.
- Long jobs: `modal run --detach ... --background` where the action supports it (`datagen`, `eval-model`, `eval-adk`);
  without `--background` the job stops when the laptop sleeps (Marcus lost runs that way). `sweep` collects its table
  on the laptop; its per-seed outputs reach the volume either way.
- The first `boot` builds a large image (Isaac Sim 6.2 + Isaac Lab + Aalto's stack); later runs reuse it.
