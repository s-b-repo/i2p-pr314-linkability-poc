#!/usr/bin/env python3
"""Clearnet collector for the PR #314 linkability PoC.

Models a *public-internet* server that receives an automatically-loaded
sub-resource (a favicon / tracking pixel) that was embedded in an I2P
eepsite page. In a real deployment it is reached through the I2P HTTP
proxy's configured outproxy, so the only source IP it ever sees is the
outproxy's -- never the user's. The whole point of this PoC is that the
source IP is NOT the leak: a per-visit label carried inside the request is.

Every request is appended, as one JSON line, to the shared log file.

Two roles are served:
  * beacon  (/px.gif, /favicon.ico, ...)  -- the sub-resource embedded in the
      eepsite. Logs the per-visit label. ALSO mints a long-lived tracking
      cookie and Set-Cookies it, exactly as a real ad/analytics beacon does.
  * identity sink (/whoami)               -- a normal clearnet endpoint the
      SAME browser later reaches while logged in. It sees the tracking cookie
      again, now next to a real identifier. This stages "step 3".

Run:  python3 collector.py --port 8632 --log logs/collector_log.jsonl
"""
import argparse
import base64
import http.cookies
import json
import os
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# Standard 1x1 transparent GIF.
PIXEL = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)

LOGFILE = None


def _read_cookie(headers, name):
    raw = headers.get("Cookie")
    if not raw:
        return None
    try:
        jar = http.cookies.SimpleCookie()
        jar.load(raw)
        morsel = jar.get(name)
        return morsel.value if morsel else None
    except http.cookies.CookieError:
        return None


class Handler(BaseHTTPRequestHandler):
    server_version = "clearnet-collector/1.0"

    def _log(self, rec):
        with open(LOGFILE, "a") as fh:
            fh.write(json.dumps(rec) + "\n")

    def do_GET(self):
        parsed = urlparse(self.path)
        q = parse_qs(parsed.query)

        # ----- step 3: identity sink -------------------------------------
        # A normal clearnet page the user is logged in to. No I2P involved;
        # the browser simply re-presents the tracking cookie the beacon set.
        if parsed.path == "/whoami":
            track = _read_cookie(self.headers, "track")
            identity = (q.get("user") or [None])[0]
            rec = {
                "event": "clearnet_identity",
                "ts": round(time.time(), 3),
                "src_ip": self.client_address[0],
                "path": self.path,
                "track_cookie": track,       # bridge back to the beacon hit
                "identity": identity,        # the real-world identifier
                "referer": self.headers.get("Referer"),
            }
            self._log(rec)
            sys.stderr.write(
                "[collector] identity  user=%s  track=%s\n" % (identity, track)
            )
            body = ("logged in as %s\n" % identity).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # ----- beacon: the embedded cross-network sub-resource -----------
        track = _read_cookie(self.headers, "track")
        set_cookie = None
        if track is None:
            # First contact: mint a durable tracking id, exactly like a real
            # analytics beacon. It will ride along on every later request this
            # browser makes to this clearnet origin -- including /whoami.
            track = uuid.uuid4().hex
            set_cookie = "track=%s; Path=/; Max-Age=31536000" % track

        rec = {
            "event": "clearnet_hit",
            "ts": round(time.time(), 3),
            # In a real I2P deployment this is the OUTPROXY's IP, identical
            # for every user of that outproxy -- useless for identifying a
            # person. That is exactly fai2p's objection, and it is correct.
            "src_ip": self.client_address[0],
            "path": self.path,
            "label": (q.get("sid") or [None])[0],
            "track_cookie": track,
            "set_cookie": set_cookie is not None,
            "referer": self.headers.get("Referer"),
            "user_agent": self.headers.get("User-Agent"),
            "sec_fetch_site": self.headers.get("Sec-Fetch-Site"),
            "sec_fetch_mode": self.headers.get("Sec-Fetch-Mode"),
            "sec_fetch_dest": self.headers.get("Sec-Fetch-Dest"),
        }
        self._log(rec)
        sys.stderr.write(
            "[collector] hit  label=%s  referer=%s  dest=%s  track=%s%s\n"
            % (rec["label"], rec["referer"], rec["sec_fetch_dest"], track,
               "  (set-cookie)" if set_cookie else "")
        )
        self.send_response(200)
        self.send_header("Content-Type", "image/gif")
        self.send_header("Content-Length", str(len(PIXEL)))
        self.send_header("Cache-Control", "no-store")
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
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
