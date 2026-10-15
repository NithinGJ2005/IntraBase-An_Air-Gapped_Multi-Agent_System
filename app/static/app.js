// Enterprise Intranet Assistant React Application (Phase 7 Frontend)
const { useState, useEffect, useRef, createElement: h } = React;

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [errorBanner, setErrorBanner] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem("assistant_token") || "");
  const [tokenModalOpen, setTokenModalOpen] = useState(false);
  const [diagModalOpen, setDiagModalOpen] = useState(false);
  const [diagnostics, setDiagnostics] = useState(null);
  const [session, setSession] = useState(null);

  const abortControllerRef = useRef(null);
  const messagesEndRef = useRef(null);

  // Auto-scroll to bottom of messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Load session identity on token change
  useEffect(() => {
    if (!token) return;
    fetch("/api/v1/session", {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.ok ? res.json() : null)
      .then(data => setSession(data))
      .catch(() => setSession(null));
  }, [token]);

  const handleSend = async (messageText) => {
    const textToSend = (messageText || input).trim();
    if (!textToSend || isLoading) return;

    setErrorBanner(null);
    setInput("");

    const userMsg = {
      id: "msg-" + Date.now(),
      role: "user",
      content: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const headers = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const response = await fetch("/api/v1/chat", {
        method: "POST",
        headers,
        body: JSON.stringify({ message: textToSend }),
        signal: controller.signal
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (response.status === 401) {
          setErrorBanner({
            type: "error",
            message: "Authentication required. Please configure a valid Bearer token in settings.",
            actionLabel: "Configure Token",
            action: () => setTokenModalOpen(true)
          });
        } else if (response.status === 403) {
          setErrorBanner({
            type: "error",
            message: data.message || "You do not have 'chat:use' permission for this service."
          });
        } else if (response.status === 429) {
          setErrorBanner({
            type: "warning",
            message: "The assistant inference service is currently at capacity. Please try again shortly."
          });
        } else if (response.status === 503) {
          setErrorBanner({
            type: "warning",
            message: "The assistant inference service is temporarily unavailable."
          });
        } else {
          setErrorBanner({
            type: "error",
            message: data.message || "An unexpected error occurred while processing your request."
          });
        }
        setIsLoading(false);
        return;
      }

      const assistantMsg = {
        id: "msg-" + Date.now() + "-ai",
        role: "assistant",
        content: data.response,
        citations: data.citations || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };

      setMessages(prev => [...prev, assistantMsg]);
    } catch (err) {
      if (err.name !== "AbortError") {
        setErrorBanner({
          type: "error",
          message: "Network error: Unable to reach the assistant service."
        });
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
      setErrorBanner({
        type: "warning",
        message: "Query cancelled by user."
      });
    }
  };

  const handleReset = () => {
    setMessages([]);
    setErrorBanner(null);
  };

  const openDiagnostics = async () => {
    setDiagModalOpen(true);
    try {
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const [liveRes, readyRes, sessionRes, toolsRes, auditRes] = await Promise.all([
        fetch("/health/live").then(r => r.json()).catch(e => ({ error: e.message })),
        fetch("/health/ready").then(r => r.json()).catch(e => ({ error: e.message })),
        fetch("/api/v1/session", { headers }).then(r => r.json()).catch(e => ({ error: e.message })),
        fetch("/api/v1/mcp/tools", { headers }).then(r => r.json()).catch(e => ({ error: e.message })),
        fetch("/api/v1/admin/audit-status", { headers }).then(r => r.json()).catch(e => ({ error: e.message }))
      ]);

      setDiagnostics({
        liveness: liveRes,
        readiness: readyRes,
        session: sessionRes,
        tools: toolsRes,
        audit: auditRes
      });
    } catch (err) {
      setDiagnostics({ error: err.message });
    }
  };

  return h("div", { className: "app-container" },
    // Header
    h("header", { className: "app-header" },
      h("div", { className: "brand-wrapper" },
        h("div", { className: "brand-icon", "aria-hidden": "true" },
          h("svg", { viewBox: "0 0 24 24" },
            h("path", { d: "M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" })
          )
        ),
        h("div", null,
          h("h1", { className: "brand-title" }, "Enterprise Intranet Assistant"),
          h("span", { className: "brand-status-pill" },
            h("span", { className: "status-dot" }),
            session ? `Signed in as ${session.subject}` : "Internal Secure"
          )
        )
      ),
      h("div", { className: "header-actions" },
        messages.length > 0 && h("button", {
          className: "btn-secondary",
          onClick: handleReset,
          title: "Clear conversation history",
          "aria-label": "Reset chat conversation"
        }, "Reset"),
        h("button", {
          className: "btn-secondary",
          onClick: () => setTokenModalOpen(true),
          "aria-label": "Configure authentication token"
        }, token ? "Auth Configured" : "Set Auth"),
        h("button", {
          className: "btn-secondary",
          onClick: openDiagnostics,
          "aria-label": "View system diagnostics"
        }, "Diagnostics")
      )
    ),

    // Main Chat Area
    h("main", { className: "chat-main", role: "log", "aria-live": "polite" },
      messages.length === 0 ? h("div", { className: "welcome-container" },
        h("span", { className: "welcome-badge" }, "Local & Confidential"),
        h("h2", { className: "welcome-title" }, "How can I help you today?"),
        h("p", { className: "welcome-desc" },
          "Ask questions about company policies, benefit documents, internal staff directories, or team resources."
        ),
        h("div", { className: "prompt-suggestions" },
          h("button", {
            className: "suggestion-pill",
            onClick: () => handleSend("What are the employee paid time off policies?")
          }, "What are our PTO policies?"),
          h("button", {
            className: "suggestion-pill",
            onClick: () => handleSend("What is the password rotation guideline?")
          }, "Password security rules"),
          h("button", {
            className: "suggestion-pill",
            onClick: () => handleSend("Who is on the Engineering team directory?")
          }, "Look up Engineering directory")
        )
      ) : h("div", { className: "messages-scrollable" },
        messages.map(msg =>
          h("div", { key: msg.id, className: `message-row ${msg.role}` },
            h("div", { className: "message-avatar", "aria-hidden": "true" },
              msg.role === "user" ? "You" : "AI"
            ),
            h("div", { className: "message-bubble" },
              h("p", null, msg.content),
              msg.citations && msg.citations.length > 0 && h("div", { className: "citations-panel" },
                h("span", { className: "citations-label" }, "Sources:"),
                msg.citations.map((c, idx) =>
                  h("span", { key: idx, className: "citation-chip", title: `Doc ID: ${c.document_id}` },
                    c.filename,
                    c.page ? ` (p. ${c.page})` : ""
                  )
                )
              )
            )
          )
        ),
        isLoading && h("div", { className: "message-row assistant" },
          h("div", { className: "message-avatar", "aria-hidden": "true" }, "AI"),
          h("div", { className: "message-bubble" },
            h("div", { className: "spinner", "aria-label": "Processing query" })
          )
        ),
        h("div", { ref: messagesEndRef })
      ),

      // Error Banner
      errorBanner && h("div", { className: `error-banner ${errorBanner.type || 'error'}`, role: "alert" },
        h("span", null, errorBanner.message),
        errorBanner.actionLabel && h("button", {
          className: "btn-secondary",
          onClick: errorBanner.action
        }, errorBanner.actionLabel)
      ),

      // Input Controls Area
      h("div", { className: "chat-input-area" },
        h("div", { className: "input-container" },
          h("textarea", {
            className: "chat-textarea",
            placeholder: "Type your query... (Enter to send, Shift+Enter for new line)",
            value: input,
            onChange: e => setInput(e.target.value),
            onKeyDown: e => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            },
            rows: 1,
            disabled: isLoading,
            "aria-label": "Chat message input"
          }),
          h("div", { className: "input-actions" },
            isLoading ? h("button", {
              className: "btn-cancel",
              onClick: handleCancel,
              "aria-label": "Cancel current query"
            }, "Cancel") : h("button", {
              className: "btn-send",
              onClick: () => handleSend(),
              disabled: !input.trim(),
              "aria-label": "Send message"
            },
              h("svg", { viewBox: "0 0 24 24", width: 16, height: 16, fill: "none", stroke: "currentColor", strokeWidth: 2 },
                h("path", { d: "M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" })
              )
            )
          )
        )
      )
    ),

    // Token Modal
    tokenModalOpen && h("div", { className: "modal-backdrop", onClick: () => setTokenModalOpen(false) },
      h("div", { className: "modal-content", onClick: e => e.stopPropagation() },
        h("div", { className: "modal-header" },
          h("h3", { className: "modal-title" }, "Authentication Settings"),
          h("button", { className: "modal-close", onClick: () => setTokenModalOpen(false) }, "✕")
        ),
        h("div", { className: "modal-body" },
          h("p", { style: { color: "var(--text-secondary)", fontSize: "0.9rem" } },
            "Enter an employee or test Bearer token. Production requires an SSO/OIDC token with 'chat:use' permission."
          ),
          h("input", {
            type: "password",
            placeholder: "eyJhbGciOiJIUzI1NiIsIn...",
            value: token,
            onChange: e => setToken(e.target.value),
            style: {
              width: "100%",
              padding: "10px 12px",
              background: "var(--bg-input)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-sm)",
              color: "var(--text-primary)",
              fontFamily: "monospace"
            }
          }),
          h("div", { style: { display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "10px" } },
            h("button", {
              className: "btn-secondary",
              onClick: () => {
                setToken("");
                localStorage.removeItem("assistant_token");
                setTokenModalOpen(false);
              }
            }, "Clear"),
            h("button", {
              className: "btn-secondary",
              style: { background: "var(--accent-blue)", color: "#fff", borderColor: "var(--accent-blue)" },
              onClick: () => {
                localStorage.setItem("assistant_token", token);
                setTokenModalOpen(false);
              }
            }, "Save Token")
          )
        )
      )
    ),

    // Diagnostics Modal
    diagModalOpen && h("div", { className: "modal-backdrop", onClick: () => setDiagModalOpen(false) },
      h("div", { className: "modal-content", onClick: e => e.stopPropagation() },
        h("div", { className: "modal-header" },
          h("h3", { className: "modal-title" }, "Restricted System Diagnostics"),
          h("button", { className: "modal-close", onClick: () => setDiagModalOpen(false) }, "✕")
        ),
        h("div", { className: "modal-body" },
          !diagnostics ? h("div", { className: "spinner", style: { margin: "20px auto" } }) : h("div", null,
            h("div", { className: "diag-item" },
              h("span", { className: "diag-label" }, "Liveness Check (/health/live)"),
              h("span", { className: "diag-val" }, JSON.stringify(diagnostics.liveness?.status || "unavailable"))
            ),
            h("div", { className: "diag-item", style: { marginTop: "8px" } },
              h("span", { className: "diag-label" }, "Readiness Check (/health/ready)"),
              h("span", { className: "diag-val" }, JSON.stringify(diagnostics.readiness?.status || "unavailable"))
            ),
            h("div", { className: "diag-item", style: { marginTop: "8px" } },
              h("span", { className: "diag-label" }, "Active Session Subject"),
              h("span", { className: "diag-val" }, diagnostics.session?.subject || "Unauthenticated")
            ),
            h("div", { className: "diag-item", style: { marginTop: "8px" } },
              h("span", { className: "diag-label" }, "Assigned Permissions"),
              h("span", { className: "diag-val" }, (diagnostics.session?.permissions || []).join(", ") || "None")
            ),
            h("div", { className: "diag-item", style: { marginTop: "8px" } },
              h("span", { className: "diag-label" }, "Audit System (/api/v1/admin/audit-status)"),
              h("span", { className: "diag-val" }, diagnostics.audit?.status ? `Available (${diagnostics.audit.status})` : (diagnostics.audit?.error || "Access Denied"))
            ),
            h("div", { className: "diag-item", style: { marginTop: "8px" } },
              h("span", { className: "diag-label" }, "Registered MCP Tools"),
              h("span", { className: "diag-val" }, (diagnostics.tools?.tools || []).map(t => t.name).join(", ") || "None / Denied")
            )
          )
        )
      )
    )
  );
}

// Mount the React application
const rootElement = document.getElementById("root");
if (rootElement && window.ReactDOM) {
  const root = ReactDOM.createRoot(rootElement);
  root.render(h(App));
}
