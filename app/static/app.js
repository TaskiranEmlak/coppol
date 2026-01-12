/**
 * Polymarket Copy Trade Bot - Dashboard JavaScript
 */

// ==================== State ====================
let ws = null;
let reconnectAttempts = 0;
let performanceChart = null;
let currentCategory = 'all';

// ==================== WebSocket ====================

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('WebSocket connected');
        reconnectAttempts = 0;
        updateConnectionStatus('connected');
        addLog('Sunucuya bağlandı', 'success');
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected');
        updateConnectionStatus('disconnected');
        addLog('Bağlantı kesildi, yeniden bağlanılıyor...', 'warning');

        // Reconnect with exponential backoff
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
        reconnectAttempts++;
        setTimeout(connectWebSocket, delay);
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        addLog('Bağlantı hatası', 'error');
    };

    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        handleMessage(message);
    };
}

function handleMessage(message) {
    switch (message.type) {
        case 'connected':
            updateStatus(message.data.status);
            updateWhalesSummary(message.data.whales);
            break;

        case 'status_update':
            updateStatus(message.data);
            break;

        case 'new_trade':
            handleNewTrade(message.data);
            break;

        case 'trade_closed':
            handleTradeClosed(message.data);
            break;

        case 'pong':
            // Keep-alive response
            break;

        case 'scanning':
            showScanningEffect(message.count);
            break;
    }
}

function showScanningEffect(count) {
    const statusDot = document.querySelector('.status-dot');
    statusDot.classList.add('scanning');

    // Add temporary scanning badge
    const badge = document.getElementById('scan-badge');
    if (badge) {
        badge.classList.add('active');
        badge.textContent = `🔍 Taranıyor (${count})...`;
        setTimeout(() => {
            badge.classList.remove('active');
            statusDot.classList.remove('scanning');
        }, 2000);
    }

}


function updateConnectionStatus(status) {
    const statusEl = document.getElementById('connection-status');
    const dot = statusEl.querySelector('.status-dot');
    const text = statusEl.querySelector('span:last-child');

    dot.className = 'status-dot ' + status;

    switch (status) {
        case 'connected':
            text.textContent = 'Bağlı';
            break;
        case 'disconnected':
            text.textContent = 'Bağlantı kesildi';
            break;
        default:
            text.textContent = 'Bağlanıyor...';
    }
}

// ==================== UI Updates ====================

function updateStatus(data) {
    // Balance
    document.getElementById('balance').textContent = formatCurrency(data.current_balance);

    // PnL
    const pnlEl = document.getElementById('pnl');
    pnlEl.textContent = formatCurrency(data.pnl, true);
    pnlEl.className = 'stat-value' + (data.pnl < 0 ? ' negative' : '');

    // Win Rate
    document.getElementById('winrate').textContent = formatPercent(data.win_rate);

    // Trade Count
    document.getElementById('trade-count').textContent =
        `${data.wins}W / ${data.losses}L (${data.total_trades})`;

    // Update timestamp
    document.getElementById('last-update').textContent =
        'Son güncelleme: ' + new Date().toLocaleTimeString('tr-TR');
}

function updateWhalesSummary(data) {
    document.getElementById('hot-count').textContent = data.hot_count || 0;
    document.getElementById('warm-count').textContent = data.warm_count || 0;
    document.getElementById('cold-count').textContent = data.cold_count || 0;
}

function handleNewTrade(data) {
    addLog(`📝 KOPYA: ${data.side} on "${data.market}" | $${data.amount} | ${data.whale}`, 'success');
    loadOpenPositions();
    loadTrades();
}

function handleTradeClosed(data) {
    const status = data.profit > 0 ? '✅' : '❌';
    addLog(`${status} KAPANDI: $${data.profit.toFixed(2)} kar/zarar`, data.profit > 0 ? 'success' : 'error');
    loadOpenPositions();
    loadTrades();
}

function addLog(message, type = 'info') {
    const logContainer = document.getElementById('activity-log');
    const entry = document.createElement('div');
    entry.className = 'log-entry ' + type;
    entry.textContent = `[${new Date().toLocaleTimeString('tr-TR')}] ${message}`;

    logContainer.insertBefore(entry, logContainer.firstChild);

    // Keep only last 50 entries
    while (logContainer.children.length > 50) {
        logContainer.removeChild(logContainer.lastChild);
    }
}

// ==================== Data Loading ====================

async function loadWhales() {
    try {
        const response = await fetch('/api/whales');
        const data = await response.json();

        renderWhaleList(data.whales);
        updateWhalesSummary(data.summary);
    } catch (error) {
        console.error('Error loading whales:', error);
        addLog('Whale verisi yüklenemedi', 'error');
    }
}

function renderWhaleList(whales) {
    const container = document.getElementById('whale-list');

    if (!whales || whales.length === 0) {
        container.innerHTML = '<div class="empty-state">Whale bulunamadı</div>';
        return;
    }

    container.innerHTML = whales.map(whale => `
        <div class="whale-item">
            <div class="whale-rank">#${whale.rank}</div>
            <div class="whale-heat">${whale.heat_emoji}</div>
            <div class="whale-info">
                <div class="whale-name">${whale.name}</div>
                <div class="whale-stats-mini">${whale.win_rate} WR | ${whale.profit}</div>
            </div>
            <div class="whale-score ${whale.heat_level}">${whale.score}</div>
        </div>
    `).join('');
}

async function loadTrades() {
    try {
        const response = await fetch('/api/trades');
        const data = await response.json();

        renderOpenPositions(data.open_positions);
        renderRecentTrades(data.history);
    } catch (error) {
        console.error('Error loading trades:', error);
    }
}

function renderOpenPositions(positions) {
    const container = document.getElementById('open-positions');

    if (!positions || positions.length === 0) {
        container.innerHTML = '<div class="empty-state">Açık pozisyon yok</div>';
        return;
    }

    container.innerHTML = positions.map(pos => `
        <div class="position-item">
            <span class="position-side ${pos.side}">${pos.side}</span>
            <span class="position-market">${pos.market.substring(0, 30)}...</span>
            <span class="position-amount">$${pos.amount.toFixed(2)}</span>
        </div>
    `).join('');
}

function renderRecentTrades(trades) {
    const container = document.getElementById('recent-trades');

    if (!trades || trades.length === 0) {
        container.innerHTML = '<div class="empty-state">Henüz işlem yok</div>';
        return;
    }

    container.innerHTML = trades.map(trade => `
        <div class="trade-item">
            <span class="trade-side ${trade.side}">${trade.side}</span>
            <span class="trade-market">${trade.market.substring(0, 25)}...</span>
            <span class="trade-profit ${trade.is_winner ? 'win' : 'loss'}">${trade.profit}</span>
        </div>
    `).join('');
}

async function loadMarkets() {
    try {
        const url = currentCategory === 'all'
            ? '/api/markets'
            : `/api/markets?category=${currentCategory}`;

        const response = await fetch(url);
        const data = await response.json();

        renderMarkets(data.by_category);
    } catch (error) {
        console.error('Error loading markets:', error);
        addLog('Market verisi yüklenemedi', 'error');
    }
}

function renderMarkets(byCategory) {
    const container = document.getElementById('markets-list');
    let markets = [];

    if (currentCategory === 'all') {
        // Merge all categories
        for (const cat in byCategory) {
            markets = markets.concat(byCategory[cat].slice(0, 5));
        }
    } else if (byCategory[currentCategory]) {
        markets = byCategory[currentCategory];
    }

    if (markets.length === 0) {
        container.innerHTML = '<div class="empty-state">Market bulunamadı</div>';
        return;
    }

    container.innerHTML = markets.map(market => `
        <div class="market-item">
            <div class="market-question">${market.question}</div>
            <div class="market-meta">
                <div class="market-prices">
                    <span class="price-yes">YES: ${(market.yes_price * 100).toFixed(0)}¢</span>
                    <span class="price-no">NO: ${(market.no_price * 100).toFixed(0)}¢</span>
                </div>
                <span>Vol: $${formatNumber(market.volume_24h)}</span>
            </div>
        </div>
    `).join('');
}

async function loadOpenPositions() {
    await loadTrades();
}

// ==================== Chart ====================

function initChart() {
    const ctx = document.getElementById('performance-chart').getContext('2d');

    performanceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Bakiye',
                data: [],
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 3,
                pointHoverRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: (ctx) => `Bakiye: $${ctx.raw.toFixed(2)}`
                    }
                }
            },
            scales: {
                x: {
                    display: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    },
                    ticks: {
                        color: '#64748b',
                        maxTicksLimit: 10
                    }
                },
                y: {
                    display: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    },
                    ticks: {
                        color: '#64748b',
                        callback: (value) => '$' + value
                    }
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            }
        }
    });

    loadBalanceHistory();
}

async function loadBalanceHistory() {
    try {
        const response = await fetch('/api/balance-history');
        const data = await response.json();

        if (data.history && data.history.length > 0) {
            updateChart(data.history);
        }
    } catch (error) {
        console.error('Error loading balance history:', error);
    }
}

function updateChart(history) {
    if (!performanceChart) return;

    performanceChart.data.labels = history.map(h => {
        const date = new Date(h.timestamp);
        return date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
    });

    performanceChart.data.datasets[0].data = history.map(h => h.balance);
    performanceChart.update();
}

// ==================== Actions ====================

async function refreshWhales() {
    addLog('Whale verileri yenileniyor...', 'info');

    try {
        await fetch('/api/refresh-whales', { method: 'POST' });
        await loadWhales();
        addLog('Whale verileri güncellendi', 'success');
    } catch (error) {
        addLog('Whale verileri güncellenemedi', 'error');
    }
}

async function resetTrading() {
    if (!confirm('Paper trading sıfırlanacak. Emin misiniz?')) {
        return;
    }

    try {
        await fetch('/api/reset', { method: 'POST' });
        addLog('Paper trading sıfırlandı', 'warning');

        // Reload all data
        loadStatus();
        loadTrades();
        loadBalanceHistory();
    } catch (error) {
        addLog('Sıfırlama başarısız', 'error');
    }
}

async function loadStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();

        updateStatus(data.trading);
        updateWhalesSummary(data.whales);
    } catch (error) {
        console.error('Error loading status:', error);
    }
}

// ==================== Helpers ====================

function formatCurrency(value, showSign = false) {
    const formatted = Math.abs(value).toLocaleString('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });

    if (showSign && value !== 0) {
        return (value > 0 ? '+' : '-') + formatted;
    }
    return value < 0 ? '-' + formatted : formatted;
}

function formatPercent(value) {
    return value.toFixed(1) + '%';
}

function formatNumber(value) {
    if (value >= 1000000) {
        return (value / 1000000).toFixed(1) + 'M';
    }
    if (value >= 1000) {
        return (value / 1000).toFixed(1) + 'K';
    }
    return value.toFixed(0);
}

async function simulateTrade() {
    addLog('⚡ Test işlemi başlatılıyor...', 'info');
    try {
        const response = await fetch('/api/simulate', { method: 'POST' });
        const data = await response.json();

        if (data.status === 'ok') {
            addLog('✅ Test işlemi başarılı!', 'success');
        } else {
            addLog('❌ Test başarısız: ' + data.message, 'error');
        }
    } catch (error) {
        console.error('Test error:', error);
        addLog('❌ Test hatası', 'error');
    }
}

// ==================== Event Listeners ====================

document.addEventListener('DOMContentLoaded', () => {
    // Initialize
    connectWebSocket();
    loadStatus();
    loadWhales();
    loadTrades();
    loadMarkets();
    initChart();

    // Category tabs
    document.querySelectorAll('.cat-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.cat-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentCategory = tab.dataset.category;
            loadMarkets();
        });
    });

    // Keep WebSocket alive
    setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
        }
    }, 30000);

    // Periodic updates
    setInterval(loadStatus, 30000);
    setInterval(loadBalanceHistory, 60000);
});
