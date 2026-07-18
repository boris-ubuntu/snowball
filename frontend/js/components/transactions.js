const TransactionsComponent = {
    portfolioId: null,
    currentPage: 0,
    pageSize: 10,
    totalLoaded: 0,

    async load(portfolioId, page = 0, force = false) {
        this.portfolioId = portfolioId || this.portfolioId;
        this.currentPage = page;
        const container = document.getElementById('operations-list');

        if (!this.portfolioId) return;

        // Кеш: при возврате на страницу не перезапрашиваем, если уже загружено (стр. 0)
        if (!force && page === 0 && this._loadedFor === this.portfolioId && this._lastTransactions) {
            this.render(this._lastTransactions);
            return;
        }

        container.innerHTML = '<div class="loading">Загрузка...</div>';

        try {
            const skip = this.currentPage * this.pageSize;
            const limit = this.pageSize + 1; // Load one extra to check if more pages exist
            const transactions = await API.getTransactions(this.portfolioId, skip, limit);
            this.totalLoaded = transactions.length;
            if (page === 0) {
                this._lastTransactions = transactions;
                this._loadedFor = this.portfolioId;
            }
            this.render(transactions);
        } catch (e) {
            container.innerHTML = '<div class="loading">⚠️ Ошибка загрузки</div>';
        }
    },

    render(transactions) {
        const container = document.getElementById('operations-list');
        const hasMore = transactions.length > this.pageSize;
        const items = hasMore ? transactions.slice(0, this.pageSize) : transactions;

        if (!items || items.length === 0) {
            container.innerHTML = '<div class="loading">Нет операций</div>';
            document.getElementById('operations-pagination').innerHTML = '';
            return;
        }

        container.innerHTML = `<table class="ops-table" style="cursor:pointer;">
            <thead>
                <tr>
                    <th>Название</th>
                    <th>Тип</th>
                    <th>Дата</th>
                    <th>Кол-во × Цена</th>
                    <th>Сумма</th>
                </tr>
            </thead>
            <tbody>
                ${items.map(tx => {
                    const ticker = tx.security ? tx.security.ticker : '?';
                    const name = tx.security ? tx.security.name : '—';
                    const isin = tx.security && tx.security.isin ? tx.security.isin : '';
                    let typeLabel;
                    if (tx.transaction_type === 'buy') { typeLabel = 'Покупка'; }
                    else if (tx.transaction_type === 'sell') { typeLabel = 'Продажа'; }
                    else if (tx.transaction_type === 'accrual') { typeLabel = 'Начисление'; }
                    else { typeLabel = tx.transaction_type; }

                    let detailStr;
                    if (tx.transaction_type === 'accrual') {
                        detailStr = '—';
                    } else {
                        detailStr = `${tx.quantity} × ${Utils.formatNumber(tx.price)}`;
                    }

                    const amountStr = Utils.formatCurrency(tx.total_amount);
                    const amountClass = tx.transaction_type === 'accrual' ? 'positive' : 
                                        tx.transaction_type === 'sell' ? 'negative' : '';

                    return `<tr class="tx-row" data-id="${tx.id}" data-ticker="${ticker}" data-name="${name}" data-type="${tx.transaction_type}" data-qty="${tx.quantity}" data-price="${tx.price}" data-commission="${tx.commission || 0}" data-date="${tx.transaction_date}" data-notes="${tx.notes || ''}">
                        <td>
                            <div class="tx-name">${name}</div>
                            <div class="tx-sub">${ticker}${isin ? ' · ' + isin : ''}</div>
                        </td>
                        <td><span class="tx-type ${tx.transaction_type}">${typeLabel}</span></td>
                        <td class="tx-date">${Utils.formatDate(tx.transaction_date)}</td>
                        <td class="tx-detail">${detailStr}</td>
                        <td class="tx-amount ${amountClass}">${amountStr}</td>
                    </tr>`;
                }).join('')}
            </tbody>
        </table>`;

        // Add click handlers for editing transactions
        document.querySelectorAll('.tx-row').forEach(row => {
            row.addEventListener('click', () => {
                const id = row.dataset.id;
                const ticker = row.dataset.ticker;
                const name = row.dataset.name;
                const type = row.dataset.type;
                const qty = row.dataset.qty;
                const price = row.dataset.price;
                const commission = row.dataset.commission;
                const date = row.dataset.date;
                const notes = row.dataset.notes;
                this.showEditModal(id, ticker, name, type, qty, price, commission, date, notes);
            });
        });

        // Pagination
        const paginationEl = document.getElementById('operations-pagination');
        if (this.currentPage > 0 || hasMore) {
            paginationEl.innerHTML = `
                <button id="ops-prev" class="icon-btn" ${this.currentPage === 0 ? 'disabled' : ''}>◀ Назад</button>
                <span class="page-info">Страница ${this.currentPage + 1}</span>
                <button id="ops-next" class="icon-btn" ${!hasMore ? 'disabled' : ''}>Вперёд ▶</button>
            `;

            document.getElementById('ops-prev').addEventListener('click', () => {
                if (this.currentPage > 0) this.load(null, this.currentPage - 1);
            });
            document.getElementById('ops-next').addEventListener('click', () => {
                if (hasMore) this.load(null, this.currentPage + 1);
            });
        } else {
            paginationEl.innerHTML = '';
        }
    },

    showEditModal(id, ticker, name, type, qty, price, commission, date, notes) {
        // Create modal overlay
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.id = 'edit-tx-modal-overlay';
        overlay.style.cssText = 'display:flex;align-items:center;justify-content:center;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:1000;';

        const typeLabel = type === 'buy' ? 'Покупка' : type === 'sell' ? 'Продажа' : 'Начисление';
        const isAccrual = type === 'accrual';

        overlay.innerHTML = `<div class="modal" style="max-width:420px;width:90%;">
            <div class="modal-header">
                <h2>✏️ ${name} (${ticker})</h2>
                <button class="close-edit-tx icon-btn">✕</button>
            </div>
            <form id="edit-tx-form" autocomplete="off">
                <input type="hidden" id="edit-tx-id" value="${id}">
                <div class="form-group" style="margin-bottom:8px;">
                    <label>Тип сделки: <strong>${typeLabel}</strong></label>
                </div>
                ${isAccrual ? '' : `
                <div class="form-row">
                    <div class="form-group">
                        <label for="edit-tx-qty">Количество</label>
                        <input type="number" id="edit-tx-qty" step="1" min="1" value="${qty}" required>
                    </div>
                    <div class="form-group">
                        <label for="edit-tx-price">Цена за шт (₽)</label>
                        <input type="number" id="edit-tx-price" step="0.01" min="0.01" value="${price}" required>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label for="edit-tx-commission">Комиссия (₽)</label>
                        <input type="number" id="edit-tx-commission" step="0.01" min="0" value="${commission}">
                    </div>
                    <div class="form-group">
                        <label for="edit-tx-date">Дата</label>
                        <input type="date" id="edit-tx-date" value="${date}" required>
                    </div>
                </div>
                `}
                <div class="form-group">
                    <label for="edit-tx-notes">Заметки</label>
                    <input type="text" id="edit-tx-notes" placeholder="Опционально" maxlength="200" value="${notes}">
                </div>
                <div style="display:flex;gap:8px;margin-top:12px;">
                    <button type="submit" class="btn-primary" style="flex:1;">💾 Сохранить</button>
                    <button type="button" id="edit-tx-delete" class="btn-danger" style="flex:1;background:var(--negative);color:white;border:none;border-radius:6px;padding:8px;cursor:pointer;">🗑 Удалить</button>
                </div>
                <button type="button" class="close-edit-tx btn-secondary" style="width:100%;margin-top:8px;">Отмена</button>
            </form>
        </div>`;

        document.body.appendChild(overlay);

        // Close handlers
        overlay.querySelectorAll('.close-edit-tx').forEach(el => {
            el.addEventListener('click', () => overlay.remove());
        });
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.remove();
        });

        // Save handler
        document.getElementById('edit-tx-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const txId = document.getElementById('edit-tx-id').value;
            const data = {};
            if (!isAccrual) {
                data.quantity = parseFloat(document.getElementById('edit-tx-qty').value);
                data.price = parseFloat(document.getElementById('edit-tx-price').value);
                data.commission = parseFloat(document.getElementById('edit-tx-commission').value || 0);
                data.transaction_date = document.getElementById('edit-tx-date').value;
            }
            data.notes = document.getElementById('edit-tx-notes').value || '';
            try {
                await API.updateTransaction(this.portfolioId, txId, data);
                overlay.remove();
                // Reload the page and refresh dashboard with recalculated positions
                this.load(null, this.currentPage, true);
                // Clear dashboard cache and refresh
                if (typeof App !== 'undefined') {
                    App.dashboardData = null;
                    await App.loadDashboard(true);
                    await DividendsHistogram.load(App.portfolioId);
                    if (App.dashboardData) {
                        ChartComponent.render(App.dashboardData, document.getElementById('chart-mode-toggle')?.checked || false);
                        SummaryComponent.render(App.dashboardData);
                    }
                }
            } catch (err) {
                alert('Ошибка сохранения: ' + err.message);
            }
        });

        // Delete handler
        document.getElementById('edit-tx-delete').addEventListener('click', async () => {
            const txId = document.getElementById('edit-tx-id').value;
            // Show confirmation
            const confirmOverlay = document.getElementById('confirm-overlay');
            if (confirmOverlay) {
                confirmOverlay.classList.remove('hidden');
                const confirmYes = document.getElementById('confirm-yes');
                const confirmNo = document.getElementById('confirm-no');
                const newConfirmYes = confirmYes.cloneNode(true);
                confirmYes.parentNode.replaceChild(newConfirmYes, confirmYes);
                const newConfirmNo = confirmNo.cloneNode(true);
                confirmNo.parentNode.replaceChild(newConfirmNo, confirmNo);
                newConfirmNo.addEventListener('click', () => {
                    confirmOverlay.classList.add('hidden');
                });
                newConfirmYes.addEventListener('click', async () => {
                    confirmOverlay.classList.add('hidden');
                    try {
                        await API.deleteTransaction(this.portfolioId, txId);
                        overlay.remove();
                        this.load(null, this.currentPage, true);
                        // Clear dashboard cache and refresh
                        if (typeof App !== 'undefined') {
                            App.dashboardData = null;
                            await App.loadDashboard(true);
                            await DividendsHistogram.load(App.portfolioId);
                            if (App.dashboardData) {
                                ChartComponent.render(App.dashboardData, document.getElementById('chart-mode-toggle')?.checked || false);
                                SummaryComponent.render(App.dashboardData);
                            }
                        }
                    } catch (err) {
                        alert('Ошибка удаления: ' + err.message);
                    }
                });
            }
        });
    },
};
