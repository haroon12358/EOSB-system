/* EOSB Management System - single page interface.
   No external libraries, so the application works with no internet. */
(function () {
"use strict";

/* ------------------------------------------------------------------ state */
var S = { meta: null, settings: {}, dashboard: null, schedule: null,
          employees: [], view: "dashboard", year: null, filters: {} };

/* ----------------------------------------------------------------- helpers */
function el(id) { return document.getElementById(id); }
function esc(v) {
  if (v === null || v === undefined) return "";
  return String(v).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}
function num(v, d) {
  if (v === null || v === undefined || v === "") return "";
  var n = Number(v);
  if (isNaN(n)) return "";
  return n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
}
function n1(v) { return num(v, 1); }
function n0(v) { return num(v, 0); }
function n2(v) { return num(v, 2); }
function money(v) { return num(v, 1); }
function dt(v) { return v ? String(v).slice(0, 10) : ""; }
function today() { return (S.meta && S.meta.clock && S.meta.clock.today) || ""; }
function cur() { return S.settings.currency || "SAR"; }

function toast(message, kind, detail) {
  var host = el("toasts");
  var box = document.createElement("div");
  box.className = "toast " + (kind || "");
  box.innerHTML = "<b>" + esc(message) + "</b>" +
    (detail ? '<div class="path">' + esc(detail) + "</div>" : "");
  host.appendChild(box);
  setTimeout(function () {
    box.style.opacity = "0";
    setTimeout(function () { box.remove(); }, 250);
  }, kind === "err" ? 7000 : 4200);
}
function flashSaved() {
  var flag = el("saveFlag");
  flag.classList.add("show");
  clearTimeout(flashSaved._t);
  flashSaved._t = setTimeout(function () { flag.classList.remove("show"); }, 1300);
}

/* --------------------------------------------------------------------- api */
function api(method, path, body) {
  var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
  var timer = controller ? setTimeout(function () { controller.abort(); }, 20000) : null;
  return fetch(path, {
    method: method,
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    signal: controller ? controller.signal : undefined,
    body: body === undefined ? undefined : JSON.stringify(body)
  }).then(function (response) {
    if (timer) clearTimeout(timer);
    return response.json().catch(function () { return {}; }).then(function (data) {
      if (!response.ok) throw new Error(data.error || ("Request failed (" + response.status + ")"));
      return data;
    });
  }, function (error) {
    if (timer) clearTimeout(timer);
    throw new Error(error && error.name === "AbortError"
      ? "The application did not answer within 20 seconds (" + path + ")."
      : "Could not reach the application (" + path + "). It may have been closed.");
  });
}
function fail(error) { toast(error.message || String(error), "err"); }

/* ------------------------------------------------------------------- modal */
var modalStack = [];
function modal(options) {
  var host = el("modalHost");
  var overlay = document.createElement("div");
  overlay.className = "overlay";
  overlay.innerHTML =
    '<div class="modal' + (options.wide ? " wide" : "") + '">' +
      '<header><h3>' + esc(options.title) + "</h3><div class='spacer'></div>" +
      '<button class="x" data-close>&times;</button></header>' +
      '<div class="body">' + options.body + "</div>" +
      '<footer>' + (options.footer || '<button class="btn" data-close>Close</button>') + "</footer>" +
    "</div>";
  host.appendChild(overlay);
  modalStack.push(overlay);
  overlay.addEventListener("click", function (event) {
    if (event.target === overlay || event.target.hasAttribute("data-close")) closeModal();
  });
  if (options.onOpen) options.onOpen(overlay);
  var first = overlay.querySelector("input,select,textarea");
  if (first) first.focus();
  return overlay;
}
function closeModal() {
  var overlay = modalStack.pop();
  if (overlay) overlay.remove();
}
document.addEventListener("keydown", function (event) {
  if (event.key === "Escape" && modalStack.length) closeModal();
});

function confirmDialog(title, message, confirmLabel, onConfirm) {
  modal({
    title: title,
    body: '<p style="margin:0;line-height:1.6">' + message + "</p>",
    footer: '<button class="btn" data-close>Cancel</button>' +
            '<button class="btn danger" id="cfmYes">' + esc(confirmLabel) + "</button>",
    onOpen: function (overlay) {
      overlay.querySelector("#cfmYes").onclick = function () {
        closeModal();
        onConfirm();
      };
    }
  });
}

/* ------------------------------------------------------------------ fields */
function textField(name, label, value, opts) {
  opts = opts || {};
  return '<div class="field"><label>' + esc(label) +
    (opts.note ? ' <span class="note">' + esc(opts.note) + "</span>" : "") + "</label>" +
    '<input type="' + (opts.type || "text") + '" name="' + name + '" value="' +
    esc(value === null || value === undefined ? "" : value) + '"' +
    (opts.step ? ' step="' + opts.step + '"' : "") +
    (opts.min !== undefined ? ' min="' + opts.min + '"' : "") +
    (opts.placeholder ? ' placeholder="' + esc(opts.placeholder) + '"' : "") + "></div>";
}
function selectField(name, label, value, options, note) {
  var html = '<div class="field"><label>' + esc(label) +
    (note ? ' <span class="note">' + esc(note) + "</span>" : "") +
    '</label><select name="' + name + '">';
  options.forEach(function (option) {
    var val = option.value !== undefined ? option.value : option;
    var text = option.label !== undefined ? option.label : option;
    html += '<option value="' + esc(val) + '"' +
      (String(val) === String(value === null || value === undefined ? "" : value) ? " selected" : "") +
      ">" + esc(text) + "</option>";
  });
  return html + "</select></div>";
}
function areaField(name, label, value) {
  return '<div class="field"><label>' + esc(label) + "</label>" +
    '<textarea name="' + name + '">' + esc(value || "") + "</textarea></div>";
}
function readForm(overlay) {
  var out = {};
  overlay.querySelectorAll("[name]").forEach(function (input) {
    out[input.name] = input.value === "" ? null : input.value;
  });
  return out;
}
function employeeOptions(selected, includeBlank) {
  var options = includeBlank ? [{ value: "", label: "Select an employee" }] : [];
  S.employees.forEach(function (e) {
    options.push({ value: e.id, label: e.name + (e.status === "Terminated" ? "  (terminated)" : "") });
  });
  return options;
}

/* ------------------------------------------------------------------ loader */
function refresh() {
  return Promise.all([
    api("GET", "/api/meta"),
    api("GET", "/api/dashboard"),
    api("GET", "/api/schedule"),
    api("GET", "/api/employees")
  ]).then(function (results) {
    S.meta = results[0];
    S.settings = results[0].settings;
    S.dashboard = results[1];
    S.schedule = results[2];
    S.employees = results[3].employees;
    if (S.year === null || S.schedule.years.indexOf(S.year) < 0) {
      S.year = S.dashboard.reporting_year || S.schedule.years[S.schedule.years.length - 1];
    }
    paintChrome();
  });
}
function reload() { return refresh().then(render).catch(fail); }

function paintChrome() {
  el("orgName").textContent = S.settings.organisation_name || "Organisation";
  el("footYear").textContent = "Reporting year " + (S.dashboard.reporting_year || "-");
  el("footDate").textContent = today() + " (" +
    (S.meta.clock.source === "online" ? "online" : "system") + " date)";
  el("footVersion").textContent = S.meta.app + " v" + S.meta.version;
}

/* ------------------------------------------------------------------ router */
var VIEWS = {};
function render() {
  document.querySelectorAll("#nav a").forEach(function (link) {
    link.classList.toggle("on", link.dataset.view === S.view);
  });
  var view = VIEWS[S.view] || VIEWS.dashboard;
  el("pageTitle").textContent = view.title;
  el("pageSub").textContent = typeof view.sub === "function" ? view.sub() : (view.sub || "");
  el("view").innerHTML = view.html();
  if (view.wire) view.wire();
}
function go(name) {
  S.view = name;
  location.hash = name;
  render();
}

/* --------------------------------------------------------------- dashboard */
VIEWS.dashboard = {
  title: "Dashboard",
  sub: function () {
    return "Position at " + (S.dashboard.year_end || today()) + "  •  amounts in " + cur();
  },
  html: function () {
    var d = S.dashboard;
    var history = d.history || [];
    var peak = Math.max.apply(null, history.map(function (h) { return h.closing; }).concat([1]));
    var bars = history.map(function (h) {
      var height = Math.max(3, Math.round((h.closing / peak) * 132));
      return '<div class="col"><div class="bar" style="height:' + height + 'px">' +
        "<span>" + n1(h.closing) + "</span></div>" +
        '<div class="yr">' + h.year + "</div></div>";
    }).join("");

    var rows = history.slice().reverse().map(function (h) {
      return "<tr><td><b>" + h.year + "</b></td>" +
        '<td class="num">' + n1(h.opening) + "</td>" +
        '<td class="num">' + n1(h.charge) + "</td>" +
        '<td class="num">' + n1(h.paid) + "</td>" +
        '<td class="num"><b>' + n1(h.closing) + "</b></td></tr>";
    }).join("");

    return '<div class="kpis">' +
      kpi("Opening Provision", n1(d.opening_provision), cur() + " at " + (d.reporting_year || "") + " opening", "n") +
      kpi("Charge This Year", n1(d.charge_for_year), "expense recognised in " + (d.reporting_year || ""), "") +
      kpi("Benefits Paid", n1(d.benefits_paid), "settled during the year", "a") +
      kpi("Closing Provision", n1(d.closing_provision), "liability at " + (d.year_end || ""), "g") +
      "</div>" +
      '<div class="statrow">' +
        ministat(n0(d.active_employees), "Active employees") +
        ministat(n0(d.terminated_employees), "Terminated employees") +
        ministat(d.reporting_year || "-", "Current reporting year") +
      "</div>" +
      '<div class="card"><header><h3>Provision by Year</h3>' +
        '<span class="hint">closing balance, ' + cur() + "</span></header>" +
        '<div class="body">' + (history.length ? '<div class="bars">' + bars + "</div>"
          : '<div class="empty">No reporting years yet.</div>') + "</div></div>" +
      '<div class="card"><header><h3>Roll Forward Summary</h3><div class="spacer"></div>' +
        '<button class="btn sm" data-goto="schedule">Open schedule</button></header>' +
        '<div class="body tight"><div class="tablewrap"><table class="data"><thead><tr>' +
        "<th>Year</th><th class='num'>Opening</th><th class='num'>Charge</th>" +
        "<th class='num'>Benefits Paid</th><th class='num'>Closing</th>" +
        "</tr></thead><tbody>" + (rows || "<tr><td colspan=5 class='muted'>No data</td></tr>") +
        "</tbody></table></div></div></div>";
  },
  wire: function () {
    document.querySelectorAll("[data-goto]").forEach(function (button) {
      button.onclick = function () { go(button.dataset.goto); };
    });
  }
};
function kpi(label, value, meta, cls) {
  return '<div class="kpi ' + (cls || "") + '"><div class="k">' + esc(label) + "</div>" +
    '<div class="v">' + value + '</div><div class="m">' + esc(meta) + "</div></div>";
}
function ministat(value, label) {
  return '<div class="ministat"><div><div class="big">' + value + "</div>" +
    '<div class="lbl">' + esc(label) + "</div></div></div>";
}

/* --------------------------------------------------------------- employees */
VIEWS.employees = {
  title: "Employees",
  sub: function () { return S.employees.length + " employee records"; },
  html: function () {
    var search = (S.filters.search || "").toLowerCase();
    var status = S.filters.status || "";
    var list = S.employees.filter(function (e) {
      if (status && e.status !== status) return false;
      if (!search) return true;
      return (e.name + " " + (e.identity_number || "") + " " + (e.employee_no || ""))
        .toLowerCase().indexOf(search) >= 0;
    });
    var block = currentBlock();
    var byId = {};
    if (block) block.rows.forEach(function (r) { byId[r.employee_id] = r; });

    var rows = list.map(function (e) {
      var calc = byId[e.id] || {};
      return "<tr>" +
        "<td>" + esc(e.employee_no || "") + "</td>" +
        '<td class="wrap"><b>' + esc(e.name) + "</b></td>" +
        "<td>" + esc(e.identity_number || "") + "</td>" +
        "<td>" + dt(e.joining_date) + "</td>" +
        "<td>" + (e.termination_date ? dt(e.termination_date) : '<span class="muted">&mdash;</span>') + "</td>" +
        '<td><span class="pill ' + (e.status === "Active" ? "ok" : "off") + '">' + esc(e.status) + "</span></td>" +
        '<td class="num">' + n2(calc.salary) + "</td>" +
        '<td class="num">' + n0(calc.net_service_days) + "</td>" +
        '<td class="num">' + n1(calc.entitlement) + "</td>" +
        '<td class="num"><b>' + n1(calc.closing_provision) + "</b></td>" +
        '<td><button class="btn sm" data-open="' + e.id + '">Open</button> ' +
            '<button class="btn sm" data-edit="' + e.id + '">Edit</button> ' +
            '<button class="btn sm danger" data-del="' + e.id + '">Delete</button></td>' +
      "</tr>";
    }).join("");

    return '<div class="toolbar">' +
        '<input type="text" id="searchBox" placeholder="Search name, identity or number" value="' +
          esc(S.filters.search || "") + '">' +
        '<select id="statusBox">' +
          '<option value="">All statuses</option>' +
          '<option value="Active"' + (status === "Active" ? " selected" : "") + ">Active</option>" +
          '<option value="Terminated"' + (status === "Terminated" ? " selected" : "") + ">Terminated</option>" +
        "</select>" +
        '<div style="flex:1"></div>' +
        '<button class="btn primary" id="addEmp">+ Add Employee</button>' +
      "</div>" +
      '<div class="card"><div class="body tight"><div class="tablewrap">' +
      '<table class="data"><thead><tr><th>No</th><th>Employee Name</th><th>Identity</th>' +
      "<th>Joining Date</th><th>Termination</th><th>Status</th>" +
      "<th class='num'>Salary</th><th class='num'>Net Days</th>" +
      "<th class='num'>Entitlement</th><th class='num'>Provision</th><th></th>" +
      "</tr></thead><tbody>" + (rows ||
        '<tr><td colspan="11"><div class="empty"><b>No employees match</b>' +
        "Adjust the search or add a new employee.</div></td></tr>") +
      "</tbody></table></div></div></div>";
  },
  wire: function () {
    var search = el("searchBox");
    search.oninput = function () {
      S.filters.search = search.value;
      var caret = search.selectionStart;
      render();
      var again = el("searchBox");
      again.focus();
      again.setSelectionRange(caret, caret);
    };
    el("statusBox").onchange = function () { S.filters.status = this.value; render(); };
    el("addEmp").onclick = function () { employeeForm(null); };
    document.querySelectorAll("[data-edit]").forEach(function (b) {
      b.onclick = function () { employeeForm(Number(b.dataset.edit)); };
    });
    document.querySelectorAll("[data-open]").forEach(function (b) {
      b.onclick = function () { employeeDetail(Number(b.dataset.open)); };
    });
    document.querySelectorAll("[data-del]").forEach(function (b) {
      b.onclick = function () {
        var employee = findEmployee(Number(b.dataset.del));
        confirmDialog("Delete employee",
          "Delete <b>" + esc(employee.name) + "</b> and all of their salary history, " +
          "leave and payment records?<br><br>This cannot be undone.",
          "Delete permanently", function () {
            api("DELETE", "/api/employees/" + employee.id).then(function () {
              toast("Employee deleted", "ok");
              flashSaved();
              return reload();
            }).catch(fail);
          });
      };
    });
  }
};
function findEmployee(id) {
  for (var i = 0; i < S.employees.length; i++) if (S.employees[i].id === id) return S.employees[i];
  return null;
}
function currentBlock() {
  if (!S.schedule) return null;
  var blocks = S.schedule.blocks;
  for (var i = 0; i < blocks.length; i++) if (blocks[i].is_current) return blocks[i];
  return blocks.length ? blocks[blocks.length - 1] : null;
}

/* --------------------------------------------------- employee form/detail */
function employeeForm(id) {
  var e = id ? findEmployee(id) : null;
  var salary = "";
  if (!e) salary = textField("monthly_salary", "Monthly Salary", "",
      { type: "number", step: "0.01", min: 0, note: "opens the salary history" });
  var body =
    '<div class="grid c2">' +
      textField("name", "Employee Name", e && e.name) +
      textField("identity_number", "Identity Number", e && e.identity_number) +
      textField("employee_no", "Employee Number", e && e.employee_no, { note: "optional" }) +
      textField("joining_date", "Joining Date", e && dt(e.joining_date), { type: "date" }) +
      textField("termination_date", "Termination Date", e && dt(e.termination_date),
                { type: "date", note: "only when the employee leaves" }) +
      selectField("termination_reason", "Reason for Leaving", e && e.termination_reason,
        [{ value: "", label: "-" }, "Resignation", "Dismissal", "End of Contract",
         "Redundancy", "Retirement", "Death", "Disability"],
        "affects the amount legally payable") +
      textField("department", "Department", e && e.department) +
      textField("position", "Position", e && e.position) +
      salary +
    "</div>" + areaField("notes", "Notes", e && e.notes) +
    '<div class="callout">Status is set automatically from the termination date. ' +
    "An employee with no termination date is Active.</div>";

  modal({
    title: e ? "Edit Employee" : "Add Employee",
    body: body,
    footer: '<button class="btn" data-close>Cancel</button>' +
            '<button class="btn primary" id="saveEmp">Save</button>',
    onOpen: function (overlay) {
      overlay.querySelector("#saveEmp").onclick = function () {
        var payload = readForm(overlay);
        var request = e ? api("PUT", "/api/employees/" + e.id, payload)
                        : api("POST", "/api/employees", payload);
        request.then(function () {
          closeModal();
          toast(e ? "Employee updated" : "Employee added", "ok");
          flashSaved();
          return reload();
        }).catch(fail);
      };
    }
  });
}

function employeeDetail(id) {
  api("GET", "/api/employees/" + id).then(function (data) {
    var e = data.employee;
    var movement = [];
    S.schedule.blocks.forEach(function (block) {
      block.rows.forEach(function (row) {
        if (row.employee_id === id) movement.push({ block: block, row: row });
      });
    });
    var latest = movement.length ? movement[movement.length - 1].row : {};

    var moveRows = movement.slice().reverse().map(function (m) {
      return "<tr><td><b>" + m.block.year + "</b>" +
        (m.block.is_future ? ' <span class="pill info">future</span>' : "") + "</td>" +
        "<td>" + dt(m.row.calculation_date) + "</td>" +
        '<td class="num">' + n2(m.row.salary) + "</td>" +
        '<td class="num">' + n0(m.row.net_service_days) + "</td>" +
        '<td class="num">' + n1(m.row.entitlement) + "</td>" +
        '<td class="num">' + n1(m.row.opening_provision) + "</td>" +
        '<td class="num">' + n1(m.row.charge_for_year) + "</td>" +
        '<td class="num">' + n1(m.row.benefits_paid) + "</td>" +
        '<td class="num"><b>' + n1(m.row.closing_provision) + "</b></td></tr>";
    }).join("");

    var salaryRows = e.salaries.map(function (s) {
      return "<tr><td>" + dt(s.effective_date) + "</td>" +
        '<td class="num">' + (s.previous_salary === null ? "&mdash;" : n2(s.previous_salary)) + "</td>" +
        '<td class="num"><b>' + n2(s.new_salary) + "</b></td>" +
        '<td class="wrap">' + esc(s.reason || "") + "</td></tr>";
    }).join("");

    var leaveRows = e.leave.map(function (l) {
      return "<tr><td>" + dt(l.start_date) + "</td><td>" + dt(l.end_date) + "</td>" +
        '<td class="num">' + n0(l.days) + '</td><td class="wrap">' + esc(l.reason || "") + "</td></tr>";
    }).join("") || '<tr><td colspan="4" class="muted">No unpaid leave recorded</td></tr>';

    var payRows = e.payments.map(function (p) {
      return "<tr><td>" + dt(p.payment_date) + "</td>" +
        '<td class="num">' + n2(p.amount) + "</td>" +
        "<td>" + esc(p.reference || "") + '</td><td class="wrap">' + esc(p.notes || "") + "</td></tr>";
    }).join("") || '<tr><td colspan="4" class="muted">No benefits paid</td></tr>';

    var settlement = "";
    if (latest.has_left && latest.settlement_adjustment > 0) {
      settlement = '<div class="callout warn"><b>Article 85 applies.</b> ' +
        "The full award is " + n1(latest.entitlement) + " " + cur() +
        " but the amount legally payable on " + esc(e.termination_reason || "leaving") +
        " is " + n1(latest.payable) + " " + cur() + ". The difference of " +
        n1(latest.settlement_adjustment) + " is released to the income statement.</div>";
    }

    modal({
      title: e.name,
      wide: true,
      body:
        '<div class="grid c3">' +
          detail("Employee Number", e.employee_no) +
          detail("Identity Number", e.identity_number) +
          detail("Status", e.status) +
          detail("Joining Date", dt(e.joining_date)) +
          detail("Termination Date", dt(e.termination_date) || "—") +
          detail("Reason for Leaving", e.termination_reason || "—") +
          detail("Current Salary", n2(e.current_salary) + " " + cur()) +
          detail("Net Service Days", n0(latest.net_service_days)) +
          detail("Service Years", latest.service_years) +
        "</div>" + settlement +
        (e.notes ? '<div class="callout">' + esc(e.notes) + "</div>" : "") +
        subTable("Provision Movement by Year",
          ["Year", "Calc Date", "Salary", "Net Days", "Entitlement", "Opening", "Charge", "Paid", "Closing"],
          [0, 0, 1, 1, 1, 1, 1, 1, 1], moveRows) +
        subTable("Salary History", ["Effective Date", "Previous", "New Salary", "Reason"],
          [0, 1, 1, 0], salaryRows) +
        subTable("Unpaid Leave", ["From", "To", "Days", "Reason"], [0, 0, 1, 0], leaveRows) +
        subTable("Benefits Paid", ["Payment Date", "Amount", "Reference", "Notes"],
          [0, 1, 0, 0], payRows),
      footer:
        '<button class="btn" id="dSalary">Add Salary Change</button>' +
        '<button class="btn" id="dLeave">Add Unpaid Leave</button>' +
        '<button class="btn" id="dPay">Record Benefit Paid</button>' +
        '<button class="btn" id="dStatement">Statement PDF</button>' +
        '<button class="btn primary" data-close>Close</button>',
      onOpen: function (overlay) {
        overlay.querySelector("#dSalary").onclick = function () { closeModal(); salaryForm(id); };
        overlay.querySelector("#dLeave").onclick = function () { closeModal(); leaveForm(id); };
        overlay.querySelector("#dPay").onclick = function () { closeModal(); paymentForm(id); };
        overlay.querySelector("#dStatement").onclick = function () {
          runReport("statement", "pdf", { employee_id: id });
        };
      }
    });
  }).catch(fail);
}
function detail(label, value) {
  return '<div class="field"><label>' + esc(label) + "</label>" +
    '<div style="padding:7px 0;font-weight:600">' +
    (value === null || value === undefined || value === "" ? "&mdash;" : esc(value)) + "</div></div>";
}
function subTable(title, columns, numeric, rows) {
  var head = columns.map(function (c, i) {
    return "<th" + (numeric[i] ? ' class="num"' : "") + ">" + esc(c) + "</th>";
  }).join("");
  return '<h4 style="margin:20px 0 8px;font-size:13px">' + esc(title) + "</h4>" +
    '<div class="tablewrap" style="border:1px solid var(--line);border-radius:6px">' +
    '<table class="data"><thead><tr>' + head + "</tr></thead><tbody>" + rows + "</tbody></table></div>";
}

/* ------------------------------------------------- salary / leave / paid */
function salaryForm(employeeId) {
  modal({
    title: "Record a Salary Change",
    body: '<div class="callout">Salary is never overwritten. Each change is stored with its ' +
      "effective date, and the schedule uses the salary in force at each year end.</div>" +
      selectField("employee_id", "Employee", employeeId || "", employeeOptions(employeeId, true)) +
      '<div class="grid c2">' +
        textField("effective_date", "Effective Date", today(), { type: "date" }) +
        textField("new_salary", "New Monthly Salary", "", { type: "number", step: "0.01", min: 0 }) +
      "</div>" +
      textField("reason", "Reason", "", { placeholder: "Annual increment, promotion, adjustment" }),
    footer: '<button class="btn" data-close>Cancel</button>' +
            '<button class="btn primary" id="saveSalary">Save</button>',
    onOpen: function (overlay) {
      overlay.querySelector("#saveSalary").onclick = function () {
        api("POST", "/api/salaries", readForm(overlay)).then(function () {
          closeModal();
          toast("Salary change recorded", "ok");
          flashSaved();
          return reload();
        }).catch(fail);
      };
    }
  });
}
function leaveForm(employeeId) {
  modal({
    title: "Record Unpaid Leave",
    body: '<div class="callout">Unpaid leave reduces net service days. The split between the ' +
      "first five years and later years is worked out from the dates automatically.</div>" +
      selectField("employee_id", "Employee", employeeId || "", employeeOptions(employeeId, true)) +
      '<div class="grid c2">' +
        textField("start_date", "From", "", { type: "date" }) +
        textField("end_date", "To", "", { type: "date" }) +
      "</div>" + textField("reason", "Reason", ""),
    footer: '<button class="btn" data-close>Cancel</button>' +
            '<button class="btn primary" id="saveLeave">Save</button>',
    onOpen: function (overlay) {
      overlay.querySelector("#saveLeave").onclick = function () {
        api("POST", "/api/leave", readForm(overlay)).then(function () {
          closeModal();
          toast("Unpaid leave recorded", "ok");
          flashSaved();
          return reload();
        }).catch(fail);
      };
    }
  });
}
function paymentForm(employeeId) {
  modal({
    title: "Record a Benefit Payment",
    body: '<div class="callout">A payment reduces the closing provision in the year it is made.</div>' +
      selectField("employee_id", "Employee", employeeId || "", employeeOptions(employeeId, true)) +
      '<div class="grid c2">' +
        textField("payment_date", "Payment Date", today(), { type: "date" }) +
        textField("amount", "Amount", "", { type: "number", step: "0.01", min: 0 }) +
      "</div>" +
      textField("reference", "Reference", "", { placeholder: "voucher or cheque number" }) +
      areaField("notes", "Notes", ""),
    footer: '<button class="btn" data-close>Cancel</button>' +
            '<button class="btn primary" id="savePay">Save</button>',
    onOpen: function (overlay) {
      overlay.querySelector("#savePay").onclick = function () {
        api("POST", "/api/payments", readForm(overlay)).then(function () {
          closeModal();
          toast("Payment recorded", "ok");
          flashSaved();
          return reload();
        }).catch(fail);
      };
    }
  });
}

function recordList(config) {
  return {
    title: config.title,
    sub: config.sub,
    html: function () {
      var rows = (S[config.cache] || []).map(config.row).join("");
      return '<div class="toolbar"><div style="flex:1"></div>' +
          '<button class="btn primary" id="addRec">+ ' + esc(config.addLabel) + "</button></div>" +
        '<div class="card"><div class="body tight"><div class="tablewrap"><table class="data">' +
        "<thead><tr>" + config.head + "</tr></thead><tbody>" + (rows ||
          '<tr><td colspan="9"><div class="empty"><b>Nothing recorded yet</b>' +
          esc(config.emptyHint) + "</div></td></tr>") + "</tbody></table></div></div></div>";
    },
    wire: function () {
      el("addRec").onclick = function () { config.add(); };
      document.querySelectorAll("[data-remove]").forEach(function (b) {
        b.onclick = function () {
          confirmDialog("Delete record", config.confirm, "Delete", function () {
            api("DELETE", config.endpoint + "/" + b.dataset.remove).then(function () {
              toast("Record deleted", "ok");
              flashSaved();
              return loadLists().then(render);
            }).catch(fail);
          });
        };
      });
    }
  };
}
function loadLists() {
  return Promise.all([
    api("GET", "/api/salaries"), api("GET", "/api/leave"), api("GET", "/api/payments")
  ]).then(function (results) {
    S.salaries = results[0].salaries;
    S.leaveList = results[1].leave;
    S.payments = results[2].payments;
    return refresh();
  });
}

VIEWS.salaries = recordList({
  title: "Salary History", sub: "every salary change, never overwritten",
  cache: "salaries", addLabel: "Record Salary Change", endpoint: "/api/salaries",
  emptyHint: "Add a salary change to begin.",
  confirm: "Delete this salary record? The schedule will be recalculated.",
  add: function () { salaryForm(null); },
  head: "<th>Effective Date</th><th>Employee</th><th class='num'>Previous Salary</th>" +
        "<th class='num'>New Salary</th><th class='num'>Change</th><th>Reason</th><th></th>",
  row: function (s) {
    var delta = s.previous_salary === null ? null : s.new_salary - s.previous_salary;
    return "<tr><td>" + dt(s.effective_date) + "</td>" +
      "<td><b>" + esc(s.employee_name) + "</b></td>" +
      '<td class="num">' + (s.previous_salary === null ? "&mdash;" : n2(s.previous_salary)) + "</td>" +
      '<td class="num"><b>' + n2(s.new_salary) + "</b></td>" +
      '<td class="num">' + (delta === null ? "&mdash;" :
        '<span class="pill ' + (delta >= 0 ? "ok" : "warn") + '">' +
        (delta >= 0 ? "+" : "") + n2(delta) + "</span>") + "</td>" +
      '<td class="wrap">' + esc(s.reason || "") + "</td>" +
      '<td><button class="btn sm danger" data-remove="' + s.id + '">Delete</button></td></tr>';
  }
});

VIEWS.leave = recordList({
  title: "Unpaid Leave", sub: "unpaid leave reduces net service days",
  cache: "leaveList", addLabel: "Record Unpaid Leave", endpoint: "/api/leave",
  emptyHint: "Unpaid leave reduces the entitlement.",
  confirm: "Delete this leave record? The schedule will be recalculated.",
  add: function () { leaveForm(null); },
  head: "<th>From</th><th>To</th><th>Employee</th><th class='num'>Days</th><th>Reason</th><th></th>",
  row: function (l) {
    return "<tr><td>" + dt(l.start_date) + "</td><td>" + dt(l.end_date) + "</td>" +
      "<td><b>" + esc(l.employee_name) + "</b></td>" +
      '<td class="num">' + n0(l.days) + "</td>" +
      '<td class="wrap">' + esc(l.reason || "") + "</td>" +
      '<td><button class="btn sm danger" data-remove="' + l.id + '">Delete</button></td></tr>';
  }
});

VIEWS.payments = recordList({
  title: "Benefits Paid", sub: "settlements reduce the closing provision",
  cache: "payments", addLabel: "Record Benefit Paid", endpoint: "/api/payments",
  emptyHint: "Record a settlement when an employee is paid out.",
  confirm: "Delete this payment? The schedule will be recalculated.",
  add: function () { paymentForm(null); },
  head: "<th>Payment Date</th><th>Employee</th><th class='num'>Amount</th>" +
        "<th>Reference</th><th>Notes</th><th></th>",
  row: function (p) {
    return "<tr><td>" + dt(p.payment_date) + "</td>" +
      "<td><b>" + esc(p.employee_name) + "</b></td>" +
      '<td class="num"><b>' + n2(p.amount) + "</b></td>" +
      "<td>" + esc(p.reference || "") + "</td>" +
      '<td class="wrap">' + esc(p.notes || "") + "</td>" +
      '<td><button class="btn sm danger" data-remove="' + p.id + '">Delete</button></td></tr>';
  }
});

/* ---------------------------------------------------------------- schedule */
var SCHEDULE_COLUMNS = [
  { key: "name",              label: "Employee Name",       num: false },
  { key: "calculation_date",  label: "Calculation Date",    num: false, date: true },
  { key: "salary",            label: "Monthly Salary",      num: true, dp: 2 },
  { key: "service_days",      label: "Service Days",        num: true, dp: 0 },
  { key: "leave_first",       label: "Leave 1-5 Yrs",       num: true, dp: 0 },
  { key: "leave_later",       label: "Leave 5 Yrs +",       num: true, dp: 0 },
  { key: "days_first",        label: "Days in First 5 Yrs", num: true, dp: 0 },
  { key: "days_later",        label: "Days Over 5 Yrs",     num: true, dp: 0 },
  { key: "net_service_days",  label: "Net Service Days",    num: true, dp: 0 },
  { key: "entitlement",       label: "Entitlement",         num: true, dp: 1, strong: true },
  { key: "opening_provision", label: "Opening Provision",   num: true, dp: 1 },
  { key: "charge_for_year",   label: "Charge for the Year", num: true, dp: 1 },
  { key: "benefits_paid",     label: "Benefits Paid",       num: true, dp: 1 },
  { key: "closing_provision", label: "Closing Provision",   num: true, dp: 1, strong: true }
];

VIEWS.schedule = {
  title: "Provision Schedule",
  sub: function () {
    return "roll forward from " + S.schedule.years[0] + " to " +
      S.schedule.years[S.schedule.years.length - 1] + "  •  amounts in " + cur();
  },
  html: function () {
    var tabs = S.schedule.years.map(function (year) {
      var block = blockFor(year);
      return '<button data-year="' + year + '"' +
        ' class="' + (year === S.year ? "on" : "") + (block && block.is_future ? " future" : "") + '">' +
        year + "</button>";
    }).join("");
    tabs += '<button data-year="all"' + (S.year === "all" ? ' class="on"' : "") + ">All years</button>";

    var blocks = S.year === "all" ? S.schedule.blocks : [blockFor(S.year)];
    var body = blocks.filter(Boolean).map(scheduleBlock).join("");

    return '<div class="callout">Closing Provision = Opening Provision + Charge for the Year ' +
      "&minus; Benefits Paid. The closing balance is anchored to the measured entitlement, so " +
      "the provision always equals the liability.</div>" +
      '<div class="yearbar">' + tabs + "</div>" + body;
  },
  wire: function () {
    document.querySelectorAll("[data-year]").forEach(function (b) {
      b.onclick = function () {
        S.year = b.dataset.year === "all" ? "all" : Number(b.dataset.year);
        render();
      };
    });
    document.querySelectorAll("[data-export]").forEach(function (b) {
      b.onclick = function () {
        runReport(S.year === "all" ? "rollforward" : "schedule", b.dataset.export,
          S.year === "all" ? {} : { year: S.year });
      };
    });
  }
};
function blockFor(year) {
  var blocks = S.schedule.blocks;
  for (var i = 0; i < blocks.length; i++) if (blocks[i].year === year) return blocks[i];
  return null;
}
function cellValue(row, column) {
  var raw = row[column.key];
  if (column.date) return dt(raw);
  if (column.num) return num(raw, column.dp);
  return esc(raw);
}
function scheduleBlock(block) {
  var head = SCHEDULE_COLUMNS.map(function (c) {
    return "<th" + (c.num ? ' class="num"' : "") + ">" + esc(c.label) + "</th>";
  }).join("");

  var rows = block.rows.map(function (row) {
    return "<tr>" + SCHEDULE_COLUMNS.map(function (c) {
      var value = cellValue(row, c);
      if (c.key === "name") {
        value = "<b>" + esc(row.name) + "</b>" +
          (row.has_left ? ' <span class="pill off">left</span>' : "");
      } else if (c.strong) {
        value = "<b>" + value + "</b>";
      }
      return "<td" + (c.num ? ' class="num"' : "") + ">" + value + "</td>";
    }).join("") + "</tr>";
  }).join("");

  var totals = "<tr class='total'>" + SCHEDULE_COLUMNS.map(function (c, index) {
    if (index === 0) return "<td>Total</td>";
    var value = block.totals[c.key];
    if (value === undefined || c.key === "salary") return "<td" + (c.num ? ' class="num"' : "") + "></td>";
    return '<td class="num">' + num(value, c.dp) + "</td>";
  }).join("") + "</tr>";

  var t = block.totals;
  var flow = n1(t.opening_provision) + " opening  +  " + n1(t.charge_for_year) +
    " charge  &minus;  " + n1(t.benefits_paid) + " paid  =  " + n1(t.closing_provision) + " closing";

  return '<div class="card"><div class="blockhead"><h4>Year Ended ' + block.year_end + "</h4>" +
    (block.is_current ? '<span class="pill info">current year</span>' : "") +
    (block.is_future ? '<span class="pill warn">projected</span>' : "") +
    '<div class="flow">' + flow + "</div>" +
    '<div class="spacer" style="flex:1"></div>' +
    '<button class="btn sm" data-export="xlsx">Excel</button> ' +
    '<button class="btn sm" data-export="pdf">PDF</button>' +
    "</div><div class='body tight'><div class='tablewrap'><table class='data'><thead><tr>" +
    head + "</tr></thead><tbody>" + rows + totals + "</tbody></table></div></div></div>";
}

/* ----------------------------------------------------------------- reports */
function runReport(kind, format, extra) {
  var payload = { kind: kind, format: format };
  for (var key in (extra || {})) payload[key] = extra[key];
  toast("Generating report…");
  api("POST", "/api/reports", payload).then(function (result) {
    toast("Report saved to " + (result.folder.indexOf("Download") >= 0 ? "Downloads" : "disk"),
      "ok", result.path);
  }).catch(fail);
}

VIEWS.reports = {
  title: "Reports",
  sub: "saved to your Downloads folder",
  html: function () {
    var cards = [
      ["employees", "Employee EOS Report",
       "Every employee with service days, entitlement and carried provision at the current reporting date."],
      ["schedule", "Provision Schedule",
       "The full calculation for a single reporting year, in the same column order as the workbook."],
      ["rollforward", "Roll Forward Report",
       "Every reporting year in sequence, plus a movement summary from opening to closing."],
      ["statement", "Employee Statement",
       "One employee: personal details, year by year movement, salary history, leave and payments."]
    ].map(function (r) {
      var picker = r[0] === "statement"
        ? '<select id="stmtEmp" style="margin-bottom:12px">' +
          employeeOptions(null, true).map(function (o) {
            return '<option value="' + esc(o.value) + '">' + esc(o.label) + "</option>";
          }).join("") + "</select>"
        : "";
      var yearPicker = r[0] === "schedule"
        ? '<select id="schedYear" style="margin-bottom:12px">' +
          S.schedule.years.map(function (y) {
            return '<option value="' + y + '"' +
              (y === S.dashboard.reporting_year ? " selected" : "") + ">Year ended " + y + "</option>";
          }).join("") + "</select>"
        : "";
      return '<div class="report"><h4>' + esc(r[1]) + "</h4><p>" + esc(r[2]) + "</p>" +
        picker + yearPicker +
        '<div class="acts">' +
          '<button class="btn primary" data-rpt="' + r[0] + '" data-fmt="xlsx">Export Excel</button>' +
          '<button class="btn" data-rpt="' + r[0] + '" data-fmt="pdf">Export PDF</button>' +
        "</div></div>";
    }).join("");
    return '<div class="callout">Reports are written to <b>' +
      esc(S.meta.downloads) + "</b></div>" +
      '<div class="reportgrid">' + cards + "</div>";
  },
  wire: function () {
    document.querySelectorAll("[data-rpt]").forEach(function (b) {
      b.onclick = function () {
        var extra = {};
        if (b.dataset.rpt === "statement") {
          var picked = el("stmtEmp").value;
          if (!picked) { toast("Select an employee first", "err"); return; }
          extra.employee_id = Number(picked);
        }
        if (b.dataset.rpt === "schedule") extra.year = Number(el("schedYear").value);
        runReport(b.dataset.rpt, b.dataset.fmt, extra);
      };
    });
  }
};

/* ------------------------------------------------------- backup / settings */
VIEWS.backup = {
  title: "Backup & Restore",
  sub: "move your data between computers",
  html: function () {
    var rows = (S.backups || []).map(function (b) {
      return "<tr><td><b>" + esc(b.filename) + "</b></td>" +
        '<td class="num">' + n0(Math.round(b.size / 1024)) + " KB</td>" +
        '<td class="wrap muted">' + esc(b.path) + "</td>" +
        '<td><button class="btn sm" data-restore="' + esc(b.path) + '">Restore</button></td></tr>';
    }).join("") || '<tr><td colspan="4" class="muted">No backups in the application folder yet</td></tr>';

    return '<div class="grid c2">' +
      '<div class="card"><header><h3>Create a Backup</h3></header><div class="body">' +
        "<p style='margin-top:0;color:var(--ink-2);line-height:1.6'>Writes a single backup " +
        "file containing the database and your settings. It is saved to your Downloads " +
        "folder, and a copy is kept inside the application folder.</p>" +
        '<div class="callout">Downloads folder<br><b>' + esc(S.meta.downloads) + "</b></div>" +
        '<button class="btn primary" id="doBackup">Create Backup Now</button>' +
      "</div></div>" +
      '<div class="card"><header><h3>Restore from a Backup</h3></header><div class="body">' +
        "<p style='margin-top:0;color:var(--ink-2);line-height:1.6'>Paste the full path of a " +
        "backup file, or restore one of the copies held in this folder. The current database " +
        "is copied aside first, so nothing is lost.</p>" +
        textField("restorePath", "Backup file path", "",
          { placeholder: "C:\\Users\\You\\Downloads\\EOSB_Backup_....eosbak" }) +
        '<button class="btn danger" id="doRestore">Restore This File</button>' +
      "</div></div></div>" +
      '<div class="card"><header><h3>Backups in the Application Folder</h3>' +
        '<div class="spacer"></div><span class="hint">' + esc(S.meta.root) + "</span></header>" +
        "<div class='body tight'><div class='tablewrap'><table class='data'><thead><tr>" +
        "<th>File</th><th class='num'>Size</th><th>Location</th><th></th></tr></thead><tbody>" +
        rows + "</tbody></table></div></div></div>" +
      '<div class="card"><header><h3>Where Your Data Lives</h3></header><div class="body">' +
        '<div class="grid c2">' + detail("Application folder", S.meta.root) +
        detail("Database file", S.meta.database) + "</div>" +
        '<div class="callout">Move or copy the whole application folder and the database ' +
        "travels with it. The launcher always opens the database stored beside it.</div>" +
      "</div></div>";
  },
  wire: function () {
    el("doBackup").onclick = function () {
      var button = el("doBackup");
      button.disabled = true;
      api("POST", "/api/backup/create", {}).then(function (result) {
        toast("Backup created", "ok", result.path);
        return loadBackups().then(render);
      }).catch(fail).then(function () { if (el("doBackup")) el("doBackup").disabled = false; });
    };
    el("doRestore").onclick = function () {
      var path = document.querySelector("[name=restorePath]").value.trim();
      if (!path) { toast("Enter the path of a backup file", "err"); return; }
      askRestore(path);
    };
    document.querySelectorAll("[data-restore]").forEach(function (b) {
      b.onclick = function () { askRestore(b.dataset.restore); };
    });
  }
};
function askRestore(path) {
  confirmDialog("Restore backup",
    "Replace all current data with the contents of:<br><br><b>" + esc(path) + "</b>" +
    "<br><br>The database being replaced is copied aside first.",
    "Restore", function () {
      api("POST", "/api/backup/restore", { path: path }).then(function (result) {
        var counts = result.counts || {};
        toast("Restore complete", "ok",
          counts.employees + " employees, " + counts.salary_history + " salary records");
        return loadBackups().then(function () { return reload(); });
      }).catch(fail);
    });
}
function loadBackups() {
  return api("GET", "/api/backup/list").then(function (data) {
    S.backups = data.backups;
    return refresh();
  });
}

VIEWS.settings = {
  title: "Settings",
  sub: "changes save immediately",
  html: function () {
    var s = S.settings;
    return '<div class="grid c2">' +
      '<div class="card"><header><h3>Organisation</h3></header><div class="body">' +
        textField("organisation_name", "Organisation Name", s.organisation_name) +
        textField("currency", "Currency", s.currency) +
        '<div class="grid c2">' +
          selectField("year_end_month", "Financial Year End Month", s.year_end_month,
            [{value:1,label:"January"},{value:2,label:"February"},{value:3,label:"March"},
             {value:4,label:"April"},{value:5,label:"May"},{value:6,label:"June"},
             {value:7,label:"July"},{value:8,label:"August"},{value:9,label:"September"},
             {value:10,label:"October"},{value:11,label:"November"},{value:12,label:"December"}]) +
          textField("year_end_day", "Day", s.year_end_day, { type: "number", min: 1 }) +
        "</div>" +
      "</div></div>" +
      '<div class="card"><header><h3>Entitlement Formula</h3>' +
        '<span class="hint">Saudi Labour Law, Article 84</span></header><div class="body">' +
        '<div class="callout">Entitlement = (days in first 5 years &divide; ' +
        esc(s.days_per_year) + " &times; salary &times; " + esc(s.first_period_factor) +
        ") + (days over 5 years &divide; " + esc(s.days_per_year) + " &times; salary &times; " +
        esc(s.later_period_factor) + ")</div>" +
        '<div class="grid c2">' +
          textField("first_period_days", "First Period Length (days)", s.first_period_days,
            { type: "number", min: 1, note: "1825 = 5 years" }) +
          textField("days_per_year", "Days per Year", s.days_per_year, { type: "number", min: 1 }) +
          textField("first_period_factor", "First Period Factor", s.first_period_factor,
            { type: "number", step: "0.01", note: "half a month" }) +
          textField("later_period_factor", "Later Period Factor", s.later_period_factor,
            { type: "number", step: "0.01", note: "one month" }) +
          textField("rounding_decimals", "Rounding (decimals)", s.rounding_decimals,
            { type: "number", min: 0 }) +
          selectField("apply_resignation_scale", "Article 85 on Resignation",
            String(s.apply_resignation_scale),
            [{ value: "true", label: "Apply to amount payable" },
             { value: "false", label: "Always pay the full award" }],
            "nothing under 2 years, one third 2-5, two thirds 5-10") +
        "</div>" +
      "</div></div></div>" +
      '<div class="card"><header><h3>Application</h3></header><div class="body">' +
        '<div class="grid c3">' +
          selectField("use_online_date", "Reporting Date Source", String(s.use_online_date),
            [{ value: "true", label: "Internet when available, then this computer" },
             { value: "false", label: "Always use this computer" }]) +
          selectField("open_browser", "Open Browser on Start", String(s.open_browser),
            [{ value: "true", label: "Yes" }, { value: "false", label: "No" }]) +
          textField("preferred_port", "Preferred Port", s.preferred_port, { type: "number" }) +
        "</div>" +
        '<div class="grid c2" style="margin-top:6px">' +
          detail("Reporting date in use", today() + "  (" + S.meta.clock.source + ")") +
          detail("This computer's date", S.meta.clock.system_date) +
        "</div>" +
      "</div></div>";
  },
  wire: function () {
    var BOOL = ["apply_resignation_scale", "use_online_date", "open_browser"];
    var NUM = ["first_period_days", "days_per_year", "first_period_factor",
               "later_period_factor", "rounding_decimals", "year_end_month",
               "year_end_day", "preferred_port"];
    document.querySelectorAll("#view [name]").forEach(function (input) {
      input.onchange = function () {
        var payload = {};
        var value = input.value;
        if (BOOL.indexOf(input.name) >= 0) value = value === "true";
        else if (NUM.indexOf(input.name) >= 0) value = Number(value);
        payload[input.name] = value;
        api("PUT", "/api/settings", payload).then(function () {
          flashSaved();
          toast("Setting saved", "ok");
          return reload();
        }).catch(fail);
      };
    });
  }
};

VIEWS.diagnostics = {
  title: "Diagnostics",
  sub: "where the data lives and whether it is healthy",
  html: function () {
    var h = S.health || {};
    var ok = h.ok;
    return '<div class="callout' + (ok ? "" : " warn") + '">' +
      (ok ? "The database is readable and its integrity check passed."
          : "<b>There is a problem with the database.</b> " + esc(h.error || h.integrity || "")) +
      "</div>" +
      '<div class="card"><header><h3>This Installation</h3></header><div class="body">' +
      '<div class="grid c2">' +
        detail("Application folder", h.folder) +
        detail("Database file", h.database) +
        detail("Database exists", h.exists ? "Yes" : "No") +
        detail("Folder is writable", h.writable ? "Yes" : "No — the application cannot save here") +
        detail("Database size", n0(h.size) + " bytes") +
        detail("Integrity check", h.integrity || "—") +
      "</div></div></div>" +
      '<div class="card"><header><h3>Record Counts</h3><div class="spacer"></div>' +
      '<button class="btn sm" id="reseedBtn">Restore the five opening employees</button>' +
      "</header><div class='body'><div class='grid c2'>" +
        detail("Employees", n0(h.employees)) +
        detail("Salary records", n0(h.salary_history)) +
        detail("Unpaid leave records", n0(h.unpaid_leave)) +
        detail("Benefit payments", n0(h.benefits_paid)) +
      "</div></div></div>";
  },
  wire: function () {
    el("reseedBtn").onclick = function () {
      confirmDialog("Restore opening employees",
        "Add the five employees from the original workbook back into the database?" +
        "<br><br>Existing records are not removed.", "Restore", function () {
          api("POST", "/api/reseed", {}).then(function () {
            toast("Opening employees restored", "ok");
            return loadHealth().then(function () { return reload(); });
          }).catch(fail);
        });
    };
  }
};
function loadHealth() {
  return api("GET", "/api/health").then(function (data) { S.health = data; })
    .catch(function () { S.health = { ok: false, error: "The health check did not answer." }; });
}

/* --------------------------------------------------------------------- boot */
document.querySelectorAll("#nav a").forEach(function (link) {
  link.onclick = function () { go(link.dataset.view); };
});
el("refreshBtn").onclick = function () {
  loadLists().then(loadBackups).then(loadHealth).then(render).then(function () { toast("Refreshed", "ok"); })
    .catch(fail);
};
el("quitBtn").onclick = function () {
  confirmDialog("Close the application",
    "Stop the application? All your changes are already saved.<br><br>" +
    "You can start it again from the launcher at any time.",
    "Close application", function () {
      api("POST", "/api/shutdown", {}).catch(function () {});
      setTimeout(function () {
        document.body.innerHTML =
          '<div style="display:flex;align-items:center;justify-content:center;' +
          'height:100vh;font:15px Segoe UI,Arial,sans-serif;color:#4a5768;' +
          'flex-direction:column;gap:8px">' +
          '<div style="font-size:19px;font-weight:600;color:#12233f">' +
          'The application has been closed</div>' +
          '<div>All data is saved. You can close this browser tab.</div></div>';
      }, 350);
    });
};
window.addEventListener("hashchange", function () {
  var name = location.hash.replace("#", "");
  if (VIEWS[name] && name !== S.view) { S.view = name; render(); }
});

var startView = location.hash.replace("#", "");
if (VIEWS[startView]) S.view = startView;

loadLists()
  .then(loadBackups)
  .then(loadHealth)
  .then(render)
  .catch(function (error) { startupFailure(error); });

function startupFailure(error) {
  el("view").innerHTML =
    '<div class="card"><header><h3>The application could not load its data</h3></header>' +
    '<div class="body">' +
    '<div class="callout warn"><b>' + esc(error.message) + "</b></div>" +
    "<p style='line-height:1.7'>The window is open but the data did not arrive. " +
    "The usual causes, in order:</p>" +
    "<ol style='line-height:1.9;padding-left:20px'>" +
    "<li><b>The folder was run from inside the ZIP.</b> Windows can open a ZIP " +
    "like a folder, but nothing written there is kept. Right-click the ZIP, " +
    "choose <b>Extract All</b>, then run <b>EOSB.bat</b> from the extracted folder.</li>" +
    "<li><b>The launcher window was closed.</b> The small black window must stay " +
    "open while you use the application.</li>" +
    "<li><b>Something else is wrong.</b> Double-click <b>DIAGNOSE.bat</b> in the " +
    "application folder. It writes <b>diagnostic_report.txt</b> describing exactly " +
    "what failed.</li></ol>" +
    '<button class="btn primary" onclick="location.reload()">Try again</button>' +
    "</div></div>";
}

})();
