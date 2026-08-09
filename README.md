# 🚀 AutoTrader_AI

### Autonomous Crypto Futures Algorithmic Trading Platform & Real-Time Telemetry Dashboard

**AutoTrader_AI** is an end-to-end algorithmic crypto futures trading platform designed to continuously analyze multiple futures markets, identify high-conviction short-term trading setups, manage position risk, execute trades through exchange APIs, and visualize live trading telemetry through a custom web dashboard.

The system combines **async Python execution, quantitative indicators, exchange API integration, automated risk controls, WebSockets, and real-time monitoring** into a single trading architecture.

> ⚠️ **Disclaimer:** This project is for educational and research purposes. Cryptocurrency futures trading involves substantial risk, and leverage can result in rapid losses. Do not use this system with real funds without extensive testing, validation, exchange sandbox testing, and appropriate risk controls.

---

## ✨ Highlights

* 📊 Multi-pair crypto futures market scanning
* ⚡ Asynchronous, non-blocking trading architecture
* 🧠 Multi-indicator signal confluence
* 📈 Candlestick pattern recognition
* 🎯 Predictive trade-confidence scoring
* 🛡️ Automated position and exposure management
* 📐 ATR-based stop-loss and take-profit management
* 🔒 Break-even protection
* ⏱️ Short-duration scalp management
* 🔗 Exchange API integration
* 📡 Real-time WebSocket telemetry
* 🖥️ Custom trading dashboard
* 💾 Persistent trade and system logging
* 💰 Automated profit-management workflow
* 🧩 Modular architecture for extending strategies and exchanges

---

# 🏗️ System Architecture

```text
                         ┌──────────────────────────┐
                         │     Crypto Exchanges     │
                         │                          │
                         │ CoinDCX / Binance /     │
                         │ Bybit / Other APIs      │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │   Market Data Layer     │
                         │                          │
                         │ REST APIs + WebSockets  │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                    ┌────────────────────────────────────┐
                    │       Quantitative Engine           │
                    │                                    │
                    │ RSI │ MACD │ EMA │ ADX │ Volume    │
                    │ ATR │ Patterns │ Volatility       │
                    └────────────────┬───────────────────┘
                                     │
                                     ▼
                         ┌──────────────────────────┐
                         │    Signal Generator     │
                         │                          │
                         │ Confluence Analysis     │
                         │ Confidence / Score      │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │     Risk Management      │
                         │                          │
                         │ Position Sizing         │
                         │ Exposure Limits         │
                         │ Correlation Guards      │
                         │ Stop / TP Management     │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │    Execution Engine      │
                         │                          │
                         │ Order Creation           │
                         │ Position Monitoring      │
                         │ Exit Management          │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │   Telemetry / Database   │
                         │                          │
                         │ SQLite + WebSockets     │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │   Real-Time Dashboard    │
                         │                          │
                         │ Positions / P&L         │
                         │ Signals / Metrics        │
                         │ System Status            │
                         └──────────────────────────┘
```

---

# 🛠️ Technology Stack

| Component               | Technology              |
| ----------------------- | ----------------------- |
| Language                | Python 3.14             |
| Async Runtime           | AsyncIO                 |
| API Framework           | FastAPI                 |
| ASGI Server             | Uvicorn                 |
| Exchange Integration    | CoinDCX API             |
| Multi-Exchange Support  | CCXT                    |
| Numerical Computing     | NumPy                   |
| Data Analysis           | Pandas                  |
| Database                | SQLite3                 |
| Real-Time Communication | WebSockets              |
| Frontend                | HTML5, CSS3, JavaScript |
| UI Design               | Glassmorphism           |
| Authentication          | HMAC-SHA256 API signing |

---

# 🧠 Quantitative Signal Engine

AutoTrader_AI uses multiple technical and market-structure signals rather than relying on a single indicator.

### Indicators

* RSI
* MACD
* EMA crossovers
* ADX
* ATR
* Volume analysis
* Volatility measurements

### Pattern Recognition

The strategy layer can identify patterns such as:

* Bullish/Bearish Engulfing
* Hammer
* Reversal formations
* Volatility squeeze conditions
* Volume expansion
* Trend-strength confirmation

Signals are combined into a **confluence-based scoring system** instead of triggering trades from a single indicator.

Conceptually:

```text
Market Data
     │
     ├── RSI
     ├── MACD
     ├── EMA
     ├── ADX
     ├── ATR
     ├── Volume
     └── Candle Patterns
             │
             ▼
      Confluence Engine
             │
             ▼
      Signal Confidence
             │
       ┌─────┴─────┐
       │           │
     LONG         SHORT
       │           │
       └─────┬─────┘
             ▼
       Risk Validation
             │
             ▼
        Order Engine
```

---

# ⚡ Async Trading Engine

The application is built around Python's asynchronous execution model.

`asyncio` allows market-data processing, position monitoring, API communication, telemetry, and dashboard updates to operate concurrently without relying on a blocking execution flow.

Example architecture:

```text
Async Event Loop
│
├── Market Scanner
├── Signal Engine
├── Position Monitor
├── Risk Manager
├── Order Executor
├── WebSocket Telemetry
├── Database Logger
└── Scheduler
```

The system is designed for **low-latency application-level execution**, but the project should not be interpreted as exchange-level or institutional HFT infrastructure.

Actual execution latency depends on:

* Internet connection
* Exchange API latency
* Exchange matching engine
* Server location
* Network congestion
* API rate limits
* Market conditions

---

# 🎯 Trade Management

The execution layer supports automated trade lifecycle management.

### Entry

Before entering a position, the system evaluates:

```text
Market Conditions
       ↓
Indicator Confluence
       ↓
Pattern Confirmation
       ↓
Volume / Trend Validation
       ↓
Risk Validation
       ↓
Position Entry
```

### Position Management

Open positions can be managed using:

* ATR-based stop loss
* ATR-based take profit
* Break-even protection
* Maximum holding duration
* Scalp timeout logic
* Position monitoring
* Automated exit conditions

---

# 🛡️ Risk Management

Risk management is treated as a first-class component of the architecture.

The system includes mechanisms for:

### Position Allocation

Available capital is distributed across permitted trading slots rather than allowing unlimited simultaneous exposure.

### Sector Exposure

Assets can be grouped into categories such as:

```text
Majors
Memecoins
L1 / L2
Other
```

Exposure limits can then be applied to each category.

Example:

```text
Maximum positions per sector = 2
```

This reduces the possibility of opening many highly correlated positions simultaneously.

### Risk Controls

```text
Signal
  ↓
Position Size Check
  ↓
Exposure Check
  ↓
Sector Correlation Check
  ↓
Risk/Reward Validation
  ↓
Order
```

---

# 📡 Real-Time Telemetry

The platform exposes live system information through **FastAPI and WebSockets**.

The dashboard can display information such as:

* Current positions
* Entry price
* Current price
* Unrealized P&L
* Realized P&L
* Trading signals
* Confidence scores
* Account information
* System status
* Market scanning activity
* Execution events
* Error logs

The goal is to provide a single real-time interface for observing the trading engine.

---

# 🖥️ Dashboard

The frontend uses:

* HTML5
* Vanilla CSS3
* ES6+ JavaScript
* WebSocket communication

The interface follows a modern **glassmorphism-inspired trading terminal design**.

```text
┌────────────────────────────────────────────────────┐
│                 AUTOTRADER_AI                      │
├────────────────────────────────────────────────────┤
│ Balance     P&L       Positions     Win Rate       │
├────────────────────────────────────────────────────┤
│                                                    │
│              LIVE MARKET TELEMETRY                │
│                                                    │
├────────────────────────────────────────────────────┤
│ Active Trades                                      │
│                                                    │
│ BTC     LONG     Entry     Current     P&L         │
│ ETH     SHORT    Entry     Current     P&L         │
│ SOL     LONG     Entry     Current     P&L         │
├────────────────────────────────────────────────────┤
│ System Events / Execution Logs                     │
└────────────────────────────────────────────────────┘
```

---

# 💾 Database

SQLite is used for local persistence and system logging.

Typical information can include:

```text
Trades
Positions
Signals
Execution Events
Performance Metrics
System Logs
```

The database layer is designed to keep trading data available for analysis and debugging.

---

# 💰 Automated Profit Management

The system includes a scheduled profit-management workflow.

At a configured daily time, realized futures profits can be evaluated and transferred according to the configured capital-management rules.

This feature is designed to separate:

```text
Trading Capital
        +
Realized Profit
        ↓
Capital Management
```

> The transfer logic should be thoroughly tested in a sandbox/test environment before enabling it for live funds.

---

# 🔌 Exchange Integration

The architecture supports exchange connectivity through:

### CoinDCX

Native API integration with authenticated requests using:

```text
HMAC-SHA256
```

### CCXT

The architecture can also interface with supported exchanges through **CCXT**, making it easier to extend the system to additional exchanges.

---

# 📁 Project Structure

A typical project structure:

```text
AutoTrader_AI/
│
├── main.py
├── config.py
├── ai_signal_engine.py
├── risk_engine.py
├── position_manager.py
├── market_scanner.py
├── wallet_manager.py
├── exchange_adapter.py
├── database.py
├── web_dashboard.py
├── render.yaml
├── requirements.txt
├── static/
│   ├── index.html
│   ├── styles.css
│   └── app.js
└── tests/
    └── test_trading_bot.py
```

---

# 🚀 Getting Started

## 1. Clone the repository

```bash
git clone https://github.com/HarshBhavsar25/Autotrader__AI.git

cd Autotrader__AI
```

## 2. Create a virtual environment

### Windows

```bash
python -m venv venv

venv\Scripts\activate
```

### Linux / macOS

```bash
python3 -m venv venv

source venv/bin/activate
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

## 4. Configure environment variables

Create a `.env` file:

```env
COINDCX_API_KEY=your_api_key
COINDCX_API_SECRET=your_api_secret

TRADING_MODE=paper
EXCHANGE_NAME=coindcx
```

**Never commit real API credentials to GitHub.**

Add the following to `.gitignore`:

```gitignore
.env
venv/
__pycache__/
*.db
*.sqlite
logs/
```

## 5. Start the application

```bash
python main.py
```

The FastAPI dashboard will typically be available at:

```text
http://localhost:8000
```

---

# 🧪 Recommended Testing Workflow

Before using real capital:

```text
Development
     ↓
Unit Tests
     ↓
Backtesting
     ↓
Paper Trading
     ↓
Exchange Testnet
     ↓
Small Capital
     ↓
Production
```

Do not skip directly from development to leveraged live trading.

---

# 📊 Performance Evaluation

Important metrics to evaluate include:

* Total Return
* Maximum Drawdown
* Sharpe Ratio
* Sortino Ratio
* Win Rate
* Profit Factor
* Average Win
* Average Loss
* Expectancy
* Average Trade Duration
* Maximum Consecutive Losses
* Fees
* Slippage
* Funding Costs

A strategy should be evaluated after accounting for **fees, slippage, funding rates, latency, and failed orders**, rather than relying only on raw signal accuracy.

---

# 🔐 Security

API credentials should be stored exclusively through environment variables or a secure secrets manager.

Recommended exchange permissions:

```text
✅ Read Account
✅ Read Positions
✅ Trading — only when required
❌ Withdrawals
```

Never enable withdrawal permissions for trading-bot API keys unless absolutely necessary.

---

# 🗺️ Roadmap

### Current

* [x] Async trading engine
* [x] Multi-indicator strategy
* [x] Pattern recognition
* [x] Risk management
* [x] Exchange API integration
* [x] WebSocket telemetry
* [x] Real-time dashboard
* [x] SQLite persistence

### Planned

* [ ] Comprehensive backtesting engine
* [ ] Walk-forward optimization
* [ ] Monte Carlo strategy analysis
* [ ] Advanced portfolio correlation matrix
* [ ] Funding-rate analysis
* [ ] Order-book imbalance
* [ ] Market microstructure signals
* [ ] Advanced execution algorithms
* [ ] Prometheus/Grafana monitoring
* [ ] PostgreSQL production database
* [ ] Docker deployment
* [ ] Automated strategy evaluation
* [ ] ML-based signal models
* [ ] Advanced portfolio-level risk engine

---

# ⚠️ Risk Disclaimer

AutoTrader_AI is an experimental algorithmic trading project.

Cryptocurrency futures are highly volatile financial instruments. Leverage can significantly amplify both gains and losses. Technical indicators and algorithmic strategies do not guarantee profitable trades.

The authors and contributors are not responsible for financial losses resulting from the use of this software.

**Use at your own risk.**

---

# 🤝 Contributing

Contributions, ideas, bug reports, and strategy research are welcome.

1. Fork the repository
2. Create a feature branch

```bash
git checkout -b feature/new-strategy
```

3. Commit your changes

```bash
git commit -m "Add new strategy"
```

4. Push the branch

```bash
git push origin feature/new-strategy
```

5. Open a Pull Request

---

# 📜 License

This project is licensed under the MIT License.

---

# 👨‍💻 Author

**Harshkumar Ravindra Bhavsar**

Built as an engineering and quantitative research project exploring:

* Algorithmic Trading
* Quantitative Finance
* Async Python
* Financial APIs
* Real-Time Systems
* Risk Management
* WebSocket Architecture
* Automated Execution

---

## ⭐ If you find this project interesting

Give the repository a ⭐ and feel free to explore, contribute, or suggest improvements.

**Built with Python • FastAPI • AsyncIO • NumPy • Pandas • WebSockets**
