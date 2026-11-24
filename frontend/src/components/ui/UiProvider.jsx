// Toasts (#1) and confirmation dialogs (#2), shared by every page.
// useToast()("Ticket submitted")  ·  await useConfirm()({ title, message, confirmLabel, tone })
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";

const UiContext = createContext(null);
const ICONS = { success: CheckCircle2, error: XCircle, info: Info, warning: AlertTriangle };
let nextToastId = 0;

function ConfirmDialog({ dialog, onClose }) {
  const confirmRef = useRef(null);
  const previousFocus = useRef(null);

  useEffect(() => {
    previousFocus.current = document.activeElement;
    confirmRef.current?.focus();
    const onKey = (e) => { if (e.key === "Escape") onClose(false); };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previousFocus.current?.focus?.();
    };
  }, [onClose]);

  const danger = dialog.tone === "danger";
  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(false); }}>
      <div className="modal" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-message">
        <div className={danger ? "modal__icon modal__icon--danger" : "modal__icon"} aria-hidden="true">
          {danger ? <AlertTriangle size={22} /> : <Info size={22} />}
        </div>
        <h2 id="confirm-title">{dialog.title}</h2>
        <div id="confirm-message" className="modal__message">{dialog.message}</div>
        <div className="form-actions">
          <button type="button" className="btn btn--secondary" onClick={() => onClose(false)}>
            {dialog.cancelLabel ?? "Cancel"}
          </button>
          <button ref={confirmRef} type="button" className={danger ? "btn btn--danger-solid" : "btn btn--primary"} onClick={() => onClose(true)}>
            {dialog.confirmLabel ?? "Confirm"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function UiProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const [dialog, setDialog] = useState(null);

  const dismiss = useCallback((id) => setToasts((list) => list.filter((t) => t.id !== id)), []);

  const toast = useCallback((message, { tone = "success", duration = 4000 } = {}) => {
    const id = ++nextToastId;
    setToasts((list) => [...list.slice(-3), { id, message, tone }]);   // at most 4 on screen
    if (duration) setTimeout(() => dismiss(id), duration);
  }, [dismiss]);

  const confirm = useCallback((options) => new Promise((resolve) => {
    setDialog({ ...options, resolve });
  }), []);

  const closeDialog = useCallback((answer) => {
    setDialog((d) => { d?.resolve(answer); return null; });
  }, []);

  return (
    <UiContext.Provider value={{ toast, confirm }}>
      {children}
      <div className="toasts" role="region" aria-label="Notifications" aria-live="polite">
        {toasts.map((t) => {
          const Icon = ICONS[t.tone] ?? Info;
          return (
            <div key={t.id} className={`toast toast--${t.tone}`} role={t.tone === "error" ? "alert" : "status"}>
              <Icon size={18} aria-hidden="true" />
              <span>{t.message}</span>
              <button type="button" className="toast__close" onClick={() => dismiss(t.id)} aria-label="Dismiss">
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
      {dialog && <ConfirmDialog dialog={dialog} onClose={closeDialog} />}
    </UiContext.Provider>
  );
}

// Fallbacks keep components usable outside the provider (e.g. in isolated tests)
const FALLBACK = { toast: () => {}, confirm: async () => true };
export const useToast = () => (useContext(UiContext) ?? FALLBACK).toast;
export const useConfirm = () => (useContext(UiContext) ?? FALLBACK).confirm;
