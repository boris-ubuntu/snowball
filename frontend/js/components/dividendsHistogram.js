const DividendsHistogram = {
    portfolioId: null,
    lastMonthlyData: null,

    async load(portfolioId, force = false) {
        this.portfolioId = portfolioId || this.portfolioId;
        const container = document.getElementById('main-dividends-histogram');
        const totalEl = document.getElementById('main-dividends-total');

        if (!container || !this.portfolioId) return;

        // Get data from dashboard (already loaded, no extra API calls)
        const dashboard = (typeof App !== 'undefined' && App.dashboardData)
            ? App.dashboardData : null;

        if (dashboard && dashboard.monthly_histogram && dashboard.monthly_histogram.length > 0) {
            // Use histogram data from backend
            this.lastMonthlyData = dashboard.monthly_histogram;
            this._loadedFor = this.portfolioId;

            const total = dashboard.portfolio.expected_annual_income || 0;
            if (totalEl && total > 0) {
                totalEl.textContent = Utils.formatCurrency(total);
            }
            container.innerHTML = this.renderHistogram(dashboard.monthly_histogram);
            this.updatePassiveIncomeCard(total, null, this.portfolioId);
        } else if (dashboard && dashboard.portfolio && dashboard.portfolio.expected_annual_income > 0) {
            // Show simple placeholder with total
            const total = dashboard.portfolio.expected_annual_income || 0;
            if (totalEl && total > 0) {
                totalEl.textContent = Utils.formatCurrency(total);
            }
            container.innerHTML = this.renderSimpleHistogram(total, dashboard.portfolio);
            this.updatePassiveIncomeCard(total, null, this.portfolioId);
        } else {
            container.innerHTML = '<div class="loading">Нет данных о выплатах</div>';
            this.updatePassiveIncomeCard(0, null, this.portfolioId);
        }
    },

    renderSimpleHistogram(total, dashboardPortfolio) {
        // Show 13 empty bars with correct labels (cached data placeholder)
        const now = new Date();
        now.setHours(0, 0, 0, 0);
        const buckets = this._buildBuckets(now);
        return this.renderHistogram(buckets, true);
    },

    updatePassiveIncomeCard(totalNext12Months, monthlyData, portfolioId) {
        const expectedIncomeEl = document.getElementById('expected-income');
        const totalAccrualsEl = document.getElementById('total-accruals');

        // Update expected income text from backend
        if (expectedIncomeEl) {
            expectedIncomeEl.textContent = totalNext12Months > 0
                ? Utils.formatCurrency(totalNext12Months)
                : '—';
        }

        // Use dashboard yield (from backend, authoritative)
        const dashboard = (typeof App !== 'undefined' && App.dashboardData && App.dashboardData.portfolio)
            ? App.dashboardData.portfolio : null;
        if (dashboard && totalAccrualsEl) {
            const yieldVal = dashboard.expected_income_yield || 0;
            const prefix = yieldVal >= 0 ? '▲' : '▼';
            totalAccrualsEl.textContent = prefix + ' ' + Utils.formatPercent(Math.abs(yieldVal));
            totalAccrualsEl.className = 'card-value ' + (yieldVal >= 0 ? 'positive' : 'negative');
        }
    },

    // Build 13 buckets: today→endOfMonth, 11 full months, 1st→today-1
    _buildBuckets(now) {
        const buckets = [];

        // Bucket 0: today → end of current month
        const endOfCurrentMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0);
        endOfCurrentMonth.setHours(23, 59, 59, 999);
        buckets.push({
            start: new Date(now),
            end: new Date(endOfCurrentMonth),
            date: new Date(now),
            dayRange: now.getDate() + '-' + endOfCurrentMonth.getDate(),
            total: 0,
            items: []
        });

        // Buckets 1-11: full calendar months
        for (let i = 1; i <= 11; i++) {
            const monthStart = new Date(now.getFullYear(), now.getMonth() + i, 1);
            monthStart.setHours(0, 0, 0, 0);
            const monthEnd = new Date(now.getFullYear(), now.getMonth() + i + 1, 0);
            monthEnd.setHours(23, 59, 59, 999);
            buckets.push({
                start: monthStart,
                end: monthEnd,
                date: new Date(monthStart),
                dayRange: null,
                total: 0,
                items: []
            });
        }

        // Bucket 12: 1st of month (now+12) → today - 1 day of next year
        const startOfNextYearMonth = new Date(now.getFullYear(), now.getMonth() + 12, 1);
        startOfNextYearMonth.setHours(0, 0, 0, 0);
        const dayBeforeTodayNextYear = new Date(now);
        dayBeforeTodayNextYear.setFullYear(dayBeforeTodayNextYear.getFullYear() + 1);
        dayBeforeTodayNextYear.setDate(dayBeforeTodayNextYear.getDate() - 1);
        dayBeforeTodayNextYear.setHours(23, 59, 59, 999);

        if (startOfNextYearMonth <= dayBeforeTodayNextYear) {
            buckets.push({
                start: startOfNextYearMonth,
                end: dayBeforeTodayNextYear,
                date: new Date(startOfNextYearMonth),
                dayRange: '1-' + dayBeforeTodayNextYear.getDate(),
                total: 0,
                items: []
            });
        }

        return buckets;
    },

    // Format number as integer without currency symbol: 1234 → "1 234"
    formatInt(value) {
        if (value == null || isNaN(value)) return '';
        return Math.round(value).toLocaleString('ru-RU');
    },

    renderHistogram(monthlyData, allowEmpty = false) {
        if (!monthlyData || monthlyData.length === 0) {
            return '<div class="loading">Нет предстоящих выплат</div>';
        }

        const maxTotal = Math.max(...monthlyData.map(m => m.total), 0);

        if (maxTotal === 0 && !allowEmpty) {
            return '<div class="loading">Нет предстоящих выплат в следующие 12 месяцев</div>';
        }

        const monthNames = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];
        const now = new Date();
        const isMobile = window.innerWidth < 640;

        let html = '<div class="histogram-container" style="display: flex; align-items: flex-end; justify-content: space-between; gap: 1px; height: 100%; min-height: 150px; padding: 4px 0; width: 100%;">';

        for (const m of monthlyData) {
            const heightPct = maxTotal > 0 ? (m.total / maxTotal) * 100 : 0;
            const monthDate = m.month ? new Date(m.month + '-01') : m.date;
            const monthLabel = monthNames[monthDate.getMonth()];
            const yearLabel = String(monthDate.getFullYear()).slice(2);
            const isCurrentMonth = now.getMonth() === monthDate.getMonth() && now.getFullYear() === monthDate.getFullYear();
            const hasItems = m.items && m.items.length > 0;
            const hasProjected = hasItems && m.items.some(i => i.source === 'projected');
            const hasAmortization = hasItems && m.items.some(i => i.is_amortization === true);

            // Build label
            let labelHtml;
            if (m.dayRange) {
                labelHtml = m.dayRange + '<br>' + monthLabel;
            } else {
                labelHtml = monthLabel + '<br>' + yearLabel;
            }

            // Group tooltip items by ticker/name, summing amounts
            const tooltipContent = hasItems
                ? (() => {
                    const grouped = {};
                    for (const i of m.items) {
                        const key = i.ticker || i.name || 'unknown';
                        if (!grouped[key]) {
                            grouped[key] = { ticker: key, total: 0, isProjected: false, isAmort: false };
                        }
                        grouped[key].total += i.total_expected || 0;
                        if (i.source === 'projected') grouped[key].isProjected = true;
                        if (i.is_amortization === true) grouped[key].isAmort = true;
                    }
                    return Object.values(grouped).map(g => {
                        const label = `${g.ticker}: ${Utils.formatCurrency(g.total)}`;
                        if (g.isProjected) return `${label} <span style="color:#a78bfa;">(прогноз)</span>`;
                        if (g.isAmort) return `${label} <span style="color:#fb923c;">(аморт.)</span>`;
                        return label;
                    }).join('<br>');
                })()
                : '';

            // Calculate amortization portion for orange stripe on top
            const amortTotal = hasAmortization
                ? m.items.filter(i => i.is_amortization === true).reduce((s, i) => s + (i.total_expected || 0), 0)
                : 0;
            const nonAmortTotal = m.total - amortTotal;
            const nonAmortHeightPct = maxTotal > 0 ? (nonAmortTotal / maxTotal) * 100 : 0;
            const amortHeightPct = maxTotal > 0 ? (amortTotal / maxTotal) * 100 : 0;

            const barHeight = hasItems ? Math.max(heightPct, 8) : 2;
            const barBg = !hasItems
                ? 'var(--bg-hover)'
                : hasProjected
                    ? 'linear-gradient(180deg, #c4b5fd, #7c3aed)'
                    : 'linear-gradient(180deg, var(--accent-light), var(--accent))';
            const barOpacity = hasItems ? 1 : 0.1;

            const valueLabel = hasItems
                ? `<div class="histogram-value" style="font-size: ${isMobile ? '0.5rem' : '0.55rem'}; font-weight: 600; color: #4ade80; opacity: 0.8; margin-bottom: 6px; white-space: nowrap; text-align: center; line-height: 1.1;">${this.formatInt(m.total)}</div>`
                : '';

            let barInnerHtml = '';
            if (hasItems) {
                barInnerHtml += `<div class="histogram-tooltip" style="display: none; position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%); background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; font-size: 0.7rem; white-space: nowrap; z-index: 10; color: var(--text-primary); margin-bottom: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);">${tooltipContent}</div>`;
            }

            html += `<div class="histogram-bar-wrapper" style="display: flex; flex-direction: column; align-items: center; flex: 1; min-width: 0; height: 100%; justify-content: flex-end; position: relative;">
                ${valueLabel}
                <div class="histogram-bar ${isCurrentMonth ? 'current' : ''} ${!hasItems ? 'empty' : ''}" 
                     style="width: ${isMobile ? '70%' : '60%'}; min-height: ${hasItems ? '4px' : '1px'}; height: ${barHeight}%; background: ${barBg}; border-radius: 3px 3px 0 0; cursor: ${hasItems ? 'pointer' : 'default'}; position: relative; transition: all 0.3s ease; opacity: ${barOpacity}; box-shadow: ${hasItems ? '0 1px 3px rgba(0,0,0,0.15)' : 'none'}; overflow: visible;">
                    ${barInnerHtml}
                    ${hasAmortization ? `<div style="position: absolute; bottom: ${nonAmortHeightPct > 0 ? (nonAmortHeightPct / heightPct * 100) : 0}%; left: 0; right: 0; height: ${amortHeightPct > 0 ? (amortHeightPct / heightPct * 100) : 4}%; background: #ea580c; border-radius: 3px 3px 0 0; z-index: 2;"></div>` : ''}
                </div>
                <div class="histogram-label" style="font-size: ${isMobile ? '0.45rem' : '0.55rem'}; color: var(--text-muted); text-align: center; margin-top: 3px; line-height: 1.1;">${labelHtml}</div>
            </div>`;
        }

        html += '</div>';

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