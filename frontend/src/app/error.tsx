"use client";

import { AlertTriangle, RotateCcw } from "lucide-react";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="shell page-state-wrap">
      <div className="state-card" role="alert">
        <span><AlertTriangle size={22} aria-hidden="true" /></span>
        <h2>頁面發生未預期錯誤</h2>
        <p>已保留錯誤邊界，請再試一次；若持續發生，請檢查應用程式紀錄。</p>
        <button type="button" onClick={reset}><RotateCcw size={16} />再試一次</button>
      </div>
    </div>
  );
}
