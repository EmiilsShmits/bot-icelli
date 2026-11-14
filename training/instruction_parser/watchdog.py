"""Local cost backstop for the overnight run (runs on the laptop, stdlib only).

Deletes every instance whose hostname starts with `gemma-parser-exp-` (and its OS volume) when
  - the instance is older than --max-age-h hours (default 5.75), or
  - the Verda balance has dropped by more than --max-spend EUR since --start-balance.
Never touches any other instance. Reads VERDA_CLIENT_ID / VERDA_CLIENT_SECRET from ../../.env, prints no secrets.

  nohup caffeinate -i python3 watchdog.py --start-balance 197.86 > ../../artifacts/instruction_parser/watchdog.log 2>&1 &
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time
import urllib.request

PREFIX = "gemma-parser-exp-"
HERE = os.path.dirname(os.path.abspath(__file__))


def env():
    out = {}
    for line in open(os.path.join(HERE, "../../.env")):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.strip().split("=", 1)
            out[k] = v.strip().strip('"').strip("'")
    return out


class Verda:
    def __init__(self, api):
        self.api = api
        self.e = env()
        self.tok = None
        self.t = 0

    def _req(self, method, path, body=None, auth=True):
        h = {"Content-Type": "application/json"}
        if auth:
            if not self.tok or time.time() - self.t > 300:
                self.tok = self._req("POST", "/oauth2/token", {"grant_type": "client_credentials",
                                                                "client_id": self.e["VERDA_CLIENT_ID"],
                                                                "client_secret": self.e["VERDA_CLIENT_SECRET"]},
                                     auth=False)["access_token"]
                self.t = time.time()
            h["Authorization"] = "Bearer " + self.tok
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.api + path, data=data, method=method, headers=h)
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read().decode()
            return json.loads(txt) if txt.strip().startswith(("{", "[")) else txt

    def get(self, p):
        return self._req("GET", p)

    def put(self, p, b):
        return self._req("PUT", p, b)


def age_h(inst):
    ts = inst.get("created_at")
    if not ts:
        return 0.0
    t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 3600


def delete(v, inst, why):
    vols = [x for x in [inst.get("os_volume_id")] if x]
    print(f"{time.strftime('%H:%M:%S')} DELETE {inst['hostname']} {inst['id']} ({why}) volumes={vols}", flush=True)
    try:
        print(v.put("/instances", {"action": "delete", "id": inst["id"], "volume_ids": vols,
                                   "delete_permanently": True}), flush=True)
    except Exception as e:  # retry next loop
        print("delete failed:", e, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="https://api.verda.com/v1")
    ap.add_argument("--start-balance", type=float, required=True)
    ap.add_argument("--max-spend", type=float, default=33.0)
    ap.add_argument("--max-age-h", type=float, default=5.75)
    ap.add_argument("--every", type=int, default=120)
    ap.add_argument("--stop-after-h", type=float, default=9.0)
    a = ap.parse_args()
    v = Verda(a.api)
    t_start = time.time()
    seen_any = False
    while time.time() - t_start < a.stop_after_h * 3600:
        try:
            insts = [i for i in v.get("/instances") if str(i.get("hostname", "")).startswith(PREFIX)]
            bal = v.get("/balance")["amount"]
            spend = a.start_balance - bal
            print(f"{time.strftime('%H:%M:%S')} balance {bal:.2f} spend {spend:.2f} "
                  + ", ".join(f"{i['hostname']}:{i.get('status')}:{age_h(i):.2f}h" for i in insts), flush=True)
            seen_any = seen_any or bool(insts)
            for i in insts:
                if i.get("status") in ("deleting", "discontinued"):
                    continue
                if age_h(i) >= a.max_age_h:
                    delete(v, i, f"age {age_h(i):.2f}h")
                elif spend >= a.max_spend:
                    delete(v, i, f"spend {spend:.2f}")
            if seen_any and not insts and os.path.exists(os.path.join(HERE, ".run_done")):
                print("all experiment instances gone and run marked done; exiting", flush=True)
                return
        except Exception as e:
            print(f"{time.strftime('%H:%M:%S')} error: {e}", flush=True)
            if "api.verda.com" in v.api:
                v.api = "https://api.datacrunch.io/v1"
                v.tok = None
                print("switching to api.datacrunch.io", flush=True)
        time.sleep(a.every)


if __name__ == "__main__":
    main()
