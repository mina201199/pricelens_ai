import type { Metadata } from "next";

import { SiteHeader } from "@/components/site-header";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Price Lens｜AI 民生物價雷達",
    template: "%s｜Price Lens",
  },
  description: "用農業部官方批發市場交易資料，理解台灣農產品目前的相對價格位置。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant" data-scroll-behavior="smooth">
      <body>
        <a className="skip-link" href="#main-content">跳到主要內容</a>
        <SiteHeader />
        <main id="main-content">{children}</main>
        <footer className="site-footer">
          <div className="shell footer-inner">
            <div>
              <strong>Price Lens</strong>
              <p>把官方批發行情，轉成容易理解的價格訊號。</p>
            </div>
            <p className="footer-notice">
              本站資料為農產品批發市場交易行情（元／公斤），不代表零售店、超市或攤商的實際售價。
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
