# APIs, credits and borrowable hardware

Sources, read 2026-11-13:
- Hackerpacks: https://hackjunction.app/participate/45/hackerpacks
- Tech-challenge pages in [`../challenges/tech/`](../challenges/tech/)
- Junction hardware desk: https://2026.hackjunction.com/hardware

**Codes and claim links are in `.env.challenges` (git-ignored). This file only names the variable.**

## Most relevant for the robotics idea (Rokoko gloves + G1 sim + Jetson)

| What | Amount | Why it matters for us | How to claim |
|---|---|---|---|
| **Verda** GPU cloud | **€200 per member** (personal account + API credentials; €800 for 4) | The Aalto sim needs an RTX-class GPU (RTX Pro 6000 / L40S / A6000 class, not A100/H100). Use on-demand instances + a persistent volume. Also covers VLA fine-tuning (80 GB GPUs). Fits the stackable **Verda Compute Track** ($10k prize), whose example ideas literally include "train … policies for Aalto's Unitree G1" and "Rokoko motion-capture teleoperation data" | 1) submit the claim form on the hackerpack card, and the credits arrive by email; 2) log in to console.verda.com and claim them; 3) **a payment card is required** (Verda: "for security reasons", not charged, removable right away; whether usage can exceed the credits is unanswered); 4) each member does this for their own account ([docs](https://docs.verda.com/resources/obtaining-free-credits/how-to-redeem-credits/)). Booth #6, floor 3 |
| **Modal** serverless GPUs | **$100 per participant** ($400 team) | Training and fine-tuning on A100/H100/H200/B200. Also has RTX PRO 6000 and L40S. Python-native (`modal run`), per-second billing. Good for training jobs; running Isaac Sim there is untested | Code in `MODAL_PROMO_CODE`; starter kit + workshop at the Modal booth |
| **Qualia** data platform | Free (environment closes after 7 days) | Upload **Rokoko mocap** or arm demos; it flags bad takes, timing issues and inconsistent demos; curate a versioned set; export to train e.g. **π0.5 with LeRobot**. Directly fits a "glove demos → policy" story | Sign up at https://junction.qualiastudios.dev/login, create a team workspace; [upload guide](https://junction-docs.qualiastudios.dev/global/guides/data-collection/). Contact: Agnes Leth |
| **Wendy** | Free, open source | "Plug a Jetson … into your laptop, run `wendy run`". Deploys Python/ROS apps to the Jetson. On-site help | https://wendy.dev/ |
| **Rokoko Device SDK** | License for the event | Real-time glove/suit data stream into our code | Create a Rokoko ID → form on the Rokoko challenge page → accepted by reps → activate the SDK license. Victoria Stein (Rokoko) + Aalto Robotics Club mentors |
| **IronShard** object storage | Free | S3-compatible + MCP. For model weights and datasets too big for GitHub (>100 MiB); judges get read access | console.ironshard.dev/sign-up with your hackathon email; event code in `IRONSHARD_EVENT_CODE`; one team account, invite the others |
| **Scailab Scaipipe** | Free early access | Synthetic labelled images from 3D scenes + detection/segmentation training in the browser, with an MCP server. Could train an object detector for the coloured blocks | Google form on the hackerpack card; they email a login |
| **Featherless GPU** | Selected teams only | Bare-metal GPUs for fine-tuning | Talk to Featherless reps on site |

## LLM / VLM APIs

| What | Amount | Notes |
|---|---|---|
| **Anthropic Claude API** | $20 per participant | Claim link in `CLAUDE_CREDITS_URL`. Good for a rung-2 instruction parser or a planner |
| **Google Gemini API** | Credits; **one form per team** | Form: https://forms.gle/bByXvjGkW9WZuYwW9. 18+ only. Stackable **Best Use of Gemini API** (€4,000) |
| **Gemma** (open weights) | Free | Small Gemma models could run **offline inside the policy container**, which matters because the Aalto finals have no network. Stackable **Best Use of Gemma** (€1,000 × 3) |
| **NVIDIA Nemotron 3.5 Super VL** | Free tier | NVIDIA Build API (OpenAI-compatible, `https://integrate.api.nvidia.com/v1`, ~40 req/min per key), OpenRouter, or HF weights. 120B MoE (12B active), too big for the 32 GB finals GPU without heavy quantisation. Stackable **Best Use of Nemotron** (2 × RTX 5080) |
| **Featherless API** | $50 per participant | Open-weight model catalog, OpenAI-compatible at `https://api.featherless.ai/v1`. Coupon link in `FEATHERLESS_COUPON_URL` |
| **OpenAI Codex** | $100 per participant | Codex usage credits only (not API credits), via an assigned link. Stackable **Best Use of Codex** |

Aalto rule to remember: external API calls from the submission container are allowed **at your own risk**. The finals PC may have no network and there are no reruns, so any LLM step needs an offline fallback (a local model or a template parser).

## Web, data and infra (less relevant to the robot idea)

| What | Amount | Claim / note |
|---|---|---|
| Exa (web search API) | $50 per participant | Code in `EXA_PROMO_CODE` at dashboard.exa.ai/billing |
| Context.dev (web data) | 50k credits per team | Code in `CONTEXTDEV_PROMO_CODE` |
| Oxylabs Web API | First month of $500 plan free | Code in `OXYLABS_PROMO_CODE`. **Needs a credit card; cancel after the event** |
| Aiven (managed DBs) | $50 | console.aiven.io/signup |
| CRACI | €1,000 per team | CI/CD build minutes + "any compute need"; GitHub Actions compatible (`runs-on: craci`) |
| MariaDB | Free | Wikipedia datasets and vector-RAG examples |
| Cloudinary | Free tier | Image/video API; tech challenge needs the cld.media survey |
| Cala, Spread, Valio | Challenge-specific | Codes in `CALA_PROMO_CODE`, `SPREAD_EVENT_CODE`, `VALIO_*` |
| MLH (MongoDB Atlas, Vultr, Tiger Data, Solana, Entire, ElevenLabs) | Sponsor free tiers | Tech-challenge prizes only; see `../challenges/tech/` |

## Borrowable hardware (Junction hardware desk, 5th floor; snapshot Fri 21:15)

Borrowing rules:
- One request per team; a request does not reserve stock.
- Collect at the desk with your team name and photo ID.

| Item | Free / total | Notes |
|---|---|---|
| Rokoko Smartgloves | **0 / 9** (8 waiting) | We already have one pair |
| Rokoko Suit | **0 / 1** (3 waiting) | Needed for arm/wrist tracking if there's no Coil Pro. Ask Rokoko reps directly |
| Arduino UNO Q dev kit | 109 / 160 | Includes a USB camera |
| Intel Core Ultra AI PC (Dell XPS 16, HP OmniBook Ultra) | 4 / 25 | Laptops, not robot stations |
| Atech dev kit, Meta Ray-Ban glasses | 0 free | — |
| **3D printers** (Prusa Core One / MK4, Bambu P1S / P2S) | ~10 free | Desk-managed queue. Samer could print glove mounts or test objects (the Aalto object STLs are in the repo) |

Notes:
- No Jetson is listed at the desk. Ours came from elsewhere, so Wendy's team is the on-site help for it.
- The Rokoko challenge also lists a **Coil Pro** (precise hand positioning), the **Smartsuit Pro II**, G1 access coordinated with the Aalto team, a possible **Booster T1**, and an **Inspire robotic-hand integration** by Aalto Robotics Club. Ask Rokoko reps; these items are not on the desk.

## Credit math for the team (4 people)

| Use | Credits |
|---|---|
| GPU compute | Verda €800 (€200 × 4) + Modal $400 (+ CRACI €1,000, mainly CI/CD) |
| LLM APIs | Claude $80 + Featherless $200 + Gemini (team form) + Nemotron free tier |

Plan: spend Verda on the RTX sim box and Modal on training bursts.
