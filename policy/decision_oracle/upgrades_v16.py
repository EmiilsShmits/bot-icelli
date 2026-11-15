"""v1.6 upgrades on top of v1.5 (upgrades_v15.py; nothing there changes): Gemini Decision 1 names colour and shape and
reads the instruction, v1.5's HSV colour, depth shape and rule parser stay as the offline fallback.

1. AnyColourCamera (RidgeCamera + leftover blobs). v1.5 finds an object only if its pixels fall in a fixed HSV range
   (camera.HSV); a real block outside every range is never seen. Here a second pass on the same "object height, on
   the mat, outside the bins" mask keeps saturated pixels (S >= LEFT_S, V >= LEFT_V: the grey arms and black hands
   stay out) that no HSV class took, and runs them through the same top-face / height / size filters. A leftover
   blob has colour None until Decision names it (labels_v16.CropLabelerV16); without a colour it is dropped. So the
   pass can only add objects, and only with a key: without one it is off and the camera is v1.5's.
   Every detection also keeps its top-face points (`top_xy`) so the yaw can be re-fitted when Decision changes the
   shape.
2. CropLabelerV16 (labels_v16.py): Decision colour + shape, "tipped" from the depth geometry always stands.
3. Instruction (policy/instruction_d1.py): one Decision call started at reset(); the first look takes its answer
   (deadline 2.5 s after reset) if every slot is confident, else the rule parser's mapping stays.

Classes: AnyColourCamera, V16OraclePolicy.
"""
from __future__ import annotations

import os

import numpy as np

from aaltonomous.baselines.classical.perception import Detection
from aaltonomous.interface.tasks import FIXED_INSTRUCTION

from . import camera as CAMMOD
from .camera import CameraPerception, _points
from .upgrades_v15 import RidgeCamera, V15OraclePolicy, _ridge_shift, classify_top_v15

LEFT_S, LEFT_V = 40, 50   # leftover pass: minimum HSV saturation / value (OpenCV 0-255)
LEFT_GAP_PX = 5           # leftover pixels must be this far from any HSV-class pixel
LEFT_DUP_M = 0.035        # a leftover blob this close to an HSV detection is the same object: dropped
# red + yellow halves of one block (warm merge). The venue orange's lit top face renders at hue 16-21 in the sim while
# its side is 14-16, so v1.5's ranges (red <= 17, yellow >= 18) split one block in two: a thin red crescent (its "top
# face" too narrow -> called lying) and a phantom yellow top. Real head frames: orange blocks' median hue 10-14,
# yellow 19-49, so the boundary itself stays; only a blob that is one block's size and holds both colours is merged.
MERGE_FRAC = 0.10         # each colour at least this share of the blob's red + yellow pixels
MERGE_LONG_MM = 70.0      # merged top face no longer than this (one 4.5 cm block: a cube's diagonal is 64 mm)
MERGE_NEAR_M = 0.03       # red / yellow detections this close to the merged centre are its halves: replaced
MERGE_RED_SHARE = 0.30    # merged blob -> red if at least this share of its red + yellow pixels is red, else yellow.
                          # Real crops: orange 0.94-1.0, yellow 0.00-0.15; sim merges (all orange) 0.49-0.90. The
                          # median hue sat on the boundary (17 / 18) and flipped between looks (e-054 seed 1000).


def _key(c):
    return (round(float(c[0]), 6), round(float(c[1]), 6))


class AnyColourCamera(RidgeCamera):
    leftovers = True       # V16OraclePolicy turns it off when there is no Decision labeler
    merge_warm = True      # V16_MERGE_WARM=off: v1.5's separate red / yellow blobs

    def _detect(self, rgb, depth):
        tops = {}

        def shape_and_points(xy):              # classify_top_v15, keeping the top-face points of each blob
            r = classify_top_v15(xy)
            if r[2] is not None:
                tops[_key(r[2])] = np.asarray(xy, float)
            return r

        saved = CAMMOD.classify_top
        CAMMOD.classify_top = shape_and_points
        try:
            dets, rej = CameraPerception._detect(self, rgb, depth)       # = RidgeCamera's HSV pass
            for d in dets:
                d.hsv_color = d.color
                d.top_xy = tops.get(_key(d.top[:2]))
            if self.merge_warm:
                dets = self._merge_warm(rgb, depth, dets, shape_and_points, tops, rej)
            if self.leftovers:
                extra = self._leftovers(rgb, depth, dets, shape_and_points, tops, rej)
                dets += extra
        finally:
            CAMMOD.classify_top = saved
        return dets, rej

    def _geom(self, depth):
        """Pelvis-frame points (h, w, 3) and the "object height, on the mat, outside the bins" mask (bool)."""
        sc = self.scene
        T = self.cal.cams[CAMMOD.CAM].T_pelvis_optical
        P = _points(self.cal, depth) @ T[:3, :3].T.astype(np.float32) + T[:3, 3].astype(np.float32)
        h = (P[..., 2] - sc.counter_z) / self.H
        pm = (P[..., :2] - sc.origin[:2].astype(np.float32))[..., ::-1]
        W, D = sc.cfg["counter"]["mat_size"]
        ok = (depth > 150) & (depth < 2000) & (h > 0.3) & (h < 1.5)
        ok &= (pm[..., 0] > -0.02) & (pm[..., 0] < W + 0.02) & (pm[..., 1] > -0.02) & (pm[..., 1] < D + 0.02)
        half = np.asarray(sc.cfg["bins"]["outer_size"], float) / 2 + 0.006
        for ctr in sc.cfg["bins"]["centers"].values():
            ok &= ~((np.abs(pm[..., 0] - ctr[0]) <= half[0]) & (np.abs(pm[..., 1] - ctr[1]) <= half[1]))
        return P, ok

    def _blob(self, P, v, u, classify, rejected, why):
        """Same top-face / height / size filters as the HSV pass for one pixel set -> (shape, yaw, centre, feat,
        z_top, n_top) or None."""
        sc = self.scene
        p = P[v, u]
        z_top = np.percentile(p[:, 2], 92)
        sel = p[:, 2] >= z_top - 0.006
        top = p[sel]
        shape, yaw, centre, feat = classify(top[:, :2])
        if centre is None:
            rejected.append((None, f"{why}: too few top points", len(v)))
            return None
        ht = (float(np.median(top[:, 2])) - sc.counter_z) / self.H
        if not 0.6 <= ht <= 1.4:
            rejected.append((None, f"{why}: top at {ht:.2f} object heights", len(v)))
            return None
        return shape, yaw, centre, feat, float(np.median(top[:, 2])), int(sel.sum())

    def _merge_warm(self, rgb, depth, dets, classify, tops, rejected):
        """One block-sized blob at object height holding both red and yellow pixels is one object: its top face from
        all of them, its colour from the share of red pixels (MERGE_RED_SHARE). Replaces the red / yellow detections it was split into."""
        import cv2
        sc = self.scene
        P, ok = self._geom(depth)
        ok = ok.astype(np.uint8) * 255
        hsv = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2HSV)
        k3 = np.ones((3, 3), np.uint8)
        masks = {}
        for c in ("red", "yellow"):
            m = np.zeros(hsv.shape[:2], np.uint8)
            for lo, hi in self.hsv.get(c, []):
                m |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
            masks[c] = cv2.morphologyEx(m & ok, cv2.MORPH_OPEN, k3)
        warm = cv2.morphologyEx(masks["red"] | masks["yellow"], cv2.MORPH_CLOSE, k3)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(warm, connectivity=8)
        out = list(dets)
        for i in range(1, n):
            area = int(stats[i, cv2.CC_STAT_AREA])
            if area < 150:
                continue
            comp = lab == i
            nr, ny = int((comp & (masks["red"] > 0)).sum()), int((comp & (masks["yellow"] > 0)).sum())
            if min(nr, ny) < MERGE_FRAC * (nr + ny):
                continue                                      # one colour: the HSV pass already has it right
            v, u = np.nonzero(comp)
            b = self._blob(P, v, u, classify, rejected, "warm merge")
            if b is None:
                continue
            shape, yaw, centre, feat, z_top, n_top = b
            if feat["long_mm"] > MERGE_LONG_MM or feat["area_mm2"] < 250:
                continue                                      # two blocks touching in the image: keep them apart
            halves = [d for d in out if d.color in ("red", "yellow") and not getattr(d, "leftover", False)
                      and np.linalg.norm(d.top[:2] - centre) < MERGE_NEAR_M]
            if not halves:
                continue
            hue = hsv[v, u, 0].astype(float)
            hue = np.where(hue >= 150, hue - 180.0, hue)
            col = "red" if nr >= MERGE_RED_SHARE * (nr + ny) else "yellow"
            d = Detection(col, np.array([centre[0], centre[1], sc.counter_z + self.H]), area, n_top, "camera", yaw,
                          (float(np.median(u)), float(np.median(v))))
            d.shape, d.tipped, d.feat, d.z_top = shape, shape == "tipped", feat, z_top
            d.bbox = (int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                      int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT]))
            d.hsv_color, d.top_xy = col, tops.get(_key(centre))
            d.merged = {"from": [f"{h.color}:{h.shape}" for h in halves], "hue": round(float(np.median(hue)), 1),
                        "red_px": nr, "yellow_px": ny}
            out = [x for x in out if not any(x is h for h in halves)] + [d]
        return out

    def _leftovers(self, rgb, depth, dets, classify, tops, rejected):
        import cv2
        sc = self.scene
        P, ok = self._geom(depth)
        hsv = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2HSV)
        known = np.zeros(hsv.shape[:2], np.uint8)
        for ranges in self.hsv.values():
            for lo, hi in ranges:
                known |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
        known = cv2.dilate(known, np.ones((2 * LEFT_GAP_PX + 1,) * 2, np.uint8))
        m = ((hsv[..., 1] >= LEFT_S) & (hsv[..., 2] >= LEFT_V) & ok & (known == 0)).astype(np.uint8) * 255
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        out = []
        for i in range(1, n):
            area = int(stats[i, cv2.CC_STAT_AREA])
            if area < 150:
                continue
            v, u = np.nonzero(lab == i)
            p = P[v, u]
            z_top = np.percentile(p[:, 2], 92)
            sel = p[:, 2] >= z_top - 0.006
            top = p[sel]
            shape, yaw, centre, feat = classify(top[:, :2])
            if centre is None:
                rejected.append((None, "leftover: too few top points", area))
                continue
            ht = (float(np.median(top[:, 2])) - sc.counter_z) / self.H
            if not 0.6 <= ht <= 1.4:
                rejected.append((None, f"leftover: top at {ht:.2f} object heights", area))
                continue
            if feat["long_mm"] > 95 or feat["area_mm2"] < 250:
                rejected.append((None, f"leftover: size {feat['long_mm']:.0f} mm / {feat['area_mm2']:.0f} mm2", area))
                continue
            if any(np.linalg.norm(d.top[:2] - centre) < LEFT_DUP_M for d in dets + out):
                continue
            d = Detection(None, np.array([centre[0], centre[1], sc.counter_z + self.H]), area, int(sel.sum()),
                          "camera", yaw, (float(np.median(u)), float(np.median(v))))
            d.shape, d.tipped, d.feat = shape, shape == "tipped", feat
            d.bbox = (int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                      int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT]))
            d.z_top = float(np.median(top[:, 2]))
            d.hsv_color, d.leftover, d.top_xy = None, True, tops.get(_key(centre))
            out.append(d)
        return out


class V16OraclePolicy(V15OraclePolicy):
    def __init__(self, client, labels="fuse", instruction="d1", **kw):
        """labels: "fuse" (Decision colour + shape, labels_v16) | "log" (record only) | "off" (= v1.5 perception).
        instruction: "d1" (Decision first, rule parser fallback) | "rules" (= v1.5).
        Other arguments: V15OraclePolicy (sides, tip_check stays off here, ...)."""
        kw.pop("tip_check", None)
        from .near_v16 import NearEnumerator, V16Chooser, near_mode
        kw.setdefault("chooser", V16Chooser())
        super().__init__(client, tip_check="off", **kw)
        self.near = near_mode()                 # V16_NEAR: off | relay | push (triangles close to the body)
        self.enum = NearEnumerator(self, self.lib, self.near)   # with "off" = MemoryEnumerator + the planners' dets
        from .crowd_v16 import CrowdPlanner, crowd_on
        for pl in (self.planner, self.relay):  # grasps that keep the fingers off other objects (V16_CROWD)
            pl.__class__ = CrowdPlanner
            pl.crowd = crowd_on()
        # lying-prism grasp fix (v1.5 keeps its old grasp): hand 18 mm further along the ridge, so the closed thumb
        # reaches the near end face (ridge sweep, eval/RESULTS.md); and a ridge plan on either arm before the stock claw
        shift = _ridge_shift(os.environ.get("V16_RIDGE_SHIFT", "18,0"))
        first = os.environ.get("V16_RIDGE_FIRST", "on").lower() not in ("0", "off", "false", "no")
        for pl in (self.planner, self.relay):
            pl.ridge_shift, pl.ridge_first = shift, first
        self.labels_mode, self.instr, self._instr_pending = labels, None, False
        self.labeler = None
        if self.cam is not None:
            self.cam = AnyColourCamera(self.scene, self.cal, log=self.log)
            if labels != "off":
                try:
                    from .labels_v16 import CropLabelerV16
                    self.labeler = CropLabelerV16(mode=labels)
                except Exception as e:          # no key: v1.5 perception
                    self.log(f"[v1.6] crop labels off: {e}")
            self.cam.leftovers = self.labeler is not None
            self.cam.merge_warm = os.environ.get("V16_MERGE_WARM", "on").lower() not in ("0", "off", "false", "no")
            # V16_BOXES: "off" | "find" (after the camera fit, measure the three boxes from depth and drop into them
            # where they really stand, boxes_v16.py) | "lid" (also look for the shape lid and its holes: cam.lid)
            from . import boxes_v16
            if boxes_v16.mode() != "off":
                boxes_v16.enable(self.cam, lid=boxes_v16.mode() == "lid")
        if instruction == "d1":
            from instruction_d1 import DecisionInstruction
            self.instr = DecisionInstruction()
            if not self.instr.enabled:
                self.log("[v1.6] instruction: no key, rule parser only")

    def reset(self, info=None):
        super().reset(info)
        if hasattr(getattr(self, "enum", None), "pushed"):
            self.enum.reset()
        self._instr_pending = False
        if getattr(self, "instr", None) is not None and info is not None:
            inst = (info.get("instruction") if isinstance(info, dict) else info) or ""
            if inst.strip() and inst.strip() != FIXED_INSTRUCTION:    # the fixed instruction maps exactly already
                self.instr.start(inst)
                self._instr_pending = True

    def _commit(self, p):
        super()._commit(p)
        if getattr(p, "push_xy", None) is not None and hasattr(getattr(self, "enum", None), "pushed"):
            self.enum.pushed.append(np.asarray(p.push_xy, float))

    def _detections(self, fresh):
        dets = super()._detections(fresh)
        if self._instr_pending:                 # first look: the Decision answer has had the camera wait to arrive
            self._instr_pending = False
            self._apply_instruction()
        return dets

    def _w(self, rec):
        """The decision log, with (colour, shape) mapping keys as "colour shape" strings: json.dumps refuses tuple keys,
        so a shape instruction ("triangles go left") would raise in reset() / the first look whenever V15_DLOG is set."""
        super()._w(_jsonable(rec))

    def _log_perception(self, dets):
        """v1.5's truth log (sim only) plus, always, what decided each object's colour and shape."""
        super()._log_perception(dets)
        if self.labeler is None or not dets:
            return
        self._w({"type": "labels", "t": round(self._t, 2), "rows": [
            {"obj": d.name, "xy": np.round(d.top[:2], 3).tolist(), "hsv": getattr(d, "hsv_color", d.color),
             "color": d.color, "color_src": getattr(d, "color_src", None), "shape": d.shape,
             "shape_geom": getattr(d, "shape_geom", d.shape), "shape_src": getattr(d, "shape_src", None),
             "leftover": bool(getattr(d, "leftover", False)), "dropped": bool(getattr(d, "other", False)),
             "merged": getattr(d, "merged", None),
             "d1": getattr(d, "d1", None)} for d in dets]})

    def _apply_instruction(self):
        from instruction_d1 import slots_to_mapping
        try:
            slots, rec = self.instr.result()
            if slots is not None:
                m = slots_to_mapping(slots)
                rec["agrees_with_rules"] = m == self.mapping
                rec["rules_mapping"] = _str_keys(self.mapping)
                if m != self.mapping:
                    self.log(f"[v1.6] instruction: Decision {m} replaces rules {self.mapping}")
                self.mapping = m
                self.planner.mapping = m
                self.relay.mapping = m
                self.mapping_source = "decision"
        except Exception as e:                  # the rule parser's mapping stays
            rec = {"used": False, "why": f"error {e!r}"}
        self._w({"type": "instruction", "t": round(self._t, 2), "mapping": self.mapping,
                 "mapping_source": self.mapping_source, **rec})


def _str_keys(m):
    return {(k if isinstance(k, str) else " ".join(map(str, k))): v for k, v in m.items()}


def _jsonable(o):
    if isinstance(o, dict):
        return {(k if isinstance(k, (str, int, float, bool)) or k is None else " ".join(map(str, k))
                 if isinstance(k, tuple) else str(k)): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    return o
