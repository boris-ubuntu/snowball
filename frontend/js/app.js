const App = {
    portfolioId: null,
    dashboardData: null,

    async init() {
        const token = API.getToken();
        if (token) {
            this.showApp();
            await this.initApp();
        } else {
            this.showLogin();
        }

        document.getElementById('login-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.handleLogin();
        });

        document.getElementById('logout-btn').addEventListener('click', () => {
            this.logout();
        });

        document.getElementById('refresh-btn').addEventListener('click', () => {
            this.refreshAllData();
        });

        const economyOverlay = document.getElementById('economy-modal-overlay');
        const economyCloseBtn = document.getElementById('close-economy-modal');
        if (economyCloseBtn) {
            economyCloseBtn.addEventListener('click', () => economyOverlay.classList.add('hidden'));
        }
        if (economyOverlay) {
            economyOverlay.addEventListener('click', (e) => {
                if (e.target === economyOverlay) economyOverlay.classList.add('hidden');
            });
        }

        document.getElementById('card-total').addEventListener('click', () => {
            this.showPage('assets');
            this.loadAssetsPositions();
            SecuritiesManager.load(this.portfolioId);
        });
        document.getElementById('card-return').addEventListener('click', () => {
            this.showPage('operations');
            TransactionsComponent.load(this.portfolioId);
        });
        document.getElementById('card-accruals').addEventListener('click', () => {
            this.showPage('dividends');
            DividendsComponent.load(this.portfolioId);
        });

        document.querySelectorAll('.back-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                this.showPage('main');
                await this.loadDashboard();
                DividendsHistogram.load(this.portfolioId, this.dashboardData);
            });
        });

        document.getElementById('chart-mode-toggle').addEventListener('change', (e) => {
            if (this.dashboardData) {
                ChartComponent.render(this.dashboardData, e.target.checked);
            }
        });

        document.getElementById('close-add-modal').addEventListener('click', () => this.closeAddSecurityModal());
        document.getElementById('cancel-add-btn').addEventListener('click', () => this.closeAddSecurityModal());
        document.getElementById('add-security-modal-overlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) this.closeAddSecurityModal();
        });
        document.getElementById('add-security-form').addEventListener('submit', (e) => this.handleAddSecurity(e));

        SecuritiesManager.init();

        document.getElementById('add-transaction-header-btn').addEventListener('click', () => this.openTransactionModal());
    },

    showLogin() {
        document.getElementById('login-page').classList.remove('hidden');
        document.getElementById('app').classList.add('hidden');
        document.getElementById('login-error').classList.add('hidden');
    },

    showApp() {
        document.getElementById('login-page').classList.add('hidden');
        document.getElementById('app').classList.remove('hidden');
    },

    async handleLogin() {
        const username = document.getElementById('login-username').value.trim();
        const password = document.getElementById('login-password').value;
        const errorEl = document.getElementById('login-error');

        if (!username || !password) {
            errorEl.classList.remove('hidden');
            return;
        }

        try {
            const result = await API.login(username, password);
            API.setToken(result.access_token);
            errorEl.classList.add('hidden');
            this.showApp();
            if (!this.portfolioId) {
                await this.initApp();
            } else {
                await this.loadDashboard(true);
                await DividendsHistogram.load(this.portfolioId);
                await SecuritiesManager.load(this.portfolioId);
            }
        } catch (e) {
            errorEl.classList.remove('hidden');
            console.error('Login failed:', e);
        }
    },

    logout() {
        API.setToken(null);
        this.dashboardData = null;
        this.portfolioId = null;
        this.showLogin();
        document.getElementById('login-username').value = '';
        document.getElementById('login-password').value = '';
    },

    async initApp() {
        document.getElementById('current-date').textContent =
            new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });

        try {
            const portfolio = await API.getDefaultPortfolio();
            this.portfolioId = portfolio.id;
            console.log(`Portfolio: ${portfolio.name} (id=${portfolio.id})`);

            await ModalComponent.init(this.portfolioId);

            // Load dashboard FIRST — sets this.dashboardData
            await this.loadDashboard();

            // Then render histogram and securities with the loaded data
            DividendsHistogram.load(this.portfolioId, this.dashboardData);
            SecuritiesManager.load(this.portfolioId).catch(() => {});
        } catch (e) {
            console.error('Failed to initialize:', e);
            if (e.message && (e.message.includes('401') || e.message.includes('Необходима авторизация'))) {
                this.logout();
            }
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

    showDividends() {
        this.showPage('dividends');
        DividendsComponent.load(this.portfolioId);
    },

    showPage(page) {
        document.getElementById('page-main').classList.toggle('hidden', page !== 'main');
        document.getElementById('page-operations').classList.toggle('hidden', page !== 'operations');
        document.getElementById('page-dividends').classList.toggle('hidden', page !== 'dividends');
        document.getElementById('page-assets').classList.toggle('hidden', page !== 'assets');
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
            await API.createSecurity({ ticker, name, security_type: type, isin });
            this.closeAddSecurityModal();
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
        try {
            const data = await API.getDashboard(this.portfolioId);
            this.dashboardData = data;
            this.renderDashboard(data);
        } catch (e) {
            console.error('Failed to load dashboard:', e);
            this.showError('Ошибка загрузки данных. Проверьте подключение к серверу.');
        }
    },

    renderDashboard(data) {
        SummaryComponent.render(data);
        ChartComponent.render(data, document.getElementById('chart-mode-toggle')?.checked || false);
    },

    async refreshAllData() {
        const btn = document.getElementById('refresh-btn');
        btn.disabled = true;
        btn.textContent = '⏳ Обновление...';
        try {
            await API.refreshAllData(this.portfolioId);
            alert('✅ Данные обновлены. Перезагрузите страницу для применения.');
        } catch (e) {
            alert('❌ Ошибка: ' + e.message);
        } finally {
            btn.disabled = false;
            btn.textContent = '🔄 Обновить данные';
        }
    },

    async refreshDashboard() {
        this.dashboardData = null;
        await this.loadDashboard(true);
        await DividendsHistogram.load(this.portfolioId);
        if (this.dashboardData) {
            ChartComponent.render(this.dashboardData, document.getElementById('chart-mode-toggle')?.checked || false);
            SummaryComponent.render(this.dashboardData);
        }
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

// Custom confirm dialog
const ConfirmDialog = {
    show(text) {
        return new Promise((resolve) => {
            const overlay = document.getElementById('confirm-overlay');
            const textEl = document.getElementById('confirm-text');
            const yesBtn = document.getElementById('confirm-yes');
            const noBtn = document.getElementById('confirm-no');
            textEl.textContent = text;
            overlay.classList.remove('hidden');
            const cleanup = () => {
                overlay.classList.add('hidden');
                yesBtn.removeEventListener('click', onYes);
                noBtn.removeEventListener('click', onNo);
                overlay.removeEventListener('click', onOverlay);
            };
            const onYes = () => { cleanup(); resolve(true); };
            const onNo = () => { cleanup(); resolve(false); };
            const onOverlay = (e) => { if (e.target === overlay) { cleanup(); resolve(false); } };
            yesBtn.addEventListener('click', onYes);
            noBtn.addEventListener('click', onNo);
            overlay.addEventListener('click', onOverlay);
        });
    }
};

// Register passive Service Worker (replaces old cache-based SW)
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch(() => {});
    });
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => App.init());
