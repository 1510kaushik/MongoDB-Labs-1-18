# Lab 18 – Comparative Analysis: MongoDB vs Cassandra vs Neo4j for a Threat / Fraud Detection System

## 1. Executive Summary

For a threat-and-fraud detection platform, **no single store wins every access pattern**. In our 100,000-threat benchmark MongoDB had the best latency for indicator history (1.9 ms), target/spread lookups (6.7 ms) and insert throughput among the three (~31.7k rows/s). Cassandra was fastest for the pre-aggregated daily-volume query (18 ms) and is the only one of the three that scales writes linearly by adding nodes. Neo4j was not the fastest at any benchmark query, but it is the only one that expresses *relationship* questions natively. In the Lab 18.1 activity, Louvain over the co-targeting graph recovered all 25 planted campaigns (purity 1.0). **Recommendation:** use **MongoDB as the system of record and primary query store** (up to ~10M threats on a replica set, beyond that sharded). Add **Neo4j as a derived graph for campaign/community analysis**, fed from MongoDB. Add **Cassandra only if sustained ingest exceeds what a sharded MongoDB cluster handles economically** (roughly >50–100k events/s, or 100M+ events with a multi-region write requirement).

## 2. Methodology

| Item | Value |
|---|---|
| Data | **100,000** threat events (the lab's "1,00,000"), 20,000 unique indicators, 5,000 target orgs, 6 sources (URLhaus, OTX, AbuseIPDB, PhishTank, ThreatFox, OpenPhish – *source names only; data is synthetic*), 6 categories, 90 days ending 2026-11-20, each with an associated transaction record (100,000 docs in MongoDB) |
| Planted structure | 35% of events come from 25 "campaigns" (40 indicators × 60 targets each) so the community-detection activity has a ground truth. Generator: [common.py](common.py), seeded and deterministic |
| Environment | Docker Desktop on Windows 11, 8 logical CPUs, ~24 GB host RAM shared with other containers. One single-node container each: `mongo:7.0` (2 GB limit), `cassandra:4.1` (1 GB heap, 3 GB limit), `neo4j:5.26-community` (1 GB heap, 512 MB page cache, 3 GB limit, GDS plugin). Client: Python 3.12 container on the same Docker network (pymongo, cassandra-driver, neo4j driver) |
| Protocol | 1 discarded warm-up + **10 timed runs per query per database**; **median** reported (plus p90/min/max in [results/bench.json](results/bench.json)). Q1/Q2 use 10 different indicators (same keys for all DBs); Q3 repeats the same query; Q4 inserts 10 distinct batches of 1,000 *new* threats |
| Correctness | Before timing, `bench.py` asserts that Q1, Q2 and Q3 return **identical results on all three databases** |
| Queries | **Q1 Threat history:** all sightings of one indicator, newest first. **Q2 Target & spread:** targets hit by an indicator, then the top-10 other indicators hitting the same targets. **Q3 Daily volume:** sightings per day × category, last 30 days. **Q4 Insert throughput:** write 1,000 new threats (all indexes / denormalised tables updated) |

**Caveats (please read):** single node, small data set that fits in RAM (so this measures engine + driver overhead, not disk behaviour); synthetic data; Cassandra was driven by the pure-Python driver (no C extensions) which penalises it heavily on Q4/bulk load. The scalability section is an *estimate from published architecture and rules of thumb*, not something measured here.

## 3. Architecture

```
                   threat feeds (URLhaus, OTX, AbuseIPDB, PhishTank, ...)
                                      │
                              ingest / normaliser
                                      │
                 ┌────────────────────┼────────────────────┐
                 ▼                    ▼                    ▼
          MongoDB (primary)     Cassandra (optional    Neo4j (derived graph)
          threats, transactions  high-rate ingest/     Indicator─HIT→Target
          flexible docs, ad-hoc  time-series tier)     CO_TARGETS, Louvain
          queries, aggregation   by_indicator/by_target communities
                 ▲                                           │
                 └──────── cross-reference tx details ◄──────┘
                                      │
                         fraud analyst UI / alerts
```

## 4. Schema Design / Data-Modelling Analysis

**MongoDB** – one document per sighting in `threats` (indicator, category, source, target, severity, ts, day, tx_id) and a `transactions` collection (`_id`=tx_id, amount, country, channel, card_hash). Indexes: `{indicator,ts}`, `{target}`, `{day,category}`, unique `{threat_id}`. *Why:* flexible docs let new feed fields appear without migrations; one compound index serves Q1 as an index-ordered scan; the aggregation pipeline handles Q2/Q3 without extra tables. Transactions are kept separate so transaction data (PII-adjacent) can have different access control.

**Cassandra** – query-first, denormalised: `threats_by_indicator ((indicator), ts DESC, threat_id)`, `threats_by_target ((target), ts DESC, threat_id)`, counter table `daily_volume ((day), category, cnt counter)`. Every event is written 3 times. *Why:* each query is a single-partition read; no joins/ad-hoc filters exist, so any new question needs a new table. Q2 is an application-side join (1 read + N concurrent reads, N≈20–60 targets). Q3 is cheap only because it was pre-aggregated at write time.

**Neo4j** – `(:Indicator {value})-[:HIT {threat_id, ts, day, category, severity, source, tx_id}]->(:Target {id})`, uniqueness constraints on both node keys, relationship index on `day`. The event is a relationship, not a node, to keep 100k events at 100k relationships. *Why:* Q2 becomes a 2-hop pattern; the same graph feeds `CO_TARGETS` edges (indicators sharing ≥3 targets) for community detection. Weak spot: Q3 scans relationships (no native aggregation index).

| Concern | MongoDB | Cassandra | Neo4j |
|---|---|---|---|
| Schema change | add a field, no migration | new table + backfill | add property; new rel types are free |
| Ad-hoc queries | good (secondary indexes, aggregation) | poor (design for known queries) | good for graph patterns, mediocre for scans/aggregates |
| Write amplification | 1 doc + 4 index entries | 3 rows + 1 counter | 1 rel + 2 node merges |
| Data size here | smallest working set (≈190 MB RSS) | ≈1.5 GB (heap-dominated) | ≈2.1 GB (page cache + heap) |

## 5. Query Performance (median of 10 runs, ms; lower is better)

| Query | MongoDB | Cassandra | Neo4j | Winner |
|---|---:|---:|---:|---|
| Q1 Threat history (one indicator) | **1.94** | 4.29 | 15.71 | MongoDB |
| Q2 Target & spread (2-hop) | **6.72** | 24.76 | 14.11 | MongoDB |
| Q3 Daily volume, last 30 days | 44.17 | **18.25** | 76.97 | Cassandra (pre-aggregated) |
| Q4 Insert 1,000 threats | **31.59** (31.7k rows/s) | 1102.14 (0.9k rows/s)* | 123.70 (8.1k rows/s) | MongoDB |
| Bulk load of 100k (s) | **5.3** | 123.0* | 22.4 | MongoDB |

\*Cassandra's write numbers are dominated by the pure-Python client driving 3 writes per event on a 1 GB-heap single node; production clients (Java/Go driver, batching by partition, 3+ nodes) are typically one to two orders of magnitude faster, so **do not read Q4 as Cassandra's real ceiling**. They do show the write-amplification cost of denormalising.
Raw per-run values: [results/bench.json](results/bench.json), [results/load_times.json](results/load_times.json).

Observations: Mongo's Q1 win is an index-ordered range scan on a warm cache. Cassandra's Q3 win exists only because Q3 was designed in advance; computing it ad hoc would require a full scan. Neo4j's Q2 (14 ms) beats Cassandra's client-side join but loses to Mongo's `$group`, because this graph is small and the fan-out (~1–2k edges) is within what an indexed aggregation handles easily; graph databases pull ahead as hop depth increases (3+ hops), which we did not benchmark.

## 6. Activity 18.1 – Graph community detection + MongoDB cross-reference

[community.py](community.py): (1) in Neo4j create `CO_TARGETS {w}` between indicators sharing ≥3 targets (19,503 edges); (2) run `gds.louvain` (weighted); (3) score communities by density (internal edges / possible) and lift vs. whole-graph density (≈0.0001); flag density ≥0.2 **and** ≥100× lift; (4) for each flagged community pull the member threats' transactions from MongoDB (`threats.indicator ∈ members` → `transactions.threat_id ∈ …`) and aggregate.

Result ([results/communities.json](results/communities.json), [.csv](results/communities.csv)): **25 communities flagged, all with density 1.0 (≈9,800× the graph baseline), matching the 25 planted campaigns with purity 1.0**; no noise community was flagged. Flagged communities' transactions average **$630–$712** vs. **$329.52** overall (~2×), spread over ~1.3–1.4k distinct cards each, with max single transactions up to ~$22.8k. Caveat: because the campaigns were planted (and given higher amounts by the generator), this validates the pipeline, not real-world detection accuracy; real data will have overlapping, partially connected clusters and needs threshold tuning and analyst review to control false positives.

## 7. Scalability Assessment (estimates, not measured here)

Assumptions: ~1 KB/event raw, 3 query access patterns above, replication factor 3, 70% disk headroom. Figures are order-of-magnitude planning numbers.

| Scale | MongoDB | Cassandra | Neo4j (Community → Enterprise) |
|---|---|---|---|
| **1M events** (~1–5 GB w/ indexes) | One 3-node replica set, 4 vCPU / 16 GB each | Works but over-engineered; 3 nodes × 4 vCPU/16 GB | Single instance 4 vCPU / 16 GB (graph fits page cache) |
| **10M** (~10–50 GB) | Replica set, 8 vCPU / 32 GB, SSD; working set + indexes fit in RAM | 3 nodes × 8 vCPU / 32 GB, 1–2 TB SSD (compaction headroom) | Single instance 8 vCPU / 64 GB; add read replicas via Enterprise causal clustering |
| **100M** (~100–500 GB) | **Sharded cluster**: 3 shards × 3-node RS (8–16 vCPU / 64 GB) + 3 config + 2+ mongos; shard key e.g. hashed `indicator` (Q1/Q2) – `target` queries then scatter-gather | 6–12 nodes × 16 vCPU / 64 GB, local NVMe; add nodes with virtual nodes rebalancing | Vertical to 16+ vCPU / 128–256 GB RAM; sharding is Enterprise "Infinigraph" / fabric-style federation and is much harder to do well; plan to keep only the *hot, recent* graph |

**Horizontal scaling mechanisms.** *MongoDB:* replica sets for HA/reads; range or hashed **sharding** by shard key via `mongos` + config servers; balancer moves chunks; shard-key choice is hard to change. *Cassandra:* **peer-to-peer ring**, consistent hashing with vnodes, add nodes online and data streams automatically; tunable consistency (`ONE`/`QUORUM`), multi-DC replication built in; scaling writes is its core strength. *Neo4j:* Community = single instance; Enterprise adds **causal clustering** (Raft primaries + read replicas) which scales *reads* and HA, not write throughput or graph size; sharding by property ("graph sharding"/federation) is newer and requires careful partition-aware modelling because traversals crossing shards are costly.

**Operational complexity.**

| | MongoDB | Cassandra | Neo4j |
|---|---|---|---|
| Backup | `mongodump` (small), filesystem/volume snapshots, Ops Manager / Atlas continuous backup; PITR via oplog | Snapshot + incremental backup per node, Medusa/Priam; restore is per-node and slow at scale | `neo4j-admin database backup` (Enterprise online) / dump offline in Community (stop DB) |
| Monitoring | `mongodb_exporter`→Prometheus (as in Lab 13): replication lag, WiredTiger cache, queues, chunk balance | `nodetool` + JMX exporter: pending compactions, tombstones, GC pauses, hinted handoff, repair status | JMX/Prometheus metrics: page cache hit ratio, tx log size, heap; GDS memory |
| Routine toil | index tuning, shard-key/balancer, oplog window | **repairs**, compaction strategy, tombstones, GC tuning, capacity headroom | page-cache sizing, query tuning (Cypher plans), store growth |
| Skills | familiar JSON/SQL-like; broad talent pool | data modelling discipline, JVM/ops expertise; steeper | Cypher / graph modelling; smaller talent pool |

## 8. Ergonomics (developer experience)

- **MongoDB:** lowest friction. Documents map to Python dicts; `insert_many`, `find().sort()`, `aggregate()` read naturally. Q2 needed two straightforward calls. Adding a new feed field cost nothing.
- **Cassandra:** CQL looks like SQL but isn't: no joins, no ad-hoc filtering, partitions must be designed per query. Q2 required client-side joining and concurrency code; Q3 required a counter table and write-time updates. Most code, most up-front design, but queries are predictable and cannot accidentally scan.
- **Neo4j:** most expressive for relationship questions (Q2 is a 3-line pattern; community detection is a procedure call). Cypher has a learning curve; tooling for aggregation-heavy analytics and bulk ingest (UNWIND/MERGE batching) is less natural; GDS needs plugin and memory planning.

## 9. Recommendation (per access pattern)

| Access pattern | Best choice | Why |
|---|---|---|
| Indicator / target history (Q1) | **MongoDB** (Cassandra if >100M and needs strict horizontal scale) | 1.9 ms median, compound index serves it directly; Cassandra close at 4.3 ms with perfect partition scaling |
| Target & spread (Q2) | **MongoDB now; Neo4j** as hop depth or relationship complexity grows | Mongo fastest at 2-hop on this data; Neo4j beats Cassandra and is far simpler to express for 3+ hops |
| Daily volume analytics (Q3) | **Cassandra counters** or a **MongoDB pre-aggregated rollup** (`$merge` into a daily collection) | Cassandra 18 ms only with pre-aggregation; ad-hoc scans cost 44 ms (Mongo) / 77 ms (Neo4j) and rise linearly with data |
| High-rate ingest (Q4) | **Cassandra at large scale** (multi-node, proper driver); **MongoDB** up to mid-scale | Cassandra's results here are driver/single-node limited — its design (LSM, no read-before-write) is the right one for sustained 100k+/s; Mongo gave the best measured throughput |
| Campaign / community detection, cross-entity patterns | **Neo4j (+ GDS)** | Louvain recovered 25/25 campaigns; MongoDB then supplies transaction detail |

**Overall:** start with MongoDB as the primary store; add Neo4j as an analytical graph projection refreshed from it; adopt Cassandra only when ingest scale or multi-region write availability makes the extra modelling and operations cost worthwhile.

## 10. Reproducing

```
docker compose up -d
docker exec lab18-runner pip install pymongo cassandra-driver neo4j
docker exec lab18-runner python load.py
docker exec lab18-runner python bench.py
docker exec lab18-runner python community.py
```
