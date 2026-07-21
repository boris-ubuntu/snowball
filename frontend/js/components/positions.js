const PositionsComponent = {
    positionsData: null,
    contextMenu: null,

    render(data) {
        const tbody = document.getElementById('positions-body');
        const positions = data.positions;
        this.positionsData = positions;

        if (!positions || positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="loading">Нет позиций. Добавьте первую сделку!</td></tr>';
            return;
        }

        tbody.innerHTML = positions.map((p, idx) => {
            const profitClass = p.profit >= 0 ? 'positive' : 'negative';
            const shareDisplay = p.share > 0 ? p.share.toFixed(2) + '%' : '0%';
            const currentPriceDisplay = p.current_price ? Utils.formatNumber(p.current_price) : '—';
            const realizedDisplay = p.realized_profit ? (p.realized_profit > 0 ? '▲' : '▼') + ' ' + Utils.formatCurrency(p.realized_profit) : '—';

            return `<tr class="pos-row" data-index="${idx}" data-id="${p.id}" style="cursor:pointer;">
                <td>
                    <div class="pos-name">${p.name}</div>
                    <div class="pos-ticker">${p.ticker}</div>
                </td>
                <td><span class="type-badge ${Utils.getTypeClass(p.security_type)}">${Utils.getTypeLabel(p.security_type)}</span></td>
                <td>${p.quantity}</td>
                <td>${p.avg_price ? Utils.formatNumber(p.avg_price) : '—'}</td>
                <td>${currentPriceDisplay}</td>
                <td>${Utils.formatCurrency(p.total_value)}</td>
                <td>${shareDisplay}</td>
                <td class="${profitClass}" style="font-weight:600">${p.profit >= 0 ? '▲' : '▼'} ${Utils.formatCurrency(p.profit)}</td>
                <td style="font-size:0.85rem;opacity:0.8">${realizedDisplay}</td>
            </tr>`;
        }).join('');

        // Bind click on rows to show context menu
        tbody.querySelectorAll('.pos-row').forEach(row => {
            row.addEventListener('click', (e) => {
                const idx = parseInt(row.dataset.index);
                const pos = this.positionsData[idx];
                if (pos) this.showContextMenu(e, pos);
            });
        });

        // Close context menu on click outside
        document.addEventListener('click', (e) => {
            if (this.contextMenu && !e.target.closest('.pos-context-menu') && !e.target.closest('.pos-row')) {
                this.closeContextMenu();
            }
        });
    },

    showContextMenu(event, pos) {
        this.closeContextMenu();

        const menu = document.createElement('div');
        menu.className = 'pos-context-menu';
        menu.style.cssText = `
            position: fixed;
            left: ${event.clientX}px;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 6px 0;
            z-index: 1001;
            min-width: 200px;
            box-shadow: var(--shadow);
        `;

        // Temporarily add to body to measure height, then reposition
        document.body.appendChild(menu);
        const menuHeight = menu.offsetHeight;
        const spaceBelow = window.innerHeight - event.clientY - 10;
        if (spaceBelow < menuHeight) {
            menu.style.top = Math.max(10, event.clientY - menuHeight) + 'px';
        } else {
            menu.style.top = event.clientY + 'px';
        }
        // Remove and re-add properly below
        menu.remove();

        const items = [
            { icon: '🟢', label: 'Купить', action: () => this.buy(pos) },
            { icon: '🔴', label: 'Продать', action: () => this.sell(pos) },
            { icon: '💰', label: 'Начисление', action: () => this.accrual(pos) },
            { icon: '✏️', label: 'Изменить среднюю цену', action: () => this.editAvgPrice(pos) },
            { icon: '📅', label: 'Изменить дату последней сделки', action: () => this.editDate(pos) },
            { icon: '🗑️', label: 'Удалить', action: () => this.deleteOperations(pos) },
        ];

        items.forEach(item => {
            const btn = document.createElement('button');
            btn.style.cssText = `
                display: block;
                width: 100%;
                padding: 8px 16px;
                background: none;
                border: none;
                color: var(--text-primary);
                font-size: 0.9rem;
                text-align: left;
                cursor: pointer;
                font-family: inherit;
            `;
            btn.innerHTML = `${item.icon} ${item.label}`;
            btn.addEventListener('mouseenter', () => btn.style.background = 'var(--bg-hover)');
            btn.addEventListener('mouseleave', () => btn.style.background = 'none');
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.closeContextMenu();
                item.action();
            });
            menu.appendChild(btn);
        });

        this.contextMenu = menu;
        document.body.appendChild(menu);
    },

    closeContextMenu() {
        if (this.contextMenu) {
            this.contextMenu.remove();
            this.contextMenu = null;
        }
    },

    buy(pos) {
        if (typeof ModalComponent !== 'undefined' && ModalComponent.openWithSecurity) {
            ModalComponent.openWithSecurity({
                id: pos.security_id,
                ticker: pos.ticker,
                name: pos.name,
                security_type: pos.security_type,
            }, 'buy');
        }
    },

    sell(pos) {
        if (typeof ModalComponent !== 'undefined' && ModalComponent.openWithSecurity) {
            ModalComponent.openWithSecurity({
                id: pos.security_id,
                ticker: pos.ticker,
                name: pos.name,
                security_type: pos.security_type,
            }, 'sell');
        }
    },

    accrual(pos) {
        document.getElementById('accrual-sec-id').value = pos.security_id;
        document.getElementById('accrual-ticker-label').textContent = `${pos.ticker} — ${pos.name}`;
        document.getElementById('accrual-amount').value = '';
        document.getElementById('accrual-date').value = new Date().toISOString().split('T')[0];
        document.getElementById('accrual-notes').value = '';
        document.getElementById('accrual-modal-overlay').classList.remove('hidden');
    },

    editAvgPrice(pos) {
        const newPrice = prompt(`Изменить среднюю цену для ${pos.ticker} (текущая: ${pos.avg_price || 'не указана'}):`, pos.avg_price || '');
        if (newPrice === null) return;
        const price = parseFloat(newPrice.replace(',', '.'));
        if (isNaN(price) || price <= 0) return;
        if (confirm(`Установить среднюю цену ${pos.ticker} = ${price} ₽?`)) {
            this.updateAvgPrice(pos, price);
        }
    },

    async updateAvgPrice(pos, newAvgPrice) {
        try {
            const API_BASE = CONFIG.API_BASE;
            const portfolioId = App.portfolioId;
            const res = await fetch(`${API_BASE}/portfolio/${portfolioId}/positions`);
            const positions = await res.json();
            const backendPos = positions.find(p => p.security_id === pos.security_id);
            if (!backendPos) {
                alert('Позиция не найдена в БД');
                return;
            }
            await fetch(`${API_BASE}/portfolio/${portfolioId}/positions/${backendPos.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ avg_price: newAvgPrice }),
            });
            if (typeof App !== 'undefined') App.loadAssetsPositions();
            if (typeof App !== 'undefined') App.loadDashboard(true);
        } catch (e) {
            alert('Ошибка: ' + e.message);
        }
    },

    editDate(pos) {
        alert('Функция изменения даты последней сделки будет добавлена позже');
    },

    async deleteOperations(pos) {
        const confirmed = await ConfirmDialog.show(`Точно удалить?\n\nВсе операции и позиция по ${pos.ticker} будут удалены. Сам актив останется.`);
        if (!confirmed) return;
        try {
            const portfolioId = App.portfolioId;
            const API_BASE = CONFIG.API_BASE;
            // Use batch delete endpoint
            const res = await fetch(`${API_BASE}/portfolio/${portfolioId}/transactions/by-security/${pos.security_id}`, {
                method: 'DELETE',
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `HTTP ${res.status}`);
            }
            if (typeof App !== 'undefined') App.loadAssetsPositions();
            if (typeof App !== 'undefined') App.loadDashboard(true);
            if (typeof App !== 'undefined' && App.refreshDashboard) App.refreshDashboard();
        } catch (e) {
            alert('Ошибка: ' + e.message);
        }
    },
};