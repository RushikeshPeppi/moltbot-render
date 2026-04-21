import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { getTokenUsage, getPlaygroundUsers, getTokenUsageCsvUrl } from '../services/api';

/*
 * Claude Sonnet 4.6 Pricing (as of Apr 2026):
 *   Input (non-cached): $3.00 per 1M tokens
 *   Output:             $15.00 per 1M tokens
 *   Cache Read:         $0.30 per 1M tokens (90% discount)
 *   Cache Write:        $3.75 per 1M tokens (25% premium)
 *
 * Token counts come from OpenClaw's usage metadata (Anthropic API).
 * Cache read/write are reported separately for accurate cost calculation.
 */
const SONNET_INPUT_RATE      = 3.00;   // $ per 1M non-cached input tokens
const SONNET_OUTPUT_RATE     = 15.00;  // $ per 1M output tokens
const SONNET_CACHE_READ_RATE = 0.30;   // $ per 1M cache read tokens
const SONNET_CACHE_WRITE_RATE = 3.75;  // $ per 1M cache write tokens
// Blended fallback for rows without detailed breakdown
const BLENDED_RATE = 0.40 * SONNET_INPUT_RATE + 0.60 * SONNET_OUTPUT_RATE;

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

    // Cost calculation using Anthropic tiered pricing
    const estimateCost = (tokens, row = null) => {
        if (!tokens || tokens === 0) return '--';
        let cost;
        if (row && (row.input_tokens || row.output_tokens)) {
            // Use detailed pricing when we have the breakdown
            const inp = row.input_tokens || 0;
            const out = row.output_tokens || 0;
            const cr = row.cache_read || 0;
            const cw = row.cache_write || 0;
            const nonCached = Math.max(0, inp - cr - cw);
            cost = (nonCached / 1_000_000) * SONNET_INPUT_RATE +
                   (cr / 1_000_000) * SONNET_CACHE_READ_RATE +
                   (cw / 1_000_000) * SONNET_CACHE_WRITE_RATE +
                   (out / 1_000_000) * SONNET_OUTPUT_RATE;
        } else {
            // Fallback: blended rate
            cost = (tokens / 1_000_000) * BLENDED_RATE;
        }
        if (cost < 0.001) return '<$0.001';
        if (cost < 0.01) return `$${cost.toFixed(4)}`;
        return `$${cost.toFixed(3)}`;
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
                        Claude Sonnet 4.6 &middot; $3.00/1M in &middot; $15.00/1M out &middot; ~${BLENDED_RATE.toFixed(2)}/1M blended
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
                    { label: 'Est. Cost', value: estimateCost(totalTokens), color: 'var(--warning)' },
                    { label: 'Avg/Req', value: trackedRows.length > 0 ? formatTokens(Math.round(totalTokens / trackedRows.length)) : '--', color: 'var(--success)' },
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
                {/* Table Header */}
                <div style={{
                    display: 'grid', gridTemplateColumns: '130px 90px 1fr 80px 90px 80px',
                    gap: '10px', padding: '12px 20px', borderBottom: '1px solid var(--border)',
                    fontSize: '11px', fontWeight: '600', color: 'var(--text-muted)',
                    textTransform: 'uppercase', letterSpacing: '0.5px',
                }}>
                    <span>Timestamp</span>
                    <span>User</span>
                    <span>Request / Response</span>
                    <span>Status</span>
                    <span style={{ textAlign: 'right' }}>Tokens</span>
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
                                return (
                                    <div key={row.id}>
                                        <div
                                            onClick={() => setExpandedRow(expandedRow === row.id ? null : row.id)}
                                            style={{
                                                display: 'grid', gridTemplateColumns: '130px 90px 1fr 80px 90px 80px',
                                                gap: '10px', padding: '11px 20px', borderBottom: '1px solid var(--border)',
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
                                            <span style={{
                                                fontSize: '12px', fontWeight: '600', textAlign: 'right', fontFamily: 'monospace', lineHeight: '1.6',
                                                color: hasTokens ? 'var(--text-primary)' : 'var(--text-muted)',
                                            }}>
                                                {hasTokens ? formatTokens(tokens) : '--'}
                                            </span>
                                            <span style={{
                                                fontSize: '11px', textAlign: 'right', fontFamily: 'monospace', lineHeight: '1.6',
                                                color: hasTokens ? 'var(--text-secondary)' : 'var(--text-muted)',
                                            }}>
                                                {hasTokens ? estimateCost(tokens) : '--'}
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
                                                        <span>Total: {tokens.toLocaleString()}</span>
                                                        <span style={{ color: '#60a5fa' }}>Input: {formatTokens(row.input_tokens || 0)}</span>
                                                        <span style={{ color: '#f59e0b' }}>Output: {formatTokens(row.output_tokens || 0)}</span>
                                                        {(row.cache_read > 0) && <span style={{ color: '#34d399' }}>Cache Read: {formatTokens(row.cache_read)}</span>}
                                                        {(row.cache_write > 0) && <span style={{ color: '#a78bfa' }}>Cache Write: {formatTokens(row.cache_write)}</span>}
                                                        <span>Cost: {estimateCost(tokens, row)}</span>
                                                    </>}
                                                    {!hasTokens && <span style={{ color: 'var(--warning)' }}>No token data (pre-tracking)</span>}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                );
                            })}

                            {/* Summary Footer Row */}
                            <div style={{
                                display: 'grid', gridTemplateColumns: '130px 90px 1fr 80px 90px 80px',
                                gap: '10px', padding: '14px 20px', background: 'rgba(37, 99, 235, 0.08)',
                                borderTop: '2px solid var(--accent)', fontWeight: '600', fontSize: '13px',
                            }}>
                                <span style={{ color: 'var(--accent-light)' }}>TOTAL</span>
                                <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>{selectedUser === 'all' ? `${allUsers.length} users` : ''}</span>
                                <span style={{ color: 'var(--text-secondary)' }}>
                                    {totalMessages} messages{untrackedRows > 0 ? ` (${trackedRows.length} tracked)` : ''}
                                </span>
                                <span></span>
                                <span style={{ color: 'var(--accent-light)', textAlign: 'right', fontFamily: 'monospace' }}>{formatTokens(totalTokens)}</span>
                                <span style={{ color: 'var(--warning)', textAlign: 'right', fontFamily: 'monospace' }}>{estimateCost(totalTokens)}</span>
                            </div>
                        </>
                    )}
                </div>
            </div>

            {/* Methodology Note */}
            <div style={{ marginTop: '16px', padding: '12px 16px', borderRadius: 'var(--radius-sm)', background: 'var(--bg-card)', border: '1px solid var(--border)', fontSize: '11px', color: 'var(--text-muted)', lineHeight: '1.6' }}>
                <span style={{ fontWeight: '600', color: 'var(--text-secondary)' }}>Methodology: </span>
                Token counts are from Anthropic's API via OpenClaw.
                Cost uses Claude Sonnet 4.6 rates: $3.00/1M input, $15.00/1M output, $0.30/1M cache read, $3.75/1M cache write.
                For exact billing, use Anthropic Console.
            </div>
        </div>
    );
}
