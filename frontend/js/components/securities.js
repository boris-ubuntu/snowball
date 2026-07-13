const SecuritiesManager = {
    portfolioId: null,

    async load(portfolioId) {
        this.portfolioId = portfolioId || this.portfolioId;
        const container = document.getElementById('securities-list');
        container.innerHTML = '<div class="loading">Загрузка...</div>';

        if (!this.portfolioId) return;

        try {
            const securities = await API.getPortfolioSecurities(this.portfolioId);
            this.render(securities);
        } catch (e) {
            container.innerHTML = '<div class="loading">⚠️ Ошибка загрузки</div>';
        }
    },

    async loadOfzBonds() {
        const btn = document.getElementById('load-ofz-btn');
        if (btn) { btn.disabled = true; btn.textContent = '⏳ Загрузка...'; }
        try {
            const result = await API.loadOfzBonds();
            alert(`✅ Загружено ${result.added} новых ОФЗ`);
            if (typeof ModalComponent !== 'undefined' && ModalComponent.loadSecurities) {
                ModalComponent.loadSecurities();
            }
        } catch (e) {
            alert('Ошибка: ' + e.message);
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '📜 Загрузить ОФЗ'; }
        }
    },

    render(securities) {
        const container = document.getElementById('securities-list');

        const headerHtml = `<div class="header-actions" style="display:flex;justify-content:flex-end;gap:8px;margin-bottom:12px;">
            <button id="load-ofz-btn" class="btn-secondary" onclick="SecuritiesManager.loadOfzBonds()">📜 Загрузить ОФЗ</button>
        </div>`;

        if (!securities || securities.length === 0) {
            container.innerHTML = headerHtml + '<div class="loading">Нет добавленных активов. Добавьте сделку на главной.</div>';
            return;
        }

        container.innerHTML = headerHtml + securities.map(sec => {
            const balance = (sec.current_price || 0) * sec.quantity + (sec.total_accruals || 0);
            const cost = (sec.avg_price || 0) * sec.quantity;
            const profit = balance - cost;

            return `<div class="security-item" data-id="${sec.id}">
                <div class="sec-info">
                    <span class="ticker">${sec.ticker}</span>
                    <span class="sec-name">${sec.name}</span>
                    <span class="type-badge ${Utils.getTypeClass(sec.security_type)}">${Utils.getTypeLabel(sec.security_type)}</span>
                    ${sec.current_price ? `<span class="sec-price">${Utils.formatCurrency(sec.current_price)}</span>` : ''}
                </div>
                <div class="sec-details">
                    <div class="sec-detail-row">
                        <span class="detail-label">Кол-во:</span>
                        <span class="detail-value">${sec.quantity} шт</span>
                    </div>
                    <div class="sec-detail-row">
                        <span class="detail-label">Средняя:</span>
                        <span class="detail-value">${sec.avg_price ? Utils.formatCurrency(sec.avg_price) : '—'}</span>
                    </div>
                    <div class="sec-detail-row">
                        <span class="detail-label">Начисления:</span>
                        <span class="detail-value positive">${Utils.formatCurrency(sec.total_accruals || 0)}</span>
                    </div>
                    <div class="sec-detail-row">
                        <span class="detail-label">Баланс:</span>
                        <span class="detail-value ${profit >= 0 ? 'positive' : 'negative'}">${Utils.formatCurrency(balance)}</span>
                    </div>
                </div>
                <div class="sec-actions">
                    <button class="icon-btn sec-buy" data-id="${sec.id}" title="Купить">🟢</button>
                    <button class="icon-btn sec-sell" data-id="${sec.id}" title="Продать">🔴</button>
                    <button class="icon-btn sec-accrual" data-id="${sec.id}" title="Начисление">💰</button>
                    <button class="icon-btn edit-sec" data-id="${sec.id}" title="Редактировать">✏️</button>
                    <button class="icon-btn delete-sec" data-id="${sec.id}" title="Удалить">🗑️</button>
                </div>
            </div>`;
        }).join('');

        // Bind action buttons
        container.querySelectorAll('.sec-buy').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id);
                const sec = securities.find(s => s.id === id);
                if (sec) this.openTransactionModal(sec, 'buy');
            });
        });

        container.querySelectorAll('.sec-sell').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id);
                const sec = securities.find(s => s.id === id);
                if (sec) this.openTransactionModal(sec, 'sell');
            });
        });

        container.querySelectorAll('.sec-accrual').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id);
                const sec = securities.find(s => s.id === id);
                if (sec) this.openAccrualModal(sec);
            });
        });

        container.querySelectorAll('.edit-sec').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id);
                const sec = securities.find(s => s.id === id);
                if (sec) this.openEditModal(sec);
            });
        });

        container.querySelectorAll('.delete-sec').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.id);
                const sec = securities.find(s => s.id === id);
                if (sec) this.confirmDelete(sec);
            });
        });
    },

    openTransactionModal(sec, type) {
        if (typeof ModalComponent !== 'undefined') {
            ModalComponent.openWithSecurity(sec, type);
        }
    },

    openAccrualModal(sec) {
        document.getElementById('accrual-sec-id').value = sec.id;
        document.getElementById('accrual-ticker-label').textContent = `${sec.ticker} — ${sec.name}`;
        document.getElementById('accrual-amount').value = '';
        document.getElementById('accrual-date').value = new Date().toISOString().split('T')[0];
        document.getElementById('accrual-notes').value = '';
        document.getElementById('accrual-modal-overlay').classList.remove('hidden');
    },

    closeAccrualModal() {
        document.getElementById('accrual-modal-overlay').classList.add('hidden');
    },

    async handleAccrualSubmit(e) {
        e.preventDefault();
        const securityId = parseInt(document.getElementById('accrual-sec-id').value);
        const amount = parseFloat(document.getElementById('accrual-amount').value);
        const date = document.getElementById('accrual-date').value;
        const notes = document.getElementById('accrual-notes').value.trim();

        if (!amount || amount <= 0) return;

        try {
            await API.createTransaction(this.portfolioId, {
                security_id: securityId,
                transaction_type: 'accrual',
                quantity: 1,
                price: amount,
                commission: 0,
                transaction_date: date,
                notes: notes || 'Начисление',
            });

            this.closeAccrualModal();
            await this.load();
            if (typeof App !== 'undefined' && App.loadDashboard) {
                await App.loadDashboard();
            }
        } catch (e) {
            alert('Ошибка: ' + e.message);
        }
    },

    openEditModal(sec) {
        document.getElementById('edit-sec-id').value = sec.id;
        document.getElementById('edit-sec-ticker').value = sec.ticker;
        document.getElementById('edit-sec-name').value = sec.name;
        document.getElementById('edit-sec-type').value = sec.security_type;
        document.getElementById('edit-security-modal-overlay').classList.remove('hidden');
    },

    closeEditModal() {
        document.getElementById('edit-security-modal-overlay').classList.add('hidden');
    },

    async confirmDelete(sec) {
        if (!confirm(`Удалить бумагу ${sec.ticker} (${sec.name})?\nЭто также удалит все связанные сделки и позиции.`)) return;
        try {
            await API.deleteSecurity(sec.id);
            await this.load();
            if (typeof ModalComponent !== 'undefined' && ModalComponent.loadSecurities) {
                ModalComponent.loadSecurities();
            }
        } catch (e) {
            alert('Ошибка при удалении: ' + e.message);
        }
    },

    async handleEditSubmit(e) {
        e.preventDefault();
        const id = parseInt(document.getElementById('edit-sec-id').value);
        const ticker = document.getElementById('edit-sec-ticker').value.trim().toUpperCase();
        const name = document.getElementById('edit-sec-name').value.trim();
        const securityType = document.getElementById('edit-sec-type').value;

        if (!ticker || !name) return;

        try {
            await API.updateSecurity(id, { ticker, name, security_type: securityType });
            this.closeEditModal();
            await this.load();
            if (typeof ModalComponent !== 'undefined' && ModalComponent.loadSecurities) {
                ModalComponent.loadSecurities();
            }
        } catch (e) {
            alert('Ошибка при сохранении: ' + e.message);
        }
    },

    init() {
        // Bind edit modal events
        document.getElementById('close-edit-modal').addEventListener('click', () => this.closeEditModal());
        document.getElementById('cancel-edit-btn').addEventListener('click', () => this.closeEditModal());
        document.getElementById('edit-security-modal-overlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) this.closeEditModal();
        });
        document.getElementById('edit-security-form').addEventListener('submit', (e) => this.handleEditSubmit(e));

        // Bind accrual modal events
        document.getElementById('close-accrual-modal').addEventListener('click', () => this.closeAccrualModal());
        document.getElementById('cancel-accrual-btn').addEventListener('click', () => this.closeAccrualModal());
        document.getElementById('accrual-modal-overlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) this.closeAccrualModal();
        });
        document.getElementById('accrual-form').addEventListener('submit', (e) => this.handleAccrualSubmit(e));
    },
};