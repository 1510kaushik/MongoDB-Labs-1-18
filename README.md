# NoSQL Labs (7–18)

Portfolio of MongoDB, Cassandra, Neo4j and RAG labs.

| Folder | Topic |
|---|---|
| `cyber-threat-intelligence-project` | CTI dashboard (Labs 7.1/7.2); later labs integrated as Flask blueprints |
| `Lab8` | Replica set with arbiter |
| `MongoDB-Lab9` | Write concern latency |
| `MongoDB-Lab10` | Multi-document transactions |
| `MongoDB-Lab11` | Sharding and hotspot detection |
| `MongoDB-Lab12` | TLS and role-based access control |
| `MongoDB-Lab13` | Monitoring (Prometheus) and Kubernetes |
| `MongoDB-Lab14` | Monitoring service, backup and recovery |
| `MongoDB-Lab15` | Multi-tenant API and isolation migration |
| `lab 16` | Three database models, FraudQueryService |
| `Lab 17` | RAG and vector index benchmark |
| `lab 18` | MongoDB vs Cassandra vs Neo4j |

## Website
Open `website/index.html` in a browser. No build step.

## Before sharing or committing
- Secrets live in `.env` files and `certificates/**/*.key|pem`. They are excluded by `.gitignore`; rotate any that were ever shared (notably Lab 17's Atlas/API keys).
- `backups/` holds ~190 MB of database dumps that should not be zipped or committed.
- Superseded `*.backup` / `*.before_lab*` copies are ignored; delete them when you no longer need them.
