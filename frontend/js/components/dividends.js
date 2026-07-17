const DividendsComponent = {
    portfolioId: null,
    showHistory: false,

    async load(portfolioId) {
        this.portfolioId = portfolioId || this.portfolioId;
        const container = document.getElementById('dividends-list');
        container.innerHTML = '<div class="loading">Загрузка данных...</div>';

        if (!this.portfolioId) return;

        try {
            const [dividends, coupons] = await Promise.all([
                API.getPortfolioDividends(this.portfolioId, true, false),
                API.getPortfolioCoupons(this.portfolioId, true, false),
            ]);
            
            if ((!dividends || dividends.length === 0) && (!coupons || coupons.length === 0)) {
                container.innerHTML = '<div class="loading">Загрузка данных с MOEX...</div>';
                const [dividendsFresh, couponsFresh] = await Promise.all([
                    API.getPortfolioDividends(this.portfolioId, true, true),
                    API.getPortfolioCoupons(this.portfolioId, true, true),
                ]);
                this.render(dividendsFresh, couponsFresh);
            } else {
                this.render(dividends, coupons);
            }
        } catch (e) {
            container.innerHTML = '<div class="loading">⚠️ Ошибка загрузки</div>';
            console.error(e);
        }
    },

    render(dividends, coupons) {
        const container = document.getElementById('dividends-list');

        // Merge all upcoming payments into one list
        const now = new Date();
        now.setHours(0, 0, 0, 0);

        const items = [];

        if (coupons) {
            for (const c of coupons) {
                const d = new Date(c.coupon_date);
                if (d < now) continue;
                items.push({
                    name: c.name || c.ticker,
                    ticker: c.ticker,
                    date: new Date(c.coupon_date),
                    amount: c.total_expected || 0,
                    type: 'Купон',
                });
            }
        }

        if (dividends) {
            for (const d of dividends) {
                const dt = new Date(d.registry_close_date);
                if (dt < now) continue;
                items.push({
                    name: d.name || d.ticker,
                    ticker: d.ticker,
                    date: new Date(d.registry_close_date),
                    amount: d.total_expected || 0,
                    type: 'Дивиденд',
                });
            }
        }

        // Sort by date ascending
        items.sort((a, b) => a.date - b.date);

        if (items.length === 0) {
            container.innerHTML = '<div class="loading">Нет предстоящих выплат</div>';
            return;
        }

        let html = '';

        // Summary stats
        const totalAmount = items.reduce((s, i) => s + i.amount, 0);
        html += `<div class="stats-cards" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 20px;">`;
        html += `<div class="summary-card" style="background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px;">
            <div class="card-label" style="font-size: 0.7rem; color: var(--text-secondary); text-transform: uppercase;">💰 Всего ожидается</div>
            <div class="card-value" style="font-size: 1.3rem; font-weight: 700; color: var(--green);">${Utils.formatCurrency(totalAmount)}</div>
        </div>`;
        html += `<div class="summary-card" style="background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px;">
            <div class="card-label" style="font-size: 0.7rem; color: var(--text-secondary); text-transform: uppercase;">📅 Всего выплат</div>
            <div class="card-value" style="font-size: 1.3rem; font-weight: 700; color: var(--text-primary);">${items.length}</div>
        </div>`;
        html += `</div>`;

        // Payment list as simple table
        html += `<div style="overflow-x:auto;">`;
        html += `<table class="ops-table" style="width:100%;">`;
        html += `<thead><tr>
            <th>Название</th>
            <th>Дата</th>
            <th style="text-align:right;">Сумма</th>
        </tr></thead><tbody>`;

        for (const item of items) {
            const dateStr = item.date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
            html += `<tr>
                <td>
                    <div class="pos-name">${item.name}</div>
                    <div class="pos-ticker">${item.ticker}</div>
                </td>
                <td class="tx-date">${dateStr}</td>
                <td class="tx-amount positive" style="text-align:right;">${Utils.formatCurrency(item.amount)}</td>
            </tr>`;
        }

        html += `</tbody></table>`;
        html += `</div>`;

        container.innerHTML = html;
    },
};