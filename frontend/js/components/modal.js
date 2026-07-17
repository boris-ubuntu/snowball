const ModalComponent = {
    portfolioId: null,
    securities: [],

    async init(portfolioId) {
        this.portfolioId = portfolioId;
        this.bindEvents();
        await this.loadSecurities();
    },

    async loadSecurities() {
        try {
            this.securities = await API.getSecurities();
            console.log(`📊 Загружено ${this.securities.length} бумаг для поиска`);
        } catch (e) {
            console.error('Failed to load securities:', e);
            this.securities = [];
        }
    },

    filterSecurities(query) {
        const select = document.getElementById('ticker-select');
        const q = query.trim().toUpperCase();

        if (!q) {
            select.innerHTML = '<option value="">— Введите текст для поиска —</option>';
            return;
        }

        const filtered = this.securities.filter(sec =>
            sec.ticker.toUpperCase().includes(q) ||
            sec.name.toUpperCase().includes(q) ||
            (sec.isin && sec.isin.toUpperCase().includes(q))
        ).slice(0, 50);

        if (filtered.length === 0) {
            select.innerHTML = '<option value="">— Ничего не найдено —</option>';
            return;
        }

        select.innerHTML = filtered.map(sec =>
            `<option value="${sec.id}">${sec.ticker} — ${sec.name} ${sec.isin ? '(' + sec.isin + ')' : ''}</option>`
        ).join('');
    },

    bindEvents() {
        const addTxBtn = document.getElementById('add-transaction-btn');
        if (addTxBtn) {
            addTxBtn.addEventListener('click', () => this.open());
        }
        document.getElementById('close-modal').addEventListener('click', () => this.close());
        document.getElementById('modal-overlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) this.close();
        });
        document.getElementById('transaction-form').addEventListener('submit', (e) => this.handleSubmit(e));

        // Search as you type
        document.getElementById('ticker-search').addEventListener('input', (e) => {
            this.filterSecurities(e.target.value);
        });

        // Select on click - auto-fill price from security's current_price
        document.getElementById('ticker-select').addEventListener('change', (e) => {
            const selected = e.target.selectedOptions[0];
            if (selected && selected.value) {
                document.getElementById('ticker-search').value = selected.text;
                // Auto-fill price from security's current price
                const secId = parseInt(selected.value);
                const sec = this.securities.find(s => s.id === secId);
                if (sec && sec.current_price) {
                    document.getElementById('tx-price').value = sec.current_price;
                }
                this.calcTotal();
            }
        });

        // Calculate total on input change
        ['tx-quantity', 'tx-price', 'tx-commission'].forEach(id => {
            document.getElementById(id).addEventListener('input', () => this.calcTotal());
        });
    },

    open() {
        document.getElementById('modal-overlay').classList.remove('hidden');
        document.getElementById('tx-date').value = Utils.getToday();
        document.getElementById('ticker-search').value = '';
        document.getElementById('ticker-select').innerHTML = '<option value="">— Введите текст для поиска —</option>';
        document.querySelector('input[name="tx-type"][value="buy"]').checked = true;
        this.calcTotal();
        this.loadSecurities();
    },

    openWithSecurity(sec, type) {
        document.getElementById('modal-overlay').classList.remove('hidden');
        document.getElementById('tx-date').value = Utils.getToday();
        document.getElementById('ticker-search').value = `${sec.ticker} — ${sec.name}`;
        // Set the select to have this security pre-selected
        const select = document.getElementById('ticker-select');
        select.innerHTML = `<option value="${sec.id}">${sec.ticker} — ${sec.name}</option>`;
        // Set transaction type
        document.querySelector(`input[name="tx-type"][value="${type}"]`).checked = true;
        document.getElementById('tx-quantity').value = '';
        document.getElementById('tx-price').value = sec.current_price || '';
        document.getElementById('tx-commission').value = '0';
        this.calcTotal();
    },

    close() {
        document.getElementById('modal-overlay').classList.add('hidden');
        document.getElementById('transaction-form').reset();
        document.getElementById('ticker-select').innerHTML = '<option value="">— Введите текст для поиска —</option>';
    },

    calcTotal() {
        const qty = parseFloat(document.getElementById('tx-quantity').value) || 0;
        const price = parseFloat(document.getElementById('tx-price').value) || 0;
        const comm = parseFloat(document.getElementById('tx-commission').value) || 0;
        const type = document.querySelector('input[name="tx-type"]:checked').value;

        let total = qty * price;
        if (type === 'buy') total += comm;
        else total -= comm;

        document.getElementById('tx-total').textContent = `Сумма: ${Utils.formatCurrency(total)}`;
    },

    async handleSubmit(e) {
        e.preventDefault();

        const securityId = parseInt(document.getElementById('ticker-select').value);
        const type = document.querySelector('input[name="tx-type"]:checked').value;
        const quantity = parseFloat(document.getElementById('tx-quantity').value);
        const price = parseFloat(document.getElementById('tx-price').value);
        const commission = parseFloat(document.getElementById('tx-commission').value) || 0;
        const date = document.getElementById('tx-date').value;
        const notes = document.getElementById('tx-notes').value.trim() || null;

        if (!securityId) {
            alert('Выберите ценную бумагу из списка');
            return;
        }

        try {
            await API.createTransaction(this.portfolioId, {
                security_id: securityId,
                transaction_type: type,
                quantity: quantity,
                price: price,
                commission: commission,
                transaction_date: date,
                notes: notes,
            });

            this.close();
            // Обновляем дашборд с принудительной перезагрузкой
            await App.refreshDashboard();
        } catch (e) {
            alert('Ошибка при создании сделки: ' + e.message);
        }
    },
};