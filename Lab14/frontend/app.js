const $ = (id) => document.getElementById(id);
let currentPage = 1;
let currentQuery = "";
let currentCategory = "";
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (value) => value == null ? "Ã¢â‚¬â€" : Number(value).toLocaleString();
async function api(url, options={}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || body.message || `Request failed (${response.status})`);
  return body;
}
async function loadHealth() {
  try {
    const data = await api('/api/health');
    $('connection').textContent = `Ã¢â€”Â DATABASE CONNECTED Ã‚Â· ${data.database}`;
    $('connection').classList.add('ok');
  } catch (e) {
    $('connection').textContent = 'Ã¢â€”Â DATABASE OFFLINE';
    $('connection').classList.remove('ok');
  }
}
async function loadThreats() {
  const params = new URLSearchParams({page: currentPage, limit: 20});
  if (currentQuery) params.set('q', currentQuery);
  if (currentCategory) params.set('category', currentCategory);
  const body = $('threatRows');
  body.innerHTML = '<tr><td colspan="5" class="empty">Searching recordsÃ¢â‚¬Â¦</td></tr>';
  try {
    const data = await api(`/api/threats?${params}`);
    $('threatCount').textContent = fmt(data.total);
    $('resultCount').textContent = `${fmt(data.total)} results Ã‚Â· page ${data.page}`;
    $('prevPage').disabled = currentPage <= 1;
    $('nextPage').disabled = currentPage * data.limit >= data.total;
    if (!data.threats.length) {
      body.innerHTML = '<tr><td colspan="5" class="empty">No records found. Import real CISA data using Ã¢â‚¬Å“Sync CISA dataÃ¢â‚¬Â.</td></tr>';
      return;
    }
    body.innerHTML = data.threats.map(t => `<tr>
      <td><button class="link-button" data-cve="${esc(t.cve_id)}">${esc(t.cve_id)}</button><div style="margin-top:5px">${esc(t.vulnerability_name || t.short_description || 'Vulnerability record')}</div></td>
      <td>${esc(t.vendor_project || 'Ã¢â‚¬â€')}<div style="margin-top:5px;color:#8193aa">${esc(t.product || '')}</div></td>
      <td>${esc(t.date_added || 'Ã¢â‚¬â€')}</td>
      <td><span class="pill">${esc(t.classification?.category || 'Unclassified')}</span></td>
      <td><a class="source-link" href="${esc(t.source?.url || 'https://www.cisa.gov/known-exploited-vulnerabilities-catalog')}" target="_blank" rel="noopener">CISA Ã¢â€ â€”</a></td>
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
    $('detailContent').innerHTML = `<p class="eyebrow">THREAT RECORD</p><h2 class="detail-title">${esc(t.cve_id)} Ã‚Â· ${esc(t.vulnerability_name || 'Vulnerability')}</h2>
      <p class="detail-value">${esc(t.short_description || 'No description provided by the source.')}</p>
      <div class="detail-grid">${rows.map(([label,value]) => `<div class="detail-card"><div class="detail-label">${esc(label)}</div><div class="detail-value">${esc(value ?? 'Ã¢â‚¬â€')}</div></div>`).join('')}</div>
      <p class="detail-label">Source attribution</p><p><a class="source-link" href="${esc(t.source?.url || '')}" target="_blank" rel="noopener">${esc(t.source?.name || 'Original source')} Ã¢â€ â€”</a></p>`;
    $('detailDialog').showModal();
  } catch (e) { alert(e.message); }
}
async function loadReports() {
  const q = $('reportSearchInput').value.trim();
  try {
    const data = await api(`/api/reports?${new URLSearchParams({q, limit: 50})}`);
    $('reportCount').textContent = fmt(data.total);
    $('reportList').innerHTML = data.reports.length ? data.reports.map(r => `<div class="report-item">
      <a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title || r.url)} Ã¢â€ â€”</a>
      <p>${r.year ? `Year: ${esc(r.year)} Ã‚Â· ` : ''}Discovered from curated report index</p>
      <p>${esc(r.url)}</p>
    </div>`).join('') : '<p class="empty">No report links found. Click Ã¢â‚¬Å“Discover reportsÃ¢â‚¬Â to import the public index.</p>';
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
    $('embeddedAvg').textContent = d.embedded?.average_bytes == null ? 'Ã¢â‚¬â€' : `${fmt(Math.round(d.embedded.average_bytes))} bytes`;
    $('referencedCount').textContent = fmt(d.referenced?.count);
    $('referencedAvg').textContent = d.referenced?.average_bytes == null ? 'Ã¢â‚¬â€' : `${fmt(Math.round(d.referenced.average_bytes))} bytes`;
    $('sizeReduction').textContent = d.average_document_reduction_bytes == null ? 'Ã¢â‚¬â€' : `${fmt(Math.round(d.average_document_reduction_bytes))} bytes (${Number(d.average_document_reduction_percent).toFixed(2)}%)`;
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
    $('replicaMembers').innerHTML = (d.members || []).map(m => `<div class="metric-line"><span>${esc(m.name || 'Member')} Ã‚Â· ${esc(m.state || 'Unknown')}</span><strong>${m.health === 1 ? 'Healthy' : 'Unhealthy'}</strong></div>`).join('') || '<p class="empty">No members returned.</p>';
  } catch (e) {
    $('replicaSetName').textContent = 'Unavailable';
    $('replicaPrimary').textContent = 'Ã¢â‚¬â€';
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
  $('syncMessage').textContent = 'Downloading official CISA feedÃ¢â‚¬Â¦';
  $('syncCisa').disabled = true;
  try { const r=await api('/api/sync/cisa',{method:'POST'}); $('syncMessage').textContent=`CISA sync complete. Feed records: ${fmt(r.feed_count)}; inserted: ${fmt(r.inserted)}; updated: ${fmt(r.modified)}.`; await loadThreats(); await loadMetrics(); }
  catch(e){$('syncMessage').textContent=`CISA sync failed: ${e.message}`;}
  finally{$('syncCisa').disabled=false;}
});
$('syncReports').addEventListener('click', async () => {
  $('syncMessage').textContent = 'Checking the annual security report indexÃ¢â‚¬Â¦';
  $('syncReports').disabled = true;
  try {const r=await api('/api/sync/reports',{method:'POST'});$('syncMessage').textContent=`Report discovery complete. Links scanned: ${fmt(r.scanned)}; new records: ${fmt(r.inserted)}.`;await loadReports();}
  catch(e){$('syncMessage').textContent=`Report discovery failed: ${e.message}`;}
  finally{$('syncReports').disabled=false;}
});
loadHealth(); loadThreats(); loadReports(); loadMetrics(); loadLab71(); loadReplicaSet();

// ==========================================
// LAB 9.1 - WRITE CONCERN LATENCY BENCHMARK
// ==========================================

function renderLab91(report) {
  const results = report.results || {};
  const keys = ["w:1", "w:majority", "w:all"];

  const labels = {
    "w:1": "w:1",
    "w:majority": "w:majority",
    "w:all": "All data-bearing members"
  };

  const values = keys.map(key => Number(results[key]?.average_latency_ms || 0));
  const maxValue = Math.max(...values, 0.001);

  $("lab91W1").textContent =
    results["w:1"] ? `${values[0].toFixed(3)} ms` : "Ã¢â‚¬â€";

  $("lab91Majority").textContent =
    results["w:majority"] ? `${values[1].toFixed(3)} ms` : "Ã¢â‚¬â€";

  $("lab91All").textContent =
    results["w:all"] ? `${values[2].toFixed(3)} ms` : "Ã¢â‚¬â€";

  $("lab91Chart").innerHTML = keys.map((key, index) => {
    const value = results[key]?.average_latency_ms;

    return `
      <div class="lab91-bar-row">
        <div class="lab91-bar-label">
          <span>${labels[key]}</span>
          <strong>${value == null ? "Ã¢â‚¬â€" : Number(value).toFixed(3) + " ms"}</strong>
        </div>
        <div class="lab91-track">
          <div class="lab91-bar" style="width:${value == null ? 0 : Math.max(1, Number(value) / maxValue * 100)}%"></div>
        </div>
      </div>
    `;
  }).join("");

  $("lab91Details").innerHTML = keys.map(key => {
    const r = results[key];

    if (!r) return "";

    return `
      <tr>
        <td>${labels[key]}</td>
        <td>${Number(r.average_latency_ms).toFixed(6)}</td>
        <td>${Number(r.minimum_latency_ms).toFixed(6)}</td>
        <td>${Number(r.maximum_latency_ms).toFixed(6)}</td>
        <td>${Number(r.total_time_seconds).toFixed(6)}</td>
      </tr>
    `;
  }).join("");

  $("lab91Note").textContent =
    `Replica set: ${report.replica_set} | Documents per concern: ${report.document_count} | Voting data-bearing members: ${report.voting_data_members}. ${report.write_concern_note || ""}`;

  $("lab91Status").textContent = "Completed";
}

async function loadLab91History() {
  try {
    const data = await api("/api/labs/9/history");

    if (!data.history.length) {
      $("lab91History").innerHTML =
        '<p class="empty">No saved benchmark results yet.</p>';
      return;
    }

    $("lab91History").innerHTML = data.history.map(item => `
      <div class="metric-line">
        <span>
          <strong>${esc(item.filename)}</strong>
          <br>
          ${esc(item.timestamp || "Unknown date")}
          <br>
          ${fmt(item.document_count)} documents per concern
        </span>
        <a class="source-link"
           href="/api/labs/9/results/${encodeURIComponent(item.filename)}">
           Download JSON
        </a>
      </div>
    `).join("");
  } catch (e) {
    $("lab91History").innerHTML =
      `<p class="empty">${esc(e.message)}</p>`;
  }
}

$("runLab91").addEventListener("click", async () => {
  const button = $("runLab91");
  const count = Number($("lab91DocumentCount").value);

  if (!Number.isInteger(count) || count < 1 || count > 100000) {
    $("lab91Message").textContent =
      "Enter a whole number between 1 and 100000.";
    return;
  }

  button.disabled = true;
  $("lab91Status").textContent = "Running";
  $("lab91Message").textContent =
    `Running ${count.toLocaleString()} inserts for each write concern...`;

  try {
    const report = await api("/api/labs/9/write-concern", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({document_count: count})
    });

    renderLab91(report);

    $("lab91Message").textContent =
      "Benchmark completed successfully. Results saved as JSON.";

    await loadLab91History();

  } catch (e) {
    $("lab91Status").textContent = "Failed";
    $("lab91Message").textContent =
      `Benchmark failed: ${e.message}`;
  } finally {
    button.disabled = false;
  }
});

$("refreshLab91History").addEventListener(
  "click",
  loadLab91History
);

loadLab91History();

// ==========================================
// LAB 10.1 - BANK TRANSFER TRANSACTION
// ==========================================

async function loadLab101Accounts() {
  try {
    const d = await api('/api/labs/10/bank/accounts');
    if (d.balances) {
      $('lab101A1001').textContent = d.balances.A1001 != null ? `$${fmt(d.balances.A1001)}` : 'â€”';
      $('lab101A1002').textContent = d.balances.A1002 != null ? `$${fmt(d.balances.A1002)}` : 'â€”';
      const total = (d.balances.A1001 || 0) + (d.balances.A1002 || 0);
      $('lab101Total').textContent = `$${fmt(total)}`;
    }
  } catch (e) {
    $('lab101A1001').textContent = 'â€”';
    $('lab101A1002').textContent = 'â€”';
    $('lab101Total').textContent = 'â€”';
  }
}

async function loadLab101History() {
  try {
    const d = await api('/api/labs/10/bank/history');
    if (!d.history || !d.history.length) {
      $('lab101History').innerHTML = '<p class="empty">No transfers yet.</p>';
      return;
    }
    $('lab101History').innerHTML = d.history.map(h => `
      <div class="metric-line">
        <span>
          <strong>${esc(h.transfer_id?.substring(0, 8))}â€¦</strong><br>
          ${esc(h.from)} â†’ ${esc(h.to)} Â· $${fmt(h.amount)}
        </span>
        <strong>${esc(h.timestamp || 'â€”')}</strong>
      </div>
    `).join('');
  } catch (e) {
    $('lab101History').innerHTML = `<p class="empty">${esc(e.message)}</p>`;
  }
}

function renderLab101Steps(steps) {
  $('lab101Steps').innerHTML = steps.map(s => {
    const icon = s.status === 'success' ? 'âœ“' : s.status === 'partial' ? 'âš ' : 'âœ—';
    const cls = s.status === 'success' ? 'lab10-step-ok' : s.status === 'partial' ? 'lab10-step-warn' : 'lab10-step-fail';
    let details = '';

    if (s.accounts) {
      details = `<div class="lab10-step-detail">Accounts: ${s.accounts.map(a => `${a.account_id} ($${a.balance})`).join(', ')}</div>`;
    } else if (s.balances) {
      details = `<div class="lab10-step-detail">Balances: ${Object.entries(s.balances).map(([k,v]) => `${k}: $${v}`).join(', ')}</div>`;
    } else if (s.final_balances) {
      details = `<div class="lab10-step-detail">
        Final: ${Object.entries(s.final_balances).map(([k,v]) => `${k}: $${v}`).join(', ')}
        Â· Total: $${s.total_money} ${s.total_money_preserved ? 'âœ“ preserved' : 'âœ— NOT preserved'}
        Â· Transfers: ${s.total_transfers} Â· History records: ${s.transfer_history_count}
      </div>`;
    }

    if (s.error) {
      details += `<div class="lab10-step-detail lab10-error">Rejected: ${esc(s.error)}</div>`;
    }
    if (s.rollback_verified !== undefined) {
      details += `<div class="lab10-step-detail">Rollback: ${s.rollback_verified ? 'âœ“ verified' : 'âœ— FAILED'}</div>`;
    }
    if (s.result && s.result.attempts) {
      details += `<div class="lab10-step-detail">Transfer ID: ${esc(s.result.transfer_id?.substring(0, 8))}â€¦ Â· Attempts: ${s.result.attempts}</div>`;
    }
    if (s.attempts_per_transfer) {
      details += `<div class="lab10-step-detail">Attempts per transfer: [${s.attempts_per_transfer.join(', ')}]</div>`;
    }

    return `
      <div class="lab10-step ${cls}">
        <div class="lab10-step-header">
          <span class="lab10-step-icon">${icon}</span>
          <strong>Step ${s.step}: ${esc(s.title)}</strong>
        </div>
        ${details}
      </div>
    `;
  }).join('');
}

function renderLab101RetryChart(steps) {
  const activity = steps.find(s => s.step === 'activity');
  if (!activity) return;

  const attempts = activity.attempts_per_transfer || [];
  const retryEvents = activity.retry_events || [];
  const maxAttempt = Math.max(...attempts, 1);

  let html = '<div class="lab10-retry-grid">';

  // Attempts bar chart
  html += '<div class="lab10-retry-section"><h4>Attempts per transfer thread</h4>';
  attempts.forEach((a, i) => {
    const pct = Math.max(5, (a / maxAttempt) * 100);
    html += `
      <div class="lab91-bar-row">
        <div class="lab91-bar-label">
          <span>Thread ${i + 1}</span>
          <strong>${a} attempt${a > 1 ? 's' : ''}</strong>
        </div>
        <div class="lab91-track">
          <div class="lab91-bar ${a > 1 ? 'lab10-bar-retry' : ''}" style="width:${pct}%"></div>
        </div>
      </div>
    `;
  });
  html += '</div>';

  // Retry events log
  if (retryEvents.length > 0) {
    html += '<div class="lab10-retry-section"><h4>Retry events (exponential backoff)</h4>';
    retryEvents.forEach(r => {
      html += `
        <div class="metric-line">
          <span>Attempt ${r.attempt} Â· delay ${r.delay_s}s</span>
          <strong class="lab10-error">${esc(r.error?.substring(0, 60) || 'WriteConflict')}â€¦</strong>
        </div>
      `;
    });
    html += '</div>';
  }

  html += '</div>';
  $('lab101RetryChart').innerHTML = html;
}

$('runLab101').addEventListener('click', async () => {
  const btn = $('runLab101');
  btn.disabled = true;
  $('lab101Status').textContent = 'Running';
  $('lab101Message').textContent = 'Running all Lab 10.1 steps (setup â†’ transfers â†’ rollback tests â†’ concurrent activity)â€¦';

  try {
    const report = await api('/api/labs/10/bank/run', { method: 'POST' });
    renderLab101Steps(report.steps);
    renderLab101RetryChart(report.steps);
    await loadLab101Accounts();
    await loadLab101History();
    $('lab101Status').textContent = 'Completed';
    $('lab101Message').textContent = 'Lab 10.1 demo completed successfully. All assertions passed.';
  } catch (e) {
    $('lab101Status').textContent = 'Failed';
    $('lab101Message').textContent = `Demo failed: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
});

$('resetLab101').addEventListener('click', async () => {
  try {
    await api('/api/labs/10/bank/setup', { method: 'POST' });
    await loadLab101Accounts();
    $('lab101Message').textContent = 'Accounts reset to initial state (Alice: $1000, Bob: $500).';
    $('lab101History').innerHTML = '<p class="empty">No transfers yet.</p>';
  } catch (e) {
    $('lab101Message').textContent = `Reset failed: ${e.message}`;
  }
});

$('lab101Transfer').addEventListener('click', async () => {
  const src = $('lab101From').value;
  const dst = $('lab101To').value;
  const amount = Number($('lab101Amount').value);

  if (src === dst) { $('lab101TransferMsg').textContent = 'Source and destination must differ.'; return; }
  if (!amount || amount <= 0) { $('lab101TransferMsg').textContent = 'Enter a positive amount.'; return; }

  $('lab101Transfer').disabled = true;
  $('lab101TransferMsg').textContent = `Transferring $${amount} from ${src} to ${dst}â€¦`;

  try {
    const r = await api('/api/labs/10/bank/transfer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from: src, to: dst, amount })
    });

    if (r.status === 'insufficient_funds') {
      $('lab101TransferMsg').textContent = `Rejected: ${r.message}`;
    } else {
      $('lab101TransferMsg').textContent = `Transfer successful (ID: ${r.transfer_id?.substring(0, 8)}â€¦, attempts: ${r.attempts})`;
    }
    await loadLab101Accounts();
    await loadLab101History();
  } catch (e) {
    $('lab101TransferMsg').textContent = `Transfer failed: ${e.message}`;
  } finally {
    $('lab101Transfer').disabled = false;
  }
});

$('refreshLab101History').addEventListener('click', loadLab101History);


// ==========================================
// LAB 10.2 - INVENTORY RESERVATION SYSTEM
// ==========================================

async function loadLab102State() {
  try {
    const d = await api('/api/labs/10/inventory/state');
    $('lab102Product').textContent = d.product ? d.product.name : 'â€”';
    $('lab102Stock').textContent = d.product ? fmt(d.product.stock) : 'â€”';
    $('lab102OrderCount').textContent = fmt(d.order_count || 0);

    if (d.orders && d.orders.length) {
      $('lab102OrderList').innerHTML = d.orders.slice(0, 20).map(o => `
        <div class="metric-line">
          <span>
            <strong>${esc(o.order_id?.substring(0, 8))}â€¦</strong>
            Â· ${esc(o.customer_id)} Â· qty: ${o.items?.[0]?.qty || '?'}
          </span>
          <strong class="${o.status === 'pending' ? '' : 'lab10-error'}">${esc(o.status)}</strong>
        </div>
      `).join('');
    } else {
      $('lab102OrderList').innerHTML = '<p class="empty">No orders yet.</p>';
    }
  } catch (e) {
    $('lab102Product').textContent = 'â€”';
    $('lab102Stock').textContent = 'â€”';
    $('lab102OrderCount').textContent = 'â€”';
  }
}

function renderLab102Concurrency(data) {
  const rounds = data.rounds || {};
  let html = '';

  for (const [label, round] of Object.entries(rounds)) {
    const consistent = round.consistent;
    const icon = consistent ? 'âœ“' : 'âœ—';
    const cls = consistent ? 'lab10-step-ok' : 'lab10-step-fail';

    html += `
      <div class="lab10-step ${cls}">
        <div class="lab10-step-header">
          <span class="lab10-step-icon">${icon}</span>
          <strong>${esc(label)}</strong>
        </div>
        <div class="lab10-step-detail">
          Outcomes: ${Object.entries(round.outcomes).map(([k,v]) => `${k}: ${v}`).join(', ')}
        </div>
        <div class="lab10-step-detail">
          Final stock: ${round.final_stock} Â· Orders: ${round.orders_created}
          Â· Consistent: ${consistent ? 'Yes âœ“' : 'No âœ—'}
        </div>
        ${round.attempts_per_success?.length ? `<div class="lab10-step-detail">Attempts per success: [${round.attempts_per_success.join(', ')}]</div>` : ''}
      </div>
    `;
  }

  $('lab102Concurrency').innerHTML = html || '<p class="empty">No concurrency data.</p>';
}

function renderLab102Inconsistency(data) {
  let html = '';
  for (const [mode, info] of Object.entries(data)) {
    const ok = info.consistent;
    const icon = ok ? 'âœ“' : 'âœ—';
    const cls = ok ? 'lab10-step-ok' : 'lab10-step-fail';
    const label = mode === 'transactional' ? 'With Transaction' : 'Without Transaction (findAndModify)';

    html += `
      <div class="lab10-step ${cls}">
        <div class="lab10-step-header">
          <span class="lab10-step-icon">${icon}</span>
          <strong>${label}</strong>
        </div>
        <div class="lab10-step-detail">${esc(info.description)}</div>
        <div class="lab10-step-detail">
          Stock: ${info.stock} Â· Orders: ${info.orders}
          Â· Units lost: ${info.units_lost} Â· Consistent: ${ok ? 'Yes âœ“' : 'No âœ—'}
        </div>
      </div>
    `;
  }

  $('lab102Inconsistency').innerHTML = html || '<p class="empty">No data.</p>';
}

function renderLab102Benchmark(benchmark) {
  if (!benchmark || !benchmark.length) return;

  // Table
  $('lab102BenchmarkTable').innerHTML = benchmark.map(r => `
    <tr>
      <td>${r.threads}</td>
      <td><span class="pill">${esc(r.mode)}</span></td>
      <td>${r.successes} / ${r.total_requests}</td>
      <td>${r.seconds}</td>
      <td><strong>${r.throughput_per_sec}</strong></td>
    </tr>
  `).join('');

  // Bar chart visualization
  const maxTput = Math.max(...benchmark.map(r => r.throughput_per_sec), 1);
  const txnData = benchmark.filter(r => r.mode === 'transaction');
  const famData = benchmark.filter(r => r.mode === 'findAndModify');

  let chartHtml = '<div class="lab10-benchmark-chart">';

  chartHtml += '<div class="lab10-bench-legend">';
  chartHtml += '<span class="lab10-legend-txn">â–  Transaction</span>';
  chartHtml += '<span class="lab10-legend-fam">â–  findAndModify</span>';
  chartHtml += '</div>';

  const levels = [1, 4, 8, 16];
  levels.forEach(n => {
    const txn = txnData.find(r => r.threads === n);
    const fam = famData.find(r => r.threads === n);
    const txnPct = txn ? Math.max(2, (txn.throughput_per_sec / maxTput) * 100) : 0;
    const famPct = fam ? Math.max(2, (fam.throughput_per_sec / maxTput) * 100) : 0;

    chartHtml += `
      <div class="lab10-bench-group">
        <div class="lab10-bench-label">${n} thread${n > 1 ? 's' : ''}</div>
        <div class="lab10-bench-bars">
          <div class="lab91-bar-row">
            <div class="lab91-track">
              <div class="lab91-bar" style="width:${txnPct}%"></div>
            </div>
            <span class="lab10-bench-val">${txn ? txn.throughput_per_sec : 'â€”'} op/s</span>
          </div>
          <div class="lab91-bar-row">
            <div class="lab91-track">
              <div class="lab91-bar lab10-bar-fam" style="width:${famPct}%"></div>
            </div>
            <span class="lab10-bench-val">${fam ? fam.throughput_per_sec : 'â€”'} op/s</span>
          </div>
        </div>
      </div>
    `;
  });

  chartHtml += '</div>';
  $('lab102BenchmarkChart').innerHTML = chartHtml;
}

$('runLab102').addEventListener('click', async () => {
  const btn = $('runLab102');
  const reqCount = Number($('lab102Requests').value);

  if (!Number.isInteger(reqCount) || reqCount < 10 || reqCount > 500) {
    $('lab102Message').textContent = 'Enter a number between 10 and 500.';
    return;
  }

  btn.disabled = true;
  $('lab102Status').textContent = 'Running';
  $('lab102Message').textContent = 'Running Lab 10.2 (concurrency test â†’ inconsistency demo â†’ throughput benchmark)â€¦ This may take a minute.';

  try {
    const report = await api('/api/labs/10/inventory/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ requests_per_level: reqCount })
    });

    renderLab102Concurrency(report.concurrency_test);
    renderLab102Inconsistency(report.inconsistency_demo);
    renderLab102Benchmark(report.throughput_benchmark);
    await loadLab102State();

    $('lab102Status').textContent = 'Completed';
    $('lab102Message').textContent = 'Lab 10.2 demo completed. Results saved as JSON.';
  } catch (e) {
    $('lab102Status').textContent = 'Failed';
    $('lab102Message').textContent = `Demo failed: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
});

$('resetLab102').addEventListener('click', async () => {
  try {
    await api('/api/labs/10/inventory/setup', { method: 'POST' });
    await loadLab102State();
    $('lab102Message').textContent = 'Inventory reset (Wireless Mouse, stock: 5).';
  } catch (e) {
    $('lab102Message').textContent = `Reset failed: ${e.message}`;
  }
});

// Initial load for Lab 10
loadLab101Accounts();
loadLab101History();
loadLab102State();

// ============================================================
// LAB 11 - MONGODB SHARDING AND HOTSPOT DETECTION
// ============================================================

const LAB11_API = 'http://127.0.0.1:5011/api/lab11';

function lab11Number(value) {
  return value == null ? 'â€”' : Number(value).toLocaleString();
}

function lab11Escape(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  })[c]);
}

async function lab11Request(endpoint, options = {}) {
  const response = await fetch(`${LAB11_API}${endpoint}`, options);
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.message || data.error || `HTTP ${response.status}`);
  }

  return data;
}

// ------------------------------------------------------------
// API HEALTH
// ------------------------------------------------------------

async function loadLab11Health() {
  const status = document.getElementById('lab11ApiStatus');
  const message = document.getElementById('lab11Message');

  try {
    const data = await lab11Request('/health');

    status.textContent = data.status === 'success'
      ? 'API Connected'
      : 'API Error';

    status.classList.toggle('ok', data.status === 'success');

    message.textContent = data.connection?.message ||
      'Lab 11 API connection successful.';

  } catch (error) {
    status.textContent = 'API Offline';
    status.classList.remove('ok');
    message.textContent = `Lab 11 connection failed: ${error.message}`;
  }
}

// ------------------------------------------------------------
// CLUSTER INFORMATION
// ------------------------------------------------------------

async function loadLab11Cluster() {
  const rows = document.getElementById('lab11ShardRows');

  try {
    const data = await lab11Request('/cluster');

    document.getElementById('lab11ShardCount').textContent =
      lab11Number(data.shard_count);

    if (!Array.isArray(data.shards)) {
      throw new Error('Invalid shard response');
    }

    rows.innerHTML = data.shards.map(shard => `
      <tr>
        <td>${lab11Escape(shard.name)}</td>
        <td>${lab11Escape(shard.host)}</td>
        <td>
          <span class="pill">
            ${Number(shard.state) === 1 ? 'Registered' : lab11Escape(shard.state)}
          </span>
        </td>
      </tr>
    `).join('') || `
      <tr><td colspan="3" class="empty">No shards registered.</td></tr>
    `;

  } catch (error) {
    rows.innerHTML = `
      <tr><td colspan="3" class="empty">
        ${lab11Escape(error.message)}
      </td></tr>
    `;
  }
}

// ------------------------------------------------------------
// SHARD KEY ANALYSIS
// ------------------------------------------------------------

async function loadLab11Analysis() {
  const rows = document.getElementById('lab11AnalysisRows');

  try {
    const data = await lab11Request('/analysis');
    const analysis = data.result;

    document.getElementById('lab11Recommendation').textContent =
      analysis.recommendation || 'Not specified';

    document.getElementById('lab11Justification').textContent =
      analysis.justification || '';

    const candidates = analysis.candidates || [];

    rows.innerHTML = candidates.map(candidate => `
      <tr>
        <td>${lab11Escape(candidate.shard_key || candidate.name || 'â€”')}</td>
        <td>${lab11Escape(candidate.distribution || 'â€”')}</td>
        <td>${lab11Escape(candidate.query_targeting || candidate.query_performance || 'â€”')}</td>
        <td>${lab11Escape(candidate.assessment || 'â€”')}</td>
      </tr>
    `).join('') || `
      <tr><td colspan="4" class="empty">
        No candidate data returned by API.
      </td></tr>
    `;

  } catch (error) {
    rows.innerHTML = `
      <tr><td colspan="4" class="empty">
        ${lab11Escape(error.message)}
      </td></tr>
    `;
  }
}

// ------------------------------------------------------------
// SHARD DISTRIBUTION
// ------------------------------------------------------------

function renderLab11Distribution(collection, elementId, label) {
  const container = document.getElementById(elementId);
  const shards = collection?.per_shard || {};

  const entries = Object.entries(shards);
  const total = Number(collection?.total_count || 0);

  if (!entries.length) {
    container.innerHTML = `<p class="empty">No distribution data returned.</p>`;
    return;
  }

  container.innerHTML = `
    <h4>${lab11Escape(label)}</h4>
    <p>Total documents: <strong>${lab11Number(total)}</strong></p>
    ${entries.map(([name, stats]) => {
      const count = Number(stats.count || 0);
      const percent = total > 0 ? (count / total) * 100 : 0;

      return `
        <div class="lab11-shard-row">
          <div class="lab11-shard-label">
            <span>${lab11Escape(name)}</span>
            <strong>${lab11Number(count)} (${percent.toFixed(1)}%)</strong>
          </div>
          <div class="lab11-track">
            <div class="lab11-bar" style="width:${percent.toFixed(2)}%"></div>
          </div>
        </div>
      `;
    }).join('')}
  `;
}

// ------------------------------------------------------------
// QUERY PERFORMANCE
// ------------------------------------------------------------

function renderLab11Queries(comparison) {
  const rows = document.getElementById('lab11QueryRows');

  const queries = [
    {
      name: 'Timestamp range query',
      data: comparison?.timestamp_range_query
    },
    {
      name: 'Hashed original-field range query',
      data: comparison?.hashed_original_field_range_query
    }
  ];

  rows.innerHTML = queries.map(item => {
    const q = item.data;

    if (!q) {
      return `<tr><td>${item.name}</td><td colspan="4">Not available</td></tr>`;
    }

    return `
      <tr>
        <td>${lab11Escape(item.name)}</td>
        <td>${lab11Escape((q.targeted_shards || []).join(', '))}</td>
        <td>${lab11Number(q.execution_time_ms)}</td>
        <td>${lab11Number(q.total_docs_examined)}</td>
        <td>${lab11Number(q.total_docs_returned)}</td>
      </tr>
    `;
  }).join('');
}

// ------------------------------------------------------------
// RENDER BENCHMARK RESULTS
// ------------------------------------------------------------

function renderLab11Results(data) {
  const result = data.result;

  if (!result) {
    throw new Error('Experiment returned no result object.');
  }

  const timestamp = result.timestamp_collection || {};
  const hashed = result.hashed_collection || {};

  document.getElementById('lab11TimestampTotal').textContent =
    lab11Number(timestamp.total_count);

  document.getElementById('lab11HashedTotal').textContent =
    lab11Number(hashed.total_count);

  document.getElementById('lab11Inserted').textContent =
    lab11Number(result.documents_inserted_per_collection);

  renderLab11Distribution(
    timestamp,
    'lab11Distribution',
    'Timestamp shard distribution'
  );

  const hashedContainer = document.createElement('div');
  hashedContainer.id = 'lab11HashedDistribution';
  document.getElementById('lab11Distribution').appendChild(hashedContainer);

  renderLab11Distribution(
    hashed,
    'lab11HashedDistribution',
    'Hashed shard distribution'
  );

  renderLab11Queries(result.range_query_comparison);

  const observations = result.observations || [];

  document.getElementById('lab11Observations').innerHTML =
    observations.map(item => `<li>${lab11Escape(item)}</li>`).join('') ||
    '<li>No observations returned.</li>';
}

// ------------------------------------------------------------
// RUN HOTSPOT EXPERIMENT
// ------------------------------------------------------------

async function runLab11Experiment() {
  const button = document.getElementById('lab11Run');
  const message = document.getElementById('lab11Message');

  button.disabled = true;
  button.textContent = 'Running experiment...';
  message.textContent = 'Inserting test documents and comparing shard performance...';

  try {
    const data = await lab11Request('/run-hotspot', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      }
    });

    renderLab11Results(data);

    message.textContent =
      'Lab 11.2 experiment completed successfully. Results loaded from MongoDB.';

  } catch (error) {
    message.textContent = `Experiment failed: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = 'Run Hotspot Experiment';
  }
}

// ------------------------------------------------------------
// REFRESH DASHBOARD
// ------------------------------------------------------------

async function refreshLab11() {
  await Promise.all([
    loadLab11Health(),
    loadLab11Cluster(),
    loadLab11Analysis()
  ]);
}

// ------------------------------------------------------------
// EVENT LISTENERS
// ------------------------------------------------------------

document.getElementById('lab11Refresh')?.addEventListener(
  'click',
  refreshLab11
);

document.getElementById('lab11Run')?.addEventListener(
  'click',
  runLab11Experiment
);

// INITIALIZE LAB 11

refreshLab11();


// ------------------------------------------------------------
// LAB 12 â€” TLS AND RBAC DASHBOARD
// ------------------------------------------------------------

async function lab12Request(endpoint, options = {}) {
  const response = await fetch(`/api/labs/12${endpoint}`, options);

  const contentType = response.headers.get('content-type') || '';

  if (!contentType.includes('application/json')) {
    const responseText = await response.text();
    throw new Error(
      `Expected JSON but received another response. HTTP ${response.status}: ${responseText.slice(0, 150)}`
    );
  }

  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.message || data.error || `Request failed (${response.status})`);
  }

  return data;
}

function renderLab12PermissionResults(containerId, permissions) {
  const container = document.getElementById(containerId);

  if (!container) return;

  if (!permissions) {
    container.textContent = 'No results returned.';
    return;
  }

  const rows = [
    ['Collection access',
      permissions.direct_collection_access ||
      permissions.employee_collection_access || 'Not reported'],
    ['Safe view access', permissions.safe_view_access || 'Not applicable'],
    ['Salary visible',
      permissions.salary_visible === true ? 'Yes' :
      permissions.salary_visible === false ? 'No' : 'Not reported'],
    ['Insert permission', permissions.insert_permission || 'Not tested'],
    ['Update permission', permissions.update_permission || 'Not tested'],
    ['Delete permission', permissions.delete_permission || 'Not tested']
  ];

  container.innerHTML = rows.map(([label, value]) => `
    <p><strong>${lab11Escape(label)}:</strong> ${lab11Escape(String(value))}</p>
  `).join('');
}

async function refreshLab12() {
  const message = document.getElementById('lab12Message');
  message.textContent = 'Checking Lab 12 TLS connection...';

  try {
    const data = await lab12Request('/status');
    const tls = data.tls || {};

    document.getElementById('lab12ApiStatus').textContent = 'Connected';
    document.getElementById('lab12TlsStatus').textContent =
      tls.status === 'success' ? 'Verified' : 'Failed';

    document.getElementById('lab12Database').textContent =
      tls.database || 'â€”';

    document.getElementById('lab12Host').textContent =
      tls.host || 'â€”';

    document.getElementById('lab12TlsProtocol').textContent =
      tls.protocol || 'Not reported';

    document.getElementById('lab12TlsCipher').textContent =
      tls.cipher || 'Not reported';

    message.textContent = tls.message || 'Lab 12 status retrieved.';
  } catch (error) {
    document.getElementById('lab12ApiStatus').textContent = 'Unavailable';
    document.getElementById('lab12TlsStatus').textContent = 'Not verified';
    document.getElementById('lab12TlsProtocol').textContent = 'â€”';
    document.getElementById('lab12TlsCipher').textContent = 'â€”';

    message.textContent = `TLS check failed: ${error.message}`;
  }
}

async function runLab12RbacTests() {
  const button = document.getElementById('lab12Run');
  const message = document.getElementById('lab12Message');

  button.disabled = true;
  button.textContent = 'Running tests...';
  message.textContent = 'Checking Reader, Writer, Analyst and HR permissions...';

  try {
    const data = await lab12Request('/rbac/test', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      }
    });

    const results = data.results || {};

    renderLab12PermissionResults('lab12ReaderResults', results.reader);
    renderLab12PermissionResults('lab12WriterResults', results.writer);
    renderLab12PermissionResults('lab12AnalystResults', results.analyst);
    renderLab12PermissionResults('lab12HrResults', results.hr);

    message.textContent =
      results.status === 'success'
        ? 'All Lab 12 RBAC tests completed successfully.'
        : 'RBAC tests returned an unsuccessful status. Check the results.';
  } catch (error) {
    message.textContent = `RBAC test failed: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = 'Run RBAC Tests';
  }
}

document.getElementById('lab12Refresh')?.addEventListener(
  'click',
  refreshLab12
);

document.getElementById('lab12Run')?.addEventListener(
  'click',
  runLab12RbacTests
);

// INITIALIZE LAB 12
refreshLab12();

// ===============================
// LAB 13 - MONITORING DASHBOARD
// ===============================

async function refreshLab13() {
  const button = document.getElementById('lab13Refresh');
  const message = document.getElementById('lab13Message');

  if (!message) return;

  if (button) {
    button.disabled = true;
    button.textContent = 'Refreshing...';
  }

  message.textContent = 'Collecting Docker, Prometheus and Kubernetes status...';

  try {
    const response = await fetch('/api/labs/13/status');
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.message || `Request failed (${response.status})`);
    }

    const docker = data.docker || {};
    const prometheus = data.prometheus || {};
    const kubernetes = data.kubernetes || {};
    const statefulset = kubernetes.statefulset || {};

    document.getElementById('lab13Overall').textContent =
      (data.status || 'unknown').toUpperCase();

    document.getElementById('lab13DockerSummary').textContent =
      `${docker.running ?? 0} / ${docker.total ?? 0} containers running`;

    document.getElementById('lab13PrometheusSummary').textContent =
      prometheus.status === 'success' ? 'Metrics available' : 'Unavailable';

    document.getElementById('lab13KubernetesSummary').textContent =
      `${kubernetes.ready ?? 0} / ${kubernetes.total ?? 0} pods ready`;

    document.getElementById('lab13StatefulSet').textContent =
      `${statefulset.ready_replicas ?? 0} / ${statefulset.desired_replicas ?? 0} replicas ready`;

    const pvcs = kubernetes.pvcs || [];
    const boundPvcs = pvcs.filter(pvc => pvc.status === 'Bound').length;

    document.getElementById('lab13PvcSummary').textContent =
      `${boundPvcs} / ${pvcs.length} volumes bound`;

    const containers = docker.containers || [];

    document.getElementById('lab13DockerRows').innerHTML = containers.length
      ? containers.map(container => `
          <p><strong>${lab11Escape(container.name || 'Unknown')}</strong>
          — ${lab11Escape(container.state || 'Unknown')}
          — ${lab11Escape(container.health || 'Health not reported')}</p>
        `).join('')
      : '<p>No container details returned.</p>';

    const metrics = prometheus.metrics || [];

    document.getElementById('lab13MetricRows').innerHTML = metrics.length
      ? metrics.map(metric => `
          <p><strong>${lab11Escape(metric.labels?.__name__ || 'Metric')}</strong>
          — Value: ${lab11Escape(metric.value ?? 'Not reported')}
          — Instance: ${lab11Escape(metric.labels?.instance || 'Unknown')}</p>
        `).join('')
      : '<p>No Prometheus metrics returned.</p>';

    const pods = kubernetes.pods || [];

    document.getElementById('lab13PodRows').innerHTML = pods.length
      ? pods.map(pod => `
          <p><strong>${lab11Escape(pod.name || 'Unknown')}</strong>
          — Phase: ${lab11Escape(pod.phase || 'Unknown')}
          — Ready: ${pod.ready ? 'Yes' : 'No'}
          — Restarts: ${lab11Escape(pod.restarts ?? 0)}</p>
        `).join('')
      : '<p>No Kubernetes pod details returned.</p>';

    document.getElementById('lab13PvcRows').innerHTML = pvcs.length
      ? pvcs.map(pvc => `
          <p><strong>${lab11Escape(pvc.name || 'Unknown')}</strong>
          — Status: ${lab11Escape(pvc.status || 'Unknown')}
          — Capacity: ${lab11Escape(pvc.capacity || 'Not reported')}</p>
        `).join('')
      : '<p>No persistent volume claims returned.</p>';

    message.textContent = data.message ||
      'Lab 13 monitoring information updated.';
  } catch (error) {
    document.getElementById('lab13Overall').textContent = 'Unavailable';
    message.textContent = `Lab 13 monitoring failed: ${error.message}`;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = 'Refresh Monitoring';
    }
  }
}

document.getElementById('lab13Refresh')?.addEventListener(
  'click',
  refreshLab13
);

// INITIALIZE LAB 13
refreshLab13();

 // ===============================
 // LAB 14.1 - MONGODB MONITORING
 // ===============================

async function refreshLab14() {
  const button = document.getElementById('lab14Refresh');
  const message = document.getElementById('lab14Message');

  if (!message) return;

  if (button) {
    button.disabled = true;
    button.textContent = 'Refreshing...';
  }

  message.textContent = 'Collecting MongoDB performance metrics...';

  const safe = value => String(value ?? 'Not available')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

  try {
    const response = await fetch('/api/labs/14/monitoring/status');
    const data = await response.json();

    if (!response.ok || !data.available) {
      throw new Error(data.error || `Request failed (${response.status})`);
    }

    const connections = data.connections || {};
    const cache = data.cache || {};
    const replica = data.replica_set || {};
    const operations = data.opcounters || {};
    const members = replica.members || [];
    const warnings = data.warnings || [];

    document.getElementById('lab14Overall').textContent =
      (data.status || 'unknown').toUpperCase();

    document.getElementById('lab14Connections').textContent =
      `${connections.current ?? 'N/A'} current / ${connections.available ?? 'N/A'} available`;

    document.getElementById('lab14Cache').textContent =
      cache.hit_ratio_percent == null
        ? 'Not available'
        : `${cache.hit_ratio_percent}%`;

    document.getElementById('lab14Lag').textContent =
      replica.maximum_secondary_lag_seconds == null
        ? 'Not available'
        : `${replica.maximum_secondary_lag_seconds} seconds`;

    document.getElementById('lab14Replica').textContent =
      replica.name || 'Not available';

    document.getElementById('lab14Version').textContent =
      data.mongodb_version || 'Not available';

    document.getElementById('lab14Operations').innerHTML =
      Object.entries(operations).map(([name, value]) =>
        `<p><strong>${safe(name)}</strong>: ${safe(value)}</p>`
      ).join('') || '<p>No operation counters returned.</p>';

    document.getElementById('lab14Members').innerHTML =
      members.map(member => `
        <p>
          <strong>${safe(member.name)}</strong>
          — ${safe(member.state)}
          — Health: ${safe(member.health)}
          — Lag: ${member.lag_seconds == null
            ? 'N/A'
            : safe(member.lag_seconds + ' seconds')}
        </p>
      `).join('') || '<p>No replica-set members returned.</p>';

    document.getElementById('lab14CacheDetails').innerHTML = `
      <p><strong>Estimated hit ratio:</strong> ${safe(cache.hit_ratio_percent)}%</p>
      <p><strong>Sample type:</strong> ${safe(cache.sample_type)}</p>
      <p><strong>Pages requested:</strong> ${safe(cache.pages_requested)}</p>
      <p><strong>Pages read into cache:</strong> ${safe(cache.pages_read_into_cache)}</p>
      <p><strong>Bytes currently in cache:</strong> ${safe(cache.bytes_currently_in_cache)}</p>
      <p><strong>Maximum cache bytes:</strong> ${safe(cache.maximum_cache_bytes)}</p>
      <p><strong>Pages written from cache:</strong> ${safe(cache.pages_written_from_cache)}</p>
    `;

    document.getElementById('lab14Warnings').innerHTML =
      warnings.length
        ? warnings.map(warning => `<p>${safe(warning)}</p>`).join('')
        : '<p>No warnings. MongoDB monitoring checks passed.</p>';

    document.getElementById('lab14CheckedAt').textContent =
      `Last checked: ${data.checked_at || 'Not available'}`;

    message.textContent = 'MongoDB monitoring data loaded successfully.';

  } catch (error) {
    document.getElementById('lab14Overall').textContent = 'Unavailable';
    message.textContent = `Lab 14.1 monitoring failed: ${error.message}`;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = 'Refresh Monitoring';
    }
  }
}

document.getElementById('lab14Refresh')?.addEventListener(
  'click',
  refreshLab14
);

// INITIALIZE LAB 14.1
refreshLab14();
