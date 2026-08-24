"use client";

import React, { useState, useEffect } from "react";

const PROXY_API = process.env.NEXT_PUBLIC_AGENT_API || "http://localhost:3000";

interface AuditEvent {
  id: number;
  prev_hash: string;
  row_hash: string;
  actor: string;
  actor_tier: string;
  event_type: string;
  detail: any;
  created_at: string;
  is_valid: boolean;
}

export default function AuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [verifiedChain, setVerifiedChain] = useState<boolean>(true);
  const [userRole, setUserRole] = useState<string>("Operator (Tier 2)");
  
  // Erasure form state
  const [targetTable, setTargetTable] = useState("episodic_memory");
  const [targetToken, setTargetToken] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  useEffect(() => {
    fetchAuditTrail();
  }, [userRole]);

  const fetchAuditTrail = async () => {
    try {
      const roleParam = encodeURIComponent(userRole);
      const res = await fetch(`${PROXY_API}/api/proxy?path=/audit&role=${roleParam}`);
      if (res.ok) {
        const data = await res.json();
        setEvents(data.events);
        setVerifiedChain(data.verified_chain);
      } else {
        setEvents([]);
      }
    } catch (err) {
      console.error("Failed to fetch audit log", err);
    }
  };

  const handleErasureRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${PROXY_API}/api/proxy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          _path: "/admin/erasure/request",
          _role: userRole,
          target_table: targetTable,
          target_specimen_token: targetToken || null,
          start_date: startDate || null,
          end_date: endDate || null
        })
      });
      
      const data = await res.json();
      if (res.ok) {
        alert(data.message);
        fetchAuditTrail(); // Refresh logs to show erasure events
      } else {
        alert(`Erasure failed: ${data.detail}`);
        fetchAuditTrail(); // Refresh logs to show the rejection
      }
    } catch (err) {
      alert("Error submitting erasure request");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      {/* Header */}
      <header className="glass-panel" style={{ margin: "16px", padding: "16px 24px", display: "flex", justifyContent: "space-between", alignItems: "center", borderRadius: "12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div style={{ width: "12px", height: "12px", borderRadius: "50%", background: verifiedChain ? "hsl(var(--color-primary))" : "hsl(var(--color-danger))" }} />
          <h1 style={{ fontSize: "1.5rem", fontWeight: "700" }}>LabMind<span style={{ color: "hsl(var(--color-primary))", fontWeight: "300" }}>AUDIT</span></h1>
          {!verifiedChain && <span style={{ fontSize: "0.8rem", color: "hsl(var(--color-danger))", fontWeight: "600" }}>[CHAIN BROKEN]</span>}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "24px" }}>
          <a href="/" style={{
              background: "rgba(255,255,255,0.05)", 
              border: "1px solid var(--border-color)", 
              color: "var(--text-secondary)", 
              padding: "6px 12px", 
              borderRadius: "6px",
              cursor: "pointer",
              fontSize: "0.85rem",
              fontWeight: "600",
              textDecoration: "none"
          }}>
            ← Back to Dashboard
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
                fontWeight: "500"
              }}
            >
              <option value="Operator (Tier 2)">Operator (Tier 2)</option>
              <option value="Administrator (Tier 3)">Administrator (Tier 3)</option>
            </select>
          </div>
        </div>
      </header>

      <main style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 400px", gap: "16px", padding: "0 16px 16px 16px" }}>
        
        {/* Audit Log Table */}
        <section className="glass-panel" style={{ padding: "20px", display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <h2 style={{ fontSize: "1.2rem", marginBottom: "16px" }}>Immutable Audit Trail</h2>
          <div style={{ overflowY: "auto", flex: 1 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
              <thead>
                <tr style={{ textAlign: "left", color: "var(--text-secondary)", borderBottom: "1px solid var(--border-color)" }}>
                  <th style={{ padding: "8px" }}>Time</th>
                  <th style={{ padding: "8px" }}>Actor</th>
                  <th style={{ padding: "8px" }}>Event Type</th>
                  <th style={{ padding: "8px" }}>Details</th>
                  <th style={{ padding: "8px" }}>Hash Integrity</th>
                </tr>
              </thead>
              <tbody>
                {events.map(ev => (
                  <tr key={ev.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                    <td style={{ padding: "8px", color: "var(--text-secondary)" }}>{new Date(ev.created_at).toLocaleString()}</td>
                    <td style={{ padding: "8px" }}>
                      <span style={{ color: ev.actor_tier === "Administrator" ? "hsl(var(--color-warning))" : "hsl(var(--color-primary))" }}>
                        {ev.actor}
                      </span>
                    </td>
                    <td style={{ padding: "8px", fontWeight: "600" }}>{ev.event_type}</td>
                    <td style={{ padding: "8px", color: "var(--text-secondary)" }}>
                      <pre style={{ margin: 0, whiteSpace: "pre-wrap", background: "rgba(0,0,0,0.2)", padding: "4px", borderRadius: "4px", fontSize: "0.75rem" }}>
                        {JSON.stringify(ev.detail, null, 2)}
                      </pre>
                    </td>
                    <td style={{ padding: "8px" }}>
                      {ev.is_valid ? <span style={{ color: "hsl(var(--color-primary))" }}>Valid</span> : <span style={{ color: "hsl(var(--color-danger))" }}>Tampered</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Erasure Request Form */}
        <section className="glass-panel" style={{ padding: "20px" }}>
          <h2 style={{ fontSize: "1.2rem", marginBottom: "16px", color: "hsl(var(--color-danger))" }}>Data Erasure Request</h2>
          <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "16px" }}>
            Erasure requests are strictly audited. Jailed categories cannot be erased. 
            Tier 3 (Administrator) privileges are required.
          </p>
          <form onSubmit={handleErasureRequest} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "4px" }}>Target Table</label>
              <input 
                value={targetTable}
                onChange={e => setTargetTable(e.target.value)}
                style={{ width: "100%", padding: "8px", background: "rgba(0,0,0,0.3)", border: "1px solid var(--border-color)", color: "#fff", borderRadius: "6px" }}
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "4px" }}>Target Specimen Token (Optional)</label>
              <input 
                value={targetToken}
                onChange={e => setTargetToken(e.target.value)}
                placeholder="SPECIMEN_..."
                style={{ width: "100%", padding: "8px", background: "rgba(0,0,0,0.3)", border: "1px solid var(--border-color)", color: "#fff", borderRadius: "6px" }}
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "4px" }}>Start Date (ISO 8601)</label>
              <input 
                type="datetime-local"
                value={startDate}
                onChange={e => setStartDate(e.target.value)}
                style={{ width: "100%", padding: "8px", background: "rgba(0,0,0,0.3)", border: "1px solid var(--border-color)", color: "#fff", borderRadius: "6px" }}
              />
            </div>
            <button 
              type="submit"
              disabled={userRole !== "Administrator (Tier 3)"}
              style={{
                background: userRole === "Administrator (Tier 3)" ? "hsl(var(--color-danger))" : "rgba(255,255,255,0.1)",
                color: "#fff",
                border: "none",
                padding: "10px",
                borderRadius: "6px",
                cursor: userRole === "Administrator (Tier 3)" ? "pointer" : "not-allowed",
                fontWeight: "600",
                marginTop: "16px"
              }}
            >
              Request Immutable Erasure
            </button>
          </form>
        </section>

      </main>
    </div>
  );
}
