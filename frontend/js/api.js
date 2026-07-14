const API = {
    async request(path, options = {}) {
        const url = CONFIG.API_BASE + path;
        const config = {
            headers: { 'Content-Type': 'application/json', ...options.headers },
            ...options,
        };
        try {
            const res = await fetch(url, config);
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

    // Securities search + OFZ loader
    searchSecurities(query) {
        return this.request(`/securities/search?q=${encodeURIComponent(query)}`);
    },
    loadOfzBonds() {
        return this.request('/securities/load-ofz', { method: 'POST' });
    },

    // Securities
    getSecurities() {
        return this.request('/securities/?limit=1000');
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

    // Dividends - ИСПРАВЛЕНО
    getPortfolioDividends(portfolioId, showAll = true, forceRefresh = false) {
        return this.request(`/portfolio/${portfolioId}/dividends?all=${showAll}&force_refresh=${forceRefresh}`);
    },
    getPortfolioCoupons(portfolioId, upcomingOnly = false, forceRefresh = false) {
        return this.request(`/portfolio/${portfolioId}/coupons?upcoming=${upcomingOnly}&force_refresh=${forceRefresh}`);
    },
    processAccruals(portfolioId) {
        return this.request(`/portfolio/${portfolioId}/process-accruals`, { method: 'POST' });
    },

    // Delete transaction
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
        return this.request('/rates/cbr');
    },
    refreshCbrRates() {
        return this.request('/rates/cbr/refresh', { method: 'POST' });
    },
};
