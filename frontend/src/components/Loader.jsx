/** Skeleton placeholder while data loads; the label is read by screen readers */
export default function Loader({ label = "Loading…" }) {
  return (
    <div className="loader" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      <span className="skeleton skeleton--title" aria-hidden="true" />
      <span className="skeleton skeleton--card" aria-hidden="true" />
      <span className="skeleton" style={{ width: "85%" }} aria-hidden="true" />
      <span className="skeleton" style={{ width: "60%" }} aria-hidden="true" />
    </div>
  );
}
