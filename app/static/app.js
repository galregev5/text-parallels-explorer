// Shared helpers for both pages. Plain vanilla JS, no build step, no framework:
// the whole UI is two static HTML pages that talk to the JSON API with fetch().

const API_BASE = "/api";

async function apiGet(path) {
  const res = await fetch(API_BASE + path);
  if (!res.ok) throw await apiError(res);
  return res.json();
}

async function apiPatch(path, body) {
  const res = await fetch(API_BASE + path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await apiError(res);
  return res.json();
}

async function apiPost(path) {
  const res = await fetch(API_BASE + path, { method: "POST" });
  if (!res.ok) throw await apiError(res);
  return res.json();
}

async function apiError(res) {
  let detail = res.statusText;
  try {
    detail = (await res.json()).detail ?? detail;
  } catch {
    /* body wasn't JSON; keep statusText */
  }
  return new Error(`${res.status} ${detail}`);
}

// Build a query string from an object, skipping null/undefined/""/false so
// a filter that isn't set doesn't clutter the URL or get sent to the API.
function toQueryString(params) {
  const parts = [];
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "" || value === false) continue;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(value)}`);
  }
  return parts.length ? "?" + parts.join("&") : "";
}

function parseQueryString() {
  const params = {};
  for (const [key, value] of new URLSearchParams(location.search)) {
    params[key] = value;
  }
  return params;
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Filter/sort keys the two pages share: the detail page's prev/next
// navigation only makes sense computed against the SAME set the list page
// was showing, so both pages read and pass around exactly this set.
const SHARED_FILTER_KEYS = [
  "doc", "doc_a", "doc_b", "match_type", "status",
  "min_score", "max_score", "q", "latest_only", "sort",
];

function sharedFilters(params) {
  const result = {};
  for (const key of SHARED_FILTER_KEYS) {
    if (params[key] !== undefined) result[key] = params[key];
  }
  return result;
}

function titleCase(slug) {
  return slug.charAt(0).toUpperCase() + slug.slice(1);
}
