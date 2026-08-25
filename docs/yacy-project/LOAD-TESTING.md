# Load testing — YaCy on Hetzner

PLAN.md Phase 5 PERF item.

## Toolchain

- `wrk` (apt) + custom Lua script `scripts/load-test-queries.lua`
  randomising over 17 real-traffic queries (short + long + with modifiers)
  sampled from prod `query_logs`.
- Driver: `scripts/load-test.sh`. Ramp 10 → 50 → 100 → 200 → 500 → 1000
  concurrent, 30 s per stage, 60 s cool-down. Aborts on 5xx > 5 %.
- Targets the `yacy` container directly via its bridge IP (`172.18.0.20:8090`)
  — bypass traefik & Cloudflare so we measure the engine, not the edge.

## First baseline run — 2026-05-08 13:17 UTC

Conservative ramp (10 / 50 / 100, 20 s stages) to find the ceiling
without DoSing prod. Cluster otherwise live.

| concurrent | RPS  | p50      | p95     | p99     | 5xx   | wrk timeouts (>2s) |
|-----------:|-----:|---------:|--------:|--------:|------:|-------------------:|
|         10 | 14.7 |   473 ms |  856 ms | 1264 ms | 0     |                  0 |
|         50 | 20.7 |  1539 ms | 1972 ms | 1995 ms | 0     |                220 |
|        100 | 22.6 |   831 ms | 1964 ms | 1998 ms | 0     |                416 |

**Observations**

- **Throughput plateaus at ~22 RPS.** Going from 50 → 100 concurrent
  added 2 RPS while doubling timeout count. Adding more clients only
  fills the queue.
- **No 5xx, no connection errors** — backend is graceful. wrk reports
  these as `Socket errors: timeout` (default 2s read timeout), the
  requests still complete server-side, just past the deadline.
- **Container CPU is NOT the bottleneck:**
  - `yacy` peaked at 280 % out of a 450 % limit (4.5 cores).
  - `yacy-vector-service` peaked at 715 % out of a 1200 % limit (12 cores).
  - `yacy-pgvector` 1.6 % CPU, 1 GiB / 2 GiB RAM — idle.
  - `yacy-redis` 0.3 % CPU, 6 MiB / 512 MiB — idle.
- **Memory is fine.** `yacy` grew 1.5 → 4.3 GiB during the run; comfortably
  inside the 6 GiB heap. No swap.

**So the ceiling is upstream of CPU.** Most likely candidates:

1. **Solr query thread pool.** Solr 9 default `<maxThreads>` for the
   query handler is bounded; deeper concurrency just queues. Worth
   inspecting `solrconfig.xml` and `web.xml`.
2. **vector_service `/rank` is the hot path.** 715 % CPU at 22 RPS ≈
   33 % CPU per request — semantic re-rank of 10 candidates per query
   is genuinely heavy. This is the choke point: every search waits on
   one rank call. Cache hit-rate via `yacy-redis` should already help
   for the popular-query subset, worth confirming Redis hit-rate metric.
3. **Jetty acceptors / selectors.** YaCy ships a stock Jetty config; on
   request bursts new connection establishment may serialise.

**Important caveat:** `wrk` timeouts at 2 s artificially flatten p99 at
~2000 ms — true tail latency at 50 / 100 concurrent is higher. To get
real p99 a re-run with `--timeout 10s` is needed.

## Decision

The 200 / 500 / 1000 stages were **NOT executed** — at 100 concurrent
we already see 92 % timeout-rate on a live prod instance, pushing
further on prod risks user-facing impact. They belong in a staging /
isolated run.

## Next steps (deferred — not blocking PLAN.md close)

- [ ] Re-run baseline with `wrk --timeout 10s` to capture true p99.
- [ ] Inspect Solr `solrconfig.xml` `<requestHandler>` thread settings.
- [ ] Measure `yacy-redis` hit-rate during the run (`redis-cli info stats`).
- [ ] If vector rank is the choke: batch candidates across concurrent
      queries OR add an LRU at the FastAPI layer keyed on query-string.
- [ ] Stand up an isolated YaCy + vector + pgvector stack on Mac mini
      and run the full ramp to 1000 there.

## How to re-run

From the Hetzner host:

```bash
cd /home/vir/stacks/yacy/deploy
bash load-test.sh                # full ramp 10..1000
bash load-test.sh 10 50 100      # only first three stages
DURATION=60s bash load-test.sh 50  # custom duration / single stage
```

Results land under `load-test-results/<UTC-stamp>-summary.txt` plus
`<stamp>-c<N>.log` per stage.
