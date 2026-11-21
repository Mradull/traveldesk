import { FLAG_LABELS } from "../utils/constants";

/**
 * <PolicyFlagList codes={["OVER_THRESHOLD"]} compact />  -> badges only (tables)
 * <PolicyFlagList flags={line.flags} />                   -> badge + message + [POL-x.y]
 */
export default function PolicyFlagList({ flags = [], codes, compact = false }) {
  const items = codes ? codes.map((c) => ({ rule_code: c })) : flags;

  if (items.length === 0) {
    return compact ? <span className="muted">None</span> : <p className="muted">No policy flags.</p>;
  }

  if (compact) {
    return (
      <span className="flag-badges">
        {items.map((f) => (
          <span key={f.rule_code} className="badge badge--amber">{FLAG_LABELS[f.rule_code] ?? f.rule_code}</span>
        ))}
      </span>
    );
  }

  return (
    <ul className="flag-list">
      {items.map((f, i) => (
        <li key={`${f.rule_code}-${i}`}>
          <span className="badge badge--amber">{FLAG_LABELS[f.rule_code] ?? f.rule_code}</span>
          <span>{f.message}</span>
          {f.policy_ref && <span className="muted">{f.policy_ref}</span>}
        </li>
      ))}
    </ul>
  );
}
