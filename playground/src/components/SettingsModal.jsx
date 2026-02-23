import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { updateUserTimezone } from '../services/api';

const COMMON_TIMEZONES = [
    'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
    'America/Toronto', 'America/Vancouver', 'America/Sao_Paulo', 'America/Mexico_City',
    'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Moscow',
    'Asia/Kolkata', 'Asia/Dubai', 'Asia/Singapore', 'Asia/Tokyo',
    'Asia/Shanghai', 'Asia/Hong_Kong', 'Asia/Seoul',
    'Australia/Sydney', 'Australia/Melbourne', 'Pacific/Auckland',
    'Africa/Cairo', 'Africa/Lagos', 'Africa/Johannesburg',
];

export default function SettingsModal({ onClose }) {
    const { user, updateTimezone } = useAuth();
    const [tz, setTz] = useState(user?.timezone || 'UTC');
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);

    const handleSave = async () => {
        setSaving(true);
        setSaved(false);
        try {
            const res = await updateUserTimezone(user.user_id, tz);
            if (res?.code === 200) {
                updateTimezone(tz);
                setSaved(true);
                setTimeout(() => setSaved(false), 2000);
            }
        } catch (err) {
            console.error('Failed to update timezone:', err);
        } finally {
            setSaving(false);
        }
    };

    useEffect(() => {
        const handleKey = (e) => { if (e.key === 'Escape') onClose(); };
        window.addEventListener('keydown', handleKey);
        return () => window.removeEventListener('keydown', handleKey);
    }, [onClose]);

    return (
        <div className="settings-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
            <div className="settings-modal">
                <div className="settings-header">
                    <div className="settings-title">Settings</div>
                    <button className="settings-close" onClick={onClose}>&#x2715;</button>
                </div>
                <div className="settings-body">
                    <div className="settings-section">
                        <label className="settings-label">Timezone</label>
                        <div className="select-wrapper">
                            <select value={tz} onChange={(e) => setTz(e.target.value)}>
                                {COMMON_TIMEZONES.map((t) => (
                                    <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
                                ))}
                            </select>
                        </div>
                        <div className="settings-hint">
                            Used for calendar events, reminders, and time-aware responses.
                        </div>
                    </div>
                </div>
                <div className="settings-footer">
                    {saved && <div className="settings-saved">Saved</div>}
                    <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
                    <button
                        className="btn btn-primary"
                        onClick={handleSave}
                        disabled={saving || tz === user?.timezone}
                    >
                        {saving ? 'Saving...' : 'Save'}
                    </button>
                </div>
            </div>
        </div>
    );
}
