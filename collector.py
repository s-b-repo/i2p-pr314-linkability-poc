#!/usr/bin/env python3
"""Clearnet collector for the PR #314 linkability PoC.

Models a *public-internet* server that receives an automatically-loaded
sub-resource (a favicon / tracking pixel) that was embedded in an I2P
eepsite page. In a real deployment it is reached through the I2P HTTP
proxy's configured outproxy, so the only source IP it ever sees is the
outproxy's -- never the user's. The whole point of this PoC is that the
source IP is NOT the leak: a per-visit label carried inside the request is.

Every request is appended, as one JSON line, to the shared log file.
Run:  python3 collector.py --port 8632 --log logs/collector_log.jsonl
"""
import argparse
import base64
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# Standard 1x1 transparent GIF.
PIXEL = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)

LOGFILE = None


class Handler(BaseHTTPRequestHandler):
    server_version = "clearnet-collector/1.0"

    def _record(self):
        q = parse_qs(urlparse(self.path).query)
        rec = {
            "event": "clearnet_hit",
            "ts": round(time.time(), 3),
            # In a real I2P deployment this is the OUTPROXY's IP, identical
            # for every user of that outproxy -- useless for identifying a
            # person. That is exactly fai2p's objection, and it is correct.
            "src_ip": self.client_address[0],
            "path": self.path,
            "label": (q.get("sid") or [None])[0],
            "referer": self.headers.get("Referer"),
            "user_agent": self.headers.get("User-Agent"),
            "sec_fetch_site": self.headers.get("Sec-Fetch-Site"),
            "sec_fetch_mode": self.headers.get("Sec-Fetch-Mode"),
            "sec_fetch_dest": self.headers.get("Sec-Fetch-Dest"),
        }
        with open(LOGFILE, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        return rec

    def do_GET(self):
        rec = self._record()
        sys.stderr.write(
            "[collector] hit  label=%s  referer=%s  dest=%s\n"
            % (rec["label"], rec["referer"], rec["sec_fetch_dest"])
        )
        self.send_response(200)
        self.send_header("Content-Type", "image/gif")
        self.send_header("Content-Length", str(len(PIXEL)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(PIXEL)

    def log_message(self, *a):  # silence default access logging
        pass


def main():
    global LOGFILE
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8632)
    ap.add_argument("--log", default="logs/collector_log.jsonl")
    args = ap.parse_args()
    LOGFILE = args.log
    os.makedirs(os.path.dirname(LOGFILE) or ".", exist_ok=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    sys.stderr.write(
        "[collector] listening on 127.0.0.1:%d  ->  %s\n" % (args.port, LOGFILE)
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
