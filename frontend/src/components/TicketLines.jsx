import EvidenceThumbnail from "./EvidenceThumbnail";
import PolicyFlagList from "./PolicyFlagList";
import { EXPENSE_CATEGORIES } from "../utils/constants";
import { formatDate, formatINR } from "../utils/format";

const categoryLabel = (value) => EXPENSE_CATEGORIES.find((c) => c.value === value)?.label ?? value;

/** Expense lines of a ticket with photos and flags (employee and manager pages) */
export default function TicketLines({ expenses }) {
  return (
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
                <EvidenceThumbnail evidenceId={l.evidence_id} evidenceCode={l.evidence_code} />
                <div className="muted small">{l.evidence_code}</div>
              </td>
              <td>
                {l.expense_code}
                {l.invoice_number && <div className="muted small">Inv. {l.invoice_number}</div>}
              </td>
              <td>{categoryLabel(l.expense_type)}</td>
              <td>{formatDate(l.expense_date)}</td>
              <td className="cell-wrap">{l.description}</td>
              <td className="num">{formatINR(l.amount)}</td>
              <td className="cell-wrap">
                {l.flags.length > 0 ? <PolicyFlagList flags={l.flags} /> : <span className="muted">None</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
