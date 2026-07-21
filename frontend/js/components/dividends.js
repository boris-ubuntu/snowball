const DividendsComponent = {
    portfolioId: null,
    showHistory: false,

    async load(portfolioId, dashboardData = null) {
        this.portfolioId = portfolioId || this.portfolioId;
        const container = document.getElementById('dividends-list');
        if (!this.portfolioId) return;

        const data = dashboardData || (typeof App !== 'undefined' ? App.dashboardData : null);

        if (data && data.upcoming_payments && data.upcoming_payments.length > 0) {
            this.renderDashboard(data.upcoming_payments);
        } else if (data && data.monthly_histogram) {
            const payments = [];
            for (const bucket of data.monthly_histogram) {
                if (bucket.items) {
                    const monthDate = bucket.month + '-01';
                    for (const item of bucket.items) {
                        payments.push({
                            ticker: item.ticker || '',
                            name: item.name || '',
                            date: monthDate,
                            total_expected: item.total_expected || 0,
                            type: item.is_amortization ? 'amortization' : (item.source === 'dividend' || item.source === 'projected' ? 'dividend' : 'coupon'),
                            source: item.source || '',
                        });
                    }
                }
            }
            if (payments.length > 0) {
                this.renderDashboard(payments);
            } else {
                container.innerHTML = '<div class="loading">Нет предстоящих выплат</div>';
            }
        } else {
            container.innerHTML = '<div class="loading">Нет предстоящих выплат</div>';
        }
    },

    renderDashboard(payments) {
        const container = document.getElementById('dividends-list');
        const now = new Date();
        now.setHours(0, 0, 0, 0);

        const items = [];

        for (const p of payments) {
            const d = new Date(p.date);
            if (d < now) continue;
            items.push({
                name: p.name || p.ticker,
                ticker: p.ticker,
                date: d,
                amount: p.total_expected || 0,
                type: p.type === 'amortization' ? 'Амортизация' : (p.type === 'dividend' ? 'Дивиденд' : 'Купон'),
                projected: p.source === 'projected',
                amortization: p.type === 'amortization',
            });
        }

        items.sort((a, b) => a.date - b.date);

        if (items.length === 0) {
            container.innerHTML = '<div class="loading">Нет предстоящих выплат</div>';
            return;
        }

        let html = '';
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

        html += `<div style="overflow-x:auto;">`;
        html += `<table class="ops-table" style="width:100%;">`;
        html += `<thead><tr>
            <th>Название</th>
            <th>Дата</th>
            <th style="text-align:right;">Сумма</th>
        </tr></thead><tbody>`;

        for (const item of items) {
            const dateStr = item.date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
            const rowStyle = item.projected ? ' style="border-left: 3px solid #7c3aed; background: rgba(124,58,237,0.06);"' : '';
            const badge = item.projected
                ? ' <span style="color:#7c3aed; font-size:0.7rem; font-weight:600; border:1px solid #7c3aed; border-radius:4px; padding:1px 5px; margin-left:6px;">прогноз</span>'
                : (item.amortization
                    ? ' <span style="color:#ea580c; font-size:0.7rem; font-weight:600; border:1px solid #ea580c; border-radius:4px; padding:1px 5px; margin-left:6px;">аморт.</span>'
                    : '');
            html += `<tr${rowStyle}>
                <td>
                    <div class="pos-name">${item.name}${badge}</div>
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