import { Lock } from "lucide-react";

export default function ReadOnlyBanner({ children = "This ticket has been decided and is read-only." }) {
  return (
    <div className="alert alert--muted">
      <p><Lock size={16} aria-hidden="true" /> {children}</p>
    </div>
  );
}