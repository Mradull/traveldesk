import { useState } from "react";
import { MessageCircle } from "lucide-react";
import ChatWindow from "./ChatWindow";

/** Round chat icon, bottom-right. Rendered ONLY by MyTripsPage. */
export default function VeraLauncher() {
  const [open, setOpen] = useState(false);
  if (open) return <ChatWindow onClose={() => setOpen(false)} />;
  return (
    <button type="button" className="vera-launcher" onClick={() => setOpen(true)} aria-label="Open Vera, the TravelDesk assistant">
      <MessageCircle size={26} aria-hidden="true" />
    </button>
  );
}
