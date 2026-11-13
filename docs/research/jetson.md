# NVIDIA Jetson (the "Jensen chip"): what it is and what it can do for us

**Question:** Which Jetson do we have, what can it run, and is it useful in a gloves → G1 humanoid teleop project?
**Short answer:** Identify it with the commands below. Whatever model it is, it **can't run Isaac Sim**. It's useful as an edge box for camera-based wrist tracking, as a glove-to-robot bridge, or for running a trained policy and a small VLM. Keep it off the critical path.
Researched 2026-11-13. "Unconfirmed" means we couldn't verify it from an official source.

---

## 1. How to identify the model (run on the board)

```bash
tr -d '\0' < /proc/device-tree/model   # e.g. "NVIDIA Jetson Orin Nano Developer Kit"
cat /etc/nv_tegra_release              # L4T / Jetson Linux version (R36 = JetPack 6.x, R39.2 = JetPack 7.2)
apt-cache show nvidia-jetpack | grep -m1 Version   # JetPack version
free -h                                # total RAM: 4 / 8 / 16 / 32 / 64 / 128 GB narrows it down
sudo nvpmodel -q                       # current power mode ("MAXN SUPER" means Super-capable firmware)
sudo tegrastats                        # live RAM/CPU/GPU load; works on every Jetson
sudo pip3 install -U jetson-stats && sudo reboot   # then:
jtop                                   # TUI; the "INFO" page shows module, part no., JetPack, CUDA
jetson_release -v                      # one-shot summary of model, L4T, JetPack, CUDA, cuDNN, TensorRT
```
- `/proc/device-tree/model` gives the board name. jetson-stats (`jtop`, `jetson_release`) maps the module part number to a name. ([jetson-stats docs](https://rbonghi.github.io/jetson_stats/reference/jtop.html), [PyPI](https://pypi.org/project/jetson-stats/), [NVIDIA forum](https://forums.developer.nvidia.com/t/how-to-identify-different-jeston-machine-nano-tx2-xariver-and-nx-etc/121445))
- `nvidia-smi` may be missing or limited on Orin with older JetPack; use `tegrastats` or `jtop` instead (unconfirmed per version).
- **Label on the module** (sticker or silkscreen), from NVIDIA's part numbers ([Jetson FAQ](https://developer.nvidia.com/embedded/faq)):

| Part number prefix | Module |
|---|---|
| `900-13767-0030` / `-0040` | Orin Nano 8GB / 4GB |
| `900-13767-0010` / `-0000` | Orin NX 8GB / 16GB |
| `900-13701-0040` / `-0050` / `-0080` | AGX Orin 32GB / 64GB / Industrial |
| `900-13834-0000` / `-0080` | Thor T4000 / T5000 |
| Dev kit box `945-13766-…` / `945-13730-…` / `945-14070-…` | Orin Nano Super / AGX Orin 64GB / AGX Thor dev kits |

- **Hint:** the G1 EDU spec lists a "High Computing Power Module … such as Orin" ([unitree.com/g1](https://www.unitree.com/g1)). Resellers say it's an Orin NX 16GB (unconfirmed by Unitree). Check whether our Jetson *is* the G1's onboard computer or a separate board.

---

## 2. Current lineup

| Module | AI perf | GPU | CPU | RAM / BW | Power | MSRP (NVIDIA FAQ, Nov 2026) |
|---|---|---|---|---|---|---|
| Orin Nano 4GB | 34 TOPS (Super; 20 originally) | 512-core Ampere, 16 Tensor | 6× A78AE 1.7 GHz | 4 GB, 51 GB/s | 7–25 W | $349 module |
| **Orin Nano 8GB / Nano Super Dev Kit** | 67 TOPS (Super; 40 originally) | 1024-core Ampere, 32 Tensor | 6× A78AE 1.7 GHz | 8 GB, 102 GB/s | 7–25 W | $399 module; **dev kit $399** (launched at $249) |
| Orin NX 8GB | 117 TOPS (Super; 70) | 1024-core Ampere, 32 Tensor | 6× A78AE 2.0 GHz | 8 GB, 102 GB/s | 10–40 W | $649 module |
| Orin NX 16GB | 157 TOPS (Super; 100) | 1024-core Ampere, 32 Tensor | 8× A78AE 2.0 GHz | 16 GB, 102 GB/s | 10–40 W | $999 module |
| AGX Orin 32GB | 241 TOPS (Super, JetPack 7.2; 200) | 1792-core Ampere, 56 Tensor | 8× A78AE | 32 GB, 204.8 GB/s | 15–40 W originally (unconfirmed); up to 60 W in Super | $1,799 module |
| AGX Orin 64GB / Dev Kit | 275 TOPS | 2048-core Ampere, 64 Tensor | 12× A78AE 2.2 GHz | 64 GB, 204.8 GB/s | 15–60 W | $2,999 module; $3,499 dev kit |
| Thor T4000 | 1200 FP4 TFLOPS (sparse) | 1536-core Blackwell | 12× Neoverse-V3AE | 64 GB LPDDR5X, 273 GB/s | 40–70 W | $2,999 module |
| **Thor T5000 / AGX Thor Dev Kit** | 2070 FP4 TFLOPS (sparse) | 2560-core Blackwell | 14× Neoverse-V3AE 2.6 GHz | 128 GB LPDDR5X, 273 GB/s | 40–130 W | $4,999 module; **dev kit $5,499** (launched at $3,499 in Aug 2025) |

Sources: [Jetson Orin page](https://www.nvidia.com/en-us/autonomous-machines/embedded-systems/jetson-orin/), [JetPack 6.2 Super mode blog](https://developer.nvidia.com/blog/nvidia-jetpack-6-2-brings-super-mode-to-nvidia-jetson-orin-nano-and-jetson-orin-nx-modules/), [Orin Nano Super dev kit](https://www.nvidia.com/en-us/autonomous-machines/embedded-systems/jetson-orin/nano-super-developer-kit/), [Jetson Thor page](https://www.nvidia.com/en-us/autonomous-machines/embedded-systems/jetson-thor/), [Thor launch](https://nvidianews.nvidia.com/news/nvidia-blackwell-powered-jetson-thor-now-available-accelerating-the-age-of-general-robotics), [Jetson FAQ prices](https://developer.nvidia.com/embedded/faq), [AGX Orin 32GB Super](https://linuxgizmos.com/nvidia-jetpack-7-2-expands-support-for-nemoclaw-yocto-project-and-agx-orin-32gb-super-mode/).
- Orin TOPS are **sparse INT8**, while Thor figures are **FP4 TFLOPS**, so they aren't directly comparable.
- "Super" is a **software update** (JetPack 6.2+) for existing Orin Nano and NX boards, not new hardware. ([Nano Super page](https://www.nvidia.com/en-us/autonomous-machines/embedded-systems/jetson-orin/nano-super-developer-kit/))
- NVIDIA has announced Thor T3000 and T2000 modules. JetPack 7.2.1 supports only T3000 *emulation* so far, and there are no public specs. ([NVIDIA blog](https://blogs.nvidia.com/blog/jetson-thor-robotics-edge-ai-agent/), [JetPack 7.2.1](https://developer.nvidia.com/embedded/jetpack/downloads/archive-7.2.1.md))

### JetPack versions
| JetPack | Jetson Linux | Base | CUDA | Devices |
|---|---|---|---|---|
| 6.2 | 36.4.3 | Ubuntu 22.04, kernel 5.15 | 12.6 | Orin family; introduced Super mode ([notes](https://docs.nvidia.com/jetson/archives/jetpack-archived/jetpack-62/release-notes/index.html)) |
| 7.0 / 7.1 | 38.x (unconfirmed) | Ubuntu 24.04 | 13.0 | Thor only ([Isaac ROS notes](https://nvidia-isaac-ros.github.io/releases/index.html)) |
| **7.2.1** (11 Aug 2026) | 39.2.1 | Ubuntu 24.04, kernel 6.8 | **13.2.2**, cuDNN 9.20, **TensorRT 10.16.2** | **Thor (T5000/T4000) + Orin family**; the Orin Nano ISO flashes Super mode by default ([notes](https://developer.nvidia.com/embedded/jetpack/downloads/archive-7.2.1.md)) |

---

## 3. Software stack

- **JetPack** bundles Jetson Linux, CUDA, cuDNN and TensorRT (versions above). Run models as PyTorch (Jetson wheels/containers), as **ONNX → TensorRT** (`trtexec --onnx=model.onnx --saveEngine=model.engine --fp16`), or through ONNX Runtime with the TensorRT execution provider.
- **jetson-containers** (dusty-nv) prebuilds Docker images: PyTorch, ONNX Runtime, DeepStream, Ollama, llama.cpp, vLLM, SGLang, MLC, ROS, LeRobot and more. It's tested on **JetPack 6.2 (CUDA 12.6) and JetPack 7 (CUDA 13.x)**. To use it: `git clone https://github.com/dusty-nv/jetson-containers && bash jetson-containers/install.sh`, then `jetson-containers run $(autotag l4t-pytorch)`. ([repo](https://github.com/dusty-nv/jetson-containers))
- **NVIDIA Jetson AI Lab** has tutorials and a model catalogue. Examples marked as fitting an **Orin Nano 8GB**: *Qwen3 VL 4B* (vLLM), *Cosmos Reason 2 2B* (vLLM / llama.cpp), *Nemotron3 Nano 4B* (vLLM / llama.cpp). *Qwen3 VL 8B* needs an Orin NX 16GB or larger. VLAs such as *Cosmos3 Edge* need an AGX Orin 64GB or Thor. ([jetson-ai-lab.com](https://www.jetson-ai-lab.com/), [models](https://www.jetson-ai-lab.com/models))
- **Isaac ROS:** release **3.2** goes with JetPack 6.2 on Orin (ROS 2 Humble). **4.6.0** (Aug 2026) adds JetPack 7.2 on Orin and Thor. **5.0.0** (Sept 2026) targets ROS 2 Lyrical on Ubuntu 24.04. ([release notes](https://nvidia-isaac-ros.github.io/releases/index.html)) The JetPack 7.2.1 page still lists Isaac ROS as "coming soon", so check before installing.
- **DeepStream:** a GStreamer video-analytics SDK, available as a jetson-containers package. Overkill for us. ([jetson-containers](https://github.com/dusty-nv/jetson-containers))
- **Camera hand and pose tracking:**
  - **MediaPipe** ships `manylinux aarch64` wheels on PyPI (v1.2.3), so `pip install mediapipe` works on the CPU. GPU acceleration on Jetson is unconfirmed. ([PyPI](https://pypi.org/project/mediapipe/)) It gives 21 hand keypoints, but depth is only relative.
  - **trt_pose_hand** (NVIDIA-AI-IOT, TensorRT hand pose) was last updated in Feb 2021 (JetPack 4 era), so it's probably stale. ([repo](https://github.com/NVIDIA-AI-IOT/trt_pose_hand))
  - For **metric 3D wrist position** you need a depth or stereo camera (RealSense, ZED, OAK): use a 2D keypoint plus the depth pixel. A mono RGB camera only gives image-plane position and a rough scale. We don't know yet whether a depth camera is available.
- **Rokoko Device SDK on Jetson:** the SDK supports **Linux Arm64 on Ubuntu 22.04 / Debian 12**, which matches JetPack 6.2. **Ubuntu 24.04 (JetPack 7.x) isn't listed**, so that's unconfirmed. The examples need Python 3.12+. ([Rokoko quick start](https://sdk.rokoko.com/guides/quick-start/), [robotics page](https://rokoko.com/use-cases/robotics))

---

## 4. Can it run Isaac Sim? **No.**

- Isaac Sim requirements: x86_64 Ubuntu 22.04/24.04 or Windows 11 with at least a **GeForce RTX 4080 (16 GB VRAM) and 32 GB RAM**. "GPUs without RT Cores (A100, H100) are not supported." "Isaac Sim aarch64 builds are currently only supported on DGX Spark system." Jetson isn't listed. ([Isaac Sim requirements](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html))
- NVIDIA forum threads confirm that Jetson, including AGX Thor, is unsupported for Isaac Sim. ([Thor thread](https://forums.developer.nvidia.com/t/isaac-sim-report-error-on-thor-agx-t5000-error-rtx-denoising-plugin-failed-to-compile-compute-shader-rtx-nrd-packfornrd-cs-hlsl/358400), [AGX Orin thread](https://forums.developer.nvidia.com/t/clarification-isaac-sim-running-on-jetson-agx-orin/370886))
- The same applies to Isaac Lab and `unitree_sim_isaaclab`. Those need an **x86 PC with an RTX GPU** (a teammate laptop with RTX ≥ 4080, a desktop, or a cloud GPU).

---

## 5. What this means for us

**Realistic roles (best first):**
1. **Edge policy inference, our pitch moment.** Train an ACT or diffusion policy (LeRobot / `unitree_lerobot`) on the RTX PC, export it to ONNX → TensorRT, and run it on the Jetson, closing the loop over DDS to the sim (or the real G1). That supports the line "data collected by teleop, policy runs on robot-class compute". Any Orin can run a small ACT policy at 30 Hz (unconfirmed, but these models are small).
   - In the **Aalto challenge** this is a demo extra, not the scored submission. The submission is a Docker image that runs on their RTX 5090 finals PC, and teams never get DDS access to the real robot (see `aalto-humanoid.md`).
2. **Camera-based wrist position fallback** if we have no Coil Pro: a USB or depth camera plus MediaPipe Hands on the Jetson gives the wrist position, and the gloves supply the fingers and orientation. Send the result over UDP or DDS to the teleop bridge. It works best with a depth camera; it's noisy otherwise. (A laptop can do the same; the Jetson mainly adds the "edge" story.)
3. **Glove bridge box:** run `rokoko-sdk` and `rkk-hand-solver` on the Jetson (Arm64 Linux, needs JetPack 6.2 / Ubuntu 22.04 to be safe) plus our retargeting, and publish Dex3 and arm joint targets over DDS. It's a tidy "wearable → edge → robot" architecture, but it adds a moving part.
4. **Stretch: language layer.** Run a small VLM or LLM (e.g. Qwen3 VL 4B on Orin Nano 8GB through jetson-containers / vLLM) to turn "sort the red blocks" into a task ID for the policy.

**What it can't do:**
- It can't run Isaac Sim or Isaac Lab, the digital twin, or RL training.
- On an Orin Nano or NX it can't train policies in reasonable time. Train on the RTX PC or in the cloud.
- An Orin Nano or NX can't run large VLAs (GR00T-class or Cosmos3 Edge); those need an AGX Orin 64GB or Thor.

**First steps:** run the section 1 commands, record the model and JetPack version in `docs/TEAM.md`, and decide on role 1 or 2 only after the core glove → sim loop works.
