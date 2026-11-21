import { Link } from "react-router-dom";
import StatusBadge from "./StatusBadge";
import { formatDateTime, formatINR } from "../utils/format";

/** Tickets of one trip. linkBase: "/tickets" for employees, "/manager/tickets" for managers. */
export default function TicketList({ tickets, linkBase = "/tickets" }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Ticket</th>
            <th>Status</th>
            <th className="num">Lines</th>
            <th className="num">Flags</th>
            <th className="num">Total</th>
            <th>Submitted</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={t.ticket_id}>
              <td><Link to={`${linkBase}/${t.ticket_id}`}>{t.ticket_code}</Link></td>
              <td><StatusBadge status={t.status} /></td>
              <td className="num">{t.line_count}</td>
              <td className="num">{t.flag_count > 0 ? <span className="flag-count">{t.flag_count}</span> : 0}</td>
              <td className="num">{formatINR(t.total_amount)}</td>
              <td>{formatDateTime(t.submitted_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
