"""Lab 16.2 - FraudQueryService: polyglot persistence over MongoDB, Cassandra, Neo4j.

* MongoDB   -> flexible lookups          (get_transaction)
* Cassandra -> time-ordered events       (get_user_profile)
* Neo4j     -> multi-hop traversal       (detect_fraud_rings)

Each backend is wrapped in a circuit breaker: after `failure_threshold`
consecutive failures the backend is skipped until `reset_timeout` seconds pass.
"""
import threading
import time
from typing import Any, Callable, Optional


class BackendUnavailable(Exception):
    """Raised when a backend's circuit is open."""


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 3,
                 reset_timeout: float = 30.0, clock: Callable[[], float] = time.monotonic):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._clock = clock
        self._failures = 0
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._opened_at is not None and \
                self._clock() - self._opened_at < self.reset_timeout

    def call(self, fn: Callable[[], Any]) -> Any:
        with self._lock:
            if self._opened_at is not None:
                if self._clock() - self._opened_at < self.reset_timeout:
                    raise BackendUnavailable(f"{self.name} circuit open")
                # timeout elapsed -> half-open: allow one trial call
        try:
            result = fn()
        except Exception:
            with self._lock:
                self._failures += 1
                if self._failures >= self.failure_threshold:
                    self._opened_at = self._clock()   # (re)open
            raise
        with self._lock:
            self._failures = 0
            self._opened_at = None
        return result


class FraudQueryService:
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017/?maxPoolSize=10",
                 cassandra_hosts=("127.0.0.1",), cassandra_keyspace: str = "fraud",
                 neo4j_uri: str = "bolt://localhost:7687", neo4j_auth=("neo4j", "password"),
                 *, mongo_client=None, cassandra_session=None, neo4j_driver=None,
                 failure_threshold: int = 3, reset_timeout: float = 30.0,
                 clock: Callable[[], float] = time.monotonic):
        """Pre-built clients can be injected (used by tests); otherwise real
        drivers are created lazily-imported with pooling configured."""
        if mongo_client is None:
            from pymongo import MongoClient
            mongo_client = MongoClient(mongo_uri, maxPoolSize=10,
                                       serverSelectionTimeoutMS=2000)
        if cassandra_session is None:
            from cassandra.cluster import Cluster
            cluster = Cluster(list(cassandra_hosts), executor_threads=4)
            cassandra_session = cluster.connect(cassandra_keyspace)
        if neo4j_driver is None:
            from neo4j import GraphDatabase
            neo4j_driver = GraphDatabase.driver(
                neo4j_uri, auth=neo4j_auth, max_connection_pool_size=20)

        self.mongo = mongo_client
        self.db = mongo_client["fraud"]
        self.cassandra = cassandra_session
        self.neo4j = neo4j_driver
        self.breakers = {n: CircuitBreaker(n, failure_threshold, reset_timeout, clock)
                         for n in ("mongodb", "cassandra", "neo4j")}

    # ---- queries ---------------------------------------------------------
    def get_transaction(self, txn_id: str) -> Optional[dict]:
        """MongoDB: full transaction document (amount, merchant, timestamp, risk_score)."""
        return self.breakers["mongodb"].call(
            lambda: self.db.transactions.find_one({"txn_id": txn_id}, {"_id": 0}))

    def get_user_profile(self, user_id: str, limit: int = 10) -> list:
        """Cassandra: user's most recent events, newest first."""
        def run():
            rows = self.cassandra.execute(
                "SELECT * FROM user_profiles WHERE user_id = %s "
                "ORDER BY event_time DESC LIMIT %s", (user_id, limit))
            return list(rows)
        return self.breakers["cassandra"].call(run)

    def detect_fraud_rings(self, user_id: str, max_hops: int = 3, limit: int = 50) -> list:
        """Neo4j: users reachable through TRANSFERRED_TO within max_hops."""
        if not isinstance(max_hops, int) or not 1 <= max_hops <= 6:
            raise ValueError("max_hops must be an integer between 1 and 6")
        # Cypher cannot parameterise path length, so the validated int is inlined.
        query = (f"MATCH path = (u:User {{id: $uid}})-[:TRANSFERRED_TO*1..{max_hops}]-"
                 f"(connected:User) RETURN path LIMIT $limit")

        def run():
            with self.neo4j.session() as session:
                return [record["path"] for record in session.run(query, uid=user_id, limit=limit)]
        return self.breakers["neo4j"].call(run)

    # ---- merged workflow -------------------------------------------------
    def analyze_transaction(self, txn_id: str, max_hops: int = 3) -> dict:
        """Full fraud analysis; a failing backend degrades the result instead of failing it."""
        report = {"txn_id": txn_id, "transaction": None, "recent_activity": None,
                  "fraud_ring": None, "errors": {}}
        try:
            report["transaction"] = self.get_transaction(txn_id)
        except Exception as e:
            report["errors"]["mongodb"] = str(e)
        txn = report["transaction"]
        if not txn:
            return report
        user_id = txn.get("user_id")
        for key, backend, fn in (
                ("recent_activity", "cassandra", lambda: self.get_user_profile(user_id)),
                ("fraud_ring", "neo4j", lambda: self.detect_fraud_rings(user_id, max_hops))):
            try:
                report[key] = fn()
            except Exception as e:
                report["errors"][backend] = str(e)
        risky = (txn.get("risk_score") or 0) >= 0.8
        ring_size = len(report["fraud_ring"] or [])
        report["flagged"] = risky or ring_size >= 5
        return report

    def close(self):
        for closer in (self.mongo.close, self.neo4j.close,
                       getattr(self.cassandra, "shutdown", lambda: None)):
            try:
                closer()
            except Exception:
                pass
