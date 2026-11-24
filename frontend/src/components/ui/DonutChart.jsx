// Donut chart (#6): share of spend per category, with a legend that also works without colour.
// CSS variables, so the second colour flips in dark mode (charcoal -> light grey)
const PALETTE = ["var(--ey-yellow)", "var(--contrast)", "#8a8a96", "#c4c4cd", "#a88f00"];

export default function DonutChart({ data, label, format }) {
  const total = data.reduce((s, d) => s + d.value, 0);
  if (!total) return null;
  const r = 52, c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <figure className="donut">
      <svg viewBox="0 0 140 140" role="img" aria-label={`${label}: ${data.map((d) => `${d.label} ${Math.round((d.value / total) * 100)}%`).join(", ")}`}>
        <circle cx="70" cy="70" r={r} fill="none" stroke="var(--grey-bg)" strokeWidth="22" />
        {data.map((d, i) => {
          const len = (d.value / total) * c;
          const seg = (
            <circle key={d.label} cx="70" cy="70" r={r} fill="none" style={{ stroke: PALETTE[i % PALETTE.length] }} strokeWidth="22"
                    strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-offset} transform="rotate(-90 70 70)" />
          );
          offset += len;
          return seg;
        })}
        <text x="70" y="66" textAnchor="middle" className="donut__total">{format(total)}</text>
        <text x="70" y="84" textAnchor="middle" className="donut__caption">total</text>
      </svg>
      <figcaption>
        <ul className="donut__legend">
          {data.map((d, i) => (
            <li key={d.label}>
              <span className="donut__swatch" style={{ background: PALETTE[i % PALETTE.length] }} aria-hidden="true" />
              <span>{d.label}</span>
              <span className="donut__value">{format(d.value)} · {Math.round((d.value / total) * 100)}%</span>
            </li>
          ))}
        </ul>
      </figcaption>
    </figure>
  );
}
