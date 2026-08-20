import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

export type Lang = "en" | "ms" | "zh";

const FB_I18N: Record<string, Record<Lang, string>> = {
  "nav.home": { en: "Home", ms: "Laman Utama", zh: "主页" },
  "home.title": { en: "Home", ms: "Laman Utama", zh: "主页" },
  "home.desc": {
    en: "Everything across your workspace, at a glance. Each card reflects live data — nothing shown here is invented.",
    ms: "Semua yang berlaku dalam ruang kerja anda, secara ringkas. Setiap kad memaparkan data sebenar — tiada apa-apa di sini direka-reka.",
    zh: "工作区的所有情况，一目了然。每张卡片都反映实时数据——这里显示的内容绝无捏造。",
  },
  "nav.aiAgents": { en: "Customer Intelligence", ms: "Risikan Pelanggan", zh: "客户情报" },
  "nav.einvoicing": { en: "e-Invoicing", ms: "e-Invois", zh: "电子发票" },
  "nav.financeDashboard": { en: "Finance Dashboard", ms: "Papan Pemuka Kewangan", zh: "财务仪表板" },
  "nav.audit": { en: "Audit", ms: "Audit", zh: "审计" },
  "nav.approvals": { en: "Approvals", ms: "Kelulusan", zh: "审批" },
  "nav.logout": { en: "Log out", ms: "Log keluar", zh: "退出登录" },
  "einvoice.title": { en: "e-Invoicing", ms: "e-Invois", zh: "电子发票" },
  "einvoice.desc": {
    en: "Receipts and invoices, mapped to MyInvois and submitted to LHDN — PDPA-aligned end to end.",
    ms: "Resit dan invois, dipetakan ke MyInvois dan dihantar ke LHDN — mematuhi PDPA sepenuhnya.",
    zh: "收据与发票，对接 MyInvois 并提交至 LHDN——全程符合 PDPA 规范。",
  },
  "einvoice.filterAll": { en: "All invoices", ms: "Semua invois", zh: "全部发票" },
  "einvoice.filterMine": { en: "My submissions", ms: "Penyerahan saya", zh: "我的提交" },
  "finance.title": { en: "Finance Dashboard", ms: "Papan Pemuka Kewangan", zh: "财务仪表板" },
  "finance.desc": {
    en: "Company earnings, at a glance — last 12 months.",
    ms: "Pendapatan syarikat secara ringkas — 12 bulan terakhir.",
    zh: "公司业绩概览——近 12 个月。",
  },
  "export.csv": { en: "Export as CSV", ms: "Eksport sebagai CSV", zh: "导出为 CSV" },
  "audit.title": { en: "Audit Trail", ms: "Rekod Audit", zh: "审计记录" },
  "audit.desc": {
    en: "Every access and action, tamper-evident and traceable.",
    ms: "Setiap akses dan tindakan, tahan gangguan dan boleh dijejaki.",
    zh: "每一次访问与操作，均可追溯且防篡改。",
  },
  "approvals.title": { en: "Approvals", ms: "Kelulusan", zh: "审批" },
  "approvals.desc": {
    en: "Everything an AI agent has prepared on your behalf — nothing is submitted, sent, or adopted until you act here.",
    ms: "Semua yang disediakan oleh ejen AI bagi pihak anda — tidak ada yang dihantar atau digunakan sehingga anda meluluskannya di sini.",
    zh: "所有由 AI 代理代您准备的事项——在您在此处操作之前，绝不会提交、发送或采用。",
  },
  "agents.desc": {
    en: "Evidence-backed answers across protected company records, with permission-aware actions.",
    ms: "Jawapan berasaskan bukti merentas rekod syarikat terlindung, dengan tindakan mengikut kebenaran.",
    zh: "跨受保护企业记录的循证答案，并提供权限感知操作。",
  },
  "agents.viewingAs": { en: "Viewing as", ms: "Melihat sebagai", zh: "查看身份：" },
  "nav.ingestion": { en: "Message Capture", ms: "Tangkapan Mesej", zh: "消息捕获" },
  "ingestion.title": { en: "Message Capture", ms: "Tangkapan Mesej", zh: "消息捕获" },
  "ingestion.desc": {
    en: "Messages forwarded from Telegram or email are captured here automatically — personal details are masked before any AI model ever sees them.",
    ms: "Mesej yang dihantar dari Telegram atau e-mel akan diambil di sini secara automatik — butiran peribadi disamarkan sebelum sebarang model AI melihatnya.",
    zh: "从 Telegram 或电子邮件转发的消息会在此自动捕获——个人信息会在任何 AI 模型读取之前先被遮蔽。",
  },
};

export const FB_UI_STRINGS: Record<Lang, { placeholder: string; send: string; switched: string }> = {
  en: { placeholder: "Ask FinBrain anything, or tell it what to do...", send: "Send", switched: "Switched to English." },
  ms: { placeholder: "Tanya FinBrain apa-apa, atau beritahu ia apa yang perlu dilakukan...", send: "Hantar", switched: "Ditukar kepada Bahasa Malaysia." },
  zh: { placeholder: "向 FinBrain 提问，或告诉它该做什么...", send: "发送", switched: "已切换为中文。" },
};

interface I18nContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: string) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>("en");
  const value = useMemo<I18nContextValue>(
    () => ({
      lang,
      setLang,
      t: (key: string) => FB_I18N[key]?.[lang] ?? FB_I18N[key]?.en ?? key,
    }),
    [lang],
  );
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
