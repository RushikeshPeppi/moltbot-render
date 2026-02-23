import React from 'react';
import { useAuth } from '../context/AuthContext';

export default function Sidebar({ activeView, onNavigate, onOpenSettings }) {
    const { user, logout } = useAuth();

    const initial = user?.name?.charAt(0)?.toUpperCase() || '?';

    const items = [
        { id: 'chat', icon: '💬', label: 'Chat' },
        { id: 'stats', icon: '📊', label: 'Stats' },
        { id: 'logs', icon: '📋', label: 'Logs' },
    ];

    const handleLogout = () => {
        logout();
        onNavigate('/');
    };

    return (
        <aside className="sidebar">
            <div className="sidebar-brand">
                <div className="sidebar-brand-name">Peppi</div>
                <div className="sidebar-brand-tag">Playground</div>
            </div>

            <nav className="sidebar-nav">
                {items.map((item) => (
                    <button
                        key={item.id}
                        className={`sidebar-item ${activeView === item.id ? 'active' : ''}`}
                        onClick={() => onNavigate(item.id)}
                    >
                        <span className="icon">{item.icon}</span>
                        <span>{item.label}</span>
                    </button>
                ))}
            </nav>

            <div className="sidebar-footer">
                <div className="sidebar-user">
                    <div className="sidebar-avatar">{initial}</div>
                    <div>
                        <div className="sidebar-user-name">{user?.name || 'Unknown'}</div>
                        <div className="sidebar-user-id">ID: {user?.user_id}</div>
                    </div>
                </div>

                <button className="sidebar-item" onClick={onOpenSettings}>
                    <span className="icon">{'\u2699'}</span>
                    <span>Settings</span>
                </button>

                <button className="sidebar-item logout-btn" onClick={handleLogout}>
                    <span className="icon">🚪</span>
                    <span>Logout</span>
                </button>
            </div>
        </aside>
    );
}
