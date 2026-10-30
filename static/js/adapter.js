import { isISODate } from "./model.js";
import { METHODS } from "./config.js";

const fail = () => { throw new Error("응답 데이터 형식이 올바르지 않습니다. API 계약을 확인하세요."); };
const numeric = value => typeof value === "number" && Number.isFinite(value);
const nullable = value => value === null || numeric(value);

// The only module that should change when ReportGenerator's wire schema settles.
export function adaptResponse(payload, query) {
  if (!payload || payload.schema_version !== 1 || !Array.isArray(payload.methods)) fail();
  const methods = {};
  for (const block of payload.methods) {
    if (!Object.hasOwn(METHODS, block.method) || methods[block.method] || !Array.isArray(block.results)) fail();
    const settings = query.methods[block.method];
    if (!block.settings || block.settings.window !== settings.window || block.settings.threshold !== settings.threshold ||
        (block.method === "seasonal" && block.settings.min_samples !== settings.min_samples)) fail();
    const seen = new Set();
    const results = block.results.map(row => {
      if (!row || !isISODate(row.date) || row.date < query.start_date || row.date > query.end_date ||
          row.district_code !== query.district_code || typeof row.district_name !== "string" ||
          row.method !== block.method || !numeric(row.actual) || row.actual < 0 ||
          ![true, false, null].includes(row.is_anomaly) || typeof row.status !== "string" ||
          !Number.isInteger(row.history_size) || row.history_size < 0 ||
          row.history_size > settings.window || row.threshold !== settings.threshold ||
          !["expected", "lower_bound", "upper_bound", "score", "deviation_ratio"].every(key => nullable(row[key])) ||
          seen.has(row.date)) fail();
      if (row.is_anomaly !== null && (row.expected === null || row.lower_bound === null || row.upper_bound === null)) fail();
      seen.add(row.date);
      return { ...row };
    }).sort((a, b) => a.date.localeCompare(b.date));
    const details = {};
    for (const [day, info] of Object.entries(block.details ?? {})) {
      if (!seen.has(day) || !info || (info.explanation != null && typeof info.explanation !== "string")) fail();
      const indicators = info.indicators ?? {};
      if (!["external_inflow", "interdistrict_movement"].every(key => indicators[key] === undefined || nullable(indicators[key]))) fail();
      details[day] = { explanation: info.explanation ?? null, indicators };
    }
    methods[block.method] = { method: block.method, settings: { ...settings }, results, details };
  }
  if (Object.keys(methods).length !== Object.keys(METHODS).length) fail();
  return { query: structuredClone(query), methods };
}
