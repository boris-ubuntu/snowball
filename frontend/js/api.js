const API = {
    BASE_URL: () => CONFIG.API_BASE,

    getToken() {
        return localStorage.getItem('auth_token');
    },

    setToken(token) {
        if (token) localStorage.setItem('auth_token', token);
        else localStorage.removeItem('auth_token');
    },

    async request(path, options = {}) {
        const url = this.BASE_URL() + path;
        const headers = { 'Content-Type': 'application/json', ...options.headers };
        const token = this.getToken();
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        const config = {
            headers,
            ...options,
        };
        try {
            const res = await fetch(url, config);
            if (res.status === 401 && !path.includes('/auth/')) {
                // Token expired or invalid - redirect to login
                API.setToken(null);
                if (typeof App !== 'undefined' && App.logout) {
                    App.logout();
                }
                return null;
            }
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `HTTP ${res.status}`);
            }
            if (res.status === 204) return null;
            return await res.json();
        } catch (err) {
            console.error(`API error [${options.method || 'GET'} ${path}]:`, err);
            throw err;
        }
    },

    // --- Lightweight client-side TTL cache (localStorage) ---
    // Used for expensive read endpoints to avoid re-fetching on every render.
    _cacheGet(path, ttlMs) {
        const key = 'api_cache:' + path;
        try {
            const raw = localStorage.getItem(key);
            if (raw) {
                const entry = JSON.parse(raw);
                if (Date.now() - entry.t < ttlMs) {
                    return entry.v;
                }
            }
        } catch (e) { /* ignore cache errors */ }
        return null;
    },

    _cacheSet(path, value) {
        const key = 'api_cache:' + path;
        try {
            localStorage.setItem(key, JSON.stringify({ t: Date.now(), v: value }));
        } catch (e) { /* ignore quota errors */ }
    },

    async cachedGet(path, ttlMs = 60000) {
        const cached = this._cacheGet(path, ttlMs);
        if (cached !== null) return cached;
        const value = await this.request(path);
        if (value !== null) this._cacheSet(path, value);
        return value;
    },

    // Invalidate a cached GET (by exact path) — call after mutations.
    invalidateCache(path) {
        try { localStorage.removeItem('api_cache:' + path); } catch (e) {}
    },

    // Auth
    async login(username, password) {
        const res = await fetch(this.BASE_URL() + '/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Ошибка авторизации');
        }
        return await res.json();
    },

    // Securities search + OFZ loader
    searchSecurities(query) {
        return this.request(`/securities/search?q=${encodeURIComponent(query)}`);
    },
    loadOfzBonds() {
        return this.request('/securities/load-ofz', { method: 'POST' });
    },

    // Securities
    getSecurities() {
        // Securities rarely change within a session — cache for 5 minutes.
        return this.cachedGet('/securities/?limit=1000', 5 * 60 * 1000);
    },
    getSecurity(id) {
        return this.request(`/securities/${id}`);
    },
    refreshSecurityPrice(id) {
        return this.request(`/securities/${id}/refresh-price`, { method: 'POST' });
    },
    createSecurity(data) {
        return this.request('/securities/', { method: 'POST', body: JSON.stringify(data) });
    },
    updateSecurity(id, data) {
        return this.request(`/securities/${id}`, { method: 'PUT', body: JSON.stringify(data) });
    },
    deleteSecurity(id) {
        return this.request(`/securities/${id}`, { method: 'DELETE' });
    },

    // Portfolio
    getDefaultPortfolio() {
        return this.request('/portfolio/default');
    },
    getDashboard(portfolioId) {
        return this.request(`/portfolio/${portfolioId}/dashboard`);
    },
    getPortfolioSecurities(portfolioId) {
        return this.request(`/portfolio/${portfolioId}/securities`);
    },

    // Positions
    getPositions(portfolioId) {
        return this.request(`/portfolio/${portfolioId}/positions`);
    },

    // Transactions
    getTransactions(portfolioId, skip = 0, limit = 10) {
        return this.request(`/portfolio/${portfolioId}/transactions?skip=${skip}&limit=${limit}`);
    },
    createTransaction(portfolioId, data) {
        return this.request(`/portfolio/${portfolioId}/transactions`, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    },

    // Dividends
    getPortfolioDividends(portfolioId, showAll = true, forceRefresh = false) {
        if (forceRefresh) this.invalidateCache(`/portfolio/${portfolioId}/dividends?all=${showAll}&force_refresh=false`);
        return this.request(`/portfolio/${portfolioId}/dividends?all=${showAll}&force_refresh=${forceRefresh}`);
    },
    getPortfolioCoupons(portfolioId, upcomingOnly = false, forceRefresh = false) {
        return this.request(`/portfolio/${portfolioId}/coupons?upcoming=${upcomingOnly}&force_refresh=${forceRefresh}`);
    },
    processAccruals(portfolioId) {
        return this.request(`/portfolio/${portfolioId}/process-accruals`, { method: 'POST' });
    },

    // Update transaction
    updateTransaction(portfolioId, transactionId, data) {
        return this.request(`/portfolio/${portfolioId}/transactions/${transactionId}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    },
    deleteTransaction(portfolioId, transactionId) {
        return this.request(`/portfolio/${portfolioId}/transactions/${transactionId}`, { method: 'DELETE' });
    },

    // Prices
    refreshPrices() {
        return this.request('/portfolio/refresh-prices', { method: 'POST' });
    },

    // Dividends
    getDividends(securityId) {
        const params = securityId ? `?security_id=${securityId}` : '';
        return this.request(`/dividends/${params}`);
    },

    // Exchange Rates (CBR)
    getCbrRates() {
        return this.cachedGet('/rates/cbr', 10 * 60 * 1000);
    },
    refreshCbrRates() {
        this.invalidateCache('/rates/cbr');
        return this.request('/rates/cbr/refresh', { method: 'POST' });
    },

    // Economy Indicators (CBR)
    getEconomyIndicators() {
        return this.cachedGet('/economy/indicators', 10 * 60 * 1000);
    },

    // LQDT projection
    getLqdtProjection(portfolioId) {
        return this.request(`/portfolio/${portfolioId}/lqdt-projection`);
    },
};