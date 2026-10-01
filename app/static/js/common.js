'use strict';
(function () {
  const PS = {};

  PS.formatINR = function (n) {
    let value = Number(n);
    if (n === null || n === undefined || n === '' || isNaN(value) || !isFinite(value)) {
      return '₹0';
    }
    const rounded = Math.round(value);
    const sign = rounded < 0 ? '-' : '';
    let digits = String(Math.abs(rounded));
    let grouped;
    if (digits.length <= 3) {
      grouped = digits;
    } else {
      const last3 = digits.slice(-3);
      let rest = digits.slice(0, -3);
      const parts = [];
      while (rest.length > 2) {
        parts.unshift(rest.slice(-2));
        rest = rest.slice(0, -2);
      }
      if (rest) parts.unshift(rest);
      grouped = parts.join(',') + ',' + last3;
    }
    return '₹' + sign + grouped;
  };

  PS.escapeText = function (str) {
    const div = document.createElement('div');
    div.textContent = String(str == null ? '' : str);
    return div.innerHTML;
  };

  PS.debounce = function (fn, wait) {
    let timer = null;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), wait);
    };
  };

  PS.showSpinner = function () {
    const el = document.getElementById('spinner');
    if (el) el.hidden = false;
  };

  PS.hideSpinner = function () {
    const el = document.getElementById('spinner');
    if (el) el.hidden = true;
  };

  PS.showErrors = function (fieldErrors, summary) {
    const box = document.getElementById('error-box');
    const list = document.getElementById('error-box-list');
    if (!box || !list) return;
    PS.clearErrors();
    const items = [];
    if (summary) {
      items.push(document.createTextNode(summary));
    }
    Object.keys(fieldErrors || {}).forEach((field) => {
      const msg = fieldErrors[field];
      const errEl = document.querySelector(`[data-error-for="${field}"]`);
      if (errEl) {
        errEl.textContent = msg;
        errEl.hidden = false;
      }
      const li = document.createElement('li');
      li.textContent = msg;
      items.push(li);
    });
    items.forEach((node) => list.appendChild(node));
    box.hidden = false;
    box.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  PS.clearErrors = function () {
    const box = document.getElementById('error-box');
    const list = document.getElementById('error-box-list');
    if (box) box.hidden = true;
    if (list) list.innerHTML = '';
    document.querySelectorAll('.field-error').forEach((el) => {
      el.textContent = '';
      el.hidden = true;
    });
  };

  async function request(url, options, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs || 60000);
    try {
      const response = await fetch(url, { ...options, signal: controller.signal });
      let data = null;
      const text = await response.text();
      try {
        data = text ? JSON.parse(text) : null;
      } catch (e) {
        data = null;
      }
      if (!response.ok) {
        const err = new Error('Request failed');
        err.status = response.status;
        err.data = data;
        throw err;
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  }

  PS.postJSON = function (url, payload) {
    return request(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }, 60000).then((data) => {
      if (data && data.error) {
        const err = new Error(data.error.message || 'Request failed');
        err.fieldErrors = data.error.fields || {};
        err.code = data.error.code;
        throw err;
      }
      return data;
    });
  };

  PS.postForm = function (url, formData) {
    return request(url, {
      method: 'POST',
      body: formData,
    }, 60000).then((data) => {
      if (data && data.error) {
        const err = new Error(data.error.message || 'Request failed');
        err.fieldErrors = data.error.fields || {};
        err.code = data.error.code;
        throw err;
      }
      return data;
    });
  };

  PS.printPlan = function () {
    window.print();
  };

  PS.copyText = async function (text) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (e) {
      // fall through to textarea fallback
    }
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'absolute';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand('copy');
    } catch (e) {
      ok = false;
    }
    document.body.removeChild(ta);
    return ok;
  };

  window.PS = PS;
})();
