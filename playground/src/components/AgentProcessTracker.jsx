import React, { useState, useEffect, useRef } from 'react';
import StageIndicator from './StageIndicator';

// ── Core pipeline stages — always shown ────────────────────────────────────
const BASE_STAGES = [
  { id: 'received', name: 'Message Received', detail: 'Request captured by FastAPI' },
  { id: 'auth', name: 'Auth Token Retrieved', detail: 'Fetching credentials from DB' },
  { id: 'routing', name: 'Agent Routing', detail: 'Deciding: Chat or Task?' },
];

/**
 * Map an action_performed string to a friendly label + icon.
 * e.g. "calendar_create" → "📅 Calendar Create"
 */
function describeSkill(actionType) {
  if (!actionType) return null;
  const t = actionType.toLowerCase();

  // Google Workspace skills
  if (t.includes('calendar_create')) return { icon: '📅', label: 'Calendar — Create Event', color: '#4285F4' };
  if (t.includes('calendar_read') || t.includes('calendar_get') || t.includes('calendar_list'))
    return { icon: '📅', label: 'Calendar — Read / List Events', color: '#4285F4' };
  if (t.includes('calendar_update')) return { icon: '📅', label: 'Calendar — Update Event', color: '#4285F4' };
  if (t.includes('calendar_delete')) return { icon: '📅', label: 'Calendar — Delete Event', color: '#4285F4' };
  if (t.includes('calendar')) return { icon: '📅', label: 'Calendar Skill', color: '#4285F4' };

  if (t.includes('gmail_send') || t.includes('email_send'))
    return { icon: '✉️', label: 'Gmail — Send Email', color: '#EA4335' };
  if (t.includes('gmail_read') || t.includes('email_read') || t.includes('gmail_search'))
    return { icon: '✉️', label: 'Gmail — Read / Search', color: '#EA4335' };
  if (t.includes('gmail')) return { icon: '✉️', label: 'Gmail Skill', color: '#EA4335' };

  if (t.includes('drive')) return { icon: '💾', label: 'Google Drive Skill', color: '#0F9D58' };
  if (t.includes('contacts')) return { icon: '👥', label: 'Contacts Skill', color: '#F4B400' };
  if (t.includes('meet')) return { icon: '📹', label: 'Google Meet Skill', color: '#00BCD4' };

  // Reminder skill
  if (t.includes('reminder_create') || t.includes('reminder_set'))
    return { icon: '⏰', label: 'Reminder — Set New Reminder', color: '#00D68F' };
  if (t.includes('reminder_list')) return { icon: '⏰', label: 'Reminder — List Reminders', color: '#00D68F' };
  if (t.includes('reminder_cancel')) return { icon: '⏰', label: 'Reminder — Cancel Reminder', color: '#00D68F' };
  if (t.includes('reminder')) return { icon: '⏰', label: 'Reminder Skill', color: '#00D68F' };

  // Fallback for unknown task
  if (t !== 'chat') return { icon: '⚙️', label: actionType, color: 'var(--accent)' };

  // Pure chat
  return { icon: '💬', label: 'Chat Response', color: 'var(--text-muted)' };
}

/**
 * Build the complete stage list based on the completed action type.
 */
function buildResolvedStages(actionType) {
  const isChat = !actionType || actionType.toLowerCase() === 'chat';
  const baseCompleted = BASE_STAGES.map((s) => ({ ...s, status: 'completed' }));

  if (isChat) {
    return [
      ...baseCompleted,
      {
        id: 'skill',
        name: '💬 Chat Response',
        detail: 'Direct reply — no Google Workspace skill needed',
        status: 'completed',
      },
    ];
  }

  const skill = describeSkill(actionType);
  return [
    ...baseCompleted,
    {
      id: 'task',
      name: 'Task Dispatched',
      detail: `Action type: ${actionType}`,
      status: 'completed',
    },
    {
      id: 'skill',
      name: `${skill.icon} ${skill.label}`,
      detail: `Skill executed successfully`,
      status: 'completed',
      _skillColor: skill.color,
    },
  ];
}

/**
 * Build animated (in-flight) stages with a rolling active indicator.
 */
function buildAnimatedStages(stageIndex) {
  const labels = [
    { id: 'received', name: 'Message Received', detail: 'Preparing request…' },
    { id: 'auth', name: 'Auth Token Retrieved', detail: 'Fetching credentials…' },
    { id: 'routing', name: 'Agent Routing', detail: 'Selecting skill…' },
    { id: 'task', name: 'Task Dispatched', detail: 'Running agent pipeline…' },
  ];
  return labels.map((s, i) => ({
    ...s,
    status: i < stageIndex ? 'completed' : i === stageIndex ? 'active' : 'pending',
  }));
}


// ── Countdown Timer ────────────────────────────────────────────────────────

function ReminderCountdown({ triggerAt }) {
  const [timeLeft, setTimeLeft] = useState(null);
  const intervalRef = useRef(null);

  useEffect(() => {
    if (!triggerAt) {
      setTimeLeft(null);
      return;
    }

    const target = new Date(triggerAt).getTime();

    const tick = () => {
      const diff = target - Date.now();
      if (diff <= 0) {
        setTimeLeft(null);
        clearInterval(intervalRef.current);
        return;
      }
      const totalSecs = Math.floor(diff / 1000);
      const h = Math.floor(totalSecs / 3600);
      const m = Math.floor((totalSecs % 3600) / 60);
      const s = totalSecs % 60;
      setTimeLeft({ h, m, s, total: totalSecs });
    };

    tick(); // immediate first render
    intervalRef.current = setInterval(tick, 1000);

    return () => clearInterval(intervalRef.current);
  }, [triggerAt]);

  if (!triggerAt || timeLeft === null) return null;

  const pad = (n) => String(n).padStart(2, '0');
  const urgency = timeLeft.total < 60;

  return (
    <div
      style={{
        margin: '12px 16px 4px',
        padding: '12px 16px',
        borderRadius: 10,
        background: urgency
          ? 'rgba(255, 110, 64, 0.12)'
          : 'rgba(0, 214, 143, 0.1)',
        border: `1px solid ${urgency ? 'rgba(255,110,64,0.4)' : 'rgba(0,214,143,0.3)'}`,
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          color: urgency ? 'var(--warning)' : 'var(--success)',
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <span style={{ animation: 'pulse 1.2s ease-in-out infinite' }}>⏰</span>
        {urgency ? 'Reminder Firing Soon!' : 'Reminder Countdown'}
      </div>

      <div
        style={{
          fontFamily: "'Roboto Mono', 'Fira Code', monospace",
          fontSize: 28,
          fontWeight: 700,
          color: urgency ? 'var(--warning)' : 'var(--text-primary)',
          letterSpacing: '0.08em',
          lineHeight: 1.2,
        }}
      >
        {timeLeft.h > 0 && `${pad(timeLeft.h)}:`}{pad(timeLeft.m)}:{pad(timeLeft.s)}
      </div>

      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
        Fires at{' '}
        {new Date(triggerAt).toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })}
      </div>
    </div>
  );
}


// ── Main Tracker ────────────────────────────────────────────────────────────

export default function AgentProcessTracker({ isLoading, actionType, requestId, reminderTriggerAt }) {
  const [stageIndex, setStageIndex] = useState(0);
  const [resolved, setResolved] = useState(false);

  // Animate stages while loading
  useEffect(() => {
    if (!isLoading) {
      if (actionType) setResolved(true);
      return;
    }

    setResolved(false);
    setStageIndex(0);

    const timers = [
      setTimeout(() => setStageIndex(1), 400),
      setTimeout(() => setStageIndex(2), 900),
      setTimeout(() => setStageIndex(3), 1800),
    ];

    return () => timers.forEach(clearTimeout);
  }, [isLoading, requestId]);

  // Reset when idle
  useEffect(() => {
    if (!isLoading && !actionType) {
      setStageIndex(0);
      setResolved(false);
    }
  }, [isLoading, actionType]);

  const stages = resolved
    ? buildResolvedStages(actionType)
    : isLoading
      ? buildAnimatedStages(stageIndex)
      : BASE_STAGES.map((s) => ({ ...s, status: 'pending' }));

  const hasActivity = isLoading || resolved;
  const isReminder = resolved && actionType?.toLowerCase().includes('reminder');

  return (
    <div className="tracker-panel">
      <div className="tracker-header">
        <div className="tracker-title">Agent Pipeline</div>
        <div className="tracker-subtitle">
          {isLoading
            ? 'Processing request…'
            : resolved
              ? 'Request completed'
              : 'Waiting for activity'}
        </div>
      </div>

      {/* Skill badge — shown after request resolves */}
      {resolved && actionType && (() => {
        const skill = describeSkill(actionType);
        if (!skill) return null;
        return (
          <div
            style={{
              margin: '12px 16px 0',
              padding: '8px 14px',
              borderRadius: 8,
              background: `${skill.color}18`,
              border: `1px solid ${skill.color}40`,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontSize: 13,
              fontWeight: 600,
              color: skill.color,
            }}
          >
            <span style={{ fontSize: 18 }}>{skill.icon}</span>
            <div>
              <div style={{ fontSize: 10, opacity: 0.7, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Skill Used
              </div>
              {skill.label}
            </div>
          </div>
        );
      })()}

      {/* Countdown timer — only shown after reminder is set */}
      {isReminder && reminderTriggerAt && (
        <ReminderCountdown triggerAt={reminderTriggerAt} />
      )}

      <div className="tracker-stages">
        {!hasActivity ? (
          <div className="tracker-empty">
            <div className="tracker-empty-icon">⚡</div>
            <div className="tracker-empty-text">
              Send a message to see the agent pipeline in action
            </div>
          </div>
        ) : (
          stages.map((stage, i) => (
            <StageIndicator
              key={stage.id}
              status={stage.status}
              name={stage.name}
              detail={stage.detail}
              index={i}
            />
          ))
        )}
      </div>
    </div>
  );
}
