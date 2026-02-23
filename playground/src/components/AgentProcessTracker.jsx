import React from 'react';
import StageIndicator from './StageIndicator';

/**
 * Default stage definitions for the agent pipeline.
 * Each stage becomes active/completed/skipped based on the current request lifecycle.
 */
const DEFAULT_STAGES = [
  { id: 'received', name: 'Message Received', detail: 'Preparing request…' },
  { id: 'auth', name: 'Auth Token Retrieved', detail: 'Fetching credentials from DB' },
  { id: 'routing', name: 'Agent Routing', detail: 'Deciding: Chat or Task?' },
  { id: 'task', name: 'Task Execution', detail: 'Running agent pipeline' },
  { id: 'workspace', name: 'Google Workspace', detail: 'Accessing workspace tools' },
  { id: 'calendar', name: 'Calendar Skills', detail: 'Managing calendar events' },
  { id: 'gmail', name: 'Gmail Skills', detail: 'Reading or sending emails' },
  { id: 'reminder', name: 'Reminder Skills', detail: 'Setting up reminders' },
];

/**
 * Determine which stages are relevant based on the action_type from the response.
 */
function resolveStages(stages, actionType) {
  if (!actionType) return stages.map((s) => ({ ...s, status: 'pending' }));

  const type = (actionType || '').toLowerCase();
  const isChat = type === 'chat';
  const isCalendar = type.includes('calendar');
  const isGmail = type.includes('gmail') || type.includes('email');
  const isReminder = type.includes('reminder');
  const isTask = !isChat;

  return stages.map((s) => {
    switch (s.id) {
      case 'received':
      case 'auth':
      case 'routing':
        return { ...s, status: 'completed' };
      case 'task':
        return { ...s, status: isTask ? 'completed' : 'skipped', detail: isTask ? `Action: ${actionType}` : 'Skipped — chat response' };
      case 'workspace':
        return { ...s, status: (isCalendar || isGmail) ? 'completed' : 'skipped' };
      case 'calendar':
        return { ...s, status: isCalendar ? 'completed' : 'skipped' };
      case 'gmail':
        return { ...s, status: isGmail ? 'completed' : 'skipped' };
      case 'reminder':
        return { ...s, status: isReminder ? 'completed' : 'skipped' };
      default:
        return { ...s, status: 'pending' };
    }
  });
}

/**
 * Build animated sequence for when request is in-flight.
 * stageIndex controls how far the pipeline has progressed.
 */
function animateStages(stages, stageIndex) {
  return stages.map((s, i) => {
    if (i < stageIndex) return { ...s, status: 'completed' };
    if (i === stageIndex) return { ...s, status: 'active' };
    return { ...s, status: 'pending' };
  });
}

export default function AgentProcessTracker({ isLoading, actionType, requestId }) {
  const [stageIndex, setStageIndex] = React.useState(0);
  const [resolved, setResolved] = React.useState(false);

  // Animate stages while loading
  React.useEffect(() => {
    if (!isLoading) {
      if (actionType) {
        setResolved(true);
      }
      return;
    }

    setResolved(false);
    setStageIndex(0);

    // Progressive stage activation
    const timers = [
      setTimeout(() => setStageIndex(1), 400),
      setTimeout(() => setStageIndex(2), 900),
      setTimeout(() => setStageIndex(3), 1800),
    ];

    return () => timers.forEach(clearTimeout);
  }, [isLoading, requestId]);

  // Reset when no action
  React.useEffect(() => {
    if (!isLoading && !actionType) {
      setStageIndex(0);
      setResolved(false);
    }
  }, [isLoading, actionType]);

  const stages = resolved
    ? resolveStages(DEFAULT_STAGES, actionType)
    : isLoading
    ? animateStages(DEFAULT_STAGES, stageIndex)
    : DEFAULT_STAGES.map((s) => ({ ...s, status: 'pending' }));

  const hasActivity = isLoading || resolved;

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
