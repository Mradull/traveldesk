import { useEffect, useRef, useState } from "react";
import { verifyReceipt } from "../api/evidence";
import { MAX_LINE_AMOUNT_INR, RECEIPT_VERIFY_DEBOUNCE_MS } from "../utils/constants";

/** Amount the API accepts, or null while the field is empty or not yet valid */
function cleanAmount(value) {
  if (value === "" || value == null || !/^\d+(\.\d{1,2})?$/.test(String(value))) return null;
  const n = Number(value);
  return n > 0 && n <= MAX_LINE_AMOUNT_INR ? n : null;
}

/**
 * Receipt check for one expense line (Spec v2.1).
 * Runs when a photo is attached and again, debounced, when category / amount / date change.
 * The first call reads the receipt with AI (a few seconds); later calls only re-compare.
 * Returns { status: "idle" | "checking" | "done" | "error", result?, error?, retry }.
 */
export function useReceiptCheck({ tripId, evidenceId, expenseType, amount, expenseDate }) {
  const [state, setState] = useState({ status: "idle" });
  const [nonce, setNonce] = useState(0);
  const latest = useRef(0);
  const cleaned = cleanAmount(amount);

  useEffect(() => {
    if (!evidenceId) {
      setState({ status: "idle" });
      return undefined;
    }
    const call = ++latest.current;
    setState((s) => ({ ...s, status: "checking" }));
    const timer = setTimeout(async () => {
      try {
        const result = await verifyReceipt(evidenceId, {
          trip_id: Number(tripId),
          expense_type: expenseType || null,
          amount: cleaned,
          expense_date: expenseDate || null,
        });
        if (call === latest.current) setState({ status: "done", result });
      } catch (error) {
        if (call === latest.current) setState({ status: "error", error });
      }
    }, RECEIPT_VERIFY_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [tripId, evidenceId, expenseType, cleaned, expenseDate, nonce]);

  return { ...state, retry: () => setNonce((n) => n + 1) };
}

/** One word per state, used by the page to decide whether Submit is allowed */
export function receiptStatusKey(check) {
  if (check.status === "idle") return "none";
  if (check.status === "checking") return "checking";
  if (check.status === "error") return "error";
  if (check.result?.enabled === false) return "none";
  return check.result.verdict === "INVALID" && check.result.over_threshold ? "INVALID_OVER" : check.result.verdict;
}
