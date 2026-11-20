"""Flask proxy for MongoDB Lab 15."""

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json

from flask import Blueprint, jsonify, request

lab15_bp = Blueprint("lab15", __name__, url_prefix="/api/lab15")

FASTAPI_URL = "http://127.0.0.1:8015"


def forward_request(path, method="GET", include_body=False):
    url = f"{FASTAPI_URL}{path}"

    headers = {"Accept": "application/json"}

    authorization = request.headers.get("Authorization")
    if authorization:
        headers["Authorization"] = authorization

    body = None
    if include_body:
        body = request.get_json(silent=True)
        if body is not None:
            body = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

    outgoing = Request(
        url,
        data=body,
        headers=headers,
        method=method
    )

    try:
        with urlopen(outgoing, timeout=10) as response:
            payload = response.read()
            result = json.loads(payload) if payload else {}
            return jsonify(result), response.status

    except HTTPError as exc:
        payload = exc.read()
        try:
            result = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            result = {"error": "FastAPI returned an unreadable response"}

        return jsonify(result), exc.code

    except (URLError, TimeoutError):
        return jsonify({
            "error": "Lab 15.1 API is unavailable. Start the FastAPI service on port 8015."
        }), 503


@lab15_bp.get("/health")
def lab15_health():
    return forward_request("/health")


@lab15_bp.post("/auth/register")
def lab15_register():
    return forward_request("/auth/register", "POST", True)


@lab15_bp.post("/auth/login")
def lab15_login():
    return forward_request("/auth/login", "POST", True)


@lab15_bp.get("/auth/me")
def lab15_me():
    return forward_request("/auth/me")


@lab15_bp.route("/tasks", methods=["GET", "POST"])
def lab15_tasks():
    if request.method == "POST":
        return forward_request("/tasks", "POST", True)

    query = request.query_string.decode("utf-8")
    path = "/tasks" + (f"?{query}" if query else "")
    return forward_request(path)


@lab15_bp.route("/tasks/<task_id>", methods=["GET", "PUT", "DELETE"])
def lab15_task_detail(task_id):
    path = f"/tasks/{task_id}"

    if request.method == "PUT":
        return forward_request(path, "PUT", True)

    return forward_request(path, request.method)
