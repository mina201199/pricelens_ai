export default function ProductLoading() {
  return (
    <div className="shell loading-page" aria-busy="true" aria-label="正在載入商品分析">
      <div className="skeleton skeleton-copy" />
      <div className="skeleton skeleton-title" />
      <div className="skeleton skeleton-panel" />
      <div className="skeleton skeleton-chart" />
    </div>
  );
}
