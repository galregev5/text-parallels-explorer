// The list page: filter form <-> URL <-> GET /api/parallels <-> table.
// State lives in the form fields plus `offset`/`limit`; the URL is kept in
// sync with it (via replaceState) so the page is bookmarkable and a
// detail-page "back" lands exactly where it started.

const form = document.getElementById("filterForm");
let offset = 0;
let limit = 50;

function readFormFilters() {
  const data = new FormData(form);
  return {
    doc_a: data.get("doc_a") || null,
    doc_b: data.get("doc_b") || null,
    match_type: data.get("match_type") || null,
    status: data.get("status") || null,
    min_score: data.get("min_score") || null,
    max_score: data.get("max_score") || null,
    q: data.get("q") || null,
    latest_only: form.latest_only.checked,
    sort: data.get("sort") || "score_desc",
  };
}

function applyFiltersToForm(params) {
  for (const field of ["doc_a", "doc_b", "match_type", "status", "min_score", "max_score", "q", "sort"]) {
    if (params[field] !== undefined) form[field].value = params[field];
  }
  if (params.latest_only !== undefined) form.latest_only.checked = params.latest_only === "true";
  if (params.offset !== undefined) offset = parseInt(params.offset, 10) || 0;
  if (params.limit !== undefined) {
    limit = parseInt(params.limit, 10) || 50;
    document.getElementById("pageSize").value = String(limit);
  }
}

function currentState() {
  return { ...readFormFilters(), offset, limit };
}

function updateUrl() {
  const qs = toQueryString(currentState());
  history.replaceState(null, "", "/" + qs);
}

async function populateDocumentOptions() {
  const docs = await apiGet("/documents");
  for (const select of [form.doc_a, form.doc_b]) {
    for (const doc of docs) {
      const option = document.createElement("option");
      option.value = doc.id;
      option.textContent = titleCase(doc.slug);
      select.appendChild(option);
    }
  }
}

function renderRow(item) {
  const tr = document.createElement("tr");
  tr.dataset.id = item.id;
  tr.innerHTML = `
    <td>${titleCase(item.doc_a.slug)} &harr; ${titleCase(item.doc_b.slug)}</td>
    <td class="snippet">
      <div class="side"><strong>${titleCase(item.doc_a.slug)}:</strong> ${escapeHtml(item.snippet_a)}</div>
      <div class="side"><strong>${titleCase(item.doc_b.slug)}:</strong> ${escapeHtml(item.snippet_b)}</div>
    </td>
    <td>${item.score.toFixed(2)}</td>
    <td class="match-type">${item.match_type}</td>
    <td>
      <span class="badge ${item.status}">${item.status}</span>
      ${item.is_stale ? '<span class="badge stale">stale</span>' : ""}
    </td>
  `;
  tr.addEventListener("click", () => {
    const target = "/detail.html" + toQueryString({ ...sharedFilters(currentState()), id: item.id });
    location.href = target;
  });
  return tr;
}

async function loadList() {
  const rowsEl = document.getElementById("rows");
  rowsEl.innerHTML = '<tr><td colspan="5" class="loading">Loading...</td></tr>';
  updateUrl();

  let data;
  try {
    data = await apiGet("/parallels" + toQueryString(currentState()));
  } catch (err) {
    rowsEl.innerHTML = `<tr><td colspan="5" class="empty">Failed to load: ${escapeHtml(err.message)}</td></tr>`;
    return;
  }

  rowsEl.innerHTML = "";
  if (data.items.length === 0) {
    rowsEl.innerHTML = '<tr><td colspan="5" class="empty">No parallels match these filters.</td></tr>';
  } else {
    for (const item of data.items) rowsEl.appendChild(renderRow(item));
  }

  const shown = data.items.length;
  const from = shown ? offset + 1 : 0;
  const to = offset + shown;
  document.getElementById("pageCount").textContent = `${from}-${to} of ${data.total}`;
  document.getElementById("prevPage").disabled = offset <= 0;
  document.getElementById("nextPage").disabled = to >= data.total;

  const banner = document.getElementById("staleBanner");
  if (data.stale_count > 0) {
    banner.hidden = false;
    banner.textContent =
      `${data.stale_count} parallel(s) are left over from an earlier analysis run with different ` +
      `parameters or corpus content, and were not confirmed by the most recent run. ` +
      `Check "Latest run only" to hide them, or Re-run analysis.`;
  } else {
    banner.hidden = true;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  offset = 0;
  loadList();
});

document.getElementById("resetButton").addEventListener("click", () => {
  form.reset();
  offset = 0;
  loadList();
});

document.getElementById("prevPage").addEventListener("click", () => {
  offset = Math.max(0, offset - limit);
  loadList();
});
document.getElementById("nextPage").addEventListener("click", () => {
  offset += limit;
  loadList();
});
document.getElementById("pageSize").addEventListener("change", (event) => {
  limit = parseInt(event.target.value, 10);
  offset = 0;
  loadList();
});

document.getElementById("rerunButton").addEventListener("click", async (event) => {
  const button = event.target;
  button.disabled = true;
  const meta = document.getElementById("runMeta");
  meta.textContent = "Re-running...";
  try {
    const result = await apiPost("/rerun");
    meta.textContent = result.ran
      ? `Run #${result.run_id}: ${result.total_parallels} parallels (${result.stale_count} stale)`
      : `Already up to date (run #${result.run_id})`;
    await loadList();
  } catch (err) {
    meta.textContent = `Re-run failed: ${err.message}`;
  } finally {
    button.disabled = false;
  }
});

(async function init() {
  applyFiltersToForm(parseQueryString());
  await populateDocumentOptions();
  applyFiltersToForm(parseQueryString()); // re-apply: options now exist to select
  await loadList();
})();
