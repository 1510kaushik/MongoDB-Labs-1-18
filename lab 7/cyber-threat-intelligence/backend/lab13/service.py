import json
import os
import subprocess
from pathlib import Path

import requests


LAB13_ROOT = Path.home() / "Downloads" / "MongoDB-Lab13"
DOCKER_COMPOSE = LAB13_ROOT / "docker" / "docker-compose.yml"
PROMETHEUS_URL = os.getenv("LAB13_PROMETHEUS_URL", "http://127.0.0.1:9090")


def run_command(command, timeout=15):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
        if result.returncode != 0:
            return {
                "success": False,
                "error": (result.stderr or result.stdout).strip()[:1000]
            }
        return {"success": True, "output": result.stdout.strip()}
    except FileNotFoundError:
        return {"success": False, "error": f"Command not found: {command[0]}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out"}
    except Exception as error:
        return {"success": False, "error": f"{type(error).__name__}: {error}"}


def get_docker_status():
    if not DOCKER_COMPOSE.exists():
        return {
            "status": "unavailable",
            "message": "Lab 13 Docker Compose file was not found.",
            "containers": []
        }

    result = run_command([
        "docker", "compose",
        "-f", str(DOCKER_COMPOSE),
        "ps", "--format", "json"
    ])

    if not result["success"]:
        return {
            "status": "unavailable",
            "message": result["error"],
            "containers": []
        }

    containers = []
    for line in result["output"].splitlines():
        try:
            item = json.loads(line)
            containers.append({
                "name": item.get("Name", item.get("Service", "unknown")),
                "service": item.get("Service", "unknown"),
                "state": item.get("State", "unknown"),
                "health": item.get("Health", "not reported"),
                "status": item.get("Status", "not reported")
            })
        except json.JSONDecodeError:
            continue

    running = sum(1 for item in containers if item["state"].lower() == "running")
    all_running = bool(containers) and running == len(containers)

    return {
        "status": "success" if all_running else "warning",
        "message": f"{running} of {len(containers)} Lab 13 containers are running.",
        "running": running,
        "total": len(containers),
        "containers": containers
    }


def get_prometheus_status():
    try:
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": "mongodb_up"},
            timeout=5
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("status") != "success":
            raise RuntimeError("Prometheus did not return a successful query.")

        results = payload.get("data", {}).get("result", [])
        metrics = [
            {
                "labels": item.get("metric", {}),
                "value": item.get("value", [None, None])[1]
            }
            for item in results
        ]

        return {
            "status": "success" if metrics else "warning",
            "message": "MongoDB exporter metrics retrieved." if metrics else
                       "Prometheus is reachable, but mongodb_up returned no series.",
            "metrics": metrics
        }
    except Exception as error:
        return {
            "status": "unavailable",
            "message": f"{type(error).__name__}: {error}",
            "metrics": []
        }


def get_kubernetes_status():
    namespace = "lab13"

    pods_result = run_command([
        "kubectl", "get", "pods", "-n", namespace, "-o", "json"
    ])
    pvc_result = run_command([
        "kubectl", "get", "pvc", "-n", namespace, "-o", "json"
    ])
    statefulset_result = run_command([
        "kubectl", "get", "statefulset", "mongo",
        "-n", namespace, "-o", "json"
    ])

    if not pods_result["success"]:
        return {
            "status": "unavailable",
            "message": pods_result["error"],
            "pods": [],
            "pvcs": [],
            "statefulset": {}
        }

    try:
        pod_data = json.loads(pods_result["output"])
        pods = []
        for item in pod_data.get("items", []):
            statuses = item.get("status", {}).get("containerStatuses", [])
            pods.append({
                "name": item.get("metadata", {}).get("name", "unknown"),
                "phase": item.get("status", {}).get("phase", "Unknown"),
                "ready": all(s.get("ready", False) for s in statuses) if statuses else False,
                "restarts": sum(s.get("restartCount", 0) for s in statuses)
            })

        pvcs = []
        if pvc_result["success"]:
            pvc_data = json.loads(pvc_result["output"])
            for item in pvc_data.get("items", []):
                pvcs.append({
                    "name": item.get("metadata", {}).get("name", "unknown"),
                    "status": item.get("status", {}).get("phase", "Unknown"),
                    "capacity": item.get("status", {}).get("capacity", {}).get("storage", "not reported")
                })

        statefulset = {}
        if statefulset_result["success"]:
            data = json.loads(statefulset_result["output"])
            spec = data.get("spec", {})
            status = data.get("status", {})
            statefulset = {
                "name": data.get("metadata", {}).get("name", "mongo"),
                "desired_replicas": spec.get("replicas", 0),
                "ready_replicas": status.get("readyReplicas", 0),
                "current_replicas": status.get("currentReplicas", 0)
            }

        ready_count = sum(
            1 for pod in pods
            if pod["phase"] == "Running" and pod["ready"]
        )
        healthy = bool(pods) and ready_count == len(pods)

        return {
            "status": "success" if healthy else "warning",
            "message": f"{ready_count} of {len(pods)} Kubernetes pods are ready.",
            "ready": ready_count,
            "total": len(pods),
            "pods": pods,
            "pvcs": pvcs,
            "statefulset": statefulset,
            "pvc_query_available": pvc_result["success"],
            "statefulset_query_available": statefulset_result["success"]
        }

    except Exception as error:
        return {
            "status": "error",
            "message": f"{type(error).__name__}: {error}",
            "pods": [],
            "pvcs": [],
            "statefulset": {}
        }


def get_lab13_status():
    docker = get_docker_status()
    prometheus = get_prometheus_status()
    kubernetes = get_kubernetes_status()

    return {
        "lab": "Lab 13",
        "docker": docker,
        "prometheus": prometheus,
        "kubernetes": kubernetes
    }
