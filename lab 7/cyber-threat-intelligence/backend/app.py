from flask import Flask, jsonify, request, render_template
from pymongo.errors import PyMongoError
from bson import ObjectId
from .db import db, check_connection
from .config import FLASK_HOST, FLASK_PORT
from .lab9 import lab9_bp
from .lab10 import lab10_bp
from .lab12 import lab12_bp
from .lab13 import lab13_bp
from .lab14_1 import lab14_1_bp
from .lab15.routes import lab15_bp
from .ingest_cisa import import_cisa
from .ingest_reports import sync_reports

app = Flask(__name__, template_folder="../frontend", static_folder="../frontend", static_url_path="/static")

app.register_blueprint(lab9_bp)
app.register_blueprint(lab10_bp)
app.register_blueprint(lab12_bp)
app.register_blueprint(lab13_bp)
app.register_blueprint(lab14_1_bp)
app.register_blueprint(lab15_bp)


def bson_size_summary(collection):
    pipeline = [{"$group": {"_id": None, "count": {"$sum": 1}, "average_bytes": {"$avg": {"$bsonSize": "$$ROOT"}}, "min_bytes": {"$min": {"$bsonSize": "$$ROOT"}}, "max_bytes": {"$max": {"$bsonSize": "$$ROOT"}}, "total_bytes": {"$sum": {"$bsonSize": "$$ROOT"}}}}]
    result = list(collection.aggregate(pipeline))
    if not result:
        return {"count": 0, "average_bytes": None, "min_bytes": None, "max_bytes": None, "total_bytes": 0}
    result[0].pop("_id", None)
    return result[0]

def json_safe(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items() if k != "_id" or True}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value

@app.get("/")
def home():
    return render_template("index.html")

@app.get("/api/health")
def health():
    try:
        check_connection()
        return jsonify({"ok": True, "database": db.name})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503

@app.get("/api/threats")
def get_threats():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    page = max(1, request.args.get("page", default=1, type=int))
    limit = min(100, max(1, request.args.get("limit", default=20, type=int)))
    query = {}
    if category:
        query["classification.category"] = category
    if q:
        query["$or"] = [
            {"cve_id": {"$regex": q, "$options": "i"}},
            {"vendor_project": {"$regex": q, "$options": "i"}},
            {"product": {"$regex": q, "$options": "i"}},
            {"vulnerability_name": {"$regex": q, "$options": "i"}},
            {"short_description": {"$regex": q, "$options": "i"}}
        ]
    try:
        total = db.threats.count_documents(query)
        cursor = db.threats.find(query, {"notes": 0}).sort("date_added", -1).skip((page - 1) * limit).limit(limit)
        return jsonify({"total": total, "page": page, "limit": limit, "threats": [json_safe(x) for x in cursor]})
    except PyMongoError as exc:
        return jsonify({"error": str(exc)}), 503

@app.get("/api/threats/<cve_id>")
def threat_detail(cve_id):
    item = db.threats.find_one({"cve_id": cve_id})
    if not item:
        return jsonify({"error": "Threat not found"}), 404
    item.pop("_id", None)
    return jsonify(json_safe(item))

@app.get("/api/reports")
def get_reports():
    q = request.args.get("q", "").strip()
    query = {}
    if q:
        query = {"$or": [{"title": {"$regex": q, "$options": "i"}}, {"url": {"$regex": q, "$options": "i"}}]}
    page = max(1, request.args.get("page", default=1, type=int))
    limit = min(100, max(1, request.args.get("limit", default=20, type=int)))
    total = db.reports.count_documents(query)
    rows = db.reports.find(query, {"_id": 0}).sort("year", -1).skip((page - 1) * limit).limit(limit)
    return jsonify({"total": total, "reports": [json_safe(x) for x in rows]})

@app.get("/api/metrics/schema")
def schema_metrics():
    latest = db.schema_metrics.find_one(sort=[("measured_at", -1)])
    if latest:
        latest.pop("_id", None)
        return jsonify(json_safe(latest))
    return jsonify({"message": "No measurements yet. Run: python -m backend.schema_analysis", "collections": []})

@app.get("/api/metrics/cache")
def cache_metrics():
    rows = list(db.performance_events.find({}, {"_id": 0}).sort("timestamp", -1).limit(20))
    return jsonify({"samples": [json_safe(x) for x in rows]})


@app.get("/api/labs/7.1/schema-design")
def lab71_schema_design():
    try:
        embedded = bson_size_summary(db.lab71_threats_embedded)
        referenced = bson_size_summary(db.lab71_threats_referenced)
        sources = bson_size_summary(db.lab71_sources)
        integrity = list(db.lab71_threats_referenced.aggregate([
            {"$lookup": {"from": "lab71_sources", "localField": "source_id", "foreignField": "_id", "as": "matched_source"}},
            {"$group": {"_id": None, "total_threats": {"$sum": 1}, "valid_references": {"$sum": {"$cond": [{"$gt": [{"$size": "$matched_source"}, 0]}, 1, 0]}}}}
        ]))
        check = integrity[0] if integrity else {"total_threats": 0, "valid_references": 0}
        check.pop("_id", None)
        check["missing_references"] = check["total_threats"] - check["valid_references"]
        reduction = None
        reduction_pct = None
        if embedded.get("average_bytes") is not None and referenced.get("average_bytes") is not None:
            reduction = embedded["average_bytes"] - referenced["average_bytes"]
            reduction_pct = (reduction / embedded["average_bytes"] * 100) if embedded["average_bytes"] else None
        return jsonify({"available": embedded["count"] > 0 or referenced["count"] > 0, "embedded": embedded, "referenced": referenced, "sources": sources, "reference_integrity": check, "average_document_reduction_bytes": reduction, "average_document_reduction_percent": reduction_pct, "reference_total_bytes_including_sources": referenced["total_bytes"] + sources["total_bytes"], "note": "BSON document totals exclude index storage and operational overhead. Compare threat documents plus source documents; this is not a full on-disk storage measurement."})
    except PyMongoError as exc:
        return jsonify({"error": str(exc)}), 503

@app.get("/api/labs/8/replica-set")
def replica_set_status():
    try:
        status = db.client.admin.command({"replSetGetStatus": 1})
        members = []
        for member in status.get("members", []):
            members.append({"name": member.get("name"), "state": member.get("stateStr"), "health": member.get("health"), "uptime": member.get("uptime"), "optimeDate": json_safe(member.get("optimeDate"))})
        primary = next((m["name"] for m in members if m.get("state") == "PRIMARY"), None)
        return jsonify({"set": status.get("set"), "ok": status.get("ok"), "primary": primary, "members": members, "checked_at": json_safe(status.get("date"))})
    except Exception as exc:
        return jsonify({"available": False, "error": str(exc), "note": "Replica-set status could not be read from this connection."}), 503

@app.post("/api/sync/cisa")
def sync_cisa():
    try:
        return jsonify(import_cisa())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502

@app.post("/api/sync/reports")
def sync_reports_route():
    try:
        return jsonify(sync_reports())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502

if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False)



