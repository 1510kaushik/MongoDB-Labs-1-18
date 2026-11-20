const $ = (id) => document.getElementById(id);
let currentPage = 1;
let currentQuery = "";
let currentCategory = "";
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (value) => value == null ? "—" : Number(value).toLocaleString();
async function api(url, options={}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}
async function loadHealth() {
  try {
    const data = await api('/api/health');
    $('connection').textContent = `● DATABASE CONNECTED · ${data.database}`;
    $('connection').classList.add('ok');
  } catch (e) {
    $('connection').textContent = '● DATABASE OFFLINE';
    $('connection').classList.remove('ok');
  }
}
async function loadThreats() {
  const params = new URLSearchParams({page: currentPage, limit: 20});
  if (currentQuery) params.set('q', currentQuery);
  if (currentCategory) params.set('category', currentCategory);
  const body = $('threatRows');
  body.innerHTML = '<tr><td colspan="5" class="empty">Searching records…</td></tr>';
  try {
    const data = await api(`/api/threats?${params}`);
    $('threatCount').textContent = fmt(data.total);
    $('resultCount').textContent = `${fmt(data.total)} results · page ${data.page}`;
    $('prevPage').disabled = currentPage <= 1;
    $('nextPage').disabled = currentPage * data.limit >= data.total;
    if (!data.threats.length) {
      body.innerHTML = '<tr><td colspan="5" class="empty">No records found. Import real CISA data using “Sync CISA data”.</td></tr>';
      return;
    }
    body.innerHTML = data.threats.map(t => `<tr>
      <td><button class="link-button" data-cve="${esc(t.cve_id)}">${esc(t.cve_id)}</button><div style="margin-top:5px">${esc(t.vulnerability_name || t.short_description || 'Vulnerability record')}</div></td>
      <td>${esc(t.vendor_project || '—')}<div style="margin-top:5px;color:#8193aa">${esc(t.product || '')}</div></td>
      <td>${esc(t.date_added || '—')}</td>
      <td><span class="pill">${esc(t.classification?.category || 'Unclassified')}</span></td>
      <td><a class="source-link" href="${esc(t.source?.url || 'https://www.cisa.gov/known-exploited-vulnerabilities-catalog')}" target="_blank" rel="noopener">CISA ↗</a></td>
    </tr>`).join('');
    body.querySelectorAll('[data-cve]').forEach(btn => btn.addEventListener('click', () => showThreat(btn.dataset.cve)));
  } catch (e) {
    body.innerHTML = `<tr><td colspan="5" class="empty">${esc(e.message)}. Check MongoDB and start the backend.</td></tr>`;
  }
}
async function showThreat(cve) {
  try {
    const t = await api(`/api/threats/${encodeURIComponent(cve)}`);
    const rows = [
      ['Vendor / project', t.vendor_project], ['Product', t.product], ['Date added', t.date_added],
      ['Remediation due date', t.due_date], ['Ransomware campaign use', t.known_ransomware_campaign_use],
      ['Required action', t.required_action], ['Classification method', t.classification?.method],
      ['Severity', t.classification?.severity ?? 'Not assigned by importer']
    ];
    $('detailContent').innerHTML = `<p class="eyebrow">THREAT RECORD</p><h2 class="detail-title">${esc(t.cve_id)} · ${esc(t.vulnerability_name || 'Vulnerability')}</h2>
      <p class="detail-value">${esc(t.short_description || 'No description provided by the source.')}</p>
      <div class="detail-grid">${rows.map(([label,value]) => `<div class="detail-card"><div class="detail-label">${esc(label)}</div><div class="detail-value">${esc(value ?? '—')}</div></div>`).join('')}</div>
      <p class="detail-label">Source attribution</p><p><a class="source-link" href="${esc(t.source?.url || '')}" target="_blank" rel="noopener">${esc(t.source?.name || 'Original source')} ↗</a></p>`;
    $('detailDialog').showModal();
  } catch (e) { alert(e.message); }
}
async function loadReports() {
  const q = $('reportSearchInput').value.trim();
  try {
    const data = await api(`/api/reports?${new URLSearchParams({q, limit: 50})}`);
    $('reportCount').textContent = fmt(data.total);
    $('reportList').innerHTML = data.reports.length ? data.reports.map(r => `<div class="report-item">
      <a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title || r.url)} ↗</a>
      <p>${r.year ? `Year: ${esc(r.year)} · ` : ''}Discovered from curated report index</p>
      <p>${esc(r.url)}</p>
    </div>`).join('') : '<p class="empty">No report links found. Click “Discover reports” to import the public index.</p>';
  } catch(e) { $('reportList').innerHTML = `<p class="empty">${esc(e.message)}</p>`; }
}
async function loadMetrics() {
  try {
    const data = await api('/api/metrics/schema');
    const rows = data.collections || [];
    const threats = rows.find(x => x.collection === 'threats');
    $('schemaStatus').textContent = threats ? 'Measured' : 'Not run';
    $('avgBson').textContent = threats?.average_bytes != null ? `${fmt(Math.round(threats.average_bytes))} bytes` : 'Not measured';
    $('maxBson').textContent = threats?.max_bytes != null ? `${fmt(threats.max_bytes)} bytes` : 'Not measured';
    $('nearLimit').textContent = threats?.near_16_mib != null ? fmt(threats.near_16_mib) : 'Not measured';
  } catch(e) {}
  try {
    const data = await api('/api/metrics/cache');
    $('cacheCount').textContent = fmt(data.samples.length);
    const sample = data.samples[0];
    $('cacheUtil').textContent = sample?.cache_utilization != null ? `${(sample.cache_utilization * 100).toFixed(1)}%` : 'Not measured';
  } catch(e) {}
}

async function loadLab71() {
  try {
    const d = await api('/api/labs/7.1/schema-design');
    $('lab71Status').textContent = d.available ? 'Measured' : 'No experiment data';
    $('embeddedCount').textContent = fmt(d.embedded?.count);
    $('embeddedAvg').textContent = d.embedded?.average_bytes == null ? '—' : `${fmt(Math.round(d.embedded.average_bytes))} bytes`;
    $('referencedCount').textContent = fmt(d.referenced?.count);
    $('referencedAvg').textContent = d.referenced?.average_bytes == null ? '—' : `${fmt(Math.round(d.referenced.average_bytes))} bytes`;
    $('sizeReduction').textContent = d.average_document_reduction_bytes == null ? '—' : `${fmt(Math.round(d.average_document_reduction_bytes))} bytes (${Number(d.average_document_reduction_percent).toFixed(2)}%)`;
    $('referenceIntegrity').textContent = `${fmt(d.reference_integrity?.valid_references)} valid / ${fmt(d.reference_integrity?.missing_references)} missing`;
    $('lab71Note').textContent = d.note || 'BSON document measurements.';
  } catch (e) {
    $('lab71Status').textContent = 'Unavailable';
    $('lab71Note').textContent = e.message;
  }
}
async function loadReplicaSet() {
  try {
    const d = await api('/api/labs/8/replica-set');
    $('replicaSetName').textContent = d.set || 'Replica set';
    $('replicaPrimary').textContent = d.primary || 'No primary reported';
    $('replicaMembers').innerHTML = (d.members || []).map(m => `<div class="metric-line"><span>${esc(m.name || 'Member')} · ${esc(m.state || 'Unknown')}</span><strong>${m.health === 1 ? 'Healthy' : 'Unhealthy'}</strong></div>`).join('') || '<p class="empty">No members returned.</p>';
  } catch (e) {
    $('replicaSetName').textContent = 'Unavailable';
    $('replicaPrimary').textContent = '—';
    $('replicaMembers').innerHTML = `<p class="empty">${esc(e.message)}</p>`;
  }
}

$('searchForm').addEventListener('submit', e => { e.preventDefault(); currentPage=1; currentQuery=$('searchInput').value.trim(); currentCategory=$('categoryFilter').value; loadThreats(); });
$('prevPage').addEventListener('click', () => { if(currentPage>1){currentPage--;loadThreats();} });
$('nextPage').addEventListener('click', () => {currentPage++;loadThreats();});
$('reportSearchForm').addEventListener('submit', e => {e.preventDefault();loadReports();});
$('closeDialog').addEventListener('click', () => $('detailDialog').close());
$('refreshMetrics').addEventListener('click', loadMetrics);
$('syncCisa').addEventListener('click', async () => {
  $('syncMessage').textContent = 'Downloading official CISA feed…';
  $('syncCisa').disabled = true;
  try { const r=await api('/api/sync/cisa',{method:'POST'}); $('syncMessage').textContent=`CISA sync complete. Feed records: ${fmt(r.feed_count)}; inserted: ${fmt(r.inserted)}; updated: ${fmt(r.modified)}.`; await loadThreats(); await loadMetrics(); }
  catch(e){$('syncMessage').textContent=`CISA sync failed: ${e.message}`;}
  finally{$('syncCisa').disabled=false;}
});
$('syncReports').addEventListener('click', async () => {
  $('syncMessage').textContent = 'Checking the annual security report index…';
  $('syncReports').disabled = true;
  try {const r=await api('/api/sync/reports',{method:'POST'});$('syncMessage').textContent=`Report discovery complete. Links scanned: ${fmt(r.scanned)}; new records: ${fmt(r.inserted)}.`;await loadReports();}
  catch(e){$('syncMessage').textContent=`Report discovery failed: ${e.message}`;}
  finally{$('syncReports').disabled=false;}
});
loadHealth(); loadThreats(); loadReports(); loadMetrics(); loadLab71(); loadReplicaSet();
