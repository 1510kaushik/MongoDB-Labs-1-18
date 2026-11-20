"""Lab 17.1 - Simple RAG pipeline on MongoDB Atlas Vector Search, with conversation memory.

Env vars (put in .env or export):
  MONGODB_URI        Atlas connection string
  VOYAGE_API_KEY     Voyage AI embeddings
  GEMINI_API_KEY     LLM (Gemini) for generation
Usage:
  python rag_pipeline.py ingest        # chunk, embed, store, create vector index
  python rag_pipeline.py chat alice    # multi-turn chat as user "alice"
"""
import os
import sys
import time
from datetime import datetime, timezone

import voyageai
from google import genai
from google.genai import types
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

load_dotenv()
load_dotenv("key.env")

DB_NAME = "rag_lab"
CHUNKS = "chunks"
CONVOS = "conversations"
INDEX_NAME = "chunk_vector_index"
EMBED_MODEL = "voyage-3.5-lite"
EMBED_DIM = 1024
LLM_MODEL = "gemini-3.1-flash-lite"
CHUNK_WORDS = 100
OVERLAP_WORDS = 20
HISTORY_MESSAGES = 10  # last 5 exchanges = 10 messages (user + assistant)

db = MongoClient(os.environ["MONGODB_URI"])[DB_NAME]
voyage = voyageai.Client()
llm = genai.Client(api_key=os.environ.get("GEMINI_API_KEY") or os.environ["GEMINI_KEY"])

# ---- 1. Documents (Threat Intelligence) -------------------------------------
DOCUMENTS = {
    "threat_intel_overview": (
        "Cyber threat intelligence (CTI) is evidence-based knowledge about existing or emerging "
        "threats to an organization's assets. It includes context, mechanisms, indicators, "
        "implications and actionable advice. CTI is commonly divided into strategic, operational, "
        "tactical and technical levels. Strategic intelligence informs executives about long-term "
        "risk and adversary motivations. Operational intelligence describes specific campaigns and "
        "the nature of attacks. Tactical intelligence covers adversary tactics, techniques and "
        "procedures (TTPs), while technical intelligence provides concrete indicators such as "
        "malicious IP addresses, file hashes and domains that defenders can block or hunt for."
    ),
    "iocs": (
        "Indicators of compromise (IOCs) are forensic artifacts observed on a network or host that "
        "suggest a system has been breached. Common IOCs include file hashes of malware samples, "
        "command-and-control IP addresses and domains, suspicious registry keys, unusual outbound "
        "traffic patterns and anomalous login times. IOCs are easy to share and automate through "
        "formats such as STIX and feeds delivered over TAXII, but they are fragile: attackers can "
        "change an IP address or recompile a binary in minutes. For that reason IOCs should be "
        "paired with behavioral detections that survive infrastructure changes."
    ),
    "mitre_attack": (
        "The MITRE ATT&CK framework is a globally accessible knowledge base of adversary tactics and "
        "techniques based on real-world observations. Tactics represent the attacker's goal, such as "
        "initial access, persistence, privilege escalation, lateral movement and exfiltration. "
        "Techniques describe how a goal is achieved, for example phishing for initial access or "
        "credential dumping for credential access. Security teams map detections, red-team exercises "
        "and threat reports to ATT&CK to identify coverage gaps, prioritize defenses against the "
        "groups most likely to target them, and communicate with a common vocabulary."
    ),
    "threat_hunting": (
        "Threat hunting is the proactive search through networks and endpoints for adversaries that "
        "evade existing security solutions. Hunts typically begin with a hypothesis drawn from threat "
        "intelligence, such as a newly reported ransomware group abusing remote management tools. "
        "Analysts query logs, endpoint telemetry and network flows for matching behavior, validate "
        "findings, and then turn confirmed discoveries into automated detection rules. Effective "
        "hunting depends on good data collection, baseline knowledge of normal activity, and a "
        "feedback loop that feeds results back into the intelligence process."
    ),
}


def chunk_words(text, size=CHUNK_WORDS, overlap=OVERLAP_WORDS):
    """Simple sliding window over words."""
    words = text.split()
    step = size - overlap
    out = []
    for start in range(0, len(words), step):
        out.append(" ".join(words[start:start + size]))
        if start + size >= len(words):
            break
    return out


def embed(texts, input_type):
    return voyage.embed(texts, model=EMBED_MODEL, input_type=input_type).embeddings


# ---- 2. Ingest + index --------------------------------------------------------
def ingest():
    db[CHUNKS].delete_many({})
    rows = []
    for source, text in DOCUMENTS.items():
        for chunk in chunk_words(text):
            rows.append({"text": chunk, "source": source})
    vectors = embed([r["text"] for r in rows], "document")
    for r, v in zip(rows, vectors):
        r["embedding"] = v
    db[CHUNKS].insert_many(rows)
    print(f"Stored {len(rows)} chunks from {len(DOCUMENTS)} documents.")

    existing = [i["name"] for i in db[CHUNKS].list_search_indexes()]
    if INDEX_NAME not in existing:
        db[CHUNKS].create_search_index(SearchIndexModel(
            name=INDEX_NAME, type="vectorSearch",
            definition={"fields": [{"type": "vector", "path": "embedding",
                                    "numDimensions": EMBED_DIM, "similarity": "cosine"}]},
        ))
    print("Waiting for index to become queryable...")
    while not next(i for i in db[CHUNKS].list_search_indexes(INDEX_NAME))["queryable"]:
        time.sleep(3)
    print("Index ready.")


# ---- 3. Retrieval -----------------------------------------------------------
def retrieve(query, k=3):
    qvec = embed([query], "query")[0]
    pipeline = [
        {"$vectorSearch": {"index": INDEX_NAME, "path": "embedding", "queryVector": qvec,
                           "numCandidates": 20, "limit": k}},
        {"$project": {"_id": 0, "text": 1, "source": 1,
                      "score": {"$meta": "vectorSearchScore"}}},
    ]
    return list(db[CHUNKS].aggregate(pipeline))


# ---- Conversation memory ----------------------------------------------------
def save_message(user_id, role, content):
    db[CONVOS].insert_one({"user_id": user_id, "timestamp": datetime.now(timezone.utc),
                           "role": role, "content": content})


def load_history(user_id, n=HISTORY_MESSAGES):
    msgs = list(db[CONVOS].find({"user_id": user_id}, {"_id": 0, "role": 1, "content": 1})
                .sort("timestamp", -1).limit(n))
    return msgs[::-1]  # oldest first


# ---- 4. Generation ----------------------------------------------------------
def answer(user_id, query):
    history = load_history(user_id)  # fetch BEFORE saving the new query
    chunks = retrieve(query)
    context = "\n\n".join(f"[{c['source']}] {c['text']}" for c in chunks)
    prompt = (f"Answer based on these documents:\n{context}\n\n"
              f"If the documents don't contain the answer, say so.\n\nQuestion: {query}")
    contents = [types.Content(role="model" if m["role"] == "assistant" else "user",
                              parts=[types.Part(text=m["content"])]) for m in history]
    contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))
    resp = llm.models.generate_content(model=LLM_MODEL, contents=contents)
    reply = resp.text
    # Store the plain query (not the bulky prompt) so history stays compact.
    save_message(user_id, "user", query)
    save_message(user_id, "assistant", reply)
    return reply, chunks


def chat(user_id):
    print(f"Chatting as '{user_id}'. Ctrl+C or empty line to quit.")
    while True:
        q = input("\nYou: ").strip()
        if not q:
            break
        reply, chunks = answer(user_id, q)
        print("Sources:", ", ".join(f"{c['source']} ({c['score']:.3f})" for c in chunks))
        print("Assistant:", reply)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "chat"
    if cmd == "ingest":
        ingest()
    else:
        chat(sys.argv[2] if len(sys.argv) > 2 else "demo_user")
