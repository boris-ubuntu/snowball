const SummaryComponent = {
    render(data) {
        const summary = data.portfolio;

        const totalValueEl = document.getElementById('total-value');
        const totalReturnEl = document.getElementById('total-return');
        const totalAccrualsEl = document.getElementById('total-accruals');

        if (totalValueEl) {
            totalValueEl.textContent = Utils.formatCurrency(summary.total_value);
        }

        if (totalReturnEl) {
            const returnText = `${Utils.formatCurrency(summary.total_return)} (${Utils.formatPercent(summary.total_return_percent)})`;
            totalReturnEl.textContent = returnText;
            totalReturnEl.className = 'card-value ' + (summary.total_return >= 0 ? 'positive' : 'negative');
        }

        if (totalAccrualsEl) {
            totalAccrualsEl.textContent = Utils.formatCurrency(summary.total_accruals);
        }
    },
};