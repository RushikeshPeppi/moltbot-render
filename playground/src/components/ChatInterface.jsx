import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { executeAction, getChatHistory, getPlaygroundMessages } from '../services/api';
import ChatMessage from './ChatMessage';
import AgentProcessTracker from './AgentProcessTracker';

// Static context prompt for playground testing — mirrors what Peppi backend sends
const PEPPI_CONTEXT = `<rules>
IDENTITY
- You are Peppi. Never say you are an AI, a bot, or a language model. Ever.
- You talk like a real friend — casual, warm, sometimes cheeky.
- You speak in short SMS-style messages. No essays.

TONE
- Match the user's energy. If they're hyped, be hyped. If chill, be chill.
- Use slang, abbreviations ("u", "rn", "ngl"), and emojis naturally.
- Never sound robotic or corporate.

RULES
- Always answer "8" when asked how many messages are left.
- Never break character.
- Keep responses under 3 sentences unless the user asks for detail.
</rules>`;

const SUGGESTIONS = [
    "What's on my calendar today?",
    'Send an email to team about standup',
    'Remind me to review docs at 3pm',
    'Summarize my recent emails',
    "What can you help me with?",
];

/** Poll interval for reminder deliveries from QStash (ms) */
const POLL_INTERVAL_MS = 5000;

export default function ChatInterface() {
    const { user } = useAuth();
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    // Start as true only if a user is already persisted (history will load immediately).
    // If no user is logged in, we don't want to show an infinite history spinner.
    const [historyLoading, setHistoryLoading] = useState(() => !!user?.user_id);
    const [lastActionType, setLastActionType] = useState(null);
    const [requestId, setRequestId] = useState(0);
    /** ISO timestamp of the next pending reminder — drives the countdown timer */
    const [reminderTriggerAt, setReminderTriggerAt] = useState(null);
    const messagesEndRef = useRef(null);
    const inputRef = useRef(null);
    const pollRef = useRef(null);

    // ── Scroll to bottom on new messages ─────────────────────────────────────
    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, isLoading]);

    // ── Load persistent chat history on login ────────────────────────────────
    useEffect(() => {
        if (!user?.user_id) return;

        const loadHistory = async () => {
            setHistoryLoading(true);
            try {
                const res = await getChatHistory(user.user_id, 200);
                const actions = res?.data?.actions || [];

                // Audit log is newest-first; reverse so oldest messages appear first in chat.
                const sorted = [...actions].reverse();

                const historyMessages = [];
                for (const log of sorted) {
                    // User turn (skip if empty - e.g., system-initiated reminders)
                    if (log.request_summary) {
                        historyMessages.push({
                            role: 'user',
                            content: log.request_summary,
                            timestamp: log.created_at,
                            fromHistory: true,
                        });
                    }
                    // Assistant turn
                    if (log.response_summary) {
                        historyMessages.push({
                            role: 'assistant',
                            content: log.response_summary,
                            timestamp: log.created_at,
                            fromHistory: true,
                            actionType: log.action_type,
                            // Apply special reminder styling if this is a reminder delivery
                            isReminderDelivery: log.action_type === 'reminder_delivery',
                        });
                    }
                }

                setMessages(historyMessages);
            } catch (err) {
                console.warn('Failed to load chat history:', err);
            } finally {
                setHistoryLoading(false);
            }
        };

        loadHistory();
    }, [user?.user_id]);

    // ── Poll for QStash reminder deliveries ──────────────────────────────────
    const appendReminderMessage = useCallback((text, timestamp) => {
        setMessages((prev) => [
            ...prev,
            {
                role: 'assistant',
                content: `⏰ **Reminder fired!** ${text}`,
                timestamp: timestamp || new Date().toISOString(),
                isReminderDelivery: true,
            },
        ]);
        // Clear the countdown — reminder has fired
        setReminderTriggerAt(null);
    }, []);

    useEffect(() => {
        if (!user?.user_id) return;

        const poll = async () => {
            try {
                const res = await getPlaygroundMessages(user.user_id);
                const msgs = res?.data?.messages || [];
                for (const m of msgs) {
                    if (m.type === 'reminder_delivery') {
                        appendReminderMessage(m.message, m.timestamp);
                    }
                }
            } catch {
                // silent — backend may be starting up
            }
        };

        // Start polling
        pollRef.current = setInterval(poll, POLL_INTERVAL_MS);
        return () => clearInterval(pollRef.current);
    }, [user?.user_id, appendReminderMessage]);

    // ── Send message ─────────────────────────────────────────────────────────
    const sendMessage = async (text) => {
        const msg = text || input.trim();
        if (!msg || isLoading) return;

        setInput('');
        setLastActionType(null);
        setRequestId((prev) => prev + 1);

        const userMsg = { role: 'user', content: msg, timestamp: new Date().toISOString() };
        setMessages((prev) => [...prev, userMsg]);
        setIsLoading(true);

        try {
            const res = await executeAction(
                user.user_id,
                msg,
                user.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
                PEPPI_CONTEXT
            );

            const aiContent =
                res?.data?.response || res?.error || 'No response received.';
            const actionType = res?.data?.action_performed || 'chat';
            const triggerAt = res?.data?.reminder_trigger_at || null;

            setLastActionType(actionType);

            // If a reminder was set, store the trigger time for the countdown
            if (triggerAt) {
                setReminderTriggerAt(triggerAt);
            }

            const aiMsg = {
                role: 'assistant',
                content: aiContent,
                timestamp: new Date().toISOString(),
                actionType,
            };
            setMessages((prev) => [...prev, aiMsg]);
        } catch (err) {
            const errorMsg = {
                role: 'assistant',
                content: `⚠️ Error: ${err.message || 'Failed to reach the API. Is the backend running?'}`,
                timestamp: new Date().toISOString(),
            };
            setMessages((prev) => [...prev, errorMsg]);
            setLastActionType(null);
        } finally {
            setIsLoading(false);
            inputRef.current?.focus();
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    const handleSuggestion = (text) => {
        sendMessage(text);
    };

    // ── Determine empty state ────────────────────────────────────────────────
    const isEmpty = !historyLoading && messages.length === 0 && !isLoading;

    return (
        <>
            <div className="chat-container">
                <div className="chat-header">
                    <div className="chat-header-title">Chat with Peppi</div>
                    <div className="chat-header-status">
                        <div className="status-dot" />
                        <span>Online</span>
                    </div>
                </div>

                <div className="chat-messages">
                    {historyLoading ? (
                        <div className="chat-empty">
                            <div className="oauth-spinner" style={{ width: 28, height: 28 }} />
                            <div className="chat-empty-desc" style={{ marginTop: 12 }}>
                                Loading conversation history…
                            </div>
                        </div>
                    ) : isEmpty ? (
                        <div className="chat-empty">
                            <div className="chat-empty-icon">🚀</div>
                            <div className="chat-empty-title">Ready to test!</div>
                            <div className="chat-empty-desc">
                                Send a message to start chatting with Peppi's AI agent. Try one
                                of the suggestions below.
                            </div>
                            <div className="chat-suggestions">
                                {SUGGESTIONS.map((s, i) => (
                                    <button
                                        key={i}
                                        className="chat-suggestion"
                                        onClick={() => handleSuggestion(s)}
                                    >
                                        {s}
                                    </button>
                                ))}
                            </div>
                        </div>
                    ) : (
                        <>
                            {messages.map((msg, i) => (
                                <ChatMessage
                                    key={i}
                                    role={msg.role}
                                    content={msg.content}
                                    timestamp={msg.timestamp}
                                    fromHistory={msg.fromHistory}
                                    isReminderDelivery={msg.isReminderDelivery}
                                />
                            ))}
                            {isLoading && (
                                <div className="typing-indicator">
                                    <div
                                        className="message-avatar"
                                        style={{
                                            background: 'rgba(0,214,143,0.15)',
                                            color: 'var(--success)',
                                        }}
                                    >
                                        🤖
                                    </div>
                                    <div className="typing-dots">
                                        <div className="typing-dot" />
                                        <div className="typing-dot" />
                                        <div className="typing-dot" />
                                    </div>
                                </div>
                            )}
                            <div ref={messagesEndRef} />
                        </>
                    )}
                </div>

                <div className="chat-input-wrapper">
                    <div className="chat-input-container">
                        <textarea
                            ref={inputRef}
                            className="chat-input"
                            placeholder="Type a message…"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            rows={1}
                            disabled={isLoading}
                        />
                        <button
                            className="send-btn"
                            onClick={() => sendMessage()}
                            disabled={!input.trim() || isLoading}
                            title="Send message"
                        >
                            ↑
                        </button>
                    </div>
                </div>
            </div>

            <AgentProcessTracker
                isLoading={isLoading}
                actionType={lastActionType}
                requestId={requestId}
                reminderTriggerAt={reminderTriggerAt}
            />
        </>
    );
}
