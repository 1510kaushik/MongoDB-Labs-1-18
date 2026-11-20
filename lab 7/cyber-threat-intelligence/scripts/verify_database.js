print("Database:", db.getName());
for (const name of ["threats", "sources", "reports", "threat_source_links", "schema_metrics", "working_set_test", "performance_events"]) {
  const exists = db.getCollectionNames().includes(name);
  printjson({collection: name, exists, count: exists ? db.getCollection(name).countDocuments({}) : 0});
}
if (db.getCollectionNames().includes("threats")) {
  print("Sample threat record:");
  printjson(db.threats.findOne({}, {cve_id: 1, vendor_project: 1, product: 1, classification: 1, source: 1}));
}
