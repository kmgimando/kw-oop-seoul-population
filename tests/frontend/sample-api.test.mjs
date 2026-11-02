import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { parseProfile, dataMode, districtOptions } from "../../static/js/config.js";
import { validateQuery, summarize, LatestRequest } from "../../static/js/model.js";
import { adaptResponse } from "../../static/js/adapter.js";
import { populationConfig, comparisonConfig } from "../../static/js/charts.js";
import { fetchHttp } from "../../static/js/api.js";

const profile = { profile_version: 1, default_mode: "api", districts: [["11110", "종로구"], ["11680", "강남구"]],
  start_date: "2026-01-01", end_date: "2026-02-09", source: { kind: "synthetic_sample", label: "합성 샘플 CSV" } };
test("runtime profile limits API coverage to two sample districts", () => {
  const parsed = parseProfile(JSON.stringify(profile));
  assert.deepEqual(districtOptions("api", parsed), profile.districts);
  assert.equal(districtOptions("mock", parsed).length, 25);
  assert.equal(districtOptions("api", null).length, 0);
});
test("launcher can default API; explicit Mock and standalone static Mock are retained", () => {
  assert.equal(dataMode("", profile), "api");
  assert.equal(dataMode("?source=mock", profile), "mock");
  assert.equal(dataMode("?source=api"), "api");
  assert.equal(dataMode(), "mock");
});
test("missing, malformed or non-sample profile cannot advertise API coverage", () => {
  for (const text of ["{{ unrendered_template }}", "{}", "null", JSON.stringify({ ...profile, source: { kind: "real" } }),
    JSON.stringify({ ...profile, districts: [] }), JSON.stringify({ ...profile, districts: [[11110, "종로구"]] })]) {
    assert.equal(parseProfile(text), null);
  }
});

const evidence = process.env.SAMPLE_API_EVIDENCE
  ? JSON.parse(await readFile(process.env.SAMPLE_API_EVIDENCE, "utf8")) : null;
const offline = { skip: evidence ? false : "Generate SAMPLE_API_EVIDENCE with export_sample_api_evidence.py" };
test("sample API queries reject unsupported districts before transport", offline, () => {
  const q = structuredClone(evidence.cases[0].query);
  validateQuery(q, profile.districts);
  q.district_code = "11440";
  assert.throws(() => validateQuery(q, profile.districts), /지원되는/);
});
test("actual Flask JSON passes adapter without changing numbers, nulls or details", offline, () => {
  assert.equal(evidence.source_kind, "synthetic_sample");
  assert.equal(evidence.source_unchanged, true);
  for (const c of evidence.cases) {
    const data = adaptResponse(c.payload, c.query);
    for (const block of c.payload.methods) {
      assert.deepEqual(data.methods[block.method].results, block.results);
      assert.deepEqual(data.methods[block.method].details, block.details);
    }
  }
});
test("chart inputs and comparison statistics equal Python/API results", offline, () => {
  for (const c of evidence.cases) {
    const data = adaptResponse(c.payload, c.query);
    const bars = comparisonConfig(data.methods);
    Object.values(data.methods).forEach((block, i) => {
      const chart = populationConfig(block.results, () => {});
      ["lower_bound", "upper_bound", "actual", "expected"].forEach((key, index) => {
        assert.deepEqual(chart.data.datasets[index].data, block.results.map(row => row[key]));
      });
      assert.deepEqual(summarize(block.results), c.stats[block.method]);
      assert.equal(bars.data.datasets[0].data[i], c.stats[block.method].anomaly);
    });
  }
});

const base = process.env.SAMPLE_API_BASE_URL;
const live = { skip: base && evidence ? false : "Set SAMPLE_API_BASE_URL and SAMPLE_API_EVIDENCE", timeout: 60000 };
const read = (query, init = {}) => fetchHttp(query, { ...init, fetchImpl: (url, options) => fetch(new URL(url, base), options) });
test("live sample HTTP responses match direct Python for all query configurations", live, async () => {
  for (const c of evidence.cases) assert.deepEqual(await read(c.query), c.payload, `${c.label} ${c.query.district_code}`);
});
test("live sample HTTP returns clear errors instead of Mock fallback", live, async () => {
  const q = structuredClone(evidence.cases[0].query);
  q.district_code = "11440";
  await assert.rejects(read(q), /자치구/);
  q.district_code = "11110"; q.methods.seasonal = {};
  await assert.rejects(read(q), /필요합니다/);
  const response = await fetch(new URL("/api/no-such-route", base));
  assert.equal(response.status, 404);
});
test("older live HTTP response cannot overwrite the latest district", live, async () => {
  const first = structuredClone(evidence.cases[0].query);
  const second = structuredClone(first); second.district_code = "11680";
  const requests = new LatestRequest(async (q, init) => adaptResponse(await read(q, init), q));
  const old = requests.run(first), latest = requests.run(second);
  assert.equal((await old).stale, true);
  const response = await latest;
  assert.equal(response.stale, false);
  assert.ok(response.data.methods.seasonal.results.every(row => row.district_code === "11680"));
});
