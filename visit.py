#!/usr/bin/env python3
"""Headless 'browser' for the PoC.

Performs a top-level navigation to the eepsite and then auto-loads the
page's sub-resources exactly as a browser would -- same Fetch Metadata
headers, same cross-origin Referer behaviour -- with no user interaction.

Why not a real browser? A real browser works too (see README), but under a
plain localhost setup it would put 127.0.0.1 in the Referer instead of the
.i2p host, which hides the very thing we are demonstrating. Driving the
requests here lets us faithfully reproduce the headers the browser sends
when it is actually on http://linkability-demo.i2p/ behind the I2P proxy.

Referer is sent ORIGIN-ONLY (http://host/), matching the modern browser
default Referrer-Policy "strict-origin-when-cross-origin". Note the label
travels in the sub-resource URL regardless of Referrer-Policy -- it does
not depend on the Referer leaking at all.

Run:  python3 visit.py --eepsite http://127.0.0.1:8631 --path /article/42
"""
import argparse
import re
import sys
import urllib.request


def fetch(url, headers):
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eepsite", required=True,
                    help="real base URL the eepsite is served on")
    ap.add_argument("--path", default="/article/42")
    ap.add_argument("--eepsite-host", default="linkability-demo.i2p")
    ap.add_argument("--ua",
                    default="Mozilla/5.0 (X11; Linux x86_64; rv:128.0) "
                            "Gecko/20100101 Firefox/128.0")
    args = ap.parse_args()

    nav_url = args.eepsite.rstrip("/") + args.path
    origin_referer = "http://%s/" % args.eepsite_host  # origin-only

    # 1) Top-level navigation: this is the only thing the user actually did.
    #    Fetch Metadata marks it mode=navigate / dest=document -> the patch
    #    ALLOWS it, even though it is cross-site.
    nav_headers = {
        "User-Agent": args.ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1",
        "Sec-Fetch-Dest": "document",
    }
    body = fetch(nav_url, nav_headers).decode("utf-8", "replace")
    sys.stderr.write("[visit] navigated to %s%s\n"
                     % (origin_referer.rstrip("/"), args.path))

    # 2) The browser now parses the HTML and auto-loads every sub-resource,
    #    with no clicks. Each carries the per-visit label and the eepsite
    #    Referer across the network boundary to the clearnet collector.
    urls = sorted(set(re.findall(r'(?:src|href)="([^"]+)"', body)))
    for u in urls:
        if not (u.startswith("http://") or u.startswith("https://")):
            continue
        low = u.lower()
        dest = "image" if any(x in low for x in
                              (".gif", ".png", ".jpg", ".ico", "favicon")) else "empty"
        sub_headers = {
            "User-Agent": args.ua,
            "Accept": "image/avif,image/webp,*/*;q=0.8",
            "Referer": origin_referer,         # eepsite ORIGIN leaks to clearnet
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Dest": dest,
        }
        fetch(u, sub_headers)
        sys.stderr.write("[visit]   auto-loaded sub-resource  %s  (dest=%s)\n"
                         % (u, dest))


if __name__ == "__main__":
    main()
