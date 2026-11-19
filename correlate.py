#!/usr/bin/env python3
"""Join the I2P-side pageview log with the clearnet-side hit log by the
per-visit label, and print what an operator / observer learns -- i.e. the
"correlation that can be established" that the reviewer asked about.

Run:  python3 correlate.py --i2p-log logs/eepsite_log.jsonl \
                           --clearnet-log logs/collector_log.jsonl
"""
import argparse
import json


def load(path):
    out = []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    except FileNotFoundError:
        pass
    return out


def pr314_verdict(hit):
    """Mirror of PR #314's blockCrossNetwork classification:
    cross-network sub-resource loads are blocked; top-level navigations
    (per Fetch Metadata) are always allowed."""
    ref = hit.get("referer") or ""
    mode = hit.get("sec_fetch_mode")
    dest = hit.get("sec_fetch_dest")
    is_navigation = (mode == "navigate") or (dest == "document")
    is_cross = ".i2p" in ref          # referer on I2P, request on clearnet
    if is_navigation:
        return "ALLOW  (top-level navigation; Sec-Fetch-Mode=navigate)"
    if is_cross:
        return "BLOCK  (cross-network sub-resource; the leak this PR stops)"
    return "ALLOW  (same-network or unclassifiable referer)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--i2p-log", default="logs/eepsite_log.jsonl")
    ap.add_argument("--clearnet-log", default="logs/collector_log.jsonl")
    args = ap.parse_args()

    i2p_by_label = {r["label"]: r for r in load(args.i2p_log) if r.get("label")}
    hits = load(args.clearnet_log)

    bar = "=" * 76
    print(bar)
    print("LINKABILITY PoC  --  I2P #314")
    print("Join clearnet observations to I2P observations by a shared label")
    print(bar)
    print()
    print("I2P-side observations (what the eepsite operator logged):")
    for r in sorted(i2p_by_label.values(), key=lambda x: x["ts"]):
        print("  [%s]  http://%s%s   label=%s"
              % (r["ts"], r["eepsite_host"], r["path"], r["label"]))
    print()
    print("Clearnet-side observations (what the public server logged):")
    print()

    linked = 0
    for h in hits:
        label = h.get("label")
        pv = i2p_by_label.get(label)
        print("  clearnet request  %s" % h.get("path"))
        print("    src_ip        : %s   <-- only the OUTPROXY ip, same for everyone"
              % h.get("src_ip"))
        print("    label         : %s" % label)
        print("    Referer       : %s   <-- reveals which I2P site, forwarded by outproxy"
              % h.get("referer"))
        print("    Sec-Fetch     : site=%s mode=%s dest=%s"
              % (h.get("sec_fetch_site"), h.get("sec_fetch_mode"),
                 h.get("sec_fetch_dest")))
        print("    PR#314 verdict: %s" % pr314_verdict(h))
        if pv:
            linked += 1
            print("    >> JOINS I2P pageview  http://%s%s  at %s"
                  % (pv["eepsite_host"], pv["path"], pv["ts"]))
            print("       => the clearnet record is tied to that exact I2P visit,")
            print("          even though the clearnet record's IP is only the outproxy.")
        print()

    print(bar)
    print("RESULT")
    print(bar)
    print("  clearnet records joined to an exact I2P visit : %d / %d"
          % (linked, len(hits)))
    print()
    print("  Correlation established, using neither the user's IP nor any cookie:")
    print("    1. SHARED LABEL  links one clearnet request to one I2P pageview,")
    print("       so the operator of the clearnet endpoint knows those two events")
    print("       belong to the same browsing session.")
    print("    2. REFERER       tells the clearnet endpoint which eepsite the")
    print("       session was on -- an I2P-only fact, now observable on clearnet.")
    print()
    print("  Why this matters despite the outproxy (fai2p's question):")
    print("    - The IP is NOT the leak; it is the outproxy's and identifies no one.")
    print("    - The leak is that an anonymous I2P pageview is converted into a")
    print("      clearnet-observable event bearing a stable, unique label.")
    print("    - Anyone who can see that clearnet request -- the endpoint operator,")
    print("      the outproxy, a network observer near the clearnet host -- can now")
    print("      pin that I2P session to a point they control on the public side.")
    print("    - If that same label is ever seen next to a real identifier (a login,")
    print("      an account-bound beacon, a second clearnet fetch), the previously")
    print("      anonymous I2P session is linked to that identity. That is the")
    print('      \"additional information\" step; the label is what makes the join')
    print("      possible in the first place.")
    print()
    print("  PR #314 blocks step (1)+(2) at the proxy: the cross-network sub-resource")
    print("  never leaves, so no shared label and no Referer reach the clearnet side,")
    print("  while the top-level navigation the user intended is still allowed.")
    print(bar)


if __name__ == "__main__":
    main()
