import { STATUS_STYLES, TICKET_STATUS_LABELS } from "../utils/constants";

export default function StatusBadge({ status }) {
  const label = TICKET_STATUS_LABELS[status] ?? status;
  const style = STATUS_STYLES[status] ?? "badge--grey";
  return <span className={`badge ${style}`}>{label}</span>;
}