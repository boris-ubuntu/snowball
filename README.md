# InvestMon€y (Snowball)

Портфель ценных бумаг — веб-приложение для управления инвестиционным портфелем, отслеживания доходности, дивидендов и купонных выплат.

## Возможности

- 📊 **Дашборд** — общая стоимость портфеля, прибыль, пассивный доход, доходность
- 💼 **Портфель** — круговая диаграмма состава портфеля (акции, ОФЗ, валюта)
- 📈 **Предстоящие выплаты** — гистограмма дивидендов, купонов и LQDT начислений на 12 месяцев
- 💰 **Пассивный доход** — расчёт ожидаемого годового дохода и доходности
- 🔄 **Автоначисление** — автоматический учёт дивидендов и купонов при наступлении даты
- 🏦 **Экономические индикаторы** — ключевая ставка ЦБ, инфляция, расчёт "сколько можно тратить"
- 🔐 **JWT-аутентификация** — защита данных паролем

## Технологии

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, PostgreSQL, JWT
- **Frontend:** Vanilla JS, Chart.js, CSS3
- **Deploy:** Docker, Render

## Локальный запуск

### Предварительные требования
- Docker и Docker Compose

### Запуск

```bash
git clone https://github.com/boris-ubuntu/snowball.git
cd snowball
docker compose up -d
```

Приложение будет доступно по адресу: http://localhost:8000

### Учётные данные для входа
- Логин: `boris`
- Пароль: `Maelstormer5`

## Разработка

### Структура проекта

```
snowball/
├── backend/
│   ├── app/
│   │   ├── routers/        # API endpoints
│   │   ├── services/       # Business logic (MOEX, CBR, LQDT, etc.)
│   │   ├── auth.py         # JWT authentication
│   │   ├── config.py       # Settings
│   │   ├── crud.py         # Database operations
│   │   ├── database.py     # DB connection
│   │   ├── models.py       # SQLAlchemy models
│   │   └── main.py         # FastAPI app
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── api.js          # API client
│       ├── app.js          # Main app logic, auth
│       ├── config.js       # Configuration
│       ├── utils.js        # Utilities
│       └── components/     # UI components
├── docker-compose.yml
├── render.yaml
└── .env.example
```

## Деплой на Render

1. Создайте форк/клон репозитория на GitHub
2. Подключите репозиторий к Render
3. Render автоматически определит `render.yaml` и создаст сервисы
4. После деплоя задайте переменные окружения:
   - `SECRET_KEY` — случайная строка для JWT (генерируется автоматически)
   - `DB_PASS` — пароль БД (устанавливается автоматически)

## API Endpoints

### Auth
- `POST /api/auth/login` — вход, получение JWT-токена

### Portfolio
- `GET /api/portfolio/default` — получить портфель по умолчанию
- `GET /api/portfolio/{id}/dashboard` — дашборд портфеля
- `GET /api/portfolio/{id}/positions` — позиции
- `GET /api/portfolio/{id}/transactions` — операции
- `POST /api/portfolio/{id}/transactions` — создать операцию
- `PUT /api/portfolio/{id}/transactions/{tx_id}` — обновить операцию
- `DELETE /api/portfolio/{id}/transactions/{tx_id}` — удалить операцию
- `GET /api/portfolio/{id}/dividends` — дивиденды
- `GET /api/portfolio/{id}/coupons` — купоны
- `GET /api/portfolio/{id}/lqdt-projection` — прогноз LQDT

### Economy
- `GET /api/economy/indicators` — ключевая ставка и инфляция

### Health
- `GET /api/health` — проверка статуса

## Лицензия

MIT