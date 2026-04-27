import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { updateUserTimezone, updateUserCity } from '../services/api';

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
    const { user, updateTimezone, updateCity } = useAuth();
    const [tz, setTz] = useState(user?.timezone || 'UTC');
    const [city, setCity] = useState(user?.city || '');
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);
    const [error, setError] = useState('');

    // Whether either field has unsaved changes. Used to gate the Save button
    // and avoid making no-op API calls.
    const tzDirty = tz !== (user?.timezone || 'UTC');
    const cityDirty = city.trim() !== (user?.city || '');
    const isDirty = tzDirty || cityDirty;

    const handleSave = async () => {
        setSaving(true);
        setSaved(false);
        setError('');

        try {
            // Save timezone and city in parallel; only call each endpoint if
            // its corresponding field actually changed.
            const tasks = [];
            if (tzDirty) tasks.push(updateUserTimezone(user.user_id, tz));
            if (cityDirty) {
                const cityClean = city.trim();
                // Backend rejects blank values; we already require non-empty
                // via the city-prompt modal, but guard here too in case the
                // user clears the field in this settings UI.
                if (!cityClean) {
                    setError('City cannot be empty.');
                    setSaving(false);
                    return;
                }
                tasks.push(updateUserCity(user.user_id, cityClean));
            }

            const results = await Promise.all(tasks);
            const ok = results.every((r) => r?.code === 200);
            if (!ok) {
                const failed = results.find((r) => r?.code !== 200);
                throw new Error(failed?.message || 'Failed to save changes.');
            }

            if (tzDirty) updateTimezone(tz);
            if (cityDirty) updateCity(city.trim());

            setSaved(true);
            setTimeout(() => setSaved(false), 2000);
        } catch (err) {
            console.error('Failed to save settings:', err);
            setError(err?.message || 'Failed to save. Please try again.');
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

                    <div className="settings-section">
                        <label className="settings-label" htmlFor="settings-city">City</label>
                        <input
                            id="settings-city"
                            className="input-field"
                            type="text"
                            placeholder="e.g. Pune, India or Brooklyn, NY"
                            value={city}
                            onChange={(e) => setCity(e.target.value)}
                            maxLength={100}
                        />
                        <div className="settings-hint">
                            Used for "near me" queries (restaurants, weather, etc.) via web search.
                        </div>
                    </div>

                    {error && (
                        <div style={{ color: 'var(--error, #c00)', fontSize: 13, marginTop: 4 }}>
                            {error}
                        </div>
                    )}
                </div>
                <div className="settings-footer">
                    {saved && <div className="settings-saved">Saved</div>}
                    <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
                    <button
                        className="btn btn-primary"
                        onClick={handleSave}
                        disabled={saving || !isDirty}
                    >
                        {saving ? 'Saving...' : 'Save'}
                    </button>
                </div>
            </div>
        </div>
    );
}
