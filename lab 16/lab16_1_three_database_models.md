# Lab 16.1 – University Course Enrollment in Three Databases

## 1. Schemas

### MongoDB (document model)
```js
// students
{ _id: "S1", name: "Alice", major: "CS",
  course_ids: ["C101", "C201"] }

// courses (embedded roster; denormalised name for display)
{ _id: "C101", title: "Intro to DB", credits: 3, prerequisites: [],
  roster: [ { student_id: "S1", name: "Alice", grade: null },
            { student_id: "S2", name: "Bob",   grade: null } ] }
```
Indexes: `students.course_ids` (multikey), `courses.roster.student_id`, `students.name`.

### Cassandra (query-driven: one table per query)
```sql
CREATE TABLE student_courses (
  student_id text, course_id text, course_title text, enrolled_at timestamp,
  PRIMARY KEY ((student_id), course_id));

CREATE TABLE course_students (
  course_id text, student_id text, student_name text, enrolled_at timestamp,
  PRIMARY KEY ((course_id), student_id));
```
Every enrollment is written to **both** tables (batch / application-level dual write).

### Neo4j (property graph)
```cypher
CREATE (:Student {id:'S1', name:'Alice'}), (:Student {id:'S2', name:'Bob'}),
       (:Course  {id:'C101', title:'Intro to DB'});
MATCH (s:Student {id:'S1'}), (c:Course {id:'C101'})
CREATE (s)-[:ENROLLED_IN {enrolled_at: datetime()}]->(c);
```
Constraints: `CREATE CONSTRAINT FOR (s:Student) REQUIRE s.id IS UNIQUE` (same for Course).

## 2. Equivalent queries

| Question | MongoDB | Cassandra | Neo4j (Cypher) |
|---|---|---|---|
| Courses for a student | `db.courses.find({"roster.student_id":"S1"})` or `db.students.findOne({_id:"S1"}).course_ids` | `SELECT course_id, course_title FROM student_courses WHERE student_id='S1';` | `MATCH (:Student {id:'S1'})-[:ENROLLED_IN]->(c) RETURN c.title` |
| Students in a course | `db.courses.findOne({_id:"C101"}).roster` | `SELECT student_id, student_name FROM course_students WHERE course_id='C101';` | `MATCH (s)-[:ENROLLED_IN]->(:Course {id:'C101'}) RETURN s.name` |
| Students sharing a course with Alice | see below | two queries + app-side join (see below) | `MATCH (a:Student {name:'Alice'})-[:ENROLLED_IN]->(c)<-[:ENROLLED_IN]-(o:Student) WHERE o <> a RETURN DISTINCT o.name` |

**MongoDB shared-course:**
```js
db.courses.aggregate([
  { $match: { "roster.student_id": "S1" } },
  { $unwind: "$roster" },
  { $match: { "roster.student_id": { $ne: "S1" } } },
  { $group: { _id: "$roster.student_id", name: { $first: "$roster.name" } } }
])
```
**Cassandra shared-course (application join):**
```python
courses = session.execute("SELECT course_id FROM student_courses WHERE student_id=%s", ["S1"])
others = set()
for c in courses:
    for r in session.execute("SELECT student_id FROM course_students WHERE course_id=%s", [c.course_id]):
        others.add(r.student_id)
others.discard("S1")
```
(N+1 queries; CQL has no joins.)

## 3. Comparison

| Aspect | MongoDB | Cassandra | Neo4j |
|---|---|---|---|
| Student→courses syntax | trivial `find` | trivial `SELECT` | trivial `MATCH` |
| Course→students syntax | trivial (embedded) | trivial (2nd table) | trivial |
| Shared-course syntax | moderate (aggregation pipeline) | worst (app-side join) | best (one pattern) |
| Performance, 1-hop lookups | very fast, single doc/index | fastest, single partition read | fast, index + pointer hop |
| Performance, shared-course | pipeline cost grows with roster size | N+1 round trips | traverses only local neighbourhood; cost independent of total data size |
| Write cost | update 2 docs (student + roster) | write 2 tables | create 1 relationship |
| Consistency / risk | duplication drift between embedded copies; 16 MB doc limit for huge rosters | duplication drift between tables; no multi-table atomicity beyond logged batch | normalised; no duplication |
| Scales best for | flexible documents, moderate scale | huge write volume, known queries | relationship-heavy, variable-depth queries |

**Takeaway:** all three answer the two simple queries in one statement; the relationship query separates them – Cypher is most natural and its cost follows the traversed subgraph rather than table size.

## 4. Activity – Hybrid architecture

```
           ┌────────────────────────── Application / API layer ──────────────────────────┐
           │  Enrollment service      Audit writer (async)        Prerequisite service    │
           └──────────┬─────────────────────┬──────────────────────────┬──────────────────┘
                      │                     │                          │
              ┌───────▼───────┐     ┌───────▼────────┐        ┌────────▼────────┐
              │   MongoDB     │     │   Cassandra    │        │     Neo4j       │
              │ operational   │     │ audit log      │        │ prerequisite    │
              │ students,     │     │ (append-only,  │        │ graph           │
              │ courses,      │     │ time-series)   │        │ (:Course)-      │
              │ enrollments   │     │                │        │ [:REQUIRES]->() │
              └───────┬───────┘     └───────▲────────┘        └────────▲────────┘
                      │  change streams / outbox events                 │
                      └─────────────────────┴───────────────────────────┘
```

**MongoDB – system of record.** `students`, `courses`, `enrollments` collections; transactional enrollment (multi-document transaction for seat count + enrollment).

**Cassandra – audit logging.**
```sql
CREATE TABLE audit_log (
  student_id text, day date, event_time timeuuid,
  action text, course_id text, actor text, details map<text,text>,
  PRIMARY KEY ((student_id, day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC)
  AND default_time_to_live = 189216000;  -- ~6 years
```
Day bucketing prevents unbounded partitions; append-only writes suit LSM storage.

**Neo4j – prerequisite chains.**
```cypher
// All prerequisites (transitive) of CS401
MATCH (c:Course {id:'CS401'})-[:REQUIRES*1..]->(p:Course) RETURN DISTINCT p.id;

// Is student S1 eligible for CS401? (missing prerequisites)
MATCH (c:Course {id:'CS401'})-[:REQUIRES*1..]->(p:Course)
WHERE NOT EXISTS { MATCH (:Student {id:'S1'})-[:COMPLETED]->(p) }
RETURN DISTINCT p.id AS missing;
```

**Data flow:** the enrollment service writes to MongoDB first; an outbox / change stream publishes events that (a) append to Cassandra `audit_log` and (b) update Neo4j `COMPLETED` relationships. Consumers are idempotent (event id as key), so the secondary stores are eventually consistent and can be rebuilt from MongoDB. A failure in Cassandra or Neo4j never blocks enrollment.
