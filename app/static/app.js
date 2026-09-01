/* Phantom Fish — JS mínimo, sin dependencias. */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const parseNum = (v) => {
    if (v == null) return 0;
    let s = String(v).trim().replace(/\s/g, "");
    if (s.includes(",") && s.lastIndexOf(",") > s.lastIndexOf(".")) {
      s = s.replace(/\./g, "").replace(",", ".");
    } else {
      s = s.replace(/,/g, "");
    }
    const n = parseFloat(s);
    return Number.isFinite(n) ? n : 0;
  };
  const fmtARS = (n) =>
    "$ " + n.toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtUSD = (n) =>
    "US$ " + n.toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const round2 = (n) => Math.round((n + Number.EPSILON) * 100) / 100;

  /* ---------- confirmación en borrados ---------- */
  $$("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (e) => {
      if (!window.confirm(form.dataset.confirm)) e.preventDefault();
    });
  });

  /* ---------- formulario de pago: cálculo en vivo ---------- */
  const payForm = $("#payment-form");
  if (payForm) initPaymentForm(payForm);

  function initPaymentForm(form) {
    const currencyRadios = $$("[name=currency_charged]", form);
    const amount = $("[name=amount_original]", form);
    const rate = $("[name=exchange_rate]", form);
    const rateType = $("[name=exchange_rate_type]", form);
    const outArs = $("#calc-ars");
    const outUsd = $("#calc-usd");
    const splitAuto = $$("[name=split_mode]", form);
    const contribInputs = $$("[data-contrib]", form);
    const sumEl = $("#contrib-sum");
    const totalEl = $("#contrib-total");
    const statusEl = $("#contrib-status");
    const box = $("#control-box");
    const pcts = JSON.parse(form.dataset.pcts || "{}");

    function currencyValue() {
      const c = currencyRadios.find((r) => r.checked);
      return c ? c.value : "USD";
    }
    function totalArs() {
      const amt = parseNum(amount.value);
      const r = parseNum(rate.value);
      if (currencyValue() === "USD") return round2(amt * r);
      return amt; // cargado en ARS
    }
    function totalUsd() {
      const amt = parseNum(amount.value);
      const r = parseNum(rate.value);
      if (currencyValue() === "USD") return amt;
      return r > 0 ? round2(amt / r) : 0;
    }
    function isAuto() {
      const checked = splitAuto.find((x) => x.checked);
      return !checked || checked.value === "auto";
    }
    function applyAutoSplit() {
      const t = totalArs();
      let running = 0;
      contribInputs.forEach((inp, i) => {
        const pid = inp.dataset.contrib;
        let share;
        if (i === contribInputs.length - 1) share = round2(t - running);
        else {
          share = round2((t * (parseFloat(pcts[pid]) || 0)) / 100);
          running += share;
        }
        inp.value = share.toFixed(2);
      });
    }
    function refreshContribControls() {
      const auto = isAuto();
      contribInputs.forEach((inp) => (inp.readOnly = auto));
      if (auto) applyAutoSplit();
      updateControl();
    }
    function updateControl() {
      const t = totalArs();
      let sum = 0;
      contribInputs.forEach((inp) => (sum += parseNum(inp.value)));
      sum = round2(sum);
      if (outArs) outArs.textContent = fmtARS(t);
      if (outUsd) outUsd.textContent = fmtUSD(totalUsd());
      if (sumEl) sumEl.textContent = fmtARS(sum);
      if (totalEl) totalEl.textContent = fmtARS(t);
      const ok = Math.abs(t - sum) < 0.01;
      if (box) {
        box.classList.toggle("control-ok", ok);
        box.classList.toggle("control-bad", !ok);
      }
      if (statusEl) {
        statusEl.textContent = ok
          ? "✓ Los aportes coinciden con el total"
          : "⚠ Diferencia: " + fmtARS(round2(t - sum));
      }
    }

    [amount, rate].forEach((el) =>
      el && el.addEventListener("input", refreshContribControls)
    );
    currencyRadios.forEach((el) => el.addEventListener("change", refreshContribControls));
    splitAuto.forEach((el) => el.addEventListener("change", refreshContribControls));
    contribInputs.forEach((el) => el.addEventListener("input", updateControl));

    /* traer cotización */
    const fetchBtn = $("#fetch-rate");
    if (fetchBtn) {
      fetchBtn.addEventListener("click", async () => {
        fetchBtn.disabled = true;
        const original = fetchBtn.textContent;
        fetchBtn.textContent = "Consultando…";
        try {
          const tipo = rateType ? rateType.value : "oficial";
          const res = await fetch("/api/exchange-rate?tipo=" + encodeURIComponent(tipo));
          const data = await res.json();
          if (data.sugerido) {
            rate.value = parseFloat(data.sugerido).toFixed(2);
            const note = $("#rate-note");
            if (note)
              note.textContent =
                "Dólar " + tipo + " " + fmtARS(parseFloat(data.sugerido)) +
                " · " + (data.fuente || "dolarapi.com") +
                ". Confirmá o ajustá el valor antes de guardar.";
            refreshContribControls();
          } else if (data.error) {
            alert("No se pudo obtener la cotización: " + data.error);
          }
        } catch (err) {
          alert("No se pudo obtener la cotización.");
        } finally {
          fetchBtn.disabled = false;
          fetchBtn.textContent = original;
        }
      });
    }

    refreshContribControls();
  }

  /* ---------- filas de items (compras / ventas) ---------- */
  const itemsBox = $("#items");
  if (itemsBox) initItemRows(itemsBox);

  function initItemRows(box) {
    const tpl = $("#item-template");
    const addBtn = $("#add-item");
    const currency = box.dataset.currency || "ARS";
    const totalEl = $("#items-total");

    function renumber() {
      $$(".item-row", box).forEach((row, i) => {
        $$("[data-name]", row).forEach((el) => {
          el.name = el.dataset.name + "_" + i;
        });
        const lbl = $(".item-row-n", row);
        if (lbl) lbl.textContent = "#" + (i + 1);
      });
    }
    function recalc() {
      let total = 0;
      $$(".item-row", box).forEach((row) => {
        const q = parseNum($("[data-name=item_qty]", row).value);
        const p = parseNum($("[data-name=item_price]", row).value);
        const line = round2(q * p);
        total += line;
        const out = $(".item-line-total", row);
        if (out) out.textContent = (currency === "USD" ? fmtUSD : fmtARS)(line);
      });
      if (totalEl) totalEl.textContent = (currency === "USD" ? fmtUSD : fmtARS)(round2(total));
    }
    function wire(row) {
      $$("[data-name=item_qty], [data-name=item_price]", row).forEach((el) =>
        el.addEventListener("input", recalc)
      );
      const del = $(".item-del", row);
      if (del)
        del.addEventListener("click", () => {
          row.remove();
          renumber();
          recalc();
        });
    }
    if (addBtn && tpl) {
      addBtn.addEventListener("click", () => {
        const node = tpl.content.firstElementChild.cloneNode(true);
        box.insertBefore(node, tpl);
        wire(node);
        renumber();
        recalc();
        $("[data-name=item_name]", node).focus();
      });
    }
    $$(".item-row", box).forEach(wire);
    renumber();
    recalc();
    if ($$(".item-row", box).length === 0 && addBtn) addBtn.click();
  }

  /* ---------- service worker (instalable) ---------- */
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/sw.js").catch(() => {});
  }
})();
