/*
 * A stand-in for the Brevo form's own helpers on the site's lead pages, which
 * the saved pages do not carry, held back as LiteSpeed holds the real ones:
 * `cargarComunas` (the comunas of `#REGION_2`, filled on its click) and
 * `validarRut` exist only after the first mouse move, key or touch. Every
 * submit is recorded (`window.__submits`) and held; `__brevo.answer(ok)`
 * shows Brevo's success or error panel, as its XHR would.
 */
(function () {
  "use strict";
  var COMUNAS = { "7": [["118", "Providencia"], ["115", "Santiago"], ["122", "Ñuñoa"], ["107", "Las Condes"]], "6": [["60", "Valparaíso"], ["61", "Viña del Mar"]] };
  window.__submits = [];
  var form = document.getElementById("sib-form");
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    window.__submits.push(e.submitter ? e.submitter.textContent.trim() : "form");
  }, true);
  function wake() {
    if (window.cargarComunas) return;
    window.cargarComunas = function () {
      var r = document.getElementById("REGION_2");
      var c = document.getElementById("COMUNA_2");
      if (!r || !c) return;
      c.innerHTML = '<option value="*" disabled selected hidden>Selecciona tu comuna</option>';
      (COMUNAS[r.value] || []).forEach(function (x) {
        var o = document.createElement("option");
        o.value = x[0];
        o.textContent = x[1];
        c.appendChild(o);
      });
    };
    window.validarRut = function (v) {
      var m = document.getElementById("mensaje");
      if (m) m.textContent = v.length < 8 ? "RUT demasiado corto" : "RUT válido";
    };
  }
  ["mousemove", "keydown", "touchstart", "wheel"].forEach(function (t) { window.addEventListener(t, wake, { once: true }); });
  window.__brevo = {
    answer: function (ok) {
      var p = document.getElementById(ok ? "success-message" : "error-message");
      p.classList.add("sib-form-message-panel--active");
      p.style.display = "block";
    },
  };
})();
