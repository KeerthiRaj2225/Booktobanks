(() => {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];
  const inr = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const money = (v) => (v === null || v === undefined || v === "" ? "" : inr.format(v));
  const fmtDate = (iso) => (iso ? iso.split("-").reverse().join("-") : "");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  let file = null;
  let data = null; // parsed statement
  let filter = "all";
  let query = "";
  const SUSPENSE = "Suspense A/c";

  // ---------- upload ----------
  const drop = $("#drop");
  const input = $("#file");
  const btn = $("#convert-btn");

  function setFile(f) {
    if (!f) return;
    if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
      showError("Please choose a PDF file.");
      return;
    }
    file = f;
    drop.classList.add("has-file");
    $("#drop-title").textContent = f.name;
    $("#drop-sub").textContent = `${(f.size / 1024).toFixed(0)} KB · click to change`;
    $("#pw-row").hidden = true;
    $("#password").value = "";
    btn.disabled = false;
    hideError();
  }
  input.addEventListener("change", () => setFile(input.files[0]));
  ["dragenter", "dragover"].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (ev) => setFile(ev.dataTransfer.files[0]));

  function showError(msg) { const e = $("#upload-error"); e.textContent = msg; e.hidden = false; }
  function hideError() { $("#upload-error").hidden = true; }

  $("#upload-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!file) return;
    hideError();
    const fd = new FormData();
    fd.append("file", file);
    const pw = $("#password").value;
    if (pw) fd.append("password", pw);
    $("#loading").hidden = false;
    try {
      const res = await fetch("/api/convert", { method: "POST", body: fd });
      const body = await res.json();
      if (!res.ok) {
        if (body.error === "password_required" || body.error === "wrong_password") {
          $("#pw-row").hidden = false;
          $("#password").focus();
        }
        showError(body.message || "Conversion failed.");
        return;
      }
      data = body;
      showResult();
    } catch (e) {
      showError("Couldn't reach the server. Is it running?");
    } finally {
      $("#loading").hidden = true;
    }
  });

  // ---------- results ----------
  async function loadLedgers() {
    try {
      const r = await fetch("/api/ledgers");
      const j = await r.json();
      $("#ledger-list").innerHTML = j.ledgers.map((l) => `<option value="${esc(l)}">`).join("");
    } catch (_) {}
  }

  function showResult() {
    $("#upload-view").hidden = true;
    $("#result-view").hidden = false;
    window.scrollTo(0, 0);
    $("#r-title").textContent = `${data.bank}${data.account_number ? " · A/c " + data.account_number : ""}`;
    const period = data.period_from ? `${fmtDate(data.period_from)} to ${fmtDate(data.period_to)}` : "";
    $("#r-sub").textContent = [data.account_holder, period, `${data.pages} page${data.pages > 1 ? "s" : ""}`].filter(Boolean).join(" · ");
    $("#bank-ledger").value = data.default_bank_ledger || "Bank A/c";
    renderStats();
    const w = $("#warnings");
    w.innerHTML = (data.warnings || []).map((x) => `<li>${esc(x)}</li>`).join("");
    w.hidden = !data.warnings || !data.warnings.length;
    // Learn ledger names already present so they appear in suggestions
    const known = new Set([...$$("#ledger-list option")].map((o) => o.value));
    data.transactions.forEach((t) => t.ledger && known.add(t.ledger));
    $("#ledger-list").innerHTML = [...known].sort().map((l) => `<option value="${esc(l)}">`).join("");
    renderTable();
  }

  function renderStats() {
    const ok = data.reconciled_pct;
    const stats = [
      ["Transactions", data.count],
      ["Opening", money(data.opening_balance)],
      ["Total debits", money(data.total_debit)],
      ["Total credits", money(data.total_credit)],
      ["Closing", money(data.closing_balance)],
      ["Balance check", `${ok}%`, ok === 100 ? "good" : "bad"],
    ];
    $("#stats").innerHTML = stats.map(([k, v, cls]) => `<div class="stat ${cls || ""}"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  }

  function visible(t) {
    if (filter === "suspense" && t.ledger !== SUSPENSE) return false;
    if (filter === "review" && t.reconciled !== false) return false;
    if (query) {
      const hay = `${t.narration} ${t.party} ${t.ref} ${t.debit} ${t.credit} ${t.ledger}`.toLowerCase();
      if (!hay.includes(query)) return false;
    }
    return true;
  }

  function renderTable() {
    const tx = data.transactions;
    $("#c-all").textContent = tx.length;
    $("#c-susp").textContent = tx.filter((t) => t.ledger === SUSPENSE).length;
    $("#c-rev").textContent = tx.filter((t) => t.reconciled === false).length;
    const rows = [];
    tx.forEach((t, i) => {
      if (!visible(t)) return;
      const cls = [t.reconciled === false ? "review" : "", t.ledger === SUSPENSE ? "suspense" : ""].join(" ");
      rows.push(`<tr class="${cls}" data-i="${i}">
        <td class="date">${fmtDate(t.date)}</td>
        <td class="narr">${esc(t.narration)}${t.ref ? `<small>Ref ${esc(t.ref)}</small>` : ""}</td>
        <td>${esc(t.party)}</td>
        <td class="num debit">${t.debit ? money(t.debit) : ""}</td>
        <td class="num credit">${t.credit ? money(t.credit) : ""}</td>
        <td class="num">${money(t.balance)}</td>
        <td><input list="ledger-list" class="ledger" value="${esc(t.ledger)}" aria-label="Ledger"></td>
        <td><select class="vtype" aria-label="Voucher type">${["Payment", "Receipt", "Contra", "Journal"].map((v) => `<option ${v === t.voucher_type ? "selected" : ""}>${v}</option>`).join("")}</select></td>
        <td>${t.reconciled === false ? `<span class="flag" title="${esc(t.note)}">⚠</span>` : ""}</td>
      </tr>`);
    });
    $("#txn-table tbody").innerHTML = rows.join("") || `<tr><td colspan="9" class="muted">No transactions match.</td></tr>`;
  }

  // Editing: a ledger set for one party is offered to every other row from the same party still in Suspense.
  $("#txn-table").addEventListener("change", (ev) => {
    const tr = ev.target.closest("tr");
    if (!tr) return;
    const i = +tr.dataset.i;
    const t = data.transactions[i];
    if (ev.target.classList.contains("ledger")) {
      const val = ev.target.value.trim() || SUSPENSE;
      t.ledger = val;
      let n = 0;
      if (t.party) {
        data.transactions.forEach((o, j) => {
          if (j !== i && o.party === t.party && o.ledger === SUSPENSE) { o.ledger = val; n++; }
        });
      }
      const opt = document.createElement("option");
      opt.value = val;
      $("#ledger-list").appendChild(opt);
      if (n) toast(`Also set "${val}" on ${n} other row${n > 1 ? "s" : ""} from ${t.party}`);
      renderTable();
    }
    if (ev.target.classList.contains("vtype")) t.voucher_type = ev.target.value;
  });

  $$(".tab").forEach((b) => b.addEventListener("click", () => {
    $$(".tab").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    filter = b.dataset.filter;
    renderTable();
  }));
  $("#search").addEventListener("input", (e) => { query = e.target.value.trim().toLowerCase(); renderTable(); });

  $("#again").addEventListener("click", () => {
    data = null; file = null; input.value = "";
    drop.classList.remove("has-file");
    $("#drop-title").textContent = "Drop your statement PDF here";
    $("#drop-sub").textContent = "or click to browse · up to 15 MB";
    btn.disabled = true;
    $("#result-view").hidden = true;
    $("#upload-view").hidden = false;
  });

  // ---------- export ----------
  $$(".export-btns .btn").forEach((b) => b.addEventListener("click", async () => {
    const fmt = b.dataset.fmt;
    b.disabled = true;
    try {
      const res = await fetch(`/api/export/${fmt}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ statement: data, bank_ledger: $("#bank-ledger").value.trim() || "Bank A/c", company: $("#company").value.trim() }),
      });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const cd = res.headers.get("Content-Disposition") || "";
      const name = (cd.match(/filename="([^"]+)"/) || [])[1] || `statement.${fmt}`;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Revoking synchronously can cancel the download in Safari/Firefox.
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (_) {
      toast("Export failed — please try again.");
    } finally {
      b.disabled = false;
    }
  }));

  let toastTimer;
  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.hidden = true), 3200);
  }

  loadLedgers();
})();
