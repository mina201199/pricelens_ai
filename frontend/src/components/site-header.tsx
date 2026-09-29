import { ScanSearch } from "lucide-react";
import Link from "next/link";

export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="shell header-inner">
        <Link className="brand" href="/" aria-label="Price Lens 首頁">
          <span className="brand-mark" aria-hidden="true">
            <ScanSearch size={22} strokeWidth={2.2} />
          </span>
          <span>
            <strong>Price Lens</strong>
            <small>民生物價雷達</small>
          </span>
        </Link>
        <nav className="main-nav" aria-label="主要導覽">
          <Link href="/#radar">價格雷達</Link>
          <Link href="/#movers">本週漲跌</Link>
          <Link href="/#ai-search">AI Search</Link>
        </nav>
        <span className="source-pill">農業部官方資料</span>
      </div>
    </header>
  );
}
