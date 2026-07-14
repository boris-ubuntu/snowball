const Utils = {
    formatDate(dateStr) {
        const d = new Date(dateStr);
        return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' });
    },

    formatCurrency(value) {
        if (value == null || isNaN(value)) return '—';
        const abs = Math.abs(value);
        const formatted = abs.toLocaleString('ru-RU', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
        return value < 0 ? `−${formatted} ₽` : `${formatted} ₽`;
    },

    formatPercent(value) {
        if (value == null || isNaN(value)) return '—';
        // ✅ Убираем знак "+" для положительных значений
        return `${value.toFixed(2)}%`;
    },

    formatNumber(value) {
        if (value == null || isNaN(value)) return '—';
        return value.toLocaleString('ru-RU', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    },

    getToday() {
        return new Date().toISOString().split('T')[0];
    },

    getTypeLabel(type) {
        const labels = {
            stock: 'Акция',
            bond: 'Облигация',
            etf: 'ETF',
            ofz: 'ОФЗ',
            currency: 'Валюта',
            other: 'Другое',
        };
        return labels[type] || type;
    },

    getTypeClass(type) {
        const classes = {
            stock: 'stock',
            bond: 'bond',
            etf: 'etf',
            ofz: 'bond',
            currency: 'currency',
            other: 'other',
        };
        return classes[type] || 'other';
    },

    currency(value) {
        return Utils.formatCurrency(value);
    },
};