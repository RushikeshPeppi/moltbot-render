import React from 'react';

export default function StageIndicator({ status, name, detail, time, index }) {
    const icons = {
        pending: '',
        active: '⟳',
        completed: '✓',
        skipped: '—',
    };

    return (
        <div className={`stage ${status}`} style={{ animationDelay: `${index * 0.08}s` }}>
            <div className="stage-dot">
                {status === 'completed' ? '✓' : status === 'active' ? '⟳' : status === 'skipped' ? '—' : (index + 1)}
            </div>
            <div className="stage-info">
                <div className="stage-name">{name}</div>
                {detail && <div className="stage-detail">{detail}</div>}
                {time && <div className="stage-time">{time}</div>}
            </div>
        </div>
    );
}
