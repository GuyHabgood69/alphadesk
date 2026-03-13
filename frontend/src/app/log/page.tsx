"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ChevronDown,
  FileText,
  Filter,
  Radio,
  RefreshCw,
} from "lucide-react";

const API = "";

interface LogEntryMetadata {
  tickers?: string[];
  total?: number;
  [key: string]: unknown;
}

interface LogEntry {
  id: number;
  time: string;
  timestamp: string;
  source: string;
  event: string;
  message: string;
  ticker: string | null;
  metadata?: LogEntryMetadata;
}

const SOURCE_COLORS: Record<string, string> = {
  scout: "#5ae892",
  analyst: "#b8a4f0",
  risk: "#60a5fa",
  executor: "#60a5fa",
  alert: "#fbbf24",
  system: "#9a9a9a",
};

const EVENT_LABELS: Record<string, string> = {
  scan_start: "Scan Started",
  scan_complete: "Scan Complete",
  anomaly_found: "Signal Detected",
  thesis_request: "Thesis Requested",
  thesis_generated: "Thesis Generated",
  risk_approved: "Risk Approved",
  risk_rejected: "Risk Rejected",
  order_submitted: "Order Submitted",
  order_filled: "Order Filled",
  alert_sent: "Alert Sent",
  agent_started: "Agent Started",
  agent_stopped: "Agent Stopped",
  error: "Error",
  info: "Info",
};

export default function LogPage() {
  const router = useRouter();
  const [authed, setAuthed] = useState(false);
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");
  const [showFilter, setShowFilter] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  // Auth check
  useEffect(() => {
    fetch(`${API}/api/auth/me`, { credentials: "include" })
      .then((res) => {
        if (res.ok) setAuthed(true);
        else router.replace("/login");
      })
      .catch(() => router.replace("/login"));
  }, [router]);

  const fetchLog = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/activity-feed/log`, { credentials: "include" });
      if (res.ok) {
        const data = await res.json();
        setEntries(data);
      }
    } catch {
      console.error("Failed to fetch activity log");
    } finally {
      setLoading(false);
      setLastRefresh(new Date());
    }
  }, []);

  useEffect(() => {
    fetchLog();
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchLog, 30_000);
    return () => clearInterval(interval);
  }, [fetchLog]);

  const filteredEntries = filter === "all"
    ? entries
    : entries.filter((e) => e.source === filter);

  const sources = ["all", ...Array.from(new Set(entries.map((e) => e.source)))];

  if (!authed) {
    return <div style={{ minHeight: "100vh", background: "var(--bg-main)" }} />;
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg-main)",
        color: "var(--text-black)",
        padding: "32px 40px",
        maxWidth: 1200,
        margin: "0 auto",
      }}
    >
      {/* ═══ HEADER ═══ */}
      <header className="flex items-center justify-between" style={{ marginBottom: 32 }}>
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="flex items-center justify-center"
            style={{
              width: 36, height: 36, borderRadius: "50%",
              background: "var(--bg-black)", color: "var(--mint)",
              textDecoration: "none", transition: "opacity 0.15s",
            }}
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4" style={{ color: "var(--text-dark)" }} />
              <h1 style={{ fontSize: "1.2rem", fontWeight: 700, letterSpacing: "-0.02em" }}>
                Activity Log
              </h1>
              <span
                style={{
                  fontSize: "0.6rem", fontWeight: 700, letterSpacing: "0.06em",
                  background: "var(--bg-black)", color: "var(--mint)",
                  padding: "2px 8px", borderRadius: 20,
                }}
              >
                24H
              </span>
            </div>
            <p style={{ fontSize: "0.7rem", color: "var(--text-light)", marginTop: 2 }}>
              Detailed system activity — refreshes every 30s
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span style={{ fontSize: "0.65rem", color: "var(--text-light)", fontFamily: "'Space Mono', monospace" }}>
            {filteredEntries.length} entries · Last refresh {lastRefresh.toLocaleTimeString("en-US", { hour12: false })}
          </span>

          {/* Source Filter */}
          <div style={{ position: "relative" }}>
            <button
              onClick={() => setShowFilter(!showFilter)}
              className="btn btn-outline flex items-center gap-1.5"
              style={{ padding: "7px 14px", fontSize: "0.72rem" }}
            >
              <Filter className="w-3 h-3" />
              {filter === "all" ? "All Sources" : filter.charAt(0).toUpperCase() + filter.slice(1)}
              <ChevronDown className="w-3 h-3" />
            </button>
            {showFilter && (
              <div
                style={{
                  position: "absolute", top: "100%", right: 0, marginTop: 4,
                  background: "white", border: "1px solid rgba(0,0,0,0.08)",
                  borderRadius: 10, boxShadow: "0 8px 24px rgba(0,0,0,0.08)",
                  zIndex: 50, overflow: "hidden", minWidth: 140,
                }}
              >
                {sources.map((s) => (
                  <button
                    key={s}
                    onClick={() => { setFilter(s); setShowFilter(false); }}
                    style={{
                      display: "flex", alignItems: "center", gap: 8,
                      width: "100%", padding: "8px 14px", border: "none",
                      background: s === filter ? "rgba(99,102,241,0.06)" : "none",
                      cursor: "pointer", fontSize: "0.72rem", fontWeight: s === filter ? 600 : 400,
                      textAlign: "left",
                    }}
                  >
                    {s !== "all" && (
                      <div
                        style={{
                          width: 6, height: 6, borderRadius: "50%",
                          background: SOURCE_COLORS[s] || "#9a9a9a",
                        }}
                      />
                    )}
                    {s === "all" ? "All Sources" : s.charAt(0).toUpperCase() + s.slice(1)}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button onClick={fetchLog} className="btn btn-outline" style={{ padding: "7px 14px", fontSize: "0.72rem" }}>
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
        </div>
      </header>

      {/* ═══ LOG TABLE ═══ */}
      <div
        style={{
          background: "var(--bg-black)",
          borderRadius: 16,
          border: "1px solid rgba(255,255,255,0.06)",
          overflow: "hidden",
        }}
      >
        {/* Table Header */}
        <div
          className="flex items-center"
          style={{
            padding: "12px 20px",
            borderBottom: "1px solid rgba(255,255,255,0.06)",
            fontSize: "0.62rem", fontWeight: 600,
            textTransform: "uppercase", letterSpacing: "0.08em",
            color: "rgba(255,255,255,0.3)",
          }}
        >
          <div style={{ width: 80 }}>Time</div>
          <div style={{ width: 80 }}>Source</div>
          <div style={{ width: 140 }}>Event</div>
          <div style={{ width: 70 }}>Ticker</div>
          <div style={{ flex: 1 }}>Message</div>
        </div>

        {/* Entries */}
        <div style={{ maxHeight: "calc(100vh - 200px)", overflowY: "auto" }}>
          {loading ? (
            <div className="flex items-center justify-center" style={{ padding: 60, color: "rgba(255,255,255,0.3)" }}>
              <Radio className="w-4 h-4" style={{ marginRight: 8, animation: "pulse 1.5s infinite" }} />
              Loading log...
            </div>
          ) : filteredEntries.length === 0 ? (
            <div className="flex flex-col items-center justify-center" style={{ padding: 60, color: "rgba(255,255,255,0.3)" }}>
              <FileText className="w-6 h-6" style={{ marginBottom: 8, opacity: 0.4 }} />
              <div style={{ fontSize: "0.82rem", fontWeight: 600, marginBottom: 4 }}>No activity in the last 24 hours</div>
              <div style={{ fontSize: "0.7rem" }}>Start the Scout agent to begin scanning</div>
            </div>
          ) : (
            filteredEntries.map((entry) => (
              <div
                key={entry.id}
                className="flex items-start"
                style={{
                  padding: "10px 20px",
                  borderBottom: "1px solid rgba(255,255,255,0.03)",
                  transition: "background 0.12s",
                  fontSize: "0.72rem",
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.02)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
              >
                {/* Time */}
                <div style={{
                  width: 80, flexShrink: 0,
                  fontFamily: "'Space Mono', monospace", fontSize: "0.68rem",
                  color: "rgba(255,255,255,0.35)",
                }}>
                  {entry.time}
                </div>

                {/* Source */}
                <div style={{ width: 80, flexShrink: 0 }} className="flex items-center gap-1.5">
                  <div
                    style={{
                      width: 6, height: 6, borderRadius: "50%",
                      background: SOURCE_COLORS[entry.source] || "#9a9a9a",
                    }}
                  />
                  <span style={{
                    fontSize: "0.62rem", fontWeight: 600,
                    textTransform: "uppercase", letterSpacing: "0.04em",
                    color: "rgba(255,255,255,0.5)",
                  }}>
                    {entry.source}
                  </span>
                </div>

                {/* Event */}
                <div style={{ width: 140, flexShrink: 0 }}>
                  <span
                    style={{
                      fontSize: "0.6rem", fontWeight: 600,
                      padding: "2px 7px", borderRadius: 4,
                      background:
                        entry.event.includes("error") ? "rgba(242,92,92,0.15)" :
                        entry.event.includes("approved") || entry.event.includes("filled") ? "rgba(90,232,146,0.12)" :
                        entry.event.includes("rejected") ? "rgba(242,92,92,0.1)" :
                        "rgba(255,255,255,0.05)",
                      color:
                        entry.event.includes("error") ? "#f25c5c" :
                        entry.event.includes("approved") || entry.event.includes("filled") ? "#5ae892" :
                        entry.event.includes("rejected") ? "#f25c5c" :
                        "rgba(255,255,255,0.5)",
                    }}
                  >
                    {EVENT_LABELS[entry.event] || entry.event}
                  </span>
                </div>

                {/* Ticker */}
                <div style={{ width: 70, flexShrink: 0 }}>
                  {entry.ticker && (
                    <span
                      style={{
                        fontSize: "0.62rem", fontWeight: 700,
                        fontFamily: "'Space Mono', monospace",
                        background: "rgba(140,245,180,0.1)", color: "#5ae892",
                        padding: "1px 6px", borderRadius: 4,
                      }}
                    >
                      {entry.ticker}
                    </span>
                  )}
                </div>

                {/* Message */}
                <div style={{ flex: 1, color: "rgba(255,255,255,0.7)", lineHeight: 1.4 }}>
                  {entry.message}
                  {entry.event === "scan_start" && entry.metadata?.tickers && (
                    <span style={{
                      marginLeft: 6, fontSize: "0.62rem",
                      color: "rgba(255,255,255,0.3)", fontFamily: "'Space Mono', monospace",
                    }}>
                      [{entry.metadata.tickers.join(", ")}
                      {(entry.metadata.total ?? 0) > 3 ? `, +${(entry.metadata.total ?? 0) - 3} more` : ""}]
                    </span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
