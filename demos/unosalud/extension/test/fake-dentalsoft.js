/*
 * A stand-in for the booking's own script (`dentalsoft.min.js`, with jQuery,
 * jquery-validate and the datepicker), which the saved page does not carry.
 * It does what the real one does to the page, on the same native events, with
 * the server's answers made up: one fieldset per step shown in place, `#step`,
 * the región → comuna → clínica lists from `#jsonSucursales`, the calendar
 * (fengyuanchen's markup) and its hours, the review table, and IMask on the
 * phones (the real IMask). Every submit is recorded (`window.__submits`, with
 * the button that sent it) and held, as jQuery holds it.
 *
 * Its "today" is 2026-10-27, the day the page was saved. A day's hours: none
 * on a day divisible by 3, else 09:00, 10:30 and 16:15.
 */
(function () {
  "use strict";
  var TODAY = new Date(2026, 9, 27);
  var MONTHS = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];
  var form = document.getElementById("dentalsoft-form");
  var $ = function (id) { return document.getElementById(id); };
  var tree = JSON.parse($("jsonSucursales").textContent);
  window.__submits = [];
  window.__serverMs = 300;

  ["fono", "new_fono"].forEach(function (id) {
    if ($(id) && window.IMask) window.IMask($(id), { mask: "+{56}0 0000 0000" });
  });

  function show(step) {
    form.querySelectorAll(":scope > fieldset").forEach(function (f) { f.classList.add("d-none"); });
    $(step).classList.remove("d-none");
    $("step").value = step;
  }
  window.back_button = function (step) { show(step); };

  function option(select, value, text, extra) {
    var o = document.createElement("option");
    o.value = value;
    o.textContent = text;
    if (extra) { o.disabled = true; o.selected = true; }
    select.appendChild(o);
  }

  // The server's answers to each step.
  var NEXT = {
    "registro-paciente": "getMRes",
    "actualiza-datos": "getMRes",
    "selecciona-motivo": "getSuc",
    "continue_getSuc": "getHor",
    "continue_getHor": "getDC",
    "confirma-cita": "setRH",
    "ingresar-rut": "setPAC",
  };
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var by = e.submitter ? e.submitter.id : "";
    window.__submits.push(by);
    if (by === "selecciona-motivo" && $("motivo").value === "0") {
      $("dentalsoft-error").textContent = "Selecciona el motivo.";
      $("dentalsoft-error").classList.remove("d-none");
      return;
    }
    $("dentalsoft-error").classList.add("d-none");
    var next = NEXT[by];
    if (!next) return;
    setTimeout(function () {
      show(next);
      if (next === "getSuc") regions();
      if (next === "getHor") days();
      if (next === "getDC") review();
    }, window.__serverMs);
  }, true);

  function regions() {
    var r = $("region");
    r.innerHTML = "";
    option(r, "", "Selecciona una Región", true);
    Object.values(tree).sort(function (a, b) { return a.prioridad - b.prioridad; }).forEach(function (x) {
      option(r, x.id, x.descripcion.toUpperCase());
    });
    r.disabled = false;
  }
  $("region").addEventListener("change", function () {
    var c = $("comuna"), s = $("sucursal");
    c.innerHTML = ""; s.innerHTML = ""; s.disabled = true;
    $("continue_getSuc").setAttribute("disabled", "disabled");
    var reg = tree[$("region").value];
    option(c, "", "Selecciona una opción", true);
    (reg ? reg.getcomunas : []).slice().sort(function (a, b) { return a.descripcion.localeCompare(b.descripcion); }).forEach(function (x) {
      option(c, x.id, x.descripcion.toUpperCase());
    });
    c.disabled = false;
  });
  $("comuna").addEventListener("change", function () {
    var s = $("sucursal");
    s.innerHTML = "";
    var reg = tree[$("region").value];
    var com = reg && reg.getcomunas.find(function (x) { return x.id === $("comuna").value; });
    option(s, "", "Selecciona una opción", true);
    (com ? com.sucursales : []).forEach(function (x) { option(s, x.id, x.descripcion); });
    s.disabled = false;
  });
  $("sucursal").addEventListener("change", function () {
    if ($("sucursal").value) $("continue_getSuc").removeAttribute("disabled");
  });

  // ─── The calendar ─────────────────────────────────────────────────────
  var shown = new Date(TODAY.getFullYear(), TODAY.getMonth(), 1);
  var panel = document.querySelector('#datepicker-fecha .datepicker-panel[data-view="days picker"]');
  function pad(n) { return String(n).padStart(2, "0"); }
  function days() {
    var head = panel.querySelector('li[data-view="month current"]');
    head.textContent = shown.getFullYear() + " - " + MONTHS[shown.getMonth()];
    var prev = panel.querySelector('li[data-view="month prev"]');
    prev.classList.toggle("disabled", shown <= new Date(TODAY.getFullYear(), TODAY.getMonth(), 1));
    var ul = panel.querySelector('ul[data-view="days"]');
    ul.innerHTML = "";
    var first = new Date(shown);
    var lead = (first.getDay() + 6) % 7;
    for (var i = lead; i > 0; i--) {
      var li0 = document.createElement("li");
      li0.className = "muted disabled";
      li0.dataset.view = "day prev";
      li0.textContent = String(new Date(shown.getFullYear(), shown.getMonth(), 1 - i).getDate());
      ul.appendChild(li0);
    }
    var n = new Date(shown.getFullYear(), shown.getMonth() + 1, 0).getDate();
    for (var d = 1; d <= n; d++) {
      var li = document.createElement("li");
      var date = new Date(shown.getFullYear(), shown.getMonth(), d);
      var off = date < TODAY || date.getDay() === 0;
      li.className = off ? "disabled" : "";
      li.dataset.view = off ? "day disabled" : "day";
      li.textContent = String(d);
      ul.appendChild(li);
    }
  }
  panel.addEventListener("click", function (e) {
    var li = e.target.closest("li");
    if (!li) return;
    var view = li.dataset.view || "";
    if (view === "month next") { shown = new Date(shown.getFullYear(), shown.getMonth() + 1, 1); return days(); }
    if (view === "month prev" && !li.classList.contains("disabled")) { shown = new Date(shown.getFullYear(), shown.getMonth() - 1, 1); return days(); }
    if (!/^day/.test(view) || li.classList.contains("disabled") || li.classList.contains("muted")) return;
    var d = Number(li.textContent);
    $("fecha").value = pad(d) + "-" + pad(shown.getMonth() + 1) + "-" + shown.getFullYear();
    $("fecha").dispatchEvent(new Event("change"));
  });
  $("fecha").addEventListener("change", function () {
    $("loading-horas").textContent = "Cargando...";
    $("alert_seleccione_horario").classList.add("d-none");
    $("alert_sin_horarios").classList.add("d-none");
    $("horarios").innerHTML = "";
    var d = Number($("fecha").value.slice(0, 2));
    setTimeout(function () {
      $("loading-horas").textContent = "";
      if (d % 3 === 0) { $("alert_sin_horarios").classList.remove("d-none"); return; }
      ["09:00", "10:30", "16:15"].forEach(function (t) {
        var col = document.createElement("div");
        col.className = "col-4 mb-2";
        col.innerHTML = '<div class="option_hora selecciona-hora card py-2 small font-weight-bold" data-value="' + t + ':00|1|11111111-1"><div>' + t + "</div></div>";
        $("horarios").appendChild(col);
      });
      $("container_select_fecha").classList.add("ocultar");
      $("container_select_hora").classList.remove("ocultar");
      document.querySelectorAll("#horarios .option_hora").forEach(function (o) {
        o.addEventListener("click", function () {
          $("hora").value = o.dataset.value;
          $("continue_getHor").removeAttribute("disabled");
          $("continue_getHor").click();
        });
      });
    }, window.__serverMs);
  });
  window.showCalendar = function () {
    $("container_select_fecha").classList.remove("ocultar");
    $("container_select_hora").classList.add("ocultar");
    $("horarios").innerHTML = "";
    shown = new Date(TODAY.getFullYear(), TODAY.getMonth(), 1);
    days();
  };

  function review() {
    var f = $("fecha").value;
    var rows = [["Paciente", "M**** P****"], ["Fecha", f], ["Hora", $("hora").value.slice(0, 5)], ["Odontólogo", "Dra. Ana Pérez"],
      ["Dirección", $("sucursal").selectedOptions[0] ? $("sucursal").selectedOptions[0].textContent : ""], ["Referencia", "Metro"]];
    $("data-reserva").innerHTML = rows.map(function (r) { return "<tr><th><div>" + r[0] + ":</div></th><td>" + r[1] + "</td></tr>"; }).join("");
  }

  /** The visitor past the RUT gate, as the server would answer: a new
   *  patient (`setPAC`), or an existing one by name (`setEF`). */
  window.__ds = {
    as: function (step, name) {
      if (name) document.querySelectorAll(".user_name").forEach(function (u) { u.textContent = name; });
      show(step);
      if (step === "getSuc") regions();
      if (step === "getHor") days();
    },
  };
  days();
})();
