# Team

Skills summary from each member's LinkedIn profile (read 2026-11-13). Professional info only. Update it as people tell us more, since LinkedIn misses a lot.

## Members

### Emīls Šmits — ML / data science
- **Now:** MSc student, Machine Learning, Data Science & AI @ Aalto University (from Aug 2026); Visiting Lecturer @ Rīga Stradiņš University (Sep 2026–).
- **Before:** Data Scientist @ BTA Baltic Insurance (Dec 2023–Oct 2026: intern → junior → data scientist, insurance pricing); Research Student @ Laboratory of Magnetic Soft Materials; Lab Assistant @ Laser Center, University of Latvia.
- **Education:** BSc Physics, University of Latvia (honors). Thesis: physics-informed neural networks for non-Newtonian fluid flow reconstruction from sparse data. SSE Riga Future Leaders Academy (team pitch on Latvia's digitalisation).
- **Skills:** Python, machine learning, deep learning, statistical modelling, insurance pricing, lecturing, leadership.

### Marcus Öberg — robotics / autonomy / C++
- **Now:** Co-founder @ KTH Robotics Society (Jun 2026–); Driverless team member @ KTH Formula Student (2022–).
- **Highlights (Formula Student):** C++ vehicle-dynamics simulation framework (DAG scheduling, threading); multithreaded MPC controller (<1 ms solves, Eigen, sparsity); Kalman filter for online parameter estimation; hybrid SLAM (EKF + factor-graph optimisation, <2 ms real time) that enabled the team's first fully autonomous runs; mentored new members on C++/ROS/CMake.
- **Research:** Research assistant @ KTH, Trustworthy Edge Computing (Apr–Aug 2025): autonomous-vehicle experiments, ROS node for ArUco camera/object pose estimation, model training.
- **Education:** MSc-level engineering degree, Computational and Applied Mathematics @ KTH (2021–2027).
- **Skills:** C++, CMake, ROS, SLAM, state estimation, MPC / control design, optimisation, point-cloud processing, sensor integration, numerical simulation, HPC.
- **Relevant context:** KTH Robotics Society runs projects on **SO-101 LeRobot arms and VLA policies**, the same arm used in the Intel Physical AI challenge.

### Tiya Kumar — AI engineering / product / hackathons
- **Now:** AI Engineer @ Wise (Sep 2026–); Co-founder @ stealth startup (Sep 2026–); Builder @ mesh. (Mar 2026–).
- **Before:** AI Product Developer intern @ Shiwaforce (Jul 2025–Aug 2026); Discrete Mathematics TA @ Eötvös Loránd University (2023–2026).
- **Education:** BSc Computer Science, Eötvös Loránd University (2023–2026); International Baccalaureate.
- **Hackathons:** **1st place, PwC Hungary AI Hackathon 2026** (out of 105 teams; built "Lumen", a market-intelligence platform for Hungarian logistics, covering business case, financial feasibility and tech). 3rd place, GDE-MIT AI hackathon.
- **Skills:** Python, C#, Haskell, HTML, mathematics, business; strong at pitching under time pressure.

### Samer Haddadin — hardware / prototyping
- **Now:** Founder @ stealth startup (Sep 2026–); Builder @ mesh. (May 2025–).
- **Education:** BSc Engineering Physics @ Budapest University of Technology and Economics (2024–2028). High school: robotics club, science club, MUN.
- **About:** hands-on hardware and robotics prototyping; passionate about mechanics, robotics and applied innovative tech.
- **Skills:** PCB design, microcontrollers, hardware development, haptics, VR, Autodesk Fusion 360 (CAD), MATLAB, C, C++, JavaScript, entrepreneurship.

## Who does what (from Fri 13 Nov evening)

| Area | Folder | People |
|---|---|---|
| Model fine-tuning | `training/` | Emīls, Tiya |
| Simulation | `sim/` | Marcus, Samer |
| Datasets, submission, sim scoring | `data/`, `policy/`, `eval/` | TBD |

## Hardware we have (as of Fri 13 Nov)

- **NVIDIA Jetson** ("Jensen chip"): exact model TBD. Identify it with `tr -d '\0' < /proc/device-tree/model` (more in `docs/research/jetson.md`). It can't run Isaac Sim
- **Rokoko Smartgloves II**: tracks all 5 fingers plus hand orientation. **Hand position in space needs a Coil Pro** (ask Rokoko reps). Details in `docs/research/rokoko.md`
- **Intel Physical AI station**: not obtained, so that challenge is off the table
- **Arduino boards**: not planning to use them

Direction: **Aalto humanoid, mostly in simulation** (brief still to be agreed). Gloves research: `docs/research/rokoko.md`.

## Team at a glance

| Area | Who | Strength |
|---|---|---|
| ML modelling, data, evaluation | Emīls | Strong |
| Robotics software: SLAM, control, state estimation, ROS, real-time C++ | Marcus | Strong |
| AI product building, LLM apps, pitching | Tiya | Strong (proven hackathon winner) |
| Hardware: PCB, microcontrollers, CAD, haptics/VR | Samer | Strong |
| Frontend / UI design | Tiya (HTML) | **Gap**: nobody lists React/UI design |
| Backend / deployment / cloud | — | **Gap**: not listed; assume shared |
| Business case & pitch | Tiya, Emīls (leadership programme), Samer (founder) | Good |

## Fit notes (facts only; the challenge choice is open)

- The team covers physical AI end to end: ML (Emīls), robotics software (Marcus), hardware (Samer) and product/pitch (Tiya). That matches the robotics/hardware challenges in `docs/challenges/` well, and Marcus already knows SO-101 + VLA.
- Weaker spots for pure web/app challenges: frontend and deployment would need to be learned or simplified.
- Unknowns to ask the team: who has a laptop with a GPU, frontend comfort, cloud/deploy experience, who wants to pitch.
