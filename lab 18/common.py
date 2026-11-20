"""Shared config + deterministic synthetic threat generator for Lab 18."""
import random, datetime as dt, hashlib

MONGO_URI = "mongodb://mongo:27017"
CASS_HOST = "cassandra"
NEO_URI, NEO_AUTH = "bolt://neo4j:7687", ("neo4j", "lab18password")

N_THREATS = 100_000
N_INDICATORS = 20_000
N_TARGETS = 5_000
N_CAMPAIGNS = 25
DAYS = 90
SOURCES = ["urlhaus", "otx_alienvault", "abuseipdb", "phishtank", "threatfox", "openphish"]
CATEGORIES = ["malware_url", "phishing", "c2_ip", "botnet", "ransomware", "spam"]
COUNTRIES = ["US", "IN", "GB", "DE", "BR", "NG", "RU", "CN", "SG", "AU"]
CHANNELS = ["card_present", "ecommerce", "wire", "atm", "mobile"]
END = dt.datetime(2026, 11, 20, 0, 0, 0)  # "now" for the dataset


def make_threats(n=N_THREATS, start_id=0, seed=18):
    """Yield dicts. ~35% of events come from 25 planted campaigns (dense indicator<->target
    clusters) so the community-detection activity has a ground truth to recover."""
    rnd = random.Random(seed + start_id)
    ind_per_c, tgt_per_c = 40, 60
    camp_ind = [list(range(c * ind_per_c, (c + 1) * ind_per_c)) for c in range(N_CAMPAIGNS)]
    camp_tgt = [list(range(c * tgt_per_c, (c + 1) * tgt_per_c)) for c in range(N_CAMPAIGNS)]
    base = N_CAMPAIGNS * ind_per_c
    for i in range(n):
        tid = start_id + i
        if rnd.random() < 0.35:
            c = rnd.randrange(N_CAMPAIGNS)
            ind, tgt = rnd.choice(camp_ind[c]), rnd.choice(camp_tgt[c])
        else:
            c = -1
            ind = rnd.randrange(base, N_INDICATORS)
            tgt = rnd.randrange(N_CAMPAIGNS * tgt_per_c, N_TARGETS)
        cat = CATEGORIES[ind % len(CATEGORIES)]
        ts = END - dt.timedelta(seconds=rnd.randrange(DAYS * 86400))
        yield {
            "threat_id": tid,
            "indicator": f"ioc-{ind:05d}",
            "category": cat,
            "source": rnd.choice(SOURCES),
            "target": f"org-{tgt:04d}",
            "severity": rnd.randint(1, 10),
            "ts": ts,
            "day": ts.strftime("%Y-%m-%d"),
            "campaign": c,          # ground truth, NOT used by detection
            "tx_id": f"tx-{tid:07d}",
            "amount": round(rnd.lognormvariate(4.5 if c < 0 else 6.0, 1.0), 2),
            "country": rnd.choice(COUNTRIES),
            "channel": rnd.choice(CHANNELS),
            "card_hash": hashlib.md5(f"{tgt}-{rnd.randrange(300)}".encode()).hexdigest()[:12],
        }


def chunks(it, n):
    buf = []
    for x in it:
        buf.append(x)
        if len(buf) == n:
            yield buf
            buf = []
    if buf:
        yield buf
