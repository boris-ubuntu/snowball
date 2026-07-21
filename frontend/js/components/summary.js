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
        const yieldValueEl = document.getElementById('yield-value');
        const yieldSubEl = document.getElementById('yield-sub');

        // Стоимость
        if (totalValueEl) {
            totalValueEl.textContent = Utils.formatCurrency(summary.total_value);
        }

        // Вложено
        if (totalInvestedEl) {
            totalInvestedEl.textContent = Utils.formatCurrency(summary.total_invested);
        }

        // Прибыль — только сумма с маленьким треугольником
        if (totalReturnEl) {
            const prefix = summary.total_return >= 0 ? '▲' : '▼';
            totalReturnEl.textContent = prefix + ' ' + Utils.formatCurrency(Math.abs(summary.total_return));
            totalReturnEl.className = 'card-value ' + (summary.total_return >= 0 ? 'positive' : 'negative');
        }

        // Подпись под прибылью — "Выплаты" + сумма всех accruals
        if (returnSubEl) {
            returnSubEl.textContent = 'Выплаты ' + Utils.formatCurrency(summary.total_accruals);
        }

        // Пассивный доход — % доходности и сумму в год устанавливает
        // DividendsHistogram.updatePassiveIncomeCard() после загрузки гистограммы.
        // Здесь НЕ трогаем #expected-income и #total-accruals, чтобы не перезаписать
        // точные данные гистограммы ошибочным fallback-ом с бэкенда.

        // Доходность — общая доходность портфеля (текущая стоимость + начисления) / вложено - 1
        if (yieldValueEl) {
            const pct = summary.total_return_percent || 0;
            const prefix = pct >= 0 ? '▲' : '▼';
            const colorClass = pct >= 0 ? 'positive' : 'negative';
            yieldValueEl.textContent = prefix + ' ' + Utils.formatPercent(Math.abs(pct));
            yieldValueEl.className = 'card-value ' + colorClass;
        }

        // Подпись: дневной P/L
        if (yieldSubEl) {
            const dailyPl = summary.daily_pl || 0;
            const prefix_ = dailyPl >= 0 ? '▲' : '▼';
            yieldSubEl.textContent = `${prefix_} ${Utils.formatCurrency(Math.abs(dailyPl))} сегодня`;
        }
    },
};