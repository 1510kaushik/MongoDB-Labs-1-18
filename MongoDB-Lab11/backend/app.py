
from flask import Flask, jsonify, request
from pymongo.errors import PyMongoError
from bson import json_util

from .config import FLASK_HOST, FLASK_PORT, DATABASE_NAME
from .connection import client, db, check_connection
from .experiments import (
    get_shard_key_analysis,
    run_hotspot_experiment
)

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")

    allowed_origins = {
        "http://127.0.0.1:5000",
        "http://localhost:5000"
    }

    if origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"

    return response


def bson_response(data, status=200):
    """Serialize MongoDB BSON values safely as Extended JSON."""
    return app.response_class(
        response=json_util.dumps(data),
        status=status,
        mimetype="application/json"
    )


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "project": "MongoDB Lab 11 API",
        "version": "1.0",
        "status": "running",
        "endpoints": [
            "/api/lab11/health",
            "/api/lab11/cluster",
            "/api/lab11/analysis",
            "/api/lab11/run-hotspot"
        ]
    })


@app.route("/api/lab11/health", methods=["GET", "OPTIONS"])
def health():
    if request.method == "OPTIONS":
        return "", 204

    connection = check_connection()

    if not connection["connected"]:
        return jsonify({
            "status": "error",
            "service": "MongoDB Lab 11",
            "database": DATABASE_NAME,
            "connection": connection
        }), 503

    return jsonify({
        "status": "success",
        "service": "MongoDB Lab 11",
        "database": DATABASE_NAME,
        "connection": connection
    })


@app.route("/api/lab11/cluster", methods=["GET", "OPTIONS"])
def cluster_status():
    if request.method == "OPTIONS":
        return "", 204

    try:
        shards_result = client.admin.command({"listShards": 1})

        shards = [
            {
                "name": shard.get("_id"),
                "host": shard.get("host"),
                "state": shard.get("state")
            }
            for shard in shards_result.get("shards", [])
        ]

        return jsonify({
            "status": "success",
            "database": DATABASE_NAME,
            "shard_count": len(shards),
            "shards": shards
        })

    except PyMongoError as error:
        return jsonify({
            "status": "error",
            "message": str(error)
        }), 500


@app.route("/api/lab11/analysis", methods=["GET", "OPTIONS"])
def lab11_analysis():
    if request.method == "OPTIONS":
        return "", 204

    try:
        return jsonify({
            "status": "success",
            "result": get_shard_key_analysis()
        })

    except Exception as error:
        return jsonify({
            "status": "error",
            "message": str(error)
        }), 500


@app.route("/api/lab11/run-hotspot", methods=["POST", "OPTIONS"])
def lab11_run_hotspot():
    if request.method == "OPTIONS":
        return "", 204

    try:
        result = run_hotspot_experiment()

        if result.get("status") == "error":
            return bson_response(result, 500)

        return bson_response({
            "status": "success",
            "message": "Lab 11.2 experiment completed",
            "result": result
        })

    except Exception as error:
        return jsonify({
            "status": "error",
            "message": str(error)
        }), 500


if __name__ == "__main__":
    app.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=False
    )
