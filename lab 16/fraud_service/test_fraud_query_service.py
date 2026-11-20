import os
import time
import unittest
from unittest.mock import MagicMock

from fraud_query_service import BackendUnavailable, CircuitBreaker, FraudQueryService


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make_service(clock=None, **kw):
    mongo, cass, neo = MagicMock(), MagicMock(), MagicMock()
    svc = FraudQueryService(mongo_client=mongo, cassandra_session=cass, neo4j_driver=neo,
                            clock=clock or time.monotonic, **kw)
    return svc, mongo, cass, neo


class TestQueries(unittest.TestCase):
    def test_get_transaction_uses_mongo(self):
        svc, mongo, _, _ = make_service()
        doc = {"txn_id": "T1", "amount": 99.5, "merchant": "ACME",
               "timestamp": "2026-01-01T00:00:00Z", "risk_score": 0.9}
        svc.db.transactions.find_one.return_value = doc
        self.assertEqual(svc.get_transaction("T1"), doc)
        self.assertEqual(svc.db.transactions.find_one.call_args[0][0], {"txn_id": "T1"})

    def test_get_user_profile_uses_cassandra_ordered_query(self):
        svc, _, cass, _ = make_service()
        cass.execute.return_value = iter([{"event": 2}, {"event": 1}])
        self.assertEqual(svc.get_user_profile("U1"), [{"event": 2}, {"event": 1}])
        cql, params = cass.execute.call_args[0]
        self.assertIn("ORDER BY event_time DESC", cql)
        self.assertEqual(params, ("U1", 10))

    def test_detect_fraud_rings_uses_neo4j(self):
        svc, _, _, neo = make_service()
        session = neo.session.return_value.__enter__.return_value
        session.run.return_value = [{"path": "p1"}, {"path": "p2"}]
        self.assertEqual(svc.detect_fraud_rings("U1", max_hops=2), ["p1", "p2"])
        query = session.run.call_args[0][0]
        self.assertIn("*1..2", query)
        self.assertEqual(session.run.call_args[1]["uid"], "U1")

    def test_max_hops_validated(self):
        svc, *_ = make_service()
        for bad in (0, 7, "3; DROP", None):
            with self.assertRaises(ValueError):
                svc.detect_fraud_rings("U1", bad)

    def test_merged_results(self):
        svc, _, cass, neo = make_service()
        svc.db.transactions.find_one.return_value = {"txn_id": "T1", "user_id": "U1", "risk_score": 0.2}
        cass.execute.return_value = [{"e": 1}]
        neo.session.return_value.__enter__.return_value.run.return_value = [{"path": i} for i in range(5)]
        r = svc.analyze_transaction("T1")
        self.assertEqual(r["recent_activity"], [{"e": 1}])
        self.assertEqual(len(r["fraud_ring"]), 5)
        self.assertTrue(r["flagged"])
        self.assertEqual(r["errors"], {})

    def test_graceful_degradation(self):
        svc, _, cass, neo = make_service()
        svc.db.transactions.find_one.return_value = {"txn_id": "T1", "user_id": "U1", "risk_score": 0.95}
        cass.execute.side_effect = RuntimeError("cassandra down")
        neo.session.return_value.__enter__.return_value.run.return_value = []
        r = svc.analyze_transaction("T1")
        self.assertIsNone(r["recent_activity"])
        self.assertIn("cassandra", r["errors"])
        self.assertTrue(r["flagged"])


class TestCircuitBreaker(unittest.TestCase):
    def test_opens_after_three_failures_and_retries_after_30s(self):
        clock = FakeClock()
        cb = CircuitBreaker("x", clock=clock)
        fail = MagicMock(side_effect=RuntimeError("boom"))
        for _ in range(3):
            with self.assertRaises(RuntimeError):
                cb.call(fail)
        with self.assertRaises(BackendUnavailable):
            cb.call(fail)
        self.assertEqual(fail.call_count, 3)          # 4th call skipped
        clock.t = 31
        self.assertEqual(cb.call(lambda: "ok"), "ok")  # half-open trial succeeds
        self.assertFalse(cb.is_open)

    def test_failed_trial_reopens(self):
        clock = FakeClock()
        cb = CircuitBreaker("x", clock=clock)
        fail = MagicMock(side_effect=RuntimeError)
        for _ in range(3):
            with self.assertRaises(RuntimeError):
                cb.call(fail)
        clock.t = 31
        with self.assertRaises(RuntimeError):
            cb.call(fail)
        with self.assertRaises(BackendUnavailable):
            cb.call(fail)

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker("x")
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                cb.call(MagicMock(side_effect=RuntimeError))
        cb.call(lambda: 1)
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                cb.call(MagicMock(side_effect=RuntimeError))
        self.assertFalse(cb.is_open)                   # never 3 consecutive

    def test_backends_are_independent(self):
        svc, _, cass, _ = make_service()
        cass.execute.side_effect = RuntimeError
        for _ in range(3):
            with self.assertRaises(RuntimeError):
                svc.get_user_profile("U1")
        with self.assertRaises(BackendUnavailable):
            svc.get_user_profile("U1")
        svc.db.transactions.find_one.return_value = {"txn_id": "T1"}
        self.assertEqual(svc.get_transaction("T1"), {"txn_id": "T1"})


class TestIntegrationWorkflow(unittest.TestCase):
    """Full fraud-analysis workflow against in-memory stand-ins for the three stores
    (a ring U1-U2-U3-U4-U5-U6 of transfers). Set FRAUD_LIVE=1 to run the same
    scenario against real databases seeded with this data (see README)."""

    def build_fakes(self):
        txns = {"T1": {"txn_id": "T1", "user_id": "U1", "amount": 9800, "merchant": "X", "risk_score": 0.4}}
        events = {"U1": [{"event_time": i, "amount": 100 * i} for i in range(1, 21)]}
        edges = {"U1": ["U2"], "U2": ["U1", "U3"], "U3": ["U2", "U4"], "U4": ["U3", "U5"],
                 "U5": ["U4", "U6"], "U6": ["U5"]}

        mongo = MagicMock()
        mongo.__getitem__.return_value.transactions.find_one.side_effect = \
            lambda q, proj=None: txns.get(q["txn_id"])

        cass = MagicMock()
        cass.execute.side_effect = lambda cql, p: sorted(
            events.get(p[0], []), key=lambda e: -e["event_time"])[:p[1]]

        def run(query, uid, limit):
            hops = int(query.split("*1..")[1].split("]")[0])
            seen, frontier = {uid}, {uid}
            for _ in range(hops):
                frontier = {n for u in frontier for n in edges[u]} - seen
                seen |= frontier
            return [{"path": u} for u in sorted(seen - {uid})][:limit]
        neo = MagicMock()
        neo.session.return_value.__enter__.return_value.run.side_effect = run
        return mongo, cass, neo

    def test_full_workflow_and_latency(self):
        mongo, cass, neo = self.build_fakes()
        svc = FraudQueryService(mongo_client=mongo, cassandra_session=cass, neo4j_driver=neo)
        start = time.perf_counter()
        r = svc.analyze_transaction("T1", max_hops=3)
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.assertEqual(r["transaction"]["amount"], 9800)
        self.assertEqual(len(r["recent_activity"]), 10)
        self.assertEqual(r["recent_activity"][0]["event_time"], 20)   # newest first
        self.assertEqual(r["fraud_ring"], ["U2", "U3", "U4"])
        self.assertFalse(r["flagged"])                                 # 3 linked, risk 0.4
        r5 = svc.analyze_transaction("T1", max_hops=5)
        self.assertEqual(len(r5["fraud_ring"]), 5)
        self.assertTrue(r5["flagged"])                                 # ring >= 5
        print(f"\n[in-memory workflow: {elapsed_ms:.2f} ms - measures service overhead only]")

    def test_unknown_transaction(self):
        mongo, cass, neo = self.build_fakes()
        svc = FraudQueryService(mongo_client=mongo, cassandra_session=cass, neo4j_driver=neo)
        r = svc.analyze_transaction("NOPE")
        self.assertIsNone(r["transaction"])
        cass.execute.assert_not_called()


@unittest.skipUnless(os.environ.get("FRAUD_LIVE") == "1", "set FRAUD_LIVE=1 with real databases running")
class TestLive(unittest.TestCase):
    def test_live_latency(self):
        svc = FraudQueryService()
        for name, fn in (("get_transaction", lambda: svc.get_transaction("T1")),
                         ("get_user_profile", lambda: svc.get_user_profile("U1")),
                         ("detect_fraud_rings(3)", lambda: svc.detect_fraud_rings("U1", 3))):
            fn()  # warm-up
            samples = []
            for _ in range(50):
                t = time.perf_counter()
                fn()
                samples.append((time.perf_counter() - t) * 1000)
            samples.sort()
            print(f"{name}: p50={samples[25]:.1f} ms p95={samples[47]:.1f} ms")


if __name__ == "__main__":
    unittest.main()
