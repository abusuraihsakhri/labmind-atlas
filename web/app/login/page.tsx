"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [role, setRole] = useState("Operator (Tier 2)");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const response = await fetch("/api/session", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({role,password})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Sign-in failed");
      setPassword("");
      router.replace("/");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-in failed");
    } finally { setBusy(false); }
  }
  return <main style={{maxWidth:460,margin:"10vh auto",padding:28}} className="glass-panel">
    <h1 style={{fontSize:28,marginBottom:10}}>LabMind ATLAS</h1>
    <p style={{color:"var(--text-secondary)",marginBottom:24}}>Secure dashboard sign-in</p>
    <form onSubmit={submit} style={{display:"grid",gap:15}}>
      <label htmlFor="role">Access tier</label>
      <select id="role" value={role} onChange={e=>setRole(e.target.value)} style={{padding:12,background:"#17263a",color:"white",border:"1px solid #526074"}}>
        <option>Operator (Tier 2)</option><option>Administrator (Tier 3)</option>
      </select>
      <label htmlFor="password">Password</label>
      <input id="password" type="password" autoComplete="current-password" required
        value={password} onChange={e=>setPassword(e.target.value)}
        style={{padding:12,background:"#17263a",color:"white",border:"1px solid #526074"}} />
      {error && <p role="alert" style={{color:"#fca5a5"}}>{error}</p>}
      <button disabled={busy} type="submit" style={{padding:12,background:"#5ddbbd",border:0,borderRadius:8,fontWeight:700}}>{busy?"Signing in…":"Sign in"}</button>
    </form>
    <p style={{marginTop:24,fontSize:12,color:"var(--text-secondary)"}}>Use only on a trusted server with HTTPS. The public GitHub Pages demo uses synthetic data and does not require credentials.</p>
  </main>;
}
