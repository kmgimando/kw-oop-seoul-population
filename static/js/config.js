// Supported regions and dates come from the loaded CSV Repository.
// Static previews continue to default Mock.
function profileDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith("0000")) return false;
  const day = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(day.getTime()) && day.toISOString().slice(0, 10) === value;
}
export function parseProfile(text) {
  try {
    const profile = JSON.parse(text);
    if (profile.profile_version !== 1 || !["synthetic_sample", "seoul_population"].includes(profile.source?.kind) ||
        typeof profile.source.label !== "string" || !Array.isArray(profile.districts) ||
        !profile.districts.length || !profile.districts.every(item => Array.isArray(item) && item.length === 2 &&
          typeof item[0] === "string" && /^\d{5}$/.test(item[0]) && typeof item[1] === "string") ||
        new Set(profile.districts.map(item => item[0])).size !== profile.districts.length ||
        !profileDate(profile.start_date) || !profileDate(profile.end_date) ||
        profile.start_date > profile.end_date) return null;
    const first = profile.default_start_date ?? profile.start_date;
    const last = profile.default_end_date ?? profile.end_date;
    if (!profileDate(first) || !profileDate(last) ||
        first < profile.start_date || last > profile.end_date || first > last) return null;
    if (profile.missing_dates !== undefined && (!Array.isArray(profile.missing_dates) ||
        !profile.missing_dates.every(profileDate))) return null;
    return profile;
  } catch { return null; }
}
export function sourcePresentation(profile) {
  const sample = profile.source.kind === "synthetic_sample";
  const range = `${profile.start_date} ~ ${profile.end_date}`;
  const missing = profile.missing_dates?.length
    ? ` 원자료 누락: ${profile.missing_dates.join(", ")}.` : "";
  return {
    label: sample ? "SAMPLE API" : "CSV API",
    title: sample ? "합성 샘플 CSV · Flask API" : "서울 생활인구 · 원본 CSV",
    description: sample
      ? `${profile.districts.map(item => item[1]).join("·")} / ${range}. 실제 서울시 분석 결과가 아닙니다.`
      : `${profile.districts.length}개 자치구 / ${range}. 처음에는 최근 90일을 표시합니다.${missing}`,
    empty: `조회된 기록이 없습니다. ${profile.source.label} 범위는 ${range}입니다.`,
  };
}
export function dataMode(search = "", profile = null) {
  const source = new URLSearchParams(search).get("source");
  if (source === "mock") return "mock";
  if (source === "api") return "api";
  return profile?.default_mode === "api" ? "api" : "mock";
}
const profile = parseProfile(globalThis.document?.getElementById("dashboard-profile")?.textContent ?? "{}");
export const CONFIG = Object.freeze({ mode: dataMode(globalThis.location?.search ?? "", profile), apiUrl: "/api/analysis", profile });
export function districtOptions(mode, profile) {
  return mode === "api" ? profile?.districts ?? [] : DISTRICTS;
}
export const WINDOWS = Object.freeze([7, 14, 28, 56]);
export const METHODS = Object.freeze({
  moving_average: { name: "이동평균", window: 7, threshold: 0.10, ratio: true },
  z_score: { name: "Z-score", window: 28, threshold: 3, ratio: false },
  seasonal: { name: "계절성", window: 28, threshold: 0.10, min_samples: 4, ratio: true },
});
export const DISTRICTS = Object.freeze([
  ["11110", "종로구"], ["11140", "중구"], ["11170", "용산구"],
  ["11200", "성동구"], ["11215", "광진구"], ["11230", "동대문구"],
  ["11260", "중랑구"], ["11290", "성북구"], ["11305", "강북구"],
  ["11320", "도봉구"], ["11350", "노원구"], ["11380", "은평구"],
  ["11410", "서대문구"], ["11440", "마포구"], ["11470", "양천구"],
  ["11500", "강서구"], ["11530", "구로구"], ["11545", "금천구"],
  ["11560", "영등포구"], ["11590", "동작구"], ["11620", "관악구"],
  ["11650", "서초구"], ["11680", "강남구"], ["11710", "송파구"],
  ["11740", "강동구"],
]);
