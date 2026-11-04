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
pres.title = "Pharma Research Intelligence Assistant — Project Review";
pres.author = "Project owner";
pres.subject = "System design, evaluation, capacity and operational risk review";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

const FOOT = "Pharma RAG · Project review · measured on Azure D8ls_v6 (8 vCPU, 16 GB, CPU only) unless marked est.";

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

// ================================================================ STORY DECK
const T = (s) => s; // titles are written as action sentences

// ---------------------------------------------------------------- 1 Title
pres.addSection({ title: "Problem" });
{
  const s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Problem" });
  s.addText("Pharma Research Intelligence Assistant", { placeholder: "title" });
  s.addText([
    { text: "Private, cited answers from research papers on local AI — project review", options: { breakLine: true } },
    { text: "2026-10-06 → 2026-10-16 · 35 commits · measured on Azure D8ls_v6 (8 vCPU, 16 GB, CPU only)", options: { fontSize: 14 } },
  ], { placeholder: "body" });
  s.addNotes("One line: a research assistant that answers from our own papers, cites its sources, refuses when it does not know, and never sends data outside. Bridge: here is the problem it solves.");
  n++;
}

// ---------------------------------------------------------------- 2 Problem
{
  const s = content("Researchers need cited answers that stay private", "Problem",
    "Problem first, then what success means. Success criteria were fixed before any tuning, in this priority order. Business baseline (users, hours per question) still to be filled. Bridge: here is where we ended up.");
  table(s, ["Today", "Why it is a problem"], [
    ["Researchers read many papers per question", "Slow; synthesis and checking are manual"],
    ["Public AI chat tools", "Documents leave the company; answers invent facts and cannot be traced"],
    [{ text: "[TO FILL] users · hours per question · questions per week", options: { color: C.accent2, bold: true } }, "Baseline for the value case"],
  ], { w: 5.9, colW: [2.9, 3.0] });
  s.addText("WHAT SUCCESS MEANS (priority order)", { x: 6.8, y: 1.35, w: 5.9, h: 0.35, fontSize: 13, bold: true, color: C.accent4, margin: 0, isTextBox: true });
  const crit = [["1", "Correct answers — no invented claims"], ["2", "Every claim cited to its source"], ["3", "Right evidence reaches the AI"], ["4", "Answer in 90–150 s"]];
  crit.forEach(([k, t], i) => {
    const y = 1.85 + i * 0.85;
    s.addShape(pres.shapes.OVAL, { x: 6.8, y, w: 0.6, h: 0.6, fill: { color: i === 0 ? C.accent1 : C.background2 }, line: { color: i === 0 ? C.accent1 : C.background2 }, objectName: "crit dot " + k });
    s.addText(k, { x: 6.8, y, w: 0.6, h: 0.6, fontSize: 16, bold: true, align: "center", valign: "middle", color: i === 0 ? C.background1 : C.text2, margin: 0, isTextBox: true, objectName: "crit num " + k });
    s.addText(t, { x: 7.6, y, w: 5.1, h: 0.6, fontSize: 16, valign: "middle", color: C.text1, margin: 0, isTextBox: true, objectName: "crit text " + k });
  });
  s.addText("Constraints: local inference only · CPU only · 8 vCPU / 16 GB VM · 568 PubMed Central papers on 8 drugs", { x: 0.6, y: 5.6, w: 12.1, h: 0.5, fontSize: 14, color: C.accent4, margin: 0, isTextBox: true });
}

// ---------------------------------------------------------------- 3 The answer
{
  const s = content("The answer: evidence delivery 50 → 88%, pilot-ready", "Problem",
    "Bottom line up front. Four numbers the rest of the talk explains, and the honest status: pilot-ready after two admin steps, not production-ready. Bridge: to follow the story, here is how the system answers a question.");
  const W = 2.875, G = 0.2;
  stat(s, 0.6, 1.4, W, 1.55, "50 → 88%", "expected facts reaching the AI (81% on new questions)", C.accent1, "evidence");
  stat(s, 0.6 + (W + G), 1.4, W, 1.55, "85%", "of that evidence stated in the answer", C.accent1, "retention");
  stat(s, 0.6 + 2 * (W + G), 1.4, W, 1.55, "0 / 12", "out-of-scope questions with invented claims", C.accent1, "abstention");
  stat(s, 0.6 + 3 * (W + G), 1.4, W, 1.55, "~100 s", "per answer on a CPU-only VM", C.accent2, "latency");
  box(s, 0.6, 3.4, 5.95, 1.0, "Pilot-ready after two admin steps", "DDF1EE", C.accent1, "pilot", 18, true);
  box(s, 6.75, 3.4, 5.95, 1.0, "Not yet production-ready: login, access control, document formats", "FBE4E4", C.accent3, "prod", 16, true);
  textBox(s, [{ text: "Story: problem → investigation → root cause → solution → proof → model choice → operational risks → readiness → next steps", options: { bullet: false } }], { x: 0.6, y: 4.8, w: 12.1, h: 0.6, fontSize: 14 });
}

// ---------------------------------------------------------------- 4 How it answers
pres.addSection({ title: "Investigation" });
{
  const s = content("How the system answers a question", "Investigation",
    "Only the vocabulary the rest of the talk needs: papers, passages, the AI model, validation. Everything runs on one VM. Bridge: before changing anything, I needed a way to measure 'correct'.");
  const steps = [["1  Find papers", "search 568 papers by\ntitle, abstract and text"], ["2  Pick passages", "8 best passages\nfrom those papers"], ["3  Write answer", "local AI model\nQwen 2.5 7B"], ["4  Validate", "every claim cited\nto a passage"]];
  const W = 2.7, G = 0.43;
  steps.forEach(([h, d], i) => {
    const x = 0.6 + i * (W + G);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.6, w: W, h: 1.9, rectRadius: 0.08, fill: { color: i === 2 ? C.text2 : C.background2 }, line: { color: i === 2 ? C.text2 : C.background2 }, objectName: "step " + i });
    s.addText([{ text: h, options: { bold: true, fontSize: 18, breakLine: true, color: i === 2 ? C.background1 : C.accent1 } }, { text: d, options: { fontSize: 14, color: i === 2 ? C.background2 : C.text1 } }],
      { x: x + 0.2, y: 1.75, w: W - 0.4, h: 1.6, valign: "top", margin: 0, isTextBox: true, objectName: "step text " + i });
    if (i < 3) arrow(s, x + W + 0.05, 2.55, x + W + G - 0.05, 2.55, "step arrow " + i);
  });
  box(s, 0.6, 3.95, 5.9, 0.85, "Nothing relevant found → refuse in ≈ 4 s, without calling the AI", "FBEFD9", C.accent2, "refuse", 15, true);
  box(s, 6.8, 3.95, 5.9, 0.85, "Output: cited answer + clickable evidence list", "DDF1EE", C.accent1, "out", 15, true);
  textBox(s, [{ text: "Runs as a web page and API on one VM; no external service while answering", options: { bullet: false } }], { x: 0.6, y: 5.2, w: 12.1, h: 0.5, fontSize: 14 });
}

// ---------------------------------------------------------------- 5 Benchmark
{
  const s = content("First, a benchmark to define 'correct'", "Investigation",
    "Each question has the facts a correct answer must contain, so 'correct' is countable. 22 questions were written later and kept aside as a final exam. The same harness runs the real production code. Bridge: the first measurement was the surprise.");
  table(s, ["Question type", "Tuning set", "Held-out (final exam)", "Total"], [
    ["Single-paper questions (expected facts)", "16 (52)", "8 (16)", "24 (68)"],
    ["Multi-paper questions", "9", "4", "13"],
    ["Out-of-scope questions (must refuse)", "2", "10", "12"],
    [{ text: "Total", options: { bold: true } }, { text: "27", options: { bold: true } }, { text: "22", options: { bold: true } }, { text: "49", options: { bold: true } }],
  ], { w: 7.4, colW: [3.6, 1.3, 1.6, 0.9] });
  textBox(s, [
    "Every question lists the facts a correct answer must contain",
    "Held-out questions written after the design; never used for tuning",
    "Runs the exact production code path",
    "Measures: evidence delivered, facts stated, citations, refusals, time",
  ], { x: 8.3, y: 1.35, w: 4.4, h: 3.2, fontSize: 15 });
}

// ---------------------------------------------------------------- 6 Baseline
{
  const s = content("Baseline: half the evidence never reached the model", "Investigation",
    "The key insight: the AI can only state facts it is given. In the original system only 26 of 52 expected facts were even in the evidence handed to the model, and 5 questions had none. So retrieval, not the AI, was the main challenge. Bridge: why was the evidence missed?");
  const funnel = [["52", "expected facts in the tuning questions", C.background2, C.text2], ["26", "reached the AI in the 8 passages (50%)", C.accent2, C.background1], ["≤ 26", "facts the AI could possibly state", C.accent3, C.background1]];
  funnel.forEach(([v, l, fill, col], i) => {
    const w = 7.2 - i * 1.2, x = 0.6 + i * 0.6, y = 1.5 + i * 1.3;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 1.1, rectRadius: 0.06, fill: { color: fill }, line: { color: fill }, objectName: "funnel " + i });
    s.addText([{ text: v + "  ", options: { bold: true, fontSize: 30, fontFace: THEME.headFontFace } }, { text: l, options: { fontSize: 15 } }], { x: x + 0.25, y, w: w - 0.5, h: 1.1, color: col, valign: "middle", margin: 0, isTextBox: true, objectName: "funnel text " + i });
  });
  stat(s, 8.4, 1.5, 4.3, 1.4, "5 of 16", "tuning questions with no expected fact in the evidence at all", C.accent3, "zero");
  stat(s, 8.4, 3.1, 4.3, 1.4, "50%", "same on held-out questions (8 of 16 facts)", C.accent3, "heldout");
  textBox(s, [{ text: "Conclusion: retrieval — not the AI model — was the bottleneck", options: { bullet: false, bold: true, color: C.text2 } }], { x: 0.6, y: 5.6, w: 12.1, h: 0.5, fontSize: 16 });
}

// ---------------------------------------------------------------- 7 Root cause
pres.addSection({ title: "Findings and solution" });
{
  const s = content("Root cause: the right paper, but the wrong passage", "Findings and solution",
    "Experiments separated finding the paper from finding the passage. The paper was found 94% of the time; the passage with the answer only 35%. Three causes explain it. Several plausible suspects were tested and ruled out, which kept the fix focused. Bridge: that pointed to a different design.");
  stat(s, 0.6, 1.4, 2.9, 1.5, "94%", "right paper found", C.accent1, "paper");
  stat(s, 0.6, 3.1, 2.9, 1.5, "35%", "answer passage found", C.accent3, "passage");
  s.addText("WHY THE PASSAGE WAS MISSED", { x: 3.9, y: 1.4, w: 4.2, h: 0.35, fontSize: 13, bold: true, color: C.accent4, margin: 0, isTextBox: true });
  textBox(s, ["Questions are worded differently from Results sections", "The reranker preferred Discussion over Results text", "Only 2 passages per paper were allowed"], { x: 3.9, y: 1.85, w: 4.2, h: 2.6, fontSize: 15 });
  s.addText("TESTED AND RULED OUT", { x: 8.5, y: 1.4, w: 4.2, h: 0.35, fontSize: 13, bold: true, color: C.accent4, margin: 0, isTextBox: true });
  table(s, ["Suspect", "Result"], [
    ["Index built wrongly", "Rebuild identical"],
    ["Text cut off when embedding", "No effect"],
    ["Distance metric", "No effect"],
    ["Rewriting the query", "+0 answer passages"],
    ["Biomedical reranker", "Worse, 3× slower"],
  ], { x: 8.5, y: 1.85, w: 4.2, colW: [2.4, 1.8], fontSize: 13 });
}

// ---------------------------------------------------------------- 8 Solution
{
  const s = content("Paper-first retrieval: find the study, then read it deeply", "Findings and solution",
    "Since papers were found reliably, search papers first, then choose passages only inside the best papers. The budget adapts to the question; if nothing is relevant the system refuses before calling the AI. Bridge: did it work?");
  const flow = [["568 papers", C.background2, C.text1], ["Top papers\n(by title + abstract + text)", C.background2, C.text1], ["Best passages\ninside those papers", C.accent1, C.background1]];
  flow.forEach(([t, f, c], i) => {
    box(s, 0.6 + i * 0.5, 1.45 + i * 1.15, 6.2 - i * 1.0, 0.95, t, f, c, "flow " + i, 15, true);
    if (i < 2) arrow(s, 3.7, 2.4 + i * 1.15, 3.7, 2.6 + i * 1.15, "flow arrow " + i);
  });
  table(s, ["Question type", "Evidence given to the AI"], [
    ["About one study", "6 passages from the top paper + 2 from the next"],
    ["Broad, across studies", "1 passage from each of 8 papers"],
    ["Nothing relevant (score < 3.5)", "Refuse — no AI call (≈ 4 s)"],
  ], { x: 7.3, y: 1.45, w: 5.4, colW: [2.3, 3.1], fontSize: 14 });
  textBox(s, [{ text: "Design follows the diagnosis: keep what worked (paper search), fix what failed (passage choice)", options: { bullet: false, bold: true } }], { x: 0.6, y: 5.2, w: 12.1, h: 0.6, fontSize: 15 });
}

// ---------------------------------------------------------------- 9 Result
pres.addSection({ title: "Validation" });
{
  const s = content("Result: evidence reaching the model rose from 50% to 88%", "Validation",
    "Measured on the tuning questions. Multi-paper coverage also improved. Questions with no evidence at all dropped from 5 to 0. Bridge: but these are the questions I tuned on — is the gain real?");
  s.addChart(pres.charts.BAR, [
    { name: "Before", labels: ["Facts reaching the AI", "Multi-paper coverage"], values: [50, 41] },
    { name: "After paper-first", labels: ["Facts reaching the AI", "Multi-paper coverage"], values: [88, 66] },
  ], Object.assign({
    x: 0.6, y: 1.3, w: 7.6, h: 5.3, barDir: "col", barGrouping: "clustered", chartColors: [HEX.light, HEX.teal],
    valAxisMinVal: 0, valAxisMaxVal: 100, valAxisMajorUnit: 20, showValue: true, dataLabelPosition: "outEnd", dataLabelColor: "1F2933",
    valGridLine: { color: HEX.grid, size: 0.5 }, catGridLine: { style: "none" }, showLegend: true, legendPos: "t",
    showTitle: true, title: "Tuning questions, % (before vs after)",
  }, chartText));
  stat(s, 8.6, 1.4, 4.1, 1.5, "+38 pts", "facts reaching the AI (26 → 46 of 52)", C.accent1, "gain");
  stat(s, 8.6, 3.1, 4.1, 1.5, "5 → 0", "questions with no evidence at all", C.accent1, "none");
}

// ---------------------------------------------------------------- 10 Proof
{
  const s = content("Proof: 81% on 22 questions never used for tuning", "Validation",
    "The 22 held-out questions were written after the design was frozen and never used to tune it. The gain holds there, so it is not overfitting. Bridge: with the evidence now present, how good are the answers?");
  s.addChart(pres.charts.BAR, [
    { name: "Before", labels: ["Tuning questions", "Held-out questions"], values: [50, 50] },
    { name: "After paper-first", labels: ["Tuning questions", "Held-out questions"], values: [88, 81] },
  ], Object.assign({
    x: 0.6, y: 1.3, w: 7.6, h: 5.3, barDir: "col", barGrouping: "clustered", chartColors: [HEX.light, HEX.teal],
    valAxisMinVal: 0, valAxisMaxVal: 100, valAxisMajorUnit: 20, showValue: true, dataLabelPosition: "outEnd", dataLabelColor: "1F2933",
    valGridLine: { color: HEX.grid, size: 0.5 }, catGridLine: { style: "none" }, showLegend: true, legendPos: "t",
    showTitle: true, title: "Facts reaching the AI, % — tuning vs held-out",
  }, chartText));
  table(s, ["Held-out metric", "Before", "After"], [
    ["Facts reaching the AI", "50%", OK("81%")],
    ["Multi-paper coverage", "0.30", OK("0.53")],
    ["Questions with no evidence", "4", OK("2")],
  ], { x: 8.6, y: 1.4, w: 4.1, colW: [2.1, 1.0, 1.0], fontSize: 14 });
  textBox(s, [{ text: "Similar gain on unseen questions → the improvement is real, not memorised", options: { bullet: false, bold: true } }], { x: 8.6, y: 3.3, w: 4.1, h: 1.2, fontSize: 15 });
}

// ---------------------------------------------------------------- 11 Answer quality
{
  const s = content("Answers state 85% of the evidence and refuse correctly", "Validation",
    "Of the facts the AI received, it stated 50 of 59. On 12 out-of-scope questions it never invented a claim; 9 were refused by retrieval in about 4 seconds. The limit: some secondary statistics are left out. Bridge: so is the AI model now the weak link?");
  const W = 3.9, G = 0.2;
  stat(s, 0.6, 1.4, W, 1.6, "85%", "of facts in the evidence stated (50 of 59)", C.accent1, "retention");
  stat(s, 0.6 + (W + G), 1.4, W, 1.6, "0 / 12", "out-of-scope questions with invented claims", C.accent1, "controls");
  stat(s, 0.6 + 2 * (W + G), 1.4, W, 1.6, "5 → 0", "correct answers discarded by validation", C.accent1, "validation");
  s.addText("REMAINING LIMITS", { x: 0.6, y: 3.35, w: 6, h: 0.35, fontSize: 13, bold: true, color: C.accent4, margin: 0, isTextBox: true });
  table(s, ["Limit", "How often"], [
    ["Secondary statistics omitted beside the main finding", "≈ 15% of facts given"],
    ["Citation not always on the same line as the claim", "56–72% on the same line"],
    ["Arithmetic slip in a derived number", "1 in 20 answers checked"],
  ], { y: 3.8, colW: [7.6, 4.5], fontSize: 14 });
}

// ---------------------------------------------------------------- 12 Bridge
pres.addSection({ title: "Model choice" });
{
  const s = content("Facts are now lost equally in search and in writing", "Model choice",
    "Of 68 expected facts: 50 are stated, 9 never reach the AI (hard retrieval cases), and 9 reach the AI but are not written. That raises the question: would a better AI model recover the 9? Bridge: so I tested that directly.");
  s.addChart(pres.charts.BAR, [
    { name: "Stated in the answer", labels: ["68 expected facts"], values: [50] },
    { name: "Reached the AI, not written", labels: ["68 expected facts"], values: [9] },
    { name: "Never reached the AI", labels: ["68 expected facts"], values: [9] },
  ], Object.assign({
    x: 0.6, y: 1.4, w: 12.1, h: 2.6, barDir: "bar", barGrouping: "stacked", chartColors: [HEX.teal, HEX.amber, HEX.light],
    showValue: true, dataLabelPosition: "ctr", dataLabelColor: "FFFFFF", valAxisMinVal: 0, valAxisMaxVal: 68, valAxisMajorUnit: 10,
    valGridLine: { color: HEX.grid, size: 0.5 }, catGridLine: { style: "none" }, showLegend: true, legendPos: "b",
    showTitle: true, title: "Where the 68 expected facts end up (all single-paper questions)",
  }, chartText));
  box(s, 0.6, 4.4, 5.9, 1.2, "Search losses (9): known hard cases — passage cut off, low rank inside the paper", C.background2, C.text1, "search loss", 15);
  box(s, 6.8, 4.4, 5.9, 1.2, "Writing losses (9): the open question — would a different AI model keep them?", "FBEFD9", C.accent2, "writing loss", 15, true);
}

// ---------------------------------------------------------------- 13 Model comparison
{
  const s = content("Seven configurations, same evidence: Qwen 2.5 7B stays", "Model choice",
    "Every model received exactly the same stored evidence, so differences come from the model alone. Larger models (12–14B) gained about one fact — within run-to-run noise — for 2.3× the time and twice the RAM. Higher precision (Q8) gave no gain. Bridge: why do bigger models cost so much time?");
  const xs = [90, 116, 128, 127, 160, 215, 224];
  const ys = [32, 28, 34, 27, 32, 33, 33];
  const labels = ["Qwen 2.5 7B (selected)", "Qwen 2.5 7B Q8", "Qwen 3 4B", "Llama 3.1 8B", "Qwen 3 8B", "", "Gemma 12B · Phi-4 14B"];
  s.addChart(pres.charts.SCATTER, [{ name: "X", values: xs }, { name: "Facts stated (of 40)", values: ys, labels }], Object.assign({
    x: 0.6, y: 1.3, w: 7.9, h: 5.4, chartColors: [HEX.teal], lineSize: 0, lineDataSymbol: "circle", lineDataSymbolSize: 11,
    valAxisMinVal: 24, valAxisMaxVal: 36, valAxisMajorUnit: 2, catAxisMinVal: 60, catAxisMaxVal: 260,
    showValAxisTitle: true, valAxisTitle: "facts stated (of 40)", showCatAxisTitle: true, catAxisTitle: "median seconds per answer",
    valAxisTitleFontSize: 11, catAxisTitleFontSize: 11, valAxisTitleColor: "475569", catAxisTitleColor: "475569", valAxisTitleFontFace: "+mn-lt", catAxisTitleFontFace: "+mn-lt",
    showLabel: true, dataLabelFormatScatter: "custom", dataLabelPosition: "t", dataLabelColor: "1F2933",
    valGridLine: { color: HEX.grid, size: 0.5 }, catGridLine: { color: HEX.grid, size: 0.5 }, showLegend: false,
    showTitle: true, title: "Quality vs speed — up and left is better",
  }, chartText));
  table(s, ["Why Qwen 2.5 7B", ""], [
    ["Facts", "Top group (± 2 = noise)"],
    ["Speed", "Fastest: 90–96 s"],
    ["RAM", "5.2 GB"],
    ["Refusals", "Correct, concise"],
    ["Licence", "Apache 2.0"],
  ], { x: 8.8, y: 1.4, w: 3.9, colW: [1.95, 1.95], fontSize: 14 });
}

// ---------------------------------------------------------------- 14 Latency
{
  const s = content("Where the 100 seconds go", "Model choice",
    "The AI reads about 3,300 tokens (the 8 passages are 81% of that) at 77 tokens/s, then writes about 370 tokens at 7.3 tokens/s. Search is 5 s. CPU inference is the limit, so the lever is hardware (GPU), not tuning. Using all 8 CPU threads gave 18–25%. Bridge: running these tests for hours exposed a real risk.");
  s.addChart(pres.charts.BAR, [
    { name: "AI reads question + 8 passages", labels: ["One answer"], values: [43] },
    { name: "AI writes the answer", labels: ["One answer"], values: [52] },
    { name: "Search + selection", labels: ["One answer"], values: [5] },
  ], Object.assign({
    x: 0.6, y: 1.3, w: 12.1, h: 2.5, barDir: "bar", barGrouping: "stacked", chartColors: [HEX.slate, HEX.teal, HEX.light],
    showValue: true, dataLabelPosition: "ctr", dataLabelColor: "FFFFFF", dataLabelFormatCode: "0\" s\"",
    valAxisMinVal: 0, valAxisMaxVal: 100, valAxisMajorUnit: 10, valGridLine: { color: HEX.grid, size: 0.5 }, catGridLine: { style: "none" },
    showLegend: true, legendPos: "b", showTitle: true, title: "Seconds per typical answer",
  }, chartText));
  table(s, ["Piece", "Tokens", "Speed", "Time"], [
    ["Question", "≈ 26", "—", "< 1 s"],
    ["Instructions", "≈ 590", "77 tok/s", "≈ 8 s"],
    ["8 evidence passages", "≈ 2,670", "77 tok/s", "≈ 35 s"],
    ["Answer written", "≈ 370", "7.3 tok/s", "≈ 52 s"],
  ], { x: 0.6, y: 4.1, w: 7.3, colW: [2.7, 1.5, 1.6, 1.5], fontSize: 14 });
  stat(s, 8.3, 4.1, 2.1, 1.6, "18–25%", "faster: 8 threads", C.accent1, "threads");
  stat(s, 10.6, 4.1, 2.1, 1.6, "10–20 s", "with a GPU (est.)", C.accent2, "gpu");
}

// ---------------------------------------------------------------- 15 Discovery
pres.addSection({ title: "Operational readiness" });
{
  const s = content("Long test runs revealed hidden memory growth", "Operational readiness",
    "Found during the model study: the AI process memory was sampled during every answer and rose about 0.19 GB each time. Ollama's log confirmed it keeps a RAM copy of each prompt's working state, up to 8 GB per model, with no setting to turn it off. On this 16 GB VM without swap that would crash the service after about 40 answers. Bridge: here is the fix and the proof.");
  const cats = ["1", "5", "10", "15", "20", "25", "30", "35", "40"];
  s.addChart(pres.charts.LINE, [
    { name: "AI process memory (no fix)", labels: cats, values: [5.2, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 11.9, 12.9] },
  ], Object.assign({
    x: 0.6, y: 1.3, w: 6.9, h: 5.4, chartColors: [HEX.red], lineSize: 2.5, lineDataSymbol: "circle", lineDataSymbolSize: 7,
    valAxisMinVal: 4, valAxisMaxVal: 16, valAxisMajorUnit: 2, showValAxisTitle: true, valAxisTitle: "GB", showCatAxisTitle: true, catAxisTitle: "answers",
    valAxisTitleFontSize: 11, catAxisTitleFontSize: 11, valAxisTitleColor: "475569", catAxisTitleColor: "475569", valAxisTitleFontFace: "+mn-lt", catAxisTitleFontFace: "+mn-lt",
    valGridLine: { color: HEX.grid, size: 0.5 }, catGridLine: { style: "none" }, showLegend: false,
    showTitle: true, title: "Measured: +0.19 GB per answer, still rising",
  }, chartText));
  table(s, ["Question", "Finding"], [
    ["Where is it stored?", "In RAM of the AI process (llama-server)"],
    ["What is stored?", "Each prompt's working state, ≈ 0.19 GB"],
    ["Limit?", "Up to 8 GB; no setting to change it"],
    ["Evidence", "Ollama log: \"39 prompts, 7,804 MiB\""],
    ["Impact", "16 GB VM, no swap → crash ≈ answer 40"],
  ], { x: 7.8, y: 1.4, w: 4.9, colW: [1.7, 3.2], fontSize: 13 });
}

// ---------------------------------------------------------------- 16 Fix
{
  const s = content("Fixed and verified: memory bounded over 75 answers", "Operational readiness",
    "The only way to free the cache is to unload and reload the model (about 6 s). The service now does this between requests after 20 answers or when free RAM drops below 4 GB, and at start-up. Verified on the live service: 75 answers, memory at most 7.8–8.6 GB, 0 errors, same evidence and same answer quality. Bridge: memory is one risk; privacy is the other.");
  const cats = ["1", "5", "10", "15", "20", "25", "30", "35", "40"];
  s.addChart(pres.charts.LINE, [
    { name: "Before fix", labels: cats, values: [5.2, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 11.9, 12.9] },
    { name: "After fix (reload between requests)", labels: cats, values: [5.2, 6.0, 7.0, 8.0, 5.4, 6.4, 7.4, 8.4, 6.0] },
  ], Object.assign({
    x: 0.6, y: 1.3, w: 6.9, h: 5.4, chartColors: [HEX.red, HEX.teal], lineSize: 2.5, lineDataSymbol: "circle", lineDataSymbolSize: 7,
    valAxisMinVal: 4, valAxisMaxVal: 16, valAxisMajorUnit: 2, showValAxisTitle: true, valAxisTitle: "GB", showCatAxisTitle: true, catAxisTitle: "answers",
    valAxisTitleFontSize: 11, catAxisTitleFontSize: 11, valAxisTitleColor: "475569", catAxisTitleColor: "475569", valAxisTitleFontFace: "+mn-lt", catAxisTitleFontFace: "+mn-lt",
    valGridLine: { color: HEX.grid, size: 0.5 }, catGridLine: { style: "none" }, showLegend: true, legendPos: "t",
    showTitle: true, title: "Measured AI process memory",
  }, chartText));
  table(s, ["Check (75 live answers)", "Result"], [
    ["Peak memory", OK("7.8–8.6 GB (was 12.9)")],
    ["Errors", OK("0")],
    ["Same evidence retrieved", OK("75 / 75")],
    ["Facts stated vs before", OK("107 vs 106")],
    ["Cost", "≈ 6 s reload, between requests"],
  ], { x: 7.8, y: 1.4, w: 4.9, colW: [2.4, 2.5], fontSize: 14 });
}

// ---------------------------------------------------------------- 17 Privacy
{
  const s = content("Documents stay on the machine; one connection to close", "Operational readiness",
    "Network traffic was recorded every second during a live question: the application only talked inside the VM. Separately, Ollama opens a background connection to ollama.com at start-up and would forward '-cloud' model names there. One setting plus a firewall rule closes it (verified on an isolated test instance). Bridge: so where does that leave us?");
  table(s, ["Check", "Result"], [
    ["Questions, documents, answers leaving the VM", OK("None — traffic stays inside the machine")],
    ["Cloud AI or telemetry", OK("None")],
    ["Ollama connection to ollama.com", BAD("Open from start-up")],
    ["Fix: OLLAMA_NO_CLOUD=1 + firewall rule", WARN("Verified on test instance; admin to apply")],
  ], { w: 12.1, colW: [6.0, 6.1], fontSize: 16 });
  box(s, 0.6, 4.3, 12.1, 0.9, "Still needed for multi-user use: login · per-document access control · retention and encryption of stored questions", C.background2, C.text1, "still needed", 15);
}

// ---------------------------------------------------------------- 18 Readiness
pres.addSection({ title: "Readiness and next steps" });
{
  const s = content("Pilot-ready after two admin steps, not production-ready", "Readiness and next steps",
    "Scorecard by area. Everything a small pilot needs is in place except two admin steps that take minutes. Production use needs security controls and internal document formats. Bridge: and if it needs to grow?");
  table(s, ["Area", "Status", "Basis"], [
    ["Answer quality and refusals", OK("Ready"), "85% of evidence stated; 0 invented claims"],
    ["Retrieval", OK("Ready (current corpus)"), "88% / 81% held-out; re-test at 10k+ documents"],
    ["Speed", OK("Within target"), "≈ 100 s per answer"],
    ["Memory stability", OK("Ready"), "Bounded; 75 live answers, 0 errors"],
    ["Privacy", WARN("Admin step"), "OLLAMA_NO_CLOUD + firewall rule"],
    ["Reliability", WARN("Admin step"), "Enable auto-start after reboot"],
    ["Security / multi-user", BAD("Not ready"), "No login, no access control, plain-text logs"],
    ["Document formats / scale", BAD("Not ready"), "PubMed XML only; one request at a time"],
  ], { colW: [3.4, 3.0, 5.7], fontSize: 14 });
}

// ---------------------------------------------------------------- 19 Scale
{
  const s = content("What it takes to scale", "Readiness and next steps",
    "Only the current VM row is measured; laptop and server rows are estimates to confirm on real hardware. Storage is cheap; the AI's speed and the number of simultaneous users are what require bigger hardware. At larger corpus sizes, retrieval quality must be re-tested. Details in appendix A3 and A4.");
  table(s, ["Hardware", "Answer time", "Users", "Capacity (documents)", "Basis"], [
    ["16 GB laptop (Qwen 3 4B)", "1.5–3 min", "1", "15–30k", "est."],
    ["32 GB laptop", "1.5–2 min", "1–2", "≈ 150k", "est."],
    [{ text: "Current VM, 16 GB", options: { bold: true } }, { text: "≈ 100 s", options: { bold: true } }, { text: "5–10", options: { bold: true } }, { text: "+12k more (disk-bound)", options: { bold: true } }, OK("measured")],
    ["Department server, 1 GPU", "10–20 s", "100–150", "1M+", "est."],
  ], { colW: [3.6, 2.2, 1.6, 3.0, 1.7], fontSize: 14 });
  const W = 3.9, G = 0.2;
  stat(s, 0.6, 4.1, W, 1.5, "0.53 GB", "disk per 1,000 documents (≈ 20 pages each)", C.accent1, "disk");
  stat(s, 0.6 + (W + G), 4.1, W, 1.5, "64 MB", "RAM per 1,000 documents", C.accent1, "ram");
  stat(s, 0.6 + 2 * (W + G), 4.1, W, 1.5, "≈ 45 min", "indexing per 1,000 documents (this VM)", C.accent2, "index");
}

// ---------------------------------------------------------------- 20 Next steps + decisions
{
  const s = content("Remaining work and decisions requested", "Readiness and next steps",
    "Close with the plan and the three decisions. Effort estimates still to be filled.");
  table(s, ["When", "Work", "Why"], [
    ["Now", "Block Ollama egress · enable auto-start · add swap", "Privacy, reliability"],
    ["Next", "Login, access control, retention policy", "Multi-user safety"],
    ["Next", "PDF / DOCX ingestion + retrieval re-test at scale", "Internal documents"],
    ["Next", "Answer structure + claim-level citations", "The 15% omission gap"],
    ["Later", "GPU server, parallel requests", "Speed, concurrency"],
  ], { w: 7.6, colW: [0.9, 4.4, 2.3], fontSize: 14 });
  const ds = [["1", "Approve a pilot", "3–5 researchers, current VM"], ["2", "Approve next work package", "Security + formats + answer structure"], ["3", "GPU server?", "≈ 10–20 s answers, 100+ users (est.)"]];
  ds.forEach(([k, h, d], i) => {
    const y = 1.35 + i * 1.45;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.5, y, w: 4.2, h: 1.25, rectRadius: 0.08, fill: { color: C.text2 }, line: { color: C.text2 }, objectName: "decision " + k });
    s.addText([{ text: "Decision " + k + " · " + h, options: { bold: true, fontSize: 16, color: C.background1, breakLine: true } }, { text: d, options: { fontSize: 14, color: C.background2 } }],
      { x: 8.7, y: y + 0.1, w: 3.8, h: 1.05, valign: "middle", margin: 0, isTextBox: true, objectName: "decision text " + k });
  });
}

// ---------------------------------------------------------------- Appendix
pres.addSection({ title: "Appendix" });
{
  const s = content("Appendix A1 · Full model comparison", "Appendix",
    "Identical stored evidence, 8 threads, 8K context, temperature 0. Facts = adjudicated facts stated on 14 single-paper screening questions (40 facts). Full 40-answer set: Qwen 2.5 7B 85%, Qwen 3 8B 81%.");
  table(s, ["Model", "Facts / 40", "Median", "p90", "RAM", "Disk", "Read tok/s", "Write tok/s", "Answer tok", "Verdict"], [
    [{ text: "Qwen 2.5 7B Q4", options: { bold: true } }, "32", "90 s", "106 s", "5.2 GB", "4.7 GB", "77", "7.3", "370", OK("Selected")],
    ["Qwen 2.5 7B Q8", "28", "116 s", "144 s", "9.2 GB", "8.1 GB", "53", "6.2", "326", BAD("No gain")],
    ["Qwen 3 4B", "34", "128 s", "165 s", "4.0 GB", "2.5 GB", "101", "6.9", "616", WARN("Verbose")],
    ["Qwen 3 8B", "32", "160 s", "201 s", "6.4 GB", "5.2 GB", "65", "4.9", "566", BAD("Slower")],
    ["Llama 3.1 8B", "27", "127 s", "147 s", "6.0 GB", "4.9 GB", "67", "5.4", "378", BAD("Weaker")],
    ["Gemma 3 12B", "33", "215 s", "244 s", "9.8 GB", "8.2 GB", "43", "4.2", "594", BAD("Too slow")],
    ["Phi-4 14B", "33", "224 s", "256 s", "10.5 GB", "9.1 GB", "36", "3.3", "442", BAD("Too slow")],
  ], { colW: [1.9, 1.0, 0.95, 0.95, 1.05, 1.0, 1.2, 1.25, 1.2, 1.6], fontSize: 13 });
}
{
  const s = content("Appendix A2 · Why the remaining fact loss persists", "Appendix",
    "All on the same stored evidence. Conclusion: the model omits statistics it treats as peripheral, plus answer templates that sometimes do not fit the question.");
  table(s, ["Factor tested", "Experiment", "Result", "Conclusion"], [
    ["Model size / family", "6 models, 4–14B", "All within ± 2 facts except Llama (−5)", "Not model-limited"],
    ["Quantization", "Q4_K_M vs Q8_0", "32 vs 28 facts", "Q4 is not the cause"],
    ["Prompt structure", "One finding per bullet", "Citations 72% → 100%; facts 32 → 29", "Changes citations, not facts"],
    ["Context size", "8 vs 4 passages", "Retention 80% → 68%", "Fewer passages hurt"],
    ["Evidence order", "Ranked vs reversed", "32 vs 30 facts", "No effect"],
    ["Answer length", "Short vs long answers", "78% vs 81%", "No effect"],
    ["Scoring", "Manual adjudication", "2 of 14 questions mis-scored", "Part of the 'loss' was scoring"],
  ], { colW: [2.4, 2.8, 4.0, 2.9], fontSize: 14 });
}
{
  const s = content("Appendix A3 · Company laptops by RAM", "Appendix",
    "Assumes office, browser and security software use 6–8 GB (est.). The assistant needs the AI model plus about 2 GB for the app. All laptop figures are estimates.");
  table(s, ["Laptop RAM", "Free for AI", "Qwen 3 4B (≈ 6 GB)", "Qwen 2.5 7B (≈ 7–10 GB)", "12–14B (≈ 12–13 GB)", "Verdict"], [
    ["8 GB", "≈ 1–2 GB", BAD("No"), BAD("No"), BAD("No"), BAD("Not supported")],
    ["16 GB", "≈ 8–10 GB", OK("Yes"), WARN("Close other apps"), BAD("No"), WARN("Single user")],
    ["32 GB", "≈ 24 GB", OK("Yes"), OK("Yes"), WARN("Fits, ≈ 4 min"), OK("Recommended")],
    ["64 GB", "≈ 56 GB", OK("Yes"), OK("Yes"), WARN("Fits, slow"), OK("Works; GPU better")],
  ], { colW: [1.5, 1.7, 2.1, 2.5, 2.2, 2.1], fontSize: 14 });
  table(s, ["Laptop", "Answer time (Qwen 2.5 7B)", "Documents (RAM-bound)"], [
    ["x86, 16 GB", "1.5–3 min", "15,000–30,000"],
    ["x86, 32 GB", "1.5–2 min", "≈ 150,000"],
    ["Apple Silicon 16–32 GB", "20–60 s", "15,000–150,000"],
  ], { y: 4.2, colW: [3.5, 4.3, 4.3], fontSize: 14 });
}
{
  const s = content("Appendix A4 · Storage capacity and per-MB cost", "Appendix",
    "Measured: 23.7 MB of indexed text occupies a 250 MB index; 0.53 MB per paper-sized document. System itself 8.9 GB. 20% of disk kept free; RAM limits capacity before disk on laptops (≈ 64 KB per document).");
  table(s, ["Input", "Disk", "RAM"], [
    ["1 MB of plain document text", "≈ 10.5 MB", "≈ 1.5 MB"],
    ["1 paper (~20 pages)", "0.53 MB", "≈ 64 KB"],
    ["1,000 papers", "0.53 GB (0.95 GB with backup)", "64 MB"],
  ], { w: 5.9, colW: [2.6, 2.1, 1.2], fontSize: 13 });
  table(s, ["Free disk", "Documents (no backup)", "With backup"], [
    ["20 GB", "≈ 13,000", "≈ 7,500"],
    ["50 GB", "≈ 58,000", "≈ 33,000"],
    ["100 GB", "≈ 134,000", "≈ 75,000"],
    ["250 GB", "≈ 360,000*", "≈ 200,000*"],
  ], { x: 6.8, w: 5.9, colW: [1.7, 2.2, 2.0], fontSize: 13 });
  table(s, ["Corpus", "Disk", "With backup", "Index RAM", "Indexing"], [
    ["10,000 papers", "5.3 GB", "9.5 GB", "0.64 GB", "≈ 7.5 h"],
    ["50,000 papers", "27 GB", "48 GB", "3.2 GB", "≈ 37 h"],
    ["100,000 papers", "53 GB", "95 GB", "6.4 GB", "≈ 3 days"],
  ], { y: 4.0, colW: [2.6, 2.2, 2.4, 2.4, 2.5], fontSize: 13 });
  textBox(s, [{ text: "* needs ≈ 23 GB RAM for the index — more than a 16 or 32 GB laptop can spare", options: { bullet: false } }], { x: 6.8, y: 3.3, w: 5.9, h: 0.5, fontSize: 12 });
}
{
  const s = content("Appendix A5 · Risk register", "Appendix",
    "Severity = impact if it happens; probability on a 16 GB host running continuously. Status as of 2026-10-19.");
  table(s, ["Risk", "Severity", "Probability", "Mitigation", "Status"], [
    ["Prompt-cache memory growth", "High", "High (before fix)", "Reload policy + start-up reset", OK("Mitigated, measured")],
    ["Ollama outbound to ollama.com", "High", "Certain", "OLLAMA_NO_CLOUD=1 + firewall", WARN("Admin step")],
    ["No authentication / access control", "High", "Certain if multi-user", "Reverse proxy + SSO; access rules", BAD("Open")],
    ["Plain-text question / answer logs", "Medium", "Certain", "Retention policy; disk encryption", BAD("Open")],
    ["One request at a time", "Medium", "High with 2+ users", "GPU server / parallel requests", BAD("Open")],
    ["Auto-start disabled", "Medium", "High after reboot", "systemctl enable pharma-rag", WARN("Admin step")],
    ["Retrieval at larger corpus", "Medium", "Medium at 10k+ docs", "Re-test at target size", BAD("Open")],
    ["Small, single-labeler benchmark", "Medium", "—", "More questions; second reviewer", BAD("Open")],
  ], { colW: [3.3, 1.2, 2.1, 3.4, 2.1], fontSize: 13 });
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT, n, "slides");
})();
