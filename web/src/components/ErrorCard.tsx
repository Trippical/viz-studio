export function ErrorCard({ id, reason }: { id: string; reason: string }) {
  return (
    <div className="error-card" role="alert">
      <div className="error-id">{id}</div>
      <div>{reason}</div>
    </div>
  );
}
