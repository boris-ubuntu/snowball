const DividendsComponent = {
    portfolioId: null,
    showHistory: false,

    async load(portfolioId) {
        this.portfolioId = portfolioId || this.portfolioId;
        const container = document.getElementById('dividends-list');
        container.innerHTML = '<div class="loading">Загрузка данных с MOEX...</div>';

        if (!this.portfolioId) return;

        try {
            const [dividends, coupons] = await Promise.all([
                API.getPortfolioDividends(this.portfolioId, true),
                API.getPortfolioCoupons(this.portfolioId, true),
            ]);
            this.render(dividends, coupons);
        } catch (e) {
            container.innerHTML = '<div class="loading">⚠️ Ошибка загрузки</div>';
        }
    },

    async processAccruals() {
        if (!this.portfolioId) return;
        try {
            const result = await API.processAccruals(this.portfolioId);
            alert(`✅ Обработано начислений:\n- Дивидендов: ${result.dividends}\n- Купонов: ${result.coupons}\n- Всего: ${Utils.formatCurrency(result.total_amount)}`);
            if (typeof App !== 'undefined') App.loadDashboard();
            this.load();
        } catch (e) {
            alert('Ошибка: ' + e.message);
        }
    },

    toggleHistory() {
        this.showHistory = !this.showHistory;
        this.load();
    },

    render(dividends, coupons) {
        const container = document.getElementById('dividends-list');

        let html = '';

        // Process Accruals Button
        html += `<div class="div-actions" style="display:flex;justify-content:flex-end;gap:8px;margin-bottom:12px;">
            <button class="btn-primary" onclick="DividendsComponent.processAccruals()">💰 Начислить прошедшие дивиденды/купоны</button>
        </div>`;

        // Monthly histogram chart
        const monthlyData = this.buildMonthlyData(dividends, coupons);
        html += `<div class="div-section-label">📊 Будущие выплаты по месяцам</div>`;
        html += `<div class="div-histogram">`;
        html += this.renderHistogram(monthlyData);
        html += `</div>`;

        // Upcoming Coupons list
        if (coupons && coupons.length > 0) {
            const now = new Date();
            const upcomingCoups = coupons.filter(c => new Date(c.coupon_date) >= now);
            if (upcomingCoups.length > 0) {
                html += `<div class="div-section-label">💰 Предстоящие купоны (ОФЗ/облигации)</div>`;
                html += upcomingCoups.map(coup => this.renderCouponItem(coup)).join('');
            }
        }

        // Dividends - upcoming only by default, with toggle for history
        if (dividends && dividends.length > 0) {
            const now = new Date();
            const upcoming = dividends.filter(d => new Date(d.registry_close_date) >= now);
            const past = dividends.filter(d => new Date(d.registry_close_date) < now);

            if (upcoming.length > 0) {
                html += `<div class="div-section-label">💵 Предстоящие дивиденды</div>`;
                html += upcoming.map(div => this.renderItem(div)).join('');
            }

            // History toggle
            if (past.length > 0) {
                html += `<div style="text-align:center;padding:12px;">
                    <button class="btn-secondary" onclick="DividendsComponent.toggleHistory()">
                        ${this.showHistory ? '🔼 Скрыть историю' : '📜 Показать историю (' + past.length + ')'}
                    </button>
                </div>`;
                if (this.showHistory) {
                    html += `<div class="div-section-label">📜 История дивидендов</div>`;
                    html += past.map(div => this.renderItem(div)).join('');
                }
            }
        }

        if (!html) {
            html = '<div class="loading">Нет данных</div>';
        }

        container.innerHTML = html;
    },

    buildMonthlyData(dividends, coupons) {
        const now = new Date();
        now.setHours(0, 0, 0, 0);
        const months = {};

        // Process coupons
        if (coupons) {
            for (const c of coupons) {
                const d = new Date(c.coupon_date);
                if (d < now) continue;
                const key = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
                if (!months[key]) {
                    months[key] = { date: d, total: 0, items: [] };
                }
                months[key].total += c.total_expected || 0;
                months[key].items.push(c);
            }
        }

        // Process dividends
        if (dividends) {
            for (const d of dividends) {
                const dt = new Date(d.registry_close_date);
                if (dt < now) continue;
                const key = dt.getFullYear() + '-' + String(dt.getMonth() + 1).padStart(2, '0');
                if (!months[key]) {
                    months[key] = { date: dt, total: 0, items: [] };
                }
                months[key].total += d.total_expected || 0;
                months[key].items.push(d);
            }
        }

        return Object.values(months).sort((a, b) => a.date - b.date);
    },

    renderHistogram(monthlyData) {
        if (!monthlyData || monthlyData.length === 0) {
            return '<div class="loading">Нет предстоящих выплат</div>';
        }

        const maxTotal = Math.max(...monthlyData.map(m => m.total));
        const monthNames = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

        let html = '<div class="histogram-container">';

        for (const m of monthlyData) {
            const heightPct = maxTotal > 0 ? (m.total / maxTotal * 100) : 0;
            const monthLabel = monthNames[m.date.getMonth()];
            const yearLabel = m.date.getFullYear();
            const isCurrentMonth = new Date().getMonth() === m.date.getMonth() && new Date().getFullYear() === m.date.getFullYear();

            html += `<div class="histogram-bar-wrapper">
                <div class="histogram-value">${Utils.formatCurrency(m.total)}</div>
                <div class="histogram-bar ${isCurrentMonth ? 'current' : ''}" style="height:${Math.max(heightPct, 5)}%">
                    <div class="histogram-tooltip">${m.items.map(i => `${i.ticker || i.name}: ${Utils.formatCurrency(i.total_expected || 0)}`).join('<br>')}</div>
                </div>
                <div class="histogram-label">${monthLabel}<br>${yearLabel}</div>
            </div>`;
        }

        html += '</div>';
        return html;
    },

    renderCouponItem(coup) {
        const total = coup.total_expected || 0;
        const now = new Date();
        const coupDate = new Date(coup.coupon_date);
        if (coupDate < now) return '';
        return `<div class="div-item">
            <div class="div-info">
                <span class="ticker">${coup.ticker}</span>
                <span class="div-name">${coup.name}</span>
            </div>
            <div class="div-details">
                <div class="div-detail-row">
                    <span class="detail-label">Дата купона</span>
                    <span class="detail-value">${Utils.formatDate(coup.coupon_date)}</span>
                </div>
                <div class="div-detail-row">
                    <span class="detail-label">На облигацию</span>
                    <span class="detail-value">${Utils.formatCurrency(coup.value_per_bond)}</span>
                </div>
                <div class="div-detail-row">
                    <span class="detail-label">Кол-во</span>
                    <span class="detail-value">${coup.quantity} шт</span>
                </div>
                <div class="div-detail-row">
                    <span class="detail-label">Итого</span>
                    <span class="detail-value positive">${Utils.formatCurrency(total)}</span>
                </div>
            </div>
        </div>`;
    },

    renderItem(div) {
        const closeDate = new Date(div.registry_close_date);
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        closeDate.setHours(0, 0, 0, 0);
        const daysUntil = Math.ceil((closeDate - today) / (1000 * 60 * 60 * 24));

        const isPast = daysUntil < 0;
        const urgencyLabel = isPast ? `${Math.abs(daysUntil)} дн. назад` :
            daysUntil === 0 ? '🔥 Сегодня' :
            daysUntil <= 7 ? `🔥 Через ${daysUntil} дн.` : `📅 Через ${daysUntil} дн.`;

        const totalStr = div.total_expected > 0
            ? Utils.formatCurrency(div.total_expected)
            : '—';

        return `<div class="div-item">
            <div class="div-info">
                <span class="ticker">${div.ticker}</span>
                <span class="div-name">${div.name}</span>
            </div>
            <div class="div-details">
                <div class="div-detail-row">
                    <span class="detail-label">Дата закрытия реестра</span>
                    <span class="detail-value">${Utils.formatDate(div.registry_close_date)}</span>
                </div>
                <div class="div-detail-row">
                    <span class="detail-label">На акцию</span>
                    <span class="detail-value">${Utils.formatCurrency(div.value_per_share)}</span>
                </div>
                <div class="div-detail-row">
                    <span class="detail-label">Кол-во</span>
                    <span class="detail-value">${div.quantity} шт</span>
                </div>
                <div class="div-detail-row">
                    <span class="detail-label">Итого</span>
                    <span class="detail-value positive">${totalStr}</span>
                </div>
                <div class="div-detail-row">
                    <span class="urgency-badge">${urgencyLabel}</span>
                </div>
            </div>
        </div>`;
    },
};