import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import Sidebar from '../components/Sidebar';
import ChatInterface from '../components/ChatInterface';
import StatsView from '../components/StatsView';
import LogsView from '../components/LogsView';
import SettingsModal from '../components/SettingsModal';

export default function MainPage({ activeView = 'chat' }) {
    const { user } = useAuth();
    const navigate = useNavigate();
    const [showSettings, setShowSettings] = useState(false);

    return (
        <div className="main-layout">
            <Sidebar
                activeView={activeView}
                onNavigate={(v) => navigate(`/${v}`)}
                onOpenSettings={() => setShowSettings(true)}
            />
            {activeView === 'chat' && <ChatInterface />}
            {activeView === 'stats' && <StatsView />}
            {activeView === 'logs' && <LogsView />}

            {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
        </div>
    );
}
