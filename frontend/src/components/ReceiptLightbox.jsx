// Receipt lightbox (#4): the photo large, next to what the AI read and each check's result.
import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, ImageOff, X } from "lucide-react";
import { getEvidenceObjectUrl } from "../api/evidence";
import { EXPENSE_CATEGORIES, RECEIPT_CHECK_LABELS, USE_MOCKS } from "../utils/constants";
import { formatDate, formatINR } from "../utils/format";
import PolicyFlagList from "./PolicyFlagList";

const categoryLabel = (v) => EXPENSE_CATEGORIES.find((c) => c.value === v)?.label ?? v;
const RESULT_TEXT = { PASS: "Pass", FAIL: "Fail", NOT_ON_RECEIPT: "Not on receipt", MISSING_INPUT: "Missing", NOT_CHECKED: "Not checked" };
const VERDICT = {
  VALID: ["badge--green", "Receipt verified"],
  INVALID: ["badge--red", "Receipt mismatch"],
  NOT_VERIFIED: ["badge--grey", "Receipt not verified"],
};

function Photo({ evidenceId, code }) {
  const [state, setState] = useState({ url: null, status: "loading" });
  useEffect(() => {
    let cancelled = false, created = null;
    setState({ url: null, status: "loading" });
    getEvidenceObjectUrl(evidenceId)
      .then((u) => { if (!cancelled) { created = u; setState({ url: u, status: u ? "ready" : "missing" }); } })
      .catch(() => { if (!cancelled) setState({ url: null, status: "error" }); });
    return () => { cancelled = true; if (created && !USE_MOCKS) URL.revokeObjectURL(created); };
  }, [evidenceId]);
  if (state.status === "loading") return <div className="lightbox__placeholder skeleton" />;
  if (state.status !== "ready") return <div className="lightbox__placeholder"><ImageOff size={40} aria-hidden="true" /><p>Photo not available</p></div>;
  return <img className="lightbox__img" src={state.url} alt={`Receipt ${code}`} />;
}

export default function ReceiptLightbox({ lines, index, onIndex, onClose }) {
  const line = lines[index];
  const closeRef = useRef(null);

  useEffect(() => {
    const previous = document.activeElement;
    closeRef.current?.focus();
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight" && index < lines.length - 1) onIndex(index + 1);
      if (e.key === "ArrowLeft" && index > 0) onIndex(index - 1);
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); previous?.focus?.(); };
  }, [index, lines.length, onClose, onIndex]);

  const [cls, label] = VERDICT[line.receipt_verdict] ?? [];
  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="lightbox" role="dialog" aria-modal="true" aria-label={`Receipt ${line.evidence_code}`}>
        <div className="lightbox__photo">
          <Photo evidenceId={line.evidence_id} code={line.evidence_code} />
        </div>
        <aside className="lightbox__panel">
          <div className="lightbox__head">
            <div>
              <p className="trip-card__code">{line.expense_code} · {line.evidence_code}</p>
              <h2>{categoryLabel(line.expense_type)} · {formatINR(line.amount)}</h2>
              <p className="muted small">{formatDate(line.expense_date)} · {line.description}</p>
            </div>
            <button ref={closeRef} type="button" className="icon-btn icon-btn--muted" onClick={onClose} aria-label="Close"><X size={20} /></button>
          </div>

          {line.receipt_verdict ? (
            <>
              <span className={`badge ${cls}`}>{label}</span>
              {line.receipt_summary && <p className="lightbox__summary"><strong>AI summary:</strong> {line.receipt_summary}</p>}
              {line.receipt_checks?.length > 0 && (
                <ul className="check-list">
                  {line.receipt_checks.map((c) => (
                    <li key={c.check} className={`check-list__item check-list__item--${c.result.toLowerCase()}`}>
                      <span className="check-list__name">{RECEIPT_CHECK_LABELS[c.check] ?? c.check}</span>
                      <span className="check-list__result">{RESULT_TEXT[c.result] ?? c.result}</span>
                      <span className="check-list__msg">{c.message}</span>
                    </li>
                  ))}
                </ul>
              )}
              {line.receipt_ai_generated_score != null && (
                <p className="muted small">AI-generated image likelihood: {Math.round(line.receipt_ai_generated_score * 100)}%</p>
              )}
            </>
          ) : (
            <p className="muted">This line was submitted before receipt checking was switched on.</p>
          )}

          {line.flags?.length > 0 && (<><h3 className="lightbox__sub">Policy flags</h3><PolicyFlagList flags={line.flags} /></>)}

          {lines.length > 1 && (
            <div className="lightbox__nav">
              <button type="button" className="btn btn--secondary btn--small" onClick={() => onIndex(index - 1)} disabled={index === 0}>
                <ChevronLeft size={16} aria-hidden="true" /> Previous
              </button>
              <span className="muted small">{index + 1} of {lines.length}</span>
              <button type="button" className="btn btn--secondary btn--small" onClick={() => onIndex(index + 1)} disabled={index === lines.length - 1}>
                Next <ChevronRight size={16} aria-hidden="true" />
              </button>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
