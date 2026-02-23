import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import SignInPage from './pages/SignInPage';
import MainPage from './pages/MainPage';
import OAuthCallback from './pages/OAuthCallback';

function ProtectedRoute({ children }) {
    const { user } = useAuth();
    if (!user) return <Navigate to="/" replace />;
    return children;
}

function AppRoutes() {
    const { user } = useAuth();

    return (
        <Routes>
            <Route
                path="/"
                element={user ? <Navigate to="/chat" replace /> : <SignInPage />}
            />
            <Route path="/oauth-callback/*" element={<OAuthCallback />} />
            <Route
                path="/chat"
                element={
                    <ProtectedRoute>
                        <MainPage activeView="chat" />
                    </ProtectedRoute>
                }
            />
            <Route
                path="/stats"
                element={
                    <ProtectedRoute>
                        <MainPage activeView="stats" />
                    </ProtectedRoute>
                }
            />
            <Route
                path="/logs"
                element={
                    <ProtectedRoute>
                        <MainPage activeView="logs" />
                    </ProtectedRoute>
                }
            />
        </Routes>
    );
}

export default function App() {
    return (
        <BrowserRouter>
            <AuthProvider>
                <AppRoutes />
            </AuthProvider>
        </BrowserRouter>
    );
}
