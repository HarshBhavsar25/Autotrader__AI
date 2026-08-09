let ws = null;

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('WebSocket Connected to AutoTrader_AI');
        document.getElementById('scanStatusText').innerText = '24/7 SCANNER ACTIVE';
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'TELEMETRY') {
                updateTelemetry(data);
            }
        } catch (err) {
            console.error('Error parsing telemetry:', err);
        }
    };

    ws.onclose = () => {
        document.getElementById('scanStatusText').innerText = 'RECONNECTING...';
        setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = (err) => {
        console.error('WebSocket Error:', err);
        ws.close();
    };
}

function updateTelemetry(data) {
    const wallet = data.wallet || {};
    const activePos = data.active_position;
    const rankings = data.rankings || [];
    const recentTrades = data.recent_trades || [];
    const logs = data.logs || [];

    // 1. Update Wallet Stats & Mode
    if (wallet.futures_balance_inr !== undefined) {
        const modeSelect = document.getElementById('headerModeSelect');
        if (modeSelect && wallet.trading_mode) {
            modeSelect.value = wallet.trading_mode;
        }

        document.getElementById('futuresBalance').innerText = `₹${wallet.futures_balance_inr.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
        document.getElementById('spotBalance').innerText = `₹${wallet.spot_balance_inr.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
        document.getElementById('dailyPnL').innerText = `${wallet.daily_net_pnl_inr >= 0 ? '+' : ''}₹${wallet.daily_net_pnl_inr.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
        
        const progPct = wallet.daily_target_progress_pct || 0;
        document.getElementById('dailyTargetProgressBar').style.width = `${Math.min(100, Math.max(0, progPct))}%`;
        document.getElementById('dailyTargetText').innerText = `Target: ₹${wallet.daily_target_inr} / 24h (${progPct.toFixed(1)}%)`;

        document.getElementById('baseCapitalText').innerText = `Base Capital: ₹${wallet.base_capital_inr.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
        document.getElementById('totalTransferredText').innerText = `Total Transferred: ₹${wallet.total_transferred_inr.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;

        // Insufficient balance warning banner
        const warnBanner = document.getElementById('insufficientBalanceBanner');
        if (wallet.trading_mode === 'LIVE' && wallet.insufficient_balance) {
            warnBanner.style.display = 'block';
            if (wallet.balance_warning_msg) warnBanner.innerText = wallet.balance_warning_msg;
        } else {
            warnBanner.style.display = 'none';
        }
    }

    // 2. Update Performance Metrics
    if (recentTrades.length > 0) {
        const winning = recentTrades.filter(t => t.net_pnl_inr > 0).length;
        const total = recentTrades.length;
        const winRate = ((winning / total) * 100).toFixed(1);
        document.getElementById('winRate').innerText = `${winRate}%`;
        document.getElementById('totalTradesText').innerText = `${total} Trades Recorded`;
    }

    // 3. Update Active Positions Section (Scrollable Multi-Positions)
    const noTradeMsg = document.getElementById('noActiveTradeMsg');
    const container = document.getElementById('activePositionsListContainer');
    const countBadge = document.getElementById('activePositionsCountBadge');
    const closeAllBtn = document.getElementById('btnCloseAllBtn');

    const activePositions = data.active_positions || (data.active_position ? [data.active_position] : []);

    if (activePositions.length > 0) {
        noTradeMsg.style.display = 'none';
        container.style.display = 'flex';
        closeAllBtn.style.display = 'inline-block';
        countBadge.innerText = `${activePositions.length} Open`;

        container.innerHTML = activePositions.map(pos => {
            const netPnL = pos.net_pnl_inr || 0;
            const pnlClass = netPnL >= 0 ? 'color: var(--accent-green);' : 'color: var(--accent-red);';
            const sideClass = pos.side ? pos.side.toLowerCase() : 'long';
            const beText = pos.is_breakeven ? '<span style="color: var(--accent-green);">ACTIVE (Locked)</span>' : '<span style="color: var(--text-muted);">INACTIVE</span>';

            return `
                <div class="position-card-item">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <span class="trade-side-badge ${sideClass}">${pos.side} ${pos.leverage}x</span>
                            <span style="font-size: 1.2rem; font-weight: 700; font-family: 'JetBrains Mono';">${pos.symbol}</span>
                        </div>
                        <div style="font-size: 1.2rem; font-weight: 700; font-family: 'JetBrains Mono'; ${pnlClass}">
                            ${netPnL >= 0 ? '+' : ''}₹${netPnL.toFixed(2)}
                        </div>
                    </div>

                    <div class="trade-details-grid" style="margin: 10px 0;">
                        <div class="detail-item">
                            <div class="detail-label">Entry Price</div>
                            <div class="detail-val">₹${pos.entry_price}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Current Price</div>
                            <div class="detail-val">₹${pos.current_price}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Position Size</div>
                            <div class="detail-val">₹${pos.position_size_inr}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Stop Loss</div>
                            <div class="detail-val" style="color: var(--accent-red);">₹${pos.stop_loss}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Take Profit</div>
                            <div class="detail-val" style="color: var(--accent-green);">₹${pos.take_profit}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Break-Even</div>
                            <div class="detail-val" style="font-size: 0.85rem;">${beText}</div>
                        </div>
                    </div>

                    <div style="display: flex; justify-content: flex-end; margin-top: 10px;">
                        <button class="btn btn-danger" style="font-size: 0.8rem; padding: 6px 14px;" onclick="closeSinglePosition('${pos.symbol}')">
                            ⚡ Exit ${pos.symbol}
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    } else {
        noTradeMsg.style.display = 'block';
        container.style.display = 'none';
        closeAllBtn.style.display = 'none';
        countBadge.innerText = '0 Open';
    }

    // 4. Update Market Scanner Rankings Table
    const tableBody = document.getElementById('rankingsTableBody');
    if (rankings.length > 0) {
        tableBody.innerHTML = rankings.map(r => {
            const sigClass = r.signal === 'LONG' ? 'color: var(--accent-green);' : (r.signal === 'SHORT' ? 'color: var(--accent-red);' : 'color: var(--text-muted);');
            return `
                <tr>
                    <td style="font-weight: 600; font-family: 'JetBrains Mono';">${r.symbol}</td>
                    <td style="font-weight: 700; ${sigClass}">${r.signal}</td>
                    <td>
                        <div class="score-bar">
                            <span style="font-family: 'JetBrains Mono'; width: 36px;">${r.confidence_score}%</span>
                            <div style="flex-grow: 1; background: rgba(255,255,255,0.08); height: 6px; border-radius: 3px;">
                                <div class="score-fill" style="width: ${r.confidence_score}%; background: ${r.confidence_score >= 80 ? 'var(--accent-green)' : 'var(--accent-cyan)'};"></div>
                            </div>
                        </div>
                    </td>
                    <td style="font-family: 'JetBrains Mono';">₹${r.price}</td>
                    <td>${r.rsi}</td>
                    <td style="font-family: 'JetBrains Mono'; color: var(--accent-green);">₹${r.expected_net_pnl.toFixed(2)}</td>
                </tr>
            `;
        }).join('');
    }

    // 5. Update Recent Trades Table
    const tradeBody = document.getElementById('tradeHistoryBody');
    if (recentTrades && recentTrades.length > 0) {
        tradeBody.innerHTML = recentTrades.map(t => {
            const rawTime = t.exit_time || t.entry_time || t.timestamp;
            const timeStr = rawTime ? new Date(rawTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : 'Just now';
            const pnlVal = t.net_pnl_inr || 0.0;
            const pnlClass = pnlVal >= 0 ? 'color: var(--accent-green);' : 'color: var(--accent-red);';
            const cleanStatus = (t.status || 'CLOSED').replace('CLOSED_', '');
            return `
                <tr>
                    <td style="font-size: 0.8rem; color: var(--text-muted);">${timeStr}</td>
                    <td style="font-weight: 600; font-family: 'JetBrains Mono';">${t.symbol}</td>
                    <td style="font-weight: 700; color: ${t.side === 'LONG' ? 'var(--accent-green)' : 'var(--accent-red)'};">${t.side}</td>
                    <td style="font-size: 0.85rem; font-family: 'JetBrains Mono';">₹${t.entry_price} → ₹${t.exit_price || t.entry_price}</td>
                    <td style="font-weight: 700; font-family: 'JetBrains Mono'; ${pnlClass}">${pnlVal >= 0 ? '+' : ''}₹${pnlVal.toFixed(2)}</td>
                    <td style="font-size: 0.8rem; color: var(--text-muted);">${cleanStatus}</td>
                </tr>
            `;
        }).join('');
    } else {
        tradeBody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 20px;">
                    No completed trades recorded yet. Open trades will auto-close here on Trailing SL / TP hit.
                </td>
            </tr>
        `;
    }

    // 6. Update System Logs Terminal
    const logBox = document.getElementById('systemLogBox');
    if (logs.length > 0) {
        logBox.innerHTML = logs.map(l => {
            const timeStr = new Date(l.timestamp).toLocaleTimeString();
            const levelClass = l.level.toLowerCase();
            return `<div class="log-entry"><span class="time">[${timeStr}]</span> <span class="${levelClass}">[${l.category}]</span> ${l.message}</div>`;
        }).join('');
    }
}

async function executeManualTransfer() {
    if (!confirm('Transfer realized profits from Futures Wallet to Spot Wallet now?')) return;
    try {
        const res = await fetch('/api/transfer-now', { method: 'POST' });
        const data = await res.json();
        alert(data.message);
    } catch (err) {
        alert('Transfer failed: ' + err);
    }
}

async function closeActivePosition() {
    if (!confirm('Are you sure you want to exit ALL active positions?')) return;
    try {
        const res = await fetch('/api/close-position-now', { method: 'POST' });
        const data = await res.json();
        alert(data.message || 'All positions closed successfully.');
    } catch (err) {
        alert('Failed to close positions: ' + err);
    }
}

async function closeSinglePosition(symbol) {
    if (!confirm(`Are you sure you want to exit position for ${symbol}?`)) return;
    try {
        const res = await fetch('/api/close-single-position', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol: symbol })
        });
        const data = await res.json();
        alert(data.message || `Position closed for ${symbol}.`);
    } catch (err) {
        alert('Failed to close position: ' + err);
    }
}

function openWalletModal() {
    document.getElementById('walletModal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('walletModal').style.display = 'none';
}

async function saveWalletCredentials() {
    const exchange = document.getElementById('modalExchange').value;
    const mode = document.getElementById('modalMode').value;
    const apiKey = document.getElementById('modalApiKey').value;
    const apiSecret = document.getElementById('modalApiSecret').value;

    if (mode === 'LIVE' && (!apiKey || !apiSecret)) {
        alert('Please enter both API Key and API Secret to connect your real-time exchange wallet.');
        return;
    }

    try {
        const res = await fetch('/api/save-credentials', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                exchange_name: exchange,
                trading_mode: mode,
                api_key: apiKey,
                api_secret: apiSecret
            })
        });
        const data = await res.json();
        if (data.success) {
            alert(data.message);
            // Save to browser localStorage so keys persist across refreshes
            localStorage.setItem('autotrader_exchange', exchange);
            localStorage.setItem('autotrader_mode', mode);
            localStorage.setItem('autotrader_api_key', apiKey);
            localStorage.setItem('autotrader_api_secret', apiSecret);

            closeModal();
            document.getElementById('headerModeSelect').value = mode;
        } else {
            alert('Error: ' + data.message);
        }
    } catch (err) {
        alert('Failed to save credentials: ' + err);
    }
}

async function loadSavedCredentialsUI() {
    const savedKey = localStorage.getItem('autotrader_api_key');
    const savedSecret = localStorage.getItem('autotrader_api_secret');
    const savedExchange = localStorage.getItem('autotrader_exchange') || 'coindcx';
    const savedMode = localStorage.getItem('autotrader_mode') || 'PAPER';

    if (savedKey) document.getElementById('modalApiKey').value = savedKey;
    if (savedSecret) document.getElementById('modalApiSecret').value = savedSecret;
    if (savedExchange) document.getElementById('modalExchange').value = savedExchange;
    if (savedMode) document.getElementById('headerModeSelect').value = savedMode;

    // Automatically sync client-side localStorage credentials with backend session on page load
    if (savedKey && savedSecret) {
        try {
            await fetch('/api/save-credentials', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    exchange_name: savedExchange,
                    trading_mode: savedMode,
                    api_key: savedKey,
                    api_secret: savedSecret
                })
            });
        } catch (e) {
            console.log('Background credential sync from localStorage:', e);
        }
    }
}

async function toggleBotEngine() {
    try {
        const res = await fetch('/api/toggle-bot', { method: 'POST' });
        const data = await res.json();
        const btn = document.getElementById('btnToggleBot');
        if (data.is_bot_running) {
            btn.innerText = '⏸️ Pause Engine';
            btn.style.background = 'linear-gradient(135deg, var(--accent-green), #059669)';
        } else {
            btn.innerText = '▶️ Start Engine';
            btn.style.background = 'linear-gradient(135deg, var(--accent-cyan), #0284C7)';
        }
    } catch (err) {
        alert('Failed to toggle bot engine: ' + err);
    }
}

async function resetPaperBalance() {
    if (!confirm('Reset Paper Trading balance back to initial ₹1,000.00?')) return;
    try {
        const res = await fetch('/api/reset-paper-balance', { method: 'POST' });
        const data = await res.json();
        alert(data.message);
    } catch (err) {
        alert('Failed to reset paper balance: ' + err);
    }
}

async function changeModeFromHeader(mode) {
    try {
        const res = await fetch('/api/set-trading-mode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
        });
        const data = await res.json();
        if (!data.success && data.requires_keys) {
            alert(data.message);
            document.getElementById('headerModeSelect').value = 'PAPER';
            openWalletModal();
        } else {
            alert(data.message);
        }
    } catch (err) {
        alert('Failed to set trading mode: ' + err);
        document.getElementById('headerModeSelect').value = 'PAPER';
    }
}

// Initial WebSocket Connection & Saved Credentials Load
window.onload = () => {
    loadSavedCredentialsUI();
    connectWebSocket();
};
