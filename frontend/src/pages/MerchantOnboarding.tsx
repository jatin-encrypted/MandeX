import React, { useState } from "react";
import { useAuth } from "../lib/AuthContext";
import { useNavigate, Link } from "react-router-dom";

export default function MerchantOnboarding() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, displayName);
      }
      navigate("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-ink flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8">
          <h1 className="text-text-ink text-2xl font-semibold">AI Commerce Gateway</h1>
          <p className="text-text-ink/60 text-sm mt-1">Merchant portal — MandeX</p>
        </div>

        <div className="flex gap-2 mb-6">
          <button
            className={`text-sm px-3 py-1.5 border transition-colors ${mode === "login" ? "border-gold text-gold" : "border-ink-raised text-text-ink/50 hover:border-text-ink/30"}`}
            onClick={() => setMode("login")}
          >
            Sign in
          </button>
          <button
            className={`text-sm px-3 py-1.5 border transition-colors ${mode === "register" ? "border-gold text-gold" : "border-ink-raised text-text-ink/50 hover:border-text-ink/30"}`}
            onClick={() => setMode("register")}
          >
            Create account
          </button>
        </div>

        <form onSubmit={submit} className="space-y-4">
          {mode === "register" && (
            <div>
              <label className="block text-xs text-text-ink/60 mb-1">Business name</label>
              <input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="w-full bg-ink-raised border border-ink-raised text-text-ink px-3 py-2 text-sm focus:outline-none focus:border-gold"
                required
              />
            </div>
          )}
          <div>
            <label className="block text-xs text-text-ink/60 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-ink-raised border border-ink-raised text-text-ink px-3 py-2 text-sm focus:outline-none focus:border-gold"
              required
            />
          </div>
          <div>
            <label className="block text-xs text-text-ink/60 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-ink-raised border border-ink-raised text-text-ink px-3 py-2 text-sm focus:outline-none focus:border-gold"
              required
            />
          </div>

          {error && <p className="text-blocked text-xs">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-gold text-text-paper px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            {loading ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        {/* AI Buyer Demo link — visible without login */}
        <div className="mt-8 pt-6 border-t border-ink-raised/60 text-center">
          <Link
            to="/buyer-demo"
            className="text-xs text-gold hover:text-gold/70 transition-colors"
          >
            AI Buyer Demo
          </Link>
          <p className="text-text-ink/30 text-xs mt-1">No login required</p>
        </div>
      </div>
    </div>
  );
}
