const DividendsComponent = {
    portfolioId: null,

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

    render(dividends, coupons) {
        const container = document.getElementById('dividends-list');

        let html = '';

        // Process Accruals Button
        html += `<div class="div-actions" style="display:flex;justify-content:flex-end;gap:8px;margin-bottom:12px;">
            <button class="btn-primary" onclick="DividendsComponent.processAccruals()">💰 Начислить прошедшие дивиденды/купоны</button>
        </div>`;

        // Upcoming Coupons section
        if (coupons && coupons.length > 0) {
            html += `<div class="div-section-label">💰 Предстоящие купоны (ОФЗ/облигации)</div>`;
            html += coupons.map(coup => this.renderCouponItem(coup)).join('');
        }

        // Dividends history
        if (dividends && dividends.length > 0) {
            html += `<div class="div-section-label">📜 История дивидендов</div>`;
            html += dividends.map(div => this.renderItem(div)).join('');
        }

        if (!html) {
            html = '<div class="loading">Нет данных</div>';
        }

        container.innerHTML = html;
    },

    renderCouponItem(coup) {
        const total = coup.total_expected || 0;
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