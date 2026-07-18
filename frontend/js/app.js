const App = {
    portfolioId: null,
    dashboardData: null,  // Кеш для данных главной страницы

    async init() {
        // Check if already authenticated
        const token = API.getToken();
        if (token) {
            // Try to load the app with existing token
            this.showApp();
            await this.initApp();
        } else {
            // Show login page
            this.showLogin();
        }

        // Login form handler
        document.getElementById('login-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.handleLogin();
        });

        // Logout button
        document.getElementById('logout-btn').addEventListener('click', () => {
            this.logout();
        });

        // Economy modal close
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

        // Cards open hidden tabs
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

        // Back buttons on hidden pages
        document.querySelectorAll('.back-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.showPage('main');
                this.loadDashboard();
                DividendsHistogram.load(this.portfolioId);
            });
        });

        // Chart mode toggle
        document.getElementById('chart-mode-toggle').addEventListener('change', (e) => {
            if (this.dashboardData) {
                ChartComponent.render(this.dashboardData, e.target.checked);
            }
        });

        // Add security modal
        document.getElementById('close-add-modal').addEventListener('click', () => this.closeAddSecurityModal());
        document.getElementById('cancel-add-btn').addEventListener('click', () => this.closeAddSecurityModal());
        document.getElementById('add-security-modal-overlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) this.closeAddSecurityModal();
        });
        document.getElementById('add-security-form').addEventListener('submit', (e) => this.handleAddSecurity(e));

        // Init securities manager
        SecuritiesManager.init();

        // Header transaction button opens modal
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
            // Initialize the app now that we're logged in
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
        // Clear form fields
        document.getElementById('login-username').value = '';
        document.getElementById('login-password').value = '';
    },

    async initApp() {
        // Set current date
        document.getElementById('current-date').textContent =
            new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });

        // Get default portfolio
        try {
            const portfolio = await API.getDefaultPortfolio();
            this.portfolioId = portfolio.id;
            console.log(`Portfolio: ${portfolio.name} (id=${portfolio.id})`);

            // Init modal
            await ModalComponent.init(this.portfolioId);

            // Load dashboard + histogram + securities in parallel
            await Promise.all([
                this.loadDashboard(),
                DividendsHistogram.load(this.portfolioId).catch(() => {}),
                SecuritiesManager.load(this.portfolioId).catch(() => {}),
            ]);

            // Re-render chart and summary with histogram data
            if (this.dashboardData) {
                ChartComponent.render(this.dashboardData, document.getElementById('chart-mode-toggle')?.checked || false);
                SummaryComponent.render(this.dashboardData);
            }

            // Подтягиваем свежие цены/курсы после фонового обновления на бэкенде
            this.scheduleDashboardSync();
        } catch (e) {
            console.error('Failed to initialize:', e);
            // If token expired, go back to login
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

    // После первой загрузки бэкенд обновляет цены/курсы в фоне (MOEX, ЦБ РФ).
    // Один отложенный перезапрос, чтобы подхватить свежие цены, НО без мерцания:
    // не перерисовываем, если новые данные хуже (например, total_value упал до 0
    // из-за ещё не обновлённых цен). Это убирает эффект «то 0.00, то значения».
    scheduleDashboardSync() {
        if (this._syncTimer) return; // уже запланировано
        const delay = 4000; // мс — ждём, пока фоновое обновление отработает
        this._syncTimer = setTimeout(async () => {
            this._syncTimer = null;
            try {
                const data = await API.getDashboard(this.portfolioId);
                const newTotal = data && data.portfolio ? data.portfolio.total_value : 0;
                const oldTotal = this.dashboardData && this.dashboardData.portfolio
                    ? this.dashboardData.portfolio.total_value : 0;
                // Не перезаписываем хорошие данные нулями (цены ещё не подгрузились)
                if (newTotal > 0 || oldTotal === 0) {
                    this.dashboardData = data;
                    if (!document.getElementById('page-main').classList.contains('hidden')) {
                        this.renderDashboard(data);
                    }
                }
            } catch (e) {
                // игнорируем ошибки фоновой синхронизации
            }
        }, delay);
    },

    renderDashboard(data) {
        // Render all components on main page
        SummaryComponent.render(data);
        ChartComponent.render(data, document.getElementById('chart-mode-toggle')?.checked || false);
        // Positions are now shown on assets page, not main page
    },

    async refreshPrices() {
        try {
            const result = await API.refreshPrices();
            console.log(`Prices refreshed: ${result.updated}`);
            await this.loadDashboard(true);
        } catch (e) {
            console.error('Failed to refresh prices:', e);
        }
    },

    // Метод для сброса кеша при добавлении новой сделки
    async refreshDashboard() {
        this.dashboardData = null;
        await this.loadDashboard(true);
        // Also refresh dividends histogram
        await DividendsHistogram.load(this.portfolioId);
        // Re-render chart and summary with histogram data
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

// Register Service Worker for PWA
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').then((reg) => {
            console.log('✅ SW registered:', reg.scope);
        }).catch((err) => {
            console.log('❌ SW registration failed:', err);
        });
    });
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => App.init());
