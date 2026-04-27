import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import Sidebar from '../components/Sidebar';
import ChatInterface from '../components/ChatInterface';
import StatsView from '../components/StatsView';
import LogsView from '../components/LogsView';
import TokenUsageView from '../components/TokenUsageView';
import SettingsModal from '../components/SettingsModal';
import CityPromptModal from '../components/CityPromptModal';

export default function MainPage({ activeView = 'chat' }) {
    const { user } = useAuth();
    const navigate = useNavigate();
    const [showSettings, setShowSettings] = useState(false);

    // Trigger the city-prompt modal whenever the logged-in user has no city
    // set. Covers two cases: (1) existing users created before migration 007,
    // (2) users who skipped the signup-step-3 city input. Derived directly
    // from auth state so it auto-dismisses the moment updateCity() fires.
    const needsCity = !!user && !(user.city && user.city.trim());

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
            {activeView === 'usage' && <TokenUsageView />}

            {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
            {needsCity && <CityPromptModal />}
        </div>
    );
}
