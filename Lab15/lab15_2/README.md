# Lab 15.2 - Data Migration Between Tenant Isolation Strategies

## 1. Objective

Demonstrate migration between:
1. Document-level tenant isolation.
2. Collection-per-tenant isolation.

Compare listing, task creation and cross-tenant analytics performance.

## 2. Environment

- Python 3.12
- MongoDB 7.0 replica set
- PyMongo
- Database: lab15_migration
- Five tenants
- 100 tasks per tenant
- Total: 500 tasks

## 3. Initial Document-Level Isolation

All tenant tasks were stored in one collection named `tasks`.

Each document contains:
- id
- tenant_id
- title
- status
- priority
- created_at

Seed results:

| Tenant | Documents |
|---|---:|
| tenant_001 | 100 |
| tenant_002 | 100 |
| tenant_003 | 100 |
| tenant_004 | 100 |
| tenant_005 | 100 |
| Total | 500 |

Seed validation: PASSED.

## 4. Migration to Collection-Per-Tenant

The migration script uses MongoDB aggregation with `$match` and `$out`.

For each tenant, a separate collection was created:

| Tenant | Collection | Documents |
|---|---|---:|
| tenant_001 | tasks_tenant_tenant_001 | 100 |
| tenant_002 | tasks_tenant_tenant_002 | 100 |
| tenant_003 | tasks_tenant_tenant_003 | 100 |
| tenant_004 | tasks_tenant_tenant_004 | 100 |
| tenant_005 | tasks_tenant_tenant_005 | 100 |

Migration results:
- Tenants migrated: 5
- Original documents: 500
- Migrated documents: 500
- Foreign documents found: 0
- All tenant validations: PASSED

The original shared collection was retained.

## 5. Migration Validation

For each tenant, the source document count was compared with the target collection count.

Validation also checked that each target collection contained only its intended tenant_id.

All five tenants passed:
- Source count = 100
- Target count = 100
- Foreign document count = 0

Total migration validation: PASSED.

## 6. Performance Benchmark Method

The benchmark script measures:
1. Listing a tenant's tasks.
2. Creating a task.
3. Cross-tenant analytics.

Measurement configuration:
- 100 iterations for listing.
- 100 iterations for task creation.
- 50 iterations for cross-tenant analytics.
- 10 warm-up operations per benchmark.
- Actual elapsed time measured with Python perf_counter_ns.
- Average, median, minimum and maximum times recorded.

The original and migrated data were checked for equivalent listing and analytics results before measuring.

Both strategies used appropriate indexes:
- Shared collection: tenant_id + created_at.
- Tenant-specific collections: created_at.

Task creation measurements include the insert operation only. Cleanup was outside the measured interval.

## 7. Measured Performance Results

All values below are actual measurements from the corrected benchmark run.

| Operation | Isolation strategy | Average (ms) | Median (ms) |
|---|---|---:|---:|
| List tenant tasks | Document-level | 3.2563 | 2.8655 |
| List tenant tasks | Collection-per-tenant | 2.8675 | 2.7592 |
| Create task | Document-level | 3.2982 | 2.8666 |
| Create task | Collection-per-tenant | 3.1991 | 2.9745 |
| Cross-tenant analytics | Document-level | 3.4222 | 3.3413 |
| Cross-tenant analytics | Collection-per-tenant | 11.6502 | 11.2493 |

### Performance Interpretation

**Task listing**

Collection-per-tenant was approximately 11.94% faster by average time. Its median improvement was smaller, so the difference should be considered modest for this dataset.

**Task creation**

The average times were close. The difference was approximately 3%, which is too small to establish a meaningful performance advantage from this experiment.

**Cross-tenant analytics**

Document-level isolation was substantially faster. It completed the measured operation in approximately one-third of the collection-per-tenant time.

The collection-per-tenant implementation performed separate aggregations over five collections and merged the results in Python.

### Benchmark Limitations

The experiment used only 500 documents and five tenants. These timings are specific to the test environment, index configuration and implementation.

They should not be treated as universal MongoDB performance guarantees. Larger datasets and different workload patterns may produce different results.

## 8. Architectural Comparison

| Consideration | Document-Level Isolation | Collection-Per-Tenant Isolation |
|---|---|---|
| Storage | One shared collection | Separate collection per tenant |
| Tenant filtering | Uses tenant_id in queries | Uses tenant-specific collection |
| Single-tenant listing | Requires tenant filter | Direct collection query |
| Cross-tenant analytics | One aggregation pipeline | Multiple collections or union operations |
| Backup granularity | Usually shared collection/database scope | Easier tenant-specific collection backup |
| Independent restore | More complex tenant-level restore | More straightforward collection-level restore |
| Schema evolution | Consistent shared schema | Requires managing schema changes across collections |
| Operational complexity | Lower with many tenants | Higher as tenant count grows |
| Isolation | Application-enforced tenant filtering | Stronger collection-level organization, but still requires authorization |

## 9. Recommendation

### Prefer Document-Level Isolation When:

- The application has frequent cross-tenant analytics.
- There are large numbers of tenants.
- A consistent schema is important.
- Most tenants share the same application features.
- Operational simplicity is a priority.

### Prefer Collection-Per-Tenant Isolation When:

- Tenants require independent backup and restore operations.
- Regulatory or contractual requirements demand stronger data separation.
- Individual tenants need different indexes or performance tuning.
- Tenant-specific schema differences are genuinely necessary.

### Final Recommendation

Most SaaS applications can begin with document-level isolation because it is simpler to operate and supports cross-tenant analytics efficiently.

Collection-per-tenant isolation becomes appropriate when independent backup, restore, data separation or per-tenant customization requirements justify the additional operational complexity.

For this experiment, document-level isolation was the stronger choice for cross-tenant analytics, while collection-per-tenant isolation showed a modest average advantage for listing tasks.

Neither strategy was conclusively better for task creation.

## 10. Final Verification

- Five tenants seeded: PASSED.
- 500 initial documents created: PASSED.
- Five tenant-specific collections created: PASSED.
- 500 documents migrated: PASSED.
- No cross-tenant migration leakage detected: PASSED.
- Listing results equivalent: PASSED.
- Analytics results equivalent: PASSED.
- Six performance measurements recorded: PASSED.
- Original and migrated data counts preserved: PASSED.

## 11. Project Files

- `.env` - Lab 15.2 database configuration.
- `.gitignore` - Excludes environment files and Python cache.
- `seed_data.py` - Creates five tenants and 500 tasks.
- `migrate_data.py` - Migrates documents into tenant-specific collections.
- `benchmark.py` - Compares both isolation strategies.
- `results/performance_benchmark.csv` - Benchmark measurements.
- `results/performance_benchmark.json` - Benchmark results in JSON format.
- `README.md` - Implementation, measured results and recommendation.

Lab 15.2 migration and performance experiment completed.
