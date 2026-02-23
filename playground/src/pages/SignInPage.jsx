import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getPlaygroundUsers, getOAuthStatus, createPlaygroundUser } from '../services/api';

const COMMON_TIMEZONES = [
    'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
    'America/Toronto', 'America/Vancouver', 'America/Sao_Paulo', 'America/Mexico_City',
    'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Moscow',
    'Asia/Kolkata', 'Asia/Dubai', 'Asia/Singapore', 'Asia/Tokyo',
    'Asia/Shanghai', 'Asia/Hong_Kong', 'Asia/Seoul',
    'Australia/Sydney', 'Australia/Melbourne', 'Pacific/Auckland',
    'Africa/Cairo', 'Africa/Lagos', 'Africa/Johannesburg',
];

const QUICK_PICKS = [
    { label: 'ET', tz: 'America/New_York' },
    { label: 'CT', tz: 'America/Chicago' },
    { label: 'PT', tz: 'America/Los_Angeles' },
    { label: 'GMT', tz: 'Europe/London' },
    { label: 'CET', tz: 'Europe/Paris' },
    { label: 'IST', tz: 'Asia/Kolkata' },
    { label: 'SGT', tz: 'Asia/Singapore' },
    { label: 'JST', tz: 'Asia/Tokyo' },
    { label: 'AEST', tz: 'Australia/Sydney' },
];

export default function SignInPage() {
    const { login } = useAuth();
    const navigate = useNavigate();

    /* -------- Existing user state -------- */
    const [users, setUsers] = useState([]);
    const [selectedUserId, setSelectedUserId] = useState('');
    const [loadingUsers, setLoadingUsers] = useState(true);
    const [loadingLogin, setLoadingLogin] = useState(false);

    /* -------- Create account state -------- */
    const [newName, setNewName] = useState('');
    const [timezone, setTimezone] = useState(
        Intl.DateTimeFormat().resolvedOptions().timeZone
    );
    const [createStep, setCreateStep] = useState(1); // 1 = name, 2 = timezone
    const [loadingCreate, setLoadingCreate] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        (async () => {
            try {
                const list = await getPlaygroundUsers();
                setUsers(list);
            } finally {
                setLoadingUsers(false);
            }
        })();
    }, []);

    /* ---- Login with existing user ---- */
    const handleExistingLogin = async () => {
        if (!selectedUserId) return;
        setLoadingLogin(true);
        setError('');

        try {
            const chosen = users.find((u) => u.user_id === selectedUserId);
            if (!chosen) return;

            let oauthConnected = false;
            try {
                const status = await getOAuthStatus(selectedUserId);
                oauthConnected = status?.data?.connected || false;
            } catch {
                // ignore
            }

            login({
                user_id: chosen.user_id,
                name: chosen.name,
                oauth_connected: oauthConnected,
                timezone: chosen.timezone || 'UTC',
            });
            navigate('/chat');
        } catch (err) {
            setError('Failed to log in. Please try again.');
        } finally {
            setLoadingLogin(false);
        }
    };

    /* ---- Create new account ---- */
    const handleCreateAccount = async () => {
        if (!newName.trim() || !timezone) return;
        setLoadingCreate(true);
        setError('');

        try {
            const callbackUrl = `${window.location.origin}/oauth-callback`;
            const res = await createPlaygroundUser(newName.trim(), callbackUrl, timezone);

            if (res?.code === 201 && res.data) {
                login({
                    user_id: res.data.user_id,
                    name: res.data.name,
                    oauth_connected: false,
                    timezone: timezone,
                });

                if (res.data.auth_url) {
                    window.location.href = res.data.auth_url;
                } else {
                    navigate('/chat');
                }
            } else {
                setError(res?.message || 'Failed to create account.');
                setLoadingCreate(false);
            }
        } catch (err) {
            setError('Failed to start sign-up. Check API connection.');
            setLoadingCreate(false);
        }
    };

    const handleNextStep = () => {
        if (!newName.trim()) return;
        setCreateStep(2);
    };

    return (
        <div className="signin-page">
            <div className="signin-badge">PM Playground</div>

            <div className="signin-header">
                <div className="signin-logo">Peppi</div>
                <h1 className="signin-title">AI-Powered Assistant</h1>
                <p className="signin-subtitle">
                    Test calendar, email, reminders, and chat in an interactive sandbox
                </p>
            </div>

            <div className="signin-cards">
                {/* Card 1 — Select Existing User */}
                <div className="signin-card">
                    <div className="card-icon">&#x1F464;</div>
                    <h2 className="card-title">Welcome Back</h2>
                    <p className="card-desc">
                        Sign in as an existing test user to continue where you left off.
                    </p>

                    <div className="select-wrapper">
                        <select
                            value={selectedUserId}
                            onChange={(e) => setSelectedUserId(e.target.value)}
                            disabled={loadingUsers}
                        >
                            <option value="">
                                {loadingUsers
                                    ? 'Loading users...'
                                    : users.length === 0
                                    ? 'No users yet'
                                    : 'Select a user'}
                            </option>
                            {users.map((u) => (
                                <option key={u.user_id} value={u.user_id}>
                                    {u.name} (ID: {u.user_id})
                                </option>
                            ))}
                        </select>
                    </div>

                    <button
                        className="btn btn-primary"
                        disabled={!selectedUserId || loadingLogin}
                        onClick={handleExistingLogin}
                    >
                        {loadingLogin ? (
                            <>
                                <span className="typing-dot" style={{ width: 6, height: 6 }} />
                                Signing in...
                            </>
                        ) : (
                            'Continue'
                        )}
                    </button>
                </div>

                {/* Card 2 — Create New Account */}
                <div className="signin-card">
                    <div className="card-icon">&#x2728;</div>
                    <h2 className="card-title">Get Started</h2>
                    <p className="card-desc">
                        Create a new user with Google OAuth to test the full experience.
                    </p>

                    {/* Step indicator */}
                    <div className="create-steps">
                        <div className={`create-step ${createStep >= 1 ? (createStep > 1 ? 'completed' : 'active') : ''}`} />
                        <div className={`create-step ${createStep >= 2 ? 'active' : ''}`} />
                    </div>

                    {createStep === 1 ? (
                        <>
                            <div className="step-label">Step 1 — Your name</div>
                            <input
                                className="input-field"
                                type="text"
                                placeholder="Enter your name"
                                value={newName}
                                onChange={(e) => setNewName(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleNextStep()}
                                style={{ marginBottom: 20 }}
                            />
                            <button
                                className="btn btn-secondary"
                                disabled={!newName.trim()}
                                onClick={handleNextStep}
                            >
                                Next
                            </button>
                        </>
                    ) : (
                        <>
                            <button className="step-back" onClick={() => setCreateStep(1)}>
                                &#8592; Back
                            </button>
                            <div className="step-label">Step 2 — Your timezone</div>
                            <div className="select-wrapper">
                                <select
                                    value={timezone}
                                    onChange={(e) => setTimezone(e.target.value)}
                                >
                                    {COMMON_TIMEZONES.map((tz) => (
                                        <option key={tz} value={tz}>
                                            {tz.replace(/_/g, ' ')}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div className="tz-quick-picks">
                                {QUICK_PICKS.map(({ label, tz }) => (
                                    <button
                                        key={tz}
                                        className={`tz-quick-pick ${timezone === tz ? 'selected' : ''}`}
                                        onClick={() => setTimezone(tz)}
                                    >
                                        {label}
                                    </button>
                                ))}
                            </div>

                            <button
                                className="btn btn-primary"
                                disabled={loadingCreate}
                                onClick={handleCreateAccount}
                                style={{ marginTop: 20 }}
                            >
                                {loadingCreate ? (
                                    <>
                                        <span className="typing-dot" style={{ width: 6, height: 6 }} />
                                        Connecting to Google...
                                    </>
                                ) : (
                                    'Sign in with Google'
                                )}
                            </button>
                        </>
                    )}
                </div>
            </div>

            {error && (
                <p
                    style={{
                        color: 'var(--error)',
                        fontSize: 13,
                        marginTop: 16,
                        textAlign: 'center',
                        animation: 'slideUp 0.3s ease-out',
                    }}
                >
                    {error}
                </p>
            )}
        </div>
    );
}
