import { CONFIG, districtOptions, METHODS } from "./config.js";
import { fetchAnalysis } from "./api.js";
import { LatestRequest, validateQuery, summarize, number, percent, settingLabel, stateOf, STATE_LABELS, STATUS_LABELS } from "./model.js";
import { renderCharts, highlightDate } from "./charts.js";

const $ = id => document.getElementById(id);
const create = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};
const badge = row => create("span", STATE_LABELS[stateOf(row)], `badge ${stateOf(row)}`);
const settings = Object.fromEntries(Object.entries(METHODS).map(([key, value]) => [key,
  { window: value.window, threshold: value.threshold, ...(key === "seasonal" ? { min_samples: value.min_samples } : {}) }]));
let activeMethod = "seasonal", currentData, selectedDate;
const requests = new LatestRequest(fetchAnalysis);
const districts = districtOptions(CONFIG.mode, CONFIG.profile);

function saveSettings() {
  settings[activeMethod] = { window: Number($("window").value),
    threshold: Number($("threshold").value) / (METHODS[activeMethod].ratio ? 100 : 1),
    ...(activeMethod === "seasonal" ? { min_samples: Number($("min-samples").value) } : {}) };
}
function updateMethodFields() {
  const info = METHODS[activeMethod], saved = settings[activeMethod];
  $("window").value = saved.window;
  $("threshold").value = info.ratio ? Number((saved.threshold * 100).toFixed(8)) : saved.threshold;
  $("threshold-label").textContent = info.ratio ? "임계값 (%)" : "임계값 (Z-score · σ)";
  $("min-samples-field").hidden = activeMethod !== "seasonal";
  $("min-samples").disabled = activeMethod !== "seasonal";
  if (activeMethod === "seasonal") $("min-samples").value = saved.min_samples;
  $("min-samples").max = saved.window;
  $("method-hint").textContent = activeMethod === "z_score"
    ? "과거 평균·모표준편차 기준 Z-score의 절댓값을 비교합니다. 3은 3σ이며 백분율이 아닙니다."
    : `${activeMethod === "seasonal" ? "평일·주말을 나누어" : "직전 기간의"} 평균 대비 변동률을 비교합니다. 10%는 API 비율 0.10에 대응합니다.`;
}
function readQuery() {
  saveSettings();
  return validateQuery({ district_code: $("district").value, start_date: $("start-date").value,
    end_date: $("end-date").value, selected_method: activeMethod,
    methods: structuredClone(settings), scenario: $("scenario").value }, districts);
}
function feedback(kind, message) {
  $("feedback").dataset.kind = kind;
  $("feedback").setAttribute("role", kind === "error" ? "alert" : "status");
  $("feedback").textContent = message;
}
function currentBlock() { return currentData.methods[currentData.query.selected_method]; }
function renderDetail(day) {
  const block = currentBlock(), row = block.results.find(r => r.date === day);
  if (!row) return;
  selectedDate = day;
  const container = $("day-detail"); container.replaceChildren();
  const heading = create("div", undefined, "detail-date"); heading.append(create("span", day), badge(row));
  const list = create("dl");
  for (const [label, value] of [
    ["실제 생활인구", `${number(row.actual)}명`], ["기준값", row.expected === null ? "—" : `${number(row.expected)}명`],
    ["기준 대비 변동률", percent(row.deviation_ratio)], ["이상 점수", block.method === "z_score" ? number(row.score) : percent(row.score)],
    ["정상 범위", row.lower_bound === null ? "—" : `${number(row.lower_bound)} ~ ${number(row.upper_bound)}`],
    ["전체 과거 이력", `${row.history_size}일`], ["처리 상태", STATUS_LABELS[row.status] ?? row.status],
  ]) list.append(create("dt", label), create("dd", value));
  const explanation = create("section", undefined, "detail-explanation");
  explanation.append(create("h3", "참고 설명 및 이동 지표"));
  const info = block.details[day];
  explanation.append(create("p", info?.explanation ?? (row.is_anomaly === null ? "기준 계산에 필요한 과거 이력 또는 동일 그룹 표본이 부족합니다." : "이 날짜에 제공된 참고 설명이 없습니다.")));
  const indicators = info?.indicators;
  explanation.append(create("p", `서울 외 유입인구: ${number(indicators?.external_inflow)}\n자치구 간 이동인구: ${number(indicators?.interdistrict_movement)}`, "indicator-note"));
  explanation.lastChild.style.whiteSpace = "pre-line";
  explanation.append(create("p", "이동 지표 미제공 값은 —로 표시합니다. 지표의 동반 변화만으로 원인을 단정하지 않습니다."));
  container.append(heading, list, explanation);
  highlightDate(day);
  for (const tr of $("results-body").children) tr.classList.toggle("selected-day", tr.dataset.date === day);
}
function renderRows() {
  const block = currentBlock(), filter = $("status-filter").value;
  const rows = block.results.filter(row => filter === "all" || stateOf(row) === filter);
  const body = $("results-body"); body.replaceChildren();
  for (const row of rows) {
    const tr = create("tr"); tr.dataset.date = row.date;
    tr.classList.toggle("selected-day", row.date === selectedDate);
    const dateCell = create("td"), button = create("button", row.date, "date-button");
    button.type = "button"; button.setAttribute("aria-label", `${row.date} 상세 보기`);
    button.addEventListener("click", () => renderDetail(row.date)); dateCell.append(button); tr.append(dateCell);
    for (const value of [number(row.actual), number(row.expected), percent(row.deviation_ratio),
      block.method === "z_score" ? number(row.score) : percent(row.score),
      row.lower_bound === null ? "—" : `${number(row.lower_bound)} ~ ${number(row.upper_bound)}`]) tr.append(create("td", value));
    const stateCell = create("td"); stateCell.append(badge(row)); tr.append(stateCell);
    const statusCell = create("td", STATUS_LABELS[row.status] ?? row.status);
    statusCell.append(create("span", row.status, "setting-line raw-status")); tr.append(statusCell);
    body.append(tr);
  }
  if (!rows.length) { const tr = create("tr"), td = create("td", "선택한 상태에 해당하는 결과가 없습니다.", "empty-row"); td.colSpan = 8; tr.append(td); body.append(tr); }
  $("table-count").textContent = `전체 ${block.results.length}일 중 ${rows.length}일 표시 · history_size는 전체 연속 이력 수이며, 동일 그룹 표본 수와 다릅니다.`;
}
function renderComparison() {
  const body = $("comparison-body"); body.replaceChildren();
  for (const block of Object.values(currentData.methods)) {
    const tr = create("tr");
    if (block.method === currentData.query.selected_method) tr.className = "selected-method";
    const method = create("td", METHODS[block.method].name);
    method.append(create("span", settingLabel(block.method, block.settings), "setting-line")); tr.append(method);
    const stats = summarize(block.results);
    for (const value of [stats.anomaly, stats.normal, stats.unavailable, percent(stats.rate)]) tr.append(create("td", String(value)));
    body.append(tr);
  }
}
function renderData(data) {
  currentData = data;
  const block = currentBlock(), stats = summarize(block.results), q = data.query;
  if (!stats.total) {
    feedback("empty", CONFIG.mode === "mock"
      ? "조회된 데이터가 없습니다. 기간을 확인하거나 다른 시나리오로 다시 실행하세요. Mock 데이터 범위는 2024-01-01 ~ 2024-03-30입니다."
      : `조회된 기록이 없습니다. 합성 샘플 범위는 ${CONFIG.profile.start_date} ~ ${CONFIG.profile.end_date}입니다.`);
    return;
  }
  $("results").hidden = false;
  $("applied-query").textContent = `${districts.find(([code]) => code === q.district_code)[1]} · ${q.start_date} ~ ${q.end_date} · ${METHODS[q.selected_method].name} · ${settingLabel(q.selected_method, block.settings)}`;
  for (const [id, value] of [["total", stats.total], ["anomaly", stats.anomaly], ["normal", stats.normal], ["unavailable", stats.unavailable]]) $(`metric-${id}`).textContent = `${value}일`;
  $("metric-rate").textContent = `탐지율 ${percent(stats.rate)} · 판정 가능 ${stats.evaluated}일`;
  $("status-filter").value = "all";
  renderComparison(); renderRows();
  renderCharts(block, data.methods, renderDetail);
  renderDetail((block.results.find(row => row.is_anomaly === true) ?? block.results.find(row => row.is_anomaly === false) ?? block.results[0]).date);
  feedback("", "");
}
async function runAnalysis(event) {
  event?.preventDefault();
  let query;
  try { query = readQuery(); }
  catch (error) { requests.invalidate(); $("results").hidden = true; $("results").setAttribute("aria-busy", "false"); feedback("error", error.message); return; }
  $("results").hidden = true; $("results").setAttribute("aria-busy", "true");
  feedback("loading", "분석 결과를 불러오는 중입니다. 조건을 바꿔 다시 실행할 수 있습니다.");
  try {
    const response = await requests.run(query);
    if (response.stale) return;
    renderData(response.data);
    $("results").setAttribute("aria-busy", "false");
  } catch (error) {
    $("results").hidden = true;
    $("results").setAttribute("aria-busy", "false");
    feedback("error", error.message || "분석 요청 중 오류가 발생했습니다.");
  }
}

for (const [code, name] of districts) { const option = create("option", name); option.value = code; $("district").append(option); }
$("district").value = CONFIG.mode === "api" ? districts[0]?.[0] ?? "" : "11440";
$("method").addEventListener("change", () => { saveSettings(); activeMethod = $("method").value; updateMethodFields(); });
$("window").addEventListener("change", () => { $("min-samples").max = $("window").value; });
$("query-form").addEventListener("submit", runAnalysis);
$("status-filter").addEventListener("change", renderRows);
if (CONFIG.mode === "api") {
  $("scenario").closest("details").hidden = true;
  $("source-label").textContent = "SAMPLE API";
  $("coverage-label").textContent = `${districts.length}개 자치구 · 3가지 탐지 방법`;
  if (CONFIG.profile) {
    $("start-date").value = CONFIG.profile.start_date;
    $("end-date").value = CONFIG.profile.end_date;
    $("demo-banner").replaceChildren(create("strong", "합성 샘플 CSV · Flask API"),
      create("span", `${districts.map(item => item[1]).join("·")} / ${CONFIG.profile.start_date} ~ ${CONFIG.profile.end_date}. 실제 서울시 분석 결과가 아닙니다.`));
  }
}
updateMethodFields();
if (CONFIG.mode === "api" && !CONFIG.profile) {
  $("run-button").disabled = true;
  $("demo-banner").replaceChildren(create("strong", "API 지원 정보 없음"),
    create("span", "데이터 출처와 지원 지역을 확인할 수 없어 조회를 중단했습니다."));
  feedback("error", "API 데이터의 지원 정보를 받지 못했습니다. 샘플 대시보드 실행 방법을 확인하세요.");
} else runAnalysis();
