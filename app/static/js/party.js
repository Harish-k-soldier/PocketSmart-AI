'use strict';
(function () {
  const form = document.getElementById('party-form');
  if (!form) return;

  const submitBtn = document.getElementById('party-submit');
  const results = document.getElementById('results');
  const stayToggle = document.getElementById('guests_travelling');
  const stayFields = document.getElementById('stay-fields');
  const notes = document.getElementById('notes');
  const notesCounter = document.getElementById('notes-counter');
  let requestSeq = 0;
  let lastPlan = null;
  let chart = null;

  if (stayToggle && stayFields) {
    stayToggle.addEventListener('change', () => {
      stayFields.hidden = !stayToggle.checked;
    });
  }

  if (notes && notesCounter) {
    notes.addEventListener('input', () => {
      notesCounter.textContent = String(notes.value.length);
    });
  }

  function validate() {
    const errors = {};
    const budget = Number(document.getElementById('budget').value);
    if (!Number.isInteger(budget) || budget < 5000 || budget > 50000000) {
      errors.budget = 'Budget must be a whole number between ₹5,000 and ₹5,00,00,000.';
    }
    const guests = Number(document.getElementById('guests').value);
    if (!Number.isInteger(guests) || guests < 2 || guests > 2000) {
      errors.guests = 'Guest count must be a whole number between 2 and 2000.';
    }
    const duration = Number(document.getElementById('duration_hours').value);
    if (!Number.isInteger(duration) || duration < 1 || duration > 24) {
      errors.duration_hours = 'Duration must be a whole number between 1 and 24 hours.';
    }
    if (stayToggle && stayToggle.checked) {
      const stayGuests = Number(document.getElementById('stay_guests').value);
      if (!Number.isInteger(stayGuests) || stayGuests < 1) {
        errors.stay_guests = 'Guests needing stay must be at least 1.';
      } else if (Number.isInteger(guests) && stayGuests > guests) {
        errors.stay_guests = 'Guests needing stay cannot exceed the total guest count.';
      }
      const nights = Number(document.getElementById('nights').value);
      if (!Number.isInteger(nights) || nights < 1 || nights > 7) {
        errors.nights = 'Nights must be a whole number between 1 and 7.';
      }
    }
    return errors;
  }

  function collectPayload() {
    const payload = {
      budget: Number(document.getElementById('budget').value),
      guests: Number(document.getElementById('guests').value),
      event_type: form.querySelector('input[name="event_type"]:checked').value,
      venue_type: form.querySelector('input[name="venue_type"]:checked').value,
      city: document.getElementById('city').value,
      duration_hours: Number(document.getElementById('duration_hours').value),
      guests_travelling: stayToggle ? stayToggle.checked : false,
      notes: notes ? notes.value : '',
    };
    if (payload.guests_travelling) {
      payload.stay_guests = Number(document.getElementById('stay_guests').value);
      payload.nights = Number(document.getElementById('nights').value);
    }
    return payload;
  }

  function badgeClass(platform) {
    return 'badge badge-' + String(platform).replace(/[^A-Za-z]/g, '');
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

  function renderChart(plan) {
    const canvas = document.getElementById('allocation-chart');
    const tableWrap = document.getElementById('allocation-table-wrap');
    if (!canvas || !tableWrap) return;
    if (typeof window.Chart === 'undefined') {
      canvas.hidden = true;
      tableWrap.hidden = false;
      return;
    }
    if (chart) {
      chart.destroy();
      chart = null;
    }
    const labels = plan.allocation.map((a) => a.label);
    const data = plan.allocation.map((a) => a.amount);
    const colors = ['#0f5e5a', '#d97706', '#2874f0', '#e23744'];
    try {
      chart = new window.Chart(canvas, {
        type: 'doughnut',
        data: {
          labels,
          datasets: [{ data, backgroundColor: colors, borderWidth: 2, borderColor: '#fff' }],
        },
        options: {
          responsive: true,
          plugins: {
            legend: { position: 'bottom' },
            tooltip: {
              callbacks: {
                label: (ctx) => ' ' + ctx.label + ': ' + PS.formatINR(ctx.parsed),
              },
            },
          },
        },
      });
      canvas.hidden = false;
      tableWrap.hidden = true;
    } catch (e) {
      canvas.hidden = true;
      tableWrap.hidden = false;
    }
  }

  function renderAllocationTable(plan) {
    const wrap = document.getElementById('allocation-table-wrap');
    if (!wrap) return;
    const table = document.createElement('table');
    table.className = 'allocation-table';
    table.style.width = '100%';
    table.style.borderCollapse = 'collapse';
    const thead = document.createElement('thead');
    const hr = document.createElement('tr');
    ['Category', 'Allocated', 'Spent'].forEach((h) => {
      const th = document.createElement('th');
      th.textContent = h;
      th.style.textAlign = 'left';
      th.style.padding = '4px 8px';
      th.style.borderBottom = '1px solid #e5e7eb';
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    const tbody = document.createElement('tbody');
    plan.allocation.forEach((a) => {
      const tr = document.createElement('tr');
      [a.label, PS.formatINR(a.amount), PS.formatINR(a.spent)].forEach((val) => {
        const td = document.createElement('td');
        td.textContent = val;
        td.style.padding = '4px 8px';
        td.style.borderBottom = '1px solid #f0f0f0';
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(thead);
    table.appendChild(tbody);
    wrap.innerHTML = '';
    wrap.appendChild(table);
  }

  function renderResults(plan) {
    lastPlan = plan;
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
      ['Per guest', PS.formatINR(plan.per_guest_cost)],
      ['Event', plan.event_type.charAt(0).toUpperCase() + plan.event_type.slice(1)],
      ['Guests', String(plan.guests)],
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

    const chartCard = document.createElement('div');
    chartCard.className = 'summary-card';
    const chartTitle = document.createElement('h2');
    chartTitle.style.marginTop = '0';
    chartTitle.textContent = 'Budget allocation';
    chartCard.appendChild(chartTitle);
    const canvas = document.createElement('canvas');
    canvas.id = 'allocation-chart';
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', 'Doughnut chart of budget allocation by category');
    chartCard.appendChild(canvas);
    const tableWrap = document.createElement('div');
    tableWrap.id = 'allocation-table-wrap';
    tableWrap.className = 'visually-hidden';
    tableWrap.setAttribute('aria-hidden', 'true');
    chartCard.appendChild(tableWrap);
    results.appendChild(chartCard);

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
        'PocketSmart AI — Party Plan',
        'Event: ' + plan.event_type + ' · Guests: ' + plan.guests,
        'Budget: ' + PS.formatINR(plan.budget_total),
        'Spent: ' + PS.formatINR(plan.total_spent),
        'Remaining: ' + PS.formatINR(plan.remaining),
        'Per guest: ' + PS.formatINR(plan.per_guest_cost),
      ];
      plan.allocation.forEach((a) => {
        lines.push('', a.label + ' (' + PS.formatINR(a.spent) + ' of ' + PS.formatINR(a.amount) + ')');
        a.options.forEach((o) => {
          if (o.id === (a.options.find((x) => x.is_recommended) || {}).id) {
            lines.push('  - ' + o.name + ' (' + o.platform + ') ' + PS.formatINR(o.total_cost));
          }
        });
      });
      const ok = await PS.copyText(lines.join('\n'));
      copyBtn.textContent = ok ? 'Copied!' : 'Copy failed';
      setTimeout(() => { copyBtn.textContent = 'Copy summary'; }, 2000);
    });
    actions.appendChild(printBtn);
    actions.appendChild(copyBtn);
    results.appendChild(actions);

    plan.allocation.forEach((alloc) => {
      const section = document.createElement('section');
      section.className = 'category-section';
      const h2 = document.createElement('h2');
      h2.textContent = alloc.label;
      const amount = document.createElement('p');
      amount.className = 'category-amount';
      amount.textContent = PS.formatINR(alloc.spent) + ' spent of ' + PS.formatINR(alloc.amount) + ' allocated';
      section.appendChild(h2);
      section.appendChild(amount);

      if (!alloc.options.length) {
        const note = document.createElement('p');
        note.className = 'unavailable-note';
        note.textContent = 'No matching vendors in the catalog for this budget.';
        section.appendChild(note);
      } else {
        const gridEl = document.createElement('div');
        gridEl.className = 'options-grid';
        const onSelect = (itemId) => {
          const current = alloc.options.find((o) => o.is_recommended);
          const next = alloc.options.find((o) => o.id === itemId);
          if (!next || (current && next.id === current.id)) return;
          const delta = current ? next.total_cost - current.total_cost : next.total_cost;
          if (plan.total_spent + delta > plan.budget_total) {
            PS.showErrors({}, 'That option would exceed your budget. Pick a cheaper one.');
            return;
          }
          alloc.options.forEach((o) => { o.is_recommended = o.id === itemId; });
          alloc.spent = next.total_cost;
          plan.total_spent += delta;
          plan.remaining = plan.budget_total - plan.total_spent;
          plan.per_guest_cost = plan.guests > 0 ? Math.round(plan.total_spent / plan.guests) : 0;
          gridEl.querySelectorAll('.option-card').forEach((card) => {
            const isSel = card.dataset.itemId === itemId;
            card.classList.toggle('selected', isSel);
            card.setAttribute('aria-pressed', String(isSel));
            const nameEl = card.querySelector('.option-card-name');
            const existing = nameEl.querySelector('.recommended-tag');
            if (existing) existing.remove();
            if (isSel) {
              const tag = document.createElement('span');
              tag.className = 'recommended-tag';
              tag.textContent = 'Recommended';
              nameEl.appendChild(tag);
            }
          });
          amount.textContent = PS.formatINR(alloc.spent) + ' spent of ' + PS.formatINR(alloc.amount) + ' allocated';
          updateBudgetBar(plan);
          renderChart(plan);
          PS.clearErrors();
        };
        alloc.options.forEach((opt) => {
          const card = document.createElement('button');
          card.type = 'button';
          card.className = 'option-card' + (opt.is_recommended ? ' selected' : '');
          card.dataset.itemId = opt.id;
          card.setAttribute('aria-pressed', String(opt.is_recommended));
          const top = document.createElement('div');
          top.className = 'option-card-top';
          const img = document.createElement('img');
          img.src = opt.image || '/static/img/placeholder.svg';
          img.alt = '';
          img.loading = 'lazy';
          img.onerror = function () { this.src = '/static/img/placeholder.svg'; };
          top.appendChild(img);
          const mid = document.createElement('div');
          const name = document.createElement('div');
          name.className = 'option-card-name';
          name.textContent = opt.name;
          if (opt.is_recommended) {
            const tag = document.createElement('span');
            tag.className = 'recommended-tag';
            tag.textContent = 'Recommended';
            name.appendChild(tag);
          }
          mid.appendChild(name);
          const body = document.createElement('div');
          body.className = 'option-card-body';
          const price = document.createElement('div');
          price.className = 'option-card-price';
          price.textContent = PS.formatINR(opt.total_cost) + ' (' + PS.formatINR(opt.unit_price) + ' ' + opt.price_unit.replace(/_/g, ' ') + ')';
          body.appendChild(price);
          if (opt.reason) {
            const reason = document.createElement('p');
            reason.className = 'option-card-reason';
            reason.textContent = opt.reason;
            body.appendChild(reason);
          }
          const link = document.createElement('a');
          link.className = 'option-card-link';
          link.href = opt.url;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          link.textContent = 'View on ' + opt.platform;
          body.appendChild(link);
          mid.appendChild(body);
          top.appendChild(mid);
          const badge = document.createElement('span');
          badge.className = badgeClass(opt.platform);
          badge.textContent = opt.platform;
          badge.style.alignSelf = 'flex-start';
          top.appendChild(badge);
          card.appendChild(top);
          card.addEventListener('click', () => onSelect(opt.id));
          gridEl.appendChild(card);
        });
        section.appendChild(gridEl);
      }
      results.appendChild(section);
    });

    renderAllocationTable(plan);
    renderChart(plan);
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
    submitBtn.disabled = true;
    PS.showSpinner();
    results.hidden = true;
    try {
      const plan = await PS.postJSON('/api/party-plan', collectPayload());
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
