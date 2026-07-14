const ChartComponent = {
    chartInstance: null,

    render(data) {
        const positions = data.positions;
        const ctx = document.getElementById('composition-chart');

        if (!ctx) return;

        if (this.chartInstance) {
            this.chartInstance.destroy();
        }

        if (!positions || positions.length === 0) {
            this.chartInstance = null;
            return;
        }

        const labels = positions.map(p => p.name);
        const values = positions.map(p => p.total_value);
        const colors = [
            '#3b82f6', '#22c55e', '#a78bfa', '#f59e0b', '#ef4444',
            '#06b6d4', '#ec4899', '#84cc16', '#f97316', '#8b5cf6',
        ];

        this.chartInstance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors.slice(0, labels.length),
                    borderWidth: 2,
                    borderColor: '#32323e',
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false,
                    },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const pct = ((context.raw / total) * 100).toFixed(1);
                                return ` ${context.label}: ${Utils.formatCurrency(context.raw)} (${pct}%)`;
                            },
                        },
                    },
                },
            },
        });
    },
};