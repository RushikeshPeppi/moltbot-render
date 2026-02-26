import React, { useState, useEffect, useMemo } from 'react';
import { useAuth } from '../context/AuthContext';
import { getTokenUsage, getPlaygroundUsers, getTokenUsageCsvUrl } from '../services/api';

export default function TokenUsageView() {
    const { user } = useAuth();
    const [rows, setRows] = useState([]);
    const [allUsers, setAllUsers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [expandedRow, setExpandedRow] = useState(null);

    // Filters
    const [selectedUser, setSelectedUser] = useState('all');
    const [dateFilter, setDateFilter] = useState('all'); // 'all', 'today', 'week', 'custom'
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
        if (!n) return '0';
        if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
        if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
        return n.toString();
    };

    // Estimate cost: ~$0.0025 per 1K tokens (Gemini 2.5 Pro blended avg)
    const estimateCost = (tokens) => {
        const cost = (tokens / 1000) * 0.0025;
        if (cost < 0.01) return '<$0.01';
        return `$${cost.toFixed(2)}`;
    };

    return (
        <div className="stats-container" style={{ padding: '24px' }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
                <div>
                    <h1 className="stats-title">Token Usage</h1>
                    <p className="stats-subtitle">Monitor AI token consumption and estimate costs</p>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                    <button className="btn btn-secondary" onClick={fetchUsage} style={{ width: 'auto', padding: '8px 16px', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '13px', fontFamily: 'var(--font)' }}>
                        Refresh
                    </button>
                    <button onClick={handleDownloadCsv} style={{ width: 'auto', padding: '8px 16px', background: 'var(--accent-gradient)', border: 'none', borderRadius: 'var(--radius-sm)', color: 'white', cursor: 'pointer', fontSize: '13px', fontFamily: 'var(--font)', fontWeight: '500' }}>
                        Download CSV
                    </button>
                </div>
            </div>

            {/* Summary Cards */}
            <div className="stats-grid" style={{ marginBottom: '20px' }}>
                <div className="stat-card">
                    <div className="stat-icon">{'#'}</div>
                    <div className="stat-value">{totalMessages}</div>
                    <div className="stat-label">Total Requests</div>
                </div>
                <div className="stat-card">
                    <div className="stat-icon" style={{ fontFamily: 'monospace' }}>Tk</div>
                    <div className="stat-value">{formatTokens(totalTokens)}</div>
                    <div className="stat-label">Total Tokens</div>
                </div>
                <div className="stat-card">
                    <div className="stat-icon">~</div>
                    <div className="stat-value">{estimateCost(totalTokens)}</div>
                    <div className="stat-label">Est. Cost</div>
                </div>
                <div className="stat-card">
                    <div className="stat-icon" style={{ fontFamily: 'monospace' }}>Avg</div>
                    <div className="stat-value">{totalMessages > 0 ? formatTokens(Math.round(totalTokens / totalMessages)) : '0'}</div>
                    <div className="stat-label">Avg Tokens/Req</div>
                </div>
            </div>

            {/* Filters */}
            <div className="usage-filters" style={{ display: 'flex', gap: '12px', marginBottom: '16px', flexWrap: 'wrap', alignItems: 'center' }}>
                {/* User Filter */}
                <select
                    value={selectedUser}
                    onChange={(e) => setSelectedUser(e.target.value)}
                    style={{
                        padding: '8px 12px', background: 'var(--bg-input)', border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: '13px',
                        fontFamily: 'var(--font)', cursor: 'pointer', minWidth: '160px',
                    }}
                >
                    <option value="all">All Users</option>
                    {allUsers.map((u) => (
                        <option key={u.user_id} value={u.user_id}>
                            {u.name} ({u.user_id.slice(0, 8)}...)
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
                        <input
                            type="date"
                            value={customFrom}
                            onChange={(e) => setCustomFrom(e.target.value)}
                            style={{
                                padding: '6px 10px', background: 'var(--bg-input)', border: '1px solid var(--border)',
                                borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: '12px',
                                fontFamily: 'var(--font)',
                            }}
                        />
                        <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>to</span>
                        <input
                            type="date"
                            value={customTo}
                            onChange={(e) => setCustomTo(e.target.value)}
                            style={{
                                padding: '6px 10px', background: 'var(--bg-input)', border: '1px solid var(--border)',
                                borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: '12px',
                                fontFamily: 'var(--font)',
                            }}
                        />
                    </div>
                )}

                {/* Action Type Filter */}
                <select
                    value={actionFilter}
                    onChange={(e) => setActionFilter(e.target.value)}
                    style={{
                        padding: '8px 12px', background: 'var(--bg-input)', border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: '13px',
                        fontFamily: 'var(--font)', cursor: 'pointer',
                    }}
                >
                    <option value="all">All Actions</option>
                    <option value="execute_action">Chat / Task</option>
                    <option value="reminder_delivery">Reminder Delivery</option>
                </select>
            </div>

            {/* Data Table */}
            <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
                {/* Table Header */}
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: '140px 100px 1fr 90px 100px',
                    gap: '12px', padding: '12px 20px',
                    borderBottom: '1px solid var(--border)',
                    fontSize: '11px', fontWeight: '600',
                    color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px',
                }}>
                    <span>Timestamp</span>
                    <span>User</span>
                    <span>Request / Response</span>
                    <span>Status</span>
                    <span style={{ textAlign: 'right' }}>Tokens</span>
                </div>

                {/* Table Body */}
                <div style={{ maxHeight: 'calc(100vh - 420px)', overflowY: 'auto' }}>
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
                            {rows.map((row) => (
                                <div key={row.id}>
                                    <div
                                        onClick={() => setExpandedRow(expandedRow === row.id ? null : row.id)}
                                        style={{
                                            display: 'grid',
                                            gridTemplateColumns: '140px 100px 1fr 90px 100px',
                                            gap: '12px', padding: '12px 20px',
                                            borderBottom: '1px solid var(--border)',
                                            cursor: 'pointer',
                                            transition: 'background 0.15s ease',
                                            background: expandedRow === row.id ? 'var(--bg-card-hover)' : 'transparent',
                                        }}
                                        onMouseEnter={(e) => { if (expandedRow !== row.id) e.currentTarget.style.background = 'var(--bg-card)'; }}
                                        onMouseLeave={(e) => { if (expandedRow !== row.id) e.currentTarget.style.background = 'transparent'; }}
                                    >
                                        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                                            {new Date(row.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                        </span>
                                        <span style={{ fontSize: '12px', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {row.user_name || row.user_id?.slice(0, 10)}
                                        </span>
                                        <div style={{ overflow: 'hidden' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                <span className={`stats-history-type ${getActionBadge(row.action_type)}`} style={{ width: 'fit-content', flexShrink: 0 }}>
                                                    {getActionBadge(row.action_type)}
                                                </span>
                                                <span style={{ fontSize: '13px', color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                    {row.request_summary || 'No summary'}
                                                </span>
                                            </div>
                                        </div>
                                        <span style={{ fontSize: '12px', fontWeight: '600', color: getStatusColor(row.status) }}>
                                            {row.status?.toUpperCase()}
                                        </span>
                                        <span style={{ fontSize: '13px', fontWeight: '600', color: row.tokens_used ? 'var(--text-primary)' : 'var(--text-muted)', textAlign: 'right', fontFamily: 'monospace' }}>
                                            {formatTokens(row.tokens_used || 0)}
                                        </span>
                                    </div>

                                    {/* Expanded Detail */}
                                    {expandedRow === row.id && (
                                        <div style={{
                                            padding: '16px 20px', background: 'rgba(37, 99, 235, 0.04)',
                                            borderBottom: '1px solid var(--border)',
                                        }}>
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
                                            <div style={{ display: 'flex', gap: '24px', marginTop: '12px', fontSize: '11px', color: 'var(--text-muted)' }}>
                                                <span>ID: {row.id}</span>
                                                <span>Session: {row.session_id?.slice(0, 12)}...</span>
                                                <span>Tokens: {(row.tokens_used || 0).toLocaleString()}</span>
                                                <span>Est: {estimateCost(row.tokens_used || 0)}</span>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ))}

                            {/* Summary Footer Row */}
                            <div style={{
                                display: 'grid',
                                gridTemplateColumns: '140px 100px 1fr 90px 100px',
                                gap: '12px', padding: '14px 20px',
                                background: 'rgba(37, 99, 235, 0.08)',
                                borderTop: '2px solid var(--accent)',
                                fontWeight: '600', fontSize: '13px',
                            }}>
                                <span style={{ color: 'var(--accent-light)' }}>TOTAL</span>
                                <span style={{ color: 'var(--text-muted)' }}>{selectedUser === 'all' ? `${allUsers.length} users` : ''}</span>
                                <span style={{ color: 'var(--text-secondary)' }}>{totalMessages} messages</span>
                                <span style={{ color: 'var(--text-muted)' }}>{estimateCost(totalTokens)}</span>
                                <span style={{ color: 'var(--accent-light)', textAlign: 'right', fontFamily: 'monospace' }}>{formatTokens(totalTokens)}</span>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
