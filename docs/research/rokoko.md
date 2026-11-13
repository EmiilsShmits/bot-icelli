# Rokoko Smartgloves II, Coil Pro and SDK: research for G1 + Dex3 teleop

**Question:** Can we get finger joint angles and wrist pose out of Rokoko Smartgloves II into Python in real time, and retarget them onto a Unitree G1 with Dex3 three-finger hands in Isaac Sim?
**Short answer:** Yes for fingers and wrist **orientation**. Wrist **position** in space needs the Coil Pro. The Rokoko Device SDK already outputs 26 OpenXR hand joints, and Unitree publishes a ready-made Dex3 retargeting config that takes the same kind of joint list.
Researched 2026-11-13. "Unconfirmed" means we couldn't verify it from an official source.

---

## 1. Smartgloves II hardware

| Item | Value | Source |
|---|---|---|
| Sensors per glove | 7: 5 finger sensors (back of the middle segment of each finger, proximal segment for the thumb), a hub on the back of the hand, and an arm sensor on the forearm near the wrist | [SDK Smartgloves ref](https://sdk.rokoko.com/reference/products/smartgloves/), [product page](https://rokoko.com/products/smartgloves-ii) |
| Sensor type | IMU (accel + gyro) plus EMF. A small EMF transmitter in the hub is picked up by the finger and arm sensors. SGII adds a 3-axis magnetometer in the hub for heading | [Tech overview](https://sdk.rokoko.com/guides/tech-overview-emf-imu/) |
| Tracked DoF | 39 = 6 DoF per finger/arm sensor pose + 3 DoF hub orientation. **45 with Coil Pro** (+6 DoF arm-sensor pose in the Coil frame) | [Datasheet TR-01/02](https://sdk.rokoko.com/datasheets/Smartgloves_I_II_Comparison_v1.0.0_External.pdf) |
| Joints per finger | There's only one sensor per finger, so per-joint angles are *solved*. The SDK hand solver outputs a 26-joint skeleton (thumb: metacarpal, proximal, distal; other fingers add a medial joint) | [Hand solving](https://sdk.rokoko.com/guides/hand-solving/) |
| Rates | IMU 250 Hz, magnetometer 83.33 Hz, EMF receivers 96 kHz, **pose output 83.33 Hz** | [Datasheet IM-01/MG-01/TR-04](https://sdk.rokoko.com/datasheets/Smartgloves_I_II_Comparison_v1.0.0_External.pdf) |
| Latency (motion to driver output) | **USB 19 ms**, Wi-Fi 20 ms average with "a lot of jitter". The robotics page separately claims "~12 ms processing latency via USB" | [Datasheet TR-05/06](https://sdk.rokoko.com/datasheets/Smartgloves_I_II_Comparison_v1.0.0_External.pdf), [Robotics page](https://rokoko.com/use-cases/robotics) |
| Hub EMF accuracy | Finger sensor position accuracy 1.60 mm and arm sensor 3.00 mm (mean at 12 cm, *simulated*, before fusion) | Datasheet EF-04, EA-05 |
| Connectivity | Wi-Fi (streams over **TCP**) and **USB data streaming (SGII only; SGI is Wi-Fi only)** | [SDK Smartgloves ref](https://sdk.rokoko.com/reference/products/smartgloves/), [product page](https://rokoko.com/products/smartgloves-ii) |
| Wi-Fi | 2.4 and 5 GHz. Rokoko recommends a **dedicated router with no internet connection** | Rokoko store/support pages (summarised by search; the pages block automated fetch), [OptiTrack setup](https://docs.optitrack.com/markersets/glove-device-setup/rokoko-smartglove-setup) |
| Power | 285 mA draw. Each glove needs an **external USB power bank (5 V / 3 A)**. Rokoko's rule of thumb is about 1 h per 1000 mAh, but no official runtime is published for the gloves (unconfirmed) | Datasheet EL-01, [Power bank article](https://support.rokoko.com/hc/en-us/articles/4561524515345-Power-bank-specifications-for-your-Rokoko-gear) |
| Extras | Button and RGB ring LED, both controllable through the SDK (`SetColorLed`, `RingLed`) | [RCSP ref](https://sdk.rokoko.com/reference/rcsp/) |

### Do the gloves give hand position in space on their own? **No.**
- Without Coil Pro, the SDK streams finger-sensor poses **relative to the hub**, the arm sensor relative to the hub, and **hub orientation only** (`ORIENTATION hub` in `LTP_NED`, with *no position*). ([SDK Smartgloves ref](https://sdk.rokoko.com/reference/products/smartgloves/))
- Rokoko: gloves alone give "accurate finger tracking", and Coil Pro adds "global position tracking for near-perfect positioning of wrists". ([bundle page](https://store.rokoko.com/pages/finger-capture-coil-pro))
- In other words, gloves alone give fingers, wrist flexion and hand orientation (yaw referenced to magnetic north). They don't give XYZ position.
- A Smartsuit Pro II with Rokoko Studio gives hand position from body forward kinematics (IMU-based). That position drifts, and the suit only gets global position when combined with gloves and Coil Pro. ([Coil Pro page](https://rokoko.com/products/coil-pro)) We couldn't confirm whether the SDK solves a full-body skeleton; its hand solver only solves gloves.

### Coil Pro
- A passive EMF field source (about 20–21 kHz on 3 axes) with **no radio and no pairing**. The gloves' arm sensor detects it automatically and computes an absolute pose in the "Coil Pro frame". ([Tech overview](https://sdk.rokoko.com/guides/tech-overview-emf-imu/), [Wi-Fi guide](https://sdk.rokoko.com/guides/wifi-setup/))
- **Range:** Rokoko's own figures conflict (2 m, 2–4 m and 5 m radius all appear). The datasheet values for SGII are a **saturation (minimum) distance of 0.39–0.47 m** and a **maximum of 4.81 m** (where noise reaches 20 mm). Field strength falls with 1/r³, so expect better quality close in. ([Coil Pro page](https://rokoko.com/products/coil-pro), [datasheet EA-07/08](https://sdk.rokoko.com/datasheets/Smartgloves_I_II_Comparison_v1.0.0_External.pdf))
- **Setup:** mount it on a tripod or hang it from the ceiling (¼" thread) and keep it **stationary**, because it defines the world origin. Stay more than about 50 cm from its centre. After the Coil is first detected, do a quick **linear shake** so the SDK can resolve the EMF flip ambiguity. There's also a 180° ambiguity about Z that `--coil-half-space` sets. Only one Coil Pro is supported at a time. ([SDK Smartgloves ref](https://sdk.rokoko.com/reference/products/smartgloves/), [Coil Pro page](https://rokoko.com/products/coil-pro))
- **Out of range (sources conflict):** a Rokoko support article says that in a gloves-only setup the position *locks to the last known value* until you re-enter the field ([support article](https://support.rokoko.com/hc/en-us/articles/21541993570193-Capture-Space-of-the-Coil-Pro), seen via a search summary). The product page says the IMU "takes over gradually" ([Coil Pro page](https://rokoko.com/products/coil-pro)). Either way, there's no reliable position outside the field.
- Check `is_coil_pro_present` before trusting the `arm_sensor → coil_pro` pose. The stream is *always declared*, even when no Coil is present. ([SDK Smartgloves ref](https://sdk.rokoko.com/reference/products/smartgloves/))

---

## 2. Software and data access

There are two independent routes. **For robotics, use the Device SDK.** Studio is the animation tool.

### A. Rokoko Device SDK (recommended)
- **What it is:** a driver (`rokoko-sdk`) that talks to the gloves over USB or Wi-Fi, a TCP command protocol (**RCSP**) and a binary streaming protocol (**RGMP v2**). It gives "low-latency access to IMU, EMF, joint, and positional data", targets robotics, and **bypasses Studio**. ([Overview](https://sdk.rokoko.com/reference/overview/), [sdk.rokoko.com](https://sdk.rokoko.com/))
- **Platforms:** Windows 10 x64, macOS 14+ (Apple silicon), **Ubuntu 22.04 / Debian 12 on x64 and Arm64**. The Python examples need **Python 3.12+**; the pure-Python solver needs 3.10+. Package contents: `bin/` (driver and CLI), `examples/` (Python), `sdk/` (C/C++ headers). ([Quick start](https://sdk.rokoko.com/guides/quick-start/), [Python solver](https://sdk.rokoko.com/examples/rgmp_hand_solver/))
- **Licence:** a dedicated SDK licence is required. Install by signing in at **id.rokoko.com**, opening the Team that holds the SDK licence, and running that tile's install script. For the challenge: create a Rokoko ID, submit the form, and wait for Rokoko to accept you (see `docs/challenges/main/rokoko--the-robot-teleoperation-challenge.md`). Retail pricing is quote-based. ([Linux install](https://sdk.rokoko.com/guides/install/linux/))
- **Ports:**

| Port | Protocol | What |
|---|---|---|
| 14041 | glove → driver (Wi-Fi) | Set with `network_configuration.py set --receiver-port`; match it with `rokoko-sdk -dup` ([Wi-Fi guide](https://sdk.rokoko.com/guides/wifi-setup/)) |
| 45451 | TCP, RCSP (binary header + JSON) | Commands: `ListDevices`, `SubscribeToData`, `ReinitAlgo`, `SetColorLed` ([RCSP](https://sdk.rokoko.com/reference/rcsp/)) |
| 12276 | TCP, RGMP | Raw per-sensor stream from the driver ([Streaming](https://sdk.rokoko.com/guides/streaming-data/)) |
| 12277 | TCP, RGMP | Solved hands from `rkk-hand-solver` ([Hand solving](https://sdk.rokoko.com/guides/hand-solving/)) |

- **RGMP v2 format:** TCP, little-endian, with an 8-byte header (`msg_prefix`, `msg_len`). There are three frame types: 1 = stream definition (JSON), 2 = binary data frame (16-byte header `device_id`, `group_id`, `timestamp_us`, then tightly packed values), 3 = device disconnect. Quaternions are **x, y, z, w**, units are metres, rad/s and m/s². Each group declares an `expected_rate_hz`; gloves run at 83.33 Hz. ([RGMP](https://sdk.rokoko.com/reference/rgmp/))
- **USB isn't streamed by default.** Start with `rokoko-sdk --auto-stream-usb` or send `SubscribeToData`. Timestamps count from device boot unless you use `-ef 1024` (shared epoch). ([Streaming](https://sdk.rokoko.com/guides/streaming-data/))
- **Hand solver (`rkk-hand-solver`, a binary that ships with the SDK):** reads :12276 and emits a 26-joint hand per glove on :12277, as `joints_local` (for retargeting), `joints_world`, or with **`--emit-openxr`** 26 OpenXR `XrHandJointEXT` joints (wrist at origin, magnetic-north yaw kept). The pure-Python solver (`rgmp_hand_solver.py`) **can't** emit OpenXR. Early-release limits: no calibration is applied, and Coil Pro world anchoring is "the least validated path". ([Hand solving](https://sdk.rokoko.com/guides/hand-solving/), [Python solver](https://sdk.rokoko.com/examples/rgmp_hand_solver/))
- **Python examples in `$ROKOKO_SDK_HOME/examples/python`:** `rgmp_stream.py` (prints rows as TSV, filters on `--measure-type`/`--target-frame`), `rcsp_cmd_example.py`, `network_configuration.py`, `rgmp_pinch_detector`, and the `rgmp_core/` client package. ([Overview](https://sdk.rokoko.com/reference/overview/))

### B. Rokoko Studio + Studio Live (the animation path)
- Studio runs on **Windows and macOS only**. ([Robotics page](https://rokoko.com/use-cases/robotics))
- **Custom streaming:** UDP, **default port 14043**, **one JSON frame per datagram** with no header. Formats are JSON v3 or v4, optionally LZ4-framed (magic `04 22 4D 18`). Reported as needing the **Plus, Pro or Enterprise** plan. ([Custom Streaming article](https://support.rokoko.com/hc/en-us/articles/4410416376977-Custom-Streaming); we saw it only through a search summary because the page blocks automated fetch, so unconfirmed in detail)
- **JSON v3 shape** (from Rokoko's official Blender receiver): `scene.actors[].body.<bone>.{position{x,y,z}, rotation{x,y,z,w}}`. Bones include `leftHand`, `leftThumbProximal`, `leftThumbMedial`, `leftThumbDistal`, `leftIndexProximal`, and so on, plus `meta.hasGloves` and `fps`. ([receiver.py](https://github.com/Rokoko/rokoko-studio-live-blender/blob/master/core/receiver.py), [live_data_manager.py](https://github.com/Rokoko/rokoko-studio-live-blender/blob/master/core/live_data_manager.py), [animation_lists.py](https://github.com/Rokoko/rokoko-studio-live-blender/blob/master/core/animation_lists.py))
- **Studio stream rate:** unconfirmed (the JSON carries an `fps` field).
- **Studio Command API:** HTTP `http://<ip>:14053/v1/<api-key>/<command>` for recording start/stop, calibrate and toggle livestream. ([studio-command-api-examples](https://github.com/Rokoko/studio-command-api-examples))
- **Use Studio when** we need Coil Pro set up through the GUI, a Smartsuit full-body skeleton, or to record FBX/BVH/CSV.

### Existing integrations (official and community)
| What | Notes | Link |
|---|---|---|
| **Isaac Lab glove device** (in the SDK) | `RokokoGloveDevice` impersonates Isaac Lab's `OpenXRDevice`. Built for **Isaac Lab 2.3.0 / Isaac Sim 5.1.0**, demoed on Fourier **GR1T2** hands (dex-retargeting) and a Franka. Includes `isaac_teleop_record.py` (HDF5 demo recording). Uses NVIDIA driver 580; driver 595 crashed Isaac Sim 5.1 RTX. Solver hop latency is about 0.1 ms | [sdk.rokoko.com/examples/isaac](https://sdk.rokoko.com/examples/isaac/) |
| **ROS 2 bridge** (Apache-2.0) | Driver → solver → `rkk_hand_bridge`. Topics `/rkk_hand_bridge/hand/joints` (26 joints) and `/tf`, plus a yaw `calibrate` service. Humble, Jazzy and Lyrical. Needs SDK ≥ 0.10.0 | [Rokoko/rokoko-ros2-bridge](https://github.com/Rokoko/rokoko-ros2-bridge), [docs](https://sdk.rokoko.com/integrations/ros2/) |
| Unity, Unreal, Blender, Maya, C4D | Studio Live plugins (animation, not robotics) | [github.com/Rokoko](https://github.com/Rokoko) |
| Robot hands Rokoko lists | Tesollo, BrainCo, Wuji, Robotis, Robotera. Inspire, Seed and Linkerbot are "coming soon". **No Unitree Dex3** | [Robotics page](https://rokoko.com/use-cases/robotics) |
| Aalto Robotics Club Inspire integration | Mentioned in the challenge text. **No public repo found**, so ask the mentors | n/a |
| Rokoko fork of NVIDIA IsaacTeleop | Fork with no extra commits on `main` (upstream is now **NVIDIA Isaac Capture**) | [Rokoko/IsaacTeleop](https://github.com/Rokoko/IsaacTeleop) |

---

## 3. Practical notes for retargeting

- **Frames:** the glove frame is right-handed and gravity-referenced (+X right, +Y toward the wrist, +Z down). Hub heading is **magnetic north, so it's arbitrary in the scene until you recenter**. Left and right hands are mirrors, not rotations. Rebase with a single proper rotation, never a mirror. In the OpenXR output, `xr_base` is the glove frame rotated +90° about X (Y up). ([Hand solving](https://sdk.rokoko.com/guides/hand-solving/))
- **Calibration:** the gloves have **no calibration command**; they auto-initialise. SGII's magnetometer needs a few hub rotations **away from metal** before `is_heading_reliable` turns true. Use `ReinitAlgo` to reset the fusion. For yaw, hold the hands level, face "forward", then zero the yaw (the ROS bridge's `calibrate` service does this, and the Isaac device has `calibrate()`). ([SDK Smartgloves ref](https://sdk.rokoko.com/reference/products/smartgloves/), [ROS 2 bridge](https://github.com/Rokoko/rokoko-ros2-bridge))
- **Magnetic interference:** ferrous metal, electric motors and big electronics distort the EMF field and the magnetometer. Use wooden or plastic tables and test in the actual demo spot. A **metal humanoid next to the Coil Pro is a risk**. Watch `is_emf_saturated` and `is_magnetometer_saturated`. ([Tech overview](https://sdk.rokoko.com/guides/tech-overview-emf-imu/))
- **Drift:** IMU-only heading drifts. SGII's magnetometer corrects heading, and only Coil Pro gives drift-free position. ([Tech overview](https://sdk.rokoko.com/guides/tech-overview-emf-imu/))
- **Wi-Fi vs USB:** USB has less jitter (19 ms) but tethers the operator. Wi-Fi needs the dedicated router. Configure Wi-Fi over USB first with `network_configuration.py set ... --receiver-address auto --receiver-port 14041`. ([Wi-Fi guide](https://sdk.rokoko.com/guides/wifi-setup/))
- **Rate:** the gloves run at 83.33 Hz, so for a 30 Hz control loop just take the latest frame each tick.

---

## 4. Ready-made G1 / Dex3 retargeting code

- **Dex3-1 kinematics:** 7 active DoF per hand: thumb 3, index 2, middle 2. ([unitree.com/g1](https://www.unitree.com/g1))
- **Unitree `xr_teleoperate`** (formerly `avp_teleoperate`) is the closest match. It teleoperates G1 + Dex3 **in simulation** (`--sim`) or on the real robot, records demos (`--record`), and has a **default control/record rate of 30 Hz** (`--frequency 30.0`). ([repo](https://github.com/unitreerobotics/xr_teleoperate))
  - Dex3 retargeting config: [`assets/unitree_hand/unitree_dex3.yml`](https://github.com/unitreerobotics/xr_teleoperate/blob/main/assets/unitree_hand/unitree_dex3.yml) uses the **dex-retargeting DexPilot** optimizer with fingertips `thumb_tip`, `index_tip`, `middle_tip` and human keypoint indices `0, 4, 9, 14` (wrist, thumb tip, index tip, middle tip) **in a 25-keypoint hand**, plus a low-pass filter (α = 0.2).
  - `Dex3_1_Controller` ([robot_hand_unitree.py](https://github.com/unitreerobotics/xr_teleoperate/blob/main/teleop/robot_control/robot_hand_unitree.py)) takes a **25×3 keypoint array per hand** and publishes DDS `rt/dex3/{left,right}/cmd`.
  - Hand and arm frame conversions (OpenXR basis → Unitree hand URDF convention) are in televuer's [`tv_wrapper.py`](https://github.com/unitreerobotics/televuer/blob/main/src/televuer/tv_wrapper.py) (`T_TO_UNITREE_HAND`, etc.). Arm IK takes a wrist SE(3) pose.
- **Our reading (not yet verified):** OpenXR's 26 joints are palm, wrist, then 4 thumb and 5 per finger. **Dropping the palm gives exactly this 25-point layout** (0 wrist, 4 thumb tip, 9 index tip, 14 middle tip). So Rokoko's `--emit-openxr` output should plug into the Dex3 config once we express the points in the wrist frame and apply televuer's transform.
- **`unitree_sim_isaaclab`** provides G1-29DoF + Dex3 Isaac Lab tasks (e.g. `Isaac-PickPlace-Cylinder-G129-Dex3-Joint`, `Isaac-Stack-RgyBlock-G129-Dex3-Joint`) using **the same DDS topics as the real robot**. `main` targets Isaac Sim 6.2.0 / Isaac Lab 3.0.0; an `IsaacSim5.1.0` branch exists. ([repo](https://github.com/unitreerobotics/unitree_sim_isaaclab))
- **`unitree_lerobot`** (formerly unitree_IL_lerobot) converts `xr_teleoperate` recordings to LeRobot format and trains policies. ([repo](https://github.com/unitreerobotics/unitree_lerobot))
- **dex-retargeting**: vector, position and DexPilot optimizers for human → robot hand. ([dexsuite/dex-retargeting](https://github.com/dexsuite/dex-retargeting))
- **NVIDIA Isaac Capture** (formerly Isaac Teleop, now part of Isaac Lab 3.0) has a `G1/trihand_motion_controller.py` retargeter, but it maps **VR controller triggers**, not hand keypoints, to the 7 G1 tri-hand joints. It also ships a Manus glove plugin; there's no Rokoko plugin upstream. ([NVIDIA/IsaacCapture](https://github.com/NVIDIA/IsaacCapture))

---

## 5. What this means for us

**Pipeline that reuses the most existing code:**
```
Smartgloves II ──USB/Wi-Fi──> rokoko-sdk :12276 ──> rkk-hand-solver --emit-openxr :12277 (RGMP/TCP)
   └─> our Python bridge (rgmp_core client): 26 OpenXR joints/hand @83 Hz
         ├─ fingers: drop palm → 25×3 in wrist frame → T_TO_UNITREE_HAND → dex-retargeting (unitree_dex3.yml) → 7 q/hand
         └─ wrist:   Coil Pro arm_sensor→coil_pro pose (if present) → xr_teleoperate arm IK (G1_29)
   └─> 30 Hz loop → DDS rt/dex3/*/cmd + arm cmd → unitree_sim_isaaclab (--enable_dex3_dds) ; --record → unitree_lerobot
```
- **Simplest integration:** fork `xr_teleoperate` and replace `TeleVuerWrapper.get_tele_data()` with a Rokoko reader that fills `left_hand_pos` / `right_hand_pos` (25×3) and the wrist poses. Everything downstream already exists: Dex3 retargeting, arm IK, sim mode, recording.
- **Keep the Rokoko reader in its own process** (Python 3.12 for the SDK examples) and pass data over shared memory, UDP or DDS, so we avoid Python, conda and Isaac version clashes. Rokoko's Isaac Lab device targets Isaac Lab 2.3, while Unitree's sim targets Isaac Lab 3.0.
- **5 → 3 fingers:** use thumb, index and middle; ignore ring and little. DexPilot keeps thumb–index and thumb–middle **pinch distances**, which is what grasping needs. Tune `scaling_factor` and `low_pass_alpha`.
- **No Coil Pro means no wrist position.** Fallbacks: fix the wrist at a nominal pose and drive only orientation plus fingers; translate with keyboard or gamepad; use camera-based wrist tracking (see `jetson.md`); or use the Smartsuit through Studio (body FK, drifts). **Ask Rokoko on site for a Coil Pro.** The challenge lists it as available.
- **To do first:** get the SDK licence (form, then id.rokoko.com) → `rokoko-sdk --auto-stream-usb` → `rgmp_stream.py --port 12277` to see the joints → map 25 points into Dex3 in sim.
- **Open questions for the Rokoko and Aalto mentors:** Can we borrow a Coil Pro? Where is the Aalto Inspire integration code? Is Linux Arm64 OK on Ubuntu 24.04 (JetPack 7)? Officially only 22.04 is listed.
