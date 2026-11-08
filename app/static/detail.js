// The detail page: fetch one parallel (in the same filtered/sorted context
// the list page was showing), render both full documents side by side with
// the matched passage highlighted and scrolled into view, and let the
// researcher record a decision.

const params = parseQueryString();
const parallelId = params.id;
const navFilters = sharedFilters(params); // everything except `id` itself

let currentStatus = null;

function renderColumn(doc, start, end, diffSpans) {
  const before = escapeHtml(doc.content.slice(0, start));
  const matched = renderMatchedPassage(doc.content, start, end, diffSpans);
  const after = escapeHtml(doc.content.slice(end));
  return `
    <div class="column">
      <h2>${titleCase(doc.slug)}</h2>
      <div class="text">${before}<mark>${matched}</mark>${after}</div>
    </div>
  `;
}

// The matched passage, with the words that differ from the other side
// (diffSpans: [start, end) offsets into the full document, from the API)
// wrapped in a second, stronger highlight nested inside the passage's own.
function renderMatchedPassage(content, start, end, diffSpans) {
  let html = "";
  let cursor = start;
  for (const [spanStart, spanEnd] of diffSpans) {
    html += escapeHtml(content.slice(cursor, spanStart));
    html += `<span class="diff">${escapeHtml(content.slice(spanStart, spanEnd))}</span>`;
    cursor = spanEnd;
  }
  return html + escapeHtml(content.slice(cursor, end));
}

function setActiveStatusButton(status) {
  currentStatus = status;
  document.querySelectorAll(".status-buttons button").forEach((button) => {
    button.classList.toggle("active", button.dataset.status === status);
  });
}

function navigateTo(id) {
  location.href = "/detail.html" + toQueryString({ ...navFilters, id });
}

async function loadDetail() {
  if (!parallelId) {
    document.getElementById("body").innerHTML = '<p class="empty">No parallel id given.</p>';
    return;
  }

  document.getElementById("backLink").href = "/" + toQueryString(navFilters);

  let data;
  try {
    data = await apiGet(`/parallels/${parallelId}` + toQueryString(navFilters));
  } catch (err) {
    document.getElementById("body").innerHTML = `<p class="empty">Failed to load: ${escapeHtml(err.message)}</p>`;
    return;
  }

  document.title = `${titleCase(data.doc_a.slug)} ↔ ${titleCase(data.doc_b.slug)} — Text Parallels Explorer`;

  document.getElementById("reviewPanel").hidden = false;
  document.getElementById("scoreValue").textContent = data.score.toFixed(2);
  document.getElementById("typeValue").textContent = data.match_type + (data.is_stale ? " · stale" : "");
  document.getElementById("noteField").value = data.note || "";
  setActiveStatusButton(data.status);
  document.getElementById("diffLegend").hidden = data.diff_a.length + data.diff_b.length === 0;

  document.getElementById("body").innerHTML = `
    <div class="columns">
      ${renderColumn(data.doc_a, data.a_start, data.a_end, data.diff_a)}
      ${renderColumn(data.doc_b, data.b_start, data.b_end, data.diff_b)}
    </div>
  `;
  document.querySelectorAll(".column mark").forEach((mark) => mark.scrollIntoView({ block: "center" }));

  document.getElementById("prevButton").disabled = data.prev_id === null;
  document.getElementById("prevButton").onclick = () => navigateTo(data.prev_id);
  document.getElementById("nextButton").disabled = data.next_id === null;
  document.getElementById("nextButton").onclick = () => navigateTo(data.next_id);
}

async function setStatus(status) {
  const previous = currentStatus;
  setActiveStatusButton(status); // optimistic
  try {
    await apiPatch(`/parallels/${parallelId}`, { status });
  } catch (err) {
    setActiveStatusButton(previous);
    alert(`Could not update status: ${err.message}`);
  }
}

document.querySelectorAll(".status-buttons button").forEach((button) => {
  button.addEventListener("click", () => setStatus(button.dataset.status));
});

document.getElementById("saveNoteButton").addEventListener("click", async () => {
  const saveState = document.getElementById("saveState");
  saveState.textContent = "Saving...";
  try {
    await apiPatch(`/parallels/${parallelId}`, { note: document.getElementById("noteField").value });
    saveState.textContent = "Saved";
    setTimeout(() => (saveState.textContent = ""), 1500);
  } catch (err) {
    saveState.textContent = `Failed: ${err.message}`;
  }
});

// Keyboard review: j/k move through the same filtered set the prev/next
// buttons do (by clicking them, so a disabled button is a no-op); a/r/p set
// the status. Deliberately no auto-advance after a/r -- the researcher sees
// the badge change before moving on with j. Ignored while typing a note.
const KEY_ACTIONS = {
  j: () => document.getElementById("nextButton").click(),
  k: () => document.getElementById("prevButton").click(),
  a: () => setStatus("approved"),
  r: () => setStatus("rejected"),
  p: () => setStatus("pending"),
};

document.addEventListener("keydown", (event) => {
  if (event.target.closest("input, textarea, select")) return;
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  const action = KEY_ACTIONS[event.key.toLowerCase()];
  if (action && !document.getElementById("reviewPanel").hidden) {
    event.preventDefault();
    action();
  }
});

loadDetail();
