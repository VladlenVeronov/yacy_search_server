# YaCy P2P audit & VIR GOO hardening — Phase 4 NETWORK

Status as of `feature/remove-third-party-links` HEAD. Outbound DHT
distribution path of the upstream YaCy is intentionally permissive —
this document records what we left in place, what we hardened, and what
is left to do.

---

## 1. Outbound RWI (DHT) distribution — code path

```
SwitchboardConstants.INDEX_DIST = "20_dhtdistribution"
   └─ Switchboard.dhtTransferJob()
        └─ Dispatcher.selectContainersEnqueueToBuffer()
             ├─ selectContainers()                    [pick term-index entries to ship]
             ├─ filterDhtBlacklisted()  ← VIR GOO     [drop refs whose URL is on DHT blacklist]
             ├─ splitContainer()                       [vertical-DHT partition]
             └─ enqueueContainersToBuffer()            [pin to redundant peer targets]
   └─ Dispatcher.dequeueContainer() → indexingTransmissionProcessor → Transmission
```

`filterDhtBlacklisted()` lives in `source/net/yacy/peers/Dispatcher.java`.
For each container it walks every `WordReference`:

1. Hot path — if `urlhash` is already in `Switchboard.urlBlacklist`'s
   `cachedUrlHashs[BlacklistType.DHT]` set, drop it. O(1).
2. Cold path — resolve `urlhash → URL` via `Segment.fulltext().getURL()`
   then `Blacklist.isListed(BlacklistType.DHT, DigestURL)`. The matcher
   auto-populates the hot cache on first match.

Both paths drop refs *before* the chunk is split into vertical
partitions and enqueued for transmission, so a blacklisted URL is never
shipped to any peer.

---

## 2. Sharing posture (yacy.conf on prod)

| key                           | value | meaning                                                        |
|-------------------------------|-------|----------------------------------------------------------------|
| `allowDistributeIndex`        | true  | We share our crawled index out via DHT.                        |
| `allowReceiveIndex`           | false | We do **not** accept other peers' DHT shares (no porn leak in).|
| `60_remotecrawlloader_isPaused`| true | We do not run other peers' crawl jobs.                         |
| `indexReceiveBlockBlacklist`  | true  | Even if receive ever flips on, blacklist filter applies.       |
| `network.unit.name`           | freeworld | Public YaCy network; `intranet` would isolate us.          |

`list.black` ships 401 entries (porn / casino / gambling / propaganda /
mainstream-tracking) and is active on `crawler / proxy / search / dht /
news` simultaneously — see Settings → Filter & Blacklists.

---

## 3. Inbound search via remote peers

`global` resource on the search form fetches results from peers; this is
*read-only at our end* — they ship us their hits, we don't accept their
DHT word-references. Spammy hosts in remote results are filtered
client-side by `BlacklistType.SEARCH` before we render them.

Stealth Mode (resource=`local`) on the search trailer disables this and
limits to our own index — for users who don't trust the network at all.

---

## 4. Reputation / repute

YaCy already tracks `Hits` / `Bytes` / `Connects` / `Recv` / `Sent` /
`Useless` per peer in the seed list (see `htroot/Network.html`). Outgoing
DHT picks targets via `DHTSelection.selectDHTDistributionTargets()` which
weights by `verticalDHTPosition()` — distance, not quality. **We do
not yet bias toward peers that send us higher-quality hits.**

A pragmatic next step: add a soft penalty in `DHTSelection` based on a
running `usefulHitRatio` per peer (= cliked-on-results / hits-served).
The vector_service already logs query→click events to pgvector; the same
table can be aggregated per source-peer once the search trailer starts
tagging hit-source. Out of scope for this sprint; tracked here as a
deferred TODO.

---

## 5. What's intentionally NOT done

* **Cryptographic peer trust** — YaCy's seed verification is just
  "did the seed file we got match our local signature for this peer".
  Phase 4 does not introduce stronger identity (e.g. signed RWI chunks).
* **Per-peer quotas on inbound** — irrelevant while
  `allowReceiveIndex=false`. Re-evaluate if we ever flip that on.
* **Repute curve in `DHTSelection`** — see §4.

---

## 6. Operator's checklist

Standing up your own VIR GOO node and joining the network:

```bash
# 1. Clone the fork
git clone -b feature/remove-third-party-links \
    https://github.com/VladlenVeronov/yacy_search_server.git
cd yacy_search_server

# 2. (Once)  ant clean all  → produces lib/yacycore.jar
ant clean all

# 3. Either run the deploy/docker-compose.yml stack, or boot in-place:
./startYACY.sh          # http://localhost:8090

# 4. Network → Use Network 'freeworld'  (default if you ran the docker compose stack)

# 5. Filter & Blacklists → confirm `list.black` is checked on
#    crawler / proxy / search / dht / news  (defaults shipped enabled)

# 6. Index Sharing (port 8090 → /IndexShare_p.html):
#    - Distribute index = ON   (share our hits with the network)
#    - Receive index    = OFF  (we trust our crawler, not strangers)
#    - Receive block via blacklist = ON (defense-in-depth)

# 7. Crawler → Crawl Start (Expert):  start with curated seed lists,
#    crawlingMustMatch limited to your domain or vetted set.
```

Smoke test the outbound filter (post-blacklist of a known host):
```bash
docker exec yacy bash -lc \
  "echo 'badcasino.example' >> /opt/yacy_search_server/DATA/LISTS/list.black"
# trigger a DHT push job in the admin UI; tail /opt/yacy_search_server/DATA/LOG/yacy00.log
# expect:  DHT-OUT  selectContainersEnqueueToBuffer: DHT blacklist dropped N of M refs before transmit
```

---

## 7. Files

| file                                                | role                                                  |
|-----------------------------------------------------|-------------------------------------------------------|
| `source/net/yacy/peers/Dispatcher.java`             | outbound RWI selection + **DHT blacklist filter**     |
| `source/net/yacy/peers/Transmission.java`           | per-target chunk transport                            |
| `source/net/yacy/peers/DHTSelection.java`           | distribution target picker (no repute weighting yet)  |
| `source/net/yacy/repository/Blacklist.java`         | matcher, cached hash set, type enum                   |
| `htroot/IndexShare_p.html`                          | admin UI for the share toggles                        |
| `defaults/list.black`                               | shipped 401-host blacklist                            |
