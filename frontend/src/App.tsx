import React, { useState, useEffect, useRef } from 'react';
import { ChatMessage, SourceCitation, SessionResponse } from './types';

export const App: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [token, setToken] = useState<string>(() => localStorage.getItem('assistant_token') || '');
  const [errorBanner, setErrorBanner] = useState<{ message: string; type?: 'error' | 'warning' } | null>(null);
  const [session, setSession] = useState<SessionResponse | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  useEffect(() => {
    if (!token) return;
    fetch('/api/v1/session', {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.ok ? res.json() : null)
      .then(data => setSession(data))
      .catch(() => setSession(null));
  }, [token]);

  const handleSend = async (customText?: string) => {
    const textToSend = (customText || input).trim();
    if (!textToSend || isLoading) return;

    setErrorBanner(null);
    setInput('');

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const response = await fetch('/api/v1/chat', {
        method: 'POST',
        headers,
        body: JSON.stringify({ message: textToSend }),
        signal: controller.signal
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (response.status === 401) {
          setErrorBanner({ type: 'error', message: 'Authentication required. Please configure a valid Bearer token.' });
        } else if (response.status === 403) {
          setErrorBanner({ type: 'error', message: data.message || "Permission 'chat:use' is required." });
        } else if (response.status === 429) {
          setErrorBanner({ type: 'warning', message: 'Inference service is currently at capacity. Please retry shortly.' });
        } else if (response.status === 503) {
          setErrorBanner({ type: 'warning', message: 'Inference service is temporarily unavailable.' });
        } else {
          setErrorBanner({ type: 'error', message: data.message || 'An unexpected error occurred.' });
        }
        setIsLoading(false);
        return;
      }

      const assistantMessage: ChatMessage = {
        id: `msg-${Date.now()}-ai`,
        role: 'assistant',
        content: data.response,
        citations: data.citations || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (err: unknown) {
      if ((err as Error)?.name !== 'AbortError') {
        setErrorBanner({ type: 'error', message: 'Network error: Unable to reach the assistant service.' });
      }
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  };

  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsLoading(false);
      setErrorBanner({ type: 'warning', message: 'Query cancelled by user.' });
    }
  };

  const handleReset = () => {
    setMessages([]);
    setErrorBanner(null);
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="brand-wrapper">
          <div className="brand-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" /></svg>
          </div>
          <div>
            <h1 className="brand-title">Enterprise Intranet Assistant</h1>
            <span className="brand-status-pill">
              <span className="status-dot" />
              {session ? `Signed in as ${session.subject}` : 'Internal Secure'}
            </span>
          </div>
        </div>
        <div className="header-actions">
          {messages.length > 0 && (
            <button className="btn-secondary" onClick={handleReset} aria-label="Reset chat">Reset</button>
          )}
        </div>
      </header>

      <main className="chat-main" role="log" aria-live="polite">
        {messages.length === 0 ? (
          <div className="welcome-container">
            <span className="welcome-badge">Local & Confidential</span>
            <h2 className="welcome-title">How can I help you today?</h2>
            <p className="welcome-desc">Ask questions about policies, benefits, and company resources.</p>
            <div className="prompt-suggestions">
              <button className="suggestion-pill" onClick={() => handleSend('What are our PTO policies?')}>PTO policies</button>
              <button className="suggestion-pill" onClick={() => handleSend('What is the password rotation guideline?')}>Password rules</button>
            </div>
          </div>
        ) : (
          <div className="messages-scrollable">
            {messages.map(msg => (
              <div key={msg.id} className={`message-row ${msg.role}`}>
                <div className="message-avatar" aria-hidden="true">{msg.role === 'user' ? 'You' : 'AI'}</div>
                <div className="message-bubble">
                  <p>{msg.content}</p>
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="citations-panel">
                      <span className="citations-label">Sources:</span>
                      {msg.citations.map((c, i) => (
                        <span key={i} className="citation-chip">
                          {c.filename}{c.page ? ` (p. ${c.page})` : ''}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="message-row assistant">
                <div className="message-avatar" aria-hidden="true">AI</div>
                <div className="message-bubble"><div className="spinner" /></div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}

        {errorBanner && (
          <div className={`error-banner ${errorBanner.type || 'error'}`} role="alert">
            <span>{errorBanner.message}</span>
          </div>
        )}

        <div className="chat-input-area">
          <div className="input-container">
            <textarea
              className="chat-textarea"
              placeholder="Type your message..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              disabled={isLoading}
              rows={1}
            />
            <div className="input-actions">
              {isLoading ? (
                <button className="btn-cancel" onClick={handleCancel}>Cancel</button>
              ) : (
                <button className="btn-send" onClick={() => handleSend()} disabled={!input.trim()}>
                  <svg viewBox="0 0 24 24" width={16} height={16} fill="none" stroke="currentColor" strokeWidth={2}>
                    <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
                  </svg>
                </button>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
export default App;
