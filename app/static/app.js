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
      const cur = currencyValue();
      if (cur === "USD" || cur === "UYU") return round2(amt * r);
      return amt; // cargado en ARS
    }
    function totalUsd() {
      const amt = parseNum(amount.value);
      const r = parseNum(rate.value);
      const cur = currencyValue();
      if (cur === "USD") return amt;
      if (cur === "UYU") return 0; // sin equivalente directo en dólares
      return r > 0 ? round2(amt / r) : 0;
    }
    // En "nuevo pago" la cotización que trae el server es solo una sugerencia:
    // al cambiar de moneda la reemplazamos por la de esa moneda. Si el usuario
    // ya la tocó, o si está editando un pago existente, la respetamos.
    let rateDirty = form.dataset.editing === "1";
    if (rate) rate.addEventListener("input", () => (rateDirty = true));

    function syncCurrencyUI() {
      const cur = currencyValue();
      const rateLabel = $("#rate-label", form);
      const rateTypeField = rateType ? rateType.closest(".field") : null;
      if (rateLabel) {
        rateLabel.textContent =
          cur === "UYU"
            ? "Cotización (ARS por peso uruguayo) *"
            : "Cotización (ARS por dólar) *";
      }
      if (rateTypeField) rateTypeField.style.display = cur === "UYU" ? "none" : "";
      if (outUsd) {
        const usdTile = outUsd.closest("div");
        if (usdTile) usdTile.style.opacity = cur === "UYU" ? 0.4 : 1;
      }
      if (rate && !rateDirty) {
        rate.value = (cur === "UYU" ? form.dataset.rateUyu : form.dataset.rateUsd) || "";
      }
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
      syncCurrencyUI();
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
    // Cambiar de moneda => querés la cotización de esa moneda: volvemos a
    // permitir el prellenado automático (salvo que después la toques o la traigas).
    currencyRadios.forEach((el) =>
      el.addEventListener("change", () => {
        if (form.dataset.editing !== "1") rateDirty = false;
        refreshContribControls();
      })
    );
    splitAuto.forEach((el) => el.addEventListener("change", refreshContribControls));
    contribInputs.forEach((el) => el.addEventListener("input", updateControl));

    /* ---- tipo de gasto: personal esconde el reparto 35/65 ---- */
    const expenseType = $("[name=expense_type]", form);
    const paidByField = $("#paid-by-field", form);
    const aportesCard = $("#aportes-card", form);
    function syncExpenseType() {
      const personal = expenseType && expenseType.value === "personal";
      if (paidByField) paidByField.hidden = !personal;
      if (aportesCard) aportesCard.hidden = personal;
    }
    if (expenseType) {
      expenseType.addEventListener("change", syncExpenseType);
      syncExpenseType();
    }

    /* ---- IVA discriminado: neto e IVA como la factura ---- */
    const vatChk = $("#vat-discrimina", form);
    const vatBox = $("#vat-box", form);
    const vatRate = $("#vat_rate", form);
    const vatNetoInp = $("#vat_neto", form);
    const vatIvaInp = $("#vat_iva", form);
    const vatSumEl = $("#vat-sum", form);
    const vatOtherEl = $("#vat-other", form);
    const vatTotalEl = $("#vat-total", form);
    // En edición respetamos lo guardado; en pago nuevo el prellenado manda.
    let vatTouched = form.dataset.editing === "1";

    function vatRatePct() {
      return vatRate ? parseNum(vatRate.value) : 21;
    }
    function prefillVat() {
      const total = totalArs();
      const r = vatRatePct();
      const iva = total > 0 && r > 0 ? round2(total - total / (1 + r / 100)) : 0;
      if (vatNetoInp) vatNetoInp.value = round2(total - iva).toFixed(2);
      if (vatIvaInp) vatIvaInp.value = iva.toFixed(2);
    }
    function updateVatSummary() {
      const net = vatNetoInp ? parseNum(vatNetoInp.value) : 0;
      const iva = vatIvaInp ? parseNum(vatIvaInp.value) : 0;
      const total = totalArs();
      if (vatSumEl) vatSumEl.textContent = fmtARS(round2(net + iva));
      if (vatOtherEl) vatOtherEl.textContent = fmtARS(round2(total - net - iva));
      if (vatTotalEl) vatTotalEl.textContent = fmtARS(total);
    }
    function syncVat() {
      const on = vatChk && vatChk.checked;
      if (vatBox) vatBox.hidden = !on;
      if (!on) return;
      if (!vatTouched) prefillVat();
      updateVatSummary();
    }
    if (vatChk)
      vatChk.addEventListener("change", () => {
        vatTouched = form.dataset.editing === "1";
        syncVat();
      });
    if (vatRate)
      vatRate.addEventListener("change", () => {
        vatTouched = false;
        syncVat();
      });
    [vatNetoInp, vatIvaInp].forEach(
      (el) =>
        el &&
        el.addEventListener("input", () => {
          vatTouched = true;
          updateVatSummary();
        })
    );
    [amount, rate].forEach((el) => el && el.addEventListener("input", syncVat));
    currencyRadios.forEach((el) => el.addEventListener("change", syncVat));
    syncVat();

    /* traer cotización */
    const fetchBtn = $("#fetch-rate");
    if (fetchBtn) {
      fetchBtn.addEventListener("click", async () => {
        fetchBtn.disabled = true;
        const original = fetchBtn.textContent;
        fetchBtn.textContent = "Consultando…";
        try {
          const tipo =
            currencyValue() === "UYU" ? "uyu" : rateType ? rateType.value : "oficial";
          const res = await fetch("/api/exchange-rate?tipo=" + encodeURIComponent(tipo));
          const data = await res.json();
          if (data.sugerido) {
            rate.value = parseFloat(data.sugerido).toFixed(2);
            rateDirty = true; // que syncCurrencyUI no lo vuelva a pisar
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

  /* ---------- venta: IVA discriminado ---------- */
  const saleForm = $("#sale-form");
  if (saleForm) initSaleVat(saleForm);

  function initSaleVat(form) {
    const chk = $("#vat-discrimina", form);
    if (!chk) return;
    const box = $("#vat-box", form);
    const rateSel = $("#vat_rate", form);
    const netoInp = $("#vat_neto", form);
    const ivaInp = $("#vat_iva", form);
    const sumEl = $("#vat-sum", form);
    const otherEl = $("#vat-other", form);
    const totalEl = $("#vat-total", form);
    const itemsBox = $("#items", form);
    let touched = form.dataset.editing === "1" || !!(netoInp && netoInp.value);

    function saleTotal() {
      let t = 0;
      $$(".item-row", itemsBox).forEach((row) => {
        const q = parseNum($("[data-name=item_qty]", row).value);
        const p = parseNum($("[data-name=item_price]", row).value);
        t += round2(q * p);
      });
      return round2(t);
    }
    function prefill() {
      const total = saleTotal();
      const r = rateSel ? parseNum(rateSel.value) : 21;
      const iva = total > 0 && r > 0 ? round2(total - total / (1 + r / 100)) : 0;
      if (netoInp) netoInp.value = round2(total - iva).toFixed(2);
      if (ivaInp) ivaInp.value = iva.toFixed(2);
    }
    function summary() {
      const net = netoInp ? parseNum(netoInp.value) : 0;
      const iva = ivaInp ? parseNum(ivaInp.value) : 0;
      const total = saleTotal();
      if (sumEl) sumEl.textContent = fmtARS(round2(net + iva));
      if (otherEl) otherEl.textContent = fmtARS(round2(total - net - iva));
      if (totalEl) totalEl.textContent = fmtARS(total);
    }
    function sync() {
      if (box) box.hidden = !chk.checked;
      if (!chk.checked) return;
      if (!touched) prefill();
      summary();
    }
    chk.addEventListener("change", () => {
      touched = form.dataset.editing === "1";
      sync();
    });
    if (rateSel)
      rateSel.addEventListener("change", () => {
        touched = false;
        sync();
      });
    [netoInp, ivaInp].forEach(
      (el) =>
        el &&
        el.addEventListener("input", () => {
          touched = true;
          summary();
        })
    );
    if (itemsBox) itemsBox.addEventListener("input", sync);
    sync();
  }

  /* ---------- service worker (instalable) ---------- */
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/sw.js").catch(() => {});
  }
})();
