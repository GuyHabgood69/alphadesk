"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Bot,
  ChevronRight,
  CircleDollarSign,
  Clock,
  Cpu,
  Crosshair,
  FileText,
  Gauge,
  Layers,
  MessageSquare,
  Plus,
  Power,
  LogOut,
  Radio,
  RefreshCw,
  Shield,
  Sparkles,
  TrendingUp,
  X,
  Zap,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────

interface TradeResult {
  id: string;
  ticker: string;
  action: "BUY" | "SELL" | "HOLD";
  notional_usd: number;
  filled_qty: number;
  filled_avg_price: number;
  status: string;
  thesis_summary: string;
  timestamp: string;
  risk_verdict: { approved: boolean; reason: string } | null;
}

interface RiskConfig {
  max_risk_pct: number;
  max_daily_drawdown_pct: number;
}

interface AgentStatus {
  name: string;
  state: string;
  last_run: string | null;
  message: string;
}

interface Portfolio {
  equity: number;
  daily_pnl: number;
  max_positions: number;
}

interface TrackedPosition {
  ticker: string;
  side: "BUY" | "SELL";
  entry_price: number;
  entry_time: string;
  notional_usd: number;
  qty: number;
  stop_loss_price: number;
  take_profit_price: number;
  max_hold_until: string;
  thesis_summary: string;
  order_id: string;
}

const API = "";

// ═══════════════════════════════════════════════════════════════════════
// DASHBOARD
// ═══════════════════════════════════════════════════════════════════════

export default function Dashboard() {
  const router = useRouter();
  const [authed, setAuthed] = useState(false);
  const [trades, setTrades] = useState<TradeResult[]>([]);
  const [risk, setRisk] = useState<RiskConfig>({ max_risk_pct: 1, max_daily_drawdown_pct: 10 });
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio>({ equity: 0, daily_pnl: 0, max_positions: 6 });
  const [pnlHistory, setPnlHistory] = useState<{ time: string; value: number }[]>([]);
  const [activityFeed, setActivityFeed] = useState<{ id: number; time: string; source: string; event: string; message: string; ticker: string | null; metadata?: Record<string, unknown> }[]>([]);
  const [marketInfo, setMarketInfo] = useState<{ market_open: boolean; next_event: string; time_et: string }>({ market_open: false, next_event: "", time_et: "" });
  const [weeklyPnlHistory, setWeeklyPnlHistory] = useState<{ time: string; value: number }[]>([]);
  const [positions, setPositions] = useState<TrackedPosition[]>([]);
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [newTicker, setNewTicker] = useState("");
  const [suggestions, setSuggestions] = useState<{ symbol: string; name: string }[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const suggestionsRef = useRef<HTMLDivElement>(null);
  const [riskInput, setRiskInput] = useState("1.0");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(new Date());
  const [pnlTab, setPnlTab] = useState<"intraday" | "weekly">("intraday");

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // ── Auth check ──────────────────────────────────────────────────────
  useEffect(() => {
    fetch(`${API}/api/auth/me`, { credentials: "include" })
      .then((res) => {
        if (res.ok) setAuthed(true);
        else router.replace("/login");
      })
      .catch(() => router.replace("/login"));
  }, [router]);

  const fetchAll = useCallback(async () => {
    try {
      const opts: RequestInit = { credentials: "include" };
      const [t, r, a, p, ph, af, wph, pos, wl] = await Promise.all([
        fetch(`${API}/api/trades`, opts), fetch(`${API}/api/risk-config`, opts),
        fetch(`${API}/api/agents/status`, opts), fetch(`${API}/api/portfolio`, opts),
        fetch(`${API}/api/pnl-history`, opts), fetch(`${API}/api/activity-feed`, opts),
        fetch(`${API}/api/pnl-history-weekly`, opts), fetch(`${API}/api/positions`, opts),
        fetch(`${API}/api/watchlist`, opts),
      ]);
      if (t.ok) { setError(null); setTrades(await t.json()); }
      if (r.ok) { const rc = await r.json(); setRisk(rc); setRiskInput(rc.max_risk_pct.toString()); }
      if (a.ok) { const ad = await a.json(); setAgents(ad.agents || ad); if (ad.market) setMarketInfo(ad.market); }
      if (p.ok) setPortfolio(await p.json());
      if (ph.ok) setPnlHistory(await ph.json());
      if (af.ok) setActivityFeed(await af.json());
      if (wph.ok) setWeeklyPnlHistory(await wph.json());
      if (pos.ok) setPositions(await pos.json());
      if (wl.ok) setWatchlist(await wl.json());
    } catch (e) {
      console.error("[AlphaDesk] API fetch failed:", e);
      setError("Unable to reach backend — retrying…");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); const i = setInterval(fetchAll, 15000); return () => clearInterval(i); }, [fetchAll]);

  const updateRisk = async () => {
    const v = parseFloat(riskInput); if (isNaN(v) || v < 0.1 || v > 10) return;
    try {
      const res = await fetch(`${API}/api/risk-config`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ max_risk_pct: v, max_daily_drawdown_pct: risk.max_daily_drawdown_pct }),
      });
      if (res.ok) setRisk(await res.json());
    } catch { /* silent */ }
  };

  const closePosition = async (ticker: string) => {
    if (!confirm(`Close position in ${ticker}?`)) return;
    try {
      const res = await fetch(`${API}/api/positions/${ticker}/close`, { method: "POST", credentials: "include" });
      if (res.ok) fetchAll();
    } catch { /* silent */ }
  };

  const toggleScout = async () => {
    try { await fetch(`${API}/api/agents/scout/toggle`, { method: "POST", credentials: "include" }); await fetchAll(); } catch { }
  };

  const addToWatchlist = async () => {
    const t = newTicker.trim().toUpperCase();
    if (!t) return;
    try {
      const res = await fetch(`${API}/api/watchlist`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ ticker: t }),
      });
      if (res.ok) { const data = await res.json(); setWatchlist(data.watchlist); setNewTicker(""); }
    } catch { /* silent */ }
  };

  const removeFromWatchlist = async (ticker: string) => {
    try {
      const res = await fetch(`${API}/api/watchlist/${ticker}`, { method: "DELETE", credentials: "include" });
      if (res.ok) { const data = await res.json(); setWatchlist(data.watchlist); }
    } catch { /* silent */ }
  };

  const scout = agents.find((a) => a.name === "ScoutAgent");
  const analyst = agents.find((a) => a.name === "AnalystAgent");
  // Scout is "active" when its loop is running (any non-stopped state means the loop is alive)
  const scoutActive = scout?.state !== undefined && scout?.message !== "Stopped";
  const scoutRunning = scout?.state === "scanning" || scout?.state === "analysing" || scout?.state === "executing";
  const pnlPositive = portfolio.daily_pnl >= 0;

  // ─── Render ─────────────────────────────────────────────────────────────────
  if (!authed) {
    return (
      <div style={{ minHeight: "100vh", background: "#0a0b0d" }} />
    );
  }

  return (
    <div className="min-h-screen" style={{ padding: "24px 24px 48px" }}>
      <div className="max-w-[1440px] mx-auto">

        {/* ═══ ERROR BANNER ═══ */}
        {error && (
          <div style={{
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            borderRadius: "0.5rem",
            padding: "0.5rem 1rem",
            marginBottom: "0.75rem",
            fontSize: "0.8rem",
            color: "#ef4444",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
          }}>
            <AlertTriangle className="w-4 h-4" style={{ color: "#ef4444", flexShrink: 0 }} /> {error}
          </div>
        )}

        {/* ═══ HEADER ═══ */}
        <header className="flex items-center justify-between mb-6 animate-in">
          <div className="flex items-center gap-3">
            <div
              className="icon-circle"
              style={{ background: "var(--bg-black)", width: 42, height: 42 }}
            >
              <Layers className="w-5 h-5" style={{ color: "var(--mint)" }} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 style={{ fontSize: "1.3rem", fontWeight: 700, letterSpacing: "-0.02em" }}>
                  AlphaDesk
                </h1>
                <span
                  style={{
                    fontSize: "0.6rem", fontWeight: 700, letterSpacing: "0.06em",
                    background: "var(--mint-bg)", color: "#1a8a4a",
                    padding: "2px 8px", borderRadius: 20,
                  }}
                >
                  PAPER
                </span>
              </div>
              <p style={{ fontSize: "0.72rem", color: "var(--text-light)", marginTop: 1 }}>
                Multi-Agent Trading Terminal
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div
              className="hidden sm:flex items-center gap-2"
              style={{
                fontSize: "0.72rem", color: "var(--text-light)",
                fontFamily: "'Space Mono', monospace",
              }}
            >
              <Clock className="w-3 h-3" />
              {now.toLocaleTimeString("en-US", { hour12: false })}
              <span style={{ color: "var(--text-light)", opacity: 0.4 }}>·</span>
              {now.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
            </div>
            <Link href="/log" className="btn btn-outline" style={{ padding: "7px 14px", fontSize: "0.72rem", textDecoration: "none", color: "inherit" }}>
              <FileText className="w-3 h-3" /> Log
            </Link>
            <button onClick={fetchAll} className="btn btn-outline" style={{ padding: "7px 14px", fontSize: "0.72rem" }}>
              <RefreshCw className="w-3 h-3" /> Refresh
            </button>
            <button
              onClick={async () => {
                await fetch(`${API}/api/auth/logout`, { method: "POST", credentials: "include" });
                router.replace("/login");
              }}
              className="btn btn-outline"
              style={{ padding: "7px 14px", fontSize: "0.72rem", color: "var(--text-light)" }}
            >
              <LogOut className="w-3 h-3" /> Sign Out
            </button>
          </div>
        </header>

        {/* ═══ BENTO GRID ═══ */}
        <div
          className="grid gap-4"
          style={{
            gridTemplateColumns: "repeat(12, 1fr)",
            gridAutoRows: "minmax(0, auto)",
          }}
        >

          {/* ── ROW 1: Hero Equity (dark) + Daily P&L (mint/red) + Trades + Risk ── */}

          {/* Portfolio Equity — dark card, 5 cols */}
          <div
            className="card-dark animate-in delay-1"
            style={{ gridColumn: "span 5", padding: "28px 28px 24px" }}
          >
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2">
                <div className="icon-circle icon-circle-dark" style={{ width: 32, height: 32 }}>
                  <CircleDollarSign className="w-4 h-4" style={{ color: "var(--mint)" }} />
                </div>
                <span style={{ fontSize: "0.72rem", color: "var(--text-white-dim)", fontWeight: 500 }}>
                  Portfolio Equity
                </span>
              </div>
              <div className="arrow-link arrow-dark"><ArrowUpRight className="w-3 h-3" /></div>
            </div>
            <div
              style={{
                fontSize: "2.6rem", fontWeight: 700, letterSpacing: "-0.03em",
                fontFamily: "'Space Mono', monospace", lineHeight: 1,
              }}
            >
              {loading ? (
                <span style={{ opacity: 0.3 }}>—</span>
              ) : (
                `$${portfolio.equity.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              )}
            </div>
            <div style={{ fontSize: "0.7rem", color: "var(--text-white-dim)", marginTop: 8 }}>
              Paper trading account
            </div>
          </div>

          {/* Daily P&L — mint or red card, 3 cols */}
          <div
            className={pnlPositive ? "card-mint" : "card-light"}
            style={{
              gridColumn: "span 3", padding: "28px 24px 24px",
              background: pnlPositive ? "var(--mint)" : "var(--red-bg)",
            }}
          >
            <div className="flex items-center justify-between mb-4">
              <span style={{ fontSize: "0.72rem", fontWeight: 500, opacity: 0.7 }}>Daily P&L</span>
              <div className="arrow-link" style={{ background: pnlPositive ? "rgba(0,0,0,0.06)" : "rgba(0,0,0,0.04)", border: "none" }}>
                {pnlPositive ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
              </div>
            </div>
            <div
              style={{
                fontSize: "2rem", fontWeight: 700, letterSpacing: "-0.02em",
                fontFamily: "'Space Mono', monospace", lineHeight: 1,
              }}
            >
              {loading ? (
                <span style={{ opacity: 0.3 }}>—</span>
              ) : (
                `${pnlPositive ? "+" : "-"}$${Math.abs(portfolio.daily_pnl).toFixed(2)}`
              )}
            </div>
            {/* Mini bar — driven by pnlHistory data */}
            <div style={{ marginTop: 16, display: "flex", gap: 3, alignItems: "flex-end" }}>
              {(() => {
                const bars = pnlHistory.length > 0
                  ? pnlHistory.slice(-12).map(p => p.value)
                  : [40, 28, 55, 35, 65, 45, 70, 50, 60, 38, 72, 48];
                const maxBar = Math.max(...bars.map(Math.abs), 1);
                return bars.map((v, i) => (
                  <div
                    key={i}
                    style={{
                      width: "100%",
                      height: Math.max(4, (Math.abs(v) / maxBar) * 44),
                      borderRadius: 3,
                      background: pnlPositive ? "rgba(0,0,0,0.10)" : "rgba(194,60,60,0.18)",
                    }}
                  />
                ));
              })()}
            </div>
          </div>

          {/* Trades Today — light card, 2 cols */}
          <div
            className="card-light animate-in delay-2"
            style={{ gridColumn: "span 2", padding: "24px 20px" }}
          >
            <div className="icon-circle icon-circle-light" style={{ width: 32, height: 32, marginBottom: 16 }}>
              <BarChart3 className="w-4 h-4" style={{ color: "var(--lavender-deep)" }} />
            </div>
            <div style={{ fontSize: "0.65rem", textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-light)", fontWeight: 600, marginBottom: 4 }}>
              Trades
            </div>
            <div style={{ fontSize: "2rem", fontWeight: 700, fontFamily: "'Space Mono', monospace", lineHeight: 1 }}>
              {trades.length}
            </div>
            <div style={{ fontSize: "0.65rem", color: "var(--text-light)", marginTop: 6 }}>
              {trades.filter(t => t.status === "filled").length} filled
            </div>
          </div>

          {/* Risk Per Trade — lavender card, 2 cols */}
          <div
            className="card-lavender animate-in delay-3"
            style={{ gridColumn: "span 2", padding: "24px 20px" }}
          >
            <div className="icon-circle icon-circle-mint" style={{ width: 32, height: 32, marginBottom: 16, background: "rgba(0,0,0,0.07)" }}>
              <Shield className="w-4 h-4" style={{ color: "var(--text-dark)" }} />
            </div>
            <div style={{ fontSize: "0.65rem", textTransform: "uppercase", letterSpacing: "0.08em", color: "rgba(0,0,0,0.5)", fontWeight: 600, marginBottom: 4 }}>
              Risk / Trade
            </div>
            <div style={{ fontSize: "2rem", fontWeight: 700, fontFamily: "'Space Mono', monospace", lineHeight: 1 }}>
              {risk.max_risk_pct}%
            </div>
            <div style={{ fontSize: "0.65rem", color: "rgba(0,0,0,0.45)", marginTop: 6 }}>
              {risk.max_daily_drawdown_pct}% max DD
            </div>
          </div>


          {/* ── P&L CHART — full-width tabbed ─────────────────────── */}
          <div
            className="card-light animate-in delay-3"
            style={{ gridColumn: "span 12", padding: "22px 24px 16px" }}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className="icon-circle icon-circle-light" style={{ width: 30, height: 30 }}>
                  {pnlTab === "intraday"
                    ? <TrendingUp className="w-3.5 h-3.5" style={{ color: "var(--mint-deep)" }} />
                    : <BarChart3 className="w-3.5 h-3.5" style={{ color: "var(--lavender-deep)" }} />
                  }
                </div>
                <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>
                  {pnlTab === "intraday" ? "Intraday P&L" : "Weekly P&L"}
                </span>
              </div>
              <div className="flex items-center" style={{ background: "var(--bg-white-soft)", borderRadius: 20, padding: 2, border: "1px solid var(--border-light)" }}>
                <button
                  onClick={() => setPnlTab("intraday")}
                  style={{
                    padding: "4px 14px", borderRadius: 18, border: "none", cursor: "pointer",
                    fontSize: "0.62rem", fontWeight: 600, letterSpacing: "0.04em",
                    background: pnlTab === "intraday" ? "var(--mint-bg)" : "transparent",
                    color: pnlTab === "intraday" ? "#1a8a4a" : "var(--text-light)",
                    transition: "all 0.15s",
                  }}
                >
                  TODAY
                </button>
                <button
                  onClick={() => setPnlTab("weekly")}
                  style={{
                    padding: "4px 14px", borderRadius: 18, border: "none", cursor: "pointer",
                    fontSize: "0.62rem", fontWeight: 600, letterSpacing: "0.04em",
                    background: pnlTab === "weekly" ? "var(--lavender-bg)" : "transparent",
                    color: pnlTab === "weekly" ? "var(--lavender-deep)" : "var(--text-light)",
                    transition: "all 0.15s",
                  }}
                >
                  THIS WEEK
                </button>
              </div>
            </div>
            {pnlTab === "intraday"
              ? <PnlChart pnl={portfolio.daily_pnl} history={pnlHistory} />
              : <PnlChart pnl={portfolio.daily_pnl} history={weeklyPnlHistory} color="lavender" />
            }
          </div>

          {/* ── ROW 2: Trade Log (5 cols) + Live Feed (3 cols) + Right Panel (4 cols) ── */}

          {/* Trade Log */}
          <div
            className="card-light animate-in delay-3"
            style={{ gridColumn: "span 8" }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "18px 22px", borderBottom: "1px solid var(--border-light)" }}>
              <div className="flex items-center gap-2">
                <div className="icon-circle icon-circle-light" style={{ width: 30, height: 30 }}>
                  <Activity className="w-3.5 h-3.5" style={{ color: "var(--text-dark)" }} />
                </div>
                <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>Recent Trades</span>
              </div>
              {trades.length > 0 && (
                <span style={{
                  fontSize: "0.65rem", fontWeight: 600,
                  background: "var(--bg-white-soft)", padding: "3px 10px",
                  borderRadius: 20, color: "var(--text-light)",
                  border: "1px solid var(--border-light)",
                }}>
                  {trades.length} entries
                </span>
              )}
            </div>
            <div style={{ maxHeight: 380, overflowY: "auto" }}>
              {loading ? (
                <div className="flex flex-col items-center justify-center py-16 gap-3" style={{ color: "var(--text-light)" }}>
                  <RefreshCw className="w-5 h-5 animate-spin" style={{ opacity: 0.3 }} />
                  <span style={{ fontSize: "0.75rem" }}>Connecting to backend…</span>
                </div>
              ) : trades.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 gap-4">
                  <div
                    className="icon-circle"
                    style={{ width: 56, height: 56, background: "var(--mint-bg)", border: "1px solid rgba(0,0,0,0.04)" }}
                  >
                    <TrendingUp className="w-6 h-6" style={{ color: "var(--mint-deep)", opacity: 0.6 }} />
                  </div>
                  <div style={{ textAlign: "center" }}>
                    <div style={{ fontWeight: 600, fontSize: "0.88rem", color: "var(--text-dark)", marginBottom: 4 }}>
                      No trades yet
                    </div>
                    <div style={{ fontSize: "0.72rem", color: "var(--text-light)" }}>
                      Start the Scout Agent to begin scanning for anomalies
                    </div>
                  </div>
                </div>
              ) : (
                <table className="trade-table">
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th>Side</th>
                      <th>Notional</th>
                      <th>Status</th>
                      <th>Fill</th>
                      <th>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((t, i) => (
                      <tr key={t.id || i}>
                        <td style={{ fontWeight: 700, fontFamily: "'Space Mono', monospace", letterSpacing: "0.03em" }}>
                          {t.ticker}
                        </td>
                        <td><span className={`badge badge-${t.action.toLowerCase()}`}>
                          {t.action === "BUY" && <ArrowUpRight className="w-3 h-3" />}
                          {t.action === "SELL" && <ArrowDownRight className="w-3 h-3" />}
                          {t.action}
                        </span></td>
                        <td style={{ fontFamily: "'Space Mono', monospace", fontSize: "0.8rem" }}>
                          ${t.notional_usd.toFixed(2)}
                        </td>
                        <td><span className={`badge badge-${t.status}`}>{t.status}</span></td>
                        <td style={{ fontFamily: "'Space Mono', monospace", fontSize: "0.78rem", color: "var(--text-light)" }}>
                          {t.filled_avg_price > 0 ? `${t.filled_qty.toFixed(4)} @ $${t.filled_avg_price.toFixed(2)}` : "—"}
                        </td>
                        <td style={{ color: "var(--text-light)", fontSize: "0.72rem", fontFamily: "'Space Mono', monospace" }}>
                          {new Date(t.timestamp).toLocaleTimeString("en-US", { hour12: false })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* ── LIVE FEED (spans 2 rows: beside Trades + Positions) ── */}
          <div
            className="card-dark animate-in delay-4"
            style={{ gridColumn: "span 4", gridRow: "span 2", display: "flex", flexDirection: "column" }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "18px 20px", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
              <div className="flex items-center gap-2">
                <div className="icon-circle icon-circle-dark" style={{ width: 30, height: 30 }}>
                  <Radio className="w-3.5 h-3.5" style={{ color: "var(--mint)" }} />
                </div>
                <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>Live Feed</span>
              </div>
              <div className="status-dot scanning" />
            </div>
            <div style={{ height: 400, overflowY: "auto", padding: "4px 0" }}>
              {activityFeed.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 gap-3" style={{ height: "100%" }}>
                  <div className="icon-circle" style={{ width: 44, height: 44, background: "rgba(140,245,180,0.08)" }}>
                    <MessageSquare className="w-5 h-5" style={{ color: "var(--mint)", opacity: 0.4 }} />
                  </div>
                  <div style={{ textAlign: "center" }}>
                    <div style={{ fontWeight: 600, fontSize: "0.78rem", color: "var(--text-white)", marginBottom: 3 }}>No activity yet</div>
                    <div style={{ fontSize: "0.65rem", color: "var(--text-white-dim)" }}>Agent actions will appear here</div>
                  </div>
                </div>
              ) : (
                activityFeed.slice(-20).map((entry) => (
                  <div
                    key={entry.id}
                    className="flex items-start gap-2.5"
                    style={{ padding: "9px 18px", borderBottom: "1px solid rgba(255,255,255,0.03)", transition: "background 0.15s" }}
                  >
                    <div
                      style={{
                        width: 6, height: 6, borderRadius: "50%", marginTop: 6, flexShrink: 0,
                        background:
                          entry.source === "scout" ? "var(--mint)" :
                            entry.source === "analyst" ? "var(--lavender-soft)" :
                              entry.source === "risk" ? (entry.event.includes("rejected") ? "var(--red)" : "var(--mint-deep)") :
                                entry.source === "executor" ? "#60a5fa" :
                                  entry.source === "alert" ? "#fbbf24" :
                                    "var(--text-light)",
                      }}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="flex items-center gap-1.5" style={{ marginBottom: 2 }}>
                        <span style={{ fontSize: "0.62rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-white-dim)" }}>
                          {entry.source}
                        </span>
                        {entry.ticker && (
                          <span style={{
                            fontSize: "0.58rem", fontWeight: 700, fontFamily: "'Space Mono', monospace",
                            background: "rgba(140,245,180,0.1)", color: "var(--mint)",
                            padding: "1px 5px", borderRadius: 4, letterSpacing: "0.02em",
                          }}>
                            {entry.ticker}
                          </span>
                        )}
                        <span style={{ fontSize: "0.58rem", color: "rgba(255,255,255,0.25)", fontFamily: "'Space Mono', monospace", marginLeft: "auto", flexShrink: 0 }}>
                          {entry.time}
                        </span>
                      </div>
                      <div style={{ fontSize: "0.7rem", color: "rgba(255,255,255,0.7)", lineHeight: 1.35 }}>
                        {entry.event === "scan_start" && entry.metadata?.tickers ? (
                          <>
                            {entry.message.split(" tickers")[0]} tickers{entry.message.split(" tickers")[1]}
                            <span style={{ marginLeft: 6, fontSize: "0.62rem", color: "rgba(255,255,255,0.4)", fontFamily: "'Space Mono', monospace" }}>
                              [{(entry.metadata.tickers as string[]).join(", ")}{(entry.metadata.total as number) > 3 ? `, +${(entry.metadata.total as number) - 3} more` : ""}]
                            </span>
                          </>
                        ) : (
                          entry.message
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* ── OPEN POSITIONS ── */}
          <div
            className="card animate-in delay-3"
            style={{ gridColumn: "span 8", display: "flex", flexDirection: "column" }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "18px 20px", borderBottom: "1px solid rgba(0,0,0,0.06)" }}>
              <div className="flex items-center gap-2">
                <div className="icon-circle" style={{ width: 30, height: 30, background: "rgba(140,245,180,0.12)" }}>
                  <Crosshair className="w-3.5 h-3.5" style={{ color: "var(--mint-deep)" }} />
                </div>
                <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>Open Positions</span>
              </div>
              <span style={{ fontSize: "0.68rem", fontWeight: 600, fontFamily: "'Space Mono', monospace", color: "var(--text-light)" }}>
                {positions.length} / {portfolio.max_positions}
              </span>
            </div>
            <div style={{ maxHeight: 300, overflowY: "auto" }}>
              {positions.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 gap-3">
                  <div className="icon-circle" style={{ width: 48, height: 48, background: "rgba(140,245,180,0.08)" }}>
                    <Crosshair className="w-5 h-5" style={{ color: "var(--mint)", opacity: 0.4 }} />
                  </div>
                  <div style={{ textAlign: "center" }}>
                    <div style={{ fontWeight: 600, fontSize: "0.82rem", color: "var(--text-dark)", marginBottom: 4 }}>No open positions</div>
                    <div style={{ fontSize: "0.7rem", color: "var(--text-light)" }}>Positions will appear here when trades are executed</div>
                  </div>
                </div>
              ) : (
                <table className="trade-table">
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th>Side</th>
                      <th>Entry</th>
                      <th>Stop Loss</th>
                      <th>Target</th>
                      <th>Notional</th>
                      <th>Days Left</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((pos) => {
                      const daysLeft = Math.max(0, Math.ceil((new Date(pos.max_hold_until).getTime() - Date.now()) / (1000 * 60 * 60 * 24)));
                      return (
                        <tr key={pos.ticker}>
                          <td style={{ fontWeight: 700, fontFamily: "'Space Mono', monospace" }}>{pos.ticker}</td>
                          <td>
                            <span className={`badge badge-${pos.side === "BUY" ? "buy" : "sell"}`} style={{ fontSize: "0.65rem", fontWeight: 700 }}>
                              {pos.side}
                            </span>
                          </td>
                          <td style={{ fontFamily: "'Space Mono', monospace", fontSize: "0.78rem" }}>
                            ${pos.entry_price.toFixed(2)}
                          </td>
                          <td style={{ fontFamily: "'Space Mono', monospace", fontSize: "0.78rem", color: "#ef4444" }}>
                            ${pos.stop_loss_price.toFixed(2)}
                          </td>
                          <td style={{ fontFamily: "'Space Mono', monospace", fontSize: "0.78rem", color: "#22c55e" }}>
                            ${pos.take_profit_price.toFixed(2)}
                          </td>
                          <td style={{ fontFamily: "'Space Mono', monospace", fontSize: "0.78rem" }}>
                            ${pos.notional_usd.toFixed(2)}
                          </td>
                          <td style={{ fontFamily: "'Space Mono', monospace", fontSize: "0.78rem", color: daysLeft <= 1 ? "#f59e0b" : "var(--text-light)" }}>
                            {daysLeft}d
                          </td>
                          <td>
                            <button
                              onClick={() => closePosition(pos.ticker)}
                              title="Close position"
                              aria-label={`Close ${pos.ticker} position`}
                              style={{
                                background: "rgba(239,68,68,0.08)",
                                border: "1px solid rgba(239,68,68,0.2)",
                                borderRadius: 6,
                                width: 28,
                                height: 28,
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                cursor: "pointer",
                                transition: "all 0.15s ease",
                              }}
                              onMouseEnter={(e) => {
                                e.currentTarget.style.background = "rgba(239,68,68,0.18)";
                                e.currentTarget.style.borderColor = "rgba(239,68,68,0.4)";
                              }}
                              onMouseLeave={(e) => {
                                e.currentTarget.style.background = "rgba(239,68,68,0.08)";
                                e.currentTarget.style.borderColor = "rgba(239,68,68,0.2)";
                              }}
                            >
                              <X className="w-3.5 h-3.5" style={{ color: "#ef4444" }} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* ── WATCHLIST ── */}
          <div
            className="card animate-in delay-3"
            style={{ gridColumn: "span 4", display: "flex", flexDirection: "column", overflow: "visible", position: "relative", zIndex: 10 }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "18px 20px", borderBottom: "1px solid rgba(0,0,0,0.06)" }}>
              <div className="flex items-center gap-2">
                <div className="icon-circle" style={{ width: 30, height: 30, background: "rgba(99,102,241,0.12)" }}>
                  <Layers className="w-3.5 h-3.5" style={{ color: "#6366f1" }} />
                </div>
                <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>Watchlist</span>
              </div>
              <span style={{ fontSize: "0.68rem", fontWeight: 600, fontFamily: "'Space Mono', monospace", color: "var(--text-light)" }}>
                {watchlist.length} tickers
              </span>
            </div>
            <div style={{ padding: "16px 20px" }}>
              {/* Add ticker input with autocomplete */}
              <div style={{ position: "relative", marginBottom: 14 }}>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={newTicker}
                    onChange={(e) => {
                      const val = e.target.value.toUpperCase();
                      setNewTicker(val);
                      if (debounceRef.current) clearTimeout(debounceRef.current);
                      if (val.length >= 1) {
                        debounceRef.current = setTimeout(async () => {
                          try {
                            const res = await fetch(`${API}/api/tickers/search?q=${encodeURIComponent(val)}`);
                            if (res.ok) {
                              const data = await res.json();
                              setSuggestions(data);
                              setShowSuggestions(data.length > 0);
                            }
                          } catch { /* ignore */ }
                        }, 250);
                      } else {
                        setSuggestions([]);
                        setShowSuggestions(false);
                      }
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") { addToWatchlist(); setShowSuggestions(false); }
                      if (e.key === "Escape") setShowSuggestions(false);
                    }}
                    onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true); }}
                    placeholder="Search ticker or company…"
                    style={{
                      flex: 1,
                      background: "rgba(0,0,0,0.03)",
                      border: "1px solid rgba(0,0,0,0.08)",
                      borderRadius: 8,
                      padding: "8px 12px",
                      fontSize: "0.78rem",
                      fontFamily: "'Space Mono', monospace",
                      outline: "none",
                      letterSpacing: "0.05em",
                    }}
                  />
                  <button
                    onClick={() => { addToWatchlist(); setShowSuggestions(false); }}
                    aria-label="Add ticker to watchlist"
                    style={{
                      background: "rgba(99,102,241,0.1)",
                      border: "1px solid rgba(99,102,241,0.2)",
                      borderRadius: 8,
                      width: 34,
                      height: 34,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      cursor: "pointer",
                      transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(99,102,241,0.2)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(99,102,241,0.1)"; }}
                  >
                    <Plus className="w-4 h-4" style={{ color: "#6366f1" }} />
                  </button>
                </div>
                {/* Autocomplete dropdown */}
                {showSuggestions && suggestions.length > 0 && (
                  <div
                    ref={suggestionsRef}
                    style={{
                      position: "absolute",
                      top: "100%",
                      left: 0,
                      right: 42,
                      background: "var(--bg-white)",
                      border: "1px solid rgba(0,0,0,0.1)",
                      borderRadius: 10,
                      marginTop: 4,
                      zIndex: 50,
                      boxShadow: "0 8px 30px rgba(0,0,0,0.12)",
                      maxHeight: 240,
                      overflowY: "auto",
                    }}
                  >
                    {suggestions.map((s) => (
                      <button
                        key={s.symbol}
                        onClick={() => {
                          setNewTicker(s.symbol);
                          setShowSuggestions(false);
                          setSuggestions([]);
                          // Directly add
                          fetch(`${API}/api/watchlist`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ ticker: s.symbol }),
                          }).then(async (res) => {
                            if (res.ok) {
                              const data = await res.json();
                              setWatchlist(data.watchlist);
                            }
                            setNewTicker("");
                          }).catch(() => { });
                        }}
                        style={{
                          width: "100%",
                          display: "flex",
                          alignItems: "center",
                          gap: 10,
                          padding: "9px 14px",
                          background: "none",
                          border: "none",
                          borderBottom: "1px solid rgba(0,0,0,0.04)",
                          cursor: "pointer",
                          textAlign: "left",
                          transition: "background 0.12s",
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(99,102,241,0.06)"; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = "none"; }}
                      >
                        <span style={{
                          fontFamily: "'Space Mono', monospace",
                          fontSize: "0.78rem",
                          fontWeight: 700,
                          color: "var(--text-black)",
                          minWidth: 54,
                        }}>
                          {s.symbol}
                        </span>
                        <span style={{
                          fontSize: "0.72rem",
                          color: "var(--text-light)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}>
                          {s.name}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {/* Ticker chips */}
              <div className="flex flex-wrap gap-2">
                {watchlist.map((t) => (
                  <div
                    key={t}
                    className="flex items-center gap-1.5"
                    style={{
                      background: "rgba(0,0,0,0.04)",
                      border: "1px solid rgba(0,0,0,0.07)",
                      borderRadius: 6,
                      padding: "5px 8px 5px 10px",
                      fontSize: "0.72rem",
                      fontWeight: 700,
                      fontFamily: "'Space Mono', monospace",
                      letterSpacing: "0.04em",
                    }}
                  >
                    {t}
                    <button
                      onClick={() => removeFromWatchlist(t)}
                      aria-label={`Remove ${t} from watchlist`}
                      style={{
                        background: "none",
                        border: "none",
                        cursor: "pointer",
                        padding: 0,
                        display: "flex",
                        opacity: 0.4,
                        transition: "opacity 0.15s ease",
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.opacity = "1"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.opacity = "0.4"; }}
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* ── RIGHT PANEL: Risk Controls ── */}
          <div
            className="card-light animate-in delay-4"
            style={{ gridColumn: "span 4" }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "18px 20px", borderBottom: "1px solid rgba(0,0,0,0.06)" }}>
              <div className="flex items-center gap-2">
                <div className="icon-circle icon-circle-light" style={{ width: 30, height: 30 }}>
                  <Gauge className="w-3.5 h-3.5" style={{ color: "var(--text-dark)" }} />
                </div>
                <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>Risk Controls</span>
              </div>
            </div>
            <div style={{ padding: "20px 24px 24px" }}>

            {/* Gauge Display */}
            <div className="flex items-center justify-between mb-5">
              <div>
                <div style={{ fontSize: "0.6rem", textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--text-light)", fontWeight: 600, marginBottom: 4 }}>
                  Max Risk Per Trade
                </div>
                <div style={{ fontSize: "2.2rem", fontWeight: 700, fontFamily: "'Space Mono', monospace", letterSpacing: "-0.03em", lineHeight: 1 }}>
                  {riskInput}%
                </div>
              </div>
              <div
                style={{
                  width: 56, height: 56, borderRadius: "50%",
                  background: "var(--bg-black)", color: "var(--mint)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}
              >
                <Shield className="w-5 h-5" />
              </div>
            </div>

            {/* Slider */}
            <div style={{ marginBottom: 16 }}>
              <input
                type="range" min="0.1" max="10" step="0.1"
                value={riskInput} onChange={(e) => setRiskInput(e.target.value)}
              />
              <div className="flex justify-between" style={{ marginTop: 6, fontSize: "0.6rem", fontFamily: "'Space Mono', monospace", color: "var(--text-light)" }}>
                <span>0.1%</span><span>5%</span><span>10%</span>
              </div>
            </div>

            <button onClick={updateRisk} className="btn btn-dark w-full" style={{ marginBottom: 16 }}>
              <Zap className="w-3.5 h-3.5" style={{ color: "var(--mint)" }} />
              Apply Limit
            </button>

            {/* Drawdown Warning */}
            <div
              className="flex items-center gap-2"
              style={{
                padding: "10px 14px", borderRadius: 14,
                background: "var(--red-bg)", fontSize: "0.72rem", color: "#c93c3c",
              }}
            >
              <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
              <span>Daily drawdown limit: <strong>{risk.max_daily_drawdown_pct}%</strong></span>
            </div>
            </div>
          </div>

          {/* ── Agent Status ── */}
          <div
            className="card-dark animate-in delay-5"
            style={{ gridColumn: "span 4" }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "18px 20px", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
              <div className="flex items-center gap-2">
                <div className="icon-circle icon-circle-dark" style={{ width: 30, height: 30 }}>
                  <Cpu className="w-3.5 h-3.5" style={{ color: "var(--lavender-soft)" }} />
                </div>
                <span style={{ fontSize: "0.85rem", fontWeight: 600 }}>Agents</span>
              </div>
              {scout?.last_run && (
                <span style={{ fontSize: "0.6rem", color: "var(--text-white-dim)", fontFamily: "'Space Mono', monospace" }}>
                  {new Date(scout.last_run).toLocaleTimeString("en-US", { hour12: false })}
                </span>
              )}
            </div>
            <div style={{ padding: "20px 24px 24px" }}>

            {/* Market Status */}
            <div
              className="flex items-center justify-between"
              style={{
                padding: "8px 14px", borderRadius: 10, marginBottom: 10,
                background: marketInfo.market_open ? "rgba(90,232,146,0.06)" : "rgba(255,255,255,0.02)",
                border: `1px solid ${marketInfo.market_open ? "rgba(90,232,146,0.12)" : "rgba(255,255,255,0.04)"}`,
              }}
            >
              <div className="flex items-center gap-2">
                <div
                  style={{
                    width: 6, height: 6, borderRadius: "50%",
                    background: marketInfo.market_open ? "#5ae892" : "rgba(255,255,255,0.25)",
                    boxShadow: marketInfo.market_open ? "0 0 8px rgba(90,232,146,0.4)" : "none",
                  }}
                />
                <span style={{ fontSize: "0.65rem", fontWeight: 600, color: marketInfo.market_open ? "#5ae892" : "rgba(255,255,255,0.4)" }}>
                  {marketInfo.market_open ? "MARKET OPEN" : "MARKET CLOSED"}
                </span>
              </div>
              <span style={{ fontSize: "0.6rem", color: "rgba(255,255,255,0.3)", fontFamily: "'Space Mono', monospace" }}>
                {marketInfo.next_event || marketInfo.time_et}
              </span>
            </div>

            {/* Scout */}
            <div
              className="flex items-center justify-between"
              style={{ padding: "12px 14px", borderRadius: 14, marginBottom: 10, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)" }}
            >
              <div className="flex items-center gap-3">
                <div style={{ position: "relative" }}>
                  <div className="icon-circle" style={{ width: 34, height: 34, background: "rgba(140,245,180,0.12)" }}>
                    <Sparkles className="w-3.5 h-3.5" style={{ color: "var(--mint)" }} />
                  </div>
                  <span className={`status-dot ${scout?.state || "idle"}`} style={{ position: "absolute", bottom: -1, right: -1, border: "2px solid var(--bg-black)" }} />
                </div>
                <div>
                  <div style={{ fontSize: "0.78rem", fontWeight: 600 }}>Scout</div>
                  <div style={{ fontSize: "0.6rem", color: "var(--text-white-dim)", fontFamily: "'Space Mono', monospace" }}>
                    {scout?.message || "idle"}
                  </div>
                </div>
              </div>
              <button
                onClick={toggleScout}
                className="flex items-center gap-1.5"
                style={{
                  padding: "6px 14px", borderRadius: 20, fontSize: "0.65rem",
                  fontWeight: 700, letterSpacing: "0.04em", border: "none", cursor: "pointer",
                  background: scoutActive ? "rgba(242,92,92,0.15)" : "rgba(140,245,180,0.15)",
                  color: scoutActive ? "var(--red)" : "var(--mint)",
                }}
              >
                <Power className="w-3 h-3" />
                {scoutActive ? "POWER OFF" : "START"}
              </button>
            </div>

            {/* Analyst */}
            <div
              className="flex items-center justify-between"
              style={{ padding: "12px 14px", borderRadius: 14, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)" }}
            >
              <div className="flex items-center gap-3">
                <div style={{ position: "relative" }}>
                  <div className="icon-circle" style={{ width: 34, height: 34, background: "rgba(184,164,240,0.15)" }}>
                    <Bot className="w-3.5 h-3.5" style={{ color: "var(--lavender-soft)" }} />
                  </div>
                  <span className={`status-dot ${analyst?.state || "idle"}`} style={{ position: "absolute", bottom: -1, right: -1, border: "2px solid var(--bg-black)" }} />
                </div>
                <div>
                  <div style={{ fontSize: "0.78rem", fontWeight: 600 }}>Analyst</div>
                  <div style={{ fontSize: "0.6rem", color: "var(--text-white-dim)", fontFamily: "'Space Mono', monospace" }}>
                    {analyst?.message || "awaiting signals"}
                  </div>
                </div>
              </div>
              <span style={{ fontSize: "0.6rem", color: "var(--text-white-dim)", fontWeight: 600, letterSpacing: "0.05em" }}>
                AUTO
              </span>
            </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════
// P&L CHART
// ═══════════════════════════════════════════════════════════════════════

function PnlChart({ pnl, history, color = "mint" }: { pnl: number; history: { time: string; value: number }[]; color?: "mint" | "lavender" }) {
  const [hovered, setHovered] = useState<number | null>(null);

  const isMint = color === "mint";
  const lineColor = isMint ? "#5ae892" : "#a78bfa";
  const fillColor = isMint ? "#8cf5b4" : "#b8a4f0";
  const gradientId = isMint ? "pnl-fill-mint" : "pnl-fill-lavender";
  const emptyBg = isMint ? "var(--mint-bg)" : "var(--lavender-bg)";
  const emptyColor = isMint ? "var(--mint-deep)" : "var(--lavender-deep)";

  // Only render the chart when we have real P&L data (more than the initial zero-point)
  if (history.length < 2) {
    return (
      <div className="flex flex-col items-center justify-center py-10 gap-3">
        <div
          className="icon-circle"
          style={{ width: 48, height: 48, background: emptyBg, border: "1px solid rgba(0,0,0,0.04)" }}
        >
          <TrendingUp className="w-5 h-5" style={{ color: emptyColor, opacity: 0.5 }} />
        </div>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontWeight: 600, fontSize: "0.82rem", color: "var(--text-dark)", marginBottom: 3 }}>
            No P&L data yet
          </div>
          <div style={{ fontSize: "0.7rem", color: "var(--text-light)" }}>
            Chart will populate as trades are executed
          </div>
        </div>
      </div>
    );
  }

  const chartData = history;

  const W = 1000;
  const H = 200;
  const PAD_L = 50;
  const PAD_R = 15;
  const PAD_T = 10;
  const PAD_B = 30;

  const chartW = W - PAD_L - PAD_R;
  const chartH = H - PAD_T - PAD_B;

  const vals = chartData.map((d) => d.value);
  const minV = Math.min(...vals, 0);
  const maxV = Math.max(...vals) * 1.1;
  const range = maxV - minV || 1;

  const points = chartData.map((d, i) => ({
    x: PAD_L + (i / (chartData.length - 1)) * chartW,
    y: PAD_T + chartH - ((d.value - minV) / range) * chartH,
    ...d,
  }));

  // Smooth bezier path
  const pathD = points.reduce((acc, p, i) => {
    if (i === 0) return `M ${p.x} ${p.y}`;
    const prev = points[i - 1];
    const cpx = (prev.x + p.x) / 2;
    return `${acc} C ${cpx} ${prev.y}, ${cpx} ${p.y}, ${p.x} ${p.y}`;
  }, "");

  // Area fill path (closes at bottom)
  const areaD = `${pathD} L ${points[points.length - 1].x} ${PAD_T + chartH} L ${points[0].x} ${PAD_T + chartH} Z`;

  // Y-axis ticks
  const yTicks = 4;
  const yLabels = Array.from({ length: yTicks + 1 }, (_, i) => {
    const val = minV + (range * i) / yTicks;
    return {
      y: PAD_T + chartH - (i / yTicks) * chartH,
      label: `$${val.toFixed(0)}`,
    };
  });

  // X-axis labels (show all for small datasets like weekly, every 4th for large)
  const xLabels = chartData.length <= 7
    ? points
    : points.filter((_, i) => i % 4 === 0 || i === points.length - 1);

  const hp = hovered !== null ? points[hovered] : null;

  return (
    <div
      style={{ position: "relative", width: "100%" }}
      onMouseLeave={() => setHovered(null)}
    >
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: "100%", height: "auto", display: "block" }}
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={fillColor} stopOpacity="0.25" />
            <stop offset="100%" stopColor={fillColor} stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {/* Grid lines */}
        {yLabels.map((yl, i) => (
          <g key={i}>
            <line
              x1={PAD_L} y1={yl.y} x2={W - PAD_R} y2={yl.y}
              stroke="rgba(0,0,0,0.04)" strokeWidth="1"
            />
            <text
              x={PAD_L - 8} y={yl.y + 3}
              textAnchor="end" fontSize="9"
              fontFamily="'Space Mono', monospace" fill="#9a9a9a"
            >
              {yl.label}
            </text>
          </g>
        ))}

        {/* X-axis labels */}
        {xLabels.map((xl, i) => (
          <text
            key={i} x={xl.x} y={H - 6}
            textAnchor="middle" fontSize="9"
            fontFamily="'Space Mono', monospace" fill="#9a9a9a"
          >
            {xl.time}
          </text>
        ))}

        {/* Area fill */}
        <path d={areaD} fill={`url(#${gradientId})`} />

        {/* Line */}
        <path
          d={pathD} fill="none"
          stroke={lineColor} strokeWidth="2.5" strokeLinecap="round"
        />

        {/* Endpoint dot */}
        <circle
          cx={points[points.length - 1].x} cy={points[points.length - 1].y}
          r="4" fill={lineColor} stroke="white" strokeWidth="2"
        />

        {/* Hover crosshair */}
        {hp && (
          <g>
            <line
              x1={hp.x} y1={PAD_T} x2={hp.x} y2={PAD_T + chartH}
              stroke="rgba(0,0,0,0.12)" strokeWidth="1" strokeDasharray="3,3"
            />
            <circle
              cx={hp.x} cy={hp.y} r="5"
              fill="#1a1a1a" stroke="white" strokeWidth="2"
            />
            {/* Tooltip */}
            <rect
              x={hp.x - 36} y={hp.y - 28}
              width="72" height="20" rx="6"
              fill="#1a1a1a"
            />
            <text
              x={hp.x} y={hp.y - 15}
              textAnchor="middle" fontSize="10" fontWeight="600"
              fontFamily="'Space Mono', monospace" fill="white"
            >
              +${hp.value.toFixed(0)}
            </text>
          </g>
        )}

        {/* Hover zones */}
        {points.map((p, i) => (
          <rect
            key={i}
            x={p.x - chartW / points.length / 2}
            y={PAD_T} width={chartW / points.length} height={chartH}
            fill="transparent" style={{ cursor: "crosshair" }}
            onMouseEnter={() => setHovered(i)}
          />
        ))}
      </svg>
    </div>
  );
}
