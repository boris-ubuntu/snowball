const DividendsHistogram = {
    portfolioId: null,
    lastMonthlyData: null,

    async load(portfolioId) {
        this.portfolioId = portfolioId || this.portfolioId;
        const container = document.getElementById('main-dividends-histogram');
        const totalEl = document.getElementById('main-dividends-total');

        if (!container || !this.portfolioId) return;

        // Use dashboard cached data immediately (instant display)
        const hasCache = typeof App !== 'undefined' && App.dashboardData && App.dashboardData.portfolio;
        const initialIncome = hasCache ? (App.dashboardData.portfolio.expected_annual_income || 0) : 0;
        const initialYield = hasCache ? (App.dashboardData.portfolio.expected_income_yield || 0) : 0;
        
        if (hasCache && initialIncome > 0) {
            // Show cached data immediately - build a simple histogram from dashboard data
            if (totalEl) {
                totalEl.textContent = Utils.formatCurrency(initialIncome);
            }
            // Update passive income card from dashboard data
            this.updatePassiveIncomeCard(initialIncome, null, this.portfolioId);
            container.innerHTML = this.renderSimpleHistogram(initialIncome, App.dashboardData.portfolio);
            // Don't return - try to refresh in background
        } else {
            container.innerHTML = '<div class="loading">Загрузка...</div>';
        }

        // Fetch fresh data in background (non-blocking for UI) - this populates the cache
        try {
            const [dividends, coupons, lqdtProjection] = await Promise.all([
                API.getPortfolioDividends(this.portfolioId, false, false).catch(() => []),
                API.getPortfolioCoupons(this.portfolioId, true, false).catch(() => []),
                API.getLqdtProjection(this.portfolioId).catch(() => []),
            ]);

            // Build monthly data from all sources
            const monthlyData = this.buildMonthlyData(dividends, coupons, lqdtProjection);
            this.lastMonthlyData = monthlyData;
            const totalNext12Months = monthlyData.reduce((sum, m) => sum + m.total, 0);

            // Update UI elements
            if (totalEl && totalNext12Months > 0) {
                totalEl.textContent = Utils.formatCurrency(totalNext12Months);
            }

            container.innerHTML = this.renderHistogram(monthlyData);

            // Update the passive income card - but only if we have real data
            if (totalNext12Months > 0) {
                this.updatePassiveIncomeCard(totalNext12Months, monthlyData, this.portfolioId);
            }
        } catch (e) {
            // Don't show error if we already have cached data displayed
            if (container.querySelector('.loading')) {
                container.innerHTML = '<div class="loading">⚠️ Ошибка обновления. Используются кешированные данные.</div>';
            }
            console.error('Histogram refresh error:', e);
        }
    },

    renderSimpleHistogram(total, dashboardPortfolio) {
        // Simple histogram showing just the total without breakdown by month
        return `<div class="histogram-container" style="display: flex; align-items: flex-end; justify-content: center; gap: 1px; height: 100%; min-height: 150px; padding: 4px 0; width: 100%;">
            <div style="display: flex; flex-direction: column; align-items: center; width: 60%; height: 100%; justify-content: flex-end;">
                <div class="histogram-value" style="font-size: 0.55rem; font-weight: 600; color: #4ade80; opacity: 0.8; margin-bottom: 6px; text-align: center; line-height: 1.1;">${this.formatInt(total)}</div>
                <div style="width: 100%; height: 40%; background: linear-gradient(180deg, var(--accent-light), var(--accent)); border-radius: 3px 3px 0 0; opacity: 0.5; position: relative;">
                </div>
                <div style="font-size: 0.55rem; color: var(--text-muted); text-align: center; margin-top: 3px; line-height: 1.1;">Кеш<br>данные</div>
            </div>
        </div>`;
    },

    updatePassiveIncomeCard(totalNext12Months, monthlyData, portfolioId) {
        // Update the passive income card with histogram total (same as гистограмма header)
        const expectedIncomeEl = document.getElementById('expected-income');
        const totalAccrualsEl = document.getElementById('total-accruals');
        
        // Update expected income text
        if (expectedIncomeEl) {
            expectedIncomeEl.textContent = totalNext12Months > 0
                ? Utils.formatCurrency(totalNext12Months)
                : '—';
        }

        // Calculate yield: all upcoming payments / value of assets that have payments
        // Collect tickers that have upcoming payments
        const payingTickers = new Set();
        if (monthlyData) {
            for (const m of monthlyData) {
                if (m.items) {
                    for (const item of m.items) {
                        const ticker = item.ticker || item.name;
                        if (ticker) payingTickers.add(ticker);
                    }
                }
            }
        }

        let payingValue = 0;
        if (typeof App !== 'undefined' && App.dashboardData && App.dashboardData.positions) {
            for (const pos of App.dashboardData.positions) {
                if (payingTickers.has(pos.ticker)) {
                    payingValue += pos.total_value;
                }
            }
        }

        // Calculate and update yield %
        if (totalAccrualsEl) {
            const incomeYield = payingValue > 0 ? (totalNext12Months / payingValue) * 100 : 0;
            const prefix = incomeYield >= 0 ? '▲' : '▼';
            totalAccrualsEl.textContent = prefix + ' ' + Utils.formatPercent(Math.abs(incomeYield));
            totalAccrualsEl.className = 'card-value ' + (incomeYield >= 0 ? 'positive' : 'negative');
        }
    },

    buildMonthlyData(dividends, coupons, lqdtProjection = []) {
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

        // Merge LQDT projections - add as single monthly total, not individual days
        if (lqdtProjection && lqdtProjection.length > 0) {
            for (const mp of lqdtProjection) {
                const d = new Date(mp.date);
                const key = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
                if (!months[key]) {
                    months[key] = { date: d, total: 0, items: [] };
                }
                months[key].total += mp.total || 0;
                // Add one aggregated item per month instead of individual daily items
                months[key].items.push({
                    ticker: 'LQDT',
                    name: 'LQDT Money Market',
                    total_expected: mp.total || 0,
                });
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

    // Format number as integer without currency symbol: 1234 → "1 234"
    formatInt(value) {
        if (value == null || isNaN(value)) return '';
        return Math.round(value).toLocaleString('ru-RU');
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
        const isMobile = window.innerWidth < 640;

        // Full-width: use flex:1 for each bar so they fill the entire card
        let html = '<div class="histogram-container" style="display: flex; align-items: flex-end; justify-content: space-between; gap: 1px; height: 100%; min-height: 150px; padding: 4px 0; width: 100%;">';

        for (const m of monthlyData) {
            const heightPct = maxTotal > 0 ? (m.total / maxTotal) * 100 : 0;
            const monthLabel = monthNames[m.date.getMonth()];
            const yearLabel = String(m.date.getFullYear()).slice(2);
            const isCurrentMonth = now.getMonth() === m.date.getMonth() && now.getFullYear() === m.date.getFullYear();
            const hasItems = m.items && m.items.length > 0;

            const tooltipContent = hasItems
                ? m.items.map(i => `${i.ticker || i.name}: ${Utils.formatCurrency(i.total_expected || 0)}`).join('<br>')
                : '';

            // Wider bars with rounded corners
            const barHeight = hasItems ? Math.max(heightPct, 8) : 2;
            const barBg = hasItems
                ? 'linear-gradient(180deg, var(--accent-light), var(--accent))'
                : 'var(--bg-hover)';
            const barOpacity = hasItems ? 1 : 0.1;

            // Value label with margin-bottom for spacing
            const valueLabel = hasItems
                ? `<div class="histogram-value" style="font-size: ${isMobile ? '0.5rem' : '0.55rem'}; font-weight: 600; color: #4ade80; opacity: 0.8; margin-bottom: 6px; white-space: nowrap; text-align: center; line-height: 1.1;">${this.formatInt(m.total)}</div>`
                : '';

            html += `<div class="histogram-bar-wrapper" style="display: flex; flex-direction: column; align-items: center; flex: 1; min-width: 0; height: 100%; justify-content: flex-end; position: relative;">
                ${valueLabel}
                <div class="histogram-bar ${isCurrentMonth ? 'current' : ''} ${!hasItems ? 'empty' : ''}" 
                     style="width: ${isMobile ? '70%' : '60%'}; min-height: ${hasItems ? '4px' : '1px'}; height: ${barHeight}%; background: ${barBg}; border-radius: 3px 3px 0 0; cursor: ${hasItems ? 'pointer' : 'default'}; position: relative; transition: all 0.3s ease; opacity: ${barOpacity}; box-shadow: ${hasItems ? '0 1px 3px rgba(0,0,0,0.15)' : 'none'};">
                    ${hasItems ? `<div class="histogram-tooltip" style="display: none; position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%); background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; font-size: 0.7rem; white-space: nowrap; z-index: 10; color: var(--text-primary); margin-bottom: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);">${tooltipContent}</div>` : ''}
                </div>
                <div class="histogram-label" style="font-size: ${isMobile ? '0.45rem' : '0.55rem'}; color: var(--text-muted); text-align: center; margin-top: 3px; line-height: 1.1;">${monthLabel}<br>${yearLabel}</div>
            </div>`;
        }

        html += '</div>';

        // Add hover effect via CSS (injected once)
        if (!document.getElementById('histogram-hover-style')) {
            const style = document.createElement('style');
            style.id = 'histogram-hover-style';
            style.textContent = `
                .histogram-bar:hover { opacity: 0.85 !important; transform: scaleY(1.02); transform-origin: bottom; }
                .histogram-bar-wrapper:hover .histogram-tooltip { display: block !important; }
                .histogram-bar { transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important; }
                .histogram-bar.current { border: 1px solid rgba(255,255,255,0.2); }
            `;
            document.head.appendChild(style);
        }

        return html;
    },
};