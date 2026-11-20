"""
Lab 3.2 - "Try it yourself"
Consider a scenario where a post has 10,000 comments. Explain why embedding
would be problematic and what alternative design you would use.

WHY EMBEDDING 10,000 COMMENTS IS PROBLEMATIC
----------------------------------------------
1. 16MB document size limit: MongoDB caps a single BSON document at 16MB.
   This script measures a realistic comment's encoded size and extrapolates
   to 10,000 of them to show how close (or over) that ceiling a single post
   document would land.
2. Constant document growth/rewrites: every new comment means re-writing
   the ENTIRE post document (WiredTiger must rewrite the whole record when
   an array field grows past its allocated space), causing document moves
   on disk and write amplification -- an $push that should be cheap becomes
   expensive as the array grows into the thousands.
3. Can't page/query comments independently: to show only the 20 most recent
   comments, MongoDB still has to read (and transfer over the wire) the
   WHOLE post document, including all 10,000 embedded comments -- there is
   no way to slice server-side and get server-side pagination without
   $slice tricks that only partly help, and updating one buried comment
   still means touching the whole array.
4. No independent indexing/sharding of comments: comments can't be
   indexed, queried, or sharded as their own entity if they only exist
   as an embedded array.

RECOMMENDED ALTERNATIVE: REFERENCED comments, indexed on post_id
------------------------------------------------------------------
Keep 'comments' as its OWN collection with a 'post_id' field, and put an
index on post_id. This lets us:
  - Paginate comments with .find({"post_id": ...}).skip().limit() instead
    of loading all 10,000 at once.
  - Insert a new comment as a small, independent document -- no rewriting
    of the parent post.
  - Optionally use the "Subset Pattern" as a hybrid: embed only the most
    recent N comments (e.g. 5) directly on the post for fast initial
    render, while the full history lives in the referenced 'comments'
    collection for pagination.

This script demonstrates both halves: (1) the size-limit math, and
(2) a working referenced + indexed + paginated implementation.
"""
import json
import os

from bson import json_util
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = "nosql_labs_ch3"
HERE = os.path.dirname(os.path.abspath(__file__))
BSON_DOC_LIMIT_BYTES = 16 * 1024 * 1024


def banner(text, width=70):
    print("\n" + "=" * width)
    print(text)
    print("=" * width)


def main():
    banner("Lab 3.2 Try It Yourself: The 10,000-Comment Problem")

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except ConnectionFailure as exc:
        raise SystemExit(f"[FATAL] Could not connect to MongoDB at {MONGO_URI}: {exc}")

    db = client[DB_NAME]

    # --- PART 1: Why embedding breaks down -- measure a realistic comment ---
    print("=== PART 1: Estimating the size of 10,000 embedded comments ===")
    import bson
    sample_comment = {
        "author": "reader1234",
        "text": "This is a fairly typical, medium-length blog comment that a "
                "real user might leave -- a couple of sentences of feedback.",
        "created": "2024-03-01T10:15:00Z",
        "likes": 12,
    }
    comment_bytes = len(bson.BSON.encode(sample_comment))
    projected_total = comment_bytes * 10_000
    print(f"  One typical embedded comment encodes to: {comment_bytes} bytes")
    print(f"  10,000 of them embedded in one post array: {projected_total:,} bytes "
          f"(~{projected_total / (1024*1024):.1f} MB)")
    print(f"  BSON hard document limit:                  {BSON_DOC_LIMIT_BYTES:,} bytes (16 MB)")
    if projected_total > BSON_DOC_LIMIT_BYTES:
        print("  [CONCLUSION] This single post document would EXCEED the 16MB limit "
              "and MongoDB would reject the write outright.")
    else:
        pct = projected_total / BSON_DOC_LIMIT_BYTES * 100
        print(f"  [CONCLUSION] This post document would already consume ~{pct:.0f}% of the "
              f"entire 16MB budget on comments alone. Well before that limit is ever hit, "
              f"you are paying for a whole-document rewrite on every single new comment, "
              f"and you cannot paginate or index comments independently of their post.")

    # --- PART 2: The recommended alternative, working end to end ---
    print("\n=== PART 2: Alternative - referenced comments, indexed + paginated ===")
    for name in ("busy_posts", "busy_post_comments"):
        if name in db.list_collection_names():
            db.drop_collection(name)
    posts_col = db["busy_posts"]
    comments_col = db["busy_post_comments"]

    post_id = posts_col.insert_one({
        "title": "A Post With a Lot of Comments",
        "author": "arjun",
        "created": "2024-03-01",
    }).inserted_id
    print(f"  Created 1 post: {post_id}")

    # Simulate a busy post: insert 500 comments (kept small for a fast demo;
    # the pattern is identical at 10,000).
    N = 500
    comments_col.insert_many([
        {"post_id": post_id, "seq": i, "author": f"reader{i % 50}", "text": f"Comment number {i}"}
        for i in range(N)
    ])
    comments_col.create_index("post_id")
    print(f"  Inserted {N} comments as independent documents (index created on post_id)")
    print("  -- inserting comment #501 costs exactly one small document write,")
    print("     not a rewrite of the whole post.")

    # Server-side pagination: get only the first page (20) of comments, sorted.
    page_size = 20
    print(f"\n  --- Paginated read: first {page_size} comments only (not all {N}) ---")
    first_page = list(
        comments_col.find({"post_id": post_id}, {"_id": 0, "seq": 1, "author": 1, "text": 1})
        .sort("seq", 1)
        .limit(page_size)
    )
    for c in first_page[:5]:
        print(f"     #{c['seq']:>3}  {c['author']:10} {c['text']}")
    print(f"     ... ({len(first_page)} of {N} loaded for this page)")

    # Subset pattern: embed only the most recent 3 comments on the post itself
    # for a fast initial render, while the full history stays referenced.
    recent = list(comments_col.find({"post_id": post_id}, {"_id": 0, "author": 1, "text": 1})
                   .sort("seq", -1).limit(3))
    posts_col.update_one({"_id": post_id}, {"$set": {"recent_comments": recent}})
    print(f"\n  --- Hybrid 'subset pattern': post also embeds its {len(recent)} most "
          f"recent comments for a fast first paint, full {N} stay referenced ---")
    post_doc = posts_col.find_one({"_id": post_id})
    for c in post_doc["recent_comments"]:
        print(f"     {c['author']:10} {c['text']}")

    # --- Export ---
    out = {
        "size_estimate": {
            "sample_comment_bytes": comment_bytes,
            "projected_10000_comments_bytes": projected_total,
            "bson_document_limit_bytes": BSON_DOC_LIMIT_BYTES,
            "would_exceed_limit": projected_total > BSON_DOC_LIMIT_BYTES,
        },
        "busy_posts": list(posts_col.find({})),
        "busy_post_comments_first_page": first_page,
        "busy_post_comments_total_count": comments_col.count_documents({"post_id": post_id}),
    }
    out_path = os.path.join(HERE, "busy_post_output.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=json_util.default)
    print(f"\n[OK] Exported size estimate + referenced/paginated demo -> {out_path}")

    banner("Lab 3.2 Try It Yourself Complete")


if __name__ == "__main__":
    main()
