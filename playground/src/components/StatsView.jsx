import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { getActionHistory, getOAuthStatus, getCredentialsStatus } from '../services/api';

export default function StatsView() {
    const { user } = useAuth();
    const [history, setHistory] = useState([]);
    const [oauthStatus, setOauthStatus] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!user?.user_id) return;

        const load = async () => {
            setLoading(true);
            try {
                const [histRes, oauthRes] = await Promise.all([
                    getActionHistory(user.user_id, 30),
                    getOAuthStatus(user.user_id),
                ]);
                setHistory(histRes?.data?.actions || []);
                setOauthStatus(oauthRes?.data || null);
            } catch {
                // handle gracefully
            } finally {
                setLoading(false);
            }
        };

        load();
    }, [user?.user_id]);

    const totalActions = history.length;
    const successCount = history.filter((a) => a.status === 'success').length;
    const failCount = history.filter((a) => a.status === 'failed').length;

    const getActionBadge = (type) => {
        if (!type) return 'chat';
        const t = type.toLowerCase();
        if (t.includes('calendar')) return 'calendar';
        if (t.includes('gmail') || t.includes('email')) return 'gmail';
        if (t.includes('reminder')) return 'reminder';
        return 'chat';
    };

    return (
        <div className="stats-container">
            <h1 className="stats-title">Dashboard</h1>
            <p className="stats-subtitle">
                Stats and activity for {user?.name} (ID: {user?.user_id})
            </p>

            <div className="stats-grid">
                <div className="stat-card">
                    <div className="stat-icon">📊</div>
                    <div className="stat-value">{totalActions}</div>
                    <div className="stat-label">Total Actions</div>
                </div>
                <div className="stat-card">
                    <div className="stat-icon">✅</div>
                    <div className="stat-value">{successCount}</div>
                    <div className="stat-label">Successful</div>
                </div>
                <div className="stat-card">
                    <div className="stat-icon">❌</div>
                    <div className="stat-value">{failCount}</div>
                    <div className="stat-label">Failed</div>
                </div>
                <div className="stat-card">
                    <div className="stat-icon">🔗</div>
                    <div className="stat-value">
                        {oauthStatus?.connected ? 'Yes' : 'No'}
                    </div>
                    <div className="stat-label">Google Connected</div>
                </div>
            </div>

            <div className="stats-history">
                <div className="stats-history-header">Recent Activity</div>
                <div className="stats-history-list">
                    {loading ? (
                        <div className="stats-history-item">
                            <div className="stats-history-text" style={{ opacity: 0.5 }}>
                                Loading activity…
                            </div>
                        </div>
                    ) : history.length === 0 ? (
                        <div className="stats-history-item">
                            <div className="stats-history-text" style={{ opacity: 0.5 }}>
                                No activity yet. Start chatting to see history here.
                            </div>
                        </div>
                    ) : (
                        history.map((action, i) => (
                            <div className="stats-history-item" key={action.id || i}>
                                <div
                                    className={`stats-history-type ${getActionBadge(action.action_type)}`}
                                >
                                    {getActionBadge(action.action_type)}
                                </div>
                                <div className="stats-history-text">
                                    {action.request_summary || action.action_type || 'Action'}
                                </div>
                                <div className="stats-history-time">
                                    {action.created_at
                                        ? new Date(action.created_at).toLocaleString([], {
                                            month: 'short',
                                            day: 'numeric',
                                            hour: '2-digit',
                                            minute: '2-digit',
                                        })
                                        : ''}
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </div>
        </div>
    );
}
