"use client";

import React, { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface StepResult {
  step: number;
  action: string;
  tool: string;
  output: string;
}

interface AgentResponse {
  goal: string;
  plan: string[];
  steps: StepResult[];
  deliverable: string;
}

const styles: Record<string, React.CSSProperties> = {
  main: {
    maxWidth: 800,
    margin: "48px auto",
    padding: "0 20px",
  },
  subtitle: {
    color: "#94a3b8",
    marginBottom: 24,
  },
  form: {
    display: "flex",
    gap: 12,
    marginBottom: 32,
  },
  input: {
    flex: 1,
    padding: "12px 16px",
    borderRadius: 10,
    border: "1px solid #334155",
    background: "#0f172a",
    color: "#f8fafc",
    fontSize: 15,
  },
  button: {
    padding: "12px 24px",
    borderRadius: 10,
    border: "none",
    background: "#38bdf8",
    color: "#090d16",
    fontWeight: 600,
    cursor: "pointer",
  },
  error: {
    color: "#f87171",
    marginBottom: 20,
  },
  card: {
    background: "#0f172a",
    padding: 20,
    borderRadius: 12,
    border: "1px solid #1e293b",
  },
  pre: {
    whiteSpace: "pre-wrap",
    margin: 0,
    color: "#e2e8f0",
  },
};

export default function HomePage() {
  const [goal, setGoal] = useState("");
  const [result, setResult] = useState<AgentResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun(e: React.FormEvent) {
    e.preventDefault();
    if (!goal.trim()) return;

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/agent/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal }),
      });
      if (!res.ok) {
        throw new Error(`Request failed (${res.status})`);
      }
      const data: AgentResponse = await res.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run agent");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={styles.main}>
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>GENAI Summit — Agent Starter</h1>
      <p style={styles.subtitle}>
        Give the agent a goal to plan, execute tools, and deliver an end-to-end result.
      </p>

      <form onSubmit={handleRun} style={styles.form}>
        <input
          type="text"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="Enter a high-level goal..."
          style={styles.input}
        />
        <button type="submit" disabled={loading} style={styles.button}>
          {loading ? "Running..." : "Run Agent"}
        </button>
      </form>

      {error && (
        <p role="alert" style={styles.error}>
          {error}
        </p>
      )}

      {result && (
        <div style={{ display: "grid", gap: 20 }}>
          <section style={styles.card}>
            <h2 style={{ fontSize: 16, marginTop: 0 }}>1. Execution Plan & Tool Steps</h2>
            <ul style={{ paddingLeft: 20, margin: 0, lineHeight: 1.7 }}>
              {result.steps.map((s) => (
                <li key={s.step}>
                  <div>
                    <strong>[{s.tool}]</strong> {s.action}
                  </div>
                  <div style={{ color: "#38bdf8" }}>{s.output}</div>
                </li>
              ))}
            </ul>
          </section>

          <section style={styles.card}>
            <h2 style={{ fontSize: 16, marginTop: 0 }}>2. Final Deliverable</h2>
            <pre style={styles.pre}>{result.deliverable}</pre>
          </section>
        </div>
      )}
    </main>
  );
}
