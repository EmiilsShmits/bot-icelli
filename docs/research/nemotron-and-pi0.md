# Nemotron and π0 / π0.5: context for the Aalto challenge

Facts from the challenge pages, Aalto's docs and the hackerpacks. Lines marked *(general knowledge, verify)* come from outside those sources. Uses listed under "options" are possibilities, not team decisions.

## π0 / π0.5 (Physical Intelligence)

**What they are:** open-source vision-language-action (VLA) models (repo: openpi). They take camera images, robot state and a text instruction, and output **chunks** of robot actions. π0.5 is the newer version, aimed at better generalisation.

**What Aalto says** (`STARTER_PATHS.md`, "Route 3: imitation learning / VLA"):
- Listed as a recommended route next to NVIDIA GR00T.
- **Aalto's submission protocol is modelled on openpi's** websocket + msgpack server.
- **Fine-tuning needs 80 GB GPUs**; inference fits the 32 GB finals GPU (RTX 5090).
- Return action chunks `(k, 14)` to keep ≥ 27 commands/s with a slow model.
- Main risk: the gap between how the sim and the real cameras look. Use domain randomisation and the Drop 1 venue images.

**Data:**
- Aalto's real demos: ~20 per rung, raw, LeRobot v3.0 + a GR00T-format copy.
- Plus anything generated in sim.
- LeRobot includes π0 / π0.5 policies *(general knowledge, verify)*.

**Sizes** *(general knowledge, verify against the openpi README)*:
- ~3B parameters, built on PaliGemma.
- openpi lists roughly: > 8 GB inference, > 22.5 GB LoRA fine-tuning, > 70 GB full fine-tuning.
- Default action size is 32 dimensions, so our 28 joints would be zero-padded.

**Where else it appears:**
- **Qualia's hackerpack:** curate demos, then export to train "π0.5 with LeRobot". The platform closes 7 days after the event.
- **Verda Compute Track:** names VLA training as an example use of their compute.

**Constraints for a submission:**
- Outputs must stay within 1 rad/s (arms) / 3 rad/s (hands), with 0 clipped steps at the sim gate. Smoothing or clamping in the policy server may be needed.
- Our own latency must allow ≥ 27 commands/s (`policy_hz_rt`). The sim running slower than real time doesn't help.
- Weights go inside the image, ≤ 40 GB.

## Nemotron (NVIDIA)

**What it is:** NVIDIA's open model family. The tech challenge centres on **Nemotron 3.5 Super VL**:
- 120B parameters, mixture-of-experts with ~12B active per token
- reads text, images, documents and video
- can call tools

**"Best Use of Nemotron" tech challenge** ([`../challenges/tech/nvidia--best-use-of-nemotron.md`](../challenges/tech/nvidia--best-use-of-nemotron.md)):
- Can be stacked on a main challenge.
- Must use **Nemotron 3.5 Super VL** in the working solution, contributing to core functionality, visible in the demo.
- Must include a short text in the submission form: which model, what it does, why it matters, how we improved its outputs.
- **Judging:** meaningful usage, technical execution, quality of AI output, creativity. 25% each.
- **Prize:** RTX 5080 for 2 teams.
- **Mentors:** Maxime Pariente and Ryan Reese, at the NVIDIA table and on the NVIDIA Discord.

**Access:**
- **NVIDIA Build:**
  - free, OpenAI-compatible, `https://integrate.api.nvidia.com/v1`
  - the page reports ~40 requests/min per key, so each teammate should use their own key
- **OpenRouter:** free variants capped at 20 requests/min and 50/day.
- **Hugging Face:** open weights. The page mentions NVIDIA's Brev for hosting; no Brev credits are offered.
- **Smaller models:**
  - the page names `nemotron-3.5-lightning-30b-a3b`
  - Jetson AI Lab lists a Nemotron3 Nano 4B for 8 GB Jetsons (see [`jetson.md`](jetson.md))
  - **the tech challenge requires Super VL specifically**

**Constraints in the Aalto challenge:**
- **Too big for the finals GPU:** 120B parameters won't fit a 32 GB RTX 5090 without extreme quantisation.
- **Network:** Aalto's docs say they provide no network ("whatever connection the venue gives it, or none"), with no reruns for failed calls. The challenge page doesn't mention network. **Confirm with Aalto on Discord** if we hear otherwise.
- **Too slow for control:** Aalto estimates frontier VLMs at 10–20 s per call. It can only plan per episode or per object, in a background thread, never tick by tick.

**Options for where it could fit** (not decided):
1. **Development-time helper** (no network needed at the finals):
   - write instruction paraphrases for rung-2 training data (the finals use unseen phrasings)
   - review demo videos to flag failed or messy takes (Aalto's drops are raw)
2. **Planner inside the submission** (only if the finals machine is online): read the instruction plus the head image once per episode, and output the colour → box mapping. A few calls per 2-minute episode fits the rate limit. Keep an offline fallback parser.
3. **A smaller local Nemotron inside the image.** Fits the GPU, but doesn't satisfy the Super VL requirement.

## Other NVIDIA things we have access to
- **Isaac Sim + Isaac Lab:** the simulator, inside Aalto's Docker image.
- **Isaac GR00T:** NVIDIA's robot model. Aalto ships its demos in a GR00T-ready format.
- **Our Jetson:** JetPack, jetson-containers and Jetson AI Lab models. It can't run Isaac Sim (see [`jetson.md`](jetson.md)).
- **NVIDIA GPUs** via the Verda (€200 per team) and Modal ($100 per person) credits. There is no NVIDIA credit hackerpack.

## How π0 and Nemotron relate
- **π0 / π0.5 (or GR00T)** would be the controller: it outputs joint actions and is what Aalto scores.
- **Nemotron Super VL** can't control the robot. It could plan, label or generate data, and it's a separate prize track.
- Aalto's rules allow any mix: any public model, hybrids encouraged, external APIs at our own risk.
