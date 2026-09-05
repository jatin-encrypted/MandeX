import axios from "axios";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const api = axios.create({ baseURL: BASE, timeout: 30000 });

// ---- Types ----
export interface Product {
  id: string;
  name: string;
  price_inr: number;
  stock: number;
  category: string;
  description: string;
  return_policy: string;
}

export interface MerchantRules {
  max_ai_discount_pct: number;
  min_margin_pct: number;
  ai_upsell_enabled: boolean;
  preferred_categories: string[];
  require_approval_above_inr: number;
}

export interface CommercePassport {
  merchant_id: string;
  products: Product[];
  rules: MerchantRules;
  status: "draft" | "active";
  created_at: string;
  activated_at: string | null;
}

export interface Mandate {
  mandate_id: string;
  buyer_id: string;
  max_amount_inr: number;
  allowed_categories: string[];
  expires_at: string;
  issued_at: string;
  signature: string;
}

export interface Cart {
  cart_id: string;
  merchant_id: string;
  mandate_id: string;
  items: CartItem[];
  upsell_items: CartItem[];
  total_inr: number;
  idempotency_key: string;
}

export interface CartItem {
  product_id: string;
  quantity: number;
  unit_price_inr: number;
}

export interface PolicyDecision {
  cart_id: string;
  mandate_check_passed: boolean;
  mandate_check_reason: string;
  policy_check_passed: boolean;
  policy_check_reason: string;
  final_decision: "APPROVE" | "BLOCK";
  decided_at: string;
}

export interface DecisionReceipt {
  receipt_id: string;
  cart_id: string;
  customer_request: string;
  products_considered: number;
  selected_product: Product;
  selection_reasons: string[];
  upsell_product: Product | null;
  upsell_reason: string | null;
  final_total_inr: number;
  mandate_check_passed: boolean;
  payment_status: "not_attempted" | "order_verified" | "payment_verified" | "failed";
  razorpay_order_id: string | null;
  razorpay_payment_id: string | null;
  blocked_reason: string | null;
  created_at: string | null;
}

export interface AuditEntry {
  log_id: string;
  event_type: string;
  merchant_id: string;
  cart_id: string | null;
  payload: Record<string, unknown>;
  timestamp: string;
}

// ---- Merchant ----
export const registerMerchant = (data: { merchant_id: string; email: string; display_name: string }) =>
  api.post("/merchant/register", data).then((r) => r.data);

export const createPassport = (merchantId: string, data: { products: Omit<Product, "id">[]; rules: MerchantRules }) =>
  api.post<CommercePassport>(`/merchant/${merchantId}/passport`, data).then((r) => r.data);

export const getPassport = (merchantId: string) =>
  api.get<CommercePassport>(`/merchant/${merchantId}/passport`).then((r) => r.data);

export const activatePassport = (merchantId: string) =>
  api.post<CommercePassport>(`/merchant/${merchantId}/passport/activate`).then((r) => r.data);

export const getAuditLog = (merchantId: string) =>
  api.get<AuditEntry[]>(`/merchant/${merchantId}/audit`).then((r) => r.data);

export const createMandate = (
  merchantId: string,
  data: { buyer_id: string; max_amount_inr: number; allowed_categories: string[]; expires_at: string }
) => api.post<Mandate>(`/merchant/${merchantId}/mandates`, data).then((r) => r.data);

// ---- MCP Tools ----
export const searchCatalog = (merchantId: string, query: string, maxPrice?: number) =>
  api.post<Product[]>("/mcp/search_catalog", { merchant_id: merchantId, query, max_price: maxPrice }).then((r) => r.data);

export const buildCart = (data: { merchant_id: string; mandate_id: string; product_id: string; quantity?: number; customer_request?: string }) =>
  api.post<Cart>("/mcp/build_cart", data).then((r) => r.data);

export const checkPolicy = (cartId: string) =>
  api.post<PolicyDecision>("/mcp/check_policy", { cart_id: cartId }).then((r) => r.data);

export const checkout = (data: { cart_id: string; customer_request: string; products_considered: number; selection_reasons: string[] }) =>
  api.post<DecisionReceipt>("/mcp/checkout", data).then((r) => r.data);

export const getReceiptByCart = (cartId: string) =>
  api.get<DecisionReceipt>(`/receipts/by-cart/${cartId}`).then((r) => r.data);

// ---- Razorpay ----
export const getRazorpayPublicKey = () =>
  api.get<{ key_id: string }>("/mcp/razorpay_public_key").then((r) => r.data);

export interface RazorpayCallbackPayload {
  cart_id: string;
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
}

export interface RazorpayCallbackResponse {
  payment_status: string;
  razorpay_payment_id: string;
  razorpay_order_id: string;
  receipt_id: string | null;
}

export const verifyRazorpayPayment = (data: RazorpayCallbackPayload) =>
  api.post<RazorpayCallbackResponse>("/mcp/razorpay_callback", data).then((r) => r.data);
