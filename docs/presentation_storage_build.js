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
pres.title = "Pharma Research Assistant — Knowledge Base Storage";
pres.author = "Project owner";
pres.subject = "System design, evaluation, capacity and operational risk review";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

const FOOT = "Pharma RAG · Knowledge base storage · per-paper rates measured on 568 papers · laptop indexing is an estimate";

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

// ================================================================ KNOWLEDGE-BASE STORAGE (1 slide)
pres.addSection({ title: "Knowledge base" });
{
  const s = content("Knowledge base size: 1,000 to 50,000 papers", "Knowledge base",
    "Per-paper rates measured on the current corpus (568 papers, 11,239 passages): ChromaDB store 249.6 MB = 0.44 MB per paper; extracted text / source XML 70.7 MB = 0.12 MB per paper; search index in RAM about 64 KB per paper. Indexing measured at about 45 minutes per 1,000 papers on the 8 vCPU VM; laptop indexing is an estimate (60–90 minutes per 1,000). A paper is about 20 pages. Not included: the fixed software and models (about 9 GB disk) and the AI model's RAM (about 7–10 GB while running). Original PDFs stay in their own folders (OneDrive or local) and are not copied. No backup copy included.");
  const W = 2.9, G = 0.17;
  stat(s, 0.6, 1.35, W, 1.25, "0.44 MB", "ChromaDB per paper (disk)", C.accent1, "chroma per paper");
  stat(s, 0.6 + (W + G), 1.35, W, 1.25, "0.12 MB", "extracted text per paper (disk)", C.accent1, "text per paper");
  stat(s, 0.6 + 2 * (W + G), 1.35, W, 1.25, "64 KB", "search index per paper (RAM)", C.accent1, "ram per paper");
  stat(s, 0.6 + 3 * (W + G), 1.35, W, 1.25, "≈ 2.7 s", "indexing per paper (VM)", C.accent2, "index per paper");
  table(s, ["Papers (≈ pages)", "ChromaDB (disk)", "Extracted text (disk)", "Total disk", "RAM for search", "Indexing (VM)", "Indexing (laptop, est.)"], [
    ["1,000 (≈ 20,000)", "0.44 GB", "0.12 GB", { text: "≈ 0.56 GB", options: { bold: true } }, "≈ 64 MB", "≈ 45 min", "≈ 1–1.5 h"],
    ["5,000 (≈ 100,000)", "2.2 GB", "0.6 GB", { text: "≈ 2.8 GB", options: { bold: true } }, "≈ 0.32 GB", "≈ 3.8 h", "≈ 5–7.5 h"],
    ["10,000 (≈ 200,000)", "4.4 GB", "1.2 GB", { text: "≈ 5.6 GB", options: { bold: true } }, "≈ 0.64 GB", "≈ 7.5 h", "≈ 10–15 h"],
    ["25,000 (≈ 500,000)", "11 GB", "3.0 GB", { text: "≈ 14 GB", options: { bold: true } }, "≈ 1.6 GB", "≈ 19 h", "≈ 1–1.5 days"],
    ["50,000 (≈ 1 million)", "22 GB", "6.0 GB", { text: "≈ 28 GB", options: { bold: true } }, "≈ 3.2 GB", "≈ 1.6 days", "≈ 2–3 days"],
  ], { y: 2.85, colW: [2.15, 1.55, 1.85, 1.45, 1.6, 1.55, 1.95], fontSize: 13 });
  s.addText("Knowledge base only · plus fixed ≈ 9 GB disk for software + models and ≈ 7–10 GB RAM for the AI while running · PDFs stay in your folders · no backup copy",
    { x: 0.6, y: 5.55, w: 12.1, h: 0.5, fontSize: 12, color: C.accent4, margin: 0, isTextBox: true });
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT, n, "slides");
})();
