import { AlertTriangle, Database, RefreshCw } from "lucide-react";
import Link from "next/link";

export function ServiceError({ detail }: { detail?: string }) {
  return (
    <div className="state-card" role="alert">
      <span><AlertTriangle size={22} aria-hidden="true" /></span>
      <h2>價格資料暫時無法載入</h2>
      <p>{detail ?? "請確認 FastAPI 與 PostgreSQL 已啟動，再重新整理頁面。"}</p>
      <Link href="/"><RefreshCw size={16} />重新整理</Link>
    </div>
  );
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="state-card">
      <span><Database size={22} aria-hidden="true" /></span>
      <h2>{title}</h2>
      <p>{detail}</p>
    </div>
  );
}
