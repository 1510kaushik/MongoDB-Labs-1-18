# Lab 16.2 – FraudQueryService

```
pip install pymongo cassandra-driver neo4j     # only needed for live use
python -m unittest -v                          # run from this folder; no databases required
FRAUD_LIVE=1 python -m unittest -v test_fraud_query_service.TestLive   # real DBs
```

## Design
| Method | Backend | Why |
|---|---|---|
| `get_transaction(txn_id)` | MongoDB `find_one` | flexible document lookup |
| `get_user_profile(user_id)` | Cassandra, partition `user_id`, clustering `event_time DESC` | time-ordered reads |
| `detect_fraud_rings(user_id, max_hops)` | Neo4j `[:TRANSFERRED_TO*1..N]` | multi-hop traversal |
| `analyze_transaction(txn_id)` | all three | merged report; a failed backend is recorded in `errors` instead of failing the call |

**Pooling:** PyMongo `maxPoolSize=10`; Cassandra `Cluster(executor_threads=4)`; Neo4j `max_connection_pool_size=20`.

**Circuit breaker (per backend):** 3 consecutive failures → open; calls raise `BackendUnavailable` without touching the database; after 30 s one trial call is allowed (success closes the circuit, failure re-opens it). A success resets the failure count.

**Safety:** `max_hops` is validated as an int in 1–6 because Cypher cannot parameterise variable-length bounds; the user id is always a bound parameter.

## Latency characteristics (expected, from the lab; not measured here)
| Operation | Typical latency | Notes |
|---|---|---|
| MongoDB lookup (indexed `txn_id`) | 2–5 ms | needs an index on `txn_id` |
| Cassandra time-ordered query | 3–8 ms | single-partition read |
| Neo4j, 1 hop | ~10 ms | |
| Neo4j, 3 hops | up to ~500 ms | grows with graph density (branching factor^hops) |
| `analyze_transaction` (sequential) | ≈ sum, ~15–520 ms | dominated by Neo4j; could run Cassandra + Neo4j concurrently to cut to max() |

The in-memory tests only measure service overhead (well under 1 ms). Use `TestLive` against real databases to record real p50/p95 numbers.
