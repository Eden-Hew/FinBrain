export type AskRole = "general_employee" | "finance_ops" | "compliance" | "owner_director";

export interface RoleIdentity {
  name: string;
  role: string;
  email: string | null;
}

export const FB_ROLE_IDENTITY: Record<AskRole, RoleIdentity> = {
  general_employee: { name: "Aiman Lee", role: "General employee", email: "aiman@finbrain.my" },
  finance_ops: { name: "Farah Lim", role: "Finance operator", email: "farah@finbrain.my" },
  compliance: { name: "Maya Wong", role: "Compliance reviewer", email: null },
  owner_director: { name: "Chloe Tan", role: "Owner / director", email: "chloe@finbrain.my" },
};

export interface AgentReplyRule {
  keywords: string[];
  reply: string;
}

export interface AgentLangData {
  greeting: string;
  defaultReply: string;
  replies: AgentReplyRule[];
}

export interface AgentDef {
  key: "invoicing" | "sheets" | "drive" | "sales";
  name: string;
  active: boolean;
  description: string;
  settings: [string, string][];
  log: [string, string][];
  i18n: Record<"en" | "ms" | "zh", AgentLangData>;
}

export const FB_AGENTS: Record<string, AgentDef> = {
  invoicing: {
    key: "invoicing",
    name: "Invoicing Agent",
    active: true,
    description: "Snap a receipt → OCR → MyInvois-compliant e-invoice, submitted after approval.",
    settings: [
      ["Sources", "Gmail, Slack, Photo upload, Telegram"],
      ["Approval required before submission", "On"],
      ["Destination", "MyInvois sandbox"],
    ],
    log: [
      ["12 min ago", "Processed receipt from Tenaga Nasional Berhad → e-invoice submitted, UIN #MY29A8F1"],
      ["1 hr ago", "Processed receipt from Grab Malaysia → e-invoice submitted, UIN #MY29A7C3"],
      ["Yesterday", "3 receipts processed, 1 flagged for manual review (missing tax ID)"],
    ],
    i18n: {
      en: {
        greeting: "Hi, I’m your Invoicing Agent. Tell me how you’d like receipts and invoices handled.",
        defaultReply: "Got it — I’ve noted that instruction and will apply it to future invoice runs.",
        replies: [
          { keywords: ["threshold", "above", "over", "under", "limit"], reply: "Understood — I’ll flag anything outside that range for manual approval instead of auto-submitting." },
          { keywords: ["gmail", "slack", "source", "watch"], reply: "Noted — I’ll add that as a watched source for incoming receipts." },
          { keywords: ["pause", "stop", "off"], reply: "Understood, pausing automatic submissions until you turn me back on." },
        ],
      },
      ms: {
        greeting: "Hai, saya Ejen Invois anda. Beritahu saya bagaimana anda mahu resit dan invois diuruskan.",
        defaultReply: "Baik — saya telah catat arahan itu dan akan gunakannya untuk proses invois akan datang.",
        replies: [
          { keywords: ["had", "ambang", "melebihi", "bawah"], reply: "Faham — saya akan tandakan apa-apa di luar julat itu untuk kelulusan manual, bukan hantar automatik." },
          { keywords: ["gmail", "slack", "sumber", "pantau"], reply: "Dicatat — saya akan tambah itu sebagai sumber yang dipantau untuk resit masuk." },
          { keywords: ["jeda", "henti", "berhenti"], reply: "Faham, saya akan jeda penghantaran automatik sehingga anda aktifkan semula." },
        ],
      },
      zh: {
        greeting: "您好，我是您的发票代理。请告诉我您希望如何处理收据和发票。",
        defaultReply: "收到 — 我已记录这项指示，并会应用于日后的发票处理。",
        replies: [
          { keywords: ["阈值", "超过", "以上", "以下", "限额"], reply: "明白 — 超出该范围的项目我会标记为需要人工批准，而不是自动提交。" },
          { keywords: ["来源", "监控", "观察"], reply: "已记录 — 我会将其新增为收据的监控来源。" },
          { keywords: ["暂停", "停止", "关闭"], reply: "明白，我会暂停自动提交，直到您重新启动我。" },
        ],
      },
    },
  },
  sheets: {
    key: "sheets",
    name: "Sheets Logger",
    active: true,
    description: "Every transaction, ticket, or approval logged into Google Sheets automatically.",
    settings: [
      ["Destination sheet", "Q3 Ledger"],
      ["Trigger", "On every approved transaction"],
      ["Columns mapped", "8"],
    ],
    log: [
      ["4 min ago", "18 rows logged to Q3 Ledger (Invoices tab)"],
      ["40 min ago", "5 rows logged to Q3 Ledger (Collections tab)"],
      ["Today", "Sheet sync verified, 0 conflicts"],
    ],
    i18n: {
      en: {
        greeting: "Hi, I’m your Sheets Logger. Tell me what to log and where.",
        defaultReply: "Noted — I’ll fold that into how I log rows going forward.",
        replies: [
          { keywords: ["tab", "sheet", "column"], reply: "Understood — I’ll update the column mapping for that tab." },
          { keywords: ["collections", "invoices"], reply: "Got it, I’ll route those rows to the right tab from now on." },
        ],
      },
      ms: {
        greeting: "Hai, saya Perekod Sheets anda. Beritahu saya apa yang perlu direkod dan di mana.",
        defaultReply: "Dicatat — saya akan gunakan itu dalam cara saya merekod baris seterusnya.",
        replies: [
          { keywords: ["tab", "helaian", "lajur"], reply: "Faham — saya akan kemas kini pemetaan lajur untuk helaian itu." },
          { keywords: ["kutipan", "invois"], reply: "Baik, saya akan hantar baris tersebut ke helaian yang betul mulai sekarang." },
        ],
      },
      zh: {
        greeting: "您好，我是您的表格记录员。请告诉我要记录什么内容以及记录在哪里。",
        defaultReply: "已记录 — 我会将其纳入日后的记录方式中。",
        replies: [
          { keywords: ["标签", "表格", "列"], reply: "明白 — 我会更新该标签的列映射。" },
          { keywords: ["收款", "发票"], reply: "收到，从现在起我会将这些行归入正确的标签。" },
        ],
      },
    },
  },
  drive: {
    key: "drive",
    name: "Drive Organizer",
    active: false,
    description: "Keeps Drive folders current — files, renames, and archives without manual upkeep.",
    settings: [
      ["Watched folder", "Finance / Invoices 2026"],
      ["Naming convention", "{date}_{supplier}_{amount}"],
      ["Archive after", "90 days"],
    ],
    log: [
      ["This morning", "6 files filed into supplier subfolders"],
      ["Yesterday", "2 files renamed to match naming convention"],
      ["3 days ago", "Archived 14 files older than 90 days"],
    ],
    i18n: {
      en: {
        greeting: "Hi, I’m your Drive Organizer. Tell me how to keep folders tidy.",
        defaultReply: "Noted — I’ll apply that the next time I organize the Drive folder.",
        replies: [
          { keywords: ["archive", "delete", "older"], reply: "Understood — I’ll adjust the archive window accordingly." },
          { keywords: ["rename", "naming"], reply: "Got it, I’ll update the file naming convention." },
        ],
      },
      ms: {
        greeting: "Hai, saya Penyusun Drive anda. Beritahu saya bagaimana untuk kekalkan folder kemas.",
        defaultReply: "Dicatat — saya akan gunakan itu pada kali seterusnya saya menyusun folder Drive.",
        replies: [
          { keywords: ["arkib", "padam", "lama"], reply: "Faham — saya akan laraskan tempoh pengarkiban mengikutnya." },
          { keywords: ["nama semula", "penamaan"], reply: "Baik, saya akan kemas kini konvensyen penamaan fail." },
        ],
      },
      zh: {
        greeting: "您好，我是您的云端硬盘整理员。请告诉我如何保持文件夹整洁。",
        defaultReply: "已记录 — 下次整理云端硬盘文件夹时我会应用这一点。",
        replies: [
          { keywords: ["归档", "删除", "较旧"], reply: "明白 — 我会相应调整归档期限。" },
          { keywords: ["重命名", "命名"], reply: "收到，我会更新文件命名规则。" },
        ],
      },
    },
  },
  sales: {
    key: "sales",
    name: "Sales & Finance Bot",
    active: true,
    description: "Answers pipeline and finance questions, drafts follow-ups and collections chases.",
    settings: [
      ["Channels", "Slack, Chat widget"],
      ["Escalates to", "Finance Director"],
      ["Tone", "Professional"],
    ],
    log: [
      ["Just now", "2 collections follow-ups drafted, awaiting approval"],
      ["20 min ago", 'Answered "What’s our overdue AR total?" — cited 3 sources'],
      ["2 hr ago", "Flagged invoice #INV-2291 as 15 days overdue"],
    ],
    i18n: {
      en: {
        greeting: "Hi, I’m your Sales & Finance Bot. Tell me what to say or check.",
        defaultReply: "Noted — I’ll factor that into how I respond and follow up going forward.",
        replies: [
          { keywords: ["overdue", "collections", "follow up", "followup"], reply: "Got it — I’ll draft a follow-up for overdue accounts and queue it for approval." },
          { keywords: ["tone", "polite", "firm"], reply: "Understood, adjusting my tone for future messages." },
        ],
      },
      ms: {
        greeting: "Hai, saya Bot Jualan & Kewangan anda. Beritahu saya apa yang perlu disebut atau disemak.",
        defaultReply: "Dicatat — saya akan ambil kira itu dalam cara saya membalas dan membuat susulan seterusnya.",
        replies: [
          { keywords: ["tertunggak", "kutipan", "susulan"], reply: "Baik — saya akan rangka susulan untuk akaun tertunggak dan gilirkan untuk kelulusan." },
          { keywords: ["nada", "sopan", "tegas"], reply: "Faham, saya akan laraskan nada untuk mesej akan datang." },
        ],
      },
      zh: {
        greeting: "您好，我是您的销售与财务机器人。请告诉我该说什么或该检查什么。",
        defaultReply: "已记录 — 我会将其纳入日后的回复和跟进方式中。",
        replies: [
          { keywords: ["逾期", "催收", "跟进"], reply: "收到 — 我会为逾期账户草拟跟进信息并提交审批。" },
          { keywords: ["语气", "礼貌", "强硬"], reply: "明白，我会调整今后信息的语气。" },
        ],
      },
    },
  },
};

export type EinvoiceStatus = "review" | "pending" | "submitted" | "validated";

export const FB_EINVOICE_STATUS_LABEL: Record<EinvoiceStatus, string> = {
  review: "Needs Review",
  pending: "Pending Approval",
  submitted: "Submitted",
  validated: "Validated",
};

export interface EinvoiceRecord {
  id: string;
  date: string;
  supplier: string;
  amount: string;
  status: EinvoiceStatus;
  uin: string | null;
  submitter: string;
  description: string;
  fields: [string, string][];
  compliance: [string, string][];
}

export const FB_EINVOICE_ORDER = ["inv-4", "inv-1", "inv-2", "inv-3", "inv-5"];

export const initialEinvoices = (): Record<string, EinvoiceRecord> => ({
  "inv-1": {
    id: "inv-1", date: "10 Aug 2026", supplier: "Tenaga Nasional Berhad", amount: "RM 1,240.00",
    status: "validated", uin: "MY29A8F1Q3RT", submitter: "aiman@finbrain.my",
    description: "Electricity — Aug 2026 billing cycle.",
    fields: [
      ["Supplier name", "Tenaga Nasional Berhad"], ["Supplier TIN", "C1234567890"],
      ["Buyer name", "FINBRAIN Sdn Bhd"], ["Invoice no.", "TNB-2026-88213"],
      ["Issue date", "10 Aug 2026"], ["Currency", "MYR"],
      ["Tax type / rate", "SST 6%"], ["Total (incl. tax)", "RM 1,240.00"],
    ],
    compliance: [
      ["OCR extracted", "No personal identifiers found on this bill."],
      ["Fields mapped", "8 of 55 mandatory UBL fields populated."],
      ["Submitted", "Digitally signed and sent to MyInvois sandbox."],
      ["Validated", "LHDN returned a UIN and QR code."],
    ],
  },
  "inv-2": {
    id: "inv-2", date: "9 Aug 2026", supplier: "Grab Malaysia", amount: "RM 86.40",
    status: "submitted", uin: "MY29A7C3K1XZ", submitter: "aiman@finbrain.my",
    description: "Ride-hailing — client site visit.",
    fields: [
      ["Supplier name", "Grab Malaysia Sdn Bhd"], ["Supplier TIN", "C9988776655"],
      ["Buyer name", "FINBRAIN Sdn Bhd"], ["Invoice no.", "GRB-4471209"],
      ["Issue date", "9 Aug 2026"], ["Currency", "MYR"],
      ["Tax type / rate", "SST 0%"], ["Total (incl. tax)", "RM 86.40"],
    ],
    compliance: [
      ["OCR extracted", "Rider phone number auto-masked before storage."],
      ["Fields mapped", "8 of 55 mandatory UBL fields populated."],
      ["Submitted", "Digitally signed and sent to MyInvois sandbox."],
    ],
  },
  "inv-3": {
    id: "inv-3", date: "8 Aug 2026", supplier: "Petronas Dagangan", amount: "RM 320.00",
    status: "pending", uin: null, submitter: "aiman@finbrain.my",
    description: "Fleet fuel — awaiting approval before submission.",
    fields: [
      ["Supplier name", "Petronas Dagangan Berhad"], ["Supplier TIN", "C1122334455"],
      ["Buyer name", "FINBRAIN Sdn Bhd"], ["Invoice no.", "PDB-990214"],
      ["Issue date", "8 Aug 2026"], ["Currency", "MYR"],
      ["Tax type / rate", "SST 6%"], ["Total (incl. tax)", "RM 320.00"],
    ],
    compliance: [
      ["OCR extracted", "No personal identifiers found on this receipt."],
      ["Fields mapped", "8 of 55 mandatory UBL fields populated."],
      ["Awaiting approval", "Ready to submit once approved below."],
    ],
  },
  "inv-4": {
    id: "inv-4", date: "7 Aug 2026", supplier: "Office Supplies Sdn Bhd", amount: "RM 545.90",
    status: "review", uin: null, submitter: "aiman@finbrain.my",
    description: "Flagged: supplier TIN missing from the receipt.",
    fields: [
      ["Supplier name", "Office Supplies Sdn Bhd"], ["Supplier TIN", "— missing —"],
      ["Buyer name", "FINBRAIN Sdn Bhd"], ["Invoice no.", "OS-4471"],
      ["Issue date", "7 Aug 2026"], ["Currency", "MYR"],
      ["Tax type / rate", "SST 6%"], ["Total (incl. tax)", "RM 545.90"],
    ],
    compliance: [
      ["OCR extracted", "No personal identifiers found on this receipt."],
      ["Flagged for review", "Supplier TIN could not be read — confirm manually before approving."],
    ],
  },
  "inv-5": {
    id: "inv-5", date: "5 Aug 2026", supplier: "Astro Malaysia", amount: "RM 129.00",
    status: "validated", uin: "MY29A5D9M2QP", submitter: "chloe@finbrain.my",
    description: "Office subscription — Aug 2026.",
    fields: [
      ["Supplier name", "Astro Malaysia Holdings"], ["Supplier TIN", "C5566778899"],
      ["Buyer name", "FINBRAIN Sdn Bhd"], ["Invoice no.", "AST-118820"],
      ["Issue date", "5 Aug 2026"], ["Currency", "MYR"],
      ["Tax type / rate", "SST 6%"], ["Total (incl. tax)", "RM 129.00"],
    ],
    compliance: [
      ["OCR extracted", "No personal identifiers found on this bill."],
      ["Fields mapped", "8 of 55 mandatory UBL fields populated."],
      ["Submitted", "Digitally signed and sent to MyInvois sandbox."],
      ["Validated", "LHDN returned a UIN and QR code."],
    ],
  },
});

export interface AskRoleData {
  displayLabel: string;
  answer: string;
  citations: { label: string; access: string; withheld: boolean }[];
  note: string | null;
}

export const FB_ASK_ROLES: Record<AskRole, AskRoleData> = {
  owner_director: {
    displayLabel: "Owner / director",
    answer: 'Q3 closed at <strong>RM 612,000 profit</strong> on <strong>RM 1.84M revenue</strong><sup>[1]</sup>. The board approved proceeding with the Acme acquisition at a 15% discount, contingent on legal due diligence closing by September<sup>[2]</sup>.',
    citations: [
      { label: "Finance Dashboard — Q3 earnings summary", access: "Internal", withheld: false },
      { label: "Board Meeting — 14 Jul 2026 minutes", access: "Restricted", withheld: false },
    ],
    note: null,
  },
  finance_ops: {
    displayLabel: "Finance operator",
    answer: 'Q3 closed at <strong>RM 612,000 profit</strong> on <strong>RM 1.84M revenue</strong><sup>[1]</sup>. Board-level decisions remain restricted to the owner/director persona.',
    citations: [
      { label: "Finance Dashboard â€” Q3 earnings summary", access: "Internal", withheld: false },
      { label: "Board Meeting â€” 14 Jul 2026 minutes", access: "Restricted", withheld: true },
    ],
    note: "1 source withheld â€” insufficient permissions.",
  },
  general_employee: {
    displayLabel: "General employee",
    answer: 'Q3 closed at <strong>RM 612,000 profit</strong> on <strong>RM 1.84M revenue</strong><sup>[1]</sup>. I don’t have access to board-level decisions on the Acme deal — that source is Restricted to Finance Director and above.',
    citations: [
      { label: "Finance Dashboard — Q3 earnings summary", access: "Internal", withheld: false },
      { label: "Board Meeting — 14 Jul 2026 minutes", access: "Restricted", withheld: true },
    ],
    note: "1 source withheld — insufficient permissions.",
  },
  compliance: {
    displayLabel: "Compliance reviewer",
    answer: "I don’t have permission to answer that from any source you can access. Ask your Finance Director for a summary, or ask something covered by public documentation.",
    citations: [
      { label: "Finance Dashboard — Q3 earnings summary", access: "Internal", withheld: true },
      { label: "Board Meeting — 14 Jul 2026 minutes", access: "Restricted", withheld: true },
    ],
    note: "2 sources withheld — insufficient permissions.",
  },
};

export interface SopStep { n: string; t: string; d: string }
export interface Sop { id: string; title: string; version: number; status: "approved" | "draft"; owner: string; steps: SopStep[]; sourceRecId?: string }

export const initialSops = (): Sop[] => [
  {
    id: "sop-seed-1", title: "Receipt Intake & OCR Review", version: 2, status: "approved", owner: "Chloe Tan",
    steps: [
      { n: "1", t: "Capture", d: "A photo or forwarded email lands in the Invoicing Agent inbox." },
      { n: "2", t: "Extract & mask", d: "OCR runs and personal identifiers are masked before anything is stored." },
      { n: "3", t: "Review exceptions", d: "Anything flagged — missing TIN, mismatched totals — goes to manual review before submission." },
    ],
  },
];

export interface Recommendation { id: string; title: string; impact: number; status: "proposed" | "sop_drafted"; evidence: string }

export const initialRecommendations = (): Recommendation[] => [
  {
    id: "rec-1", title: "Standardize the invoice-approval threshold at RM 50", impact: 3, status: "proposed",
    evidence: "Detected across 14 of 20 processed invoices this month: manual approval was requested for amounts the Invoicing Agent could safely auto-approve under a consistent RM 50 threshold — an estimated 2 hours/week of approval work.",
  },
  {
    id: "rec-2", title: "Auto-flag receipts missing a Supplier TIN before OCR completes", impact: 2, status: "proposed",
    evidence: "3 of the last 12 e-invoices were only flagged for a missing TIN after full OCR processing. Catching this at capture time avoids rework and keeps the queue moving.",
  },
  {
    id: "rec-3", title: "Add a weekly digest for stale collections follow-ups", impact: 2, status: "proposed",
    evidence: '6 unanswered Sales & Finance Bot chat queries this month asked some version of "why hasn\'t this invoice been followed up" — there is no existing SOP covering escalation timing.',
  },
];

export interface AuditRow { time: string; actor: string; type: string; resource: string; grant: string; status: "Allowed" | "Denied"; hash: string }

export const FB_AUDIT_BASE_COUNT = 122;

export const initialAuditRows = (): AuditRow[] => [
  { time: "10:42:03", actor: "chloe@finbrain.my", type: "Chat Query", resource: "Board Meeting — 14 Jul 2026 minutes", grant: "owner_director", status: "Allowed", hash: "a91f3c…" },
  { time: "10:41:58", actor: "chloe@finbrain.my", type: "Chat Query", resource: "Finance Dashboard — Q3 summary", grant: "owner_director", status: "Allowed", hash: "7e2b10…" },
  { time: "09:15:22", actor: "compliance-demo", type: "Chat Query", resource: "Board Meeting — 14 Jul 2026 minutes", grant: "compliance", status: "Denied", hash: "4d8a91…" },
  { time: "09:02:11", actor: "aiman@finbrain.my", type: "e-Invoice Submit", resource: "TNB-2026-88213", grant: "general_employee", status: "Allowed", hash: "c310ff…" },
  { time: "08:47:05", actor: "invoicing-agent", type: "Agent Run", resource: "Receipt OCR — Grab Malaysia", grant: "system", status: "Allowed", hash: "9b1e77…" },
  { time: "Yesterday 17:20", actor: "chloe@finbrain.my", type: "SOP Approval", resource: "Receipt Intake & OCR Review v2", grant: "owner_director", status: "Allowed", hash: "22af5d…" },
];

export interface PendingAction { id: string; active: boolean; kind: string; agent: string; title: string; approveLabel: string; detail: string }

export const initialPendingActions = (): PendingAction[] => [
  {
    id: "act-1", active: true, kind: "Collections chase", agent: "Sales & Finance Bot",
    title: "Follow-up email to Meridian Corp", approveLabel: "Approve & send",
    detail: "RM 18,400 overdue by 30+ days. Approving will email the client contact directly — review the account before it goes out.",
  },
];

export const FB_TG_SAMPLES = [
  { initials: "BJ", name: "Bina Jaya Hardware", kind: "Supplier", note: "Receipt for the cement order attached 🧾", amount: "RM 94.50", uin: "MY29B3K8QMRT" },
  { initials: "WK", name: "Warung Kak Yah", kind: "Customer", note: "Lunch catering receipt, please process 🧾", amount: "RM 420.00", uin: "MY29C1D5RNXZ" },
  { initials: "TL", name: "Timur Logistics", kind: "Supplier", note: "Delivery receipt for this week 🧾", amount: "RM 156.80", uin: "MY29D6P4WQTP" },
];

export const FB_VOICE_SAMPLES = [
  "What e-invoices need my approval?",
  "Which accounts are overdue?",
  "What’s our cash flow looking like?",
  "Show me open process recommendations",
];

export const FB_UNIFIED_FALLBACK: Record<"en" | "ms" | "zh", string> = {
  en: "I can help with invoicing, e-invoice compliance, cash flow, collections, process recommendations, SOPs, Telegram receipts, spreadsheets, and file organizing — try one of the suggestions above, or ask me directly.",
  ms: "Saya boleh bantu dengan invois, pematuhan e-invois, aliran tunai, kutipan, cadangan proses, SOP, resit Telegram, hamparan, dan penyusunan fail — cuba salah satu cadangan di atas, atau tanya saya terus.",
  zh: "我可以协助处理发票、电子发票合规、现金流、催收、流程优化建议、SOP、Telegram 收据、表格与文件整理 — 试试上面的建议，或直接问我。",
};
