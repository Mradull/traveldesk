import { useEffect, useState } from "react";
import { ImageOff } from "lucide-react";
import { getEvidenceObjectUrl } from "../api/evidence";
import { USE_MOCKS } from "../utils/constants";

/** Loads a receipt photo through the API (it needs the auth header) and opens it full size on click */
/** onOpen: when given, clicking opens the receipt lightbox instead of a new tab */
export default function EvidenceThumbnail({ evidenceId, evidenceCode, onOpen }) {
  const [url, setUrl] = useState(null);
  const [state, setState] = useState("loading"); // loading | ready | missing | error

  useEffect(() => {
    let cancelled = false;
    let created = null;
    // In mock mode the URL belongs to the mock store, so we must not revoke it
    const release = (u) => { if (u && !USE_MOCKS) URL.revokeObjectURL(u); };

    getEvidenceObjectUrl(evidenceId)
      .then((u) => {
        if (cancelled) { release(u); return; }
        created = u;
        setUrl(u);
        setState(u ? "ready" : "missing");
      })
      .catch(() => { if (!cancelled) setState("error"); });

    return () => { cancelled = true; release(created); };
  }, [evidenceId]);

  if (state === "loading") return <span className="evidence-thumb evidence-thumb--empty" aria-label="Loading photo" />;
  if (state !== "ready" && onOpen) {
    // No photo to show, but the lightbox still has the receipt check details
    return (
      <button type="button" className="evidence-thumb evidence-thumb--empty" onClick={onOpen} title={`View ${evidenceCode} details`}>
        <ImageOff size={18} aria-hidden="true" />
      </button>
    );
  }
  if (state !== "ready") {
    return (
      <span
        className="evidence-thumb evidence-thumb--empty"
        title={state === "missing" ? "Photo not available (seed data in mock mode)" : "Couldn't load the photo"}
      >
        <ImageOff size={18} aria-hidden="true" />
      </span>
    );
  }
  if (onOpen) {
    return (
      <button type="button" className="evidence-thumb" onClick={onOpen} title={`View ${evidenceCode} with the receipt check`}>
        <img src={url} alt={`Receipt ${evidenceCode}`} />
      </button>
    );
  }
  return (
    <a href={url} target="_blank" rel="noreferrer" className="evidence-thumb" title={`Open ${evidenceCode} full size`}>
      <img src={url} alt={`Receipt ${evidenceCode}`} />
    </a>
  );
}
