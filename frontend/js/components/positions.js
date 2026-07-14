const PositionsComponent = {
    render(data) {
        const tbody = document.getElementById('positions-body');
        const positions = data.positions;

        if (!positions || positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="loading">Нет позиций. Добавьте первую сделку!</td></tr>';
            return;
        }

        tbody.innerHTML = positions.map(p => {
            const profitClass = p.profit >= 0 ? 'positive' : 'negative';
            const shareDisplay = p.share > 0 ? p.share.toFixed(2) + '%' : '0%';
            const currentPriceDisplay = p.current_price ? Utils.formatNumber(p.current_price) : '—';
            
            return `<tr>
                <td>${p.name}</td>
                <td><span class="ticker">${p.ticker}</span></td>
                <td><span class="type-badge ${Utils.getTypeClass(p.security_type)}">${Utils.getTypeLabel(p.security_type)}</span></td>
                <td>${p.quantity}</td>
                <td>${p.avg_price ? Utils.formatNumber(p.avg_price) : '—'}</td>
                <td>${currentPriceDisplay}</td>
                <td>${Utils.formatCurrency(p.total_value)}</td>
                <td>${shareDisplay}</td>
                <td class="${profitClass}" style="font-weight:600">${Utils.formatCurrency(p.profit)} (${p.profit_percent >= 0 ? '+' : ''}${p.profit_percent.toFixed(2)}%)</td>
            </tr>`;
        }).join('');
    },
};