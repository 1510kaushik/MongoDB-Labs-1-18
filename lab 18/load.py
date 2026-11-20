"""Load the same 100k threats into MongoDB, Cassandra and Neo4j; record load times."""
import json, time, sys
from pymongo import MongoClient
from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent_with_args
from neo4j import GraphDatabase
from common import *

timings = {}

# ---------------- MongoDB ----------------
def load_mongo():
    db = MongoClient(MONGO_URI)["lab18"]
    db.threats.drop(); db.transactions.drop()
    t0 = time.perf_counter()
    for batch in chunks(make_threats(), 10_000):
        db.threats.insert_many([{k: v for k, v in d.items()
                                 if k not in ("amount", "country", "channel", "card_hash")} for d in batch], ordered=False)
        db.transactions.insert_many([{"_id": d["tx_id"], "threat_id": d["threat_id"], "amount": d["amount"],
                                      "country": d["country"], "channel": d["channel"],
                                      "card_hash": d["card_hash"], "ts": d["ts"]} for d in batch], ordered=False)
    db.threats.create_index([("indicator", 1), ("ts", -1)])
    db.threats.create_index([("target", 1)])
    db.threats.create_index([("day", 1), ("category", 1)])
    db.threats.create_index([("threat_id", 1)], unique=True)
    timings["mongo"] = time.perf_counter() - t0

# ---------------- Cassandra ----------------
CQL = [
 "DROP KEYSPACE IF EXISTS lab18",
 "CREATE KEYSPACE lab18 WITH replication={'class':'SimpleStrategy','replication_factor':1}",
 """CREATE TABLE lab18.threats_by_indicator (indicator text, ts timestamp, threat_id bigint, category text,
    source text, target text, severity int, PRIMARY KEY ((indicator), ts, threat_id)) WITH CLUSTERING ORDER BY (ts DESC, threat_id ASC)""",
 """CREATE TABLE lab18.threats_by_target (target text, ts timestamp, threat_id bigint, indicator text,
    category text, severity int, PRIMARY KEY ((target), ts, threat_id)) WITH CLUSTERING ORDER BY (ts DESC, threat_id ASC)""",
 "CREATE TABLE lab18.daily_volume (day text, category text, cnt counter, PRIMARY KEY ((day), category))",
]

def load_cassandra():
    s = Cluster([CASS_HOST]).connect()
    for q in CQL:
        s.execute(q, timeout=60)
    ins1 = s.prepare("INSERT INTO lab18.threats_by_indicator (indicator,ts,threat_id,category,source,target,severity) VALUES (?,?,?,?,?,?,?)")
    ins2 = s.prepare("INSERT INTO lab18.threats_by_target (target,ts,threat_id,indicator,category,severity) VALUES (?,?,?,?,?,?)")
    upd = s.prepare("UPDATE lab18.daily_volume SET cnt = cnt + 1 WHERE day=? AND category=?")
    t0 = time.perf_counter()
    for batch in chunks(make_threats(), 5_000):
        a, b, c = [], [], []
        for d in batch:
            a.append((d["indicator"], d["ts"], d["threat_id"], d["category"], d["source"], d["target"], d["severity"]))
            b.append((d["target"], d["ts"], d["threat_id"], d["indicator"], d["category"], d["severity"]))
            c.append((d["day"], d["category"]))
        for stmt, args in ((ins1, a), (ins2, b), (upd, c)):
            for ok, res in execute_concurrent_with_args(s, stmt, args, concurrency=64, raise_on_first_error=True):
                pass
    timings["cassandra"] = time.perf_counter() - t0

# ---------------- Neo4j ----------------
def load_neo4j():
    drv = GraphDatabase.driver(NEO_URI, auth=NEO_AUTH)
    with drv.session() as s:
        s.run("MATCH (n) DETACH DELETE n").consume()
        s.run("CREATE CONSTRAINT ind_u IF NOT EXISTS FOR (i:Indicator) REQUIRE i.value IS UNIQUE").consume()
        s.run("CREATE CONSTRAINT tgt_u IF NOT EXISTS FOR (t:Target) REQUIRE t.id IS UNIQUE").consume()
        s.run("CREATE INDEX hit_day IF NOT EXISTS FOR ()-[r:HIT]-() ON (r.day)").consume()
        s.run("CREATE INDEX hit_tid IF NOT EXISTS FOR ()-[r:HIT]-() ON (r.threat_id)").consume()
        t0 = time.perf_counter()
        for batch in chunks(make_threats(), 5_000):
            rows = [{"i": d["indicator"], "c": d["category"], "t": d["target"], "tid": d["threat_id"], "src": d["source"],
                     "sev": d["severity"], "ts": d["ts"].isoformat(), "day": d["day"], "tx": d["tx_id"]} for d in batch]
            s.run("""UNWIND $rows AS r
                     MERGE (i:Indicator {value:r.i}) ON CREATE SET i.category=r.c
                     MERGE (t:Target {id:r.t})
                     CREATE (i)-[:HIT {threat_id:r.tid, source:r.src, severity:r.sev, ts:datetime(r.ts), day:r.day, tx_id:r.tx, category:r.c}]->(t)""",
                  rows=rows).consume()
        timings["neo4j"] = time.perf_counter() - t0
    drv.close()

if __name__ == "__main__":
    which = sys.argv[1:] or ["mongo", "cassandra", "neo4j"]
    for w in which:
        print("loading", w, flush=True)
        globals()["load_" + w]()
        print(f"  {w}: {timings[w]:.1f}s -> {N_THREATS/timings[w]:.0f} rows/s", flush=True)
    json.dump(timings, open("results/load_times.json", "w"), indent=2)
