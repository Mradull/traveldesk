// KPI count-up (#11): numbers tick up once on load; instant with reduced motion.
import { useEffect, useState } from "react";
import { prefersReducedMotion } from "../../hooks/useMediaQuery";

export default function CountUp({ value, format = (n) => Math.round(n).toLocaleString("en-IN"), duration = 700 }) {
  const target = Number(value) || 0;
  const [shown, setShown] = useState(() => (prefersReducedMotion() || typeof requestAnimationFrame !== "function" ? target : 0));

  useEffect(() => {
    if (prefersReducedMotion() || typeof requestAnimationFrame !== "function") { setShown(target); return undefined; }
    let frame;
    const start = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      setShown(target * (1 - (1 - t) ** 3));            // ease-out
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, duration]);

  return <span aria-label={format(target)}><span aria-hidden="true">{format(shown)}</span></span>;
}
