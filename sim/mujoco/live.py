"""Live feed of a MuJoCo run over HTTP: an MJPEG stream of the newest frame (head camera | third-person view) and a
status line. run.py starts it with --live PORT; on Modal, modal_mujoco.py exposes the port through a tunnel.

    GET /         page with the stream and the status
    GET /stream   multipart/x-mixed-replace JPEG stream (~10 fps)
    GET /status   JSON: tag, trial, seed, instruction, results so far
"""
from __future__ import annotations

import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>MuJoCo live</title><style>body{background:#111;color:#ddd;font:14px/1.4 system-ui;margin:12px}
img{width:100%;max-width:1280px;display:block;border:1px solid #333}pre{white-space:pre-wrap}</style></head>
<body><img src="/stream"><pre id="s">...</pre><script>
async function f(){try{const r=await fetch('/status');const j=await r.json();
document.getElementById('s').textContent=JSON.stringify(j,null,1)}catch(e){}}setInterval(f,1000);f()</script>
</body></html>"""


class Live:
    def __init__(self, backend, port, fps=10.0):
        self.be, self.fps = backend, fps
        self.status = {}
        self._jpg, self._src = None, None
        live = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path.startswith("/stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    try:
                        while True:
                            jpg = live.jpeg()
                            if jpg:
                                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                                 + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                            time.sleep(1.0 / live.fps)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                body, ctype = ((json.dumps(live.status, default=str).encode(), "application/json")
                               if self.path.startswith("/status") else (PAGE.encode(), "text/html; charset=utf-8"))
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Access-Control-Allow-Origin", "*")     # a grid page elsewhere may poll /status
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.srv = ThreadingHTTPServer(("0.0.0.0", port), H)
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        print(f"live feed on http://localhost:{port}/", flush=True)

    def jpeg(self):
        fr = self.be.last_frame
        if fr is None:
            return None
        if fr is not self._src:                      # encode each new frame once, whatever the number of viewers
            from PIL import Image
            b = io.BytesIO()
            Image.fromarray(fr).save(b, "JPEG", quality=75)
            self._jpg, self._src = b.getvalue(), fr
        return self._jpg

    def close(self):
        self.srv.shutdown()
