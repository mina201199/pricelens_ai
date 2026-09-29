export default function Loading() {
  return (
    <div className="shell loading-page" aria-busy="true" aria-label="正在載入價格資料">
      <div className="skeleton skeleton-title" />
      <div className="skeleton skeleton-copy" />
      <div className="skeleton-grid">
        {Array.from({ length: 8 }).map((_, index) => <div className="skeleton skeleton-card" key={index} />)}
      </div>
    </div>
  );
}
