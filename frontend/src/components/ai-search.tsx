"use client";

import { ArrowRight, CalendarDays, Database, LoaderCircle, Search, Sparkles } from "lucide-react";
import { FormEvent, useState } from "react";

import type { AskResponse } from "@/lib/types";

const examples = [
  "高麗菜現在算貴嗎？",
  "番茄最近漲多少？",
  "哪些菜本週變便宜？",
  "哪個商品最貴？",
];

export function AiSearch() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function ask(value: string) {
    const normalized = value.trim();
    setAnswer(null);
    setError("");
    if (!normalized) {
      setError("請先輸入想查詢的商品或價格問題。");
      return;
    }
    setIsLoading(true);
    try {
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: normalized }),
      });
      if (!response.ok) {
        throw new Error("價格問答服務暫時無法回應。");
      }
      setAnswer((await response.json()) as AskResponse);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "查詢失敗，請稍後再試。");
    } finally {
      setIsLoading(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void ask(question);
  }

  return (
    <section className="ai-search-card" id="ai-search" aria-labelledby="ai-search-title">
      <div className="ai-search-copy">
        <span className="feature-icon"><Sparkles size={19} aria-hidden="true" /></span>
        <p className="eyebrow">CONTROLLED AI SEARCH</p>
        <h2 id="ai-search-title">直接問你真正想知道的問題</h2>
        <p>常見問題走固定分析工具，探索式問題只讀取受控語意資料；沒有官方文件時不猜測價格原因。</p>
      </div>
      <div className="ai-search-action">
        <form onSubmit={submit} className="search-form">
          <Search size={20} aria-hidden="true" />
          <label className="sr-only" htmlFor="price-question">輸入價格問題</label>
          <input
            id="price-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="例如：高麗菜現在算貴嗎？"
          />
          <button type="submit" aria-label="送出問題" disabled={isLoading}>
            {isLoading ? <LoaderCircle className="spin" size={20} /> : <ArrowRight size={20} />}
          </button>
        </form>
        {error && <p className="search-message" role="alert">{error}</p>}
        {isLoading && <p className="search-message" role="status">正在查詢已驗證的批發資料…</p>}
        <div className="question-chips" aria-label="範例問題">
          {examples.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => {
                setQuestion(example);
                void ask(example);
              }}
              disabled={isLoading}
            >
              {example}
            </button>
          ))}
        </div>
        {answer && (
          <div className="search-answer" role="status" aria-live="polite">
            <p>{answer.answer}</p>
            <div className="answer-meta">
              {answer.as_of && <span><CalendarDays size={14} />資料 {answer.as_of}</span>}
              <span><Database size={14} />批發 · 元／公斤</span>
              <span>{answer.scope?.type === "market" ? "單一市場" : "所有回報市場"}</span>
            </div>
            <div className="answer-source">
              來源：{answer.evidence.map((item, index) => (
                <span key={item.source_url}>
                  {index > 0 && "、"}
                  <a href={item.source_url} target="_blank" rel="noreferrer">{item.publisher}</a>
                </span>
              ))}
            </div>
            {answer.possible_factors?.map((factor) => (
              <div className="answer-factor" key={`${factor.evidence.document_id}-${factor.statement}`}>
                <p>{factor.statement}</p>
                <a href={factor.evidence.source_url} target="_blank" rel="noreferrer">
                  {factor.evidence.publisher}：{factor.evidence.title}
                </a>
                <span>
                  發布 {factor.evidence.published_at}
                  {factor.evidence.event_start && factor.evidence.event_end &&
                    ` · 事件期間 ${factor.evidence.event_start} 至 ${factor.evidence.event_end}`}
                </span>
              </div>
            ))}
            {answer.warnings.map((warning) => <p className="answer-warning" key={warning}>{warning}</p>)}
          </div>
        )}
      </div>
    </section>
  );
}
