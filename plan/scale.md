# What breaks at 500 concurrent users

Worked out on 2026-10-03, from the code and from the running install. The
figures are measured where they say measured. Re-measure rather than trusting
these after any of it changes.

## The ceilings, in the order they are met

**1. Gunicorn runs sync workers, four of them, on one replica.**
`bin/docker-entrypoint` has no `-k`, so **four concurrent HTTP requests** is
the whole web tier. One 3 MB result fetch holds a worker for its duration.
500 viewers checking in every 15s is 20–33 req/s before anybody loads a page.
Nothing else matters until this is fixed.

**2. Postgres connections run out before the web tier scales.** SQLAlchemy
defaults to 5 + 10 overflow *per process*; four workers is up to 60 per
replica, and Postgres ships with `max_connections=100`. The third replica
meets `FATAL: sorry, too many clients already`. Nothing in the chart sets
`SQLALCHEMY_POOL_SIZE`.

**3. Redis has no `maxmemory` and no volume.** It holds RQ job state, stream
slots and live check-ins. Unbounded until the container limit kills it, and a
restart loses every in-flight query. It must be `noeviction` — evicting a key
loses a running query silently.

**4. The uploads volume pins every worker to one node.** `ReadWriteOnce`
mounts on one node, so the chart gives the workers affinity to the server's.
A `ReadWriteMany` class (EFS, Filestore, Azure Files, NFS) removes it.

**5. No HPA, no PDB, no topology spread** in the chart. Scaling is
`kubectl scale`, and a node drain can take the whole web tier.

**6. The scheduler is a singleton with no leader election.** If it dies
nothing refreshes, and the only signal is Outdated Queries growing.

**7. Results travel through the web tier and are rebuilt per viewer.**
Measured on 20k×8 (3.3 MB): `JSON.parse` 14 ms, `QueryResult.update()`
**960 ms** on the browser's main thread. One dashboard pays once since 0.5;
100 viewers of it pay 100 times.

## Already fine

Checked, do not re-investigate: the dashboard N+1 (9 statements for 15
widgets, 19 per check-in), the `query_results(query_hash, data_source_id,
retrieved_at DESC)` index, `_unlock` running after `store_result`,
Redis-backed rate limiting that works across replicas, and hidden tabs that
stop checking in.

## Measured memory, idle

| Process | Resident | What grows it |
|---|---|---|
| `server` pod, 4 web workers | 250 MB | Serializing results |
| `worker` process | 200 MB | The result it holds, in full |
| `stream-worker` process | 280 MB | Flat — flushes to a file each second |
| `mcp-worker` process | 380 MB | As a worker, plus the catalog |
| `scheduler` | 190 MB | Nothing; it only enqueues |

## 500 concurrent

Assuming ~300 watching live dashboards and ~25 queries executing at any moment.

| Tier | Shape |
|---|---|
| Web | 6 × (1 vCPU, 1.5 GB), 4 workers each — 24 is the figure to reach |
| Query workers | 4 × (2 vCPU, 2.5 GB), 8 processes each |
| Postgres | 8 vCPU, 32 GB, 500 GB SSD, **behind PgBouncer** |
| Redis | 2 vCPU, 4 GB, `maxmemory` set, `noeviction` |
| Scheduler | 1 × (0.5 vCPU, 512 MB) — exactly one, always |
| Stream workers | 1 process per topic consuming at once |
| Renderer | 2 × (1 vCPU, 2 GB), only if alerts carry pictures |

About **22 vCPU and 50 GB** for SQLDesk, plus the database.

**The warehouse is the real constraint.** 500 people against Snowflake or
BigQuery costs far more than 22 vCPU. SQLDesk's job at that size is to not be
the bottleneck and to protect the warehouse — which is why per-data-source
queues matter more than web-tier capacity, and why the cost model is the
centre of 0.8.

## What an administrator still cannot do

Each of these is a gap, not an oversight, and the first three are in
[0.8-plan.md](0.8-plan.md):

- **No audit view.** `events` records everything; nothing reads it as "what
  has this person been doing".
- **No per-user or per-data-source throttle.** One person can queue fifty
  queries against the warehouse everybody shares.
- **No per-data-source kill switch.** When a warehouse is in trouble you want
  to stop sending it work without deleting the data source.
- **No history.** Top users is the last hour only.
- **No Prometheus endpoint** — StatsD only, which is the wrong shape now.
- **No connection-pool visibility**, which is the thing most likely to fall
  over.
- **No active-session list**, and no way to sign somebody out.
- **No maintenance mode.**
