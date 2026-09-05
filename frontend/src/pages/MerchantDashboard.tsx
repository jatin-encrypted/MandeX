import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../lib/AuthContext";
import {
  getPassport,
  createPassport,
  activatePassport,
  getAuditLog,
  createMandate,
  type CommercePassport,
  type AuditEntry,
  type Mandate,
  type MerchantRules,
} from "../lib/api";
import toast from "react-hot-toast";

const DEFAULT_RULES: MerchantRules = {
  max_ai_discount_pct: 10,
  min_margin_pct: 20,
  ai_upsell_enabled: true,
  preferred_categories: [],
  require_approval_above_inr: 10000,
};

interface ProductRow {
  name: string;
  price_inr: string;
  stock: string;
  category: string;
  description: string;
  return_policy: string;
}

const EMPTY_PRODUCT: ProductRow = {
  name: "",
  price_inr: "",
  stock: "",
  category: "",
  description: "",
  return_policy: "30 days",
};

export default function MerchantDashboard() {
  const { user, logout } = useAuth();
  const [tab, setTab] = useState<"passport" | "audit" | "mandate">("passport");
  const [passport, setPassport] = useState<CommercePassport | null>(null);
  const [products, setProducts] = useState<ProductRow[]>([{ ...EMPTY_PRODUCT }]);
  const [rules, setRules] = useState<MerchantRules>(DEFAULT_RULES);
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);
  const [mandate, setMandate] = useState<Mandate | null>(null);
  const [mandateForm, setMandateForm] = useState(() => {
    // Calculate a default expiry 30 days from now in local time for the datetime-local input
    const future = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
    const offset = future.getTimezoneOffset() * 60000;
    const localIso = new Date(future.getTime() - offset).toISOString().slice(0, 16);
    return {
      buyer_id: "demo-buyer",
      max_amount_inr: "6000",
      allowed_categories: "",
      expires_at: localIso,
    };
  });
  const [loading, setLoading] = useState(false);

  // Prefer the env-configured demo merchant ID (set by seed_demo.py output).
  // Falls back to the Firebase UID for real merchants who registered via the dashboard.
  const merchantId = import.meta.env.VITE_DEMO_MERCHANT_ID || user!.uid;

  useEffect(() => {
    loadPassport();
    loadAudit();
  }, []);

  const loadPassport = async () => {
    try {
      const p = await getPassport(merchantId);
      setPassport(p);
      setProducts(p.products.map((pr) => ({
        name: pr.name,
        price_inr: String(pr.price_inr),
        stock: String(pr.stock),
        category: pr.category,
        description: pr.description,
        return_policy: pr.return_policy,
      })));
      setRules(p.rules);
    } catch {
      // no passport yet — start fresh
    }
  };

  const loadAudit = async () => {
    try {
      const entries = await getAuditLog(merchantId);
      setAuditLog(entries);
    } catch {
      // ignore
    }
  };

  const handleSavePassport = async () => {
    setLoading(true);
    try {
      const p = await createPassport(merchantId, {
        products: products.map((row) => ({
          name: row.name,
          price_inr: parseFloat(row.price_inr),
          stock: parseInt(row.stock, 10),
          category: row.category,
          description: row.description,
          return_policy: row.return_policy,
        })),
        rules,
      });
      setPassport(p);
      toast.success("Commerce Passport saved as draft.");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(typeof msg === "string" ? msg : "Validation failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleActivate = async () => {
    setLoading(true);
    try {
      const p = await activatePassport(merchantId);
      setPassport(p);
      await loadAudit();
      toast.success("Commerce Passport is now ACTIVE. Merchant is AI-buyer-ready.");
    } catch {
      toast.error("Activation failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateMandate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const m = await createMandate(merchantId, {
        buyer_id: mandateForm.buyer_id,
        max_amount_inr: parseFloat(mandateForm.max_amount_inr),
        allowed_categories: mandateForm.allowed_categories
          ? mandateForm.allowed_categories.split(",").map((s) => s.trim())
          : [],
        expires_at: new Date(mandateForm.expires_at).toISOString(),
      });
      setMandate(m);
      toast.success("Mandate created and signed.");
    } catch {
      toast.error("Failed to create mandate.");
    } finally {
      setLoading(false);
    }
  };

  const addProductRow = () => setProducts([...products, { ...EMPTY_PRODUCT }]);
  const removeProductRow = (i: number) => setProducts(products.filter((_, idx) => idx !== i));
  const updateProduct = (i: number, field: keyof ProductRow, val: string) => {
    const next = [...products];
    next[i] = { ...next[i], [field]: val };
    setProducts(next);
  };

  return (
    <div className="min-h-screen bg-ink flex">
      {/* Nav */}
      <aside className="w-52 bg-ink-raised border-r border-ink-raised/80 flex flex-col p-4 shrink-0">
        <div className="mb-8">
          <p className="text-gold text-sm font-semibold">MandeX</p>
          <p className="text-text-ink/40 text-xs mt-1 truncate">{user!.email}</p>
        </div>
        <nav className="flex flex-col gap-1 text-sm">
          {(["passport", "audit", "mandate"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`text-left px-3 py-2 transition-colors ${tab === t ? "text-gold bg-ink/50" : "text-text-ink/60 hover:text-text-ink"}`}
            >
              {t === "passport" ? "Commerce Passport" : t === "audit" ? "Audit Log" : "Mandates"}
            </button>
          ))}
        </nav>
        <Link
          to="/buyer-demo"
          className="text-sm text-text-ink/60 hover:text-text-ink px-3 py-2 transition-colors"
        >
          AI Buyer Demo
        </Link>
        <button onClick={logout} className="mt-auto text-text-ink/40 text-xs hover:text-text-ink/70 text-left">
          Sign out
        </button>
      </aside>

      {/* Content */}
      <main className="flex-1 p-8 overflow-y-auto">
        {tab === "passport" && (
          <div>
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-text-ink text-lg font-semibold">Commerce Passport</h2>
                <p className="text-text-ink/50 text-xs mt-0.5">Your AI-readable merchant profile</p>
              </div>
              {passport && (
                <span className={`text-xs px-2 py-1 border mono ${passport.status === "active" ? "border-verified text-verified" : "border-gold text-gold"}`}>
                  {passport.status.toUpperCase()}
                </span>
              )}
            </div>

            {/* Products table */}
            <div className="mb-6">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-text-ink/80 text-sm font-medium">Catalog</h3>
                <button onClick={addProductRow} className="text-xs text-gold border border-gold px-2 py-1">
                  Add product
                </button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-text-ink/80">
                  <thead>
                    <tr className="border-b border-ink-raised text-text-ink/40">
                      <th className="text-left pb-2 pr-3">Name</th>
                      <th className="text-left pb-2 pr-3">Category</th>
                      <th className="text-left pb-2 pr-3 mono">Price ₹</th>
                      <th className="text-left pb-2 pr-3 mono">Stock</th>
                      <th className="text-left pb-2 pr-3">Description</th>
                      <th className="text-left pb-2 pr-3">Return policy</th>
                      <th className="pb-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {products.map((p, i) => (
                      <tr key={i} className="border-b border-ink-raised/40">
                        {(["name", "category"] as const).map((f) => (
                          <td key={f} className="py-2 pr-3">
                            <input
                              value={p[f]}
                              onChange={(e) => updateProduct(i, f, e.target.value)}
                              className="bg-ink-raised border border-ink-raised/80 text-text-ink px-2 py-1 w-full focus:outline-none focus:border-gold text-xs"
                            />
                          </td>
                        ))}
                        {(["price_inr", "stock"] as const).map((f) => (
                          <td key={f} className="py-2 pr-3">
                            <input
                              value={p[f]}
                              onChange={(e) => updateProduct(i, f, e.target.value)}
                              type="number"
                              className="bg-ink-raised border border-ink-raised/80 text-text-ink px-2 py-1 w-24 focus:outline-none focus:border-gold text-xs mono"
                            />
                          </td>
                        ))}
                        {(["description", "return_policy"] as const).map((f) => (
                          <td key={f} className="py-2 pr-3">
                            <input
                              value={p[f]}
                              onChange={(e) => updateProduct(i, f, e.target.value)}
                              className="bg-ink-raised border border-ink-raised/80 text-text-ink px-2 py-1 w-36 focus:outline-none focus:border-gold text-xs"
                            />
                          </td>
                        ))}
                        <td className="py-2">
                          <button onClick={() => removeProductRow(i)} className="text-blocked hover:opacity-70 text-xs">✕</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Rules */}
            <div className="mb-6">
              <h3 className="text-text-ink/80 text-sm font-medium mb-3">AI Buyer Rules</h3>
              <div className="grid grid-cols-2 gap-4 max-w-lg">
                <label className="text-xs text-text-ink/60">
                  Max AI discount (%)
                  <input
                    type="number"
                    value={rules.max_ai_discount_pct}
                    onChange={(e) => setRules({ ...rules, max_ai_discount_pct: parseFloat(e.target.value) })}
                    className="mt-1 block w-full bg-ink-raised border border-ink-raised/80 text-text-ink px-2 py-1 text-xs mono focus:outline-none focus:border-gold"
                  />
                </label>
                <label className="text-xs text-text-ink/60">
                  Minimum margin (%)
                  <input
                    type="number"
                    value={rules.min_margin_pct}
                    onChange={(e) => setRules({ ...rules, min_margin_pct: parseFloat(e.target.value) })}
                    className="mt-1 block w-full bg-ink-raised border border-ink-raised/80 text-text-ink px-2 py-1 text-xs mono focus:outline-none focus:border-gold"
                  />
                </label>
                <label className="text-xs text-text-ink/60">
                  Require approval above (₹)
                  <input
                    type="number"
                    value={rules.require_approval_above_inr}
                    onChange={(e) => setRules({ ...rules, require_approval_above_inr: parseFloat(e.target.value) })}
                    className="mt-1 block w-full bg-ink-raised border border-ink-raised/80 text-text-ink px-2 py-1 text-xs mono focus:outline-none focus:border-gold"
                  />
                </label>
                <label className="text-xs text-text-ink/60 flex items-center gap-2 mt-4">
                  <input
                    type="checkbox"
                    checked={rules.ai_upsell_enabled}
                    onChange={(e) => setRules({ ...rules, ai_upsell_enabled: e.target.checked })}
                    className="accent-gold"
                  />
                  AI upsell enabled
                </label>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3">
              <button
                onClick={handleSavePassport}
                disabled={loading}
                className="text-sm px-4 py-2 bg-ink-raised border border-gold text-gold disabled:opacity-50"
              >
                Save draft
              </button>
              {passport?.status === "draft" && (
                <button
                  onClick={handleActivate}
                  disabled={loading}
                  className="text-sm px-4 py-2 bg-gold text-text-paper font-medium disabled:opacity-50"
                >
                  Activate passport
                </button>
              )}
            </div>
          </div>
        )}

        {tab === "audit" && (
          <div>
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-text-ink text-lg font-semibold">Audit Log</h2>
              <button onClick={loadAudit} className="text-xs text-text-ink/50 hover:text-text-ink">Refresh</button>
            </div>
            {auditLog.length === 0 ? (
              <p className="text-text-ink/40 text-sm">No events yet. Run a demo to populate the audit log.</p>
            ) : (
              <table className="w-full text-xs text-text-ink/80">
                <thead>
                  <tr className="border-b border-ink-raised text-text-ink/40">
                    <th className="text-left pb-2 pr-4 mono">Timestamp</th>
                    <th className="text-left pb-2 pr-4">Event</th>
                    <th className="text-left pb-2 pr-4 mono">Cart ID</th>
                    <th className="text-left pb-2">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLog.map((e) => {
                    // -----------------------------------------------------------
                    // UTC → IST conversion at render time only (stored data stays UTC)
                    // Format: "05 Sep 2026, 11:02:32 PM IST"
                    // -----------------------------------------------------------
                    // SQLite timestamps lack timezone info (e.g., "2026-09-05T17:32:32.123456").
                    // Append 'Z' to force JS to parse it as UTC, fixing the offset issue.
                    const timestampStr = e.timestamp.endsWith('Z') ? e.timestamp : `${e.timestamp}Z`;
                    const utcDate = new Date(timestampStr);
                    const istParts = new Intl.DateTimeFormat("en-IN", {
                      timeZone: "Asia/Kolkata",
                      day: "2-digit",
                      month: "short",
                      year: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                      hour12: true,
                    }).formatToParts(utcDate);

                    const p = (type: string) =>
                      istParts.find((x) => x.type === type)?.value ?? "";
                    const istStr = `${p("day")} ${p("month")} ${p("year")}, ${p("hour")}:${p("minute")}:${p("second")} ${p("dayPeriod").toUpperCase()} IST`;

                    // -----------------------------------------------------------
                    // Event colour — uses existing design tokens:
                    //   verified (green) — success events
                    //   blocked  (red)   — failure / mismatch / blocked events
                    //   gold             — neutral / in-progress events
                    // -----------------------------------------------------------
                    const eventType = e.event_type;
                    const payload = e.payload || {};
                    let eventColor = "text-gold"; // default: neutral

                    if (
                      eventType.includes("verified") ||
                      eventType === "passport_activated"
                    ) {
                      eventColor = "text-verified";
                    } else if (
                      eventType.includes("failed") ||
                      eventType.includes("mismatch") ||
                      eventType.includes("blocked") ||
                      payload.passed === false ||
                      payload.final_decision === "BLOCK"
                    ) {
                      eventColor = "text-blocked";
                    }

                    return (
                      <tr key={e.log_id} className="border-b border-ink-raised/40 align-top">
                        <td className="py-2 pr-4 mono text-text-ink/50 whitespace-nowrap">
                          {istStr}
                        </td>
                        <td className="py-2 pr-4">
                          <span className={`px-1.5 py-0.5 text-xs ${eventColor}`}>
                            {eventType}
                          </span>
                        </td>
                        <td className="py-2 pr-4 mono text-text-ink/50 text-xs">{e.cart_id?.slice(0, 8) ?? "—"}</td>
                        <td className="py-2 text-text-ink/50 mono text-xs max-w-xs truncate">
                          {JSON.stringify(e.payload)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}

        {tab === "mandate" && (
          <div className="max-w-md">
            <h2 className="text-text-ink text-lg font-semibold mb-6">Create Buyer Mandate</h2>
            <form onSubmit={handleCreateMandate} className="space-y-4">
              <label className="block text-xs text-text-ink/60">
                Buyer ID
                <input
                  value={mandateForm.buyer_id}
                  onChange={(e) => setMandateForm({ ...mandateForm, buyer_id: e.target.value })}
                  className="mt-1 block w-full bg-ink-raised border border-ink-raised/80 text-text-ink px-3 py-2 text-sm focus:outline-none focus:border-gold"
                />
              </label>
              <label className="block text-xs text-text-ink/60">
                Max amount (₹)
                <input
                  type="number"
                  value={mandateForm.max_amount_inr}
                  onChange={(e) => setMandateForm({ ...mandateForm, max_amount_inr: e.target.value })}
                  className="mt-1 block w-full bg-ink-raised border border-ink-raised/80 text-text-ink px-3 py-2 text-sm mono focus:outline-none focus:border-gold"
                />
              </label>
              <label className="block text-xs text-text-ink/60">
                Allowed categories (comma-separated, leave blank for all)
                <input
                  value={mandateForm.allowed_categories}
                  onChange={(e) => setMandateForm({ ...mandateForm, allowed_categories: e.target.value })}
                  placeholder="shoes, apparel"
                  className="mt-1 block w-full bg-ink-raised border border-ink-raised/80 text-text-ink px-3 py-2 text-sm focus:outline-none focus:border-gold"
                />
              </label>
              <label className="block text-xs text-text-ink/60">
                Expires at
                <input
                  type="datetime-local"
                  value={mandateForm.expires_at}
                  onChange={(e) => setMandateForm({ ...mandateForm, expires_at: e.target.value })}
                  className="mt-1 block w-full bg-ink-raised border border-ink-raised/80 text-text-ink px-3 py-2 text-sm mono focus:outline-none focus:border-gold"
                />
              </label>
              <button
                type="submit"
                disabled={loading}
                className="w-full bg-gold text-text-paper px-4 py-2 text-sm font-medium disabled:opacity-50"
              >
                Create mandate
              </button>
            </form>

            {mandate && (
              <div className="mt-6 bg-ink-raised p-4 text-xs mono text-text-ink/70">
                <p className="text-gold mb-2 font-medium">Mandate created</p>
                <p>ID: {mandate.mandate_id}</p>
                <p>Buyer: {mandate.buyer_id}</p>
                <p>Max: ₹{mandate.max_amount_inr.toLocaleString()}</p>
                <p>Expires: {new Date(mandate.expires_at.endsWith('Z') ? mandate.expires_at : `${mandate.expires_at}Z`).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true })}</p>
                <p className="mt-2 text-text-ink/40 break-all">Signature: {mandate.signature}</p>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
