import { useState } from "react";
import EvidenceThumbnail from "./EvidenceThumbnail";
import ReceiptLightbox from "./ReceiptLightbox";
import PolicyFlagList from "./PolicyFlagList";
import { EXPENSE_CATEGORIES, RECEIPT_CHECK_LABELS } from "../utils/constants";
import { formatDate, formatINR } from "../utils/format";

const categoryLabel = (value) => EXPENSE_CATEGORIES.find((c) => c.value === value)?.label ?? value;

/** Expense lines of a ticket with photos and flags (employee and manager pages) */
const VERDICT_BADGE = {
  VALID: ["badge--green", "Receipt verified"],
  INVALID: ["badge--red", "Receipt mismatch"],
  NOT_VERIFIED: ["badge--grey", "Receipt not verified"],
};

/** Automated receipt check result frozen with the line (Spec v2.1); nothing for older lines */
function ReceiptResult({ line }) {
  if (!line.receipt_verdict) return null;
  const [cls, label] = VERDICT_BADGE[line.receipt_verdict] ?? VERDICT_BADGE.NOT_VERIFIED;
  const failed = (line.receipt_checks ?? []).filter((c) => c.result === "FAIL");
  return (
    <div className="receipt-result">
      <span className={`badge ${cls}`}>{label}</span>
      {line.receipt_summary && <p className="receipt-result__summary">AI summary: {line.receipt_summary}</p>}
      {failed.length > 0 && (
        <ul className="receipt-result__fails">
          {failed.map((c) => <li key={c.check}><strong>{RECEIPT_CHECK_LABELS[c.check] ?? c.check}:</strong> {c.message}</li>)}
        </ul>
      )}
    </div>
  );
}

export default function TicketLines({ expenses }) {
  const [open, setOpen] = useState(null);   // index of the line shown in the lightbox
  return (
    <>
    <div className="table-wrap">
      <table className="table ticket-lines">
        <thead>
          <tr>
            <th>Photo</th><th>Expense</th><th>Category</th><th>Date</th>
            <th>Description</th><th className="num">Amount</th><th>Policy flags</th>
          </tr>
        </thead>
        <tbody>
          {expenses.map((l) => (
            <tr key={l.expense_id}>
              <td>
                <EvidenceThumbnail evidenceId={l.evidence_id} evidenceCode={l.evidence_code} onOpen={() => setOpen(expenses.indexOf(l))} />
                <div className="muted small">{l.evidence_code}</div>
              </td>
              <td>
                {l.expense_code}
                {l.invoice_number && <div className="muted small">Inv. {l.invoice_number}</div>}
              </td>
              <td>{categoryLabel(l.expense_type)}</td>
              <td>{formatDate(l.expense_date)}</td>
              <td className="cell-wrap">
                {l.description}
                <ReceiptResult line={l} />
              </td>
              <td className="num">{formatINR(l.amount)}</td>
              <td className="cell-wrap">
                {l.flags.length > 0 ? <PolicyFlagList flags={l.flags} /> : <span className="muted">None</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    {open !== null && <ReceiptLightbox lines={expenses} index={open} onIndex={setOpen} onClose={() => setOpen(null)} />}
    </>
  );
}
