"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Lock, Eye, EyeOff, AlertCircle, ArrowRight } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);

  // Check if already logged in
  useEffect(() => {
    fetch(`${API}/api/auth/me`, { credentials: "include" })
      .then((res) => {
        if (res.ok) router.replace("/");
        else setCheckingSession(false);
      })
      .catch(() => setCheckingSession(false));
  }, [router]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch(`${API}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
        credentials: "include",
      });

      if (res.ok) {
        router.replace("/");
      } else {
        const data = await res.json();
        setError(data.detail || "Invalid credentials");
      }
    } catch {
      setError("Unable to connect to backend");
    } finally {
      setLoading(false);
    }
  };

  if (checkingSession) {
    return (
      <div style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#0a0b0d",
      }}>
        <div style={{ color: "rgba(255,255,255,0.3)", fontSize: "0.85rem" }}>
          Checking session…
        </div>
      </div>
    );
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "#0a0b0d",
      fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
    }}>
      {/* Background gradient */}
      <div style={{
        position: "fixed", inset: 0, zIndex: 0,
        background: "radial-gradient(ellipse at 50% 0%, rgba(140,245,180,0.04) 0%, transparent 60%)",
      }} />

      <div style={{
        position: "relative", zIndex: 1,
        width: "100%", maxWidth: 400, padding: "0 24px",
      }}>
        {/* Logo / Title */}
        <div style={{ textAlign: "center", marginBottom: 40 }}>
          <div style={{
            width: 56, height: 56, borderRadius: 16,
            background: "rgba(140,245,180,0.08)",
            border: "1px solid rgba(140,245,180,0.15)",
            display: "flex", alignItems: "center", justifyContent: "center",
            margin: "0 auto 20px",
          }}>
            <Lock style={{ width: 24, height: 24, color: "#8cf5b4" }} />
          </div>
          <h1 style={{
            fontSize: "1.5rem", fontWeight: 700, color: "#fff",
            marginBottom: 6, letterSpacing: "-0.02em",
          }}>
            AlphaDesk
          </h1>
          <p style={{
            fontSize: "0.82rem", color: "rgba(255,255,255,0.35)",
          }}>
            Sign in to access the trading terminal
          </p>
        </div>

        {/* Login Card */}
        <form onSubmit={handleLogin}>
          <div style={{
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: 20,
            padding: "32px 28px",
            backdropFilter: "blur(20px)",
          }}>
            {/* Error */}
            {error && (
              <div style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "10px 14px", borderRadius: 10, marginBottom: 20,
                background: "rgba(242,92,92,0.08)",
                border: "1px solid rgba(242,92,92,0.15)",
                color: "#f25c5c", fontSize: "0.78rem", fontWeight: 500,
              }}>
                <AlertCircle style={{ width: 16, height: 16, flexShrink: 0 }} />
                {error}
              </div>
            )}

            {/* Username */}
            <div style={{ marginBottom: 16 }}>
              <label style={{
                display: "block", fontSize: "0.72rem", fontWeight: 600,
                color: "rgba(255,255,255,0.5)", marginBottom: 8,
                textTransform: "uppercase", letterSpacing: "0.08em",
              }}>
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="admin"
                autoComplete="username"
                autoFocus
                style={{
                  width: "100%", padding: "12px 16px",
                  background: "rgba(255,255,255,0.04)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 12, color: "#fff",
                  fontSize: "0.88rem", outline: "none",
                  fontFamily: "'Space Mono', monospace",
                  transition: "border-color 0.15s",
                  boxSizing: "border-box",
                }}
                onFocus={(e) => { e.target.style.borderColor = "rgba(140,245,180,0.3)"; }}
                onBlur={(e) => { e.target.style.borderColor = "rgba(255,255,255,0.08)"; }}
              />
            </div>

            {/* Password */}
            <div style={{ marginBottom: 28 }}>
              <label style={{
                display: "block", fontSize: "0.72rem", fontWeight: 600,
                color: "rgba(255,255,255,0.5)", marginBottom: 8,
                textTransform: "uppercase", letterSpacing: "0.08em",
              }}>
                Password
              </label>
              <div style={{ position: "relative" }}>
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  style={{
                    width: "100%", padding: "12px 48px 12px 16px",
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.08)",
                    borderRadius: 12, color: "#fff",
                    fontSize: "0.88rem", outline: "none",
                    fontFamily: "'Space Mono', monospace",
                    transition: "border-color 0.15s",
                    boxSizing: "border-box",
                  }}
                  onFocus={(e) => { e.target.style.borderColor = "rgba(140,245,180,0.3)"; }}
                  onBlur={(e) => { e.target.style.borderColor = "rgba(255,255,255,0.08)"; }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  style={{
                    position: "absolute", right: 12, top: "50%",
                    transform: "translateY(-50%)",
                    background: "none", border: "none", cursor: "pointer",
                    color: "rgba(255,255,255,0.3)", padding: 4,
                  }}
                >
                  {showPassword
                    ? <EyeOff style={{ width: 18, height: 18 }} />
                    : <Eye style={{ width: 18, height: 18 }} />
                  }
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading || !username || !password}
              style={{
                width: "100%", padding: "13px 20px",
                borderRadius: 12, border: "none", cursor: "pointer",
                background: loading ? "rgba(140,245,180,0.08)" : "rgba(140,245,180,0.12)",
                color: "#8cf5b4",
                fontSize: "0.82rem", fontWeight: 700,
                letterSpacing: "0.04em",
                display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                transition: "all 0.15s",
                opacity: (!username || !password) ? 0.4 : 1,
              }}
              onMouseEnter={(e) => {
                if (username && password) e.currentTarget.style.background = "rgba(140,245,180,0.18)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "rgba(140,245,180,0.12)";
              }}
            >
              {loading ? "Signing in…" : "Sign In"}
              {!loading && <ArrowRight style={{ width: 16, height: 16 }} />}
            </button>
          </div>
        </form>

        {/* Footer */}
        <p style={{
          textAlign: "center", marginTop: 24,
          fontSize: "0.68rem", color: "rgba(255,255,255,0.15)",
        }}>
          Multi-Agent Trading Terminal · AlphaDesk v0.1
        </p>
      </div>
    </div>
  );
}
