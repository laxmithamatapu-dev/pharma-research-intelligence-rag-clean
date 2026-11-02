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
pres.title = "Pharma Research Intelligence RAG — Architecture";
pres.author = "Project owner";
pres.subject = "System design, evaluation, capacity and operational risk review";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

const FOOT = "Pharma RAG · Architecture block diagrams · Azure D8ls_v6 (8 vCPU, 16 GB, CPU only)";

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

// ================================================================ ARCHITECTURE DIAGRAMS
function link(slide, x1, y1, x2, y2, o = {}) {
  slide.addShape(pres.shapes.LINE, {
    x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.max(Math.abs(x2 - x1), 0.001), h: Math.max(Math.abs(y2 - y1), 0.001),
    flipH: x2 < x1, flipV: y2 < y1,
    line: { color: o.color || HEX.slate, width: o.width || 1.5, endArrowType: o.noArrow ? undefined : "triangle", dashType: o.dash ? "dash" : "solid" },
    objectName: o.name || "link",
  });
}
function lbl(slide, x, y, w, text, o = {}) {
  slide.addText(text, { x, y, w, h: o.h || 0.3, fontSize: o.fs || 11, color: o.color || C.accent4, bold: !!o.bold, align: o.align || "left", valign: "middle", margin: 0, isTextBox: true, objectName: "label " + text.slice(0, 20) });
}
function group(slide, x, y, w, h, title) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.1, fill: { color: C.background1 }, line: { color: HEX.light, width: 1.25, dashType: "dash" }, objectName: "group " + title });
  lbl(slide, x + 0.2, y + 0.08, w - 0.4, title, { bold: true, fs: 12, color: C.accent4 });
}
const LIGHT = C.background2, DARK = C.text2, STORE = C.accent1;
const TINT_AMBER = "FBEFD9", TINT_TEAL = "DDF1EE", TINT_RED = "FBE4E4";
function node(slide, x, y, w, h, title, sub, kind, name) {
  const fill = { light: LIGHT, dark: DARK, store: STORE, amber: TINT_AMBER, out: TINT_TEAL, red: TINT_RED }[kind || "light"];
  const col = { light: C.text1, dark: C.background1, store: C.background1, amber: C.accent2, out: C.accent1, red: C.accent3 }[kind || "light"];
  const subCol = { light: C.accent4, dark: C.background2, store: C.background2, amber: C.accent2, out: C.accent1, red: C.accent3 }[kind || "light"];
  slide.addShape(kind === "store" ? pres.shapes.CAN : pres.shapes.ROUNDED_RECTANGLE,
    Object.assign({ x, y, w, h, fill: { color: fill }, line: { color: fill }, objectName: name || title }, kind === "store" ? {} : { rectRadius: 0.07 }));
  const runs = [{ text: title, options: { bold: true, fontSize: 13, color: col, breakLine: !!sub } }];
  if (sub) runs.push({ text: sub, options: { fontSize: 11, color: subCol } });
  slide.addText(runs, { x: x + 0.05, y: y + (kind === "store" ? h * 0.12 : 0), w: w - 0.1, h: kind === "store" ? h * 0.88 : h, align: "center", valign: "middle", margin: 0.03, isTextBox: true, objectName: (name || title) + " text" });
}
const notesSrc = "Source: docs/PROJECT_STATE.md section 3, docs/OPERATIONS.md, code in src/.";

// ---------------------------------------------------------------- 0 Title
pres.addSection({ title: "Architecture" });
{
  const s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Architecture" });
  s.addText("Pharma Research Intelligence RAG — Architecture Block Diagrams", { placeholder: "title" });
  s.addText([
    { text: "System context · offline indexing · online answering · paper-first retrieval · generation · deployment · evaluation", options: { breakLine: true } },
    { text: "All components run on one Azure VM (8 vCPU, 16 GB RAM, CPU only)", options: { fontSize: 14 } },
  ], { placeholder: "body" });
  s.addNotes(notesSrc);
  n++;
}

// ---------------------------------------------------------------- 1 System context
{
  const s = content("1 · System context: everything runs inside one VM", "Architecture", "Users reach the service through an SSH tunnel or VS Code port forward; the service only listens on 127.0.0.1. The only outbound connection observed is Ollama's background link to ollama.com, which is closed with OLLAMA_NO_CLOUD=1 plus a firewall rule. " + notesSrc);
  node(s, 0.6, 2.05, 1.9, 1.0, "Researcher", "browser on laptop", "out", "user");
  group(s, 2.9, 1.35, 8.3, 5.3, "Azure VM · 8 vCPU · 16 GB RAM · CPU only · no GPU");
  node(s, 3.2, 1.95, 2.3, 1.0, "Web page + API", "serve.py · 127.0.0.1:8000", "light", "svc");
  node(s, 5.95, 1.95, 2.3, 1.0, "Pipeline", "app.py", "light", "pipe");
  node(s, 8.7, 1.95, 2.3, 1.0, "Ollama :11434", "Qwen 2.5 7B Q4_K_M", "dark", "ollama");
  node(s, 3.2, 3.45, 2.3, 1.0, "Query understanding", "intent · drugs · scope", "light", "qu");
  node(s, 5.95, 3.45, 2.3, 1.0, "Paper-first retrieval", "MedCPT + MiniLM reranker", "light", "ret");
  node(s, 8.7, 3.45, 2.3, 1.0, "Answer repair", "citations · validation", "light", "rep");
  node(s, 3.2, 5.05, 2.3, 1.15, "systemd units", "pharma-rag · ollama", "light", "sysd");
  node(s, 5.95, 5.0, 2.3, 1.35, "ChromaDB", "passage + paper index", "store", "chroma");
  node(s, 8.7, 5.05, 2.3, 1.15, "Records", "debug_runs/ · logs/", "light", "records");
  link(s, 2.5, 2.45, 3.2, 2.45, { name: "user to svc" });
  lbl(s, 2.45, 1.7, 0.8, "SSH tunnel", { fs: 10 });
  link(s, 5.5, 2.45, 5.95, 2.45, { name: "svc to pipe" });
  link(s, 8.25, 2.45, 8.7, 2.45, { name: "pipe to ollama" });
  link(s, 6.4, 2.95, 4.35, 3.45, { name: "pipe to qu" });
  link(s, 7.1, 2.95, 7.1, 3.45, { name: "pipe to ret" });
  link(s, 7.8, 2.95, 9.85, 3.45, { name: "pipe to rep" });
  link(s, 7.1, 4.45, 7.1, 5.0, { name: "ret to chroma" });
  link(s, 9.85, 4.45, 9.85, 5.05, { name: "rep to records" });
  node(s, 11.55, 1.95, 1.15, 1.0, "Internet", "ollama.com", "red", "internet");
  link(s, 11.0, 2.45, 11.55, 2.45, { color: HEX.red, dash: true, name: "egress" });
  lbl(s, 11.4, 3.05, 1.4, "close with\nOLLAMA_NO_CLOUD\n+ firewall", { fs: 10, color: C.accent3, h: 0.7 });
}

// ---------------------------------------------------------------- 2 Offline indexing
{
  const s = content("2 · Offline indexing: from PubMed Central to two indexes", "Architecture", "Runs once, and again whenever the corpus changes. Passage index: MedCPT article encoder, mean pooling, about 400-word chunks with 100-word overlap. Paper index: title + abstract, CLS pooling, inner product. Rebuild the paper index after every passage rebuild. " + notesSrc);
  const steps = [["Find papers", "pmc_search.py"], ["Download XML", "pmc_oai.py"], ["Parse", "pmc_parser.py"], ["Enrich", "drugs · design · year"], ["Chunk", "≈ 400 words, 100 overlap"]];
  steps.forEach(([t, sub], i) => {
    node(s, 0.6 + i * 2.5, 1.55, 2.1, 1.05, t, sub, "light", "off " + i);
    if (i < 4) link(s, 0.6 + i * 2.5 + 2.1, 2.075, 0.6 + (i + 1) * 2.5, 2.075, { name: "off link " + i });
  });
  node(s, 8.1, 3.3, 2.1, 1.05, "Embed title + abstract", "MedCPT · CLS pooling", "light", "embed papers");
  node(s, 10.6, 3.3, 2.1, 1.05, "Embed passages", "MedCPT · mean pooling", "light", "embed passages");
  link(s, 9.15, 2.6, 9.15, 3.3, { name: "enrich to embed" });
  link(s, 11.65, 2.6, 11.65, 3.3, { name: "chunk to embed" });
  node(s, 8.1, 4.95, 2.1, 1.45, "Paper index", "pharma_papers · 568", "store", "paper index");
  node(s, 10.6, 4.95, 2.1, 1.45, "Passage index", "pharma_research · 11,239", "store", "passage index");
  link(s, 9.15, 4.35, 9.15, 4.95, { name: "to paper index" });
  link(s, 11.65, 4.35, 11.65, 4.95, { name: "to passage index" });
  table(s, ["Stage", "Count / cost"], [
    ["Papers found / staged / indexed", "643 / 595 / 568"],
    ["Passages", "11,239"],
    ["Index size (ChromaDB)", "238 MB"],
    ["Source XML", "72 MB"],
    ["Indexing time", "≈ 45 min per 1,000 papers"],
  ], { x: 0.6, y: 3.3, w: 6.9, colW: [3.9, 3.0], fontSize: 13 });
}

// ---------------------------------------------------------------- 3 Online answering
{
  const s = content("3 · Online answering: one question, eight steps", "Architecture", "Median times on this VM. Generation is about 95% of the answer time. Questions with no relevant paper stop at step 4 and are answered 'Not established in the supplied evidence' in about 4 seconds without calling the AI. Every request, including failures, is saved as a JSON record. " + notesSrc);
  const steps = [
    ["1  Analyze question", "query_understanding.py", "≈ 0 s"],
    ["2  Choose retrieval plan", "retrieval_strategy.py", "≈ 0 s"],
    ["3  Find candidate papers", "paper_retriever.py", "≈ 0.1 s"],
    ["4  Rank papers", "MiniLM cross-encoder", "≈ 2.3 s"],
    ["5  Select 8 passages", "reranker.py · retriever.py", "≈ 2–8 s"],
    ["6  Build evidence prompt", "context_builder.py", "≈ 0 s"],
    ["7  Generate answer", "generator.py → Ollama · Qwen 2.5 7B", "≈ 96 s"],
    ["8  Repair + validate", "generator.py", "≈ 0 s"],
  ];
  const X = 3.4, W = 4.6, H = 0.52, G = 0.12, Y0 = 1.4;
  steps.forEach(([t, sub, time], i) => {
    const y = Y0 + i * (H + G);
    const kind = i === 6 ? "dark" : "light";
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: X, y, w: W, h: H, rectRadius: 0.06, fill: { color: kind === "dark" ? DARK : LIGHT }, line: { color: kind === "dark" ? DARK : LIGHT }, objectName: "step " + i });
    s.addText([{ text: t + "   ", options: { bold: true, fontSize: 13, color: kind === "dark" ? C.background1 : C.text1 } }, { text: sub, options: { fontSize: 11, color: kind === "dark" ? C.background2 : C.accent4 } }],
      { x: X + 0.15, y, w: W - 0.3, h: H, valign: "middle", margin: 0, isTextBox: true, objectName: "step text " + i });
    lbl(s, X + W + 0.15, y + 0.11, 1.1, time, { bold: i === 6, color: i === 6 ? C.accent2 : C.accent4, fs: 12 });
    if (i < steps.length - 1) link(s, X + W / 2, y + H, X + W / 2, y + H + G, { name: "step link " + i, width: 1 });
  });
  const yEnd = Y0 + 8 * (H + G);
  node(s, 0.6, Y0, 2.3, 0.9, "Question", "web page / API", "out", "question");
  link(s, 2.9, Y0 + 0.26, X, Y0 + 0.26, { name: "q in" });
  node(s, 0.6, Y0 + 3 * (H + G) - 0.2, 2.3, 0.95, "Abstain ≈ 4 s", "best score < 3.5 · no AI call", "amber", "abstain");
  link(s, X, Y0 + 3 * (H + G) + 0.26, 2.9, Y0 + 3 * (H + G) + 0.26, { name: "to abstain", color: HEX.amber });
  node(s, 0.6, Y0 + 7 * (H + G) - 0.2, 2.3, 0.95, "Cited answer", "+ references + timings", "out", "answer");
  link(s, X, Y0 + 7 * (H + G) + 0.26, 2.9, Y0 + 7 * (H + G) + 0.26, { name: "to answer" });
  node(s, 9.7, Y0 + 2 * (H + G), 3.0, 1.15, "ChromaDB", "paper + passage index", "store", "chroma");
  link(s, 9.7, Y0 + 2 * (H + G) + 0.4, X + W + 1.25, Y0 + 2 * (H + G) + 0.26, { name: "chroma link", noArrow: true, dash: true });
  node(s, 9.7, Y0 + 4 * (H + G) - 0.05, 3.0, 0.75, "MedCPT + MiniLM", "PyTorch on CPU", "light", "encoders");
  link(s, 9.7, Y0 + 4 * (H + G) + 0.3, X + W + 1.25, Y0 + 3 * (H + G) + 0.26, { name: "enc link", noArrow: true, dash: true });
  node(s, 9.7, Y0 + 6 * (H + G) - 0.3, 3.0, 0.8, "Ollama · llama-server", "Qwen 2.5 7B · 8K ctx · 8 threads", "dark", "ollama");
  link(s, 9.7, Y0 + 6 * (H + G) + 0.1, X + W + 1.25, Y0 + 6 * (H + G) + 0.26, { name: "ollama link", noArrow: true, dash: true });
  node(s, 9.7, yEnd - 0.5, 3.0, 0.55, "Record", "debug_runs/run_*.json", "light", "record");
}

// ---------------------------------------------------------------- 4 Paper-first retrieval
{
  const s = content("4 · Paper-first retrieval: find the study, then the passages", "Architecture", "Two searches feed one candidate set; the cross-encoder ranks papers on title + abstract. The best score and the margin between the top two papers choose the plan: abstain below 3.5; depth (6 + 2) for single-study questions or a margin of at least 2.0; otherwise breadth (1 from each of 8 papers). Inside the chosen papers, a dense pre-rank keeps up to 20 passages per paper and the cross-encoder picks the final 8. " + notesSrc);
  node(s, 0.6, 2.0, 1.8, 1.0, "Question", "+ analysis", "out", "q");
  node(s, 2.9, 1.4, 2.4, 0.95, "Paper index search", "top 30 papers", "light", "ps");
  node(s, 2.9, 2.65, 2.4, 0.95, "Passage index search", "top 60 → their papers", "light", "pas");
  link(s, 2.4, 2.35, 2.9, 1.875, { name: "q-ps" });
  link(s, 2.4, 2.65, 2.9, 3.125, { name: "q-pas" });
  node(s, 5.8, 2.0, 2.0, 1.0, "Candidate papers", "union of both", "light", "cand");
  link(s, 5.3, 1.875, 5.8, 2.35, { name: "ps-c" });
  link(s, 5.3, 3.125, 5.8, 2.65, { name: "pas-c" });
  node(s, 8.3, 2.0, 2.1, 1.0, "Rank papers", "MiniLM cross-encoder", "light", "rank");
  link(s, 7.8, 2.5, 8.3, 2.5, { name: "c-r" });
  s.addShape(pres.shapes.DIAMOND, { x: 10.8, y: 1.75, w: 1.9, h: 1.5, fill: { color: DARK }, line: { color: DARK }, objectName: "decision" });
  s.addText("Best score\n& margin", { x: 10.8, y: 1.75, w: 1.9, h: 1.5, fontSize: 12, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: "decision text" });
  link(s, 10.4, 2.5, 10.8, 2.5, { name: "r-d" });
  node(s, 11.0, 4.5, 1.7, 1.0, "Abstain", "score < 3.5 · no AI", "amber", "abstain");
  node(s, 6.6, 3.85, 2.5, 0.95, "Depth plan", "6 top paper + 2 second", "light", "depth");
  node(s, 6.6, 5.15, 2.5, 0.95, "Breadth plan", "1 from each of 8 papers", "light", "breadth");
  link(s, 11.75, 3.25, 11.75, 4.5, { name: "d-ab", color: HEX.amber });
  lbl(s, 11.85, 3.7, 0.8, "< 3.5", { fs: 10, color: C.accent2 });
  link(s, 11.25, 3.03, 9.1, 4.3, { name: "d-depth" });
  lbl(s, 7.9, 3.3, 2.3, "single study / margin ≥ 2.0", { fs: 10, align: "right" });
  link(s, 11.5, 3.12, 9.1, 5.5, { name: "d-breadth" });
  lbl(s, 10.0, 5.0, 0.9, "otherwise", { fs: 10 });
  node(s, 3.3, 4.45, 2.9, 1.15, "Select passages inside papers", "pre-rank ≤ 20 / paper → cross-encoder", "light", "select");
  link(s, 6.6, 4.32, 6.2, 4.85, { name: "depth-sel" });
  link(s, 6.6, 5.62, 6.2, 5.2, { name: "breadth-sel" });
  node(s, 0.6, 4.45, 2.2, 1.15, "8 evidence passages", "→ prompt builder", "out", "evidence");
  link(s, 3.3, 5.025, 2.8, 5.025, { name: "sel-ev" });
}

// ---------------------------------------------------------------- 5 Generation
{
  const s = content("5 · Generation and validation: prompt → Qwen → answer", "Architecture", "Token counts are medians over 40 answers. The model reads at about 77 tokens/s and writes at about 7.3 tokens/s on 8 threads. Post-processing repairs instead of discarding: citations are normalized, invented 'X et al.' attributions removed, bracketed statistics converted, and only offending sentences dropped; validation then checks every [E#] exists and no forbidden phrasing remains. " + notesSrc);
  lbl(s, 0.6, 1.35, 3.6, "PROMPT ≈ 3,300 TOKENS", { bold: true, fs: 12 });
  node(s, 0.6, 1.75, 3.6, 0.75, "Instructions", "rules · structure · citation format · ≈ 590", "light", "instr");
  node(s, 0.6, 2.6, 3.6, 0.5, "Question", "≈ 26 tokens", "light", "qq");
  node(s, 0.6, 3.2, 3.6, 2.6, "8 evidence passages [E1]–[E8]", "title · design · year · section · text\n≈ 2,670 tokens (≈ 334 each)", "out", "passages");
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 4.9, y: 2.5, w: 3.2, h: 2.4, rectRadius: 0.08, fill: { color: DARK }, line: { color: DARK }, objectName: "llm" });
  s.addText([
    { text: "Qwen 2.5 7B (Q4_K_M)", options: { bold: true, fontSize: 15, color: C.background1, breakLine: true } },
    { text: "Ollama chat API · llama-server", options: { fontSize: 12, color: C.background2, breakLine: true } },
    { text: "8K context · temperature 0 · 8 threads", options: { fontSize: 12, color: C.background2, breakLine: true } },
    { text: " ", options: { fontSize: 6, breakLine: true } },
    { text: "Read ≈ 43 s · Write ≈ 52 s", options: { fontSize: 13, bold: true, color: "F6C77A" } },
  ], { x: 5.0, y: 2.5, w: 3.0, h: 2.4, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: "llm text" });
  link(s, 4.2, 3.7, 4.9, 3.7, { name: "prompt-llm" });
  lbl(s, 4.95, 5.05, 3.1, "draft answer ≈ 370 tokens", { align: "center", fs: 12 });
  const rep = [["Normalize citations", "[E1, E2] → [E1] [E2]"], ["Remove invented authors", "\"X et al.\" stripped"], ["Fix bracketed statistics", "[95% CI …] → (95% CI …)"], ["Drop offending sentences", "keep the rest"], ["Validate", "every [E#] exists · format"]];
  rep.forEach(([t, sub], i) => {
    const y = 1.45 + i * 0.95;
    node(s, 8.8, y, 3.9, 0.75, t, sub, i === 4 ? "out" : "light", "rep " + i);
    if (i < 4) link(s, 10.75, y + 0.75, 10.75, y + 0.95, { name: "rep link " + i, width: 1 });
  });
  link(s, 8.1, 3.7, 8.8, 1.82, { name: "llm-rep" });
  node(s, 8.8, 6.2, 3.9, 0.55, "Cited answer", "", "out", "final");
  link(s, 10.75, 6.0, 10.75, 6.2, { name: "rep-final" });
}

// ---------------------------------------------------------------- 6 Deployment
{
  const s = content("6 · Service and deployment on the VM", "Architecture", "Two systemd services. pharma-rag (serve.py) serves the web page and API on 127.0.0.1:8000, answers one request at a time, and reloads the model between requests after 20 answers or when free RAM falls below 4 GB (and at start-up) to free Ollama's prompt cache. Ollama runs the models in llama-server processes; the 1.5B helper unloads after 5 minutes idle. " + notesSrc);
  node(s, 0.6, 1.6, 2.0, 1.0, "Laptop browser", "localhost:8000", "out", "browser");
  group(s, 3.0, 1.35, 9.7, 5.35, "Azure VM · Standard_D8ls_v6 · 29 GB Premium SSD");
  group(s, 3.3, 1.85, 4.4, 3.5, "systemd: pharma-rag.service");
  node(s, 3.55, 2.35, 1.9, 0.6, "GET /", "web page", "light", "get root");
  node(s, 5.6, 2.35, 1.9, 0.6, "GET /health", "status · memory", "light", "health");
  node(s, 3.55, 3.05, 3.95, 0.6, "POST /ask", "request lock: one answer at a time", "light", "ask");
  node(s, 3.55, 3.75, 3.95, 0.6, "Pipeline (app.py)", "retrieval + generation", "light", "pipe");
  node(s, 3.55, 4.45, 3.95, 0.7, "Memory guard", "reload every 20 answers / < 4 GB free", "amber", "guard");
  group(s, 8.1, 1.85, 4.3, 3.5, "systemd: ollama.service  ·  127.0.0.1:11434");
  node(s, 8.35, 2.4, 3.8, 1.05, "llama-server: Qwen 2.5 7B", "5.2 GB · kept loaded · 8 threads", "dark", "runner7");
  node(s, 8.35, 3.7, 3.8, 1.05, "llama-server: Qwen 2.5 1.5B", "1.4 GB · query helper · unloads after 5 min", "light", "runner15");
  link(s, 2.6, 2.1, 3.3, 2.1, { name: "browser-svc" });
  lbl(s, 2.55, 2.25, 0.8, "SSH tunnel", { fs: 10 });
  link(s, 7.5, 4.05, 8.35, 2.92, { name: "pipe-ollama" });
  link(s, 7.5, 4.8, 8.35, 3.15, { name: "guard-ollama", color: HEX.amber, dash: true });
  node(s, 3.3, 5.6, 2.8, 0.85, "data/chromadb", "238 MB", "store", "disk chroma");
  node(s, 6.4, 5.6, 2.8, 0.85, "debug_runs/ · logs/", "≈ 20 KB / question", "light", "disk logs");
  node(s, 9.5, 5.6, 2.9, 0.85, "Models on disk", "Ollama 5.7 GB · HF 1.0 GB", "light", "disk models");
}

// ---------------------------------------------------------------- 7 Evaluation
{
  const s = content("7 · Evaluation architecture: how every number was measured", "Architecture", "The harness drives the real app.py pipeline and records every stage. The model study replays the stored evidence from the final baseline to any Ollama model, so differences come from the model alone. The soak test sends questions to the live service while sampling memory every 5 seconds. Results go to benchmark_runs/<timestamp>_<mode>_<label>/. " + notesSrc);
  node(s, 0.6, 1.5, 2.6, 1.1, "49 benchmark questions", "27 tuning · 22 held-out", "out", "questions");
  node(s, 3.8, 1.5, 2.8, 1.1, "Benchmark harness", "harness.py · run_benchmark.py", "light", "harness");
  node(s, 7.2, 1.5, 2.6, 1.1, "Real pipeline", "app.py (production path)", "dark", "real pipe");
  node(s, 10.4, 1.5, 2.3, 1.1, "Run records", "records/*.json", "light", "records");
  link(s, 3.2, 2.05, 3.8, 2.05, { name: "q-h" });
  link(s, 6.6, 2.05, 7.2, 2.05, { name: "h-p" });
  link(s, 9.8, 2.05, 10.4, 2.05, { name: "p-r" });
  node(s, 10.4, 3.1, 2.3, 1.0, "Scoring", "scoring.py · report.py", "light", "scoring");
  link(s, 11.55, 2.6, 11.55, 3.1, { name: "r-s" });
  node(s, 10.4, 4.55, 2.3, 1.0, "summary.md", "facts · citations · time", "out", "summary");
  link(s, 11.55, 4.1, 11.55, 4.55, { name: "s-sum" });
  node(s, 3.8, 3.1, 2.8, 1.0, "Stored evidence", "final baseline contexts", "store", "snapshot");
  link(s, 10.4, 2.4, 6.6, 3.45, { name: "r-snap", dash: true });
  node(s, 3.8, 4.55, 2.8, 1.0, "Model comparison", "model_comparison.py", "light", "mc");
  link(s, 5.2, 4.1, 5.2, 4.55, { name: "snap-mc" });
  node(s, 7.2, 4.55, 2.6, 1.0, "Any Ollama model", "7 configurations", "dark", "models");
  link(s, 6.6, 5.05, 7.2, 5.05, { name: "mc-m" });
  link(s, 9.8, 5.05, 10.4, 5.05, { name: "m-sum" });
  node(s, 0.6, 3.1, 2.6, 1.0, "Soak test", "service_soak.py", "light", "soak");
  node(s, 0.6, 4.55, 2.6, 1.0, "Live service /ask", "+ memory every 5 s", "dark", "live");
  link(s, 1.9, 4.1, 1.9, 4.55, { name: "soak-live" });
  node(s, 0.6, 5.85, 2.6, 0.7, "memory.csv", "answers.json", "out", "memcsv");
  link(s, 1.9, 5.55, 1.9, 5.85, { name: "live-mem" });
  node(s, 3.8, 5.85, 8.9, 0.7, "66 unit tests", "retrieval · indexing · validation · service · memory guard · classification", "light", "tests");
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT, n, "slides");
})();
