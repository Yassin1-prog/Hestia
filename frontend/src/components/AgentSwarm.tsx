"use client";

import { Bot, Check, CircleAlert, LoaderCircle, ShieldCheck } from "lucide-react";

import type { TraceAgent } from "@/lib/trace";

function AgentIcon({ status }: { status: TraceAgent["status"] }) {
  if (status === "running") return <LoaderCircle size={12} strokeWidth={2} className="spin" />;
  if (status === "done") return <Check size={12} strokeWidth={2.5} className="check-draw" />;
  return <CircleAlert size={12} strokeWidth={2} />;
}

/**
 * Collaborating agents inside a step: a hub (the orchestrator, or the Oumi Iris model) wired to
 * one node per sub-agent. Wires carry moving packets while an agent works, then settle.
 */
export function AgentSwarm({ hub, agents }: { hub?: string; agents: TraceAgent[] }) {
  const live = agents.some((a) => a.status === "running");
  const HubIcon = hub === "Oumi Iris" ? ShieldCheck : Bot;
  return (
    <div className={`swarm${live ? " is-live" : ""}`} role="list" aria-label="Collaborating agents">
      <div className="swarm-hub">
        <span className="swarm-hub-icon">
          <HubIcon size={14} strokeWidth={1.75} />
        </span>
        <span className="swarm-hub-label">{hub ?? "Orchestrator"}</span>
      </div>
      <ul className="swarm-agents">
        {agents.map((a, i) => (
          <li
            key={a.id}
            role="listitem"
            className={`swarm-agent swarm-${a.status}`}
            style={{ animationDelay: `${i * 90}ms` }}
          >
            <span className="swarm-link" aria-hidden="true">
              <i className="swarm-packet" />
              <i className="swarm-packet swarm-packet-2" />
            </span>
            <span className="swarm-node">
              <span className="swarm-node-icon">
                <AgentIcon status={a.status} />
              </span>
              <span className="swarm-node-label">{a.label}</span>
            </span>
            {a.detail && (
              <span className="swarm-detail" key={a.detail}>
                {a.detail}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
