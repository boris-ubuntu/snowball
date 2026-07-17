const ChartComponent = {
    chartInstance: null,
    averageMonthlyIncome: '0 ₽',
    averageMonthlyIncomeRaw: 0,

    render(data, byClass = false) {
        const positions = data.positions || [];
        const ctx = document.getElementById('composition-chart');

        if (!ctx) return;

        if (this.chartInstance) {
            this.chartInstance.destroy();
        }

        const sorted = [...positions].sort((a, b) => b.total_value - a.total_value);
        const total = sorted.reduce((s, p) => s + p.total_value, 0);

        if (total <= 0 || sorted.length === 0) {
            this.chartInstance = null;
            return;
        }

        let labels, values;

        if (byClass) {
            // Group by asset class: акции, офз, фонды, валюта
            const classMap = {
                'Акции': ['stock'],
                'ОФЗ': ['ofz', 'bond'],
                'Фонды': ['etf'],
                'Валюта': ['currency'],
            };
            const classTotals = { 'Акции': 0, 'ОФЗ': 0, 'Фонды': 0, 'Валюта': 0 };
            for (const p of sorted) {
                let found = false;
                for (const [cls, types] of Object.entries(classMap)) {
                    if (types.includes(p.security_type)) {
                        classTotals[cls] += p.total_value;
                        found = true;
                        break;
                    }
                }
                if (!found) classTotals['Прочее'] = (classTotals['Прочее'] || 0) + p.total_value;
            }
            labels = [];
            values = [];
            for (const [cls, val] of Object.entries(classTotals)) {
                if (val > 0) {
                    labels.push(cls);
                    values.push(val);
                }
            }
        } else {
            // Filter: only positions >= 5%, group rest into "Прочие"
            const main = sorted.filter(p => (p.total_value / total) >= 0.05);
            const other = sorted.filter(p => (p.total_value / total) < 0.05);
            const otherTotal = other.reduce((s, p) => s + p.total_value, 0);

            // Акции и ОФЗ показываем по названию, валюту и фонды/ETF - по тикеру
            labels = main.map(p => {
                if (p.security_type === 'currency' || p.security_type === 'etf') {
                    return p.ticker;
                }
                return p.name;
            });
            values = main.map(p => p.total_value);
            if (otherTotal > 0) {
                labels.push('Прочие');
                values.push(otherTotal);
            }
        }

        const colors = [
            '#53909d', '#56cfe1', '#5e60ce', '#6930c3', '#2acbcb',
            '#4ea8de', '#72efdd', '#64dfdf', '#80ffdb', '#7400b8',
        ];

        // Calculate average monthly income from histogram data (total next 12 months / 12)
        // Apply 0.87 tax coefficient (13% НДФЛ)
        this.averageMonthlyIncome = '0 ₽';
        this.averageMonthlyIncomeRaw = 0;
        if (typeof DividendsHistogram !== 'undefined' && DividendsHistogram.lastMonthlyData) {
            const totalNext12Months = DividendsHistogram.lastMonthlyData.reduce((sum, m) => sum + m.total, 0);
            if (totalNext12Months > 0) {
                const avg = (totalNext12Months / 12) * 0.87;
                this.averageMonthlyIncomeRaw = avg;
                // Round to integer and format without decimals
                this.averageMonthlyIncome = Math.round(avg).toLocaleString('ru-RU') + ' ₽';
            }
        }

        const self = this;

        this.chartInstance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors.slice(0, labels.length),
                    borderWidth: 2,
                    borderColor: '#32323e',
                    hoverOffset: 8,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: window.innerWidth < 640 ? '55%' : '62%',
                layout: {
                    padding: 6,
                },
                plugins: {
                    legend: {
                        display: false,
                    },
                    tooltip: {
                        bodyFont: { family: 'Segoe UI, Tahoma, sans-serif', size: 13 },
                        callbacks: {
                            label: function (context) {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const pct = ((context.raw / total) * 100).toFixed(1);
                                return ' ' + context.label + ': ' + Utils.formatCurrency(context.raw) + ' (' + pct + '%)';
                            },
                        },
                    },
                },
                onClick: (event, elements, chart) => {
                    // Click on center area: show economy modal
                    if (!chart) return;
                    // If elements array is empty -> clicked on empty space (center hole or outside)
                    if (elements.length === 0) {
                        self.showEconomyModal();
                        return;
                    }
                    // Also check if click is inside the inner radius (center hole)
                    const rect = chart.canvas.getBoundingClientRect();
                    const x = event.clientX - rect.left;
                    const y = event.clientY - rect.top;
                    const chartArea = chart.chartArea;
                    if (!chartArea) return;
                    const centerX = (chartArea.left + chartArea.right) / 2;
                    const centerY = (chartArea.top + chartArea.bottom) / 2;
                    const meta = chart.getDatasetMeta(0);
                    if (!meta.data || meta.data.length === 0) return;
                    const innerRadius = meta.data[0].innerRadius;
                    const dist = Math.sqrt((x - centerX) ** 2 + (y - centerY) ** 2);
                    if (dist <= innerRadius) {
                        self.showEconomyModal();
                    }
                },
            },
            plugins: [{
                id: 'innerLabels',
                afterDraw(chart) {
                    const { ctx, data, chartArea } = chart;
                    const meta = chart.getDatasetMeta(0);
                    if (!meta.data || meta.data.length === 0) return;

                    const total = data.datasets[0].data.reduce((a, b) => a + b, 0);
                    const centerX = chartArea.left + chartArea.width / 2;
                    const centerY = chartArea.top + chartArea.height / 2;
                    const outerRadius = meta.data[0].outerRadius;
                    const innerRadius = meta.data[0].innerRadius;

                    const isNarrow = chart.width < 500;
                    const nameFont = isNarrow ? 11 : 13;
                    const pctFont = isNarrow ? 10 : 12;

                    ctx.save();
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';

                    for (let i = 0; i < data.labels.length; i++) {
                        const arc = meta.data[i];
                        const angle = arc.endAngle - arc.startAngle;
                        // Слишком маленькие сегменты не подписываем
                        if (angle < 0.18) continue;

                        const midAngle = arc.startAngle + angle / 2;
                        const r = (innerRadius + outerRadius) / 2;
                        const x = centerX + Math.cos(midAngle) * r;
                        const y = centerY + Math.sin(midAngle) * r;
                        const value = data.datasets[0].data[i];
                        const pct = ((value / total) * 100).toFixed(1);

                        ctx.fillStyle = '#ffffff';
                        ctx.shadowColor = 'rgba(0,0,0,0.65)';
                        ctx.shadowBlur = 3;

                        ctx.font = 'bold ' + nameFont + 'px Segoe UI, Tahoma, sans-serif';
                        ctx.fillText(data.labels[i], x, y - (isNarrow ? 7 : 8));

                        ctx.font = pctFont + 'px Segoe UI, Tahoma, sans-serif';
                        ctx.fillStyle = 'rgba(255,255,255,0.85)';
                        ctx.fillText(pct + '%', x, y + (isNarrow ? 6 : 7));
                    }

                    ctx.restore();
                },
            }, {
                id: 'centerText',
                beforeDraw: function (chart) {
                    const width = chart.width;
                    const height = chart.height;
                    const ctx = chart.ctx;
                    ctx.restore();
                    // Fixed font size to match original 320px height (320/160 = 2.0em)
                    const fontSize = '2.0';
                    ctx.font = 'bold ' + fontSize + 'em Segoe UI, Tahoma, sans-serif';
                    ctx.textBaseline = 'middle';
                    // Show average monthly income over next 12 months (integer)
                    const text = ChartComponent.averageMonthlyIncome || '0 ₽';
                    const textY = height / 2 - 8;
                    ctx.fillStyle = '#e2e8f0';
                    ctx.textAlign = 'center';
                    ctx.fillText(text, width / 2, textY);

                    // Sub-label
                    ctx.font = (parseFloat(fontSize) * 0.45) + 'em Segoe UI, Tahoma, sans-serif';
                    ctx.fillStyle = 'rgba(255,255,255,0.6)';
                    ctx.fillText('в среднем в месяц', width / 2, textY + 18);
                    ctx.save();
                },
            }],
        });
    },

    async showEconomyModal() {
        const overlay = document.getElementById('economy-modal-overlay');
        if (!overlay) return;

        try {
            const data = await API.getEconomyIndicators();
            const keyRate = data.key_rate || 0;
            const inflation = data.inflation_rate || 0;

            // Get passive yield from summary card
            const accrualsEl = document.getElementById('total-accruals');
            let passiveYield = 0;
            if (accrualsEl) {
                const text = accrualsEl.textContent;
                const match = text.match(/([\d.]+)/);
                if (match) {
                    passiveYield = parseFloat(match[1]);
                }
            }

            // New formula:
            // inflation / passiveYield = ratio to keep in capital
            // (1 - ratio) * total annual income / 12 = monthly spendable
            const monthlyIncome = this.averageMonthlyIncomeRaw;
            const annualIncome = monthlyIncome * 12;
            let spendable = 0;
            if (passiveYield > 0 && annualIncome > 0) {
                const keepRatio = inflation / passiveYield;
                const spendRatio = Math.max(0, 1 - keepRatio);
                spendable = (spendRatio * annualIncome) / 12;
            }

            // Backend returns values in percent (e.g. 14.25), formatPercent outputs them as-is
            document.getElementById('economy-key-rate').textContent = Utils.formatPercent(keyRate);
            document.getElementById('economy-inflation').textContent = Utils.formatPercent(inflation);
            document.getElementById('economy-passive-yield').textContent = Utils.formatPercent(passiveYield);

            const spendableEl = document.getElementById('economy-spendable');
            spendableEl.textContent = Utils.formatCurrency(Math.round(spendable));
            spendableEl.className = 'economy-spendable-value';
        } catch (e) {
            console.error('Failed to load economy indicators:', e);
        }

        overlay.classList.remove('hidden');
    },
};