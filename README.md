# PoC: cross-network sub-resource linkability (i2p.i2p PR #314)

This is a minimal, self-contained proof of concept for the linkability that
PR #314 ("HTTP proxy: block cross-network sub-resource loads") mitigates.
It answers the reviewer's question:

> Can you provide a PoC of the linkability you refer to, and what correlation
> can be established? It does not need to be fancy, as long as it gets the
> point across.

Python 3 standard library only. No I2P router required.

```
python3 -m pip install nothing   # there are no dependencies
bash run_poc.sh
```

## The point, up front

The reviewer is right that **the clearnet host only sees the outproxy's IP**.
The IP is *not* the leak. The leak is that a page on one network can make the
browser emit an *automatic, unavoidable* request on the other network carrying
a **unique per-visit label**. That label turns an otherwise anonymous I2P
pageview into a **clearnet-observable event that can be joined back to it** —
with no cookie and no real IP involved.

```
  I2P side (anonymous)                      Clearnet side (observable)
  --------------------                      --------------------------
  GET http://linkability-demo.i2p/article/42
      |  server mints label = c122...c5
      |  page embeds:
      |    <img src="http://beacon/px.gif?sid=c122...c5">
      v  (browser auto-loads it, no click)
                           -- crosses the proxy boundary -->
                                            GET /px.gif?sid=c122...c5
                                              src_ip  = OUTPROXY (useless)
                                              Referer = http://linkability-demo.i2p/
                                              label   = c122...c5   <== JOIN KEY
```

Same label on both sides ⇒ the two observations are the same session.

## Roles / threat model

| Component | Real-world counterpart | In this PoC |
|---|---|---|
| `eepsite.py` | An I2P eepsite (malicious, compromised, or just carrying a third-party widget) | `http://linkability-demo.i2p/` served on `127.0.0.1:8631` |
| `collector.py` | A public-internet server hosting the embedded resource (favicon/pixel/font/script) | `127.0.0.1:8632` |
| `visit.py` | The victim's browser behind the I2P HTTP proxy | sends the exact Fetch-Metadata + Referer a browser sends |
| `correlate.py` | The adversary joining the two logs | prints the correlation |

The adversary only needs to **observe the clearnet request**. The strongest
position is operating both endpoints, but it is not required — the outproxy,
or any party on the path to / at the clearnet host, sees the same label +
Referer and can do the same join.

## What the run shows

- **4/4** clearnet requests join back to an exact I2P visit (`/article/42`,
  `/forum/thread/7`) purely by the shared label.
- `src_ip` on every clearnet record is the outproxy — identical, identifying
  no one. The correlation does **not** use it.
- `Referer: http://linkability-demo.i2p/` reaches the clearnet side, so the
  clearnet observer also learns *which I2P site* the session was on. This is
  origin-only (modern `strict-origin-when-cross-origin` default); the label
  does not depend on it.
- Each clearnet hit is tagged with the verdict PR #314's `blockCrossNetwork`
  logic would give it: the sub-resource loads are **BLOCK**, the top-level
  navigation is **ALLOW** (Fetch Metadata `mode=navigate`).

## What "correlation can be established" concretely means

1. **Session linkage (demonstrated):** one clearnet request ⇄ one I2P
   pageview, via the label. The clearnet-side observer learns an anonymous
   I2P session reached a point they control, *when*, and *from which eepsite*.
2. **Cross-anonymity-set move (demonstrated):** an event that lived inside
   I2P (where outside observers see only tunnels) is re-emitted on the public
   internet where far more parties can see it.
3. **De-anonymization (the escalation):** if that same label (or a cookie the
   beacon sets) is ever observed next to a real-world identifier — a logged-in
   request, an ad/analytics beacon the user also loads elsewhere, a second
   fetch tied to an account — the I2P session links to that identity.
   `step3_identity.py` now stages exactly this (see below); steps 1-2 are the
   join primitive it builds on. This matches the author's own framing ("a
   real-world identity or IP would require additional information").

## Step 3: from an anonymous label to a real identity (optional)

`bash run_step3.sh` runs the escalation end to end:

```
Phase 1  anonymous I2P pageview auto-loads the beacon
         GET <collector>/px.gif?sid=LABEL        (cross-site, no-cors)
         -> collector mints  Set-Cookie: track=COOKIE   and logs (LABEL, COOKIE)

Phase 2  later, SAME browser, ordinary clearnet, logged in
         GET <collector>/whoami?user=alice@example.com
         -> browser re-sends  Cookie: track=COOKIE
         -> collector logs (COOKIE, alice@example.com)

Join     LABEL -> COOKIE -> alice@example.com -> the exact I2P pageview
```

`correlate.py` prints the chain and reports the I2P pageview de-anonymized.

**The one added assumption, stated plainly:** a single browser profile (one
cookie jar) is used for *both* the I2P-proxied beacon load and an ordinary
authenticated clearnet request. That is precisely the configuration a correct
anonymity setup avoids (separate browsers / profiles for I2P and clearnet), and
precisely the client PR #314 protects as defense-in-depth. The patch removes
the **precondition**, not just the symptom: the cross-network beacon is blocked,
so the cookie is never set and there is nothing to bridge. The `track` cookie
here stands in for any durable clearnet identifier an ad/analytics endpoint sets
— the mechanism is ordinary third-party cookie tracking, applied across the
I2P/clearnet boundary.

## How PR #314 stops it

The proxy classifies the outgoing request from the headers it can see:

- `Sec-Fetch-Mode: navigate` / `Sec-Fetch-Dest: document` ⇒ top-level
  navigation ⇒ **allowed** (the user's own click/typing).
- Otherwise, Referer host on one network + request on the other ⇒ cross-network
  **sub-resource** ⇒ **blocked** (served the `crossnet-header.ht` 403).

In this PoC that is exactly the split: the navigation to the eepsite is
allowed, and the auto-loaded `px.gif` / `favicon.ico` that carry the label
are blocked — so no label and no Referer ever reach the clearnet side, and the
join in `correlate.py` has nothing to join.

## Honest limitations

- **Transport is localhost HTTP, not a live I2P + outproxy path.** This is
  deliberate: the correlation mechanism lives entirely at the HTTP layer
  (label in URL, Referer, Fetch Metadata). The real I2P path changes only the
  *source IP* seen by the collector — to the outproxy's — which is precisely
  the value the attack does **not** rely on. Running it over a real router
  would not add anything to the correlation; it would only make the IP column
  read `<outproxy>` instead of `127.0.0.1`.
- **Single browser / single user.** The PoC shows linkability of one session's
  two-network footprint. It does not, by itself, defeat a correctly configured
  anonymizing browser that blocks third-party sub-resource loads at the browser
  layer — the patch is defense-in-depth at the proxy for clients that don't.
- **Referer is origin-only** by default here, matching current browsers; under
  a stricter `no-referrer` policy the host would not leak, but the **label
  still does**, which is why the label — not the Referer — is the core of the
  attack.
- Requests with no classifiable referer are allowed by the patch (noted in the
  PR); those are out of scope for this demonstration.

## Files

```
eepsite.py         I2P eepsite that mints a per-visit label and embeds clearnet sub-resources
collector.py       clearnet server: logs sub-resource hits, sets a tracking cookie, has a /whoami identity sink
visit.py           headless browser: navigation + automatic sub-resource loads, real headers
step3_identity.py  one cookie jar across an I2P beacon load and a later authenticated clearnet request
correlate.py       joins the logs by label (+ the cookie->identity chain) and prints the PR#314 verdict
run_poc.sh         starts both servers, runs two visits, prints the result
run_step3.sh       runs the label -> cookie -> identity de-anonymization chain
logs/              JSONL observation logs written by the two servers
```

### Trying it in a real browser (optional)

Start the two servers (`python3 collector.py & python3 eepsite.py &`), point a
browser at `http://127.0.0.1:8631/article/42`, then run `correlate.py`. The
join still works; the only difference is the Referer will show `127.0.0.1:8631`
instead of the `.i2p` host, because a plain browser is not actually going
through the I2P proxy. `visit.py` exists to reproduce the real `.i2p` Referer
faithfully.
