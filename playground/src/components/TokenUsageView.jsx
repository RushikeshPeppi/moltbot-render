import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { getTokenUsage, getPlaygroundUsers, getTokenUsageCsvUrl } from '../services/api';

/*
 * Per-row cost is computed server-side now (FastAPI playground.py:_row_cost)
 * using the canonical Anthropic pricing for Sonnet 4.6:
 *   Input (non-cached):  $3.00 / 1M tokens
 *   Output:              $15.00 / 1M tokens
 *   Cache Read:          $0.30 / 1M tokens (10% of input)
 *   Cache Write 5m TTL:  $3.75 / 1M tokens (1.25x input)
 *   Cache Write 1h TTL:  $6.00 / 1M tokens (2.00x input)
 *
 * The three input counters (input_tokens, cache_read_input_tokens,
 * cache_creation_input_tokens) are NON-OVERLAPPING per Anthropic — they sum
 * to the total billable input. Do NOT subtract cache from input.
 *
 * Server returns row.cost_usd and row.total_input pre-computed; this component
 * just displays them. The block below is kept only for the legacy fallback
 * (the rare row with no token data at all).
 */
const FALLBACK_BLENDED_RATE = 0.15 * 3.00 + 0.85 * 15.00; // last-resort estimate

// Dark-theme select styles (shared between dropdowns)
const selectStyle = {
    padding: '8px 12px',
    background: '#1a1b23',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-sm)',
    color: 'var(--text-primary)',
    fontSize: '13px',
    fontFamily: 'var(--font)',
    cursor: 'pointer',
    minWidth: '160px',
    appearance: 'none',
    WebkitAppearance: 'none',
    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E")`,
    backgroundRepeat: 'no-repeat',
    backgroundPosition: 'right 10px center',
    paddingRight: '32px',
};

export default function TokenUsageView() {
    const { user } = useAuth();
    const [rows, setRows] = useState([]);
    const [allUsers, setAllUsers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [expandedRow, setExpandedRow] = useState(null);

    // Filters
    const [selectedUser, setSelectedUser] = useState('all');
    const [dateFilter, setDateFilter] = useState('all');
    const [customFrom, setCustomFrom] = useState('');
    const [customTo, setCustomTo] = useState('');
    const [actionFilter, setActionFilter] = useState('all');

    // Totals
    const [totalMessages, setTotalMessages] = useState(0);
    const [totalTokens, setTotalTokens] = useState(0);
    const [totalCostUsd, setTotalCostUsd] = useState(0);

    useEffect(() => {
        loadUsers();
    }, []);

    useEffect(() => {
        fetchUsage();
    }, [selectedUser, dateFilter, customFrom, customTo, actionFilter]);

    const loadUsers = async () => {
        try {
            const users = await getPlaygroundUsers();
            setAllUsers(users || []);
        } catch {
            // ignore
        }
    };

    const buildFilters = () => {
        const filters = {};
        if (selectedUser !== 'all') filters.user_id = selectedUser;

        if (dateFilter === 'today') {
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            filters.date_from = today.toISOString();
        } else if (dateFilter === 'week') {
            const week = new Date();
            week.setDate(week.getDate() - 7);
            week.setHours(0, 0, 0, 0);
            filters.date_from = week.toISOString();
        } else if (dateFilter === 'custom') {
            if (customFrom) filters.date_from = new Date(customFrom).toISOString();
            if (customTo) {
                const to = new Date(customTo);
                to.setHours(23, 59, 59, 999);
                filters.date_to = to.toISOString();
            }
        }

        if (actionFilter !== 'all') filters.action_type = actionFilter;
        return filters;
    };

    const fetchUsage = async () => {
        setLoading(true);
        try {
            const filters = buildFilters();
            const res = await getTokenUsage(filters);
            const data = res?.data || {};
            setRows(data.rows || []);
            setTotalMessages(data.total_messages || 0);
            setTotalTokens(data.total_tokens || 0);
            setTotalCostUsd(data.total_cost_usd || 0);
        } catch (err) {
            console.error('Failed to fetch token usage:', err);
        } finally {
            setLoading(false);
        }
    };

    const handleDownloadCsv = () => {
        const filters = buildFilters();
        const url = getTokenUsageCsvUrl(filters);
        window.open(url, '_blank');
    };

    const getActionBadge = (type) => {
        if (!type) return 'chat';
        const t = type.toLowerCase();
        if (t.includes('calendar')) return 'calendar';
        if (t.includes('gmail') || t.includes('email')) return 'gmail';
        if (t.includes('reminder')) return 'reminder';
        return 'chat';
    };

    const getStatusColor = (status) => {
        switch (status) {
            case 'success': return 'var(--success)';
            case 'failed': return 'var(--error)';
            case 'pending': return 'var(--warning)';
            default: return 'var(--text-muted)';
        }
    };

    const formatTokens = (n) => {
        if (!n || n === 0) return '--';
        if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
        if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
        return n.toLocaleString();
    };

    // Cost: prefer server-computed row.cost_usd (correct, single-source-of-truth).
    // Fall back to a blended estimate ONLY when neither cost_usd nor breakdown exist.
    const formatCost = (cost) => {
        if (cost === null || cost === undefined) return '--';
        if (cost === 0) return '$0';
        if (cost < 0.001) return '<$0.001';
        if (cost < 0.01) return `$${cost.toFixed(4)}`;
        if (cost < 1) return `$${cost.toFixed(3)}`;
        return `$${cost.toFixed(2)}`;
    };
    const rowCost = (row) => {
        if (!row) return null;
        if (typeof row.cost_usd === 'number') return row.cost_usd;
        const tokens = row.tokens_used || 0;
        if (!tokens) return null;
        return (tokens / 1_000_000) * FALLBACK_BLENDED_RATE;
    };
    const estimateCost = (tokens, row = null) => {
        const c = row ? rowCost(row) : (tokens ? (tokens / 1_000_000) * FALLBACK_BLENDED_RATE : null);
        return formatCost(c);
    };

    // Count rows that actually have token data
    const trackedRows = rows.filter(r => (r.tokens_used || 0) > 0);
    const untrackedRows = rows.length - trackedRows.length;

    return (
        <div className="stats-container" style={{ padding: '24px' }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <div>
                    <h1 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '2px' }}>Token Usage</h1>
                    <p style={{ fontSize: '11px', color: 'var(--text-muted)', margin: 0 }}>
                        Claude Sonnet 4.6 &middot; in $3.00/M &middot; out $15.00/M &middot; cache read $0.30/M &middot; cache write 5m $3.75/M &middot; cache write 1h $6.00/M
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                    <button onClick={fetchUsage} style={{
                        padding: '8px 16px', background: 'var(--bg-card)', border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)', cursor: 'pointer',
                        fontSize: '13px', fontFamily: 'var(--font)',
                    }}>
                        Refresh
                    </button>
                    <button onClick={handleDownloadCsv} style={{
                        padding: '8px 16px', background: 'var(--accent-gradient)', border: 'none',
                        borderRadius: 'var(--radius-sm)', color: 'white', cursor: 'pointer',
                        fontSize: '13px', fontFamily: 'var(--font)', fontWeight: '500',
                    }}>
                        Download CSV
                    </button>
                </div>
            </div>

            {/* Summary Metrics Bar */}
            <div style={{ display: 'flex', gap: '10px', marginBottom: '16px' }}>
                {[
                    { label: 'Requests', value: totalMessages, color: 'var(--accent-light)' },
                    { label: 'Tokens', value: formatTokens(totalTokens), color: 'var(--accent-light)' },
                    { label: 'Total Cost', value: formatCost(totalCostUsd), color: 'var(--warning)' },
                    { label: 'Avg/Req', value: trackedRows.length > 0 ? formatCost(totalCostUsd / trackedRows.length) : '--', color: 'var(--success)' },
                ].map((m, i) => (
                    <div key={i} style={{
                        flex: 1, display: 'flex', alignItems: 'center', gap: '10px',
                        padding: '10px 16px', background: 'var(--bg-card)', border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-sm)',
                    }}>
                        <span style={{ fontSize: '20px', fontWeight: '700', color: m.color, fontFamily: 'monospace' }}>{m.value}</span>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{m.label}</span>
                    </div>
                ))}
            </div>

            {/* Untracked data notice */}
            {untrackedRows > 0 && (
                <div style={{
                    padding: '10px 16px', marginBottom: '16px', borderRadius: 'var(--radius-sm)',
                    background: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245, 158, 11, 0.2)',
                    fontSize: '12px', color: 'var(--warning)', display: 'flex', alignItems: 'center', gap: '8px',
                }}>
                    <span style={{ fontWeight: '600' }}>{untrackedRows} request{untrackedRows > 1 ? 's' : ''}</span>
                    <span style={{ color: 'var(--text-secondary)' }}>
                        have no token data (pre-tracking). Tokens are tracked for all new requests after Feb 26 deploy.
                    </span>
                </div>
            )}

            {/* Filters */}
            <div style={{ display: 'flex', gap: '12px', marginBottom: '16px', flexWrap: 'wrap', alignItems: 'center' }}>
                {/* User Filter */}
                <select value={selectedUser} onChange={(e) => setSelectedUser(e.target.value)} style={selectStyle}>
                    <option value="all">All Users</option>
                    {allUsers.map((u) => (
                        <option key={u.user_id} value={u.user_id}>
                            {u.name} ({u.user_id.slice(0, 8)})
                        </option>
                    ))}
                </select>

                {/* Date Filter Chips */}
                <div style={{ display: 'flex', gap: '4px' }}>
                    {[
                        { id: 'all', label: 'All Time' },
                        { id: 'today', label: 'Today' },
                        { id: 'week', label: 'Last 7 Days' },
                        { id: 'custom', label: 'Custom' },
                    ].map((opt) => (
                        <button
                            key={opt.id}
                            onClick={() => setDateFilter(opt.id)}
                            style={{
                                padding: '6px 14px',
                                border: `1px solid ${dateFilter === opt.id ? 'var(--accent)' : 'var(--border)'}`,
                                borderRadius: 'var(--radius-full)',
                                background: dateFilter === opt.id ? 'rgba(37, 99, 235, 0.15)' : 'var(--bg-card)',
                                color: dateFilter === opt.id ? 'var(--accent-light)' : 'var(--text-secondary)',
                                fontSize: '12px', cursor: 'pointer', fontFamily: 'var(--font)', fontWeight: '500',
                                transition: 'var(--transition-fast)',
                            }}
                        >
                            {opt.label}
                        </button>
                    ))}
                </div>

                {/* Custom date inputs */}
                {dateFilter === 'custom' && (
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <input type="date" value={customFrom} onChange={(e) => setCustomFrom(e.target.value)}
                            style={{ padding: '6px 10px', background: '#1a1b23', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: '12px', fontFamily: 'var(--font)', colorScheme: 'dark' }} />
                        <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>to</span>
                        <input type="date" value={customTo} onChange={(e) => setCustomTo(e.target.value)}
                            style={{ padding: '6px 10px', background: '#1a1b23', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: '12px', fontFamily: 'var(--font)', colorScheme: 'dark' }} />
                    </div>
                )}

                {/* Action Type Filter */}
                <select value={actionFilter} onChange={(e) => setActionFilter(e.target.value)} style={{ ...selectStyle, minWidth: '140px' }}>
                    <option value="all">All Actions</option>
                    <option value="execute_action">Chat / Task</option>
                    <option value="reminder_delivery">Reminder Delivery</option>
                </select>
            </div>

            {/* Data Table */}
            <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
                {/* Table Header — 11 columns. Token counters use right-align +
                    monospace so digits column-up. Tooltips on the cache columns
                    explain rate differences. */}
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: '110px 80px 1fr 70px 64px 64px 64px 56px 56px 70px 78px',
                    gap: '8px', padding: '12px 20px', borderBottom: '1px solid var(--border)',
                    fontSize: '11px', fontWeight: '600', color: 'var(--text-muted)',
                    textTransform: 'uppercase', letterSpacing: '0.5px',
                }}>
                    <span>Timestamp</span>
                    <span>User</span>
                    <span>Request / Response</span>
                    <span>Status</span>
                    <span style={{ textAlign: 'right' }} title="Fresh non-cached input tokens at $3.00/M">Input</span>
                    <span style={{ textAlign: 'right' }} title="Generated output tokens at $15.00/M">Output</span>
                    <span style={{ textAlign: 'right' }} title="Cache hits at $0.30/M (10% of input)">Cache R</span>
                    <span style={{ textAlign: 'right' }} title="Cache writes at 5min TTL — $3.75/M (1.25× input)">CW 5m</span>
                    <span style={{ textAlign: 'right' }} title="Cache writes at 1h TTL — $6.00/M (2× input)">CW 1h</span>
                    <span style={{ textAlign: 'right' }} title="Total billable input = Input + Cache R + CW 5m + CW 1h (non-overlapping per Anthropic)">Total In</span>
                    <span style={{ textAlign: 'right' }}>Cost</span>
                </div>

                {/* Table Body */}
                <div style={{ maxHeight: 'calc(100vh - 480px)', overflowY: 'auto' }}>
                    {loading ? (
                        <div style={{ display: 'flex', justifyContent: 'center', padding: '40px' }}>
                            <div className="oauth-spinner" style={{ width: '24px', height: '24px' }} />
                        </div>
                    ) : rows.length === 0 ? (
                        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                            No data found for the selected filters.
                        </div>
                    ) : (
                        <>
                            {rows.map((row) => {
                                const tokens = row.tokens_used || 0;
                                const hasTokens = tokens > 0;
                                const inp = row.input_tokens || 0;
                                const out = row.output_tokens || 0;
                                const cr = row.cache_read || 0;
                                const cw5 = row.cache_write_5m || 0;
                                const cw1h = row.cache_write_1h || 0;
                                const cwLegacy = (cw5 + cw1h) > 0 ? 0 : (row.cache_write || 0);
                                // total_input from server, but compute defensively if missing.
                                const totalInput = row.total_input ?? (inp + cr + cw5 + cw1h + cwLegacy);
                                const numCell = (n, color) => (
                                    <span style={{
                                        fontSize: '11px', textAlign: 'right', fontFamily: 'monospace',
                                        lineHeight: '1.6',
                                        color: n > 0 ? (color || 'var(--text-secondary)') : 'var(--text-muted)',
                                    }}>
                                        {n > 0 ? formatTokens(n) : '--'}
                                    </span>
                                );
                                return (
                                    <div key={row.id}>
                                        <div
                                            onClick={() => setExpandedRow(expandedRow === row.id ? null : row.id)}
                                            style={{
                                                display: 'grid',
                                                gridTemplateColumns: '110px 80px 1fr 70px 64px 64px 64px 56px 56px 70px 78px',
                                                gap: '8px', padding: '11px 20px', borderBottom: '1px solid var(--border)',
                                                cursor: 'pointer', transition: 'background 0.15s ease',
                                                background: expandedRow === row.id ? 'var(--bg-card-hover)' : 'transparent',
                                            }}
                                            onMouseEnter={(e) => { if (expandedRow !== row.id) e.currentTarget.style.background = 'var(--bg-card)'; }}
                                            onMouseLeave={(e) => { if (expandedRow !== row.id) e.currentTarget.style.background = 'transparent'; }}
                                        >
                                            <span style={{ fontSize: '11px', color: 'var(--text-muted)', lineHeight: '1.6' }}>
                                                {new Date(row.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                            </span>
                                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', lineHeight: '1.6' }}>
                                                {row.user_name || row.user_id?.slice(0, 10)}
                                            </span>
                                            <div style={{ overflow: 'hidden' }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                    <span className={`stats-history-type ${getActionBadge(row.action_type)}`} style={{ width: 'fit-content', flexShrink: 0 }}>
                                                        {getActionBadge(row.action_type)}
                                                    </span>
                                                    <span style={{ fontSize: '13px', color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                        {row.request_summary || (row.action_type === 'reminder_delivery' ? 'Reminder delivery' : 'No summary')}
                                                    </span>
                                                </div>
                                            </div>
                                            <span style={{ fontSize: '12px', fontWeight: '600', color: getStatusColor(row.status), lineHeight: '1.6' }}>
                                                {row.status?.toUpperCase()}
                                            </span>
                                            {numCell(inp, '#60a5fa')}
                                            {numCell(out, '#f59e0b')}
                                            {numCell(cr, '#34d399')}
                                            {numCell(cw5, '#a78bfa')}
                                            {numCell(cw1h + cwLegacy, '#c084fc')}
                                            {numCell(totalInput)}
                                            <span style={{
                                                fontSize: '11px', textAlign: 'right', fontFamily: 'monospace', lineHeight: '1.6',
                                                color: hasTokens ? 'var(--warning)' : 'var(--text-muted)',
                                                fontWeight: '600',
                                            }}>
                                                {hasTokens ? estimateCost(tokens, row) : '--'}
                                            </span>
                                        </div>

                                        {/* Expanded Detail */}
                                        {expandedRow === row.id && (
                                            <div style={{ padding: '16px 20px', background: 'rgba(37, 99, 235, 0.04)', borderBottom: '1px solid var(--border)' }}>
                                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                                    <div>
                                                        <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px', fontWeight: '600' }}>Request</div>
                                                        <div style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: '1.5', wordBreak: 'break-word' }}>
                                                            {row.request_summary || 'N/A'}
                                                        </div>
                                                    </div>
                                                    <div>
                                                        <div style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px', fontWeight: '600' }}>Response</div>
                                                        <div style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: '1.5', wordBreak: 'break-word', maxHeight: '200px', overflowY: 'auto' }}>
                                                            {row.response_summary || 'N/A'}
                                                        </div>
                                                    </div>
                                                </div>
                                                <div style={{ display: 'flex', gap: '20px', marginTop: '12px', fontSize: '11px', color: 'var(--text-muted)', flexWrap: 'wrap' }}>
                                                    <span>ID: {row.id}</span>
                                                    <span>Session: {row.session_id?.slice(0, 16)}</span>
                                                    {hasTokens && <>
                                                        <span>Total tokens: {tokens.toLocaleString()}</span>
                                                        <span style={{ color: '#60a5fa' }}>Input: {formatTokens(row.input_tokens || 0)}</span>
                                                        <span style={{ color: '#f59e0b' }}>Output: {formatTokens(row.output_tokens || 0)}</span>
                                                        {(row.cache_read > 0) && <span style={{ color: '#34d399' }}>Cache Read: {formatTokens(row.cache_read)}</span>}
                                                        {(row.cache_write_5m > 0) && <span style={{ color: '#a78bfa' }}>Cache Write 5m: {formatTokens(row.cache_write_5m)}</span>}
                                                        {(row.cache_write_1h > 0) && <span style={{ color: '#c084fc' }}>Cache Write 1h: {formatTokens(row.cache_write_1h)}</span>}
                                                        {(!row.cache_write_5m && !row.cache_write_1h && row.cache_write > 0) && <span style={{ color: '#c084fc' }}>Cache Write (legacy): {formatTokens(row.cache_write)}</span>}
                                                        {row.total_input != null && <span>Total billable input: {formatTokens(row.total_input)}</span>}
                                                        <span style={{ color: 'var(--warning)', fontWeight: 600 }}>Cost: {estimateCost(tokens, row)}</span>
                                                    </>}
                                                    {!hasTokens && <span style={{ color: 'var(--warning)' }}>No token data (pre-tracking)</span>}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                );
                            })}

                            {/* Summary Footer Row — same 11-column grid as the body */}
                            <div style={{
                                display: 'grid',
                                gridTemplateColumns: '110px 80px 1fr 70px 64px 64px 64px 56px 56px 70px 78px',
                                gap: '8px', padding: '14px 20px', background: 'rgba(37, 99, 235, 0.08)',
                                borderTop: '2px solid var(--accent)', fontWeight: '600', fontSize: '12px',
                                fontFamily: 'monospace',
                            }}>
                                <span style={{ color: 'var(--accent-light)', fontFamily: 'var(--font)' }}>TOTAL</span>
                                <span style={{ color: 'var(--text-muted)', fontSize: '11px', fontFamily: 'var(--font)' }}>{selectedUser === 'all' ? `${allUsers.length} users` : ''}</span>
                                <span style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font)' }}>
                                    {totalMessages} messages{untrackedRows > 0 ? ` (${trackedRows.length} tracked)` : ''}
                                </span>
                                <span></span>
                                <span style={{ textAlign: 'right', color: '#60a5fa' }}>{formatTokens(rows.reduce((a, r) => a + (r.input_tokens || 0), 0))}</span>
                                <span style={{ textAlign: 'right', color: '#f59e0b' }}>{formatTokens(rows.reduce((a, r) => a + (r.output_tokens || 0), 0))}</span>
                                <span style={{ textAlign: 'right', color: '#34d399' }}>{formatTokens(rows.reduce((a, r) => a + (r.cache_read || 0), 0))}</span>
                                <span style={{ textAlign: 'right', color: '#a78bfa' }}>{formatTokens(rows.reduce((a, r) => a + (r.cache_write_5m || 0), 0))}</span>
                                <span style={{ textAlign: 'right', color: '#c084fc' }}>{formatTokens(rows.reduce((a, r) => {
                                    const cw5 = r.cache_write_5m || 0;
                                    const cw1h = r.cache_write_1h || 0;
                                    const legacy = (cw5 + cw1h) > 0 ? 0 : (r.cache_write || 0);
                                    return a + cw1h + legacy;
                                }, 0))}</span>
                                <span style={{ textAlign: 'right', color: 'var(--text-primary)' }}>{formatTokens(rows.reduce((a, r) => a + (r.total_input || 0), 0))}</span>
                                <span style={{ textAlign: 'right', color: 'var(--warning)', fontWeight: '700' }}>{formatCost(totalCostUsd)}</span>
                            </div>
                        </>
                    )}
                </div>
            </div>

            {/* Methodology Note */}
            <div style={{ marginTop: '16px', padding: '12px 16px', borderRadius: 'var(--radius-sm)', background: 'var(--bg-card)', border: '1px solid var(--border)', fontSize: '11px', color: 'var(--text-muted)', lineHeight: '1.6' }}>
                <span style={{ fontWeight: '600', color: 'var(--text-secondary)' }}>Methodology: </span>
                Token counts are returned by Anthropic's Messages API (Claude Sonnet 4.6) and stored
                per request in the audit log. The three input counters
                <code style={{ padding: '0 4px' }}>input_tokens</code>,
                <code style={{ padding: '0 4px' }}>cache_read_input_tokens</code>, and
                <code style={{ padding: '0 4px' }}>cache_creation_input_tokens</code>
                are non-overlapping per Anthropic's docs — the table's "Total In" column is
                their sum and equals the total billable input. Cost is computed server-side
                using the canonical rates ($3.00 in, $15.00 out, $0.30 cache read,
                $3.75 cache write 5m, $6.00 cache write 1h, all per 1M tokens). For
                authoritative invoicing, reconcile with Anthropic Console.
            </div>
        </div>
    );
}
