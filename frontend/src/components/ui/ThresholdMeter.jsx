// Threshold meter (#8): how close a line's amount is to its review threshold.
import { formatINR } from "../../utils/format";

export default function ThresholdMeter({ amount, threshold }) {
  const value = Number(amount);
  if (!threshold || !value || value <= 0) return null;
  const pct = Math.min(100, (value / threshold) * 100);
  const over = value > threshold;
  return (
    <div className={over ? "meter meter--over" : pct >= 80 ? "meter meter--near" : "meter"}>
      <div className="meter__track" role="meter" aria-valuemin={0} aria-valuemax={threshold} aria-valuenow={Math.min(value, threshold)}
           aria-label={`Amount compared with the ${formatINR(threshold)} review threshold`}>
        <span className="meter__bar" style={{ width: `${pct}%` }} />
      </div>
      <span className="meter__text">{over ? `${formatINR(value - threshold)} over the threshold` : `${Math.round(pct)}% of the ${formatINR(threshold)} threshold`}</span>
    </div>
  );
}
