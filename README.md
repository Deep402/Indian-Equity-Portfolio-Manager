# Indian-Equity-Portfolio-Manager

A comprehensive portfolio management system for Indian equity investors with broker integration, real-time data, and advanced analytics.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Active-brightgreen)

## 📊 Overview

This project consists of two complementary portfolio management applications:

1. **`new.py`** - Enhanced version with Zerodha Kite and Dhan (Angel Broking) integration
2. **`final2.py`** - Standalone portfolio manager with advanced analytics and visualization

Both applications provide sophisticated tools for tracking Indian equity investments with real-time market data, performance analytics, and broker integration capabilities.

## ✨ Features

### 🔗 Broker Integration
- **Zerodha Kite Connect API** integration with OAuth2 authentication
- **Dhan (Angel Broking)** API support for portfolio synchronization
- Automatic holdings and positions synchronization
- Secure token management

### 📈 Portfolio Management
- Create and manage multiple portfolios
- Add, modify, and remove stocks with complete transaction history
- Undo/Redo functionality for all operations
- Real-time price updates with caching mechanism
- Comprehensive audit logging

### 📊 Analytics & Visualization
- Real-time profit/loss calculations
- Daily performance tracking
- Portfolio allocation charts (pie charts)
- Profit/loss visualization (bar charts)
- Historical performance charts
- Market snapshot with Indian and global indices

### 💾 Data Management
- JSON-based portfolio storage with automatic backups
- Excel export functionality
- Complete audit trail with change history
- Price caching for reduced API calls

### 🎨 User Experience
- Rich terminal interface with color-coded output
- Interactive charts using Plotly
- Responsive design with real-time updates
- Keyboard shortcuts and intuitive navigation

## 🛠️ Installation

### Prerequisites
- Python 3.8+
- pip package manager

### Install Dependencies

```bash
# Core dependencies
pip install pandas numpy yfinance requests pytz

# UI and visualization
pip install rich plotly

# For Zerodha integration (new.py only)
pip install webbrowser
```

### Clone the Repository

```bash
git clone https://github.com/yourusername/indian-equity-portfolio.git
cd indian-equity-portfolio
```

## ⚙️ Configuration

### Broker API Setup

#### Zerodha Kite Connect
1. Register at [Kite Connect](https://kite.trade/)
2. Create an app to get API key and secret
3. Set redirect URL to `http://127.0.0.1:8000/`
4. Update the API credentials in `new.py`:

```python
KITE_API_KEY = "your_api_key_here"
KITE_API_SECRET = "your_api_secret_here"
```

#### Dhan API
1. Get access token from Dhan platform
2. Configure in the application:

```python
DHAN_ACCESS_TOKEN = "your_access_token_here"
```

## 🚀 Usage

### Running the Applications

**Enhanced version with broker integration:**
```bash
python new.py
```

**Standalone portfolio manager:**
```bash
python final2.py
```

### Main Menu Options

1. **Portfolio Management** - Create/delete portfolios
2. **Stock Operations** - Add/edit/remove stocks
3. **Dashboard Views** - Performance analytics
4. **Market Analysis** - Indices & trends
5. **Visualizations** - Charts & graphs
6. **Data Operations** - Export/import
7. **History & Audit** - Change tracking
8. **Exit** - Save & quit

## 📁 File Structure

```
indian-equity-portfolio/
├── new.py                 # Enhanced version with broker integration
├── final2.py              # Standalone portfolio manager
├── portfolios.json        # Portfolio data storage
├── portfolios_backup.json # Automatic backups
├── portfolio_audit.log    # Change history
├── price_cache.json       # Cached price data
├── kite_token.json        # Zerodha authentication tokens
└── README.md              # This file
```

## 🔧 Troubleshooting

### Common Issues

1. **Zerodha Authentication Failed**
   - Check API key and secret
   - Verify redirect URL configuration
   - Ensure internet connectivity

2. **Price Fetching Errors**
   - Check internet connection
   - Verify ticker symbols end with `.NS` for Indian stocks

3. **File Permission Issues**
   - Ensure write permissions in application directory

### Log Files
- Check `portfolio_audit.log` for operation history
- Review console output for error messages
- Emergency backups in `portfolios_backup.json`

## 📈 Market Data Sources

- **Indian Indices**: Nifty 50, Nifty Bank, Sensex
- **Global Indices**: S&P 500, NASDAQ, Dow Jones, FTSE 100
- **Stock Prices**: Yahoo Finance API
- **Real-time Updates**: Automatic refresh every 2 seconds

## 🤝 Contributing

We welcome contributions! Please feel free to submit pull requests or open issues for bugs and feature requests.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This software is provided for educational purposes only. The authors are not responsible for any financial losses incurred through the use of this application. Always verify broker API terms and conditions before use.

**Note**: This application requires active internet connection for real-time data fetching and broker integration. Market data may be delayed by 15-20 minutes during trading hours.

## 🏆 Acknowledgments

- Yahoo Finance for market data API
- Zerodha for Kite Connect API
- Dhan for brokerage API
- Plotly for visualization library
- Rich for terminal formatting

---

**Happy Investing!** 📈💹
