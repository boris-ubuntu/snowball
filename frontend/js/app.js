const App = {
    portfolioId: null,
    dashboardData: null,  // Кеш для данных главной страницы

    async init() {
        // Set current date
        document.getElementById('current-date').textContent =
            new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });

        // Bind refresh
        document.getElementById('refresh-btn').addEventListener('click', () => this.refreshPrices());

        // Header transaction button opens modal
        document.getElementById('add-transaction-header-btn').addEventListener('click', () => this.openTransactionModal());

        // Navigation
        document.getElementById('nav-main').addEventListener('click', () => {
            this.showPage('main');
            this.loadDashboard();
            DividendsHistogram.load(this.portfolioId);
        });
        document.getElementById('nav-assets').addEventListener('click', () => {
            this.showPage('assets');
            SecuritiesManager.load(this.portfolioId);
            // Load positions when assets page is shown
            this.loadAssetsPositions();
        });
        document.getElementById('nav-operations').addEventListener('click', () => {
            this.showPage('operations');
            TransactionsComponent.load(this.portfolioId);
        });
        document.getElementById('nav-dividends').addEventListener('click', () => {
            this.showPage('dividends');
            DividendsComponent.load(this.portfolioId);
        });

        // Add security modal
        document.getElementById('add-security-btn').addEventListener('click', () => this.openAddSecurityModal());
        document.getElementById('close-add-modal').addEventListener('click', () => this.closeAddSecurityModal());
        document.getElementById('cancel-add-btn').addEventListener('click', () => this.closeAddSecurityModal());
        document.getElementById('add-security-modal-overlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) this.closeAddSecurityModal();
        });
        document.getElementById('add-security-form').addEventListener('submit', (e) => this.handleAddSecurity(e));

        // Init securities manager
        SecuritiesManager.init();

        // Get default portfolio
        try {
            const portfolio = await API.getDefaultPortfolio();
            this.portfolioId = portfolio.id;
            console.log(`Portfolio: ${portfolio.name} (id=${portfolio.id})`);

            // Init modal
            await ModalComponent.init(this.portfolioId);

            // Load main page
            await this.loadDashboard();

            // Load dividends histogram on main page
            await DividendsHistogram.load(this.portfolioId);

            // Load assets
            await SecuritiesManager.load(this.portfolioId);
        } catch (e) {
            console.error('Failed to initialize:', e);
            this.showError('Не удалось подключиться к серверу. Запустите бэкенд.');
        }
    },

    async loadAssetsPositions() {
        if (!this.portfolioId) return;
        try {
            const data = await API.getDashboard(this.portfolioId);
            PositionsComponent.render(data);
        } catch (e) {
            console.error('Failed to load positions:', e);
        }
    },

    showPage(page) {
        document.getElementById('page-main').classList.toggle('hidden', page !== 'main');
        document.getElementById('page-operations').classList.toggle('hidden', page !== 'operations');
        document.getElementById('page-dividends').classList.toggle('hidden', page !== 'dividends');
        document.getElementById('page-assets').classList.toggle('hidden', page !== 'assets');
        document.getElementById('nav-main').classList.toggle('active', page === 'main');
        document.getElementById('nav-assets').classList.toggle('active', page === 'assets');
        document.getElementById('nav-operations').classList.toggle('active', page === 'operations');
        document.getElementById('nav-dividends').classList.toggle('active', page === 'dividends');
    },

    openAddSecurityModal() {
        document.getElementById('add-security-modal-overlay').classList.remove('hidden');
    },

    closeAddSecurityModal() {
        document.getElementById('add-security-modal-overlay').classList.add('hidden');
        document.getElementById('sec-ticker').value = '';
        document.getElementById('sec-name').value = '';
        document.getElementById('sec-isin').value = '';
    },

    async handleAddSecurity(e) {
        e.preventDefault();

        const ticker = document.getElementById('sec-ticker').value.trim().toUpperCase();
        const name = document.getElementById('sec-name').value.trim();
        const isin = document.getElementById('sec-isin').value.trim().toUpperCase() || null;
        const type = document.getElementById('sec-type').value;

        if (!ticker || !name) return;

        try {
            await API.createSecurity({
                ticker: ticker,
                name: name,
                security_type: type,
                isin: isin,
            });

            this.closeAddSecurityModal();

            // Reload securities list and modal
            await SecuritiesManager.load(this.portfolioId);
            if (typeof ModalComponent !== 'undefined' && ModalComponent.loadSecurities) {
                await ModalComponent.loadSecurities();
            }
        } catch (e) {
            alert('Ошибка: ' + e.message);
        }
    },

    async loadDashboard(forceRefresh = false) {
        if (!this.portfolioId) return;

        // Если есть кеш и не требуется принудительное обновление - используем его
        if (this.dashboardData && !forceRefresh) {
            console.log('📊 Используем кешированные данные дашборда');
            this.renderDashboard(this.dashboardData);
            return;
        }

        try {
            const data = await API.getDashboard(this.portfolioId);
            // Сохраняем в кеш
            this.dashboardData = data;
            this.renderDashboard(data);
        } catch (e) {
            console.error('Failed to load dashboard:', e);
            this.showError('Ошибка загрузки данных. Проверьте подключение к серверу.');
        }
    },

    renderDashboard(data) {
        // Render all components on main page
        SummaryComponent.render(data);
        ChartComponent.render(data);
        // Positions are now shown on assets page, not main page
    },

    async refreshPrices() {
        const btn = document.getElementById('refresh-btn');
        btn.textContent = '⏳';
        btn.disabled = true;

        try {
            const result = await API.refreshPrices();
            console.log(`Prices refreshed: ${result.updated}`);
            // Принудительно обновляем данные
            await this.loadDashboard(true);
        } catch (e) {
            console.error('Failed to refresh prices:', e);
        } finally {
            btn.textContent = '🔄';
            btn.disabled = false;
        }
    },

    // Метод для сброса кеша при добавлении новой сделки
    async refreshDashboard() {
        this.dashboardData = null;
        await this.loadDashboard(true);
        // Also refresh dividends histogram
        await DividendsHistogram.load(this.portfolioId);
    },

    openTransactionModal() {
        if (typeof ModalComponent !== 'undefined' && ModalComponent.open) {
            ModalComponent.open();
        }
    },

    showError(msg) {
        document.querySelectorAll('.loading').forEach(el => {
            el.textContent = '⚠️ ' + msg;
        });
    },
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => App.init());