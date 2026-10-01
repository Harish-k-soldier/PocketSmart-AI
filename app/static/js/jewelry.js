'use strict';
(function () {
  const form = document.getElementById('jewelry-form');
  if (!form) return;

  const submitBtn = document.getElementById('jewelry-submit');
  const results = document.getElementById('results');
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('outfit_image');
  const preview = document.getElementById('image-preview');
  const previewImg = document.getElementById('image-preview-img');
  const removeBtn = document.getElementById('remove-image');
  const notes = document.getElementById('notes');
  const notesCounter = document.getElementById('notes-counter');
  const MAX_BYTES = 5 * 1024 * 1024;
  const ALLOWED = ['image/jpeg', 'image/png', 'image/webp'];
  let objectUrl = null;
  let requestSeq = 0;

  if (notes && notesCounter) {
    notes.addEventListener('input', () => {
      notesCounter.textContent = String(notes.value.length);
    });
  }

  function clearPreview() {
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
    if (preview) preview.hidden = true;
    if (previewImg) previewImg.src = '';
    if (fileInput) fileInput.value = '';
  }

  function showPreview(file) {
    if (!ALLOWED.includes(file.type)) {
      PS.showErrors({ outfit_image: 'Only JPEG, PNG, or WebP images are allowed.' }, null);
      return;
    }
    if (file.size > MAX_BYTES) {
      PS.showErrors({ outfit_image: 'Image must be 5 MB or smaller.' }, null);
      return;
    }
    PS.clearErrors();
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(file);
    previewImg.src = objectUrl;
    preview.hidden = false;
  }

  if (dropzone && fileInput) {
    dropzone.addEventListener('click', () => fileInput.click());
    dropzone.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        fileInput.click();
      }
    });
    fileInput.addEventListener('change', () => {
      if (fileInput.files && fileInput.files[0]) showPreview(fileInput.files[0]);
    });
    ['dragover', 'dragenter'].forEach((evt) => {
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
      });
    });
    ['dragleave', 'drop'].forEach((evt) => {
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
      });
    });
    dropzone.addEventListener('drop', (e) => {
      const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) {
        showPreview(file);
        try {
          const dt = new DataTransfer();
          dt.items.add(file);
          fileInput.files = dt.files;
        } catch (err) {
          // Some browsers don't allow setting files; preview still works.
        }
      }
    });
  }

  if (removeBtn) {
    removeBtn.addEventListener('click', clearPreview);
  }

  function validate() {
    const errors = {};
    const budget = Number(document.getElementById('budget').value);
    if (!Number.isInteger(budget) || budget < 500 || budget > 5000000) {
      errors.budget = 'Budget must be a whole number between ₹500 and ₹50,00,000.';
    }
    return errors;
  }

  function updateBudgetBar(plan) {
    const fill = document.querySelector('[data-budget-bar-fill]');
    const label = document.querySelector('[data-budget-bar-label]');
    const remaining = document.querySelector('[data-budget-bar-remaining]');
    if (!fill || !label || !remaining) return;
    const pct = Math.min(100, Math.max(0, (plan.total_spent / plan.budget_total) * 100));
    fill.style.width = pct.toFixed(1) + '%';
    fill.classList.toggle('warn', pct >= 85);
    label.textContent = 'Spent: ' + PS.formatINR(plan.total_spent) + ' of ' + PS.formatINR(plan.budget_total);
    remaining.textContent = 'Remaining: ' + PS.formatINR(plan.remaining);
    fill.setAttribute('role', 'progressbar');
    fill.setAttribute('aria-valuenow', String(Math.round(pct)));
    fill.setAttribute('aria-valuemin', '0');
    fill.setAttribute('aria-valuemax', '100');
  }

  function badgeClass(platform) {
    return 'badge badge-' + String(platform).replace(/[^A-Za-z]/g, '');
  }

  function renderResults(plan) {
    results.innerHTML = '';
    results.hidden = false;

    if (plan.notice) {
      const banner = document.createElement('div');
      banner.className = 'notice-banner';
      banner.textContent = plan.notice;
      results.appendChild(banner);
    }

    const summary = document.createElement('div');
    summary.className = 'summary-card';
    const grid = document.createElement('div');
    grid.className = 'summary-grid';
    [
      ['Budget', PS.formatINR(plan.budget_total)],
      ['Spent', PS.formatINR(plan.total_spent)],
      ['Remaining', PS.formatINR(plan.remaining)],
    ].forEach(([lbl, val]) => {
      const stat = document.createElement('div');
      stat.className = 'summary-stat';
      const l = document.createElement('div');
      l.className = 'stat-label';
      l.textContent = lbl;
      const v = document.createElement('div');
      v.className = 'stat-value';
      v.textContent = val;
      stat.appendChild(l);
      stat.appendChild(v);
      grid.appendChild(stat);
    });
    summary.appendChild(grid);
    const bar = document.createElement('div');
    bar.className = 'budget-bar';
    bar.innerHTML =
      '<div class="budget-bar-track"><div class="budget-bar-fill" data-budget-bar-fill style="width:0%"></div></div>' +
      '<div class="budget-bar-meta"><span data-budget-bar-label>Spent: ₹0</span><span data-budget-bar-remaining>Remaining: ₹0</span></div>';
    summary.appendChild(bar);
    results.appendChild(summary);

    if (plan.palette && plan.palette.length > 0) {
      const paletteRow = document.createElement('div');
      paletteRow.className = 'palette-row';
      const label = document.createElement('span');
      label.className = 'item-row-meta';
      label.textContent = 'Outfit palette:';
      paletteRow.appendChild(label);
      plan.palette.forEach((color) => {
        const swatch = document.createElement('span');
        swatch.className = 'swatch';
        const dot = document.createElement('span');
        dot.className = 'swatch-color';
        dot.style.backgroundColor = color.hex;
        dot.setAttribute('aria-hidden', 'true');
        const name = document.createElement('span');
        name.textContent = (color.name || '') + ' ' + color.hex;
        swatch.appendChild(dot);
        swatch.appendChild(name);
        paletteRow.appendChild(swatch);
      });
      results.appendChild(paletteRow);
    }

    const actions = document.createElement('div');
    actions.className = 'results-actions';
    const printBtn = document.createElement('button');
    printBtn.type = 'button';
    printBtn.className = 'btn btn-secondary';
    printBtn.textContent = 'Save / Print plan';
    printBtn.addEventListener('click', () => PS.printPlan());
    const copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.className = 'btn btn-ghost';
    copyBtn.textContent = 'Copy summary';
    copyBtn.addEventListener('click', async () => {
      const lines = [
        'PocketSmart AI — Jewelry Plan',
        'Budget: ' + PS.formatINR(plan.budget_total),
        'Spent: ' + PS.formatINR(plan.total_spent),
        'Remaining: ' + PS.formatINR(plan.remaining),
      ];
      plan.recommendations.forEach((r) => {
        lines.push('  - ' + r.name + ' (' + r.platform + ') ' + PS.formatINR(r.price) + ' — match ' + r.match_score + '/100');
      });
      const ok = await PS.copyText(lines.join('\n'));
      copyBtn.textContent = ok ? 'Copied!' : 'Copy failed';
      setTimeout(() => { copyBtn.textContent = 'Copy summary'; }, 2000);
    });
    actions.appendChild(printBtn);
    actions.appendChild(copyBtn);
    results.appendChild(actions);

    plan.recommendations.forEach((rec) => {
      const card = document.createElement('div');
      card.className = 'jewelry-card';
      const top = document.createElement('div');
      top.className = 'jewelry-card-top';
      const img = document.createElement('img');
      img.src = rec.image || '/static/img/placeholder.svg';
      img.alt = '';
      img.loading = 'lazy';
      img.onerror = function () { this.src = '/static/img/placeholder.svg'; };
      top.appendChild(img);
      const mid = document.createElement('div');
      const nameRow = document.createElement('div');
      nameRow.style.display = 'flex';
      nameRow.style.alignItems = 'center';
      nameRow.style.gap = '8px';
      nameRow.style.flexWrap = 'wrap';
      const name = document.createElement('span');
      name.className = 'jewelry-card-name';
      name.textContent = rec.name;
      const score = document.createElement('span');
      score.className = 'match-score';
      score.textContent = 'Match ' + rec.match_score + '/100';
      nameRow.appendChild(name);
      nameRow.appendChild(score);
      mid.appendChild(nameRow);
      const price = document.createElement('div');
      price.className = 'option-card-price';
      price.textContent = PS.formatINR(rec.price) + ' · ' + rec.platform;
      mid.appendChild(price);
      if (rec.why_it_matches) {
        const why = document.createElement('p');
        why.className = 'jewelry-card-why';
        why.textContent = rec.why_it_matches;
        mid.appendChild(why);
      }
      const link = document.createElement('a');
      link.className = 'option-card-link';
      link.href = rec.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'View on ' + rec.platform;
      mid.appendChild(link);
      top.appendChild(mid);
      const badge = document.createElement('span');
      badge.className = badgeClass(rec.platform);
      badge.textContent = rec.platform;
      badge.style.alignSelf = 'flex-start';
      top.appendChild(badge);
      card.appendChild(top);
      results.appendChild(card);
    });

    updateBudgetBar(plan);
    results.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    PS.clearErrors();
    const errors = validate();
    if (Object.keys(errors).length > 0) {
      PS.showErrors(errors, 'Please fix the highlighted fields and try again.');
      return;
    }
    const seq = ++requestSeq;
    const formData = new FormData();
    formData.append('budget', document.getElementById('budget').value);
    formData.append('occasion', form.querySelector('input[name="occasion"]:checked').value);
    formData.append('style', form.querySelector('input[name="style"]:checked').value);
    formData.append('metal', document.getElementById('metal').value);
    formData.append('stone', document.getElementById('stone').value);
    formData.append('notes', notes ? notes.value : '');
    if (fileInput && fileInput.files && fileInput.files[0]) {
      formData.append('outfit_image', fileInput.files[0]);
    }
    submitBtn.disabled = true;
    PS.showSpinner();
    results.hidden = true;
    try {
      const plan = await PS.postForm('/api/jewelry-plan', formData);
      if (seq !== requestSeq) return;
      if (plan.status === 'insufficient_budget') {
        PS.showErrors({}, plan.message + ' Minimum required: ' + PS.formatINR(plan.minimum_required));
        return;
      }
      renderResults(plan);
    } catch (err) {
      if (seq !== requestSeq) return;
      PS.showErrors(err.fieldErrors || {}, err.message || 'Something went wrong. Please try again.');
    } finally {
      if (seq === requestSeq) {
        PS.hideSpinner();
        submitBtn.disabled = false;
      }
    }
  });

  window.addEventListener('pageshow', (event) => {
    if (event.persisted) {
      PS.hideSpinner();
      submitBtn.disabled = false;
    }
  });
})();
