// Empty-state illustrations (#12): simple line drawings in the brand colours.
const STROKE = "var(--illustration-stroke)";
const ART = {
  trips: (
    <>
      <rect x="30" y="38" width="100" height="64" rx="6" fill="none" stroke={STROKE} strokeWidth="3" />
      <path d="M62 38v-10h36v10" fill="none" stroke={STROKE} strokeWidth="3" />
      <rect x="30" y="58" width="100" height="10" fill="var(--brand-bright)" />
      <path d="M128 22l14-6-4 14-10 2z" fill="var(--brand-bright)" stroke={STROKE} strokeWidth="2" />
    </>
  ),
  inbox: (
    <>
      <path d="M28 70l16-38h72l16 38v32H28z" fill="none" stroke={STROKE} strokeWidth="3" strokeLinejoin="round" />
      <path d="M28 70h32l6 12h28l6-12h32" fill="none" stroke={STROKE} strokeWidth="3" />
      <circle cx="80" cy="44" r="10" fill="var(--brand-bright)" />
      <path d="M75 44l4 4 7-8" fill="none" stroke="#022c22" strokeWidth="2.5" />
    </>
  ),
  receipt: (
    <>
      <path d="M50 18h60v86l-10-6-10 6-10-6-10 6-10-6-10 6z" fill="none" stroke={STROKE} strokeWidth="3" strokeLinejoin="round" />
      <path d="M62 38h36M62 52h36M62 66h22" stroke={STROKE} strokeWidth="3" />
      <rect x="84" y="62" width="16" height="8" fill="var(--brand-bright)" />
    </>
  ),
};

export default function Illustration({ name = "inbox" }) {
  return (
    <svg className="illustration" viewBox="0 0 160 120" width="160" height="120" aria-hidden="true">
      {ART[name] ?? ART.inbox}
    </svg>
  );
}
