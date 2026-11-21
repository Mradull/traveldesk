import { Trash2 } from "lucide-react";
import EvidencePicker from "./EvidencePicker";
import { EXPENSE_CATEGORIES } from "../utils/constants";
import { formatINR } from "../utils/format";

/** One expense line on the expense page */
export default function ExpenseLineEditor({
  index, line, onChange, onRemove, canRemove, errors, thresholds, minDate, maxDate, disabled, onUploadingChange,
}) {
  const err = (field) => errors[`expenses.${index}.${field}`];
  const set = (field) => (e) => onChange({ ...line, [field]: e.target.value });
  const threshold = thresholds?.[line.expense_type];
  const over = threshold != null && Number(line.amount) > threshold;

  return (
    <div className="card expense-line">
      <div className="expense-line__head">
        <strong>Line {index + 1}</strong>
        {canRemove && (
          <button type="button" className="icon-btn icon-btn--muted" onClick={onRemove} disabled={disabled} aria-label={`Remove line ${index + 1}`}>
            <Trash2 size={16} />
          </button>
        )}
      </div>

      <div className="expense-line__grid">
        <label className="field">
          <span>Category</span>
          <select value={line.expense_type} onChange={set("expense_type")} disabled={disabled} aria-invalid={Boolean(err("expense_type"))}>
            <option value="">Choose…</option>
            {EXPENSE_CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
          {err("expense_type") && <span className="field__error">{err("expense_type")}</span>}
        </label>

        <label className="field">
          <span>Amount (₹)</span>
          <input
            type="number" min="0.01" step="0.01" inputMode="decimal" value={line.amount} onChange={set("amount")}
            disabled={disabled} aria-invalid={Boolean(err("amount"))}
          />
          {err("amount") && <span className="field__error">{err("amount")}</span>}
          {!err("amount") && threshold != null && (
            <span className={over ? "field__warn" : "hint"}>
              {over ? `Above the ${formatINR(threshold)} review threshold: this ticket will go to your manager.` : `Review above ${formatINR(threshold)}`}
            </span>
          )}
        </label>

        <label className="field">
          <span>Expense date</span>
          <input
            type="date" value={line.expense_date} min={minDate} max={maxDate} onChange={set("expense_date")}
            disabled={disabled} aria-invalid={Boolean(err("expense_date"))}
          />
          {err("expense_date") && <span className="field__error">{err("expense_date")}</span>}
        </label>

        <label className="field">
          <span>Invoice number <small className="muted">(optional)</small></span>
          <input
            value={line.invoice_number} onChange={set("invoice_number")} placeholder="e.g. INV-88231"
            disabled={disabled} aria-invalid={Boolean(err("invoice_number"))}
          />
          {err("invoice_number") && <span className="field__error">{err("invoice_number")}</span>}
        </label>

        <label className="field expense-line__wide">
          <span>Description</span>
          <input
            value={line.description} onChange={set("description")} maxLength={300} placeholder="e.g. Hotel, 3 nights"
            disabled={disabled} aria-invalid={Boolean(err("description"))}
          />
          {err("description") && <span className="field__error">{err("description")}</span>}
        </label>

        <div className="field expense-line__wide">
          <span>Receipt photo <small className="muted">(required)</small></span>
          <EvidencePicker
            value={line.evidence}
            onChange={(evidence) => onChange({ ...line, evidence })}
            onUploadingChange={onUploadingChange}
            disabled={disabled}
            error={err("evidence_id")}
          />
        </div>
      </div>
    </div>
  );
}
