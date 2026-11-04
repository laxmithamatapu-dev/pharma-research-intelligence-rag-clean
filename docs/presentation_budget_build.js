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
pres.title = "Pharma Research Assistant — Resource Budget";
pres.author = "Project owner";
pres.subject = "System design, evaluation, capacity and operational risk review";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

const FOOT = "Pharma RAG · Resource budget · fixed parts measured on the VM; knowledge base scaled from measured per-paper rates";

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

// ================================================================ RESOURCE BUDGET (3 slides)
pres.addSection({ title: "Resource budget" });

const FIXED_DISK = [
  ["Qwen 2.5 7B (writes answers)", 4.68],
  ["Qwen 2.5 1.5B (question helper)", 0.99],
  ["MedCPT query encoder (search)", 0.44],
  ["MedCPT article encoder (indexing)", 0.44],
  ["MiniLM reranker", 0.13],
  ["Python + PyTorch + libraries", 1.75],
  ["Ollama runtime", 0.11],
  ["Pipeline code (app, retrieval, service, web page)", 0.001],
];
const FIXED_DISK_TOTAL = FIXED_DISK.reduce((a, b) => a + b[1], 0); // 8.54

function budgetSlide({ title, label, docs, chroma, text, indexRamMB, indexVM, indexLaptop, notes, kbNote }) {
  const s = content(title, "Resource budget", notes);
  const kbDisk = chroma + text;
  const totalDisk = FIXED_DISK_TOTAL + kbDisk;
  const idxGB = indexRamMB / 1024;
  const appTypical = 1.2 - 0.04 + idxGB;          // measured app 1.2 GB incl. 0.04 GB index for 568 papers
  const typical = 5.2 + appTypical + 1.5;          // model + app + typical cache
  const peak = 5.2 + 3.4 + 1.4 + (2.0 - 0.04 + idxGB) + 0.03;
  const f1 = (v) => v < 0.01 ? "≈ 1 MB" : (v >= 10 ? v.toFixed(1) : v.toFixed(2)) + " GB";
  const W = 2.9, G = 0.17;
  stat(s, 0.6, 1.3, W, 1.2, docs, label, C.text2, "docs");
  stat(s, 0.6 + (W + G), 1.3, W, 1.2, "≈ " + totalDisk.toFixed(1) + " GB", "total disk", C.accent1, "disk");
  stat(s, 0.6 + 2 * (W + G), 1.3, W, 1.2, typical.toFixed(1) + "–" + peak.toFixed(1) + " GB", "RAM: typical – peak", C.accent1, "ram");
  stat(s, 0.6 + 3 * (W + G), 1.3, W, 1.2, indexVM, "VM · laptop " + indexLaptop, C.accent2, "index");

  const kb = (v) => ({ text: v, options: { bold: true, color: C.accent1 } });
  table(s, ["DISK · component", "Size"], [
    ...FIXED_DISK.map(([n, v]) => [n, f1(v)]),
    [kb("ChromaDB vector database"), kb(chroma >= 1 ? chroma.toFixed(1) + " GB" : Math.round(chroma * 1000) + " MB")],
    [kb("Extracted text / source files"), kb(text >= 1 ? text.toFixed(1) + " GB" : Math.round(text * 1000) + " MB")],
    [{ text: "Total", options: { bold: true } }, { text: "≈ " + totalDisk.toFixed(1) + " GB", options: { bold: true } }],
  ], { y: 2.75, w: 5.9, colW: [4.3, 1.6], fontSize: 11 });

  table(s, ["RAM · what is loaded", "Size", "When"], [
    ["Qwen 2.5 7B weights + context", "5.2 GB", "always while running"],
    ["Prompt cache (bounded by reload)", "0 → ≈ 3.4 GB", "grows per answer; reset every 20"],
    ["Qwen 2.5 1.5B helper", "0 or 1.4 GB", "only when needed"],
    ["Python, PyTorch, libraries + our code", "≈ 0.47 GB", "always"],
    ["MedCPT query + MiniLM models", "≈ 0.45 GB", "always"],
    [kb("Vector index (search)"), kb(indexRamMB >= 1024 ? idxGB.toFixed(2) + " GB" : Math.max(1, Math.round(indexRamMB)) + " MB"), kb("grows with documents")],
    ["Working memory during a search", "≈ 0.3–1.0 GB", "per request"],
    ["Ollama background service", "0.03 GB", "always"],
    [{ text: "Total", options: { bold: true } }, { text: typical.toFixed(1) + " typical · " + peak.toFixed(1) + " peak (GB)", options: { bold: true } }, ""],
  ], { x: 6.75, y: 2.75, w: 5.95, colW: [2.5, 1.35, 2.1], fontSize: 11 });
  s.addText(kbNote + " · saved answers + logs add ≈ 20 KB per question · plus Windows/OS and your apps · PDFs stay in your folders · no backup", { x: 0.6, y: 6.62, w: 12.1, h: 0.3, fontSize: 10, color: C.accent4, margin: 0, isTextBox: true });
}

budgetSlide({
  title: "Today: 568 papers — what the system needs",
  label: "papers (11,239 passages)",
  docs: "568", chroma: 0.25, text: 0.07, indexRamMB: 40, indexVM: "≈ 25 min", indexLaptop: "≈ 35–50 min (est.)",
  kbNote: "Disk and RAM measured on the VM (du, /proc/smaps, soak runs)",
  notes: "All measured on the project VM. Disk: du of each model file, the Python environment, ChromaDB (249.6 MB) and source XML (70.7 MB). RAM: the app process was measured module by module (libraries 0.45 GB at import, search model files 0.45 GB, the rest working memory; 1.24 GB after two searches); the Qwen runner measured at 5.2 GB after load and 7.8–8.6 GB peak with the bounded cache; the helper model 1.4 GB. Peak is the measured worst case when cache, helper and app peak together (about 11 GB). The qwen3:8b test model (5.2 GB) still on the VM is not needed and is excluded.",
});
budgetSlide({
  title: "100 documents: almost all of it is fixed cost",
  label: "documents (≈ 2,000 pages)",
  docs: "100", chroma: 0.044, text: 0.012, indexRamMB: 6.4, indexVM: "≈ 4.5 min", indexLaptop: "≈ 6–9 min (est.)",
  kbNote: "Knowledge base scaled from measured per-paper rates (0.44 MB ChromaDB, 0.12 MB text, 64 KB index RAM)",
  notes: "The models, software and runtime cost the same whether the library holds 100 or 5,000 documents. For 100 documents the knowledge base itself is only about 56 MB of disk and about 6 MB of RAM. Indexing at about 2.7 s per document on the VM.",
});
budgetSlide({
  title: "5,000 documents: knowledge base grows, models stay the same",
  label: "documents (≈ 100,000 pages)",
  docs: "5,000", chroma: 2.2, text: 0.6, indexRamMB: 320, indexVM: "≈ 3.8 h", indexLaptop: "≈ 5–7.5 h (est.)",
  kbNote: "Knowledge base scaled from measured per-paper rates (0.44 MB ChromaDB, 0.12 MB text, 64 KB index RAM)",
  notes: "Only the highlighted rows grow: ChromaDB about 2.2 GB, extracted text about 0.6 GB, vector index about 0.32 GB of RAM. Everything else is identical to the 100-document case. Search time grows slightly (about 5–8 s instead of about 5 s); answer time is unchanged.",
});

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT, n, "slides");
})();
