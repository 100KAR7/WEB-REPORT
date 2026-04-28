const runsBody = document.getElementById("runs-body");
const detailsEl = document.getElementById("run-details");
const statusEl = document.getElementById("submit-status");

async function fetchRuns() {
  const resp = await fetch("/v1/runs?limit=30");
  if (!resp.ok) throw new Error("Failed to load runs");
  const payload = await resp.json();
  renderRuns(payload.items || []);
}

function renderRuns(items) {
  if (!items.length) {
    runsBody.innerHTML = '<tr><td colspan="5">No runs yet.</td></tr>';
    return;
  }

  runsBody.innerHTML = "";
  for (const run of items) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${run.id}</td>
      <td title="${run.target_url}">${run.target_url}</td>
      <td>${run.status}</td>
      <td>${new Date(run.created_at).toLocaleString()}</td>
      <td>${run.report_url ? `<a href="${run.report_url}" target="_blank">Open</a>` : "-"}</td>
    `;
    tr.onclick = () => selectRun(run.id);
    runsBody.appendChild(tr);
  }
}

async function selectRun(runId) {
  const resp = await fetch(`/v1/runs/${runId}`);
  if (!resp.ok) {
    detailsEl.textContent = `Failed to load run ${runId}`;
    return;
  }
  const run = await resp.json();
  detailsEl.textContent = JSON.stringify(run, null, 2);
}

async function submitRun(event) {
  event.preventDefault();
  statusEl.textContent = "Submitting run...";
  const payload = {
    url: document.getElementById("url").value,
    max_pages: Number(document.getElementById("max_pages").value),
    format: document.getElementById("format").value,
    no_ai: document.getElementById("no_ai").checked,
    no_seo: document.getElementById("no_seo").checked,
    no_perf: document.getElementById("no_perf").checked,
  };

  const resp = await fetch("/v1/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await resp.json();
  if (!resp.ok) {
    statusEl.textContent = `Error: ${data.detail || "Run creation failed"}`;
    return;
  }
  statusEl.textContent = `Run #${data.run_id} queued.`;
  await fetchRuns();
}

document.getElementById("run-form").addEventListener("submit", submitRun);
document.getElementById("refresh-btn").addEventListener("click", fetchRuns);

fetchRuns();
setInterval(fetchRuns, 5000);
