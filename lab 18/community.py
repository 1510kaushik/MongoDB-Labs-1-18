"""Activity 18.1: Neo4j community detection on co-targeting graph, cross-referenced with MongoDB transactions."""
import json, csv, collections
from pymongo import MongoClient
from neo4j import GraphDatabase
from common import *

drv = GraphDatabase.driver(NEO_URI, auth=NEO_AUTH)
mdb = MongoClient(MONGO_URI)["lab18"]
MIN_SHARED = 3  # two indicators are "linked" if they hit >= 3 common targets

with drv.session() as s:
    s.run("MATCH ()-[r:CO_TARGETS]->() DELETE r").consume()
    s.run("""MATCH (a:Indicator)-[:HIT]->(t:Target)<-[:HIT]-(b:Indicator) WHERE a.value < b.value
             WITH a, b, count(DISTINCT t) AS w WHERE w >= $m
             CREATE (a)-[:CO_TARGETS {w:w}]->(b)""", m=MIN_SHARED).consume()
    edges = s.run("MATCH ()-[r:CO_TARGETS]->() RETURN count(r) AS n").single()["n"]
    method = "gds.louvain"
    try:
        s.run("CALL gds.graph.drop('co', false)").consume()
        s.run("""CALL gds.graph.project('co', 'Indicator', {CO_TARGETS:{orientation:'UNDIRECTED', properties:'w'}})""").consume()
        s.run("CALL gds.louvain.write('co', {writeProperty:'community', relationshipWeightProperty:'w'})").consume()
        s.run("CALL gds.graph.drop('co')").consume()
    except Exception as e:  # fallback if GDS plugin missing: connected components over strong edges (pure Cypher + client)
        print("GDS unavailable, falling back to connected components:", str(e)[:120])
        method = "python connected-components"
        adj = collections.defaultdict(set)
        for r in s.run("MATCH (a)-[:CO_TARGETS]->(b) RETURN a.value AS a, b.value AS b"):
            adj[r["a"]].add(r["b"]); adj[r["b"]].add(r["a"])
        comp, cid = {}, 0
        for n in adj:
            if n in comp: continue
            stack = [n]; comp[n] = cid
            while stack:
                x = stack.pop()
                for y in adj[x]:
                    if y not in comp: comp[y] = cid; stack.append(y)
            cid += 1
        s.run("UNWIND $rows AS r MATCH (i:Indicator {value:r.v}) SET i.community=r.c",
              rows=[{"v": k, "c": v} for k, v in comp.items()]).consume()

    # community stats: size, internal edges, density, weighted degree vs. baseline
    rows = s.run("""MATCH (i:Indicator) WHERE i.community IS NOT NULL
                    WITH i.community AS c, collect(i) AS members
                    UNWIND members AS m
                    OPTIONAL MATCH (m)-[r:CO_TARGETS]-(o) WHERE o.community = c
                    WITH c, size(members) AS size, m, sum(coalesce(r.w,0)) AS wdeg, count(r) AS deg
                    WITH c, size, sum(deg)/2 AS edges, sum(wdeg)/2 AS wsum, collect(m.value) AS members
                    RETURN c, size, edges, wsum, members""").data()

stats = []
for r in rows:
    if r["size"] < 5: continue
    possible = r["size"] * (r["size"] - 1) / 2
    r["density"] = r["edges"] / possible
    r["avg_w"] = r["wsum"] / max(r["edges"], 1)
    stats.append(r)
n_ind = sum(r["size"] for r in rows)   # all indicators that have a community id
mean_d = edges / (n_ind * (n_ind - 1) / 2)          # whole-graph baseline density
for x in stats: x["lift"] = x["density"] / mean_d
# "unusually high" inter-connectivity: >=20% of possible pairs linked AND >=100x denser than the whole graph
flagged = [x for x in stats if x["density"] >= 0.2 and x["lift"] >= 100]
print("community size/density distribution (size>=5):", sorted((round(x["density"], 2), x["size"]) for x in stats)[-5:], "total", len(stats))

out = []
for x in sorted(flagged, key=lambda x: -x["wsum"]):
    members = x["members"]
    tids = [t["threat_id"] for t in mdb.threats.find({"indicator": {"$in": members}}, {"threat_id": 1})]
    agg = list(mdb.transactions.aggregate([
        {"$match": {"threat_id": {"$in": tids}}},
        {"$group": {"_id": None, "n": {"$sum": 1}, "total": {"$sum": "$amount"}, "avg": {"$avg": "$amount"},
                    "max": {"$max": "$amount"}, "cards": {"$addToSet": "$card_hash"}, "countries": {"$addToSet": "$country"}}}]))[0]
    camps = collections.Counter(d["campaign"] for d in mdb.threats.find({"indicator": {"$in": members}}, {"campaign": 1}))
    top_c, top_n = camps.most_common(1)[0]
    out.append({"community": x["c"], "indicators": x["size"], "co_target_edges": x["edges"], "density": round(x["density"], 3), "lift_vs_graph": round(x["lift"]),
                "avg_shared_targets": round(x["avg_w"], 2), "threat_events": agg["n"], "tx_total": round(agg["total"], 2),
                "tx_avg": round(agg["avg"], 2), "tx_max": round(agg["max"], 2), "distinct_cards": len(agg["cards"]),
                "countries": len(agg["countries"]), "ground_truth_campaign": top_c,
                "ground_truth_purity": round(top_n / sum(camps.values()), 3)})

base = list(mdb.transactions.aggregate([{"$group": {"_id": None, "avg": {"$avg": "$amount"}}}]))[0]["avg"]
res = {"method": method, "co_target_edges_total": edges, "min_shared_targets": MIN_SHARED, "communities_ge5": len(stats),
       "mean_density": round(mean_d, 4), "flagged": len(flagged), "baseline_tx_avg": round(base, 2), "flagged_communities": out}
json.dump(res, open("results/communities.json", "w"), indent=2)
with open("results/communities.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
print(json.dumps({k: v for k, v in res.items() if k != "flagged_communities"}, indent=1))
for o in out[:30]: print(o)
