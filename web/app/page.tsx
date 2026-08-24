"use client";

import React, { useState, useEffect } from "react";

const PROXY_API = process.env.NEXT_PUBLIC_AGENT_API || "http://localhost:3000";

interface Specimen {
  specimen_token: string;
  current_status: string;
  accessioned_at: string;
  expected_signout_at: string;
  tat_risk_level: "green" | "yellow" | "red";
  last_event_at: string;
}

interface Action {
  id: string;
  agent_name: string;
  specimen_token: string;
  action_type: string;
  payload: any;
  confidence: number;
  reasoning: string;
  status: string;
  proposed_at: string;
}

export default function DashboardPage() {
  const [specimens, setSpecimens] = useState<Specimen[]>([]);
  const [actions, setActions] = useState<Action[]>([]);
  const [trustStage, setTrustStage] = useState<string>("SUGGEST");
  const [userRole, setUserRole] = useState<string>("Operator (Tier 2)");
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<Array<{ sender: "user" | "supervisor"; text: string }>>([
    { sender: "supervisor", text: "Hello, I am ATLAS Supervisor. How can I assist you with lab workflows today?" }
  ]);
  const [isOffline, setIsOffline] = useState(false);

  // Fetch initial data & Poll live specimen changes
  useEffect(() => {
    const fetchStates = async () => {
      try {
        const roleParam = encodeURIComponent(userRole);
        const specRes = await fetch(`${PROXY_API}/api/proxy?path=/specimens&role=${roleParam}`);
        if (specRes.ok) {
          const specData = await specRes.json();
          setSpecimens(specData);
        }

        const actRes = await fetch(`${PROXY_API}/api/proxy?path=/actions&role=${roleParam}`);
        if (actRes.ok) {
          const actData = await actRes.json();
          setActions(actData);
        }

        const stageRes = await fetch(`${PROXY_API}/api/proxy?path=/admin/stage&role=${roleParam}`);
        if (stageRes.ok) {
          const stageData = await stageRes.json();
          setTrustStage(stageData.trust_stage);
        }
        setIsOffline(false);
      } catch (err) {
        console.error("Dashboard failed to connect to agent service, using mock/offline state:", err);
        setIsOffline(true);
      }
    };

    fetchStates();
    const interval = setInterval(fetchStates, 3000);
    return () => clearInterval(interval);
  }, [userRole]);

  const handleApproveAction = async (actionId: string) => {
    try {
      const res = await fetch(`${PROXY_API}/api/proxy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ _path: `/actions/${actionId}/approve`, _role: userRole })
      });
      if (res.ok) {
        setActions(prev => prev.filter(a => a.id !== actionId));
      }
    } catch (err) {
      alert("Error executing action approval on backend.");
    }
  };

  const handleDismissAction = async (actionId: string) => {
    try {
      const res = await fetch(`${PROXY_API}/api/proxy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ _path: `/actions/${actionId}/dismiss`, _role: userRole })
      });
      if (res.ok) {
        setActions(prev => prev.filter(a => a.id !== actionId));
      }
    } catch (err) {
      alert("Error executing action dismissal on backend.");
    }
  };

  const toggleTrustStage = async () => {
    const nextStage = trustStage === "OBSERVE" ? "SUGGEST" : "OBSERVE";
    try {
      const res = await fetch(`${PROXY_API}/api/proxy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ _path: "/admin/stage", _role: userRole, stage: nextStage })
      });
      if (res.ok) {
        setTrustStage(nextStage);
      } else {
        const errData = await res.json();
        alert(`Failed to update trust stage: ${errData.detail || res.statusText}`);
      }
    } catch (err) {
      alert("Failed to update trust stage on agent core.");
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    
    const userMsg = chatInput;
    setChatMessages(prev => [...prev, { sender: "user", text: userMsg }]);
    setChatInput("");
    
    try {
      const res = await fetch(`${PROXY_API}/api/proxy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ _path: "/supervisor/chat", _role: userRole, question: userMsg })
      });
      if (res.ok) {
        const data = await res.json();
        setChatMessages(prev => [...prev, { sender: "supervisor", text: data.response }]);
      } else {
        throw new Error("Chat request failed");
      }
    } catch (err) {
      // Offline fallback
      setTimeout(() => {
        setChatMessages(prev => [...prev, { 
          sender: "supervisor", 
          text: `[Offline Local Fallback] Query "${userMsg}" received. Retrieving offline cache stats...`
        }]);
      }, 800);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      {/* Header */}
      <header className="glass-panel" style={{ margin: "16px", padding: "16px 24px", display: "flex", justifyContent: "space-between", alignItems: "center", borderRadius: "12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div style={{ 
            width: "12px", 
            height: "12px", 
            borderRadius: "50%", 
            background: isOffline ? "hsl(var(--color-danger))" : "hsl(var(--color-primary))", 
            boxShadow: isOffline ? "0 0 10px hsl(var(--color-danger))" : "0 0 10px hsl(var(--color-primary))" 
          }} />
          <h1 style={{ fontSize: "1.5rem", fontWeight: "700" }}>LabMind<span style={{ color: "hsl(var(--color-primary))", fontWeight: "300" }}>ATLAS</span></h1>
          {isOffline && <span style={{ fontSize: "0.8rem", color: "hsl(var(--color-danger))", fontWeight: "600" }}>[OFFLINE MODE]</span>}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "24px" }}>
          <button 
            onClick={toggleTrustStage}
            style={{ 
              background: "rgba(255,255,255,0.05)", 
              border: "1px solid var(--border-color)", 
              color: "hsl(var(--color-warning))", 
              padding: "6px 12px", 
              borderRadius: "6px",
              cursor: "pointer",
              fontSize: "0.85rem",
              fontWeight: "600"
            }}
          >
            Toggle Stage: {trustStage}
          </button>
          <a href="/audit" style={{
              background: "rgba(255,255,255,0.05)", 
              border: "1px solid var(--border-color)", 
              color: "hsl(var(--color-primary))", 
              padding: "6px 12px", 
              borderRadius: "6px",
              cursor: "pointer",
              fontSize: "0.85rem",
              fontWeight: "600",
              textDecoration: "none"
          }}>
            Governance & Audit
          </a>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Active Actor</span>
            <select
              value={userRole}
              onChange={(e) => setUserRole(e.target.value)}
              style={{
                background: "rgba(0,0,0,0.3)",
                border: "1px solid var(--border-color)",
                color: "#fff",
                padding: "4px 8px",
                borderRadius: "4px",
                outline: "none",
                fontSize: "0.9rem",
                fontWeight: "500",
                cursor: "pointer"
              }}
            >
              <option value="Operator (Tier 2)">Operator (Tier 2)</option>
              <option value="Administrator (Tier 3)">Administrator (Tier 3)</option>
            </select>
          </div>
        </div>
      </header>

      {/* Main Grid */}
      <main style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1.2fr", gap: "16px", padding: "0 16px 16px 16px" }}>
        
        {/* Left: Specimen Monitor */}
        <section className="glass-panel" style={{ padding: "20px", display: "flex", flexDirection: "column" }}>
          <h2 style={{ fontSize: "1.2rem", marginBottom: "16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>Live Specimen Tracker</span>
            <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)", background: "rgba(255,255,255,0.05)", padding: "4px 8px", borderRadius: "20px" }}>
              {specimens.length} active
            </span>
          </h2>
          
          <div style={{ flex: 1, overflowY: "auto" }}>
            {specimens.length === 0 ? (
              <div style={{ height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", color: "var(--text-secondary)", gap: "8px" }}>
                <p>Waiting for LIS Event Stream...</p>
                <span style={{ fontSize: "0.8rem", opacity: 0.6 }}>Start Docker services to feed mock pipeline data</span>
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-color)", color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                    <th style={{ padding: "8px" }}>Token</th>
                    <th style={{ padding: "8px" }}>Status</th>
                    <th style={{ padding: "8px" }}>Risk</th>
                    <th style={{ padding: "8px" }}>Last Event</th>
                  </tr>
                </thead>
                <tbody>
                  {specimens.map(specimen => (
                    <tr key={specimen.specimen_token} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)", fontSize: "0.9rem" }}>
                      <td style={{ padding: "12px 8px", fontFamily: "monospace" }}>{specimen.specimen_token.substring(0, 12)}...</td>
                      <td style={{ padding: "12px 8px" }}>
                        <span style={{ background: "rgba(255,255,255,0.05)", padding: "2px 6px", borderRadius: "4px" }}>
                          {specimen.current_status}
                        </span>
                      </td>
                      <td style={{ padding: "12px 8px" }}>
                        <span style={{ 
                          color: specimen.tat_risk_level === "red" ? "hsl(var(--color-danger))" : specimen.tat_risk_level === "yellow" ? "hsl(var(--color-warning))" : "hsl(var(--color-success))"
                        }}>
                          ● {specimen.tat_risk_level.toUpperCase()}
                        </span>
                      </td>
                      <td style={{ padding: "12px 8px", color: "var(--text-secondary)" }}>
                        {new Date(specimen.last_event_at).toLocaleTimeString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        {/* Right: Actions, Approvals & Chat Split */}
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          
          {/* Action / Approval Queue */}
          <section className="glass-panel" style={{ flex: 1, padding: "20px", display: "flex", flexDirection: "column" }}>
            <h2 style={{ fontSize: "1.2rem", marginBottom: "12px" }}>Action Approval Queue</h2>
            <div style={{ flex: 1, overflowY: "auto" }}>
              {actions.length === 0 ? (
                <div style={{ height: "100%", display: "flex", justifyContent: "center", alignItems: "center", color: "var(--text-secondary)", fontSize: "0.9rem" }}>
                  No pending actions requiring Operator approval
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  {actions.map(action => (
                    <div key={action.id} style={{ border: "1px solid var(--border-color)", padding: "12px", borderRadius: "8px", background: "rgba(0,0,0,0.2)" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                        <strong style={{ color: "hsl(var(--color-warning))" }}>{action.action_type}</strong>
                        <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>Conf: {action.confidence}</span>
                      </div>
                      <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "8px" }}>{action.reasoning}</p>
                      <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
                        <button 
                          onClick={() => handleDismissAction(action.id)}
                          style={{ background: "rgba(255,255,255,0.05)", border: "none", color: "var(--text-primary)", padding: "4px 8px", borderRadius: "4px", cursor: "pointer" }}
                        >
                          Dismiss
                        </button>
                        <button 
                          onClick={() => handleApproveAction(action.id)}
                          style={{ background: "hsl(var(--color-primary))", border: "none", color: "#000", fontWeight: "600", padding: "4px 12px", borderRadius: "4px", cursor: "pointer" }}
                        >
                          Approve Action
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          {/* Supervisor Chat Panel */}
          <section className="glass-panel" style={{ flex: 1, padding: "20px", display: "flex", flexDirection: "column", minHeight: "300px" }}>
            <h2 style={{ fontSize: "1.2rem", marginBottom: "12px" }}>ATLAS Supervisor Agent</h2>
            
            <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "8px", marginBottom: "12px" }}>
              {chatMessages.map((msg, i) => (
                <div key={i} style={{ 
                  alignSelf: msg.sender === "user" ? "flex-end" : "flex-start",
                  background: msg.sender === "user" ? "rgba(99, 102, 241, 0.15)" : "rgba(255,255,255,0.03)",
                  border: msg.sender === "user" ? "1px solid rgba(99, 102, 241, 0.3)" : "1px solid rgba(255,255,255,0.05)",
                  padding: "8px 12px",
                  borderRadius: "12px",
                  maxWidth: "80%",
                  fontSize: "0.9rem"
                }}>
                  {msg.text}
                </div>
              ))}
            </div>

            <form onSubmit={handleSendMessage} style={{ display: "flex", gap: "8px" }}>
              <input 
                type="text" 
                value={chatInput} 
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Ask Supervisor: 'What is at risk right now?'"
                style={{ 
                  flex: 1, 
                  background: "rgba(0,0,0,0.3)", 
                  border: "1px solid var(--border-color)", 
                  color: "#fff", 
                  padding: "8px 12px", 
                  borderRadius: "6px",
                  outline: "none"
                }}
              />
              <button 
                type="submit" 
                style={{ 
                  background: "hsl(var(--color-primary))", 
                  color: "#000", 
                  border: "none", 
                  fontWeight: "600", 
                  padding: "8px 16px", 
                  borderRadius: "6px",
                  cursor: "pointer"
                }}
              >
                Send
              </button>
            </form>
          </section>

        </div>

      </main>
    </div>
  );
}
