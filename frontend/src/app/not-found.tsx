import { SearchX } from "lucide-react";
import Link from "next/link";

export default function NotFound() {
  return (
    <div className="shell page-state-wrap">
      <div className="state-card">
        <span><SearchX size={22} aria-hidden="true" /></span>
        <h1>找不到這個商品</h1>
        <p>商品可能尚未納入 canonical mapping，或沒有足夠的批發交易資料。</p>
        <Link href="/">返回價格雷達</Link>
      </div>
    </div>
  );
}
