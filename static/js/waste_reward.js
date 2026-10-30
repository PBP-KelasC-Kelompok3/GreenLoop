(function () {
    'use strict';

    const balanceNode = document.getElementById('reward-balance');
    if (!balanceNode) return;

    const number = value => new Intl.NumberFormat('id-ID').format(value);
    let balance = Number(balanceNode.dataset.value);

    function announce(message, isError = false) {
        let status = document.getElementById('reward-ajax-status');
        if (!status) {
            status = document.createElement('p');
            status.id = 'reward-ajax-status';
            status.className = 'reward-ajax-status';
            status.setAttribute('role', 'status');
            status.setAttribute('aria-live', 'polite');
            document.querySelector('.reward-content').prepend(status);
        }
        status.textContent = message;
        status.classList.toggle('error', isError);
        status.hidden = false;
        window.clearTimeout(status.dismissTimer);
        status.dismissTimer = window.setTimeout(() => { status.hidden = true; }, 5000);
    }

    function updateBalance(data) {
        balance = data.balance;
        balanceNode.dataset.value = String(balance);
        balanceNode.textContent = data.balance_display;
        document.getElementById('reward-level-badge').textContent = `Level ${data.level}`;
        const levelCopy = document.getElementById('reward-level-copy');
        const first = document.createElement('span');
        const second = document.createElement('span');
        first.textContent = data.is_max_level ? 'Level tertinggi' : `Menuju ${data.next_level}`;
        second.textContent = data.is_max_level
            ? 'Platinum'
            : `${data.balance_display} / ${data.next_threshold}`;
        levelCopy.replaceChildren(first, second);

        const progress = document.getElementById('reward-level-progress');
        progress.value = data.progress;
        progress.textContent = `${data.progress}%`;
        progress.setAttribute('aria-label', `Progres menuju ${data.next_level}`);
        const hint = document.getElementById('reward-level-hint');
        hint.hidden = data.is_max_level;
        hint.textContent = data.is_max_level
            ? ''
            : `${data.points_to_next} poin lagi menuju ${data.next_level}`;

        updateRedeemButtons();
    }

    function updateRedeemButtons() {
        const isBusy = Boolean(document.querySelector('[data-redeem-form][aria-busy="true"]'));
        document.querySelectorAll('[data-redeem-form]').forEach(form => {
            const button = form.querySelector('button[type="submit"]');
            button.disabled = isBusy || balance < Number(form.dataset.pointsCost);
            button.title = balance < Number(form.dataset.pointsCost) ? 'Poin belum cukup' : '';
        });
    }

    function addOwnedVoucher(voucher) {
        const list = document.getElementById('owned-voucher-list');
        list.querySelector('.owned-empty')?.remove();
        const card = document.createElement('article');
        card.className = 'owned-voucher';
        const title = document.createElement('strong');
        title.textContent = `${voucher.title} ${voucher.value_label}`;
        const codeRow = document.createElement('div');
        codeRow.className = 'voucher-code-row';
        const code = document.createElement('code');
        code.textContent = voucher.code;
        const state = document.createElement('span');
        state.textContent = 'Siap dipakai';
        codeRow.append(code, state);
        const expiry = document.createElement('small');
        expiry.textContent = `Aktif s.d. ${voucher.expires_display}`;
        card.append(title, codeRow, expiry);
        list.prepend(card);
        while (list.querySelectorAll('.owned-voucher').length > 4) list.lastElementChild.remove();

        const count = document.getElementById('available-voucher-count');
        const activeCount = Number(count.dataset.count) + 1;
        count.dataset.count = String(activeCount);
        count.textContent = `${activeCount} aktif`;
    }

    function addHistoryEntry(data) {
        const params = new URLSearchParams(window.location.search);
        if ((params.get('kind') && params.get('kind') !== 'redemption')
            || (params.get('period') && params.get('period') !== 'all'
                && params.get('period') !== '30' && params.get('period') !== '90')
            || Number(params.get('page') || '1') !== 1
            || params.has('q')) return;

        const body = document.getElementById('reward-history-rows');
        body.querySelector('.table-empty')?.closest('tr')?.remove();
        const row = document.createElement('tr');
        const date = new Intl.DateTimeFormat('id-ID', {
            day: '2-digit', month: 'short', year: 'numeric'
        }).format(new Date());
        const values = [
            date,
            data.transaction.description,
            '—',
            `−${data.transaction.points_display}`,
            data.balance_display
        ];
        values.forEach((value, index) => {
            const cell = document.createElement('td');
            cell.textContent = value;
            if (index === 3) cell.className = 'debit';
            row.append(cell);
        });
        body.prepend(row);
        while (body.rows.length > 10) body.deleteRow(-1);
    }

    document.querySelectorAll('[data-redeem-form]').forEach(form => {
        form.addEventListener('submit', async event => {
            event.preventDefault();
            const button = form.querySelector('button[type="submit"]');
            const cost = Number(form.dataset.pointsCost);
            if (button.disabled || balance < cost) return;

            const previousBalance = balance;
            balance -= cost;
            balanceNode.dataset.value = String(balance);
            balanceNode.textContent = number(balance);
            button.textContent = 'Memproses…';
            form.setAttribute('aria-busy', 'true');
            updateRedeemButtons();

            try {
                const response = await fetch(form.action, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': form.querySelector('[name="csrfmiddlewaretoken"]').value,
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json'
                    },
                    body: new FormData(form),
                    credentials: 'same-origin'
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Penukaran voucher gagal.');

                updateBalance(data);
                addOwnedVoucher(data.voucher);
                addHistoryEntry(data);
                announce(`Voucher ${data.voucher.code} berhasil ditukar.`);
            } catch (error) {
                balance = previousBalance;
                balanceNode.dataset.value = String(balance);
                balanceNode.textContent = number(balance);
                announce(error.message, true);
            } finally {
                button.textContent = 'Tukar';
                form.removeAttribute('aria-busy');
                updateRedeemButtons();
            }
        });
    });

    document.querySelectorAll('.reward-history-filters select').forEach(select => {
        select.addEventListener('change', () => select.form.requestSubmit());
    });
})();
