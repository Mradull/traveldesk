import { useEffect, useRef, useState } from "react";
import { Camera, Loader2, X } from "lucide-react";
import { uploadEvidence } from "../api/evidence";
import { EVIDENCE_MAX_BYTES, EVIDENCE_TYPES } from "../utils/constants";

/**
 * Choose or take a receipt photo; it uploads at once (POST /evidence).
 * value: { evidence_id, evidence_code, original_filename, previewUrl } or null
 */
export default function EvidencePicker({ value, onChange, onUploadingChange, disabled = false, error }) {
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);

  // Free the local preview when the photo is removed or the row goes away
  useEffect(() => () => {
    if (value?.previewUrl) URL.revokeObjectURL(value.previewUrl);
  }, [value?.previewUrl]);

  async function handleFile(event) {
    const file = event.target.files?.[0];
    event.target.value = ""; // allow choosing the same file again
    if (!file) return;
    if (!EVIDENCE_TYPES.includes(file.type)) { setUploadError("Only JPEG, PNG or WEBP photos."); return; }
    if (file.size > EVIDENCE_MAX_BYTES) { setUploadError("The photo must be 5 MB or smaller."); return; }

    setUploadError(null);
    setUploading(true);
    onUploadingChange?.(true);
    try {
      const evidence = await uploadEvidence(file);
      onChange({ ...evidence, previewUrl: URL.createObjectURL(file) });
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
      onUploadingChange?.(false);
    }
  }

  if (value) {
    return (
      <div className="evidence evidence--done">
        <img src={value.previewUrl} alt={`Receipt ${value.evidence_code}`} className="evidence__thumb" />
        <div className="evidence__meta">
          <strong>{value.evidence_code}</strong>
          <span className="muted small">{value.original_filename}</span>
        </div>
        <button type="button" className="icon-btn icon-btn--muted" onClick={() => onChange(null)} disabled={disabled} aria-label="Remove photo">
          <X size={16} />
        </button>
      </div>
    );
  }

  return (
    <div className="evidence">
      <input ref={inputRef} type="file" accept={EVIDENCE_TYPES.join(",")} onChange={handleFile} hidden />
      <button type="button" className="btn btn--secondary btn--small" onClick={() => inputRef.current?.click()} disabled={disabled || uploading}>
        {uploading
          ? <><Loader2 size={16} className="spin" aria-hidden="true" /> Uploading…</>
          : <><Camera size={16} aria-hidden="true" /> Add receipt photo</>}
      </button>
      {(uploadError || error) && <span className="field__error">{uploadError || error}</span>}
    </div>
  );
}
