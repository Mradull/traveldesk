/** Policy rule ids the answer came from, e.g. POL-6.2 */
export default function CitationChips({ citations }) {
  return (
    <div className="citations" aria-label="Policy references">
      {citations.map((c) => (
        <span key={c.ref_id} className="citation" title={c.title}>{c.ref_id}</span>
      ))}
    </div>
  );
}
