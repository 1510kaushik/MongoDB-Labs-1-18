"""4 benchmark queries x 3 databases, 1 warm-up + 10 timed runs each (median reported)."""
import json, time, statistics as st, datetime as dt
from pymongo import MongoClient
from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent_with_args
from neo4j import GraphDatabase
from common import *

RUNS = 10
KEYS = [f"ioc-{5 + 97 * k:05d}" for k in range(RUNS + 1)]   # campaign indicators: non-trivial history & spread
CUTOFF_DAY = (END - dt.timedelta(days=30)).strftime("%Y-%m-%d")
DAYS30 = [(END - dt.timedelta(days=d)).strftime("%Y-%m-%d") for d in range(31)]

mdb = MongoClient(MONGO_URI)["lab18"]
cs = Cluster([CASS_HOST]).connect("lab18")
drv = GraphDatabase.driver(NEO_URI, auth=NEO_AUTH)
ns = drv.session()

# ---- Q1 threat history ------------------------------------------------------
def q1_mongo(k):
    return len(list(mdb.threats.find({"indicator": k}, {"_id": 0, "ts": 1, "target": 1, "severity": 1, "source": 1}).sort("ts", -1)))
_q1c = cs.prepare("SELECT ts,target,severity,source FROM threats_by_indicator WHERE indicator=?")
def q1_cass(k):
    return len(list(cs.execute(_q1c, (k,))))
def q1_neo(k):
    return len(ns.run("MATCH (i:Indicator {value:$k})-[r:HIT]->(t) RETURN r.ts AS ts, t.id AS target, r.severity AS sev, r.source AS src ORDER BY ts DESC", k=k).data())

# ---- Q2 target & spread: targets hit by IOC, then other IOCs co-targeting them (top 10)
def q2_mongo(k):
    tg = mdb.threats.distinct("target", {"indicator": k})
    r = list(mdb.threats.aggregate([{"$match": {"target": {"$in": tg}, "indicator": {"$ne": k}}},
                                    {"$group": {"_id": "$indicator", "t": {"$addToSet": "$target"}}},
                                    {"$project": {"n": {"$size": "$t"}}}, {"$sort": {"n": -1, "_id": 1}}, {"$limit": 10}]))
    return [(x["_id"], x["n"]) for x in r]
_q2a = cs.prepare("SELECT target FROM threats_by_indicator WHERE indicator=?")
_q2b = cs.prepare("SELECT indicator FROM threats_by_target WHERE target=?")
def q2_cass(k):
    tg = {r.target for r in cs.execute(_q2a, (k,))}
    seen = {}
    tl = list(tg)
    for (ok, rows), t in zip(execute_concurrent_with_args(cs, _q2b, [(t,) for t in tl], concurrency=32), tl):
        for r in rows:
            if r.indicator != k:
                seen.setdefault(r.indicator, set()).add(t)
    return sorted(((i, len(s)) for i, s in seen.items()), key=lambda x: (-x[1], x[0]))[:10]
def q2_neo(k):
    r = ns.run("""MATCH (i:Indicator {value:$k})-[:HIT]->(t)<-[:HIT]-(o:Indicator) WHERE o<>i
                  RETURN o.value AS v, count(DISTINCT t) AS n ORDER BY n DESC, v LIMIT 10""", k=k).data()
    return [(x["v"], x["n"]) for x in r]

# ---- Q3 daily volume analytics (last 30 days, per day x category) -----------
def q3_mongo(_):
    return list(mdb.threats.aggregate([{"$match": {"day": {"$gte": CUTOFF_DAY}}},
                                       {"$group": {"_id": {"d": "$day", "c": "$category"}, "n": {"$sum": 1}}}]))
_q3c = cs.prepare("SELECT day,category,cnt FROM daily_volume WHERE day=?")
def q3_cass(_):
    out = []
    for ok, rows in execute_concurrent_with_args(cs, _q3c, [(d,) for d in DAYS30], concurrency=31):
        out.extend(rows)
    return out
def q3_neo(_):
    return ns.run("MATCH ()-[r:HIT]->() WHERE r.day >= $d RETURN r.day AS d, r.category AS c, count(*) AS n", d=CUTOFF_DAY).data()

# ---- Q4 real-time insert throughput: 1,000-row batches of NEW threats --------
_BATCH = [list(make_threats(1000, 1_000_000 + 1000 * i, seed=99)) for i in range(RUNS + 1)]
def q4_mongo(i):
    mdb.threats.insert_many([{k: v for k, v in d.items() if k not in ("amount", "country", "channel", "card_hash")} for d in _BATCH[i]], ordered=False)
_c1 = cs.prepare("INSERT INTO threats_by_indicator (indicator,ts,threat_id,category,source,target,severity) VALUES (?,?,?,?,?,?,?)")
_c2 = cs.prepare("INSERT INTO threats_by_target (target,ts,threat_id,indicator,category,severity) VALUES (?,?,?,?,?,?)")
_c3 = cs.prepare("UPDATE daily_volume SET cnt = cnt + 1 WHERE day=? AND category=?")
def q4_cass(i):
    b = _BATCH[i]
    for stmt, args in ((_c1, [(d["indicator"], d["ts"], d["threat_id"], d["category"], d["source"], d["target"], d["severity"]) for d in b]),
                       (_c2, [(d["target"], d["ts"], d["threat_id"], d["indicator"], d["category"], d["severity"]) for d in b]),
                       (_c3, [(d["day"], d["category"]) for d in b])):
        list(execute_concurrent_with_args(cs, stmt, args, concurrency=64))
def q4_neo(i):
    rows = [{"i": d["indicator"], "c": d["category"], "t": d["target"], "tid": d["threat_id"], "src": d["source"],
             "sev": d["severity"], "ts": d["ts"].isoformat(), "day": d["day"], "tx": d["tx_id"]} for d in _BATCH[i]]
    ns.run("""UNWIND $rows AS r MERGE (i:Indicator {value:r.i}) ON CREATE SET i.category=r.c MERGE (t:Target {id:r.t})
              CREATE (i)-[:HIT {threat_id:r.tid, source:r.src, severity:r.sev, ts:datetime(r.ts), day:r.day, tx_id:r.tx, category:r.c}]->(t)""", rows=rows).consume()

BENCH = {
    "Q1 threat history": (q1_mongo, q1_cass, q1_neo),
    "Q2 target & spread": (q2_mongo, q2_cass, q2_neo),
    "Q3 daily volume (30d)": (q3_mongo, q3_cass, q3_neo),
    "Q4 insert 1,000 threats": (q4_mongo, q4_cass, q4_neo),
}

def timeit(fn, args):
    fn(args[0])  # warm-up (discarded)
    ts = []
    for a in args[1:]:
        t0 = time.perf_counter(); fn(a); ts.append((time.perf_counter() - t0) * 1000)
    return ts

if __name__ == "__main__":
    # sanity: the three engines must agree on answers
    for k in KEYS[:3]:
        a, b, c = q1_mongo(k), q1_cass(k), q1_neo(k)
        s1, s2, s3 = q2_mongo(k), q2_cass(k), q2_neo(k)
        assert a == b == c, ("Q1 mismatch", k, a, b, c)
        assert s1 == s2 == s3, ("Q2 mismatch", k, s1, s2, s3)
    m = {(x["_id"]["d"], x["_id"]["c"]): x["n"] for x in q3_mongo(0)}
    cc = {(r.day, r.category): r.cnt for r in q3_cass(0)}
    nn = {(x["d"], x["c"]): x["n"] for x in q3_neo(0)}
    assert m == cc == nn, "Q3 mismatch"
    print("cross-engine result check: Q1/Q2/Q3 identical on all three databases")

    res = {}
    for name, (fm, fc, fn) in BENCH.items():
        args = list(range(RUNS + 1)) if name.startswith("Q4") else (KEYS if name[:2] in ("Q1", "Q2") else [0] * (RUNS + 1))
        res[name] = {}
        for db, fn_ in (("MongoDB", fm), ("Cassandra", fc), ("Neo4j", fn)):
            ts = timeit(fn_, args)
            s = sorted(ts)
            res[name][db] = {"median_ms": st.median(ts), "min_ms": s[0], "max_ms": s[-1],
                             "p90_ms": s[int(0.9 * (len(s) - 1))], "runs_ms": [round(x, 2) for x in ts]}
            if name.startswith("Q4"):
                res[name][db]["throughput_rows_per_s"] = 1000 / (st.median(ts) / 1000)
            print(f"{name:26s} {db:10s} median={st.median(ts):9.2f} ms", flush=True)
    json.dump(res, open("results/bench.json", "w"), indent=2)
