"""Can a vision/language model monitor the planner? Tests on saved head frames with true poses (no sim).

    python monitor_probe.py --frames FRAMES_DIR --run RUN_DIR --log decisions.jsonl --out results.json \
        [--roles grasp,grasp_pair,place,place_pair,census,sanity,diagnose,critique,critique_exp,critique_img]
        [--models d1,er,hydrogen] [--env-file .env] [--scene scene.yaml] [--scale 0.5] [--more RUN=LOG ...]

FRAMES_DIR: f_<unix time>.npz files (rgb, depth, state = the sim's true object poses) captured WHILE the run in
RUN_DIR was executing; they are lined up with the run's episodes by layout and with the picks by the episode
files' modification times (copy the run with scp -p), checked by matching "an object is in the air" to "the
fingers hold something" (monitor_rules.py). The *_pair roles send two images: before the pick and now.
Every model answer is cached in --out, so a second call only prints the tables. Needs numpy, opencv and
GEMINI_API_KEY (env var or --env-file). Models: Gemini Decision 1 (createDecision: yes/no and choice questions),
Gemini Robotics-ER 2 and Gemini 4 Hydrogen (generateContent with a JSON schema, thinking off).
Write-up: docs/research/model-monitor-oracle.md.
"""
from __future__ import annotations

import argparse
import base64
import collections
import glob
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monitor_rules as R  # noqa: E402

BASE = "https://generativelanguage.googleapis.com/v1beta"
GEN = {"er": "gemini-robotics-er-2-preview", "hydrogen": "gemini-4-hydrogen"}
BINS = {"left": (0.505, 0.26), "center": (0.505, 0.0), "right": (0.505, -0.26)}      # pelvis xy of the bin centres
WORD = {"red": "orange-red", "yellow": "yellow", "blue": "blue-purple"}
SCENE = ("The image is the head camera of a humanoid robot standing at a table. It sorts small coloured blocks "
         "(cubes, cylinders, triangular prisms; orange-red, yellow or blue-purple) into three open orange boxes "
         "(bins) at the far side of the table: left, center, right as seen in the image. Grey robot arms and "
         "three-finger hands may be in view. ")
_key = None


# ---------------------------------------------------------------------------------------------- API
def api_key(env_file=None):
    global _key
    if _key is None:
        _key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not _key and env_file:
            for line in open(env_file):
                if line.startswith("GEMINI_API_KEY="):
                    _key = line.split("=", 1)[1].strip().strip("\"'")
        if not _key:
            raise RuntimeError("no GEMINI_API_KEY (env var or --env-file)")
    return _key


def post(path, body, timeout):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"x-goog-api-key": api_key(), "Content-Type": "application/json"})
    t = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r), time.monotonic() - t, None
    except urllib.error.HTTPError as e:
        return None, time.monotonic() - t, f"http {e.code}: {e.read()[:200].decode('utf-8', 'replace')}"
    except Exception as e:          # timeout, connection
        return None, time.monotonic() - t, f"{type(e).__name__}: {str(e)[:120]}"


def ask(model, item, timeout=30.0):
    """item: text, images (JPEG bytes), questions {name: {"type": "noul"|"choice", "instructions", "criteria"}}.
    -> {"answers": {name: {"value": bool|str, "p": float|None}}, "latency_s", "error"}"""
    qs = item["questions"]
    if model == "d1":
        parts = [{"type": "text", "text": item["text"]}] + [
            {"type": "image", "data": base64.b64encode(j).decode(), "mime_type": "image/jpeg"} for j in item["images"]]
        out, dt, err = post("/decisions", {"model": "gemini-decision-1", "input": parts, "questions": qs}, timeout)
        ans = {}
        if not err:
            for n, q in qs.items():
                a = (out.get("answers") or {}).get(n) or {}
                if q["type"] == "noul" and "noul" in a:
                    ans[n] = {"value": a["noul"] >= 0.5, "p": a["noul"]}
                elif q["type"] == "choice" and "choice" in a:
                    ans[n] = {"value": a["choice"], "p": a.get("confidence")}
        return {"answers": ans, "latency_s": round(dt, 2), "error": err}
    props, lines = {}, []
    for n, q in qs.items():
        if q["type"] == "noul":
            props[n] = {"type": "BOOLEAN"}
            lines.append(f"- {n} (true/false): {q['instructions']}")
        else:
            props[n] = {"type": "STRING", "enum": list(q["criteria"])}
            lines.append(f"- {n}: {q['instructions']} Options: " + "; ".join(f"{k} = {v}" for k, v in q["criteria"].items()))
    text = item["text"] + "\nAnswer these questions as JSON:\n" + "\n".join(lines)
    parts = [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(j).decode()}} for j in item["images"]]
    body = {"contents": [{"role": "user", "parts": parts + [{"text": text}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                                 "responseSchema": {"type": "OBJECT", "properties": props, "required": list(props)},
                                 "thinkingConfig": {"thinkingBudget": 0}}}
    out, dt, err = post(f"/models/{GEN[model]}:generateContent", body, timeout)
    ans = {}
    if not err:
        try:
            txt = "".join(p.get("text", "") for p in out["candidates"][0]["content"]["parts"] if not p.get("thought"))
            ans = {n: {"value": v, "p": None} for n, v in json.loads(txt).items() if n in qs}
        except Exception as e:
            err = f"parse {e!r}"
    return {"answers": ans, "latency_s": round(dt, 2), "error": err}


# ---------------------------------------------------------------------------------------------- frames + truth
SCALE = 1.0          # --scale: shrink the images before sending (smaller upload, lower latency)


def jpeg(rgb, q=85):
    import cv2
    rgb = np.asarray(rgb)
    if SCALE != 1.0:
        rgb = cv2.resize(rgb, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, q])
    return buf.tobytes()


def bin_of(p):
    for b, (cx, cy) in BINS.items():
        if abs(p[0] - cx) < 0.102 and abs(p[1] - cy) < 0.102:
            return b
    return None


def tilt_deg(q):
    x, y, _, _ = q
    return float(np.degrees(np.arccos(np.clip(1 - 2 * (x * x + y * y), -1, 1))))


def load_frames(frames_dir, run, picks, scene_yaml=None):
    cam_cls = scene = cal = None
    if scene_yaml:      # the geometric rule to compare with: camera.py on the same frames (needs aaltonomous on PYTHONPATH)
        from aaltonomous.interface.calibration import Calibration
        from aaltonomous.scene.scene import Scene
        from camera import CameraPerception as cam_cls
        scene, cal = Scene.load(scene_yaml), Calibration.load()
    ev = json.load(open(os.path.join(run, "eval.json")))["trials"]
    lay = {ep: sorted((o["color"], o["shape"], round(o["x"], 3)) for o in t["layout"]) for ep, t in enumerate(ev)}
    F = []
    for f in sorted(glob.glob(os.path.join(frames_dir, "f_*.npz"))):
        z = np.load(f)
        st = json.loads(str(z["state"]))
        l = sorted((o["color"], o["shape"], round(o["x"], 3)) for o in st["layout"])
        ep = next((e for e, v in lay.items() if v == l), None)
        objs = {}
        for o in st["objects"]:
            if not o["active"]:
                continue
            p, b = o["pos"], bin_of(o["pos"])
            where = ("bin:" + b) if (b and p[2] < 0.085) else ("air" if p[2] > 0.05 else ("counter" if p[2] > -0.04 else "off"))
            lying = o["shape"] != "cube" and where == "counter" and 45 < tilt_deg(o["quat_xyzw"]) < 135
            objs[o["name"]] = dict(name=o["name"], color=o["color"], shape=o["shape"], pos=p, where=where, lying=lying)
        F.append(dict(file=f, ts=int(os.path.basename(f)[2:-4]), ep=ep, objs=objs, t=None, pick=None, rgb=z["rgb"], cam=None))
        if cam_cls is not None and ep is not None:
            dets = cam_cls(scene, cal).detect(z["rgb"], z["depth"])
            F[-1]["cam"] = {"n": len(dets), "lying": any(getattr(d, "tipped", False) for d in dets)}
    # time inside the episode: the offset that best matches "an object is in the air" with "fingers hold something"
    for ep in sorted({f["ep"] for f in F if f["ep"] is not None}):
        z = np.load(os.path.join(run, f"episode_{ep:03d}.npz"))
        t, wall = z["t"], z["wall"]
        held = np.zeros(len(t), bool)       # fingers closed for >= 1.5 s and stalled on something
        for p in picks:
            if p["ep"] == ep and p["t_close"] is not None:
                i0 = np.searchsorted(t, p["t0"])
                held[i0:i0 + len(p["err"])] = p["closed"] & (p["err"] > R.HELD_RAD) & (p["tt"] >= p["t_close"] + 1.5)
        fr = [f for f in F if f["ep"] == ep]
        ts = np.array([f["ts"] for f in fr], float)
        air = np.array([any(o["where"] == "air" for o in f["objs"].values()) for f in fr])

        def score(o):
            w = ts - o
            i = np.clip(np.searchsorted(wall, w), 0, len(t) - 1)
            return int(((held[i] == air) & (w >= -1) & (w <= wall[-1] + 1)).sum())
        # the episode file is written when the episode ends, so with file times preserved (scp -p) the offset is
        # known to about 1 s; refine it within +-1.5 s. Without usable file times: search the whole range.
        om = os.path.getmtime(os.path.join(run, f"episode_{ep:03d}.npz")) - wall[-1]
        lo, hi = ts.max() - wall[-1] - 5, ts.min() + 5
        how = "file time" if lo <= om <= hi else "search"
        grid = np.arange(om - 1.5, om + 1.5, 0.1) if how == "file time" else np.arange(lo, hi, 0.1)
        sc = np.array([score(o) for o in grid])
        o = float(np.median(grid[sc == sc.max()]))
        best = int(sc.max())
        home = z["arm_q"][0]
        for f in fr:
            i = int(np.clip(np.searchsorted(wall, f["ts"] - o), 0, len(t) - 1))
            f["t"] = float(t[i])
            f["arm_home"] = bool(np.abs(z["arm_q"][i] - home).max() < 0.15)
            f["pick"] = next((p for p in picks if p["ep"] == ep and p["t0"] <= f["t"] < p["t1"]), None)
        print(f"episode {ep}: {len(fr)} frames, time offset from {how} matches {best}/{len(fr)} frames")
    return [f for f in F if f["t"] is not None]


def target(f, p):
    return f["objs"].get(p["obj"])


def nice(o):
    return f"{WORD[o['color']]} {'triangular prism' if o['shape'] in ('triangle', 'tipped') else o['shape']}"


# ---------------------------------------------------------------------------------------------- roles -> items
def items_grasp(F, variant="noul"):
    """Hand closed for >= 1.5 s: is the block in the hand?  truth: the target object is off the table.
    variant: "noul" one image, yes/no; "choice" one image, two described answers; "pair" image before the pick + now."""
    out = []
    for f in F:
        p = f["pick"]
        if not p or p["t_close"] is None or not (p["t_close"] + 1.5 <= f["t"] <= p["t_open"]):
            continue
        o = target(f, p)
        q = {"held": {"type": "noul", "instructions":
                      f"Is the {nice(o)} held in the robot's {p['arm']} hand right now (lifted off the table, between the fingers)?"}}
        txt = SCENE + (f"The robot's {p['arm']} hand has just closed its fingers to grasp a {nice(o)} and is lifting it "
                       "or carrying it towards a bin. Sometimes the grasp misses and the hand is empty while the block "
                       "stays on the table.")
        i = int(np.searchsorted(p["tt"], f["t"]))
        imgs = [jpeg(f["rgb"])]
        if variant == "choice":
            q = {"held": {"type": "choice", "instructions": f"What is in the robot's closed {p['arm']} hand?", "criteria": {
                "block": f"A {nice(o)} is between the fingers of the {p['arm']} hand, lifted off the table.",
                "empty": f"The {p['arm']} hand is closed on nothing; the {nice(o)} is still standing or lying on the table."}}}
        if variant == "pair":
            b = [g for g in F if g["ep"] == f["ep"] and p["t0"] - 3 <= g["t"] <= p["t0"] + 1.0]
            if not b:
                continue
            imgs = [jpeg(b[-1]["rgb"]), imgs[0]]
            txt = SCENE.replace("The image is", "Both images are from") + (
                f"First image: before the pick. Second image: now, after the robot's {p['arm']} hand closed its fingers "
                f"to grasp a {nice(o)} and started to lift or carry it. Sometimes the grasp misses: then the block is "
                "still on the table in the second image.")
            q = {"held": {"type": "noul", "instructions":
                          f"In the second image, is the {nice(o)} off the table and in the robot's {p['arm']} hand?"}}
        out.append(dict(id=f"{f['ts']}", text=txt, images=imgs, questions=q,
                        truth={"held": ("block" if o["where"] == "air" else "empty") if variant == "choice" else o["where"] == "air"},
                        tags={"shape": o["shape"], "pick_ok": p["ok"]},
                        rule={"held": bool(p["err"][min(i, len(p["err"]) - 1)] > R.HELD_RAD)} if variant != "choice" else {}))
    return out


def items_place(F, pair=False):
    """Hand open again after the carry: where is the block?  truth: bin / table from the true pose.
    pair: image before the pick + image now, one question "is it gone from the table?"."""
    out = []
    crit = {"left": "Inside the left bin.", "center": "Inside the center bin.", "right": "Inside the right bin.",
            "table": "On the table, outside the bins.", "hand": "Still in the robot's hand."}
    for f in F:
        p = f["pick"]
        if not p or p["t_open"] is None or f["t"] < p["t_open"] + 1.0:
            continue
        o = target(f, p)
        same = sum(1 for x in f["objs"].values() if (x["color"], x["shape"]) == (o["color"], o["shape"]))
        txt = SCENE + (f"The robot's {p['arm']} hand has just tried to pick up a {nice(o)} from the table and drop it "
                       f"into the {p['bin']} bin. The hand has opened again.")
        q = {"in_bin": {"type": "noul", "instructions": f"Is that {nice(o)} now inside the {p['bin']} bin?"},
             "where": {"type": "choice", "instructions": f"Where is that {nice(o)} now?", "criteria": crit}}
        w = o["where"].replace("bin:", "").replace("counter", "table").replace("air", "hand")
        i = np.where(p["closed"])[0]
        imgs, truth = [jpeg(f["rgb"])], {"in_bin": o["where"] == f"bin:{p['bin']}", "where": w}
        if pair:
            b = [g for g in F if g["ep"] == f["ep"] and p["t0"] - 3 <= g["t"] <= p["t0"] + 1.0]
            if not b:
                continue
            imgs = [jpeg(b[-1]["rgb"]), imgs[0]]
            txt = SCENE.replace("The image is", "Both images are from") + (
                f"First image: before the robot's {p['arm']} hand tried to pick up a {nice(o)} from the table and drop it "
                f"into the {p['bin']} bin. Second image: after the attempt, the hand has opened again. A failed attempt "
                "leaves the block on the table, at the same place or pushed a few centimetres.")
            q = {"in_bin": {"type": "noul", "instructions":
                            f"Is that {nice(o)} gone from the table in the second image (so it was moved into a bin)?"}}
            truth = {"in_bin": truth["in_bin"]}
        out.append(dict(id=f"{f['ts']}", text=txt, images=imgs, questions=q, truth=truth,
                        tags={"twin": same > 1, "arm_home": f["arm_home"]},
                        rule={"in_bin": bool(p["err"][i[-1] - 3] > R.HELD_RAD)}))       # held until the release
    return out


def items_census(F):
    """How many blocks are in each bin / on the table?  truth: counts from the true poses."""
    out = []
    crit = {str(k): f"{k} blocks." for k in range(4)}
    crit["4"] = "4 or more blocks."
    for f in F:
        cnt = collections.Counter(o["where"] for o in f["objs"].values())
        q = {b: {"type": "choice", "instructions": f"How many blocks lie inside the {b} bin?", "criteria": crit}
             for b in BINS}
        q["table"] = {"type": "choice", "criteria": crit, "instructions":
                      "How many blocks are on the table outside the bins (do not count a block held in a hand)?"}
        truth = {b: str(min(4, cnt[f"bin:{b}"])) for b in BINS}
        truth["table"] = str(min(4, cnt["counter"]))
        out.append(dict(id=f"{f['ts']}", text=SCENE, images=[jpeg(f["rgb"])], questions=q, truth=truth,
                        tags={"arm_home": f["arm_home"]}, rule={"table": str(min(4, f["cam"]["n"]))} if f["cam"] else {}))
    return out


def items_sanity(F):
    """Is a block on the table lying on its side?  truth: a cylinder or prism on the table tilted 45-135 degrees."""
    out = []
    for f in F:
        q = {"lying": {"type": "noul", "instructions":
                       "Is at least one block on the table (outside the bins, not in a hand) lying on its side, i.e. "
                       "tipped over: a cylinder resting on its curved side or a triangular prism resting on a "
                       "rectangular side instead of standing on its flat end?"}}
        out.append(dict(id=f"{f['ts']}", text=SCENE, images=[jpeg(f["rgb"])], questions=q,
                        truth={"lying": any(o["lying"] for o in f["objs"].values())},
                        tags={"arm_home": f["arm_home"]}, rule={"lying": f["cam"]["lying"]} if f["cam"] else {}))
    return out


def items_diagnose(F, picks):
    """Before / after image of one pick: what happened to the block, and was another block disturbed?"""
    out = []
    crit = {"in_bin": "It is gone from the table: it is in a bin now.",
            "same": "Still on the table at the same place, same pose (the hand missed it).",
            "pushed": "Still on the table, standing as before, but pushed to a different place.",
            "tipped": "Still on the table but it fell over / now lies on its side."}
    for p in picks:
        fr = [f for f in F if f["ep"] == p["ep"]]
        before = [f for f in fr if p["t0"] - 3 <= f["t"] <= p["t0"] + 1.0]
        after = [f for f in fr if p["t1"] - 1.0 <= f["t"] <= p["t1"] + 1.0]
        if not before or not after or p["ok"] is None:
            continue
        b, a = before[-1], min(after, key=lambda f: abs(f["t"] - p["t1"]))
        ob, oa = target(b, p), target(a, p)
        d = float(np.hypot(oa["pos"][0] - ob["pos"][0], oa["pos"][1] - ob["pos"][1]))
        what = "in_bin" if oa["where"].startswith("bin") else ("tipped" if oa["lying"] and not ob["lying"] else
                                                               ("pushed" if d > 0.01 else "same"))
        other = False
        for n, x in b["objs"].items():
            y = a["objs"][n]
            if n != p["obj"] and x["where"] == "counter":
                other |= (np.hypot(y["pos"][0] - x["pos"][0], y["pos"][1] - x["pos"][1]) > 0.01) or (y["lying"] != x["lying"])
        txt = SCENE + (f"Two images: the first was taken just before the robot's {p['arm']} hand tried to pick up a "
                       f"{nice(ob)} and carry it to the {p['bin']} bin, the second just after the attempt.")
        q = {"what": {"type": "choice", "instructions": f"What happened to that {nice(ob)}?", "criteria": crit},
             "other": {"type": "noul", "instructions":
                       "Did any OTHER block on the table move or fall over between the two images?"}}
        out.append(dict(id=p["dec"], text=txt, images=[jpeg(b["rgb"]), jpeg(a["rgb"])], questions=q,
                        truth={"what": what, "other": bool(other)}, tags={"moved_cm": round(d * 100, 1)}, rule={}))
    return out


EXPERIENCE = ("Experience from earlier runs of this robot (picks that ended in the bin): cube with a face grasp 5 of 5, "
              "cube with the stock claw 4 of 7, cylinder with the stock claw 18 of 27, triangular prism with a face "
              "grasp 1 of 1, triangular prism with the stock claw 1 of 15. A failed pick usually leaves the block on "
              "the table, pushed 1-3 cm.\n")
GRASP = {"face": "fingers on one flat side face, thumb on the opposite face",
         "face_alt": "fingers on a side face, turned 15-30 degrees towards the apex",
         "stock": "generic claw from above, not aligned to the block's faces"}


def items_critique(picks, F, experience):
    """Before a pick runs: will it end in the bin?  text only (what the planner knows) + the look image when saved."""
    out = []
    for p in picks:
        if p["ok"] is None:
            continue
        hist = "".join(f" Attempt {k + 1}: {a} arm, {g} grasp, {'ended in the bin' if ok else 'failed, block still on the table'}."
                       for k, (a, g, ok) in enumerate(p["before"]))
        o = {"color": p["color"], "shape": p["shape"]}
        txt = ("A humanoid robot with two arms and three-finger hands sorts small blocks (4.5 cm cubes, cylinders, "
               "triangular prisms) from a table into bins. A motion planner has checked that the next pick is reachable "
               "and collision-free.\n" + (EXPERIENCE if experience else "") +
               f"Next pick: the {nice(o)}{' (it lies on its side)' if p['shape'] == 'tipped' else ''}, with the {p['arm']} arm, "
               f"grasp: {GRASP[p['kind']]}; it goes to the {p['bin']} bin."
               + (f" Earlier attempts on this block in this episode:{hist}" if hist else " This is the first attempt on this block."))
        img = []
        if F is not None:
            fr = [f for f in F if f["ep"] == p["ep"] and p["t0"] - 3 <= f["t"] <= p["t0"] + 1.0]
            if not fr:
                continue
            img = [jpeg(fr[-1]["rgb"])]
            txt += " The image is the robot's head camera just before the pick."
        q = {"ok": {"type": "noul", "instructions": "Will this pick end with the block resting inside its bin?"}}
        fails = {b[:2] for b in p["before"] if not b[2]}
        out.append(dict(id=p["run"][:14] + p["dec"], text=txt, images=img, questions=q, truth={"ok": bool(p["ok"])},
                        tags={"run": p["run"]},
                        rule={"ok": not ((p["shape"] in ("triangle", "tipped") and p["kind"] == "stock")
                                         or (p["arm"], p["kind"]) in fails)}))
    return out


# ---------------------------------------------------------------------------------------------- run + report
def key(role, m, it):
    import hashlib
    h = hashlib.md5((it["text"] + json.dumps(it["questions"], sort_keys=True)).encode()).hexdigest()[:8]
    return f"{role}|{m}|{it['id']}|{h}" + ("" if SCALE == 1.0 else f"|s{SCALE}")


def run_role(role, items, models, cache, lock, out_path, workers):
    for m in models:
        todo = [it for it in items if key(role, m, it) not in cache]

        def one(it):
            r = ask(m, it)
            if r["error"] and ("429" in r["error"] or "http 5" in r["error"]):
                time.sleep(3)
                r = ask(m, it)
            with lock:
                cache[key(role, m, it)] = r
        if todo:
            with ThreadPoolExecutor(workers if m != "d1" else 1) as ex:      # Decision 1 one at a time: honest latency
                list(ex.map(one, todo))
            with lock:
                json.dump(cache, open(out_path, "w"))


def report(role, items, models, cache):
    print(f"\n## {role}: {len(items)} items")
    for q in items[0]["questions"]:
        truth = [it["truth"][q] for it in items]
        c = collections.Counter(str(t) for t in truth)
        print(f"question '{q}': truth {dict(c)}")
        if items[0]["rule"].get(q) is not None:
            line = f"   {'rule':9s} right {sum(it['rule'][q] == it['truth'][q] for it in items)}/{len(items)}"
            if "arm_home" in items[0]["tags"]:
                h = [it for it in items if it["tags"]["arm_home"]]
                line += f"; arms at home: {sum(it['rule'][q] == it['truth'][q] for it in h)}/{len(h)}"
            print(line)
        for m in models:
            rs = [cache.get(key(role, m, it)) for it in items]
            got = [(it, r["answers"][q]) for it, r in zip(items, rs) if r and q in r["answers"]]
            lat = sorted(r["latency_s"] for r in rs if r and not r["error"])
            errs = sum(1 for r in rs if r is None or r["error"] or q not in r["answers"])
            right = sum(a["value"] == it["truth"][q] for it, a in got)
            line = f"   {m:9s} right {right}/{len(got)}"
            if isinstance(truth[0], bool):
                tp = sum(a["value"] and it["truth"][q] for it, a in got)
                fp = sum(a["value"] and not it["truth"][q] for it, a in got)
                fn = sum((not a["value"]) and it["truth"][q] for it, a in got)
                tn = len(got) - tp - fp - fn
                line += f" (yes+true {tp}, yes+false {fp}, no+true {fn}, no+false {tn})"
                ps = [(a["p"], it["truth"][q]) for it, a in got if a["p"] is not None]
                if ps:
                    line += (f" mean p when true {np.mean([p for p, t in ps if t] or [np.nan]):.2f}, when false "
                             f"{np.mean([p for p, t in ps if not t] or [np.nan]):.2f}")
            if lat:
                line += f"; latency median {lat[len(lat) // 2]:.2f} s, max {lat[-1]:.2f} s"
            line += f"; no answer {errs}"
            print(line)
            for tag in items[0]["tags"]:
                c = collections.defaultdict(lambda: [0, 0])
                for it, a in got:
                    c[str(it["tags"][tag])][1] += 1
                    c[str(it["tags"][tag])][0] += a["value"] == it["truth"][q]
                if 1 < len(c) <= 6:
                    print(f"        by {tag}: " + ", ".join(f"{k}: {v[0]}/{v[1]}" for k, v in sorted(c.items())))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--run", required=True, help="run folder the frames were captured in")
    ap.add_argument("--log", required=True, help="its decisions.jsonl")
    ap.add_argument("--more", nargs="*", default=[], help="more RUN_DIR=decisions.jsonl pairs (critique only)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--roles", default="grasp,place,census,sanity,diagnose,critique")
    ap.add_argument("--models", default="d1,er,hydrogen")
    ap.add_argument("--env-file")
    ap.add_argument("--scene", help="scene yaml: also run camera.py on every frame as the rule to compare with")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dump", help="folder for the test images (to look at them)")
    ap.add_argument("--scale", type=float, default=1.0, help="image scale, e.g. 0.5 = 320 x 240")
    a = ap.parse_args()
    global SCALE
    SCALE = a.scale
    api_key(a.env_file)
    picks = R.load([(a.run, a.log)])
    allp = picks + R.load([x.split("=", 1) for x in a.more])
    F = load_frames(a.frames, a.run, picks, a.scene)
    cache = json.load(open(a.out)) if os.path.exists(a.out) else {}
    lock, models = threading.Lock(), a.models.split(",")
    sets = {"grasp": lambda: items_grasp(F), "grasp_choice": lambda: items_grasp(F, "choice"),
            "grasp_pair": lambda: items_grasp(F, "pair"), "place": lambda: items_place(F), "place_pair": lambda: items_place(F, True), "census": lambda: items_census(F),
            "sanity": lambda: items_sanity(F), "diagnose": lambda: items_diagnose(F, picks),
            "critique": lambda: items_critique(allp, None, False),
            "critique_exp": lambda: items_critique(allp, None, True),
            "critique_img": lambda: items_critique(picks, F, False)}
    for role in a.roles.split(","):
        items = sets[role]()
        if a.dump:
            os.makedirs(a.dump, exist_ok=True)
            for it in items:
                for k, j in enumerate(it["images"]):
                    open(os.path.join(a.dump, f"{role}_{it['id']}_{k}.jpg"), "wb").write(j)
        run_role(role, items, models, cache, lock, a.out, a.workers)
        report(role, items, models, cache)


if __name__ == "__main__":
    main()
