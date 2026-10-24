/**
 * MedRescue — Frontend Application
 * ==================================
 * Fetches data from Flask API, renders charts, tables, and
 * interactive visualizations for the DSA-powered dashboard.
 */

const API = '';
let currentAlgo = 'bipartite';
let networkData = null;

// ───────────────────────────────────────────────
//  Navigation
// ───────────────────────────────────────────────

document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
        const page = item.dataset.page;
        if (!page) return;

        // Update nav
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        item.classList.add('active');
        closeSidebar();

        // Update page
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        const target = document.getElementById(`page-${page}`);
        if (target) target.classList.add('active');

        // Update title
        const titles = {
            dashboard: 'Dashboard',
            transfers: 'Transfer Recommendations',
            facilities: 'Healthcare Facilities',
            network: 'Transport Network',
            heap: 'Expiry Priority Heap',
            algorithms: 'Algorithm Comparison',
        };
        document.getElementById('pageTitle').textContent = titles[page] || 'Dashboard';

        // Load page-specific data
        if (page === 'network') loadNetwork();
        if (page === 'heap') loadHeap();
        if (page === 'algorithms') loadAlgoComparison();
    });
});

const menuButton = document.getElementById('menuBtn');
const sidebarBackdrop = document.getElementById('sidebarBackdrop');

function closeSidebar() {
    document.getElementById('sidebar').classList.remove('open');
    sidebarBackdrop.classList.remove('visible');
    menuButton.setAttribute('aria-expanded', 'false');
}

menuButton.addEventListener('click', () => {
    const isOpen = document.getElementById('sidebar').classList.toggle('open');
    sidebarBackdrop.classList.toggle('visible', isOpen);
    menuButton.setAttribute('aria-expanded', String(isOpen));
});

sidebarBackdrop.addEventListener('click', closeSidebar);

// ───────────────────────────────────────────────
//  Data Fetching
// ───────────────────────────────────────────────

async function fetchJSON(endpoint, options = {}) {
    const res = await fetch(`${API}${endpoint}`, options);
    const data = await res.json();
    if (!res.ok) {
        throw new Error(data.error || `Request failed (${res.status})`);
    }
    return data;
}

async function refreshData() {
    const btn = document.getElementById('refreshBtn');
    btn.classList.add('spinning');

    try {
        await Promise.all([
            loadStats(),
            loadExpiryTimeline(),
            loadCategoryBreakdown(),
            loadUrgentTable(),
            loadTransfers(),
            loadFacilities(),
        ]);
        hideNotice();
        return true;
    } catch (error) {
        showNotice(error.message, true);
        return false;
    } finally {
        setTimeout(() => btn.classList.remove('spinning'), 600);
    }
}

// ───────────────────────────────────────────────
//  Dashboard Stats
// ───────────────────────────────────────────────

async function loadStats() {
    const s = await fetchJSON('/api/stats');

    const grid = document.getElementById('statsGrid');
    grid.innerHTML = `
        <div class="stat-card animate-in delay-1">
            <div class="stat-header">
                <div>
                    <div class="stat-label">Total Stock Units</div>
                    <div class="stat-value">${s.total_medicines.toLocaleString()}</div>
                    <div class="stat-sub">across ${s.total_facilities} facilities</div>
                </div>
                <div class="stat-icon">💊</div>
            </div>
        </div>
        <div class="stat-card animate-in delay-2">
            <div class="stat-header">
                <div>
                    <div class="stat-label">Inventory Value</div>
                    <div class="stat-value">$${formatNumber(s.total_value)}</div>
                    <div class="stat-sub">active stock value</div>
                </div>
                <div class="stat-icon">💰</div>
            </div>
        </div>
        <div class="stat-card animate-in delay-3">
            <div class="stat-header">
                <div>
                    <div class="stat-label">Expiring Soon</div>
                    <div class="stat-value text-amber">${s.expiring_soon.toLocaleString()}</div>
                    <div class="stat-sub"><span class="negative">within 30 days</span></div>
                </div>
                <div class="stat-icon">⏰</div>
            </div>
        </div>
        <div class="stat-card animate-in delay-4">
            <div class="stat-header">
                <div>
                    <div class="stat-label">Wastage Prevented</div>
                    <div class="stat-value text-teal">$${formatNumber(s.wastage_prevented)}</div>
                    <div class="stat-sub"><span class="positive">+${s.active_transfers} transfers</span></div>
                </div>
                <div class="stat-icon">🛡️</div>
            </div>
        </div>
        <div class="stat-card animate-in delay-5">
            <div class="stat-header">
                <div>
                    <div class="stat-label">Net Savings</div>
                    <div class="stat-value text-teal">$${formatNumber(s.transfer_savings)}</div>
                    <div class="stat-sub"><span class="positive">after transport costs</span></div>
                </div>
                <div class="stat-icon">📈</div>
            </div>
        </div>
    `;
}

// ───────────────────────────────────────────────
//  Expiry Timeline Bar Chart
// ───────────────────────────────────────────────

async function loadExpiryTimeline() {
    const data = await fetchJSON('/api/expiry-timeline');
    const chart = document.getElementById('expiryChart');

    const maxVal = Math.max(...data.map(d => d.count), 1);
    const colors = ['#ef4444', '#f97316', '#f59e0b', '#3b82f6', '#8b5cf6', '#10b981'];

    chart.innerHTML = data.map((d, i) => {
        const height = Math.max((d.count / maxVal) * 180, 4);
        return `
            <div class="bar-group">
                <div class="bar-value">${d.count.toLocaleString()}</div>
                <div class="bar" style="height: ${height}px; background: ${colors[i]};"
                     title="${d.range}: ${d.count} units"></div>
                <div class="bar-label">${d.range}</div>
            </div>
        `;
    }).join('');
}

// ───────────────────────────────────────────────
//  Category Donut Chart (SVG)
// ───────────────────────────────────────────────

async function loadCategoryBreakdown() {
    const data = await fetchJSON('/api/category-breakdown');
    const wrapper = document.getElementById('categoryChart');

    const total = data.reduce((sum, d) => sum + d.count, 0);
    const colors = ['#06d6a0', '#3b82f6', '#8b5cf6', '#f59e0b', '#ef4444', '#ec4899', '#14b8a6', '#f97316'];

    // Build SVG donut
    let cumulativePercent = 0;
    const radius = 60;
    const cx = 80, cy = 80;
    const circumference = 2 * Math.PI * radius;

    let segments = '';
    data.forEach((d, i) => {
        const percent = total ? d.count / total : 0;
        const offset = circumference * (1 - percent);
        const rotation = cumulativePercent * 360;
        segments += `
            <circle r="${radius}" cx="${cx}" cy="${cy}"
                    fill="transparent"
                    stroke="${colors[i % colors.length]}"
                    stroke-width="18"
                    stroke-dasharray="${circumference}"
                    stroke-dashoffset="${offset}"
                    transform="rotate(${rotation - 90} ${cx} ${cy})"
                    style="transition: stroke-dashoffset 1s ease ${i * 0.1}s;" />
        `;
        cumulativePercent += percent;
    });

    const legend = data.map((d, i) => `
        <div class="legend-item">
            <div class="legend-dot" style="background: ${colors[i % colors.length]};"></div>
            <span>${d.category}</span>
            <span class="legend-value">${d.count.toLocaleString()}</span>
        </div>
    `).join('');

    wrapper.innerHTML = `
        <svg class="donut-svg" viewBox="0 0 160 160">
            <circle r="${radius}" cx="${cx}" cy="${cy}" fill="transparent"
                    stroke="rgba(255,255,255,0.05)" stroke-width="18" />
            ${segments}
            <text x="${cx}" y="${cy - 6}" text-anchor="middle" fill="#f1f5f9"
                  font-size="20" font-weight="800" font-family="Inter">${total.toLocaleString()}</text>
            <text x="${cx}" y="${cy + 12}" text-anchor="middle" fill="#64748b"
                  font-size="9" font-weight="600" font-family="Inter">TOTAL UNITS</text>
        </svg>
        <div class="donut-legend">${legend}</div>
    `;
}

// ───────────────────────────────────────────────
//  Urgent Medicines Table
// ───────────────────────────────────────────────

async function loadUrgentTable() {
    const data = await fetchJSON('/api/top-urgent?n=10');
    const tbody = document.getElementById('urgentTable');

    tbody.innerHTML = data.map((m, i) => {
        const daysClass = m.days_until_expiry <= 7 ? 'text-red' :
                          m.days_until_expiry <= 30 ? 'text-amber' : 'text-teal';
        const storageClass = `storage-${m.storage}`;
        return `
            <tr class="animate-in delay-${Math.min(i + 1, 5)}">
                <td><span class="font-mono font-bold">${i + 1}</span></td>
                <td><strong>${m.name}</strong></td>
                <td class="text-muted">${m.facility}</td>
                <td class="font-mono">${m.batch}</td>
                <td>${m.quantity.toLocaleString()}</td>
                <td class="font-mono">${m.expiry}</td>
                <td><span class="${daysClass} font-bold">${m.days_until_expiry}d</span></td>
                <td><span class="storage-badge ${storageClass}">${m.storage}</span></td>
                <td><span class="badge ${m.regulatory_class === 'OTC' ? 'badge-teal' : m.regulatory_class === 'Rx' ? 'badge-blue' : 'badge-red'}">${m.regulatory_class}</span></td>
                <td class="font-mono">${m.urgency_score}</td>
            </tr>
        `;
    }).join('');
}

// ───────────────────────────────────────────────
//  Transfers
// ───────────────────────────────────────────────

async function loadTransfers() {
    const data = await fetchJSON(`/api/transfers?algo=${currentAlgo}`);
    const list = document.getElementById('transferList');
    const badge = document.getElementById('transfer-count-badge');
    const algoBadge = document.getElementById('algo-label-badge');

    badge.textContent = data.length;
    algoBadge.textContent = currentAlgo === 'bipartite' ? 'Bipartite Matching' : 'Greedy Allocation';

    if (data.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <div class="icon">📭</div>
                <p>No beneficial transfers found with current constraints.</p>
            </div>
        `;
        return;
    }

    list.innerHTML = data.map((t, i) => `
        <div class="transfer-card animate-in delay-${Math.min(i + 1, 5)}">
            <div class="transfer-route">
                <div class="transfer-facility">
                    ${t.donor}
                    <small>Donor</small>
                </div>
                <div class="transfer-arrow">→</div>
                <div class="transfer-facility">
                    ${t.receiver}
                    <small>Receiver</small>
                </div>
            </div>
            <div class="transfer-med">
                ${t.medicine_name}
                <small>${t.quantity} units · ${t.batch} · <span class="storage-badge storage-${t.storage}">${t.storage}</span></small>
            </div>
            <div>
                <span class="badge ${t.days_until_expiry <= 14 ? 'badge-red' : t.days_until_expiry <= 30 ? 'badge-amber' : 'badge-teal'}">
                    ${t.days_until_expiry}d left
                </span>
            </div>
            <div class="transfer-savings">
                <div class="amount">+$${formatNumber(t.net_saving)}</div>
                <div class="cost">${t.distance_km} km · $${formatNumber(t.transport_cost)} transport</div>
            </div>
            <button class="approve-btn ${t.status === 'approved' ? 'approved' : ''}"
                    onclick="approveTransfer('${t.id}', this)"
                    ${t.status === 'approved' ? 'disabled' : ''}>
                ${t.status === 'approved' ? '✓ Approved' : 'Approve'}
            </button>
        </div>
    `).join('');
}

async function approveTransfer(id, btn) {
    btn.disabled = true;
    try {
        await fetchJSON(`/api/transfers/${id}/approve`, { method: 'POST' });
        if (await refreshData()) {
            showNotice('Transfer approved; inventory and demand have been updated.');
        }
    } catch (error) {
        showNotice(error.message, true);
        btn.disabled = false;
    }
}

function switchAlgorithm(algo) {
    currentAlgo = algo;
    document.getElementById('btn-bipartite').classList.toggle('active', algo === 'bipartite');
    document.getElementById('btn-greedy').classList.toggle('active', algo === 'greedy');
    Promise.all([loadTransfers(), loadStats()]).catch(error => showNotice(error.message, true));
}

// ───────────────────────────────────────────────
//  Facilities
// ───────────────────────────────────────────────

async function loadFacilities() {
    const data = await fetchJSON('/api/facilities');
    const grid = document.getElementById('facilityGrid');

    grid.innerHTML = data.map((f, i) => `
        <div class="facility-card animate-in delay-${Math.min(i + 1, 5)}" onclick="loadFacilityDetail('${f.id}')">
            <div class="facility-name">${f.name}</div>
            <div class="facility-city">📍 ${f.city}</div>
            <div class="facility-stats">
                <div class="fac-stat">
                    <div class="fac-stat-label">Stock</div>
                    <div class="fac-stat-value">${f.total_stock.toLocaleString()}</div>
                </div>
                <div class="fac-stat">
                    <div class="fac-stat-label">Value</div>
                    <div class="fac-stat-value">$${formatNumber(f.inventory_value)}</div>
                </div>
                <div class="fac-stat">
                    <div class="fac-stat-label">Expiring</div>
                    <div class="fac-stat-value ${f.expiring_soon > 0 ? 'text-amber' : ''}">${f.expiring_soon}</div>
                </div>
                <div class="fac-stat">
                    <div class="fac-stat-label">Expired</div>
                    <div class="fac-stat-value ${f.expired > 0 ? 'text-red' : ''}">${f.expired}</div>
                </div>
            </div>
            <div class="facility-tags">
                ${f.storage_capabilities.map(s => `<span class="storage-badge storage-${s}">${s}</span>`).join('')}
                ${f.can_handle_controlled ? '<span class="badge badge-red">Controlled</span>' : ''}
            </div>
        </div>
    `).join('');
}

async function loadFacilityDetail(fid) {
    const f = await fetchJSON(`/api/facilities/${fid}`);
    const detail = document.getElementById('facilityDetail');
    const title = document.getElementById('facilityDetailName');
    const tbody = document.getElementById('facilityInventoryTable');

    title.textContent = `${f.name} — Inventory`;
    detail.style.display = 'block';

    tbody.innerHTML = f.inventory.map(m => {
        const daysClass = m.is_expired ? 'text-red' :
                          m.days_until_expiry <= 30 ? 'text-amber' : 'text-teal';
        const status = m.is_expired ? '<span class="badge badge-red">Expired</span>' :
                       m.days_until_expiry <= 30 ? '<span class="badge badge-amber">Expiring</span>' :
                       '<span class="badge badge-teal">Good</span>';
        return `
            <tr>
                <td><strong>${m.name}</strong></td>
                <td class="font-mono">${m.batch}</td>
                <td>${m.quantity.toLocaleString()}</td>
                <td class="font-mono">${m.expiry}</td>
                <td><span class="${daysClass} font-bold">${m.days_until_expiry}d</span></td>
                <td><span class="storage-badge storage-${m.storage}">${m.storage}</span></td>
                <td>$${m.unit_value.toFixed(2)}</td>
                <td>${status}</td>
            </tr>
        `;
    }).join('');

    detail.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ───────────────────────────────────────────────
//  Network Graph (Canvas)
// ───────────────────────────────────────────────

async function loadNetwork() {
    networkData = await fetchJSON('/api/network');
    drawNetwork();
    window.addEventListener('resize', drawNetwork);
}

function drawNetwork() {
    if (!networkData) return;

    const canvas = document.getElementById('networkCanvas');
    const wrapper = canvas.parentElement;
    canvas.width = wrapper.clientWidth * 2;
    canvas.height = wrapper.clientHeight * 2;
    canvas.style.width = wrapper.clientWidth + 'px';
    canvas.style.height = wrapper.clientHeight + 'px';

    const ctx = canvas.getContext('2d');
    ctx.scale(2, 2);
    const W = wrapper.clientWidth;
    const H = wrapper.clientHeight;

    ctx.clearRect(0, 0, W, H);

    const { nodes, edges } = networkData;

    // Map lat/lon to canvas coords
    const lats = nodes.map(n => n.lat);
    const lons = nodes.map(n => n.lon);
    const minLat = Math.min(...lats), maxLat = Math.max(...lats);
    const minLon = Math.min(...lons), maxLon = Math.max(...lons);

    const pad = 60;
    const mapX = lon => pad + ((lon - minLon) / (maxLon - minLon || 1)) * (W - 2 * pad);
    const mapY = lat => pad + ((maxLat - lat) / (maxLat - minLat || 1)) * (H - 2 * pad);

    const nodePositions = {};
    nodes.forEach(n => {
        nodePositions[n.id] = { x: mapX(n.lon), y: mapY(n.lat), ...n };
    });

    // Draw edges
    edges.forEach(e => {
        const a = nodePositions[e.source];
        const b = nodePositions[e.target];
        if (!a || !b) return;

        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = 'rgba(50, 104, 200, 0.22)';
        ctx.lineWidth = 1;
        ctx.stroke();

        // Distance label at midpoint
        const mx = (a.x + b.x) / 2;
        const my = (a.y + b.y) / 2;
        ctx.fillStyle = 'rgba(96, 115, 139, 0.72)';
        ctx.font = '9px Inter';
        ctx.textAlign = 'center';
        ctx.fillText(`${e.distance} km`, mx, my - 4);
    });

    // Draw nodes
    nodes.forEach(n => {
        const pos = nodePositions[n.id];

        // Glow
        const grad = ctx.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, 20);
        grad.addColorStop(0, 'rgba(8, 126, 114, 0.2)');
        grad.addColorStop(1, 'rgba(8, 126, 114, 0)');
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, 20, 0, Math.PI * 2);
        ctx.fillStyle = grad;
        ctx.fill();

        // Node circle
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, 8, 0, Math.PI * 2);
        ctx.fillStyle = '#087e72';
        ctx.fill();
        ctx.strokeStyle = 'rgba(8, 126, 114, 0.4)';
        ctx.lineWidth = 2;
        ctx.stroke();

        // Label
        ctx.fillStyle = '#20364e';
        ctx.font = '11px Inter';
        ctx.textAlign = 'center';
        ctx.fillText(n.name, pos.x, pos.y - 16);

        // City
        ctx.fillStyle = '#718096';
        ctx.font = '9px Inter';
        ctx.fillText(n.city, pos.x, pos.y + 22);
    });
}

// ───────────────────────────────────────────────
//  Heap Visualization
// ───────────────────────────────────────────────

async function loadHeap() {
    const data = await fetchJSON('/api/heap-state');
    const container = document.getElementById('heapVis');

    container.innerHTML = data.map((m, i) => {
        const maxUrgency = Math.max(...data.map(d => d.urgency_score), 1);
        const pct = Math.min((m.urgency_score / maxUrgency) * 100, 100);
        const color = m.days_until_expiry <= 7 ? '#ef4444' :
                      m.days_until_expiry <= 30 ? '#f59e0b' :
                      m.days_until_expiry <= 60 ? '#3b82f6' : '#10b981';
        return `
            <div class="heap-node animate-in delay-${Math.min(i + 1, 5)}">
                <div class="rank">${i + 1}</div>
                <div class="med-name">${m.name}</div>
                <div class="med-detail">${m.facility}</div>
                <div class="med-detail">${m.days_until_expiry}d · ${m.quantity} units · ${m.storage}</div>
                <div class="urgency-bar">
                    <div class="urgency-fill" style="width: ${100 - pct}%; background: ${color};"></div>
                </div>
            </div>
        `;
    }).join('');
}

// ───────────────────────────────────────────────
//  Algorithm Comparison
// ───────────────────────────────────────────────

async function loadAlgoComparison() {
    const data = await fetchJSON('/api/compare-algorithms');
    const container = document.getElementById('algoComparison');

    const biWins = data.bipartite.net_savings >= data.greedy.net_savings;

    container.innerHTML = `
        <div class="algo-card ${biWins ? 'winner' : ''} animate-in delay-1">
            <div class="algo-name">Bipartite Matching</div>
            <div class="algo-desc">Benefit-ranked matching · Capacity-aware heuristic</div>
            <div class="algo-metric">
                <div class="algo-metric-label">Transfers</div>
                <div class="algo-metric-value">${data.bipartite.transfers}</div>
            </div>
            <div class="algo-metric">
                <div class="algo-metric-label">Net Savings</div>
                <div class="algo-metric-value teal">$${formatNumber(data.bipartite.net_savings)}</div>
            </div>
            <div class="algo-metric">
                <div class="algo-metric-label">Wastage Prevented</div>
                <div class="algo-metric-value">$${formatNumber(data.bipartite.wastage_prevented)}</div>
            </div>
        </div>
        <div class="algo-card ${!biWins ? 'winner' : ''} animate-in delay-2">
            <div class="algo-name">Greedy Allocation</div>
            <div class="algo-desc">Expiry-priority order · Locally optimal</div>
            <div class="algo-metric">
                <div class="algo-metric-label">Transfers</div>
                <div class="algo-metric-value">${data.greedy.transfers}</div>
            </div>
            <div class="algo-metric">
                <div class="algo-metric-label">Net Savings</div>
                <div class="algo-metric-value blue">$${formatNumber(data.greedy.net_savings)}</div>
            </div>
            <div class="algo-metric">
                <div class="algo-metric-label">Wastage Prevented</div>
                <div class="algo-metric-value">$${formatNumber(data.greedy.wastage_prevented)}</div>
            </div>
        </div>
    `;
}

// ───────────────────────────────────────────────
//  Utilities
// ───────────────────────────────────────────────

function formatNumber(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toFixed(0);
}

function showNotice(message, isError = false) {
    let notice = document.getElementById('appNotice');
    if (!notice) {
        notice = document.createElement('div');
        notice.id = 'appNotice';
        notice.className = 'app-notice';
        notice.setAttribute('role', 'status');
        document.body.appendChild(notice);
    }
    notice.textContent = message;
    notice.classList.toggle('error', isError);
    notice.classList.add('visible');
}

function hideNotice() {
    const notice = document.getElementById('appNotice');
    if (notice) notice.classList.remove('visible');
}

// ───────────────────────────────────────────────
//  Initial Load
// ───────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    refreshData();
});
