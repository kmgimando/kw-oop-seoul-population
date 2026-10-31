// Actual API URL and top-level JSON schema are PROVISIONAL. No API is live.
export const CONFIG = Object.freeze({ mode: "mock", apiUrl: "/api/analysis" });
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
