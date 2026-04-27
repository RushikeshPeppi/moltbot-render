import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { updateUserCity } from '../services/api';

/**
 * CityPromptModal — appears on /chat load for any logged-in user whose city
 * field is empty. Used to backfill city for existing users created before the
 * city column was added (migration 007), and as a safety net for new users
 * who somehow bypassed step 3 of signup.
 *
 * The modal is intentionally NOT dismissable without entering a city — there
 * is no close button, no Escape handler, and the overlay does not close on
 * outside-click. This is the senior-team-test playground, not a permission
 * dance: the web-search "near me" handling depends on having a city.
 *
 * Accessibility: focus auto-lands on the input, Enter submits, the value is
 * trimmed before sending, and any backend error is surfaced inline so the
 * tester can retry without losing input.
 */
export default function CityPromptModal({ onSaved }) {
    const { user, updateCity } = useAuth();
    const [value, setValue] = useState('');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const inputRef = useRef(null);

    useEffect(() => {
        // Auto-focus on mount so testers can just start typing.
        inputRef.current?.focus();
    }, []);

    const handleSave = async () => {
        const trimmed = value.trim();
        if (!trimmed) {
            setError('Please enter a city.');
            return;
        }
        setSaving(true);
        setError('');
        try {
            const res = await updateUserCity(user.user_id, trimmed);
            if (res?.code === 200) {
                updateCity(trimmed);
                onSaved?.(trimmed);
            } else {
                setError(res?.message || 'Failed to save city. Please try again.');
                setSaving(false);
            }
        } catch (err) {
            setError('Network error. Please try again.');
            setSaving(false);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && value.trim() && !saving) {
            handleSave();
        }
    };

    return (
        <div className="settings-overlay" role="dialog" aria-modal="true" aria-labelledby="city-prompt-title">
            <div className="settings-modal" style={{ maxWidth: 460 }}>
                <div className="settings-header">
                    <div className="settings-title" id="city-prompt-title">
                        <span style={{ marginRight: 8 }}>📍</span>One quick thing
                    </div>
                    {/* No close button on purpose — city is mandatory before chat. */}
                </div>
                <div className="settings-body">
                    <div className="settings-section">
                        <p style={{ fontSize: 14, lineHeight: 1.5, marginTop: 0, marginBottom: 16 }}>
                            What city are you in? Peppi uses this to answer "near me"
                            questions about restaurants, weather, places, and similar.
                        </p>
                        <label className="settings-label" htmlFor="city-input">City</label>
                        <input
                            id="city-input"
                            ref={inputRef}
                            className="input-field"
                            type="text"
                            placeholder="e.g. Pune, India or Brooklyn, NY"
                            value={value}
                            onChange={(e) => setValue(e.target.value)}
                            onKeyDown={handleKeyDown}
                            maxLength={100}
                            disabled={saving}
                        />
                        {error && (
                            <div style={{ color: 'var(--error, #c00)', fontSize: 13, marginTop: 8 }}>
                                {error}
                            </div>
                        )}
                        <div className="settings-hint" style={{ marginTop: 12 }}>
                            You can change this later in Settings.
                        </div>
                    </div>
                </div>
                <div className="settings-footer">
                    <button
                        className="btn btn-primary"
                        onClick={handleSave}
                        disabled={saving || !value.trim()}
                        style={{ marginLeft: 'auto' }}
                    >
                        {saving ? 'Saving...' : 'Save'}
                    </button>
                </div>
            </div>
        </div>
    );
}
