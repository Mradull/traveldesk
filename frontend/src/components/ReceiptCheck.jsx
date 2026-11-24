import { AlertTriangle, CheckCircle2, ImageOff, Info, Loader2, ShieldAlert, XCircle } from "lucide-react";
import { RECEIPT_CHECK_LABELS } from "../utils/constants";
import { formatDate, formatINR } from "../utils/format";

const STYLE = {
  VALID: { tone: "ok", icon: CheckCircle2, title: "Receipt verified" },
  INVALID: { tone: "warn", icon: AlertTriangle, title: "Receipt doesn't match this line" },
  INVALID_OVER: { tone: "bad", icon: XCircle, title: "This line will be rejected by the receipt check" },
  UNREADABLE: { tone: "bad", icon: ImageOff, title: "We couldn't read this receipt" },
  NOT_VERIFIED: { tone: "muted", icon: ShieldAlert, title: "Receipt couldn't be checked" },
  INCOMPLETE: { tone: "muted", icon: Info, title: "Receipt read" },
};

function ReadingLine({ reading }) {
  if (!reading || reading.status !== "READ") return null;
  const parts = [
    reading.merchant,
    reading.total_amount != null ? formatINR(reading.total_amount) : null,
    reading.receipt_date ? formatDate(reading.receipt_date) : null,
    reading.from_place && reading.to_place ? `${reading.from_place} → ${reading.to_place}` : reading.city,
  ].filter(Boolean);
  if (parts.length === 0) return null;
  return <p className="receipt-check__read">Read from receipt: {parts.join(" · ")}</p>;
}

/**
 * Box under a receipt photo with the automated check (Spec v2.1).
 * check: state from useReceiptCheck. onReplace: removes the photo so a clearer one can be added.
 */
export default function ReceiptCheck({ check, onReplace }) {
  if (check.status === "idle") return null;

  if (check.status === "checking" && !check.result) {
    return (
      <div className="receipt-check receipt-check--muted" role="status">
        <p className="receipt-check__title"><Loader2 size={16} className="spin" aria-hidden="true" /> Checking receipt…</p>
        <p className="receipt-check__text">Reading the amount, date and place from the photo. This takes a few seconds.</p>
      </div>
    );
  }

  if (check.status === "error") {
    return (
      <div className="receipt-check receipt-check--muted" role="status">
        <p className="receipt-check__title"><ShieldAlert size={16} aria-hidden="true" /> Couldn't check the receipt</p>
        <p className="receipt-check__text">{check.error?.message} It will be checked again when you submit.</p>
        <button type="button" className="btn btn--ghost btn--small" onClick={check.retry}>Try again</button>
      </div>
    );
  }

  const { result } = check;
  if (!result || result.enabled === false) return null;
  const key = result.verdict === "INVALID" && result.over_threshold ? "INVALID_OVER" : result.verdict;
  const style = STYLE[key] ?? STYLE.NOT_VERIFIED;
  const Icon = style.icon;
  const failed = (result.checks ?? []).filter((c) => c.result === "FAIL");
  const shown = result.verdict === "VALID" || result.verdict === "INCOMPLETE" ? [] : failed;

  return (
    <div className={`receipt-check receipt-check--${style.tone}`} role="status" aria-live="polite">
      <p className="receipt-check__title">
        <Icon size={16} aria-hidden="true" /> {style.title}
        {check.status === "checking" && <Loader2 size={14} className="spin receipt-check__busy" aria-label="Updating" />}
      </p>
      <ReadingLine reading={result.reading} />
      {shown.length > 0 && (
        <ul className="receipt-check__list">
          {shown.map((c) => (
            <li key={c.check}><strong>{RECEIPT_CHECK_LABELS[c.check] ?? c.check}:</strong> {c.message}</li>
          ))}
        </ul>
      )}
      {/* the title already says "Receipt verified"; only repeat the outcome when it adds something */}
      {!(result.verdict === "VALID" && !result.over_threshold) && <p className="receipt-check__text">{result.outcome}</p>}
      {result.verdict === "UNREADABLE" && onReplace && (
        <button type="button" className="btn btn--secondary btn--small" onClick={onReplace}>Replace photo</button>
      )}
      {result.verdict === "NOT_VERIFIED" && (
        <button type="button" className="btn btn--ghost btn--small" onClick={check.retry}>Try again</button>
      )}
    </div>
  );
}
