export default function ErrorBanner({ error, onRetry }) {
  if (!error) return null;
  const message = typeof error === "string" ? error : error.message;
  return (
    <div className="alert alert--error" role="alert">
      <div>
        <p>{message}</p>
        {error.requestId && <p className="alert__meta">Reference: {error.requestId}</p>}
      </div>
      {onRetry && (
        <button type="button" className="btn btn--secondary" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}