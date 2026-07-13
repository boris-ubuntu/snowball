const TransactionsComponent = {
    portfolioId: null,
    currentPage: 0,
    pageSize: 10,
    totalLoaded: 0,

    async load(portfolioId, page = 0) {
        this.portfolioId = portfolioId || this.portfolioId;
        this.currentPage = page;
        const container = document.getElementById('operations-list');
        container.innerHTML = '<div class="loading">Загрузка...</div>';

        if (!this.portfolioId) return;

        try {
            const skip = this.currentPage * this.pageSize;
            const limit = this.pageSize + 1; // Load one extra to check if more pages exist
            const transactions = await API.getTransactions(this.portfolioId, skip, limit);
            this.totalLoaded = transactions.length;
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

        container.innerHTML = items.map(tx => {
            const ticker = tx.security ? tx.security.ticker : '?';
            let typeLabel, typeIcon;
            if (tx.transaction_type === 'buy') { typeLabel = 'Покупка'; typeIcon = '🟢'; }
            else if (tx.transaction_type === 'sell') { typeLabel = 'Продажа'; typeIcon = '🔴'; }
            else if (tx.transaction_type === 'accrual') { typeLabel = 'Начисление'; typeIcon = '💰'; }
            else { typeLabel = tx.transaction_type; typeIcon = '❓'; }

            let detailStr;
            if (tx.transaction_type === 'accrual') {
                detailStr = Utils.formatCurrency(tx.total_amount);
            } else {
                detailStr = `${tx.quantity} шт × ${Utils.formatNumber(tx.price)}`;
            }

            const amountStr = Utils.formatCurrency(tx.total_amount);

            return `<div class="tx-item">
                <div class="tx-info">
                    <span class="tx-ticker">${ticker}</span>
                    <span class="tx-type ${tx.transaction_type}">${typeIcon} ${typeLabel}</span>
                    <span class="tx-date">${Utils.formatDate(tx.transaction_date)}</span>
                    <span>${detailStr}</span>
                </div>
                <div class="tx-amount ${tx.transaction_type === 'accrual' ? 'positive' : ''}">${amountStr}</div>
            </div>`;
        }).join('');

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
};