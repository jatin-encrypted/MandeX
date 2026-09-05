import { type DecisionReceipt as DR } from "../lib/api";

interface Props {
  receipt: DR;
}

export default function DecisionReceiptView({ receipt }: Props) {
  const blocked = !!receipt.blocked_reason;

  return (
    <div className="flex justify-center px-4 py-12">
      <div className="paper-card w-full max-w-sm p-6">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="text-text-paper/50 text-xs uppercase tracking-wide">Customer request</p>
            <p className="text-text-paper font-medium mt-0.5">{receipt.customer_request || "—"}</p>
          </div>
          <div className={`stamp ${blocked ? "stamp-blocked" : "stamp-approved"}`}>
            {blocked ? "BLOCKED" : "APPROVED"}
          </div>
        </div>

        <div className="paper-rule" />

        {/* Products considered */}
        <div className="mb-4">
          <p className="text-text-paper/50 text-xs">AI considered</p>
          <p className="mono text-text-paper text-sm">{receipt.products_considered} products</p>
        </div>

        {/* Selected product */}
        <div className="mb-4">
          <p className="text-text-paper/50 text-xs">Selected</p>
          <p className="text-text-paper font-medium">{receipt.selected_product.name}</p>
          <p className="mono text-text-paper text-sm">₹{receipt.selected_product.price_inr.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</p>
        </div>

        {receipt.selection_reasons.length > 0 && (
          <div className="mb-4">
            <p className="text-text-paper/50 text-xs mb-1">Why</p>
            {receipt.selection_reasons.map((r, i) => (
              <p key={i} className="text-verified text-sm">✓ {r}</p>
            ))}
          </div>
        )}

        {/* Upsell */}
        {receipt.upsell_product && (
          <div className="mb-4 pl-3 border-l-2 border-paper-line">
            <p className="text-text-paper/50 text-xs">Upsell</p>
            <p className="text-text-paper text-sm">{receipt.upsell_product.name} — <span className="mono">₹{receipt.upsell_product.price_inr.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span></p>
            {receipt.upsell_reason && <p className="text-text-paper/50 text-xs">Why: {receipt.upsell_reason}</p>}
          </div>
        )}

        <div className="paper-rule" />

        {/* Totals */}
        <div className="flex justify-between items-center mb-4">
          <p className="text-text-paper/50 text-xs">Final total</p>
          <p className="mono text-text-paper font-medium text-base">₹{receipt.final_total_inr.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</p>
        </div>

        {/* Authorization */}
        <div className="mb-4">
          <p className="text-text-paper/50 text-xs mb-1">Authorization</p>
          <p className={`text-sm ${receipt.mandate_check_passed ? "text-verified" : "text-blocked"}`}>
            {receipt.mandate_check_passed ? "✓ Within buyer limit" : "✗ Exceeds buyer limit"}
          </p>
        </div>

        {/* Block reason */}
        {blocked && (
          <div className="bg-blocked/10 border border-blocked/30 p-3 mb-4">
            <p className="text-blocked text-xs font-medium mb-1">Blocked — reason</p>
            <p className="text-blocked/80 text-xs">{receipt.blocked_reason}</p>
            <p className="text-text-paper/40 text-xs mt-2 italic">Razorpay was never called.</p>
          </div>
        )}

        {/* Payment */}
        {!blocked && (
          <div className="mb-4">
            <p className="text-text-paper/50 text-xs mb-1">Payment</p>

            {receipt.payment_status === "payment_verified" && (
              <>
                <p className="text-verified text-sm">✓ Payment captured</p>
                {receipt.razorpay_payment_id && (
                  <p className="mono text-text-paper/50 text-xs mt-1">
                    pay_id: {receipt.razorpay_payment_id}
                  </p>
                )}
              </>
            )}

            {receipt.payment_status === "order_verified" && (
              <>
                <p className="text-gold text-sm">◎ Order confirmed — awaiting payment</p>
                <p className="text-text-paper/40 text-xs mt-1">
                  Razorpay order created and amount verified. No payment captured yet —
                  complete the checkout widget to transfer funds.
                </p>
              </>
            )}

            {receipt.payment_status === "failed" && (
              <p className="text-blocked text-sm">✗ Payment failed</p>
            )}

            {receipt.razorpay_order_id && (
              <p className="mono text-text-paper/50 text-xs mt-1">
                order_id: {receipt.razorpay_order_id}
              </p>
            )}
          </div>
        )}

        <div className="paper-rule" />
        <p className="mono text-text-paper/30 text-xs">{receipt.receipt_id}</p>
      </div>
    </div>
  );
}
