/* ═══════════════════════════════════════════════════════════
   WhatsApp Campaign Dashboard - Core JavaScript
   ═══════════════════════════════════════════════════════════ */

// ─── API Helper ──────────────────────────────────────────
const api = {
    async get(url) {
        const res = await fetch(url);
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        return res.json();
    },
    async post(url, data) {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        return res.json();
    },
    async put(url, data) {
        const res = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        return res.json();
    },
    async del(url) {
        const res = await fetch(url, { method: 'DELETE' });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        return res.json();
    },
    async upload(url, formData) {
        const res = await fetch(url, { method: 'POST', body: formData });
        if (!res.ok) {
            try {
                const errData = await res.json();
                throw new Error(errData.detail || res.statusText);
            } catch (e) {
                // If response is not JSON (e.g., HTML error page), show generic message
                throw new Error(`Upload failed: ${res.status} ${res.statusText}. Check server logs.`);
            }
        }
        return res.json();
    },
};

// ─── Toast Notifications ─────────────────────────────────
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const icons = { success: 'check-circle', error: 'exclamation-circle', info: 'info-circle', warning: 'exclamation-triangle' };
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<i class="fas fa-${icons[type] || 'info-circle'}"></i> ${message}`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ─── Sidebar Toggle ──────────────────────────────────────
function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
}

// ─── Modal Helpers ───────────────────────────────────────
function openModal(id) {
    document.getElementById(id).classList.add('active');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('active');
    }
});

// ─── Formatting Helpers ──────────────────────────────────
function formatDate(isoStr) {
    if (!isoStr) return '—';
    const d = new Date(isoStr);
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function timeAgo(isoStr) {
    if (!isoStr) return 'Never';
    const diff = Date.now() - new Date(isoStr).getTime();
    const secs = Math.floor(diff / 1000);
    if (secs < 60) return `${secs}s ago`;
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
}

function statusBadge(status) {
    return `<span class="badge badge-${status}">${status}</span>`;
}

function batteryIcon(level) {
    const cls = level > 60 ? 'high' : level > 20 ? 'medium' : 'low';
    return `
        <div class="battery-bar">
            <div class="battery-bar-fill ${cls}" style="width:${level}%"></div>
        </div>
        <span style="font-size:12px;margin-left:4px">${level}%</span>
    `;
}

// ─── Server Health Check ─────────────────────────────────
async function checkServerHealth() {
    try {
        await api.get('/api/agent/health');
        const el = document.getElementById('serverStatus');
        if (el) el.innerHTML = '<span class="status-dot online"></span><span>Server Online</span>';
    } catch {
        const el = document.getElementById('serverStatus');
        if (el) el.innerHTML = '<span class="status-dot offline"></span><span>Server Offline</span>';
    }
}

// Check health every 30s
setInterval(checkServerHealth, 30000);

// ─── Confirm Dialog ──────────────────────────────────────
function confirmAction(message) {
    return confirm(message);
}
