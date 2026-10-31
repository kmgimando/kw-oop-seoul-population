import { DISTRICTS, METHODS } from "./config.js";

let fixturePromise;
function delay(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException("Aborted", "AbortError"));
    const aborted = () => { clearTimeout(timer); reject(new DOMException("Aborted", "AbortError")); };
    const timer = setTimeout(() => { signal?.removeEventListener("abort", aborted); resolve(); }, ms);
    signal?.addEventListener("abort", aborted, { once: true });
  });
}
async function loadFixture() {
  if (!fixturePromise) fixturePromise = fetch(new URL("../mock/detection-fixtures.json", import.meta.url))
    .then(response => { if (!response.ok) throw new Error("Mock JSON 파일을 불러올 수 없습니다."); return response.json(); })
    .catch(error => { fixturePromise = undefined; throw error; });
  return fixturePromise;
}

// No detector is reimplemented in JS: expected/score/scales come from Python.
// Only presentation-fixture scaling, threshold ranges and min_samples masking
// are applied here. These are synthetic examples, not real district estimates.
export function buildMockResponse(fixture, query) {
  const districtIndex = DISTRICTS.findIndex(([code]) => code === query.district_code);
  const [code, name] = DISTRICTS[districtIndex];
  const factor = 1 + districtIndex * 0.045;
  const dataset = fixture.datasets[query.scenario === "zero" ? "zero" : "mixed"];
  const methods = Object.keys(METHODS).map(method => {
    const settings = query.methods[method];
    const fixtureBlock = dataset[method][settings.window];
    const details = {};
    const results = query.scenario === "empty" ? [] : fixtureBlock.results.flatMap((entry, i) => {
      if (entry.date < query.start_date || entry.date > query.end_date) return [];
      const row = { ...entry, district_code: code, district_name: name, threshold: settings.threshold };
      for (const field of ["actual", "expected", "lower_bound", "upper_bound"]) {
        if (row[field] !== null) row[field] *= factor;
      }
      if (method === "seasonal" && fixtureBlock.matching_samples[i] < settings.min_samples) {
        for (const field of ["expected", "lower_bound", "upper_bound", "score", "deviation_ratio", "is_anomaly"]) row[field] = null;
        row.status = "insufficient_history";
      } else if (row.is_anomaly !== null) {
        const scale = fixtureBlock.scales[i] * factor;
        row.lower_bound = Math.max(0, row.expected - settings.threshold * scale);
        row.upper_bound = row.expected + settings.threshold * scale;
        row.is_anomaly = row.score === null ? row.actual !== row.expected : Math.abs(row.score) > settings.threshold;
      }
      details[row.date] = { explanation: row.is_anomaly === true ? "합성 데이터에서 기준 범위를 벗어난 날짜입니다. 실제 사건이나 원인을 의미하지 않습니다." : null,
        indicators: { external_inflow: null, interdistrict_movement: null } };
      return [row];
    });
    return { method, settings: { ...settings }, results, details };
  });
  return { schema_version: 1, methods };
}
export async function fetchMock(query, { signal } = {}) {
  await delay(query.scenario === "slow" ? 2500 : 180, signal);
  if (query.scenario === "error") throw new Error("시연용 오류 응답: 분석 데이터를 불러오지 못했습니다. 시나리오를 바꿔 다시 실행하세요.");
  const fixture = await loadFixture();
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  return buildMockResponse(fixture, query);
}
