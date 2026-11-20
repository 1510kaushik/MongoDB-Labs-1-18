# MongoDB Lab 9.1
## Measure Write Concern Latency

### Objective
Measure the impact of different MongoDB write concerns on write latency.

### Environment
- Python 3.14
- PyMongo 4.17.0
- MongoDB Replica Set: rs0
- Three voting data-bearing members
- One arbiter

### Experiment
Inserted 1,000 documents individually for each write concern.

| Write Concern | Average Latency |
|---|---:|
| w:1 | 2.813751 ms |
| w:majority | 6.113819 ms |
| w:all equivalent (w:3) | 4.142302 ms |

### Implementation
- service.py: Benchmark implementation
- write_concern_test.py: Standalone execution
- routes.py: Flask API endpoints
- run.py: Flask application launcher
- results/: JSON benchmark reports

### Important Note
MongoDB does not support a literal w:all write concern.
This experiment uses w:3 as an equivalent requiring
acknowledgement from all three voting data-bearing members.

The arbiter is excluded because it does not store data.

### Conclusion
The w:1 write concern demonstrated the lowest latency
in this experiment. The majority and w:3 configurations
required stronger acknowledgement guarantees and
showed higher latency in this particular run.

Results may vary depending on hardware, network,
replication timing and system load.
