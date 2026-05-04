// ---- helpers --------------------------------------------------
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

// ---- parsing --------------------------------------------------
function parseProgram(text) {
  const out = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || line.startsWith(";")) continue;
    const parts = line.split(/\s+/);
    const mnemonic = parts[0].toUpperCase();
    const operand = parts.length > 1 ? parseInt(parts[1], 10) : 0;
    if (Number.isNaN(operand)) throw new Error(`bad operand on line: ${line}`);
    out.push({ mnemonic, operand });
  }
  return out;
}

function parseData(text) {
  const out = {};
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const m = line.match(/^(\d+)\s*=\s*(\d+)$/);
    if (!m) throw new Error(`bad data line: ${line}`);
    out[parseInt(m[1], 10)] = parseInt(m[2], 10);
  }
  return out;
}

// ---- renderers -----------------------------------------------
function renderState({ registers, ram }) {
  const reg = $("#reg-table");
  reg.innerHTML = "";
  for (const k of ["pc", "mar", "ir", "a", "b", "alu", "out", "halted"]) {
    const v = registers[k] ?? 0;
    reg.innerHTML += `<tr><td>${k.toUpperCase()}</td><td>${v}</td><td>0x${v.toString(16).padStart(2, "0")}</td></tr>`;
  }
  const grid = $("#ram-grid");
  grid.innerHTML = "";
  ram.forEach((val, addr) => {
    const klass = addr < 12 ? "handler" : "scratch";
    grid.innerHTML += `<div class="cell ${klass}"><span class="addr">${addr}</span>${val}</div>`;
  });
}

function renderTrace(rows) {
  const tbody = $("#trace-table tbody");
  tbody.innerHTML = "";
  for (const r of rows) {
    tbody.innerHTML +=
      `<tr><td>${r.cycle}</td><td>${r.mnemonic}</td><td>${r.operand}</td>` +
      `<td>${r.a_before}</td><td>${r.a_after}</td><td>${r.out_after}</td>` +
      `<td>${r.t_states}</td></tr>`;
  }
}

function renderChunks(chunks) {
  const tbody = $("#chunks-table tbody");
  tbody.innerHTML = "";
  for (const c of chunks) {
    const body = c.body.map(b => `${b.mnemonic} ${b.operand ?? ""}`.trim()).join(" ; ");
    const params = c.params.length ? c.params.join(", ") : "—";
    tbody.innerHTML += `<tr><td>${c.name}</td><td>${params}</td><td>${body}</td><td>${c.description ?? ""}</td></tr>`;
  }
}

function renderVectors(vectors) {
  const tbody = $("#vectors-table tbody");
  tbody.innerHTML = "";
  for (const v of vectors) {
    tbody.innerHTML += `<tr><td>${v.event_type}</td><td>${v.handler_chunk}</td><td>${v.description ?? ""}</td></tr>`;
  }
}

function renderEventLog(events) {
  const tbody = $("#event-log-table tbody");
  tbody.innerHTML = "";
  for (const e of events) {
    const halted = e.halted_clean ? "yes" : "<span class='error'>no</span>";
    const err = e.error ? `<span class='error'>${e.error}</span>` : "";
    tbody.innerHTML +=
      `<tr><td>${e.id}</td><td>${e.event_type}</td>` +
      `<td>${e.handler_chunk ?? "—"}</td><td>${halted}</td>` +
      `<td>${e.cycles_used ?? ""}</td><td>${e.output_a ?? ""}</td>` +
      `<td>${e.output_out ?? ""}</td><td>${err}</td></tr>`;
  }
}

// ---- refresh helpers -----------------------------------------
async function refreshState() {
  const s = await api("/api/state");
  renderState(s);
}
async function refreshChunks() {
  const { chunks } = await api("/api/chunks");
  renderChunks(chunks);
}
async function refreshVectors() {
  const { vectors } = await api("/api/vectors");
  renderVectors(vectors);
}
async function refreshEventLog() {
  const { events } = await api("/api/event_log");
  renderEventLog(events);
}
async function refreshAll() {
  await Promise.all([refreshState(), refreshChunks(), refreshVectors(), refreshEventLog()]);
}

// ---- handlers ------------------------------------------------
$("#btn-reset").addEventListener("click", async () => {
  await api("/api/reset", { method: "POST" });
  $("#trace-table tbody").innerHTML = "";
  await refreshAll();
});

$("#btn-run").addEventListener("click", async () => {
  try {
    const instructions = parseProgram($("#program-input").value);
    const data = parseData($("#data-input").value);
    const result = await api("/api/program", {
      method: "POST",
      body: { instructions, data, reset_first: true },
    });
    renderState({ registers: result.registers, ram: result.ram });
    renderTrace(result.trace);
    await refreshChunks();
    await refreshVectors();
    await refreshEventLog();
  } catch (e) {
    alert("error: " + e.message);
  }
});

const examples = {
  add:     { p: "LDA 14\nADD 15\nOUT\nHLT",                        d: "14=3\n15=4" },
  sub:     { p: "LDA 14\nSUB 15\nOUT\nHLT",                        d: "14=5\n15=9" },
  loop:    { p: "LDA 14\nSUB 13\nJZ 5\nJMP 1\nHLT",                 d: "14=5\n13=1" },
  bitwise: { p: "LDA 14\nAND 15\nOUT\nHLT",                        d: "14=12\n15=10" },
};
$$("a[data-example]").forEach(a => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    const ex = examples[a.dataset.example];
    if (ex) { $("#program-input").value = ex.p; $("#data-input").value = ex.d; }
  });
});

$("#btn-vector").addEventListener("click", async () => {
  try {
    await api("/api/vectors", {
      method: "POST",
      body: {
        event_type:    $("#vec-event").value,
        handler_chunk: $("#vec-handler").value,
      },
    });
    await refreshVectors();
  } catch (e) { alert("error: " + e.message); }
});

$("#btn-fire").addEventListener("click", async () => {
  try {
    const result = await api("/api/event", {
      method: "POST",
      body: { event_type: $("#ev-event").value },
    });
    renderState({ registers: result.registers, ram: result.ram });
    await refreshEventLog();
  } catch (e) { alert("error: " + e.message); }
});

$("#btn-seed-counter").addEventListener("click", async () => {
  // Seed: a counter chunk + tick handler + persistent state
  // counter_inc: LDA 14 ; ADD 13 ; STA 14   (where mem[13]=1 is the increment)
  try {
    await api("/api/chunks", {
      method: "POST",
      body: {
        name: "counter_inc",
        body: [{ mnemonic: "LDA", operand: 14 },
               { mnemonic: "ADD", operand: 13 },
               { mnemonic: "STA", operand: 14 }],
        description: "increment scratch[14] by scratch[13]",
        replace: true,
      },
    });
    await api("/api/vectors", {
      method: "POST",
      body: { event_type: "tick", handler_chunk: "counter_inc",
              description: "tick the counter" },
    });
    // Pre-seed: write 1 into mem[13] (the increment) without resetting state
    // We do this by running a tiny program that stages mem[13] = 1
    // Simpler: a single LDA from a constant address won't work without immediate mode.
    // Instead, seed mem with a one-off program that loads HLT only after writing.
    // Easiest approach: use /api/program WITHOUT reset_first, supplying data.
    // But /api/program currently always resets RAM. So we run a one-shot
    // program that puts 1 at addr 13 via STA after LDA from somewhere else.
    // For now, we just rely on the user to fire 'seed_init' first OR
    // we register a 'seed_init' chunk that does it explicitly:
    await api("/api/chunks", {
      method: "POST",
      body: {
        name: "seed_init",
        body: [{ mnemonic: "LDA", operand: 15 },   // load mem[15]
               { mnemonic: "STA", operand: 13 },   // store to mem[13]
               { mnemonic: "LDA", operand: 14 },   // restore A from scratch
               { mnemonic: "STA", operand: 14 }],  // (no-op write — re-stores A)
        description: "copy mem[15] -> mem[13] (used to seed increment value)",
        replace: true,
      },
    });
    await api("/api/vectors", {
      method: "POST",
      body: { event_type: "init", handler_chunk: "seed_init",
              description: "one-time setup" },
    });
    // We can't easily set mem[13] = 1 from here without running a full program,
    // so the easiest demo is: after seeding, the user clicks "fire init" with
    // mem[15] pre-set to 1 by running a bootstrap program.  Pre-fill via
    // /api/program with reset_first=true:
    await api("/api/program", {
      method: "POST",
      body: {
        instructions: [{ mnemonic: "HLT", operand: 0 }],
        data: { 13: 1, 14: 0, 15: 1 },
        reset_first: true,
      },
    });
    await refreshAll();
    $("#vec-event").value = "tick";
    $("#vec-handler").value = "counter_inc";
    $("#ev-event").value = "tick";
    alert("seeded.\n\n• chunk 'counter_inc' registered as handler for 'tick'\n• mem[13] = 1 (increment), mem[14] = 0 (counter)\n• registers reset\n\nNow click 'fire' a few times — watch mem[14] climb.");
  } catch (e) { alert("error: " + e.message); }
});

// ---- init ----------------------------------------------------
refreshAll();
