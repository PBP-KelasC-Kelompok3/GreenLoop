(() => {
    'use strict';

    const form = document.getElementById('wr-voucher-form');
    if (!form) return;

    const editor = document.getElementById('wr-voucher-editor');
    const idInput = document.getElementById('wr-voucher-id');
    const status = document.getElementById('wr-admin-status');
    const tableBody = document.querySelector('#wr-voucher-table tbody');
    const saveButton = document.getElementById('wr-save-voucher');
    const csrf = form.querySelector('[name="csrfmiddlewaretoken"]').value;
    const createUrl = form.action;
    const detailUrl = id => `${createUrl.replace(/create\/$/, '')}${id}/`;
    const archiveUrl = id => `${detailUrl(id)}archive/`;

    function announce(message, error = false) {
        status.textContent = message;
        status.className = `alert ${error ? 'alert-danger' : 'alert-success'}`;
        status.hidden = false;
    }

    function clearErrors() {
        form.querySelectorAll('[data-error-for]').forEach(node => { node.textContent = ''; });
    }

    function showErrors(errors = {}) {
        clearErrors();
        Object.entries(errors).forEach(([name, items]) => {
            const node = form.querySelector(`[data-error-for="${CSS.escape(name)}"]`);
            if (node) node.textContent = items.map(item => item.message).join(' ');
        });
    }

    function resetEditor() {
        form.reset();
        idInput.value = '';
        form.action = createUrl;
        document.getElementById('wr-editor-title').textContent = 'Tambah voucher';
        clearErrors();
        editor.classList.remove('d-none');
        editor.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function closeEditor() {
        editor.classList.add('d-none');
        form.reset();
        clearErrors();
        idInput.value = '';
        form.action = createUrl;
    }

    function cell(row, key) { return row.querySelector(`[data-cell="${key}"]`); }

    function updateRow(voucher) {
        const row = tableBody.querySelector(`[data-voucher-row="${voucher.id}"]`);
        if (!row) return;
        cell(row, 'title').textContent = voucher.title;
        cell(row, 'code').textContent = voucher.code;
        cell(row, 'kind').textContent = voucher.kind_display;
        cell(row, 'cost').textContent = `${number(voucher.points_cost)} poin`;
        cell(row, 'days').textContent = `${voucher.valid_days} hari`;
        cell(row, 'status').innerHTML = `<span class="badge ${voucher.is_active ? 'text-bg-success' : 'text-bg-secondary'}">${voucher.is_active ? 'Aktif' : 'Diarsipkan'}</span>`;
        if (!voucher.is_active) row.querySelector('[data-archive-voucher]')?.remove();
    }

    const number = value => new Intl.NumberFormat('id-ID').format(value);

    function appendRow(voucher) {
        document.getElementById('wr-empty-row')?.remove();
        const row = document.createElement('tr');
        row.dataset.voucherRow = voucher.id;
        const addCell = (key, value, className = '') => {
            const td = document.createElement('td');
            if (key) td.dataset.cell = key;
            td.className = className;
            td.textContent = value;
            row.append(td);
            return td;
        };
        const titleCell = addCell(null, '');
        const title = document.createElement('strong');
        title.dataset.cell = 'title';
        title.textContent = voucher.title;
        const code = document.createElement('small');
        code.className = 'd-block text-muted';
        code.dataset.cell = 'code';
        code.textContent = voucher.code;
        titleCell.append(title, code);
        addCell('kind', voucher.kind_display);
        addCell('cost', `${number(voucher.points_cost)} poin`);
        addCell('days', `${voucher.valid_days} hari`);
        addCell(null, '0');
        const state = addCell('status', 'Aktif');
        state.innerHTML = '<span class="badge text-bg-success">Aktif</span>';
        const actions = addCell(null, '');
        actions.className = 'text-nowrap';
        actions.innerHTML = `<button type="button" class="btn btn-sm btn-outline-primary" data-edit-voucher="${voucher.id}">Edit</button> <button type="button" class="btn btn-sm btn-outline-danger" data-archive-voucher="${voucher.id}">Arsipkan</button>`;
        tableBody.prepend(row);
    }

    document.getElementById('wr-new-voucher').addEventListener('click', resetEditor);
    document.getElementById('wr-close-editor').addEventListener('click', closeEditor);
    document.getElementById('wr-cancel-editor').addEventListener('click', closeEditor);

    tableBody.addEventListener('click', async event => {
        const edit = event.target.closest('[data-edit-voucher]');
        const archive = event.target.closest('[data-archive-voucher]');
        if (edit) {
            clearErrors();
            try {
                const response = await fetch(detailUrl(edit.dataset.editVoucher), { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Voucher gagal dimuat.');
                const voucher = data.voucher;
                Object.entries(voucher).forEach(([name, value]) => {
                    const input = form.elements.namedItem(name);
                    if (!input) return;
                    if (input.type === 'checkbox') input.checked = Boolean(value);
                    else input.value = value ?? '';
                });
                idInput.value = voucher.id;
                form.action = detailUrl(voucher.id);
                document.getElementById('wr-editor-title').textContent = `Edit ${voucher.title}`;
                editor.classList.remove('d-none');
                editor.scrollIntoView({ behavior: 'smooth', block: 'start' });
            } catch (error) { announce(error.message, true); }
        }
        if (archive && window.confirm('Arsipkan voucher ini? Voucher lama dan riwayat penukaran tetap tersimpan.')) {
            archive.disabled = true;
            try {
                const response = await fetch(archiveUrl(archive.dataset.archiveVoucher), {
                    method: 'POST', headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' }, credentials: 'same-origin'
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Voucher gagal diarsipkan.');
                updateRow(data.voucher);
                announce('Voucher berhasil diarsipkan. Riwayat penukaran tetap tersimpan.');
            } catch (error) { archive.disabled = false; announce(error.message, true); }
        }
    });

    form.addEventListener('submit', async event => {
        event.preventDefault();
        clearErrors();
        saveButton.disabled = true;
        saveButton.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch(form.action, {
                method: 'POST', body: new FormData(form),
                headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
                credentials: 'same-origin'
            });
            const data = await response.json();
            if (!response.ok) {
                if (data.errors) showErrors(data.errors);
                throw new Error(data.error || 'Periksa kembali data voucher.');
            }
            if (data.status === 'created') appendRow(data.voucher);
            else updateRow(data.voucher);
            announce(data.status === 'created' ? 'Voucher berhasil dibuat.' : 'Perubahan voucher berhasil disimpan.');
            closeEditor();
        } catch (error) { announce(error.message, true); }
        finally { saveButton.disabled = false; saveButton.removeAttribute('aria-busy'); }
    });
})();
