const SummaryComponent = {
    render(data) {
        const summary = data.portfolio;

        const totalValueEl = document.getElementById('total-value');
        const totalReturnEl = document.getElementById('total-return');
        const totalAccrualsEl = document.getElementById('total-accruals');
        const accrualsPercentEl = document.getElementById('accruals-percent');
        const expectedIncomeEl = document.getElementById('expected-income');

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

        if (accrualsPercentEl) {
            const pct = summary.total_value > 0
                ? (summary.total_accruals / summary.total_value * 100)
                : 0;
            const expectedText = summary.expected_annual_income > 0
                ? Utils.formatCurrency(summary.expected_annual_income)
                : '—';
            accrualsPercentEl.innerHTML = `Ожидается за 12 мес: <span id="expected-income">${expectedText}</span>`;
        }

        if (expectedIncomeEl) {
            const text = summary.expected_annual_income > 0
                ? Utils.formatCurrency(summary.expected_annual_income)
                : '—';
            expectedIncomeEl.textContent = text;
        }
    },
};