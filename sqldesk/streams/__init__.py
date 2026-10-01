"""
A stream is a window, not a pipeline.

SQLDesk keeps the last few minutes of raw events from a topic and rolls
everything older into per-minute buckets it can keep for a day. A dashboard
asking "what is happening now" reads the raw window; one asking "how does now
compare to this morning" reads the rollup. Neither needs SQLDesk to hold a day
of raw Kafka, and it will not.

**For history, land the topic in your warehouse** with Kafka Connect or Flink
and point SQLDesk at the warehouse. That is not a limitation being apologised
for -- it is the division of labour. A broker already has retention, a
warehouse already has history, and a dashboard tool that tried to be either
would be a worse version of both while being the thing that falls over.

Three ideas carry the whole design:

**Python moves bytes; DuckDB does the work.** The consumer never decodes a
message. It collects raw message bytes for one second and hands the buffer to
DuckDB as newline-delimited JSON, which parses it, stores it, and once a minute
aggregates it. Measured on 200,000 events of ordinary JSON on two cores:
`json.loads` one at a time managed 250,000 events/sec, DuckDB parsing the whole
batch managed 914,000, and the rollup `GROUP BY` over those rows took seven
milliseconds. The aggregation was never the cost. The parsing was, and the way
to win is to do neither in Python.

**The row budget is the limit; the window follows from it.** A fixed window is
wrong in both directions -- thirty minutes of a 50,000/s topic is gigabytes,
five minutes of a 3/s topic is an empty chart. So a budget of rows is set and
the window is whatever that buys at the rate actually observed. See `window`.

**Nothing is ever buffered on the way in.** Over the ceiling, events are
sampled and the chart says so. An unbounded queue in front of a slow writer is
the crash, not the protection against it: whatever arrives in a second is
either written or sampled away within that second.
"""
