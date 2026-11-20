"""Lab 17.2 - Compare HNSW and IVF vector indexes in MongoDB Atlas.

Steps: build 5,000 x 384-d docs -> for each index config: create index, time build,
run 100 queries, measure latency and recall@20 vs brute force -> table + CSV + curve PNG.

NOTE: index option syntax follows the lab text ("indexOption": hnsw / ivf). Atlas only exposes
the index types/options your cluster version supports; if an option is rejected the script
reports it and continues. At query time the tunable knob is numCandidates, so it is used as
the "efSearch" / "nprobe" analogue in the latency-recall sweep.
"""
import csv
import os
import random
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from datasets import load_dataset
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel
from sentence_transformers import SentenceTransformer

load_dotenv()
N_DOCS, N_QUERIES, TOP_K, DIM = 5000, 100, 20, 384
DB, COLL, IDX = "vector_lab", "docs", "bench_idx"
coll = MongoClient(os.environ["MONGODB_URI"])[DB][COLL]


def load_sentences(n):
    ds = load_dataset("Salesforce/wikitext", "wikitext-2-raw-v1", split="train")
    sents = set()
    for row in ds:
        for s in row["text"].replace("\n", " ").split(". "):
            s = s.strip()
            if 6 <= len(s.split()) <= 40 and "=" not in s:
                sents.add(s)
    sents = sorted(sents)
    random.Random(42).shuffle(sents)
    return sents[:n]


def prepare_data():
    if coll.count_documents({}) == N_DOCS:
        vecs = np.array([d["embedding"] for d in coll.find({}, {"embedding": 1}).sort("_id", 1)])
        return vecs
    coll.delete_many({})
    sents = load_sentences(N_DOCS)
    model = SentenceTransformer("all-MiniLM-L6-v2")  # 384 dims
    vecs = model.encode(sents, normalize_embeddings=True, show_progress_bar=True)
    docs = [{"_id": i, "text": s, "embedding": v.tolist()} for i, (s, v) in enumerate(zip(sents, vecs))]
    for i in range(0, len(docs), 500):
        coll.insert_many(docs[i:i + 500])
    return np.array(vecs)


def build_index(option):
    """Create index, return build time in seconds (until queryable)."""
    for i in coll.list_search_indexes():
        coll.drop_search_index(i["name"])
    while list(coll.list_search_indexes()):
        time.sleep(2)
    definition = {"fields": [{"type": "vector", "path": "embedding", "numDimensions": DIM,
                              "similarity": "cosine", **option}]}
    t0 = time.perf_counter()
    coll.create_search_index(SearchIndexModel(name=IDX, type="vectorSearch", definition=definition))
    while True:
        info = next(coll.list_search_indexes(IDX))
        if info["queryable"]:
            return time.perf_counter() - t0
        if info.get("status") == "FAILED":
            msg = (info.get("statusDetail") or [{}])[0].get("mainIndex", {}).get("message", "unknown")
            raise RuntimeError(f"index build FAILED: {msg}")
        time.sleep(1)


def evaluate(vecs, query_ids, truth, num_candidates):
    lats, recalls = [], []
    for qi, true_ids in zip(query_ids, truth):
        pipe = [{"$vectorSearch": {"index": IDX, "path": "embedding",
                                   "queryVector": vecs[qi].tolist(),
                                   "numCandidates": num_candidates, "limit": TOP_K}},
                {"$project": {"_id": 1}}]
        t0 = time.perf_counter()
        got = {d["_id"] for d in coll.aggregate(pipe)}
        lats.append((time.perf_counter() - t0) * 1000)
        recalls.append(len(got & true_ids) / TOP_K)
    return float(np.mean(lats)), float(np.mean(recalls) * 100)


def main():
    vecs = prepare_data()
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    query_ids = random.Random(1).sample(range(N_DOCS), N_QUERIES)
    # Brute-force ground truth: exact cosine over all 5,000 docs.
    sims = vecs[query_ids] @ vecs.T
    truth = [set(np.argsort(-row)[:TOP_K].tolist()) for row in sims]

    # (label, indexOption, params text, numCandidates values to sweep)
    configs = []
    for ef in (100, 128, 256, 512):  # Atlas requires numEdgeCandidates >= 100
        configs.append(("HNSW", {"indexingMethod": "hnsw",
                                 "hnswOptions": {"maxEdges": 16, "numEdgeCandidates": ef}},
                        f"M=16, efConstruction={ef}"))
    # IVF is not offered by Atlas/Atlas Local (indexingMethod must be flat or hnsw);
    # try it anyway so the script reports it, and add exact 'flat' as a baseline.
    configs.append(("IVF", {"indexingMethod": "ivf"}, "nlist=100"))
    configs.append(("FLAT", {"indexingMethod": "flat"}, "exact"))

    rows, curve = [], {"HNSW": [], "IVF": []}
    for kind, option, params in configs:
        try:
            build = build_index(option)
        except Exception as e:
            print(f"[skip] {kind} {params}: {e}")
            continue
        # Default row: numCandidates=200 (>= 10x limit, Atlas recommendation)
        lat, rec = evaluate(vecs, query_ids, truth, 200)
        rows.append([kind, params, round(build, 1), round(lat, 2), round(rec, 1)])
        print(rows[-1])
        # Latency-recall sweep. IVF: nprobe analogue = 10, 50, 100(=nlist) via numCandidates.
        sweep = (10, 50, 100, 200) if kind == "IVF" else (200,)
        for nc in sweep:
            nc_eff = max(nc, TOP_K)
            l, r = evaluate(vecs, query_ids, truth, nc_eff)
            label = f"{params}, nc={nc_eff}" if kind == "IVF" else params
            curve.setdefault(kind, []).append((l, r, label))

    with open("results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Index Type", "Parameters", "Build Time (s)", "Avg Query Latency (ms)", "Recall (%)"])
        w.writerows(rows)
    print("\n{:<6} {:<28} {:>10} {:>12} {:>10}".format(*["Type", "Params", "Build(s)", "Latency(ms)", "Recall(%)"]))
    for r in rows:
        print("{:<6} {:<28} {:>10} {:>12} {:>10}".format(*r))

    plt.figure(figsize=(7, 5))
    for kind, marker in (("HNSW", "o-"), ("IVF", "s--")):
        pts = sorted(curve[kind])
        if pts:
            plt.plot([p[0] for p in pts], [p[1] for p in pts], marker, label=kind)
            for l, r, lab in pts:
                plt.annotate(lab.split(",")[-1].strip(), (l, r), fontsize=7)
    plt.xlabel("Avg query latency (ms)")
    plt.ylabel("Recall@20 (%)")
    plt.title("Latency-recall trade-off: HNSW vs IVF")
    plt.grid(alpha=.3)
    plt.legend()
    plt.savefig("latency_recall.png", dpi=150, bbox_inches="tight")
    print("Saved results.csv and latency_recall.png")


if __name__ == "__main__":
    main()
