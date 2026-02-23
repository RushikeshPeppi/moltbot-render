import React from 'react';

/**
 * Parse structured content (email lists, calendar events, etc.)
 * and return formatted JSX instead of a plain text wall.
 */
function formatContent(text) {
    if (!text || typeof text !== 'string') return text;

    // Detect email list pattern: contains multiple 📧 markers
    const emailMarker = '📧';
    if (text.includes(emailMarker) && text.split(emailMarker).length > 2) {
        return formatEmailList(text);
    }

    // Detect calendar/event list pattern: contains multiple 📅 markers
    const calMarker = '📅';
    if (text.includes(calMarker) && text.split(calMarker).length > 2) {
        return formatGenericList(text, calMarker, 'calendar');
    }

    // Default: preserve newlines
    return text.split('\n').map((line, i) => (
        <React.Fragment key={i}>
            {i > 0 && <br />}
            {line}
        </React.Fragment>
    ));
}

function formatEmailList(text) {
    // Split on 📧 — first chunk is the intro text
    const parts = text.split('📧').map((s) => s.trim()).filter(Boolean);
    const isIntro = !parts[0]?.startsWith('From:');
    const intro = isIntro ? parts.shift() : null;

    const emails = parts.map((raw, i) => {
        const fromMatch = raw.match(/From:\s*(.+?)(?:\s*\|\s*|$)/);
        const subjectMatch = raw.match(/Subject:\s*(.+)/);
        return (
            <div key={i} className="fmt-email-item">
                <div className="fmt-email-from">{fromMatch?.[1] || raw}</div>
                {subjectMatch && (
                    <div className="fmt-email-subject">{subjectMatch[1]}</div>
                )}
            </div>
        );
    });

    return (
        <div className="fmt-email-list">
            {intro && <div className="fmt-intro">{intro}</div>}
            {emails}
        </div>
    );
}

function formatGenericList(text, marker, type) {
    const parts = text.split(marker).map((s) => s.trim()).filter(Boolean);
    const isIntro = !parts[0]?.includes('|');
    const intro = isIntro ? parts.shift() : null;

    return (
        <div className={`fmt-list fmt-list--${type}`}>
            {intro && <div className="fmt-intro">{intro}</div>}
            {parts.map((item, i) => (
                <div key={i} className="fmt-list-item">{item}</div>
            ))}
        </div>
    );
}

export default function ChatMessage({ role, content, timestamp }) {
    const isUser = role === 'user';
    const avatar = isUser ? '👤' : '🤖';

    const timeStr = timestamp
        ? new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : '';

    return (
        <div className={`message ${role}`}>
            <div className="message-avatar">{avatar}</div>
            <div>
                <div className="message-content">
                    {isUser ? content : formatContent(content)}
                </div>
                {timeStr && <div className="message-time">{timeStr}</div>}
            </div>
        </div>
    );
}
