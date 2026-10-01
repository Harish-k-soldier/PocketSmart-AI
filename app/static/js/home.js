'use strict';
(function () {
  const ROOM_LABELS = {
    living_room: 'Living Room',
    kitchen: 'Kitchen',
    bedroom: 'Bedroom',
    dining_room: 'Dining Room',
    kids_room: 'Kids Room',
    study_room: 'Study/Home Office',
  };

  const ROOM_ITEMS = {
    living_room: { lights: 3, ceiling_fans: 1, sofas: 1, rugs: 1, curtains: 2, wall_decor: 2 },
    kitchen: { lights: 2, ceiling_fans: 1, kitchen_storage: 2 },
    bedroom: { lights: 2, ceiling_fans: 1, beds: 1, mattresses: 1, wardrobes: 1, curtains: 2 },
    dining_room: { lights: 2, ceiling_fans: 1, dining_tables: 1, curtains: 1 },
    kids_room: { lights: 2, ceiling_fans: 1, beds: 1, study_tables: 1, wardrobes: 1 },
    study_room: { lights: 2, ceiling_fans: 1, study_tables: 1, curtains: 1 },
  };

  const CATEGORY_LABELS = {
    lights: 'Lights', ceiling_fans: 'Ceiling Fans', sofas: 'Sofas', rugs: 'Rugs',
    curtains: 'Curtains', wall_decor: 'Wall Decor', kitchen_storage: 'Kitchen Storage',
    beds: 'Beds', mattresses: 'Mattresses', wardrobes: 'Wardrobes',
    dining_tables: 'Dining Tables', study_tables: 'Study Tables',
  };

  const form = document.getElementById('home-form');
  if (!form) return;

  const roomFields = document.getElementById('room-fields');
  const submitBtn = document.getElementById('home-submit');
  const results = document.getElementById('results');
  let requestSeq = 0;
  let lastPlan = null;

  function selectedRooms() {
    return Array.from(document.querySelectorAll('.chip[aria-pressed="true"]'))
      .map((c) => c.dataset.room);
  }

  function renderRoomFields() {
    const rooms = selectedRooms();
    roomFields.innerHTML = '';
    rooms.forEach((room) => {
      const fieldset = document.createElement('fieldset');
      fieldset.className = 'room-fieldset';
      fieldset.dataset.room = room;
      const legend = document.createElement('legend');
      legend.textContent = ROOM_LABELS[room] || room;
      fieldset.appendChild(legend);
      const grid = document.createElement('div');
      grid.className = 'room-items';
      Object.entries(ROOM_ITEMS[room] || {}).forEach(([cat, defQty]) => {
        const row = document.createElement('div');
        row.className = 'room-item';
        const label = document.createElement('label');
        label.htmlFor = `qty_${room}_${cat}`;
        label.textContent = CATEGORY_LABELS[cat] || cat;
        const input = document.createElement('input');
        input.type = 'number';
        input.id = `qty_${room}_${cat}`;
        input.min = '0';
        input.max = '10';
        input.step = '1';
        input.value = String(defQty);
        input.dataset.room = room;
        input.dataset.category = cat;
        row.appendChild(label);
        row.appendChild(input);
        grid.appendChild(row);
      });
      fieldset.appendChild(grid);
      roomFields.appendChild(fieldset);
    });
  }

  document.querySelectorAll('.chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      const pressed = chip.getAttribute('aria-pressed') === 'true';
      chip.setAttribute('aria-pressed', String(!pressed));
      renderRoomFields();
      PS.clearErrors();
    });
  });

  const notes = document.getElementById('notes');
  const notesCounter = document.getElementById('notes-counter');
  if (notes && notesCounter) {
    notes.addEventListener('input', () => {
      notesCounter.textContent = String(notes.value.length);
    });
  }

  function validate() {
    const errors = {};
    const budget = Number(document.getElementById('budget').value);
    if (!Number.isInteger(budget) || budget < 10000 || budget > 100000000) {
      errors.budget = 'Budget must be a whole number between ₹10,000 and ₹10,00,00,000.';
    }
    const rooms = selectedRooms();
    if (rooms.length === 0) {
      errors.rooms = 'Select at least one room.';
    }
    let anyItem = false;
    document.querySelectorAll('#room-fields input[type="number"]').forEach((input) => {
      const v = Number(input.value);
      if (!Number.isInteger(v) || v < 0 || v > 10) {
        errors.rooms = 'Quantities must be whole numbers between 0 and 10.';
      } else if (v > 0) {
        anyItem = true;
      }
    });
    if (rooms.length > 0 && !anyItem) {
      errors.rooms = 'Add at least one item.';
    }
    return errors;
  }

  function collectPayload() {
    const rooms = [];
    document.querySelectorAll('.room-fieldset').forEach((fieldset) => {
      const room = fieldset.dataset.room;
      const items = {};
      fieldset.querySelectorAll('input[type="number"]').forEach((input) => {
        const v = Number(input.value);
        if (Number.isInteger(v) && v > 0) items[input.dataset.category] = v;
      });
      if (Object.keys(items).length > 0) rooms.push({ name: room, items });
    });
    return {
      budget: Number(document.getElementById('budget').value),
      style: form.querySelector('input[name="style"]:checked').value,
      notes: notes ? notes.value : '',
      rooms,
    };
  }

  function badgeClass(platform) {
    return 'badge badge-' + String(platform).replace(/[^A-Za-z]/g, '');
  }

  function optionCard(item, quantity, selected, onSelect) {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'option-card' + (selected ? ' selected' : '');
    card.setAttribute('aria-pressed', String(selected));

    const top = document.createElement('div');
    top.className = 'option-card-top';

    const img = document.createElement('img');
    img.src = item.image || '/static/img/placeholder.svg';
    img.alt = '';
    img.loading = 'lazy';
    img.onerror = function () { this.src = '/static/img/placeholder.svg'; };
    top.appendChild(img);

    const mid = document.createElement('div');
    const name = document.createElement('div');
    name.className = 'option-card-name';
    name.textContent = item.name;
    if (selected) {
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
    price.textContent = PS.formatINR(item.unit_price) + ' each · ' + PS.formatINR(item.line_total) + ' total';
    body.appendChild(price);
    if (item.reason) {
      const reason = document.createElement('p');
      reason.className = 'option-card-reason';
      reason.textContent = item.reason;
      body.appendChild(reason);
    }
    const link = document.createElement('a');
    link.className = 'option-card-link';
    link.href = item.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'View on ' + item.platform;
    body.appendChild(link);
    mid.appendChild(body);
    top.appendChild(mid);

    const badge = document.createElement('span');
    badge.className = badgeClass(item.platform);
    badge.textContent = item.platform;
    badge.style.alignSelf = 'flex-start';
    top.appendChild(badge);

    card.appendChild(top);
    card.addEventListener('click', () => onSelect(item.id));
    return card;
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
    bar.setAttribute('data-budget-bar', '');
    bar.innerHTML =
      '<div class="budget-bar-track"><div class="budget-bar-fill" data-budget-bar-fill style="width:0%"></div></div>' +
      '<div class="budget-bar-meta"><span data-budget-bar-label>Spent: ₹0</span><span data-budget-bar-remaining>Remaining: ₹0</span></div>';
    summary.appendChild(bar);
    results.appendChild(summary);

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
        'PocketSmart AI — Home Plan',
        'Budget: ' + PS.formatINR(plan.budget_total),
        'Spent: ' + PS.formatINR(plan.total_spent),
        'Remaining: ' + PS.formatINR(plan.remaining),
      ];
      plan.rooms.forEach((room) => {
        lines.push('', room.label + ' (' + PS.formatINR(room.room_spent) + ')');
        room.items.forEach((item) => {
          const sel = item.options.find((o) => o.id === item.recommended_id);
          if (sel) lines.push('  - ' + item.label + ' x' + item.quantity + ': ' + sel.name + ' (' + PS.formatINR(sel.line_total) + ')');
        });
      });
      const ok = await PS.copyText(lines.join('\n'));
      copyBtn.textContent = ok ? 'Copied!' : 'Copy failed';
      setTimeout(() => { copyBtn.textContent = 'Copy summary'; }, 2000);
    });
    actions.appendChild(printBtn);
    actions.appendChild(copyBtn);
    results.appendChild(actions);

    const accordion = document.createElement('div');
    accordion.className = 'accordion';
    plan.rooms.forEach((room, roomIdx) => {
      const item = document.createElement('div');
      item.className = 'accordion-item';
      const header = document.createElement('button');
      header.type = 'button';
      header.className = 'accordion-header';
      header.setAttribute('aria-expanded', roomIdx === 0 ? 'true' : 'false');
      const title = document.createElement('span');
      title.textContent = room.label + ' — ' + PS.formatINR(room.room_spent) + ' of ' + PS.formatINR(room.room_budget);
      const chevron = document.createElement('span');
      chevron.className = 'chevron';
      chevron.textContent = '▾';
      chevron.setAttribute('aria-hidden', 'true');
      header.appendChild(title);
      header.appendChild(chevron);
      const panel = document.createElement('div');
      panel.className = 'accordion-panel';
      if (roomIdx !== 0) panel.hidden = true;

      room.items.forEach((itemResult) => {
        const row = document.createElement('div');
        row.className = 'item-row';
        const head = document.createElement('div');
        head.className = 'item-row-head';
        const h3 = document.createElement('h3');
        h3.textContent = itemResult.label + ' × ' + itemResult.quantity;
        const meta = document.createElement('span');
        meta.className = 'item-row-meta';
        meta.textContent = 'Ceiling ' + PS.formatINR(itemResult.unit_ceiling) + '/unit';
        head.appendChild(h3);
        head.appendChild(meta);
        row.appendChild(head);

        if (itemResult.unavailable || !itemResult.options.length) {
          const note = document.createElement('p');
          note.className = 'unavailable-note';
          note.textContent = 'No matching items in the catalog for this budget.';
          row.appendChild(note);
        } else {
          const gridEl = document.createElement('div');
          gridEl.className = 'options-grid';
          const onSelect = (itemId) => {
            const current = itemResult.recommended_id;
            if (itemId === current) return;
            const newSel = itemResult.options.find((o) => o.id === itemId);
            const oldSel = itemResult.options.find((o) => o.id === current);
            if (newSel && oldSel) {
              const delta = newSel.line_total - oldSel.line_total;
              if (plan.total_spent + delta > plan.budget_total) {
                PS.showErrors({}, 'That option would exceed your budget. Pick a cheaper one.');
                return;
              }
            }
            itemResult.recommended_id = itemId;
            plan.total_spent += delta;
            plan.remaining = plan.budget_total - plan.total_spent;
            room.room_spent = room.items.reduce((sum, it) => {
              const sel = it.options.find((o) => o.id === it.recommended_id);
              return sum + (sel ? sel.line_total : 0);
            }, 0);
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
            title.textContent = room.label + ' — ' + PS.formatINR(room.room_spent) + ' of ' + PS.formatINR(room.room_budget);
            updateBudgetBar(plan);
            PS.clearErrors();
          };
          itemResult.options.forEach((opt) => {
            const card = optionCard(opt, itemResult.quantity, opt.id === itemResult.recommended_id, onSelect);
            card.dataset.itemId = opt.id;
            gridEl.appendChild(card);
          });
          row.appendChild(gridEl);
        }
        panel.appendChild(row);
      });

      header.addEventListener('click', () => {
        const open = header.getAttribute('aria-expanded') === 'true';
        header.setAttribute('aria-expanded', String(!open));
        panel.hidden = open;
      });
      item.appendChild(header);
      item.appendChild(panel);
      accordion.appendChild(item);
    });
    results.appendChild(accordion);
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
      const plan = await PS.postJSON('/api/home-plan', collectPayload());
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

  renderRoomFields();
})();
