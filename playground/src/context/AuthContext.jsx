import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const AuthContext = createContext(null);

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be inside AuthProvider');
    return ctx;
}

const STORAGE_KEY = 'peppi_playground_user';

export function AuthProvider({ children }) {
    const [user, setUser] = useState(() => {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            return saved ? JSON.parse(saved) : null;
        } catch {
            return null;
        }
    });

    useEffect(() => {
        if (user) {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
        } else {
            localStorage.removeItem(STORAGE_KEY);
        }
    }, [user]);

    const login = (userData) => {
        setUser({
            user_id: userData.user_id,
            name: userData.name,
            oauth_connected: userData.oauth_connected || false,
            timezone: userData.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
            logged_in_at: new Date().toISOString(),
        });
    };

    const logout = () => {
        setUser(null);
    };

    const updateOAuthStatus = useCallback((connected) => {
        setUser((prev) => prev ? { ...prev, oauth_connected: connected } : null);
    }, []);

    const updateTimezone = useCallback((tz) => {
        setUser((prev) => prev ? { ...prev, timezone: tz } : null);
    }, []);

    return (
        <AuthContext.Provider value={{ user, login, logout, updateOAuthStatus, updateTimezone }}>
            {children}
        </AuthContext.Provider>
    );
}
