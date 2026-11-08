// The detail page: fetch one parallel (in the same filtered/sorted context
// the list page was showing), render both full documents side by side with
// the matched passage highlighted and scrolled into view, and let the
// researcher record a decision.

const params = parseQueryString();
const parallelId = params.id;
const navFilters = sharedFilters(params); // everything except `id` itself

let currentStatus = null;

function renderColumn(doc, start, end) {
  const before = escapeHtml(doc.content.slice(0, start));
  const matched = escapeHtml(doc.content.slice(start, end));
  const after = escapeHtml(doc.content.slice(end));
  return `
    <div class="column">
      <h2>${titleCase(doc.slug)}</h2>
      <div class="text">${before}<mark>${matched}</mark>${after}</div>
    </div>
  `;
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

  document.getElementById("body").innerHTML = `
    <div class="columns">
      ${renderColumn(data.doc_a, data.a_start, data.a_end)}
      ${renderColumn(data.doc_b, data.b_start, data.b_end)}
    </div>
  `;
  document.querySelectorAll("mark").forEach((mark) => mark.scrollIntoView({ block: "center" }));

  document.getElementById("prevButton").disabled = data.prev_id === null;
  document.getElementById("prevButton").onclick = () => navigateTo(data.prev_id);
  document.getElementById("nextButton").disabled = data.next_id === null;
  document.getElementById("nextButton").onclick = () => navigateTo(data.next_id);
}

document.querySelectorAll(".status-buttons button").forEach((button) => {
  button.addEventListener("click", async () => {
    const status = button.dataset.status;
    setActiveStatusButton(status); // optimistic
    try {
      await apiPatch(`/parallels/${parallelId}`, { status });
    } catch (err) {
      setActiveStatusButton(currentStatus);
      alert(`Could not update status: ${err.message}`);
    }
  });
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

// j/k-free keyboard support kept out deliberately -- it's a Phase 6
// candidate feature to propose and justify separately, not baseline.
loadDetail();
