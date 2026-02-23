import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function OAuthCallback() {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const { user, updateOAuthStatus } = useAuth();
    const [message, setMessage] = useState('Completing authentication…');

    useEffect(() => {
        const status = searchParams.get('status');
        const error = searchParams.get('error');

        if (status === 'success') {
            setMessage('Google connected successfully! Redirecting…');
            updateOAuthStatus(true);
            setTimeout(() => navigate('/chat', { replace: true }), 1200);
        } else if (status === 'error') {
            setMessage(`Authentication failed: ${error || 'Unknown error'}. Redirecting…`);
            setTimeout(() => navigate('/', { replace: true }), 2500);
        } else {
            // No status param — just redirect home
            setTimeout(() => navigate('/', { replace: true }), 1000);
        }
    }, [searchParams, navigate, updateOAuthStatus]);

    return (
        <div className="oauth-callback">
            <div className="oauth-spinner" />
            <p className="oauth-text">{message}</p>
        </div>
    );
}
