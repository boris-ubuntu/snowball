const DividendsHistogram = {
    portfolioId: null,

    async load(portfolioId) {
        this.portfolioId = portfolioId || this.portfolioId;
        const container = document.getElementById('main-dividends-histogram');
        const totalEl = document.getElementById('main-dividends-total');

        if (!container || !this.portfolioId) return;

        container.innerHTML = '<div class="loading">Загрузка...</div>';

        try {
            const [dividends, coupons] = await Promise.all([
                API.getPortfolioDividends(this.portfolioId, true, false),
                API.getPortfolioCoupons(this.portfolioId, true, false),
            ]);

            const monthlyData = this.buildMonthlyData(dividends, coupons);
            const totalNext12Months = monthlyData.reduce((sum, m) => sum + m.total, 0);

            if (totalEl) {
                totalEl.textContent = Utils.formatCurrency(totalNext12Months);
            }

            container.innerHTML = this.renderHistogram(monthlyData);
        } catch (e) {
            container.innerHTML = '<div class="loading">⚠️ Ошибка загрузки</div>';
            console.error(e);
        }
    },

    buildMonthlyData(dividends, coupons) {
        const now = new Date();
        now.setHours(0, 0, 0, 0);

        const oneYearFromNow = new Date(now);
        oneYearFromNow.setFullYear(oneYearFromNow.getFullYear() + 1);

        const months = {};

        if (coupons) {
            for (const c of coupons) {
                const d = new Date(c.coupon_date);
                if (d < now || d > oneYearFromNow) continue;
                const key = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
                if (!months[key]) {
                    months[key] = { date: d, total: 0, items: [] };
                }
                months[key].total += c.total_expected || 0;
                months[key].items.push(c);
            }
        }

        if (dividends) {
            for (const d of dividends) {
                const dt = new Date(d.registry_close_date);
                if (dt < now || dt > oneYearFromNow) continue;
                const key = dt.getFullYear() + '-' + String(dt.getMonth() + 1).padStart(2, '0');
                if (!months[key]) {
                    months[key] = { date: dt, total: 0, items: [] };
                }
                months[key].total += d.total_expected || 0;
                months[key].items.push(d);
            }
        }

        const result = [];
        const currentDate = new Date(now);

        for (let i = 0; i < 12; i++) {
            const year = currentDate.getFullYear();
            const month = currentDate.getMonth();
            const key = year + '-' + String(month + 1).padStart(2, '0');

            if (months[key]) {
                result.push(months[key]);
            } else {
                result.push({
                    date: new Date(year, month, 1),
                    total: 0,
                    items: []
                });
            }
            currentDate.setMonth(currentDate.getMonth() + 1);
        }

        return result;
    },

    renderHistogram(monthlyData) {
        if (!monthlyData || monthlyData.length === 0) {
            return '<div class="loading">Нет предстоящих выплат</div>';
        }

        const maxTotal = Math.max(...monthlyData.map(m => m.total), 0);

        if (maxTotal === 0) {
            return '<div class="loading">Нет предстоящих выплат в следующие 12 месяцев</div>';
        }

        const monthNames = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];
        const now = new Date();

        let html = '<div class="histogram-container" style="display: flex; align-items: flex-end; justify-content: space-around; gap: 8px; height: 100%; min-height: 220px; padding: 10px 0;">';

        for (const m of monthlyData) {
            const heightPct = maxTotal > 0 ? (m.total / maxTotal) * 100 : 0;
            const monthLabel = monthNames[m.date.getMonth()];
            const yearLabel = m.date.getFullYear();
            const isCurrentMonth = now.getMonth() === m.date.getMonth() && now.getFullYear() === m.date.getFullYear();

            const hasItems = m.items && m.items.length > 0;
            const tooltipContent = hasItems
                ? m.items.map(i => `${i.ticker || i.name}: ${Utils.formatCurrency(i.total_expected || 0)}`).join('<br>')
                : 'Нет выплат';

            const barHeight = Math.max(heightPct, m.total > 0 ? 10 : 2);

            html += `<div class="histogram-bar-wrapper" style="display: flex; flex-direction: column; align-items: center; flex: 1; min-width: 35px; height: 100%; justify-content: flex-end; position: relative;">
                <div class="histogram-value" style="font-size: 0.65rem; font-weight: 700; color: var(--green); margin-bottom: 3px; white-space: nowrap; text-align: center;">${m.total > 0 ? Utils.formatCurrency(m.total) : '0'}</div>
                <div class="histogram-bar ${isCurrentMonth ? 'current' : ''} ${!hasItems ? 'empty' : ''}" 
                     style="width: 100%; max-width: 40px; min-height: ${m.total > 0 ? '6px' : '3px'}; height: ${barHeight}%; background: ${hasItems ? 'linear-gradient(180deg, var(--accent-light), var(--accent))' : 'var(--bg-hover)'}; border-radius: 4px 4px 0 0; cursor: default; position: relative; transition: all 0.3s ease; opacity: ${hasItems ? 1 : 0.25};">
                    ${hasItems ? `<div class="histogram-tooltip" style="display: none; position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%); background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; font-size: 0.7rem; white-space: nowrap; z-index: 10; color: var(--text-primary); margin-bottom: 4px;">${tooltipContent}</div>` : ''}
                </div>
                <div class="histogram-label" style="font-size: 0.6rem; color: var(--text-muted); text-align: center; margin-top: 4px; line-height: 1.2;">${monthLabel}<br>${yearLabel}</div>
            </div>`;
        }

        html += '</div>';
        return html;
    },
};