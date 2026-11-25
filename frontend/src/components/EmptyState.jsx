import Illustration from "./ui/Illustration";

/** illustration: "trips" | "inbox" | "receipt" */
export default function EmptyState({ title, message, action, illustration = "inbox" }) {
  return (
    <div className="empty">
      <Illustration name={illustration} />
      <h2>{title}</h2>
      {message && <p>{message}</p>}
      {action}
    </div>
  );
}
