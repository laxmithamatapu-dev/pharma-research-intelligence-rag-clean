const pptxgen = require("pptxgenjs");
const { applyTheme } = require("/home/azureuser/.claude/skills/synced/790a45c8-d77a-4165-a0fe-79ba44f8dfdd_46598cbe-dcdf-4054-86f3-f5788cc7a54b/pptx/scripts/apply_theme.js");

const OUT = process.argv[2] || "deck.pptx";

const THEME = {
  name: "Engineering Review",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1F2933", lt1: "FFFFFF", dk2: "22313A", lt2: "EEF2F3",
    accent1: "0F766E", accent2: "B45309", accent3: "B91C1C",
    accent4: "475569", accent5: "94A3B8", accent6: "15803D",
    hlink: "0F766E", folHlink: "475569",
  },
};
const HEX = { teal: "0F766E", amber: "B45309", red: "B91C1C", slate: "475569", light: "94A3B8", green: "15803D", grid: "D9E0E3", text: "1F2933" };

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.title = "Pharma Research Assistant — Laptop Plan";
pres.author = "Project owner";
pres.subject = "System design, evaluation, capacity and operational risk review";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

const FOOT = "Pharma RAG · Laptop plan · Dell Pro 14 Plus (Core Ultra 7 255U, 32 GB, 1 of 2 slots) · laptop figures are estimates";

pres.defineSlideMaster({
  title: "TITLE_DARK",
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.0, w: 11.7, h: 1.5, fontSize: 40, bold: true, color: C.background1, valign: "bottom" }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 3.7, w: 11.7, h: 1.6, fontSize: 18, color: C.background2, valign: "top" }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: C.background1 },
  margin: [0.4, 0.6, 0.6, 0.6],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.3, w: 12.1, h: 0.85, fontSize: 30, bold: true, color: C.text2, valign: "middle" }, text: "" } },
    { text: { text: FOOT, options: { x: 0.6, y: 7.02, w: 10.5, h: 0.3, fontSize: 10, color: C.accent4 } } },
  ],
  slideNumber: { x: 12.2, y: 7.02, w: 0.5, h: 0.3, fontSize: 10, color: C.accent4, align: "right" },
});

let n = 0;
function content(title, section, notes) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  if (notes) s.addNotes(notes);
  n++;
  return s;
}

function cell(text, opts = {}) { return { text: String(text), options: opts }; }
function table(slide, header, rows, o) {
  const head = header.map(h => cell(h, { bold: true, color: C.background1, fill: { color: C.text2 }, valign: "middle" }));
  const body = rows.map((r, i) => r.map(v => {
    if (v && typeof v === "object" && v.text !== undefined) {
      return cell(v.text, Object.assign({ fill: { color: i % 2 ? C.background2 : C.background1 }, valign: "middle" }, v.options));
    }
    return cell(v, { fill: { color: i % 2 ? C.background2 : C.background1 }, valign: "middle", color: C.text1 });
  }));
  slide.addTable([head, ...body], Object.assign({
    x: 0.6, y: 1.35, w: 12.1, fontSize: 14, border: { type: "solid", pt: 0.5, color: HEX.grid },
    margin: [0.06, 0.08, 0.06, 0.08], autoPage: false,
  }, o));
}
const st = (text, color) => ({ text, options: { bold: true, color } });
const OK = c => st(c, C.accent6), WARN = c => st(c, C.accent2), BAD = c => st(c, C.accent3);

function stat(slide, x, y, w, h, value, label, color, name) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: C.background2 }, line: { color: C.background2 }, objectName: name + " card" });
  slide.addText(value, { x: x + 0.2, y: y + 0.12, w: w - 0.4, h: h * 0.55, fontSize: 32, bold: true, color, fontFace: THEME.headFontFace, margin: 0, isTextBox: true, valign: "bottom", objectName: name + " value" });
  slide.addText(label, { x: x + 0.2, y: y + 0.12 + h * 0.55, w: w - 0.4, h: h * 0.4 - 0.12, fontSize: 13, color: C.text1, margin: 0, isTextBox: true, valign: "top", objectName: name + " label" });
}
function textBox(slide, items, o) {
  const runs = items.map((t, i) => {
    const base = { bullet: o.bullet === false ? false : true, breakLine: i < items.length - 1, paraSpaceAfter: 6 };
    return typeof t === "string" ? { text: t, options: base } : { text: t.text, options: Object.assign(base, t.options) };
  });
  slide.addText(runs, Object.assign({ fontSize: 14, color: C.text1, valign: "top", isTextBox: true, margin: [0.05, 0.1, 0.05, 0.1] }, o, { bullet: undefined }));
}
function box(slide, x, y, w, h, text, fill, color, name, fs = 12, bold = false) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.06, fill: { color: fill }, line: { color: fill }, objectName: name });
  slide.addText(text, { x, y, w, h, fontSize: fs, bold, color, align: "center", valign: "middle", margin: 0.04, isTextBox: true, objectName: name + " text" });
}
function arrow(slide, x1, y1, x2, y2, name) {
  slide.addShape(pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1) || 0.001, h: Math.abs(y2 - y1) || 0.001, flipV: y2 < y1, line: { color: HEX.slate, width: 1.25, endArrowType: "triangle" }, objectName: name });
}
const chartText = { catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", legendFontFace: "+mn-lt", dataLabelFontFace: "+mn-lt", titleFontFace: "+mn-lt",
  catAxisLabelColor: "475569", valAxisLabelColor: "475569", catAxisLabelFontSize: 12, valAxisLabelFontSize: 11, dataLabelFontSize: 11, legendFontSize: 12, titleFontSize: 14, titleColor: "1F2933" };

// ================================================================ LAPTOP PLAN v2 (3 slides, based on measured Task Manager)
pres.addSection({ title: "Laptop plan" });

// ---------------------------------------------------------------- 1 Today's memory
{
  const s = content("Today the laptop has 11 GB free — just enough, no margin", "Laptop plan",
    "Measured in Task Manager: 20.4 GB in use (2.1 GB already compressed by Windows, a sign of memory pressure), 11.0 GB available, committed 25.2 of 33.5 GB, one of two memory slots used (single channel). The assistant needs about 9.5–10 GB at peak: model, bounded prompt cache, app and the helper model when it loads. That leaves under 1.5 GB for the document index and no safety margin. Assistant sizes are measured on the project VM; laptop figures are estimates.");
  s.addChart(pres.charts.BAR, [
    { name: "Your apps today (measured)", labels: ["Today", "Assistant running"], values: [20.4, 20.4] },
    { name: "Free (measured)", labels: ["Today", "Assistant running"], values: [11.1, 0] },
    { name: "Qwen 2.5 7B", labels: ["Today", "Assistant running"], values: [0, 5.2] },
    { name: "Prompt cache (reset every 10)", labels: ["Today", "Assistant running"], values: [0, 1.9] },
    { name: "App + helper model", labels: ["Today", "Assistant running"], values: [0, 2.9] },
    { name: "Left for documents + margin", labels: ["Today", "Assistant running"], values: [0, 1.1] },
  ], Object.assign({
    x: 0.6, y: 1.3, w: 7.6, h: 4.0, barDir: "bar", barGrouping: "stacked",
    chartColors: ["94A3B8", "D9E0E3", "22313A", "B45309", "475569", "B91C1C"],
    showValue: true, dataLabelPosition: "ctr", dataLabelColor: "FFFFFF", dataLabelFormatCode: "0.0;;;",
    valAxisMinVal: 0, valAxisMaxVal: 32, valAxisMajorUnit: 4, valGridLine: { color: HEX.grid, size: 0.5 }, catGridLine: { style: "none" },
    showLegend: true, legendPos: "b", showTitle: true, title: "31.5 GB RAM (GB)",
  }, chartText));
  table(s, ["Task Manager", "Value", "Meaning"], [
    ["In use", "20.4 GB", "Your apps, before the assistant"],
    ["Available", OK("11.0 GB"), "What the assistant can use"],
    ["Compressed", WARN("2.1 GB"), "Windows already squeezing memory"],
    ["Committed", "25.2 / 33.5 GB", "Little room left before low-memory errors"],
    ["Slots used", BAD("1 of 2"), "Single channel → slower AI"],
  ], { x: 8.5, y: 1.35, w: 4.2, colW: [1.3, 1.25, 1.65], fontSize: 12 });
  box(s, 0.6, 5.6, 12.1, 0.8, "Fits only for a small library (≈ 5,000–10,000 documents) with Windows on the edge — free RAM or add memory first", "FBEFD9", C.accent2, "verdict", 15, true);
}

// ---------------------------------------------------------------- 2 Options
{
  const s = content("Three ways to run it — adding the second memory slot is best", "Laptop plan",
    "Document capacity uses about 64 KB of RAM per 20-page document for the search index; disk is never the limit (about 0.55 MB per document, 325 GB free). Option A: keep current apps, smaller model or tight reset. Option B: reduce everyday usage to about 12 GB (close heavy browser tabs, VS Code, background apps while using the assistant). Option C: add a matching 32 GB module in the empty slot: 64 GB total and dual-channel memory, which also speeds up the AI. Estimates; confirm on the laptop.");
  table(s, ["", "A · As used today", "B · Free ≈ 8 GB of apps", "C · Add 2nd 32 GB module"], [
    ["Total RAM / available", "31.5 / ≈ 11 GB", "31.5 / ≈ 19 GB", "63 / ≈ 43 GB"],
    ["Model", "Qwen 2.5 7B (reset every 10) or Qwen 3 4B", "Qwen 2.5 7B", "Qwen 2.5 7B"],
    ["RAM left for documents", BAD("≈ 0.5–1 GB"), OK("≈ 5–6 GB"), OK("≈ 25+ GB")],
    [{ text: "Documents (≈ pages)", options: { bold: true } }, { text: "≈ 5,000–10,000 (≈ 0.1–0.2 M)", options: { bold: true, color: C.accent3 } }, { text: "≈ 50,000 (≈ 1 M)", options: { bold: true, color: C.accent6 } }, { text: "≈ 100,000+ (≈ 2 M+)", options: { bold: true, color: C.accent6 } }],
    ["Disk used", "≈ 12–15 GB", "≈ 37 GB", "≈ 64 GB (100k docs)"],
    ["Answer time (est.)", "≈ 2–4 min", "≈ 2–4 min", OK("≈ 1.5–3 min (dual channel)")],
    ["Risk", BAD("Windows slows if apps grow"), WARN("Needs app discipline"), OK("Comfortable")],
    ["Verdict", WARN("Trial only"), OK("Workable"), OK("Recommended")],
  ], { colW: [2.6, 3.3, 3.0, 3.2], fontSize: 13 });
}

// ---------------------------------------------------------------- 3 Time
{
  const s = content("More documents barely change answer time — indexing grows", "Laptop plan",
    "Answer time is set by the AI reading 8 passages and writing about 370 tokens, independent of library size; search grows slowly. On this laptop the single memory channel slows the AI writing step: estimated 2–4 minutes per answer now, about 1.5–3 minutes with a second module. Indexing grows in proportion to documents (about 60–90 minutes per 1,000, est.); after the first build only new files are processed. The 568-paper VM row is measured; all laptop rows are estimates.");
  table(s, ["Library size", "Search", "AI answer (1 slot)", "AI answer (2 slots)", "First-time indexing", "Start-up after reboot"], [
    ["568 papers (VM, measured)", "≈ 5 s", "≈ 96 s (VM)", "—", "≈ 25 min", "≈ 3.5 min cold"],
    ["1,000 docs", "≈ 5–8 s", "≈ 2–4 min", "≈ 1.5–3 min", "≈ 1–1.5 h", "≈ 1–3 min"],
    ["10,000 docs", "≈ 6–10 s", "≈ 2–4 min", "≈ 1.5–3 min", "≈ 10–15 h", "≈ 1–3 min"],
    ["50,000 docs", "≈ 8–15 s", "≈ 2–4 min", "≈ 1.5–3 min", WARN("≈ 2–3 days"), "≈ 2–4 min"],
    ["100,000 docs", "≈ 10–20 s", "needs option C", "≈ 1.5–3 min", WARN("≈ 4–6 days"), "≈ 2–5 min"],
  ], { colW: [2.5, 1.4, 2.0, 2.0, 2.1, 2.1], fontSize: 14 });
  const W = 3.9, G = 0.2;
  box(s, 0.6, 4.55, W, 1.35, "Answer time stays flat:\nthe AI always reads 8 passages", "DDF1EE", C.accent1, "flat", 15, true);
  box(s, 0.6 + (W + G), 4.55, W, 1.35, "Indexing grows with documents:\nfirst build overnight, in batches", "FBEFD9", C.accent2, "indexing", 15, true);
  box(s, 0.6 + 2 * (W + G), 4.55, W, 1.35, "Second memory module:\nmore documents and faster answers", C.background2, C.text1, "upgrade", 15, true);
  s.addText("Laptop figures are estimates — confirm with the benchmark on this laptop", { x: 0.6, y: 6.15, w: 12.1, h: 0.4, fontSize: 12, color: C.accent4, margin: 0, isTextBox: true });
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT, n, "slides");
})();
