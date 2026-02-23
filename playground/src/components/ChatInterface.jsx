import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { executeAction } from '../services/api';
import ChatMessage from './ChatMessage';
import AgentProcessTracker from './AgentProcessTracker';

const SUGGESTIONS = [
    "What's on my calendar today?",
    'Send an email to team about standup',
    'Remind me to review docs at 3pm',
    'Summarize my recent emails',
    "What can you help me with?",
];

export default function ChatInterface() {
    const { user } = useAuth();
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [lastActionType, setLastActionType] = useState(null);
    const [requestId, setRequestId] = useState(0);
    const messagesEndRef = useRef(null);
    const inputRef = useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, isLoading]);

    const sendMessage = async (text) => {
        const msg = text || input.trim();
        if (!msg || isLoading) return;

        setInput('');
        setLastActionType(null);
        setRequestId((prev) => prev + 1);

        // Add user message
        const userMsg = { role: 'user', content: msg, timestamp: new Date().toISOString() };
        setMessages((prev) => [...prev, userMsg]);
        setIsLoading(true);

        try {
            const res = await executeAction(
                user.user_id,
                msg,
                user.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone
            );

            const aiContent =
                res?.data?.response || res?.error || 'No response received.';
            const actionType = res?.data?.action_performed || 'chat';

            setLastActionType(actionType);

            const aiMsg = {
                role: 'assistant',
                content: aiContent,
                timestamp: new Date().toISOString(),
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
                    {messages.length === 0 && !isLoading ? (
                        <div className="chat-empty">
                            <div className="chat-empty-icon">🚀</div>
                            <div className="chat-empty-title">Ready to test!</div>
                            <div className="chat-empty-desc">
                                Send a message to start chatting with Peppi's AI agent. Try one of the suggestions below.
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
                                />
                            ))}
                            {isLoading && (
                                <div className="typing-indicator">
                                    <div className="message-avatar" style={{ background: 'rgba(0,214,143,0.15)', color: 'var(--success)' }}>
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
            />
        </>
    );
}
