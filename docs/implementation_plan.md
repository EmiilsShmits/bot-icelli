# Unitree G1 Agent Studio & Exportable Python Skill Architecture

An interactive robotics workbench and ready-to-deploy Python 3.12 agent package grounded directly in your `bot-icelli` repository and the pinned `zupermiez/aaltonomous-humanoid` starter codebase, unifying your existing Gemini Decisions instruction parser, classical IK planner wrappers, dual-loop 30 Hz runtime, demonstration recorder, and offline safety test suite.

---

### User Review & Critical Decisions

> [!IMPORTANT]
> **Ground-Truth Reconciliation From `EmiilsShmits/bot-icelli` & `zupermiez/aaltonomous-humanoid`**: Inspecting both live repositories revealed seven concrete code-vs-prompt discrepancies and high-leverage starter mechanics that our workbench and exported Python package incorporate directly:
> 1. **Bin Key Spelling (`"center"`, not `"centre"`)**: `scene.yaml`, `interface/tasks.py`, and `training/instruction_parser/spec.py` all key the middle bin as `"center"`. Passing `"centre"` into `Planner` or `Scene` raises a `KeyError`—all skill wrappers normalize `"centre"` → `"center"`.
> 2. **Existing Gemini Decisions Parser (`gemini_decision.py` + `rule_parser.py` + `hybrid.py`)**: Your team already benchmarked `GeminiDecision` (`POST .../v1beta/decisions`, `gemini-decision-1`) across the 10-slot schema (`9 colour×shape pairs + other` + `is_invalid` `noul`), plus `rule_parser` and `hybrid` (`agree` / `other_leave`). We promote that exact parser into Level 2 `reset()` rather than reinventing it.
> 3. **Real vs. Sim Object Colours & Bin Interference**: Sim uses `red / yellow / blue`, whereas the real robot uses `orange / yellow / purple`—and the bins are also orange (`H ~ 11–13`), causing stock HSV (`config.yaml`) to miss real orange and pale-green yellow (`H ~ 34–46`). Our perception wrapper and workbench support `sim` and `real_venue` HSV profiles.
> 4. **Policy Interface Signature Mismatch**: `deploy.policy_server.Policy.reset(instruction, task, seed)` differs from `baselines.classical.policy.ClassicalPolicy.reset(info)`. Our exported `AgentPolicy` subclasses `deploy.policy_server.Policy` cleanly and registers in `policy/server.py` alongside `HoldChunkPolicy`.
> 5. **Oracle Tuning & Existing `plan_relocation`**: `Planner.plan_relocation` already exists in `baselines/classical/planner.py`, and `sim/oracle.py` already adds critical fixes absent from stock `config.yaml`: `ARM_HOME` (stock `home_arm_q` collides hand-vs-body in sim), `grasp.point_in_palm: [0.099, -0.084, 0.015]` (thumb vs 1 finger so 45 mm objects don't wedge), `BIN_MARGIN = 0.0`, `SHORTCUT_TOL = 0.01` (~3× faster paths), `DROP_OFFSETS` (avoids stacking over the 6 cm rim), and `_tri_shift` (`TRI_PHI_DEG = 105` centroid-to-midpoint shift for triangular prisms).
> 6. **Strict Safety & Rate Margins (`submission/server.py`)**: `AALTO_WARMUP_TICKS = 15` (stale frame guard), `AALTO_ACT_TICKS = 8` (keeps `ACT_TICKS × 30 × RTF >= 27 Hz` at 0.30 RTF), and stricter local velocity caps (`0.98 rad/s` arm, `2.7 rad/s` hand vs. runner's `1.0 / 3.0`) guarantee **zero clipped ticks**.
> 7. **Workspace Reach & Camera Clipping (`ORGANIZER_ISSUES.md`)**: Counter surface is `z = +0.01 m` (keep-out `z <= 0.03 m`), bin centers sit at pelvis `(0.505, +0.26 / 0.0 / -0.26)` with `drop_inset = 0.05 m` (`x ≈ 0.45 m`), near-edge objects (`pelvis x ≈ 0.26 m`) approach image row `v = 440–480`, and left/right bins are single-arm only.

- **Confirmed Deliverable Format**: An interactive **Unitree G1 Agent Workbench** (live counter/reachability simulator, server-side Gemini Decisions & Gemini 4 Hydrogen execution, real-time safety validator, decision trace log) paired with a one-click **exportable Python `agent/` package** (`skills`, `runtime`, `demo`, `tests`) engineered to drop straight into `bot-icelli` alongside `third_party/aaltonomous-humanoid`.
- **Confirmed Challenge Scope**: Full end-to-end execution for **Level 1 (`sort_fixed`)** and **Level 2 (`sort_language`, including colour+shape rules, real orange/purple/yellow aliases, and invalid/distractor refusal)**, plus documented **Level 3 (`insert_shapes`)** hole-alignment stubs.

---

### 1. Overview & Core Concept

- **What It Does**:
  1. **Interactive Robotics Workbench**: Simulates the exact G1 counter geometry from `scene.yaml` (`mat_origin_in_pelvis: [0.14, -0.45, 0.01]`, `mat_size: [0.90, 0.50]`, `bins` at `x = 0.40..0.61 m`, `objects = 4.5 cm` cubes/cylinders/triangular prisms). Lets your team drag objects, switch `sim` vs `real_venue` colour palettes, test arbitrary Level 2 instructions against real server-side **Gemini Decisions API (`gemini-decision-1`)** and **Gemini 4 Hydrogen**, inject network timeouts/3s stalls to verify the non-blocking fallback chain, and inspect trajectory safety dry-runs.
  2. **Exportable Python `agent/` Codebase**: Generates complete, self-contained Python 3.12 modules wrapping your read-only `aaltonomous` submodule (`Planner`, `ArmKinematics`, `Perception`, `SafetyFilter`, `Scene`, `Policy`) plus your `rule_parser` / `GeminiDecision` modules—including new motion skills (`push_clear`, `re_grasp`, `hand_over`, `pi05_skill` adapter), `gen_demos.py`-compatible segment labeling (`aalto-simdemo-v1`), and offline `RenderMockBackend` unit tests.
- **Target Audience**: Your four-person Junction 2026 team (sim, perception, VLA/π0.5, and deployment engineers) needing a unified skill & agent layer before tomorrow's submission cutoff.
- **Key Value**: Bridges your working classical oracle (97% cube / 91% cylinder / 35% prism), your instruction parser experiments, and your π0.5 policy server into one safety-verified skill-calling agent with live Gemini verification and instant offline fallback.

---

### 2. User Experience & Visual Design

- **Key User Flows**:
  1. **Scene & Task Configuration**: Select Level 1 (`sort_fixed`), Level 2 (`sort_language`), or Level 3 (`insert_shapes` stub), toggle `Sim Palette (Red/Yellow/Blue)` vs. `Venue Palette (Orange/Yellow/Purple)`, place or randomize 3–5 objects on the counter mat, and edit the episode instruction.
  2. **Instruction Parsing & Slot Matrix Inspection**: Trigger `Parse Instruction` to run your 10-slot (`9 colour×shape + other`) + `is_invalid` evaluator via server-side **Gemini Decisions API (`gemini-decision-1`)** or **Gemini 4 Hydrogen** structured JSON, side-by-side with the local `rule_parser` output and hybrid agreement check.
  3. **Live Agent Cycle & Fault Injection**: Click `Step Cycle` or `Run Episode` to watch the background decision loop evaluate `detect_objects` → `check_reachability` → `gemini-decision-1` candidate selection → `SafetyFilter` dry-run → 30 Hz chunked playback (`8 ticks/call`, `15-tick warmup`). Toggle `Offline / Drop Network` or `3s API Stall` to prove `act()` remains `< 1 ms` and the nearest-object rule fallback keeps sorting without pausing.
  4. **Skill Matrix, Discrepancy Audit & Python Bundle Export**: Inspect the exact mapping table from every skill to existing `aaltonomous` functions, review documented repo caveats, copy individual Python modules, or export the complete `agent/` bundle as a downloadable ZIP.
- **Visual Identity & Theme** *(Science & Robotics Precision Instrumentation)*:
  - **Aesthetic Direction**: Calibrated robotics telemetry console—dark obsidian lab canvas, hairline structural grids, zero decorative clutter.
  - **Color Palette (60-30-10 Budget)**:
    - *60% Primary Canvas*: Deep lab slate (`#090D16`).
    - *30% Structural Panels & Grids*: Flat slate surfaces (`#111827` / `#161F30`) with crisp 1px borders (`border-slate-800`).
    - *10% Calibrated Accents*: Telemetry cyan (`#06B6D4`) for active arm trajectories and primary actions; semantic emerald (`#10B981`), amber (`#F59E0B`), and rose (`#F43F5E`) paired with explicit text labels for safety verification (`0 Clips`), fallback tier, and unreachable/keep-out warnings.
  - **Typography & Tabular Discipline**: `Plus Jakarta Sans` for headings and navigation, `IBM Plex Sans` for explanatory prose, and `JetBrains Mono` with `tabular-nums` for all pelvis/mat coordinates, joint velocities, decision probabilities, and latency measurements.
  - **Layout Architecture**:
    - *Top Header (3-zone contract)*: Single-line wordmark (`G1 Agent Workbench`) — 4 single-line views (`Workbench`, `Skill Mapping`, `Decision Trace`, `Python Export`) — 1 primary CTA (`Export agent.zip`).
    - *Asymmetric Split Console*: Fixed left control & fault-injection rail (340px) — Center interactive counter top-down + Z-clearance elevation viewport with live Gemini decision probabilities — Bottom tabular decision & safety log tray.
- **Interactive Feedback & Motion**:
  - Snappy transitions (`<= 200ms`) when dragging counter objects, toggling arm reachability envelopes (`r <= 0.52 m` left/right/center overlap), or inspecting trajectory phases (`to_pregrasp`, `descend`, `close`, `lift`, `carry`, `open`, `retreat`, `home`).
  - Explicit non-hue-only state indicators (`● Safety: 0 Clips`, `▲ Fallback: Rule-Based`, `✖ Stale Warmup 15/15`) and clean loading states during server-side Gemini API calls.

---

### 3. Key Product Decisions & Trade-Offs

- **Decision 1: Multimodal `gemini-decision-1` First, Generative Models Only for Continuous Coordinates**
  - *Chosen Approach*:
    1. **At `reset()` (Level 2)**: Call `POST https://generativelanguage.googleapis.com/v1beta/decisions` (`gemini-decision-1`) using your team's proven 10-slot `choice` + `is_invalid` `noul` schema (with `gemini-4-hydrogen` structured JSON available as an optional comparator), combined with `rule_parser` via your `hybrid` safety check (`agree` / `other_leave`), caching the resolved mapping for the episode.
    2. **Per Pick-and-Place Cycle (Background Thread, Multimodal)**: `gemini-decision-1` **natively accepts images directly** in `input` via `inline_data` (`head_rgb` + optional `wrist_rgb` JPEG alongside the structured object/reachability table). In a single ~150–250 ms forward pass (1.2s hard timeout), it simultaneously answers: (a) which pre-validated feasible skill candidate (`pick_and_place`, `push_clear`, `hand_over`, `re_grasp`, `pi05_skill`, `done`) to execute next (`choice`), (b) visual shape classification (`cube` / `cylinder` / `triangle` / `distractor`) for each detected blob, and (c) grasp/clutter checks (`noul`: `needs_push_first`, `is_grasp_clear`). No `gemini-4-hydrogen` call is needed to review images for closed-set decisions.
    3. **Only When Continuous Coordinates Are Needed**: Invoke `gemini-robotics-er-2-preview` asynchronously only when HSV+depth fails to localize an object (returning `(u, v)` pixel points) or for Level 3 lid-hole `(u, v)` and yaw alignment stubs.
  - *Why*: Passing `head_rgb` directly into `gemini-decision-1` avoids chaining two network calls (`hydrogen` → `decisions`), keeps cycle latency ~200 ms with zero output tokens, eliminates JSON parse failures, and solves `Perception`'s shape blindness (`cube` vs `cylinder` vs `triangle`) in the same forward pass.
  - *Alternatives Considered*: Calling `gemini-4-hydrogen` on every frame to caption the scene before `gemini-decision-1`—adds 0.8–2s of redundant latency per cycle and risks schema drift.

- **Decision 2: High-ROI New Skills Targeting the 35% Prism & Clutter Bottleneck**
  - *Chosen Approach*: Wrap `Planner`, `ArmKinematics`, `Perception`, and `SafetyFilter` read-only while adding three targeted new planning skills:
    1. **`push_clear(object_id, arm, push_dir)`**: Sweeps an object away from a bin wall or neighboring block (`min_spacing < 0.08 m`) using `ArmKinematics` Cartesian waypoints at `z = counter_z + 0.025 m` before re-detecting and grasping.
    2. **`re_grasp(object_id, arm, hint_index)`**: Detects missed grasps (via `hand_q` closing to `closed` limit without object departure on next look, or low fingertip load/lead) and retries with rotated `finger_hints` (`[1,0,0]`, `[1,-1,0]`, `[0,-1,0]`) + adjusted height.
    3. **`hand_over(object_id, from_arm, to_arm)`**: Clean skill wrapper over `oracle.py`'s relay pattern (`RELAY_POINTS` in the shared center workspace band where both arms reach).
    4. **`insert(object_id, hole)` (Level 3 Stub)**: Complete typed contract, yaw/hole-shape alignment stub, and `SafetyFilter` gate ready for post-finals extension.
  - *Why*: Directly addresses the oracle's #1 failure mode (triangular prisms slipping or moving slightly out of alignment) without breaking existing `Planner` guarantees.

- **Decision 3: Zero-Clip Safety Gate & Qualification-Safe 30 Hz Executor**
  - *Chosen Approach*: Mirror `submission/server.py`'s exact timing & filtering discipline: ignore ticks `0..14` (`warmup_ticks = 15`), return `8`-tick chunks per `act()` call (ensuring `>= 27 Hz` under low RTF), enforce local `SafetyFilter` dry-run at `0.98 rad/s` arm and `2.7 rad/s` hand (inside the runner's `1.0 / 3.0`), and maintain a lock-protected ring buffer so `act()` completes in `< 1 ms` even when a mocked Gemini call blocks for 3 seconds.
  - *Why*: Meets the zero-clipped-ticks and `>= 27 Hz` qualification gate unconditionally.

- **Decision 4: Demonstration Mode Compatible With `aalto-simdemo-v1`**
  - *Chosen Approach*: Drive the same skill library with a randomized chooser (varying arm choice when center-reachable, `finger_hints`, `approach_height`, `time_scale` speed, `drop_inset` offsets, and intentional `push_clear` / `re_grasp` recoveries) inside `gen_demos.py`'s exact `DemoRecorder` format (`lowdim.npz` + `.mjpg` + `meta.json`), enriching each segment label with `{skill_name, args, language_prompt}` for π0.5 sub-task training.

---

### 4. Technical Architecture & Data Strategy

- **Architecture & Component Diagram**:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                  INTERACTIVE WORKBENCH (React + Express Server)                  │
│                                                                                  │
│  ┌──────────────────────────┐   /api/agent/*    ┌─────────────────────────────┐  │
│  │ Workbench Console        │ ────────────────► │ Express Gemini Proxy        │  │
│  │ - Scene & Drag Sim       │                   │ - @google/genai (server)    │  │
│  │ - Sim vs Venue Palette   │ ◄──────────────── │ - v1beta/decisions          │  │
│  │ - Fault/Latency Injector │   Decisions +     │   (gemini-decision-1)       │  │
│  │ - Python Bundle Exporter │   Safety Traces   │ - gemini-4-hydrogen         │  │
│  └──────────────────────────┘                   │ - gemini-robotics-er-2      │  │
│                                                 └─────────────────────────────┘  │
└───────────────────────────────────────┬──────────────────────────────────────────┘
                                        │ Exports ready-to-run Python 3.12 agent/
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│              EXPORTED PYTHON AGENT PACKAGE (bot-icelli / policy/)                │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │ AgentPolicy(Policy) · act(obs) [< 1 ms, never blocks]                      │  │
│  │   - Guards ticks 0..14 (warmup) -> hands out 8-tick chunks from queue      │  │
│  │   - Holds last safe arm_q / hand_q target when planner/Gemini is busy      │  │
│  └────────────────────────────────────▲───────────────────────────────────────┘  │
│                                       │ Validated TrajectoryHandle (0 clips)     │
│  ┌────────────────────────────────────┴───────────────────────────────────────┐  │
│  │ Background Agent Loop (1 decision per pick-and-place cycle)                │  │
│  │   1. Reset Map: gemini-decision-1 (10-slot) + rule_parser hybrid cache     │  │
│  │   2. Observe: get_joint_state() + detect_objects("camera")                 │  │
│  │   3. Pre-Filter: check_reachability() builds feasible skill candidates     │  │
│  │   4. Select: [gemini-decision-1 (1.2s timeout)]                            │  │
│  │                └─► timeout/low-conf ─► [Nearest-Object Rule Fallback]      │  │
│  │                                          └─► none feasible ─► [Hold]       │  │
│  │   5. Verify: SafetyFilter.dry_run(0.98 arm / 2.7 hand) -> 0 clips required │  │
│  │   6. Audit Log: {inputs, decision, confidence, latency_ms, next_outcome}   │  │
│  └────────────────────────────────────┬───────────────────────────────────────┘  │
│                                       │ Read-only wrapper imports                │
│  ┌────────────────────────────────────▼───────────────────────────────────────┐  │
│  │ third_party/aaltonomous-humanoid (Planner · ArmKinematics · SafetyFilter)  │  │
│  │ + bot-icelli rule_parser / spec / DemoRecorder (aalto-simdemo-v1)          │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

- **Data Model & State**:
  - **Workspace & Scene Model**: Mirrors `scene.yaml` exact coordinates (`counter_size [1.10, 0.60]`, `mat_size [0.90, 0.50]`, `mat_origin_in_pelvis [0.14, -0.45, 0.01]`, bins `left/center/right` at pelvis `(0.505, +0.26/0/-0.26)` with `0.21×0.21 m` footprint and `0.06 m` walls, keep-out `z <= 0.03 m`).
  - **10-Slot Instruction Mapping**: Matches `spec.py` (`{red|yellow|blue} {cube|cylinder|triangle}` + `other` → `left | center | right | leave`, or `"invalid"` refusal).
  - **Trajectory Handle**: `handle_id`, `skill_name`, `args`, `arm (T, 14)`, `hand (T, 14)`, `phases`, `safety_clips (must be 0)`, `max_arm_vel`, `max_hand_vel`, `min_counter_clearance`, and `segment_prompt`.
  - **Decision Log Entry**: `cycle`, `t_s`, `model_or_fallback`, `candidates`, `chosen_candidate`, `probabilities`, `confidence`, `latency_ms`, `outcome`.

- **Interactive Component & State Mapping**:
  - **Counter & Kinematics Canvas**: Interactive top-down + Z-height view showing mat grid (`5 cm` pitch), arm reach arcs (`~0.52 m`), bin drop targets (`drop_inset = 0.05 m`), relay zone, draggable objects, and animated trajectory playback; recalculates reachability and clearance instantaneously on drag.
  - **Level 2 Instruction & Hybrid Parser Panel**: Tests live instructions against server-side `gemini-decision-1` (`v1beta/decisions`) and `gemini-4-hydrogen`, alongside an exact TypeScript mirror of `rule_parser.py` and `hybrid.py` (`agree` / `rule_first` / `other_leave`) so teams can verify edge cases (e.g. `orange` / `purple`, `"the rest"`, distractors, `"centre"` vs `"center"`).
  - **Skill & Fault-Injection Runner**: Triggers single-step or multi-object episodes with live toggles for `Offline Mode`, `3s Network Stall`, and `Prism Slip Simulation` (triggering `re_grasp` or `push_clear`), verifying `< 5 ms` `act()` response times and `0` safety clips.
  - **Python Package & Documentation Inspector**: Renders the full generated Python 3.12 code (`skills`, `runtime`, `demo`, `tests`), the Tool-to-Existing-Code Mapping Table, exact Gemini API payloads & caveats, and the list of repo discrepancies/open questions, with copy and full ZIP download actions.

- **Key Sequences & Integrations**:
  - **Server-Side Gemini Decisions Route (`/api/gemini/decide`)**: Invokes `POST https://generativelanguage.googleapis.com/v1beta/decisions` (`model: "gemini-decision-1"`) with `GEMINI_API_KEY` on the Express server—supporting both the 10-slot instruction parser and closed-set cycle skill selection (`choice` + `noul`).
  - **Server-Side Gemini Hydrogen / Robotics ER 2 Route (`/api/gemini/vision-or-parse`)**: Uses `@google/genai` (`ai.models.generateContent`) for `gemini-4-hydrogen` structured JSON comparison and `gemini-robotics-er-2-preview` spatial/shape inspection on synthetic or uploaded camera frames.
