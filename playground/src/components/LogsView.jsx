import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { getActionHistory } from '../services/api';

export default function LogsView() {
    const { user } = useAuth();
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchLogs = async () => {
        if (!user?.user_id) return;
        setLoading(true);
        try {
            const res = await getActionHistory(user.user_id, 100);
            setLogs(res?.data?.actions || []);
        } catch (err) {
            console.error('Failed to fetch logs:', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchLogs();
    }, [user?.user_id]);

    const getStatusColor = (status) => {
        switch (status) {
            case 'success': return 'var(--success)';
            case 'failed': return 'var(--error)';
            case 'pending': return 'var(--warning)';
            default: return 'var(--text-muted)';
        }
    };

    return (
        <div className="stats-container" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                <div>
                    <h1 className="stats-title">Audit Logs</h1>
                    <p className="stats-subtitle">Full transaction history for user {user?.user_id}</p>
                </div>
                <button className="btn btn-secondary" onClick={fetchLogs} style={{ width: 'auto', padding: '8px 16px' }}>
                    Refresh
                </button>
            </div>

            <div className="stats-history" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
                <div className="stats-history-header" style={{ display: 'grid', gridTemplateColumns: '150px 1fr 100px 150px', gap: '16px', fontWeight: 'bold' }}>
                    <span>Time</span>
                    <span>Action / Summary</span>
                    <span>Status</span>
                    <span>ID</span>
                </div>
                <div className="stats-history-list" style={{ maxHeight: 'calc(100vh - 250px)' }}>
                    {loading ? (
                        <div className="stats-history-item" style={{ justifyContent: 'center', padding: '40px' }}>
                            <div className="oauth-spinner" style={{ width: '24px', height: '24px' }} />
                        </div>
                    ) : logs.length === 0 ? (
                        <div className="stats-history-item" style={{ justifyContent: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                            No logs found for this user.
                        </div>
                    ) : (
                        logs.map((log) => (
                            <div key={log.id} className="stats-history-item" style={{ display: 'grid', gridTemplateColumns: '150px 1fr 100px 150px', gap: '16px', alignItems: 'center', padding: '16px 20px' }}>
                                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                                    {new Date(log.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                                </span>
                                <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                                    <span className={`stats-history-type ${log.action_type?.toLowerCase().includes('calendar') ? 'calendar' : log.action_type?.toLowerCase().includes('gmail') ? 'gmail' : log.action_type?.toLowerCase().includes('reminder') ? 'reminder' : 'chat'}`} style={{ width: 'fit-content', marginBottom: '4px' }}>
                                        {log.action_type}
                                    </span>
                                    <span style={{ fontSize: '13px', color: 'var(--text-primary)', whiteSpace: 'normal', lineBreak: 'anywhere' }}>
                                        {log.request_summary || 'No summary'}
                                    </span>
                                </div>
                                <span style={{ fontSize: '12px', fontWeight: '600', color: getStatusColor(log.status) }}>
                                    {log.status.toUpperCase()}
                                </span>
                                <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                                    {log.id}
                                </span>
                            </div>
                        ))
                    )}
                </div>
            </div>
        </div>
    );
}
