# Lab submission notes

## Lab 7.1 — Schema analysis
1. Import live CISA records and report index metadata.
2. Run `python -m backend.schema_analysis`.
3. Record average, minimum, maximum BSON size and count of documents >= 15 MiB for each collection.
4. Explain the schema decisions:
   - Embed small classification metadata in each threat because it is read together.
   - Reference sources because source records are shared by many threats.
   - Keep report body content out of threat documents to avoid duplication and oversized documents.
5. Compare baseline referencing with the embedded alternative in which each threat stores a compact `sources` array. Describe faster single-document detail reads versus harder publisher-wide updates and reverse lookups.

## Lab 7.2 — Working set and cache
1. Run `python -m backend.working_set_test` (100,000 synthetic docs, roughly 2 KB each).
2. Run `python -m backend.cache_monitor` in one terminal.
3. Run `python -m backend.random_reads` in another terminal.
4. Observe cache utilization and the interval hit-ratio estimate over time.
5. Record MongoDB version, host RAM, configured cache, dataset size, and actual observations.
6. Note that cache metrics and field names vary by MongoDB version. The script reports available fields and an approximate ratio based on counter deltas, not a guaranteed canonical hit-rate metric.

## Classification notes
CISA KEV membership is a source-backed classification for known exploited vulnerabilities. This is not a CVSS severity rating, and it does not claim that a particular organization is compromised. Report records are metadata links, not a verdict that the linked report confirms a particular threat.
