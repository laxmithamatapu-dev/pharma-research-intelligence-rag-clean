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
pres.title = "Pharma Research Intelligence RAG — Engineering Review";
pres.author = "Project owner";
pres.subject = "System design, evaluation, capacity and operational risk review";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

const FOOT = "Pharma RAG · Engineering review · measured on Azure D8ls_v6 (8 vCPU, 16 GB, CPU only) unless marked est.";

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

// ---------------------------------------------------------------- 1 Title
pres.addSection({ title: "Overview" });
{
  const s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Overview" });
  s.addText("Pharma Research Intelligence RAG — Engineering Review", { placeholder: "title" });
  s.addText([
    { text: "System design, evaluation results, capacity and operational risks", options: { breakLine: true } },
    { text: "Project period 2026-10-06 → 2026-10-16 · 35 commits · review date 2026-10-18", options: { fontSize: 14 } },
  ], { placeholder: "body" });
  s.addNotes("Purpose: an engineering review of what was built, how it was evaluated, and what is still open. All figures are measured on the project VM unless marked est. Sources: docs/PROJECT_STATE.md, docs/LLM_EVALUATION.md, docs/OPERATIONS.md, docs/ENTERPRISE_DEPLOYMENT_ASSESSMENT.md.");
  n++;
}

// ---------------------------------------------------------------- 2 Review summary
{
  const s = content("Review summary: core objectives met; security and scale open", "Overview",
    "Four headline measurements, then status per area. Retrieval and abstention meet the criteria; generation has a known ~15% omission gap; operations are pilot-ready after two admin steps; security controls for multi-user use do not exist yet.");
  const W = 2.875, G = 0.2;
  stat(s, 0.6, 1.35, W, 1.35, "88% / 81%", "expected facts reaching the model (tuning / held-out)", C.accent1, "retrieval");
  stat(s, 0.6 + (W + G), 1.35, W, 1.35, "85%", "facts in the evidence stated in the answer", C.accent1, "retention");
  stat(s, 0.6 + 2 * (W + G), 1.35, W, 1.35, "~100 s", "end-to-end median per answer (p90 ~125 s)", C.accent2, "latency");
  stat(s, 0.6 + 3 * (W + G), 1.35, W, 1.35, "7.8–8.6 GB", "peak model memory after fix (was 12.9 GB)", C.accent1, "memory");
  table(s, ["Area", "Status", "Evidence"], [
    ["Retrieval", OK("Ready for current corpus"), "Facts reaching model 50 → 88%; gain holds on held-out questions"],
    ["Generation", WARN("Functional, 15% omission gap"), "6 models + Q8_0 tested on identical evidence; none better overall"],
    ["Abstention", OK("Working"), "0 of 12 out-of-corpus questions produced claims"],
    ["Operations", WARN("Pilot-ready after 2 admin steps"), "Memory bounded (measured); auto-start + Ollama egress block pending"],
    ["Security / multi-user", BAD("Not ready"), "No login, no access control, questions and answers stored in plain text"],
  ], { y: 2.95, colW: [2.4, 3.3, 6.4] });
}

// ---------------------------------------------------------------- 3 Scope & criteria
{
  const s = content("Scope, constraints and success criteria", "Overview",
    "Criteria were fixed by the owner before tuning: correctness first, then grounding, retrieval, latency. Business baseline (users, current hours per question) still to be provided.");
  table(s, ["#", "Criterion", "Target", "Measured", "Status"], [
    ["1", "Correct answers", "Expected facts stated; no invented claims", "85% of available facts; 0 invented", OK("Met")],
    ["2", "Evidence grounding", "Every claim cited to a source passage", "Citations validated; 0 failures (103 answers)", OK("Met")],
    ["3", "Reliable retrieval", "Right evidence reaches the model", "88% tuning / 81% held-out", OK("Met")],
    ["4", "Acceptable latency", "90–150 s per answer", "~100–106 s median", OK("Met")],
    ["—", "Operating envelope", "Local only, CPU only, 16 GB VM", "No external calls by the app; memory bounded", OK("Met")],
  ], { colW: [0.5, 2.3, 3.6, 4.2, 1.5] });
  textBox(s, [
    { text: "Corpus: ", options: { bold: true, bullet: false, breakLine: false } },
    { text: "PubMed Central open-access full text · 8 drugs · 643 discovered / 568 indexed papers · 11,239 passages", options: { bullet: false } },
  ], { x: 0.6, y: 4.75, w: 12.1, h: 0.5, bullet: false });
  textBox(s, [
    { text: "Business baseline [TO FILL]: ", options: { bold: true, bullet: false, breakLine: false, color: C.accent2 } },
    { text: "target users · current time per question · questions per week", options: { bullet: false } },
  ], { x: 0.6, y: 5.3, w: 12.1, h: 0.5, bullet: false });
}

// ---------------------------------------------------------------- 4 Work performed
{
  const s = content("Work performed: eight phases, each measured", "Overview",
    "Each phase ended with a measured outcome before the next started. Sources: docs/IMPLEMENTATION_LOG.md, docs/PROJECT_HANDBOOK.md.");
  const phases = [
    ["1 Discovery", "Code + architecture map; defects listed"],
    ["2 Measurement", "Benchmark harness on production path"],
    ["3 Root cause", "10+ retrieval experiments (E1–E6, studies)"],
    ["4 Redesign", "Paper-first retrieval: facts 50 → 88%"],
    ["5 Answer fixes", "API, repair, determinism: failures 5 → 0"],
    ["6 Service", "HTTP API, web page, systemd unit"],
    ["7 Model study", "7 configurations, identical evidence"],
    ["8 Hardening", "Memory bound; network audit"],
  ];
  const W = 2.875, H = 1.25, G = 0.2;
  phases.forEach((p, i) => {
    const x = 0.6 + (i % 4) * (W + G), y = 1.4 + Math.floor(i / 4) * (H + 0.3);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: W, h: H, rectRadius: 0.06, fill: { color: C.background2 }, line: { color: C.background2 }, objectName: "phase " + (i + 1) });
    s.addText([{ text: p[0], options: { bold: true, fontSize: 15, color: C.accent1, breakLine: true } }, { text: p[1], options: { fontSize: 13, color: C.text1 } }],
      { x: x + 0.15, y: y + 0.1, w: W - 0.3, h: H - 0.2, valign: "top", margin: 0, isTextBox: true, objectName: "phase text " + (i + 1) });
  });
  const facts = [["35", "commits"], ["66", "automated tests"], ["49", "benchmark questions"], ["315", "answers scored in model study"], ["22", "design / ops documents"]];
  const FW = 2.3, FG = 0.15;
  facts.forEach((f, i) => {
    const x = 0.6 + i * (FW + FG);
    s.addText([{ text: f[0], options: { bold: true, fontSize: 28, color: C.text2, fontFace: THEME.headFontFace, breakLine: true } }, { text: f[1], options: { fontSize: 13, color: C.accent4 } }],
      { x, y: 4.6, w: FW, h: 1.1, margin: 0, isTextBox: true, valign: "top", objectName: "fact " + f[1] });
  });
}

// ---------------------------------------------------------------- 5 Architecture
pres.addSection({ title: "System design" });
{
  const s = content("Architecture: offline indexing, local online answering", "System design",
    "Offline: parse PubMed Central XML, enrich (drugs, design, year), build passage and paper indexes with MedCPT. Online: everything runs on the VM; the only network hop is loopback to Ollama.");
  s.addText("OFFLINE INDEXING (≈ 45 min per 1,000 papers)", { x: 0.6, y: 1.3, w: 8, h: 0.35, fontSize: 13, bold: true, color: C.accent4, margin: 0, isTextBox: true });
  const off = [["PMC XML\n568 papers", 0.6], ["Parse + enrich\ndrugs, design, year", 2.75], ["Chunk 400 words\n+ MedCPT (mean)", 4.9], ["Passage index\n11,239 passages", 7.05]];
  off.forEach(([t, x], i) => box(s, x, 1.75, 1.85, 0.9, t, i === 3 ? C.accent1 : C.background2, i === 3 ? C.background1 : C.text1, "off" + i));
  for (let i = 0; i < 3; i++) arrow(s, off[i][1] + 1.85, 2.2, off[i + 1][1], 2.2, "off arrow " + i);
  box(s, 4.9, 2.95, 1.85, 0.9, "Title + abstract\n+ MedCPT (CLS)", C.background2, C.text1, "off4");
  box(s, 7.05, 2.95, 1.85, 0.9, "Paper index\n568 papers", C.accent1, C.background1, "off5");
  arrow(s, 3.675, 2.65, 4.9, 3.4, "off arrow 4");
  arrow(s, 6.75, 3.4, 7.05, 3.4, "off arrow 5");

  s.addText("ONLINE ANSWERING (local; ≈ 100 s)", { x: 0.6, y: 4.15, w: 8, h: 0.35, fontSize: 13, bold: true, color: C.accent4, margin: 0, isTextBox: true });
  const on = ["Question", "Query analysis\nintent, drugs, scope", "Candidate papers\nboth indexes", "Cross-encoder\nranks papers", "Passage\nselection", "Qwen 2.5 7B\nQ4_K_M (Ollama)", "Repair +\nvalidation"];
  const OW = 1.55, OG = 0.21;
  on.forEach((t, i) => box(s, 0.6 + i * (OW + OG), 4.6, OW, 0.95, t, i === 5 ? C.text2 : C.background2, i === 5 ? C.background1 : C.text1, "on" + i, 11));
  for (let i = 0; i < 6; i++) arrow(s, 0.6 + i * (OW + OG) + OW, 5.075, 0.6 + (i + 1) * (OW + OG), 5.075, "on arrow " + i);
  box(s, 0.6 + 3 * (OW + OG), 5.95, OW, 0.65, "Abstain if score < 3.5\n(≈ 4 s, no LLM)", "FBEFD9", C.accent2, "abstain", 11, true);
  arrow(s, 0.6 + 3 * (OW + OG) + OW / 2, 5.55, 0.6 + 3 * (OW + OG) + OW / 2, 5.95, "abstain arrow");
  box(s, 0.6 + 6 * (OW + OG), 5.95, OW, 0.65, "Cited answer\n+ JSON record", "DDF1EE", C.accent1, "answer", 11, true);
  arrow(s, 0.6 + 6 * (OW + OG) + OW / 2, 5.55, 0.6 + 6 * (OW + OG) + OW / 2, 5.95, "answer arrow");
  textBox(s, ["Indexes: ChromaDB, local files (238 MB)", "Service: HTTP /ask, /health, web page; one request at a time", "No external service at runtime"], { x: 9.3, y: 1.75, w: 3.4, h: 2.2, fontSize: 13 });
}

// ---------------------------------------------------------------- 6 Request path
{
  const s = content("Request path: generation is 95% of answer time", "System design",
    "Stage timings from docs/PIPELINE_REPORT.md section 2 and the 8-thread runs. Query analysis uses the 1.5B helper model only when rules are not confident (4–11 s).");
  table(s, ["Step", "Component", "Output", "Time"], [
    ["1 Query analysis", "Rules; Qwen 2.5 1.5B fallback", "Intent, drugs, scope", "≈ 0 s (4–11 s with fallback)"],
    ["2 Candidate papers", "Paper index top 30 ∪ papers of passage top 60", "Candidate set", "≈ 0.1 s"],
    ["3 Paper ranking", "MiniLM cross-encoder on title + abstract", "Scores; abstain if best < 3.5", "≈ 2.3 s"],
    ["4 Passage selection", "Cross-encoder within chosen papers", "8 evidence blocks (≤ 1,200 chars)", "≈ 2–8 s"],
    ["5 Generation", "Qwen 2.5 7B Q4_K_M, 8K context, temp 0", "Draft answer (~370 tokens)", { text: "≈ 96 s median", options: { bold: true, color: C.accent2 } }],
    ["6 Repair + validation", "Citation normalization, attribution removal", "Validated answer", "negligible"],
    ["7 Record", "JSON per request incl. failures", "debug_runs/*.json", "negligible"],
  ], { colW: [2.4, 4.3, 3.3, 2.1] });
  textBox(s, ["Out-of-corpus questions stop at step 3: ≈ 4 s, no model call"], { x: 0.6, y: 5.6, w: 12.1, h: 0.5 });
}

// ---------------------------------------------------------------- 7 Paper-first
{
  const s = content("Paper-first retrieval fixed the main evidence bottleneck", "System design",
    "Diagnosis from the retrieval-only baseline and RCA: dense passage search found the right paper 94% of the time but the answer passage only 35%. Causes: wording mismatch between questions and Results text, reranker preference for Discussion sections, and a 2-per-paper cap. Source: docs/RETRIEVAL_RCA.md, docs/PAPER_FIRST_BLUEPRINT.md.");
  stat(s, 0.6, 1.35, 2.9, 1.35, "94%", "right paper in dense top-20 (single-paper questions)", C.accent1, "paper found");
  stat(s, 0.6, 2.9, 2.9, 1.35, "35%", "answer passage in dense top-20", C.accent3, "passage found");
  textBox(s, [
    { text: "Root causes", options: { bold: true, bullet: false } },
    "Question wording ≠ Results-section wording",
    "Reranker preferred Discussion over Results",
    "Cap of 2 passages per paper",
  ], { x: 0.6, y: 4.45, w: 2.9, h: 1.9, fontSize: 13 });
  table(s, ["Plan", "Used when", "Passages to model"], [
    ["Depth", "Single-study question, or top-paper margin ≥ 2.0", "6 from top paper + 2 from second"],
    ["Breadth", "Otherwise (multi-paper questions)", "1 from each of 8 papers"],
    ["Abstain", "Best paper score < 3.5", "0 — no model call"],
  ], { x: 3.8, y: 1.35, w: 8.9, colW: [1.4, 4.3, 3.2] });
  table(s, ["Result (single-paper questions)", "Before", "After"], [
    ["Facts reaching model, tuning (52 facts)", "26 (50%)", OK("46 (88%)")],
    ["Facts reaching model, held-out (16 facts)", "8 (50%)", OK("13 (81%)")],
    ["Questions with no expected fact visible", "5 / 4", OK("0 / 2")],
  ], { x: 3.8, y: 3.55, w: 8.9, colW: [4.9, 2.0, 2.0] });
}

// ---------------------------------------------------------------- 8 Tech stack
{
  const s = content("Technology stack and selection evidence", "System design",
    "Each component choice has a measurement or constraint behind it. Versions from requirements.lock and ollama --version.");
  table(s, ["Layer", "Component", "Version / size", "Why (evidence)"], [
    ["Vector store", "ChromaDB, embedded", "1.5.9 · 238 MB", "Local files, no server; telemetry client is a no-op"],
    ["Embeddings", "MedCPT article + query encoders", "HF, CPU", "Biomedical retrieval model; pooling verified per model card"],
    ["Reranker", "MiniLM-L-12 cross-encoder", "HF, CPU", "MedCPT cross-encoder tested: worse and 3× slower"],
    ["LLM runtime", "Ollama (llama.cpp)", "0.40.2 (pinned)", "Local CPU inference; behaviour is version-specific"],
    ["LLM", "Qwen 2.5 7B Instruct, Q4_K_M", "4.68 GB", "Best of 7 configurations; Apache 2.0"],
    ["Service", "Python stdlib HTTP + systemd", "—", "No extra dependencies; health endpoint"],
    ["Python env", "torch 2.14.1+cpu, transformers 5.19", "1.8 GB", "Pinned (requirements.lock); CUDA packages removed"],
    ["Quality", "unittest + benchmark harness", "66 tests", "Harness runs the production code path"],
  ], { colW: [1.8, 3.4, 2.3, 4.6] });
}

// ---------------------------------------------------------------- 9 Method
pres.addSection({ title: "Evaluation" });
{
  const s = content("Evaluation method: production path, held-out set", "Evaluation",
    "Held-out questions were written after the design and never used to tune. Model comparisons replay the evidence stored by the final baseline run, so differences come from generation only. Disputed gold patterns (2) were adjudicated manually and applied to every model.");
  table(s, ["Question set", "Tuning", "Held-out", "Total"], [
    ["Single-paper (facts)", "16 (52)", "8 (16)", "24 (68)"],
    ["Multi-paper", "9", "4", "13"],
    ["Out-of-corpus controls", "2", "10", "12"],
    [{ text: "Total", options: { bold: true } }, { text: "27", options: { bold: true } }, { text: "22", options: { bold: true } }, { text: "49", options: { bold: true } }],
  ], { w: 5.6, colW: [2.6, 1.0, 1.0, 1.0] });
  textBox(s, [
    "Harness drives the real app code path (no mocks)",
    "Metrics: facts visible / stated, same-line citation, numbers, abstention",
    "Ops metrics: prefill / decode tokens/s, latency, runner RSS, CPU",
    "Model study: 315 answers on stored evidence, 8 threads",
    "Manual review: flagged numbers, control answers, disputed facts",
    "Noise floor: ± 2 facts between runs at temperature 0",
  ], { x: 6.5, y: 1.35, w: 6.2, h: 3.6 });
}

// ---------------------------------------------------------------- 10 Retrieval results
{
  const s = content("Retrieval: gains hold on questions never used for tuning", "Evaluation",
    "Before = original flat passage retrieval; after = paper-first. Multi-paper coverage is a lower bound (gold paper lists drawn from titles). Remaining single-paper misses: passage truncation (N1) and within-paper ranking (N4, L1-09).");
  s.addChart(pres.charts.BAR, [
    { name: "Before", labels: ["Facts reaching model (tuning)", "Facts reaching model (held-out)", "Multi-paper coverage (tuning)", "Multi-paper coverage (held-out)"], values: [50, 50, 41, 30] },
    { name: "After", labels: ["Facts reaching model (tuning)", "Facts reaching model (held-out)", "Multi-paper coverage (tuning)", "Multi-paper coverage (held-out)"], values: [88, 81, 66, 53] },
  ], Object.assign({
    x: 0.6, y: 1.3, w: 8.3, h: 5.4, barDir: "col", barGrouping: "clustered", chartColors: [HEX.light, HEX.teal],
    valAxisMinVal: 0, valAxisMaxVal: 100, valAxisMajorUnit: 20, valAxisTitle: "percent", showValAxisTitle: true, valAxisTitleFontSize: 11, valAxisTitleColor: "475569", valAxisTitleFontFace: "+mn-lt",
    showValue: true, dataLabelPosition: "outEnd", dataLabelColor: "1F2933",
    valGridLine: { color: HEX.grid, size: 0.5 }, catGridLine: { style: "none" }, showLegend: true, legendPos: "t",
    showTitle: true, title: "Before vs after paper-first retrieval (%)",
  }, chartText));
  stat(s, 9.2, 1.4, 3.5, 1.4, "+38 pts", "facts reaching the model, tuning set (50 → 88%)", C.accent1, "gain");
  stat(s, 9.2, 3.0, 3.5, 1.4, "5 → 0", "tuning questions with no expected fact visible (held-out 4 → 2)", C.accent1, "no evidence");
  textBox(s, ["Open: N1 truncation; N4, L1-09 within-paper rank"], { x: 9.2, y: 4.65, w: 3.5, h: 1.0, fontSize: 13 });
}

// ---------------------------------------------------------------- 11 Answer quality
{
  const s = content("Answer quality: 85% retention; residual issues are known", "Evaluation",
    "Retention = facts stated / facts present in the evidence (full 40-answer set, adjudicated: 50 of 59). Control answers were reviewed manually: automatic 'claim' flags on Qwen 3 / Llama were false positives (sentences saying the topic is not covered).");
  const W = 2.875, G = 0.2;
  stat(s, 0.6, 1.35, W, 1.3, "85%", "facts in evidence stated (50 of 59)", C.accent1, "retention");
  stat(s, 0.6 + (W + G), 1.35, W, 1.3, "0 / 12", "out-of-corpus questions with claims", C.accent1, "controls");
  stat(s, 0.6 + 2 * (W + G), 1.35, W, 1.3, "9 / 12", "refused at retrieval, ≈ 4 s, no model call", C.accent1, "fast refusals");
  stat(s, 0.6 + 3 * (W + G), 1.35, W, 1.3, "5 → 0", "answers lost to validation (103 replayed)", C.accent1, "validation");
  table(s, ["Residual issue", "Frequency (measured)", "Handling"], [
    ["Secondary statistics omitted beside main finding", "≈ 15% of visible facts", WARN("Open")],
    ["Comparison-style sections used for single-study questions", "2 of 14 screening questions", WARN("Open — template fix")],
    ["Same-line citation to the correct paper", "56–72% of stated facts", WARN("Open — claim-level citations")],
    ["Arithmetic sign error in a derived number", "1 in 20 screening answers", WARN("Open; citations allow checking")],
    ["Invented author attributions (\"X et al.\")", "Observed in raw output", OK("Removed in post-processing")],
  ], { y: 2.9, colW: [5.2, 3.5, 3.4] });
}

// ---------------------------------------------------------------- 12 Model table
{
  const s = content("Model evaluation: no candidate beat Qwen 2.5 7B Q4_K_M", "Evaluation",
    "Identical stored evidence, 8 threads, 8K context, temperature 0. Facts = adjudicated facts stated on 14 single-paper screening questions (40 visible facts); ± 2 is run-to-run noise. Full 40-answer set: Qwen 2.5 7B 50/59 (85%), Qwen 3 8B 48/59 (81%). Decision rule required +5 pts fact recall without worse numbers, citations, abstention or latency > 150 s.");
  table(s, ["Model (Q4_K_M unless noted)", "Facts / 40", "Median gen.", "p90", "RAM loaded", "Disk", "Num. errors", "Verdict"], [
    [{ text: "Qwen 2.5 7B", options: { bold: true } }, { text: "32", options: { bold: true } }, { text: "90 s", options: { bold: true } }, "106 s", "5.2 GB", "4.7 GB", "1", OK("Selected")],
    ["Qwen 2.5 7B Q8_0", "28", "116 s", "144 s", "9.2 GB", "8.1 GB", "0", BAD("No gain, slower")],
    ["Qwen 3 4B Instruct", "34", "128 s", "165 s", "4.0 GB", "2.5 GB", "2", WARN("Verbose; validate")],
    ["Qwen 3 8B (think off)", "32", "160 s", "201 s", "6.4 GB", "5.2 GB", "0", BAD("Slower")],
    ["Llama 3.1 8B", "27", "127 s", "147 s", "6.0 GB", "4.9 GB", "0", BAD("Weaker")],
    ["Gemma 3 12B", "33", "215 s", "244 s", "9.8 GB", "8.2 GB", "0", BAD("Too slow on CPU")],
    ["Phi-4 14B", "33", "224 s", "256 s", "10.5 GB", "9.1 GB", "0", BAD("Too slow on CPU")],
  ], { colW: [2.75, 1.05, 1.25, 0.95, 1.25, 1.0, 1.25, 2.6], fontSize: 13 });
  textBox(s, ["All 7: 0 validation failures; all handled out-of-corpus questions correctly (Gemma, Phi padded answers with off-topic findings)"], { x: 0.6, y: 5.3, w: 12.1, h: 0.7, fontSize: 13 });
}

// ---------------------------------------------------------------- 13 Trade-off chart
{
  const s = content("Quality vs latency: larger models add ~1 fact for 2.3× time", "Evaluation",
    "Scatter of the screening results. X = median generation seconds, Y = adjudicated facts stated (of 40). Qwen 3 4B is +2 facts (within noise) but slower because it writes 66% longer answers.");
  const xs = [90, 116, 128, 127, 160, 215, 224];
  const ys = [32, 28, 34, 27, 32, 33, 33];
  const labels = ["Qwen 2.5 7B", "Qwen 2.5 7B Q8", "Qwen 3 4B", "Llama 3.1 8B", "Qwen 3 8B", "", "Gemma 12B · Phi-4 14B"];
  s.addChart(pres.charts.SCATTER, [{ name: "X", values: xs }, { name: "Facts stated (of 40)", values: ys, labels }], Object.assign({
    x: 0.6, y: 1.3, w: 8.4, h: 5.4, chartColors: [HEX.teal], lineSize: 0, lineDataSymbol: "circle", lineDataSymbolSize: 11,
    valAxisMinVal: 24, valAxisMaxVal: 36, valAxisMajorUnit: 2, catAxisMinVal: 60, catAxisMaxVal: 260,
    showValAxisTitle: true, valAxisTitle: "facts stated (of 40)", showCatAxisTitle: true, catAxisTitle: "median generation time (s)",
    valAxisTitleFontSize: 11, catAxisTitleFontSize: 11, valAxisTitleColor: "475569", catAxisTitleColor: "475569", valAxisTitleFontFace: "+mn-lt", catAxisTitleFontFace: "+mn-lt",
    showLabel: true, dataLabelFormatScatter: "custom", dataLabelPosition: "t", dataLabelColor: "1F2933",
    valGridLine: { color: HEX.grid, size: 0.5 }, catGridLine: { color: HEX.grid, size: 0.5 }, showLegend: false,
    showTitle: true, title: "Screening results: facts vs median time",
  }, chartText));
  table(s, ["Step up", "Facts", "Time", "RAM"], [
    ["7B → 12–14B", "+1", "×2.4", "×2"],
    ["Q4 → Q8", "−4", "+29%", "+4 GB"],
    ["7B → 4B", "+2", "+42%*", "−1.2 GB"],
  ], { x: 9.3, y: 1.4, w: 3.4, colW: [1.3, 0.6, 0.75, 0.75] });
  textBox(s, ["* longer answers; prompt reading is faster", "Differences ≤ 2 facts are noise"], { x: 9.3, y: 3.3, w: 3.4, h: 1.2, fontSize: 12 });
}

// ---------------------------------------------------------------- 14 Root cause
{
  const s = content("Remaining fact loss: not size, precision or context", "Evaluation",
    "All experiments on the same stored evidence with Qwen 2.5 7B unless the row is a model change. Source: docs/LLM_EVALUATION.md section 13.");
  table(s, ["Factor tested", "Experiment", "Result", "Conclusion"], [
    ["Model architecture / size", "6 models, 4–14B", "All within ± 2 facts except Llama (−5)", "Not model-limited"],
    ["Quantization", "Q4_K_M vs Q8_0", "32 vs 28 facts; citations 72% vs 48%", "Q4_K_M is not the cause"],
    ["Prompt structure", "Claim-per-bullet format", "Citations 72% → 100%; facts 32 → 29", "Moves citation style, not retention"],
    ["Context size", "8 vs first 4 blocks", "Retention 80% → 68% of still-visible facts", "Fewer blocks hurt"],
    ["Evidence position", "Ranked vs reversed order", "32 vs 30 facts (noise)", "No lost-in-the-middle effect"],
    ["Answer length", "Short vs long half; verbose models", "78% vs 81%", "Not the lever"],
    ["Gold scoring", "Manual adjudication", "2 of 14 questions mis-scored for some models", "Part of 'loss' was scoring"],
  ], { colW: [2.4, 2.8, 4.0, 2.9] });
  textBox(s, [{ text: "Diagnosis: the model omits statistics it treats as peripheral, plus answer templates that sometimes do not fit the question.", options: { bullet: false, bold: true } }], { x: 0.6, y: 5.65, w: 12.1, h: 0.6, fontSize: 14 });
}

// ---------------------------------------------------------------- 15 Latency
{
  const s = content("Latency: CPU inference dominates; per-model token rates", "Evaluation",
    "Typical answer: 3,302 prompt tokens + 370 answer tokens. Thread change measured on the same 3,850-token prompt: 4 → 8 threads raised prefill 54.9 → 68.5 tok/s and decode 5.81 → 6.88 tok/s. GPU figure is an estimate.");
  s.addChart(pres.charts.BAR, [
    { name: "Read prompt (prefill)", labels: ["Typical answer"], values: [43] },
    { name: "Write answer (decode)", labels: ["Typical answer"], values: [51] },
    { name: "Search + selection", labels: ["Typical answer"], values: [5] },
  ], Object.assign({
    x: 0.6, y: 1.3, w: 6.0, h: 2.6, barDir: "bar", barGrouping: "stacked", chartColors: [HEX.slate, HEX.teal, HEX.light],
    showValue: true, dataLabelPosition: "ctr", dataLabelColor: "FFFFFF", dataLabelFormatCode: "0\" s\"",
    valAxisMinVal: 0, valAxisMaxVal: 100, valAxisMajorUnit: 20, valGridLine: { color: HEX.grid, size: 0.5 }, catGridLine: { style: "none" },
    showLegend: true, legendPos: "b", showTitle: true, title: "Qwen 2.5 7B: ~100 s per answer (seconds)",
  }, chartText));
  textBox(s, ["Prefill ≈ 45% · decode ≈ 54% · search ≈ 5%", "Each evidence block ≈ 350 tokens ≈ 4.5 s", "Each 100 answer tokens ≈ 14 s", "8 threads vs default 4: 18–25% faster", "GPU server: ≈ 10–20 s (est.)"], { x: 0.6, y: 4.1, w: 6.0, h: 2.6, fontSize: 13 });
  table(s, ["Model", "Prefill tok/s", "Decode tok/s", "Answer tokens"], [
    [{ text: "Qwen 2.5 7B", options: { bold: true } }, "77", "7.3", "370"],
    ["Qwen 2.5 7B Q8", "53", "6.2", "326"],
    ["Qwen 3 4B", "101", "6.9", "616"],
    ["Qwen 3 8B", "65", "4.9", "566"],
    ["Llama 3.1 8B", "67", "5.4", "378"],
    ["Gemma 3 12B", "43", "4.2", "594"],
    ["Phi-4 14B", "36", "3.3", "442"],
  ], { x: 6.9, y: 1.35, w: 5.8, colW: [2.2, 1.2, 1.2, 1.2] });
}

// ---------------------------------------------------------------- 16 Resources
pres.addSection({ title: "Operations and capacity" });
{
  const s = content("Resource utilization on the current VM", "Operations and capacity",
    "Azure Standard_D8ls_v6, East US 2, 8 vCPU (4 cores × 2 threads, AVX-512/AMX), 16 GB RAM, no GPU, no swap, 29 GB Premium SSD.");
  table(s, ["Resource", "Measured", "Notes"], [
    ["CPU", "8 of 8 vCPU (7.96 avg) during generation", "Idle between requests; one answer saturates the VM"],
    ["RAM — model runner", "5.2 GB loaded; 7.8–8.6 GB peak (bounded)", "Was 12.9 GB after 40 answers before the fix"],
    ["RAM — service", "1.2–2.0 GB", "Encoders, reranker, Chroma; no leak over 11 h"],
    ["RAM — query helper", "1.4 GB when loaded", "Qwen 2.5 1.5B; unloads after 5 min idle"],
    ["Disk — system", "≈ 9 GB", "Python 1.8 · models 6.7 · index + corpus 0.31 GB"],
    ["Disk — per paper", "0.53 MB", "Passages 0.39 + source 0.12 + record 0.02 MB"],
    ["Throughput", "≈ 35 answers / hour", "Requests are serialized"],
    ["Start-up", "≈ 6 s warm restart; ≈ 3.5 min after VM boot", "Cold load from disk after reboot"],
  ], { colW: [2.6, 4.6, 4.9] });
}

// ---------------------------------------------------------------- 17 Memory
{
  const s = content("Ollama prompt cache: unbounded growth found and bounded", "Operations and capacity",
    "Root cause: Ollama 0.40.2 starts llama-server with a host-RAM prompt cache of up to 8,192 MiB and exposes no setting; only unloading frees it. Fix: the service reloads the model after 20 answers or when free RAM < 4 GB (between requests), and at start-up. Series: before = 40-answer run without reload; after = 50-answer live service run. Source: docs/OPERATIONS.md section 7.");
  const cats = ["1", "5", "10", "15", "20", "25", "30", "35", "40"];
  s.addChart(pres.charts.LINE, [
    { name: "Before fix", labels: cats, values: [5.2, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 11.9, 12.9] },
    { name: "After fix (reload policy)", labels: cats, values: [5.2, 6.0, 7.0, 8.0, 5.4, 6.4, 7.4, 8.4, 6.0] },
  ], Object.assign({
    x: 0.6, y: 1.3, w: 7.2, h: 5.4, chartColors: [HEX.red, HEX.teal], lineSize: 2.5, lineDataSymbol: "circle", lineDataSymbolSize: 7,
    valAxisMinVal: 4, valAxisMaxVal: 14, valAxisMajorUnit: 2, showValAxisTitle: true, valAxisTitle: "model runner RSS (GB)", showCatAxisTitle: true, catAxisTitle: "answers",
    valAxisTitleFontSize: 11, catAxisTitleFontSize: 11, valAxisTitleColor: "475569", catAxisTitleColor: "475569", valAxisTitleFontFace: "+mn-lt", catAxisTitleFontFace: "+mn-lt",
    valGridLine: { color: HEX.grid, size: 0.5 }, catGridLine: { style: "none" }, showLegend: true, legendPos: "t",
    showTitle: true, title: "Measured model memory per answer",
  }, chartText));
  table(s, ["", "Before", "After (75 live answers)"], [
    ["Peak runner RSS", BAD("12.9 GB, rising"), OK("7.8–8.6 GB")],
    ["Projected at 100", BAD("OOM ≈ answer 35–42"), OK("≤ 8.6 GB")],
    ["Errors", "—", "0"],
    ["Same evidence", "—", "75 / 75"],
    ["Facts stated", "106 (baseline)", "107"],
    ["Reload cost", "—", "≈ 6 s, between requests"],
  ], { x: 8.1, y: 1.35, w: 4.6, colW: [1.6, 1.5, 1.5], fontSize: 12 });
}

// ---------------------------------------------------------------- 18 Privacy
{
  const s = content("Privacy audit: app traffic local; Ollama egress must be blocked", "Operations and capacity",
    "Network checked with ss every second during a live question. Isolated Ollama instance (separate port, empty model folder) used to test cloud behaviour without touching production. Source: docs/OPERATIONS.md section 8.");
  table(s, ["Check", "Method", "Result", "Action"], [
    ["App traffic while answering", "ss sampling, live question", OK("Loopback only"), "—"],
    ["Hugging Face at runtime", "HF_HUB_OFFLINE=1", OK("Disabled"), "—"],
    ["Vector DB telemetry", "Chroma 1.5.9 source", OK("No-op client"), "Set explicitly off (defence in depth)"],
    ["Ollama background connection", "Isolated instance, no requests", BAD("ollama.com:443 open ≈ 1 s after start"), "OLLAMA_NO_CLOUD=1 + egress rule"],
    ["Ollama '-cloud' model names", "Isolated instance request", BAD("Forwarded to ollama.com"), "Same setting refuses them locally"],
    ["With OLLAMA_NO_CLOUD=1", "Isolated instance, 45 samples", OK("0 outbound connections"), "Apply in production (admin)"],
    ["Authentication / access control", "Code review", BAD("None"), "Reverse proxy + SSO; per-collection ACL"],
    ["Stored questions / answers", "Code review", WARN("Plain text JSON + logs"), "Retention policy; disk encryption"],
  ], { colW: [2.9, 2.7, 3.3, 3.2], fontSize: 12 });
}

// ---------------------------------------------------------------- 19 Laptop RAM
{
  const s = content("Company laptops: what runs at each RAM size", "Operations and capacity",
    "Assumes Windows/macOS plus office, browser and security tools use 6–8 GB (est.). Assistant needs the model runner plus ≈ 2 GB for the app; cache bounded by the reload policy. Laptop answer times are estimates; Apple Silicon uses the GPU via Metal.");
  table(s, ["Laptop RAM", "Free for AI (est.)", "Qwen 3 4B\n(needs ≈ 6 GB)", "Qwen 2.5 7B\n(needs ≈ 7–10 GB)", "12–14B models\n(need ≈ 12–13 GB)", "Verdict"], [
    ["8 GB", "≈ 1–2 GB", BAD("No"), BAD("No"), BAD("No"), BAD("Not supported")],
    ["16 GB", "≈ 8–10 GB", OK("Yes"), WARN("Close other apps"), BAD("No"), WARN("Single user, light use")],
    ["32 GB", "≈ 24 GB", OK("Yes"), OK("Yes"), WARN("Fits; ≈ 4 min answers"), OK("Recommended")],
    ["64 GB", "≈ 56 GB", OK("Yes"), OK("Yes"), WARN("Fits; still slow on CPU"), OK("Works; GPU better")],
  ], { colW: [1.5, 1.9, 2.0, 2.3, 2.3, 2.1], fontSize: 13 });
  table(s, ["Laptop type", "Answer time, Qwen 2.5 7B (est.)", "Documents held (RAM-bound, est.)"], [
    ["x86, 16 GB", "1.5–3 min", "15,000–30,000"],
    ["x86, 32 GB", "1.5–2 min", "≈ 150,000"],
    ["Apple Silicon 16–32 GB", "20–60 s", "15,000–150,000"],
  ], { y: 4.4, colW: [3.5, 4.3, 4.3] });
}

// ---------------------------------------------------------------- 20 Storage by disk
{
  const s = content("Storage: how many documents fit in a given free disk", "Operations and capacity",
    "System stack 8.9 GB with Qwen 2.5 7B (6.7 GB with Qwen 3 4B). 0.53 MB per paper-sized document (~20 pages), 0.95 MB with one index backup; 20% of the disk kept free. RAM limits capacity before disk on laptops: ≈ 64 KB of RAM per document.");
  table(s, ["Free disk", "Left for documents", "Documents (no backup)", "Documents (with backup)", "RAM needed for that many"], [
    ["20 GB", "7 GB", "≈ 13,000", "≈ 7,500", "≈ 0.9 GB"],
    ["50 GB", "31 GB", "≈ 58,000", "≈ 33,000", "≈ 3.7 GB"],
    ["100 GB", "71 GB", "≈ 134,000", "≈ 75,000", "≈ 8.6 GB"],
    ["250 GB", "191 GB", "≈ 360,000", "≈ 200,000", { text: "≈ 23 GB — exceeds 16/32 GB laptops", options: { color: C.accent3, bold: true } }],
  ], { colW: [1.6, 2.2, 2.5, 2.6, 3.2], fontSize: 14 });
  textBox(s, [
    "Effective capacity = the smaller of the disk and RAM limits",
    "16 GB laptop: ≈ 15–30k documents (RAM-bound) · 32 GB: ≈ 150k · current VM: ≈ 15k more (29 GB disk)",
  ], { x: 0.6, y: 4.3, w: 12.1, h: 1.2, fontSize: 14 });
}

// ---------------------------------------------------------------- 21 Storage per MB
{
  const s = content("Storage per MB: 1 MB of text ≈ 10.5 MB of index", "Operations and capacity",
    "Measured 2026-10-18: 23.7 MB of indexed text (passages with 25% overlap + paper abstracts) occupies a 250 MB Chroma store; source XML 70.7 MB. Each passage stores text, a 768-dim vector, an HNSW graph entry and metadata. Indexing ≈ 45 min per 1,000 papers on this VM.");
  table(s, ["Input", "Disk needed", "RAM needed (index)"], [
    ["1 MB of plain document text", "≈ 10.5 MB", "≈ 1.5 MB"],
    ["1 MB of PubMed Central XML", "≈ 3.5 MB index + 1 MB source = ≈ 4.5 MB", "≈ 0.5 MB"],
    ["1 paper (~20 pages)", "0.53 MB", "≈ 64 KB"],
  ], { w: 12.1, colW: [4.0, 5.1, 3.0], fontSize: 14 });
  table(s, ["Corpus", "Index + documents", "With one backup", "Index RAM", "Indexing time (this VM)"], [
    ["1,000 papers", "0.53 GB", "0.95 GB", "64 MB", "≈ 45 min"],
    ["10,000 papers", "5.3 GB", "9.5 GB", "0.64 GB", "≈ 7.5 h"],
    ["50,000 papers", "27 GB", "48 GB", "3.2 GB", "≈ 37 h"],
    ["100,000 papers", "53 GB", "95 GB", "6.4 GB", "≈ 3 days"],
  ], { y: 3.35, colW: [2.4, 2.6, 2.4, 2.0, 2.7], fontSize: 14 });
}

// ---------------------------------------------------------------- 22 Deployment tiers
{
  const s = content("Deployment options by hardware tier", "Operations and capacity",
    "Only the current VM row is measured. Laptop and server figures are projections from the VM measurements and must be confirmed with src/evaluation/model_comparison.py on the target hardware before purchase.");
  table(s, ["Hardware", "Recommended model", "Answer time", "Concurrent users", "Documents", "Basis"], [
    ["16 GB laptop", "Qwen 3 4B (after validation)", "1.5–3 min", "1", "15–30k", "est."],
    ["32 GB laptop", "Qwen 2.5 7B Q4_K_M", "1.5–2 min", "1–2", "≈ 150k", "est."],
    [{ text: "Current VM, 16 GB", options: { bold: true } }, { text: "Qwen 2.5 7B Q4_K_M", options: { bold: true } }, { text: "≈ 100 s", options: { bold: true } }, { text: "5–10 active", options: { bold: true } }, { text: "+15k (disk)", options: { bold: true } }, OK("measured")],
    ["Small server, CPU, 64 GB", "Qwen 2.5 7B Q4_K_M", "40–80 s", "15–30", "≈ 500k", "est."],
    ["Department server, 1 GPU 16–24 GB", "Qwen 2.5 7B; re-test 12–14B", "10–20 s", "100–150", "1M+", "est."],
  ], { colW: [2.9, 2.9, 1.5, 1.7, 1.6, 1.5] });
  textBox(s, ["Scale risk: retrieval thresholds were calibrated on 568 papers — re-benchmark at the target corpus size", "Generation cost does not grow with corpus size; retrieval time grows sub-linearly"], { x: 0.6, y: 4.6, w: 12.1, h: 1.2, fontSize: 14 });
}

// ---------------------------------------------------------------- 23 Risk register
pres.addSection({ title: "Status and next steps" });
{
  const s = content("Risk register", "Status and next steps",
    "Severity = impact if it happens; probability on a 16 GB host running continuously. Status reflects 2026-10-18.");
  table(s, ["Risk", "Severity", "Probability", "Mitigation", "Status"], [
    ["Prompt-cache memory growth (OOM)", "High", "High (before fix)", "Reload policy + start-up reset", OK("Mitigated, measured")],
    ["Ollama outbound to ollama.com", "High", "Certain", "OLLAMA_NO_CLOUD=1 + egress rule", WARN("Admin step pending")],
    ["No authentication / access control", "High", "Certain if multi-user", "Reverse proxy + SSO; ACLs", BAD("Open")],
    ["Plain-text question / answer logs", "Medium", "Certain", "Retention policy; disk encryption", BAD("Open")],
    ["Requests serialized (queueing)", "Medium", "High with 2+ users", "GPU server / parallel slots", BAD("Open")],
    ["Service auto-start disabled", "Medium", "High after reboot", "systemctl enable pharma-rag", WARN("Admin step pending")],
    ["Retrieval thresholds at scale", "Medium", "Medium at 10k+ docs", "Re-benchmark at target size", BAD("Open")],
    ["Small single-labeler benchmark", "Medium", "—", "Second reviewer; more questions", BAD("Open")],
  ], { colW: [3.4, 1.2, 2.0, 3.4, 2.1], fontSize: 12 });
}

// ---------------------------------------------------------------- 24 Open work
{
  const s = content("Open work, ordered by dependency", "Status and next steps",
    "Effort estimates are not yet made; fill before the planning discussion.");
  table(s, ["Phase", "Item", "Reason", "Effort"], [
    ["Now", "Apply OLLAMA_NO_CLOUD + egress rule; enable auto-start; add swap", "Privacy, reliability", "hours"],
    ["Next", "Login, access control, retention policy", "Multi-user safety", "[TO FILL]"],
    ["Next", "PDF / DOCX ingestion + retrieval re-benchmark at target size", "Internal documents", "[TO FILL]"],
    ["Next", "Answer-template fit + claim-level citation enforcement", "≈ 15% omission; citation granularity", "[TO FILL]"],
    ["Next", "Expand benchmark; second labeler", "Decision confidence", "[TO FILL]"],
    ["Later", "GPU server; parallel requests; re-test 12–14B models", "Latency, concurrency", "[TO FILL]"],
  ], { colW: [1.1, 5.6, 3.6, 1.8] });
}

// ---------------------------------------------------------------- 25 Decisions
{
  const s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Status and next steps" });
  s.addText("Decisions requested and lessons", { placeholder: "title" });
  s.addText([
    { text: "1  Pilot with 3–5 researchers on the current VM, after the two admin steps", options: { breakLine: true } },
    { text: "2  Approve next work package: access control, PDF/DOCX ingestion, answer structure", options: { breakLine: true } },
    { text: "3  Decide on a GPU server for department scale (≈ 10–20 s answers, est.)", options: { breakLine: true } },
    { text: " ", options: { breakLine: true, fontSize: 8 } },
    { text: "Lessons: measure before optimizing · hold out a test set · bigger models are not better on CPU · audit memory and network, not only quality", options: { fontSize: 14 } },
  ], { placeholder: "body" });
  s.addNotes("Close with the three decisions. Lessons: most early hypotheses were disproven by measurement; the held-out set confirmed the retrieval gain; the operational issues (memory, network) were found only by running the service under load and auditing traffic.");
  n++;
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT, n, "slides");
})();
