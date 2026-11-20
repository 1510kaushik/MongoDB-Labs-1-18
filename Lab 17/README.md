# Lab 17 – RAG and Vector Index Comparison

## Setup
```
pip install -r requirements.txt
```
Create `.env`:
```
MONGODB_URI=mongodb+srv://...
VOYAGE_API_KEY=...
ANTHROPIC_API_KEY=...
```

## Lab 17.1 – RAG with conversation memory (`rag_pipeline.py`)
```
python rag_pipeline.py ingest      # 4 threat-intel docs -> 100-word chunks (20-word overlap) -> Voyage embeddings -> Atlas + vector index
python rag_pipeline.py chat alice  # multi-turn chat
```
- Retrieval: `$vectorSearch`, `numCandidates=20`, `limit=3`, returns text, source, score.
- Memory: `conversations` collection (`user_id`, `timestamp`, `role`, `content`). Each turn stores the user query and the reply; the last 5 exchanges (10 messages) are loaded and sent as prior chat turns.
- Try: ask "What is an IOC?" then "Why are they fragile?" – the second only works with memory.

## Lab 17.2 – HNSW vs IVF (`index_benchmark.py`)
```
python index_benchmark.py
```
Loads 5,000 Wikipedia sentences, embeds with `all-MiniLM-L6-v2` (384-d), and inserts in batches of 500. Builds HNSW (efConstruction 32/64/128/256, M=16) and IVF (nlist=100), runs 100 queries (random doc vectors) and computes recall@20 against numpy brute-force cosine. Outputs `results.csv` and `latency_recall.png`.

Caveats: Atlas may not accept IVF options on every cluster tier/version (the script skips and reports rejected configs); the query-time sweep uses `numCandidates` as the nprobe/efSearch analogue. Free (M0) clusters allow only a few search indexes, so the script drops existing indexes on the collection before each build.

## Recommendations (expected from lab)
- HNSW: recall-critical use (customer-facing search, RAG). ~95–99% recall at ~2–5 ms.
- IVF: very large datasets (millions) where memory overhead and sub-ms latency matter more than perfect recall; needs nprobe tuning.
- Fill in your own measured numbers in the table once you run the benchmark.
