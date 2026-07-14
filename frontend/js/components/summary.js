const SummaryComponent = {
    render(data) {
        const summary = data.portfolio;

        const totalValueEl = document.getElementById('total-value');
        const totalReturnEl = document.getElementById('total-return');
        const totalAccrualsEl = document.getElementById('total-accruals');
        const accrualsPercentEl = document.getElementById('accruals-percent');
        const expectedIncomeEl = document.getElementById('expected-income');
        const totalInvestedEl = document.getElementById('total-invested');
        const returnSubEl = document.getElementById('return-sub');

        // Стоимость
        if (totalValueEl) {
            totalValueEl.textContent = Utils.formatCurrency(summary.total_value);
        }

        // Вложено
        if (totalInvestedEl) {
            totalInvestedEl.textContent = Utils.formatCurrency(summary.total_invested);
        }

        // Прибыль — только сумма с треугольником, без процентов
        if (totalReturnEl) {
            const prefix = summary.total_return >= 0 ? '▲' : '▼';
            totalReturnEl.textContent = prefix + ' ' + Utils.formatCurrency(Math.abs(summary.total_return));
            totalReturnEl.className = 'card-value ' + (summary.total_return >= 0 ? 'positive' : 'negative');
        }

        // Подпись под прибылью — пассивный доход
        if (returnSubEl) {
            returnSubEl.textContent = 'Пассивный доход ' + Utils.formatCurrency(summary.total_accruals);
        }

        // Пассивный доход — показываем суммарную доходность с треугольником
        if (totalAccrualsEl) {
            const pct = summary.total_invested > 0
                ? ((summary.total_value + summary.total_accruals) / summary.total_invested - 1) * 100
                : 0;
            const prefix = pct >= 0 ? '▲' : '▼';
            const colorClass = pct >= 0 ? 'positive' : 'negative';
            totalAccrualsEl.textContent = prefix + ' ' + Utils.formatPercent(Math.abs(pct));
            totalAccrualsEl.className = 'card-value ' + colorClass;
        }

        // Подпись под пассивным доходом
        if (accrualsPercentEl) {
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