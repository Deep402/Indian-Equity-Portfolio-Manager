import sys
import random
import os
import json
import time
from queue import Queue
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import threading
import warnings
import matplotlib.dates as mdates
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QPushButton, QListWidget, QStackedWidget, QLineEdit,
                            QTableWidget, QTableWidgetItem, QComboBox, QSpinBox, 
                            QDoubleSpinBox, QDateEdit, QMessageBox, QFileDialog, QDialog,
                            QTabWidget, QSizePolicy, QFrame, QHeaderView, QTextEdit,
                            QInputDialog, QFontDialog, QLabel)  # Added QInputDialog here
from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QColor, QFont, QIcon
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

# Suppress warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=UserWarning)

plt.style.use('dark_background')

class Worker(QThread):
    data_fetched = pyqtSignal(dict)
    finished_signal = pyqtSignal()
    
    def __init__(self, tickers, parent=None):
        super().__init__(parent)
        self.tickers = tickers
        self._is_running = True
        self.fetcher = MarketDataFetcher()
        
    def run(self):
        def on_batch_complete(prices):
            if self._is_running:
                self.data_fetched.emit(prices)
            self.finished_signal.emit()
        
        self.fetcher.fetch_batch(self.tickers, on_batch_complete)
        
    def stop(self):
        self._is_running = False
        self.quit()
        self.wait(1000)

class TechnicalAnalyzer:
    def __init__(self):
        self.history_days = 90  # Default lookback period
        
    def detect_breakouts(self, historical_data):
        """Detect breakouts from consolidation patterns"""
        results = {
            'resistance_breakout': False,
            'support_breakout': False,
            'consolidation_range': None,
            'breakout_price': None,
            'breakout_volume': None
        }
        
        if len(historical_data) < 20:  # Need at least 20 days of data
            return results
            
        closes = historical_data['Close'].values
        highs = historical_data['High'].values
        lows = historical_data['Low'].values
        volumes = historical_data['Volume'].values
        
        # Calculate recent price range (last 20 days)
        recent_high = highs[-20:].max()
        recent_low = lows[-20:].min()
        range_size = recent_high - recent_low
        
        # Check if price was in consolidation (small range)
        if range_size < 0.05 * recent_high:  # Less than 5% range
            current_close = closes[-1]
            current_volume = volumes[-1]
            avg_volume = volumes[-20:].mean()
            
            # Resistance breakout
            if current_close > recent_high and current_volume > 1.5 * avg_volume:
                results['resistance_breakout'] = True
                results['breakout_price'] = recent_high
                results['breakout_volume'] = current_volume
                results['consolidation_range'] = (recent_low, recent_high)
            
            # Support breakout
            elif current_close < recent_low and current_volume > 1.5 * avg_volume:
                results['support_breakout'] = True
                results['breakout_price'] = recent_low
                results['breakout_volume'] = current_volume
                results['consolidation_range'] = (recent_low, recent_high)
                
        return results
    
    def identify_support_resistance(self, historical_data):
        """Identify key support and resistance levels"""
        levels = []
        closes = historical_data['Close'].values
        highs = historical_data['High'].values
        lows = historical_data['Low'].values
        
        # Look for areas where price reversed multiple times
        for i in range(2, len(highs)-2):
            if highs[i] == highs[i-1:i+2].max() and highs[i] > highs[i-2] and highs[i] > highs[i+2]:
                levels.append({'price': highs[i], 'type': 'resistance'})
            elif lows[i] == lows[i-1:i+2].min() and lows[i] < lows[i-2] and lows[i] < lows[i+2]:
                levels.append({'price': lows[i], 'type': 'support'})
        
        # Consolidate nearby levels
        consolidated = []
        tolerance = 0.01 * closes[-1]  # 1% tolerance
        
        for level in sorted(levels, key=lambda x: x['price']):
            if not consolidated:
                consolidated.append(level)
            else:
                last = consolidated[-1]
                if abs(level['price'] - last['price']) <= tolerance and level['type'] == last['type']:
                    # Average the nearby levels
                    last['price'] = (last['price'] + level['price']) / 2
                else:
                    consolidated.append(level)
        
        return consolidated
    
    def detect_candlestick_patterns(self, historical_data):
        """Detect common candlestick patterns"""
        patterns = []
        closes = historical_data['Close'].values
        opens = historical_data['Open'].values
        highs = historical_data['High'].values
        lows = historical_data['Low'].values
        
        # Need at least 3 days for most patterns
        if len(closes) < 3:
            return patterns
            
        # Check for common patterns
        current_close = closes[-1]
        current_open = opens[-1]
        current_high = highs[-1]
        current_low = lows[-1]
        
        prev_close = closes[-2]
        prev_open = opens[-2]
        prev_high = highs[-2]
        prev_low = lows[-2]
        
        # Bullish Engulfing
        if (prev_close < prev_open and 
            current_open < prev_close and 
            current_close > prev_open):
            patterns.append('bullish_engulfing')
            
        # Bearish Engulfing
        elif (prev_close > prev_open and 
              current_open > prev_close and 
              current_close < prev_open):
            patterns.append('bearish_engulfing')
            
        # Hammer
        body = abs(current_close - current_open)
        lower_shadow = min(current_open, current_close) - current_low
        upper_shadow = current_high - max(current_open, current_close)
        
        if (lower_shadow > 2 * body and 
            upper_shadow < body and 
            current_close > current_open):
            patterns.append('hammer')
            
        # Shooting Star
        if (upper_shadow > 2 * body and 
            lower_shadow < body and 
            current_close < current_open):
            patterns.append('shooting_star')
            
        return patterns
    
    def moving_average_crossovers(self, historical_data):
        """Detect moving average crossovers"""
        closes = historical_data['Close'].values
        
        if len(closes) < 50:  # Need enough data for MA calculations
            return None
            
        # Calculate moving averages
        ma_short = sum(closes[-20:]) / 20  # 20-day MA
        ma_long = sum(closes[-50:]) / 50    # 50-day MA
        
        prev_ma_short = sum(closes[-21:-1]) / 20
        prev_ma_long = sum(closes[-51:-1]) / 50
        
        # Check for crossovers
        if prev_ma_short < prev_ma_long and ma_short > ma_long:
            return 'golden_cross'
        elif prev_ma_short > prev_ma_long and ma_short < ma_long:
            return 'death_cross'
        
        return None

class TechnicalAnalysisWorker(QThread):
    # Define all signals at class level
    analysis_complete = pyqtSignal(dict)
    finished_signal = pyqtSignal()
    
    def __init__(self, symbol, timeframe, parent=None):
        super().__init__(parent)
        self.symbol = symbol
        self.timeframe = timeframe
        self._is_running = True
        
    def run(self):
        try:
            if not self._is_running:
                self.finished_signal.emit()
                return
                
            # Fetch historical data
            stock = yf.Ticker(self.symbol)
            hist = stock.history(period="6mo", interval=self.timeframe)
            
            if hist.empty:
                if self._is_running:
                    self.analysis_complete.emit({
                        'error': f"No data found for {self.symbol}"
                    })
                self.finished_signal.emit()
                return
                
            # Run technical analysis
            analyzer = TechnicalAnalyzer()
            
            analysis = {
                'breakouts': analyzer.detect_breakouts(hist),
                'support_resistance': analyzer.identify_support_resistance(hist),
                'candlestick_patterns': analyzer.detect_candlestick_patterns(hist),
                'ma_crossover': analyzer.moving_average_crossovers(hist)
            }
            
            if self._is_running:
                self.analysis_complete.emit({
                    'symbol': self.symbol,
                    'data': hist,
                    'analysis': analysis
                })
                
        except Exception as e:
            if self._is_running:
                self.analysis_complete.emit({
                    'error': f"Error analyzing {self.symbol}: {str(e)}"
                })
        finally:
            self.finished_signal.emit()
    
    def stop(self):
        self._is_running = False
        self.quit()
        self.wait(1000)  # Wait up to 1 second for thread to finish

import time
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import threading
from queue import Queue

class MarketDataFetcher:
    def __init__(self):
        self.cache = {}
        self.cache_duration = timedelta(minutes=15)  # Cache data for 15 minutes
        self.request_queue = Queue()
        self.rate_limit_delay = 1.0  # 1 second between requests
        self.last_request_time = None
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()

    def _process_queue(self):
        while True:
            ticker, callback = self.request_queue.get()
            try:
                # Enforce rate limiting
                if self.last_request_time:
                    elapsed = time.time() - self.last_request_time
                    if elapsed < self.rate_limit_delay:
                        time.sleep(self.rate_limit_delay - elapsed)
                
                # Check cache first
                if ticker in self.cache:
                    cached_data, timestamp = self.cache[ticker]
                    if datetime.now() - timestamp < self.cache_duration:
                        callback(ticker, cached_data)
                        continue
                
                # Fetch fresh data
                self.last_request_time = time.time()
                stock = yf.Ticker(ticker)
                hist = stock.history(period="1d")
                
                if not hist.empty:
                    price = hist['Close'].iloc[-1]
                    self.cache[ticker] = (price, datetime.now())
                    callback(ticker, price)
                else:
                    callback(ticker, None)
                    
            except Exception as e:
                print(f"Error fetching {ticker}: {str(e)}")
                callback(ticker, None)
            finally:
                self.request_queue.task_done()

    def fetch_price(self, ticker, callback):
        """Request price data for a ticker, callback will be called with (ticker, price)"""
        self.request_queue.put((ticker, callback))

    def fetch_batch(self, tickers, callback):
        """Request prices for multiple tickers, callback will be called with {ticker: price}"""
        results = {}
        remaining = len(tickers)
        
        def batch_callback(ticker, price):
            nonlocal remaining
            results[ticker] = price
            remaining -= 1
            if remaining == 0:
                callback(results)
        
        for ticker in tickers:
            self.fetch_price(ticker, batch_callback)

class MarketDataWorker(QThread):
    data_fetched = pyqtSignal(dict)
    finished_signal = pyqtSignal()
    
    def __init__(self, indices, parent=None):
        super().__init__(parent)
        self.indices = indices
        self._is_running = True
        
    def run(self):
        results = {}
        for name, ticker in self.indices.items():
            if not self._is_running:
                break
            try:
                # Add delay between requests to avoid rate limiting
                time.sleep(1)  # 1 second delay between requests
                
                index = yf.Ticker(ticker)
                hist = index.history(period="2d")
                
                if len(hist) >= 2:
                    current = hist['Close'].iloc[-1]
                    prev_close = hist['Close'].iloc[-2]
                    change = current - prev_close
                    pct_change = (change / prev_close) * 100
                    
                    results[name] = {
                        'Current': current,
                        'Change': change,
                        '% Change': pct_change,
                        'Previous Close': prev_close,
                        'Market Hours': '09:15-15:30 IST' if '^NSE' in ticker else '09:30-16:00 ET',
                        'Status': "Open" if self.is_market_open(ticker) else "Closed"
                    }
            except Exception as e:
                print(f"Error fetching {name}: {str(e)}")
                results[name] = None
                # Add extra delay after an error
                time.sleep(2)
        
        if self._is_running:
            self.data_fetched.emit(results)
        self.finished_signal.emit()
        
    def stop(self):
        self._is_running = False
        self.quit()
        self.wait(1000)
        
    def is_market_open(self, ticker):
        now = datetime.now()
        if '^NSE' in ticker:  # Indian market
            return (now.weekday() < 5 and 
                    9 <= now.hour < 15 or 
                    (now.hour == 15 and now.minute <= 30))
        else:  # US market
            return (now.weekday() < 5 and 
                    9 <= (now.hour - 4) < 16)  # Adjusting for timezone

class PortfolioTracker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Portfolio Tracker")
        self.setGeometry(100, 100, 1400, 900)
        self.portfolios = {}
        self.workers = []
        self.data_fetcher = MarketDataFetcher()
        self.load_data()
        self.init_ui()
        self.set_dark_theme()
        
    def init_ui(self):
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        self.create_main_menu()
        self.create_portfolio_management()
        self.create_stock_operations()
        self.create_dashboard_views()
        self.create_market_analysis()
        self.create_data_operations()
        self.create_audit_history()
        self.create_mutual_fund_operations()
        
        self.stacked_widget.setCurrentIndex(0)
        
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.auto_refresh)
        self.refresh_timer.start(300000)  # 5 minutes
        
    def set_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1A1B26;
            }
            QWidget {
                background-color: #1A1B26;
                font-family: 'Arial', sans-serif;
            }
            QLabel, QPushButton, QListWidget, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit {
                color: #E0E0E0;
                font-size: 14px;
            }
            QPushButton {
                background-color: #4361EE;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                min-width: 120px;
                min-height: 40px;
                font-weight: bold;
                color: white;
            }
            QPushButton:hover {
                background-color: #3A86FF;
            }
            QPushButton:pressed {
                background-color: #3F37C9;
            }
            QPushButton:disabled {
                background-color: #616161;
                color: #9E9E9E;
            }
            QListWidget, QTableWidget, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTabWidget::pane {
                background-color: #0F1017;
                border: 1px solid #2D2E3A;
                border-radius: 6px;
                padding: 8px;
            }
            QListWidget::item, QTableWidget::item {
                padding: 8px;
            }
            QListWidget::item:selected, QTableWidget::item:selected {
                background-color: #4361EE;
                color: white;
            }
            QHeaderView::section {
                background-color: #1A1B26;
                color: #E0E0E0;
                padding: 6px;
                border: none;
                font-weight: bold;
            }
            QTabWidget::pane {
                border: 1px solid #333;
                border-radius: 2px;
                padding: 5px;
                background: #1E1E1E;
            }
            QTabBar::tab {
                background: #1E1E1E;
                color: #E0E0E0;
                padding: 6px 10px;
                border-top-left-radius: 2px;
                border-top-right-radius: 2px;
                border: 1px solid #333;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #1E88E5;
                border-bottom: 2px solid #64B5F6;
            }
            QTabBar::tab:hover {
                background: #2196F3;
            }
            QDialog {
                background-color: #121212;
            }
            QTextEdit {
                background-color: #1E1E1E;
                border: 1px solid #333;
                font-size: 12px;
            }
        """)

    def create_main_menu(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header bar
        header = QWidget()
        header.setStyleSheet("background-color: #1A1B26;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 5, 10, 5)
        
        title = QLabel("PORTFOLIO TRACKER")
        title.setStyleSheet("""
            color: #FFFFFF;
            font-size: 18px;
            font-weight: bold;
        """)
        
        self.time_label = QLabel()
        self.time_label.setStyleSheet("""
            color: #AAAAAA;
            font-size: 14px;
        """)
        self.update_time()
        time_timer = QTimer(self)
        time_timer.timeout.connect(self.update_time)
        time_timer.start(1000)
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.time_label)
        layout.addWidget(header)
        
        # Main content
        content = QWidget()
        content.setStyleSheet("background-color: #121212;")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Left sidebar
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet("""
            background-color: #1A1B26;
            border-right: 1px solid #333333;
        """)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        
        menu_buttons = [
            ("PORTFOLIOS", lambda: self.stacked_widget.setCurrentIndex(1)),
            ("STOCKS", lambda: self.stacked_widget.setCurrentIndex(2)),
            ("DASHBOARD", lambda: self.stacked_widget.setCurrentIndex(3)),
            ("MARKET DATA", lambda: self.stacked_widget.setCurrentIndex(4)),
            ("DATA TOOLS", lambda: self.stacked_widget.setCurrentIndex(5)),
            ("AUDIT LOG", lambda: self.stacked_widget.setCurrentIndex(6)),
            ("MUTUAL FUNDS", lambda: self.stacked_widget.setCurrentIndex(7)),  
        ]
        
        for text, command in menu_buttons:
            btn = QPushButton(text)
            btn.setStyleSheet("""
                QPushButton {
                    color: #CCCCCC;
                    background-color: #1A1B26;
                    border: none;
                    text-align: left;
                    padding: 12px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #2A2B36;
                    color: #FFFFFF;
                }
                QPushButton:pressed {
                    background-color: #3A3B46;
                }
            """)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(command)
            sidebar_layout.addWidget(btn)
        
        sidebar_layout.addStretch()
        
        exit_btn = QPushButton("EXIT")
        exit_btn.setStyleSheet("""
            QPushButton {
                color: #FF5555;
                background-color: #1A1B26;
                border: none;
                text-align: left;
                padding: 12px 15px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2A2B36;
                color: #FF7777;
            }
        """)
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.clicked.connect(self.close)
        sidebar_layout.addWidget(exit_btn)
        
        content_layout.addWidget(sidebar)
        
        # Right content
        right_content = QWidget()
        right_layout = QVBoxLayout(right_content)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(15)
        
        # Summary boxes
        summary_layout = QHBoxLayout()
        summary_layout.setSpacing(15)
        
        # Market indices summary
        market_box = QFrame()
        market_box.setFrameShape(QFrame.StyledPanel)
        market_box.setStyleSheet("""
            background-color: #1A1B26;
            border: 1px solid #333333;
            border-radius: 4px;
        """)
        market_layout = QVBoxLayout(market_box)
        market_layout.setContentsMargins(10, 10, 10, 10)
        
        market_title = QLabel("MARKET INDICES")
        market_title.setStyleSheet("""
            color: #64B5F6;
            font-size: 14px;
            font-weight: bold;
        """)
        market_layout.addWidget(market_title)
        
        self.market_summary = QLabel("Loading market data...")
        self.market_summary.setStyleSheet("""
            color: #CCCCCC;
            font-size: 12px;
        """)
        market_layout.addWidget(self.market_summary)
        
        summary_layout.addWidget(market_box, 1)
        
        # Portfolio summary
        portfolio_box = QFrame()
        portfolio_box.setFrameShape(QFrame.StyledPanel)
        portfolio_box.setStyleSheet("""
            background-color: #1A1B26;
            border: 1px solid #333333;
            border-radius: 4px;
        """)
        portfolio_layout = QVBoxLayout(portfolio_box)
        portfolio_layout.setContentsMargins(10, 10, 10, 10)
        
        portfolio_title = QLabel("PORTFOLIO SUMMARY")
        portfolio_title.setStyleSheet("""
            color: #64B5F6;
            font-size: 14px;
            font-weight: bold;
        """)
        portfolio_layout.addWidget(portfolio_title)
        
        self.portfolio_summary = QLabel("No portfolio data available")
        self.portfolio_summary.setStyleSheet("""
            color: #CCCCCC;
            font-size: 12px;
        """)
        portfolio_layout.addWidget(self.portfolio_summary)
        
        summary_layout.addWidget(portfolio_box, 1)
        
        right_layout.addLayout(summary_layout)
        
        # Quick actions
        actions_title = QLabel("QUICK ACTIONS")
        actions_title.setStyleSheet("""
            color: #64B5F6;
            font-size: 14px;
            font-weight: bold;
        """)
        right_layout.addWidget(actions_title)
        
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)
        
        quick_actions = [
            ("ADD PORTFOLIO", self.show_create_portfolio_dialog),
            ("ADD STOCK", lambda: [self.stacked_widget.setCurrentIndex(2), self.show_add_stock_dialog()]),
            ("REFRESH DATA", self.refresh_all_data),
            ("EXPORT DATA", self.export_all_portfolios)
        ]
        
        for text, command in quick_actions:
            btn = QPushButton(text)
            btn.setStyleSheet("""
                QPushButton {
                    color: #CCCCCC;
                    background-color: #1A1B26;
                    border: 1px solid #333333;
                    padding: 8px 12px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #2A2B36;
                    color: #FFFFFF;
                }
            """)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(command)
            actions_layout.addWidget(btn)
        
        right_layout.addLayout(actions_layout)
        
        # Recent activity
        activity_title = QLabel("RECENT ACTIVITY")
        activity_title.setStyleSheet("""
            color: #64B5F6;
            font-size: 14px;
            font-weight: bold;
        """)
        right_layout.addWidget(activity_title)
        
        activity_box = QFrame()
        activity_box.setFrameShape(QFrame.StyledPanel)
        activity_box.setStyleSheet("""
            background-color: #1A1B26;
            border: 1px solid #333333;
            border-radius: 4px;
        """)
        activity_layout = QVBoxLayout(activity_box)
        activity_layout.setContentsMargins(10, 10, 10, 10)
        
        self.activity_log = QTextEdit()
        self.activity_log.setStyleSheet("""
            QTextEdit {
                color: #CCCCCC;
                background-color: #1A1B26;
                border: none;
                font-size: 12px;
            }
        """)
        self.activity_log.setReadOnly(True)
        activity_layout.addWidget(self.activity_log)
        
        right_layout.addWidget(activity_box)
        
        content_layout.addWidget(right_content, 1)
        layout.addWidget(content, 1)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)
        
        # Load initial data
        self.refresh_market_summary()
        self.refresh_portfolio_summary()
        self.refresh_activity_log()

    def update_time(self):
        self.time_label.setText(datetime.now().strftime("%H:%M:%S %d-%m-%Y"))

    def refresh_market_summary(self):
        indices = {
            'NIFTY 50': '^NSEI',
            'SENSEX': '^BSESN',
            'S&P 500': '^GSPC',
            'NASDAQ': '^IXIC'
        }
        
        def update_summary(prices):
            summary_text = ""
            for name, data in prices.items():
                if data is None:
                    continue
                    
                change = data['Change']
                pct_change = data['% Change']
                color = "#4CAF50" if change >= 0 else "#F44336"
                arrow = "↑" if change >= 0 else "↓"
                
                summary_text += (
                    f"<span style='color:white;'>{name.ljust(10)}</span> "
                    f"<span style='color:{color};'>{data['Current']:,.2f} {arrow} {pct_change:+.2f}%</span><br>"
                )
            
            self.market_summary.setText(summary_text)
        
        worker = MarketDataWorker(indices)
        worker.data_fetched.connect(update_summary)
        worker.finished_signal.connect(lambda: self.worker_finished(worker))
        self.workers.append(worker)
        worker.start()

    def refresh_portfolio_summary(self):
        if not self.portfolios:
            self.portfolio_summary.setText("No portfolios created")
            return
            
        total_investment = 0
        total_current = 0
        
        for portfolio in self.portfolios.values():
            if 'Investment Value' in portfolio.columns:
                total_investment += portfolio['Investment Value'].sum()
            if 'Current Value' in portfolio.columns:
                total_current += portfolio['Current Value'].sum()
            else:
                total_current += (portfolio['Quantity'] * portfolio['Purchase Price']).sum()
        
        pl = total_current - total_investment
        pct_pl = (pl / total_investment * 100) if total_investment > 0 else 0
        
        color = "#4CAF50" if pl >= 0 else "#F44336"
        arrow = "↑" if pl >= 0 else "↓"
        
        summary_text = (
            f"<span style='color:white;'>Portfolios: {len(self.portfolios)}</span><br>"
            f"<span style='color:white;'>Invested: ₹{total_investment:,.2f}</span><br>"
            f"<span style='color:white;'>Current: ₹{total_current:,.2f}</span><br>"
            f"<span style='color:{color};'>P/L: ₹{pl:+,.2f} {arrow} {pct_pl:+.2f}%</span>"
        )
        
        self.portfolio_summary.setText(summary_text)

    def refresh_activity_log(self):
        try:
            with open("portfolio_audit.log", "r") as f:
                log_entries = [line.strip() for line in f.readlines() if line.strip()]
        except FileNotFoundError:
            log_entries = []
        
        recent_entries = reversed(log_entries[-5:]) if log_entries else ["No recent activity"]
        
        html = ""
        for entry in recent_entries:
            parts = entry.split(" | ")
            if len(parts) == 5:
                timestamp, action, portfolio, stock, details = parts
                html += f"""
                    <div style="margin-bottom: 5px;">
                        <span style="color: #AAAAAA;">[{timestamp}]</span>
                        <span style="color: #64B5F6;">{action}</span>
                        <span style="color: white;">{portfolio}</span>
                        {f'<span style="color: #FFC107;">{stock}</span>' if stock else ''}
                        {f'<span style="color: #CCCCCC;">- {details}</span>' if details else ''}
                    </div>
                """
            else:
                html += f'<div style="color: #CCCCCC;">{entry}</div>'
        
        self.activity_log.setHtml(html)

    def refresh_all_data(self):
        self.refresh_market_summary()
        self.refresh_portfolio_summary()
        self.refresh_activity_log()
        
        current_page = self.stacked_widget.currentIndex()
        if current_page == 2:
            self.refresh_stock_table()
        elif current_page == 3:
            self.refresh_dashboard_data()
        elif current_page == 4:
            self.refresh_indian_market_data()
            self.refresh_global_market_data()
        
        QMessageBox.information(self, "Refresh", "All data refreshed successfully!")

    def create_portfolio_management(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        title = QLabel("Portfolio Management")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        list_frame = QFrame()
        list_frame.setFrameShape(QFrame.StyledPanel)
        list_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 5px;")
        list_layout = QVBoxLayout(list_frame)
        
        self.portfolio_list = QListWidget()
        self.portfolio_list.setStyleSheet("font-size: 14px;")
        self.portfolio_list.setSelectionMode(QListWidget.SingleSelection)
        self.refresh_portfolio_list()
        list_layout.addWidget(self.portfolio_list)
        
        layout.addWidget(list_frame)
        
        btn_layout = QHBoxLayout()
        create_btn = QPushButton("Create Portfolio")
        create_btn.clicked.connect(self.show_create_portfolio_dialog)
        delete_btn = QPushButton("Delete Portfolio")
        delete_btn.clicked.connect(self.delete_portfolio)
        view_btn = QPushButton("View Portfolio")
        view_btn.clicked.connect(self.view_portfolio_details)
        
        btn_layout.addWidget(create_btn)
        btn_layout.addWidget(delete_btn)
        btn_layout.addWidget(view_btn)
        layout.addLayout(btn_layout)
        
        back_btn = QPushButton("Back to Main Menu")
        back_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        layout.addWidget(back_btn)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)

    def refresh_portfolio_list(self):
        self.portfolio_list.clear()
        for portfolio in sorted(self.portfolios.keys()):
            self.portfolio_list.addItem(portfolio)

    def show_create_portfolio_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Portfolio")
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        name_label = QLabel("Portfolio Name:")
        name_label.setStyleSheet("font-size: 14px;")
        self.portfolio_name_input = QLineEdit()
        self.portfolio_name_input.setPlaceholderText("Enter portfolio name")
        
        layout.addWidget(name_label)
        layout.addWidget(self.portfolio_name_input)
        
        btn_layout = QHBoxLayout()
        create_btn = QPushButton("Create")
        create_btn.clicked.connect(lambda: self.create_portfolio(dialog))
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(create_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()

    def create_portfolio(self, dialog):
        name = self.portfolio_name_input.text().strip()
        if name:
            if name not in self.portfolios:
                self.portfolios[name] = pd.DataFrame(columns=[
                    'Stock Name', 'Ticker Symbol', 'Quantity', 'Purchase Price',
                    'Purchase Date', 'Sector', 'Investment Value'
                ])
                self.log_audit("CREATED_PORTFOLIO", name)
                self.refresh_portfolio_list()
                dialog.accept()
                QMessageBox.information(self, "Success", f"Portfolio '{name}' created successfully!")
            else:
                QMessageBox.warning(self, "Error", "Portfolio already exists!")
        else:
            QMessageBox.warning(self, "Error", "Portfolio name cannot be empty!")

    def delete_portfolio(self):
        selected = self.portfolio_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Error", "Please select a portfolio first!")
            return
            
        portfolio = selected.text()
        reply = QMessageBox.question(
            self, "Confirm Deletion", 
            f"Are you sure you want to delete the portfolio '{portfolio}'?\nThis action cannot be undone.", 
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            del self.portfolios[portfolio]
            self.log_audit("DELETED_PORTFOLIO", portfolio)
            self.refresh_portfolio_list()
            QMessageBox.information(self, "Success", f"Portfolio '{portfolio}' deleted successfully!")

    def view_portfolio_details(self):
        selected = self.portfolio_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Error", "Please select a portfolio first!")
            return
            
        portfolio = selected.text()
        self.portfolio_combo.setCurrentText(portfolio)
        self.stacked_widget.setCurrentIndex(2)
        self.refresh_stock_table()

    def create_stock_operations(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        title = QLabel("Stock Operations")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        portfolio_frame = QFrame()
        portfolio_frame.setFrameShape(QFrame.StyledPanel)
        portfolio_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 5px; padding: 10px;")
        portfolio_layout = QHBoxLayout(portfolio_frame)
        
        portfolio_label = QLabel("Selected Portfolio:")
        portfolio_label.setStyleSheet("font-size: 14px;")
        self.portfolio_combo = QComboBox()
        self.portfolio_combo.setStyleSheet("font-size: 14px;")
        self.portfolio_combo.addItems(sorted(self.portfolios.keys()))
        self.portfolio_combo.currentTextChanged.connect(self.refresh_stock_table)
        
        portfolio_layout.addWidget(portfolio_label)
        portfolio_layout.addWidget(self.portfolio_combo)
        portfolio_layout.addStretch()
        layout.addWidget(portfolio_frame)
        
        table_frame = QFrame()
        table_frame.setFrameShape(QFrame.StyledPanel)
        table_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 5px;")
        table_layout = QVBoxLayout(table_frame)
        
        self.stock_table = QTableWidget()
        self.stock_table.setColumnCount(7)
        self.stock_table.setHorizontalHeaderLabels([
            "Stock", "Ticker", "Qty", "Avg Price", "Curr Price", "P/L", "Daily P/L"
        ])
        self.stock_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.stock_table.setSelectionMode(QTableWidget.SingleSelection)
        self.stock_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stock_table.verticalHeader().setVisible(False)
        
        table_layout.addWidget(self.stock_table)
        layout.addWidget(table_frame)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Stock")
        add_btn.clicked.connect(self.show_add_stock_dialog)
        modify_btn = QPushButton("Modify Stock")
        modify_btn.clicked.connect(self.show_modify_stock_dialog)
        manage_btn = QPushButton("Manage Shares")
        manage_btn.clicked.connect(self.show_manage_shares_dialog)
        refresh_btn = QPushButton("Refresh Data")
        refresh_btn.clicked.connect(self.refresh_stock_table)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(modify_btn)
        btn_layout.addWidget(manage_btn)
        btn_layout.addWidget(refresh_btn)
        layout.addLayout(btn_layout)
        
        back_btn = QPushButton("Back to Main Menu")
        back_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        layout.addWidget(back_btn)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)
        
    def refresh_stock_table(self):
        portfolio = self.portfolio_combo.currentText()
        if not portfolio or portfolio not in self.portfolios:
            return
            
        df = self.portfolios[portfolio]
        self.stock_table.setRowCount(len(df))
        
        if len(df) == 0:
            return
            
        tickers = df['Ticker Symbol'].tolist()
        worker = Worker(tickers)
        worker.data_fetched.connect(
            lambda prices: self.update_stock_table_with_prices(portfolio, prices)
        )
        worker.finished_signal.connect(lambda: self.worker_finished(worker))
        self.workers.append(worker)
        worker.start()
        
    def update_stock_table_with_prices(self, portfolio, prices):
        """Update the stock table with current prices and calculate all metrics"""
        if portfolio not in self.portfolios:
            return
            
        df = self.portfolios[portfolio].copy()
        
        # Update current prices from the fetched data
        df['Current Price'] = df['Ticker Symbol'].map(prices)
        
        # Calculate basic metrics
        df['Current Value'] = df['Quantity'] * df['Current Price']
        df['Investment Value'] = df['Quantity'] * df['Purchase Price']
        df['Profit/Loss'] = df['Current Value'] - df['Investment Value']
        
        # Calculate percentages (handle division by zero)
        df['Profit/Loss %'] = np.where(
            df['Investment Value'] > 0,
            (df['Profit/Loss'] / df['Investment Value']) * 100,
            0
        )
        
        # Calculate daily metrics
        df['Daily P/L'] = 0.0
        df['Daily Return %'] = 0.0
        
        # Fetch historical data for daily calculations
        for idx, row in df.iterrows():
            ticker = row['Ticker Symbol']
            current_price = row['Current Price']
            
            if pd.isna(current_price):
                continue
                
            try:
                # Get previous close price
                stock = yf.Ticker(ticker)
                hist = stock.history(period="2d")
                
                if len(hist) >= 2:
                    prev_close = hist['Close'].iloc[-2]
                    daily_change = current_price - prev_close
                    
                    # Calculate daily P/L
                    df.at[idx, 'Daily P/L'] = daily_change * row['Quantity']
                    
                    # Calculate daily return percentage
                    if prev_close > 0:
                        df.at[idx, 'Daily Return %'] = (daily_change / prev_close) * 100
                        
            except Exception as e:
                print(f"Error calculating daily metrics for {ticker}: {str(e)}")
                continue
        
        # Update the portfolio data with all calculated fields
        self.portfolios[portfolio] = df
        
        # Update the table display
        self.stock_table.setRowCount(len(df))
        
        for row in range(len(df)):
            stock = df.iloc[row]
            
            # Basic information
            self.stock_table.setItem(row, 0, QTableWidgetItem(stock['Stock Name']))
            self.stock_table.setItem(row, 1, QTableWidgetItem(stock['Ticker Symbol']))
            self.stock_table.setItem(row, 2, QTableWidgetItem(str(stock['Quantity'])))
            self.stock_table.setItem(row, 3, QTableWidgetItem(f"{stock['Purchase Price']:.2f}"))
            
            if pd.notna(stock['Current Price']):
                # Current price
                self.stock_table.setItem(row, 4, QTableWidgetItem(f"{stock['Current Price']:.2f}"))
                
                # Profit/Loss
                pl_item = QTableWidgetItem(f"{stock['Profit/Loss']:+,.2f}")
                pl_item.setForeground(QColor('#4CAF50') if stock['Profit/Loss'] >= 0 else QColor('#F44336'))
                self.stock_table.setItem(row, 5, pl_item)
                
                # Profit/Loss %
                pl_pct_item = QTableWidgetItem(f"{stock['Profit/Loss %']:+.2f}%")
                pl_pct_item.setForeground(QColor('#4CAF50') if stock['Profit/Loss'] >= 0 else QColor('#F44336'))
                self.stock_table.setItem(row, 6, pl_pct_item)
                
                # Daily P/L
                daily_pl_item = QTableWidgetItem(f"{stock['Daily P/L']:+,.2f}")
                daily_pl_item.setForeground(QColor('#4CAF50') if stock['Daily P/L'] >= 0 else QColor('#F44336'))
                self.stock_table.setItem(row, 7, daily_pl_item)
                
                # Daily Return %
                daily_ret_item = QTableWidgetItem(f"{stock['Daily Return %']:+.2f}%")
                daily_ret_item.setForeground(QColor('#4CAF50') if stock['Daily Return %'] >= 0 else QColor('#F44336'))
                self.stock_table.setItem(row, 8, daily_ret_item)
            else:
                # Handle cases where price data isn't available
                for col in range(4, 9):
                    self.stock_table.setItem(row, col, QTableWidgetItem("N/A"))
        
        # Resize columns to fit content
        self.stock_table.resizeColumnsToContents()
                    
    def get_daily_change(self, ticker, row):
        def fetch_daily_change():
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period="2d")
                if len(hist) >= 2:
                    current = hist['Close'].iloc[-1]
                    prev_close = hist['Close'].iloc[-2]
                    change = current - prev_close
                    
                    item = QTableWidgetItem(f"{change:+,.2f}")
                    item.setForeground(QColor('#4CAF50') if change >= 0 else QColor('#F44336'))
                    self.stock_table.setItem(row, 6, item)
            except Exception as e:
                print(f"Error fetching daily change for {ticker}: {str(e)}")
                self.stock_table.setItem(row, 6, QTableWidgetItem("N/A"))
                
        thread = threading.Thread(target=fetch_daily_change)
        thread.daemon = True
        thread.start()
        
    def show_add_stock_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Stock")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        fields = [
            ("Stock Name", QLineEdit()),
            ("Ticker Symbol", QLineEdit()),
            ("Quantity", QSpinBox()),
            ("Purchase Price", QDoubleSpinBox()),
            ("Purchase Date", QDateEdit(QDate.currentDate())),
            ("Sector", QLineEdit())
        ]
        
        for label, widget in fields:
            field_layout = QHBoxLayout()
            label_widget = QLabel(f"{label}:")
            label_widget.setStyleSheet("font-size: 14px; min-width: 120px;")
            
            if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setMinimum(1)
                widget.setMaximum(999999)
                widget.setValue(1)
            elif isinstance(widget, QDateEdit):
                widget.setCalendarPopup(True)
                widget.setDisplayFormat("dd-MM-yyyy")
            
            widget.setStyleSheet("font-size: 14px;")
            field_layout.addWidget(label_widget)
            field_layout.addWidget(widget)
            layout.addLayout(field_layout)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Stock")
        add_btn.clicked.connect(lambda: self.add_stock(dialog, fields))
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()
        
    def add_stock(self, dialog, fields):
        portfolio = self.portfolio_combo.currentText()
        stock_data = {
            'Portfolio Name': portfolio,  # Add portfolio name
            'Stock Name': fields[0][1].text().strip(),
            'Ticker Symbol': fields[1][1].text().strip().upper(),
            'Quantity': fields[2][1].value(),
            'Purchase Price': fields[3][1].value(),
            'Purchase Date': fields[4][1].date().toString("dd-MM-yyyy"),
            'Sector': fields[5][1].text().strip(),
            'Investment Value': fields[2][1].value() * fields[3][1].value(),
            'Current Price': fields[3][1].value(),  # Initially same as purchase price
            'Current Value': fields[2][1].value() * fields[3][1].value(),
            'Profit/Loss': 0,  # Initially zero
            'Profit/Loss %': 0,  # Initially zero
            'Daily Return %': 0,  # Initially zero
            'Daily P/L': 0  # Initially zero
        }
        
        if not stock_data['Stock Name'] or not stock_data['Ticker Symbol']:
            QMessageBox.warning(self, "Error", "Stock name and ticker are required!")
            return
            
        existing_stocks = self.portfolios[portfolio]['Ticker Symbol'].tolist()
        if stock_data['Ticker Symbol'] in existing_stocks:
            reply = QMessageBox.question(
                self, "Stock Exists",
                "This stock already exists in the portfolio. Would you like to add these shares to the existing position?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                idx = existing_stocks.index(stock_data['Ticker Symbol'])
                existing_qty = self.portfolios[portfolio].at[idx, 'Quantity']
                existing_price = self.portfolios[portfolio].at[idx, 'Purchase Price']
                
                total_investment = (existing_qty * existing_price) + (stock_data['Quantity'] * stock_data['Purchase Price'])
                new_qty = existing_qty + stock_data['Quantity']
                new_avg = total_investment / new_qty
                
                self.portfolios[portfolio].at[idx, 'Quantity'] = new_qty
                self.portfolios[portfolio].at[idx, 'Purchase Price'] = new_avg
                self.portfolios[portfolio].at[idx, 'Investment Value'] = total_investment
                
                self.log_audit(
                    "ADDED_SHARES", portfolio, stock_data['Stock Name'],
                    f"Added {stock_data['Quantity']} @ {stock_data['Purchase Price']:.2f}, New Qty: {new_qty}, New Avg: {new_avg:.2f}"
                )
                
                dialog.accept()
                self.refresh_stock_table()
                return
        
        self.portfolios[portfolio] = pd.concat([
            self.portfolios[portfolio],
            pd.DataFrame([stock_data])
        ], ignore_index=True)
        
        self.log_audit("ADDED_STOCK", portfolio, stock_data['Stock Name'], 
                      f"Qty: {stock_data['Quantity']} @ {stock_data['Purchase Price']}")
        
        self.refresh_stock_table()
        dialog.accept()
        QMessageBox.information(self, "Success", "Stock added successfully!")
        
    def show_modify_stock_dialog(self):
        selected = self.stock_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Error", "Please select a stock first!")
            return
            
        portfolio = self.portfolio_combo.currentText()
        stock = self.portfolios[portfolio].iloc[selected]
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Modify Stock")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        fields = [
            ("Stock Name", QLineEdit(stock['Stock Name'])),
            ("Ticker Symbol", QLineEdit(stock['Ticker Symbol'])),
            ("Quantity", QSpinBox()),
            ("Purchase Price", QDoubleSpinBox()),
            ("Purchase Date", QDateEdit(QDate.fromString(stock['Purchase Date'], "dd-MM-yyyy"))),
            ("Sector", QLineEdit(stock['Sector']))
        ]
        
        fields[2][1].setValue(stock['Quantity'])
        fields[3][1].setValue(stock['Purchase Price'])
        
        for label, widget in fields:
            field_layout = QHBoxLayout()
            label_widget = QLabel(f"{label}:")
            label_widget.setStyleSheet("font-size: 14px; min-width: 120px;")
            
            if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setMinimum(1)
                widget.setMaximum(999999)
            elif isinstance(widget, QDateEdit):
                widget.setCalendarPopup(True)
                widget.setDisplayFormat("dd-MM-yyyy")
            
            widget.setStyleSheet("font-size: 14px;")
            field_layout.addWidget(label_widget)
            field_layout.addWidget(widget)
            layout.addLayout(field_layout)
        
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save Changes")
        save_btn.clicked.connect(lambda: self.modify_stock(dialog, selected, fields))
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()
        
    def modify_stock(self, dialog, row, fields):
        portfolio = self.portfolio_combo.currentText()
        stock_data = {
            'Portfolio Name': portfolio,
            'Stock Name': fields[0][1].text().strip(),
            'Ticker Symbol': fields[1][1].text().strip().upper(),
            'Quantity': fields[2][1].value(),
            'Purchase Price': fields[3][1].value(),
            'Purchase Date': fields[4][1].date().toString("dd-MM-yyyy"),
            'Sector': fields[5][1].text().strip(),
            'Investment Value': fields[2][1].value() * fields[3][1].value(),
            'Current Price': fields[3][1].value(),  # Initially same as purchase price
            'Current Value': fields[2][1].value() * fields[3][1].value(),
            'Profit/Loss': 0,
            'Profit/Loss %': 0,
            'Daily Return %': 0,
            'Daily P/L': 0
        }
        if not stock_data['Stock Name'] or not stock_data['Ticker Symbol']:
            QMessageBox.warning(self, "Error", "Stock name and ticker are required!")
            return
            
        self.portfolios[portfolio].iloc[row] = stock_data
        self.log_audit("MODIFIED_STOCK", portfolio, stock_data['Stock Name'])
        self.refresh_stock_table()
        dialog.accept()
        QMessageBox.information(self, "Success", "Stock modified successfully!")
        
    def show_manage_shares_dialog(self):
        selected = self.stock_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Error", "Please select a stock first!")
            return
            
        portfolio = self.portfolio_combo.currentText()
        stock = self.portfolios[portfolio].iloc[selected]
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Shares")
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        current_qty = QLabel(f"Current Quantity: {stock['Quantity']}")
        current_qty.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(current_qty)
        
        action_combo = QComboBox()
        action_combo.addItems(["Add Shares", "Remove Shares"])
        action_combo.setStyleSheet("font-size: 14px;")
        layout.addWidget(action_combo)
        
        qty_label = QLabel("Quantity:")
        qty_label.setStyleSheet("font-size: 14px;")
        qty_input = QSpinBox()
        qty_input.setMinimum(1)
        qty_input.setMaximum(999999)
        qty_input.setValue(1)
        qty_input.setStyleSheet("font-size: 14px;")
        layout.addWidget(qty_label)
        layout.addWidget(qty_input)
        
        price_label = QLabel("Price (for adding shares):")
        price_label.setStyleSheet("font-size: 14px;")
        price_input = QDoubleSpinBox()
        price_input.setMinimum(0.01)
        price_input.setMaximum(999999)
        price_input.setValue(stock['Purchase Price'])
        price_input.setStyleSheet("font-size: 14px;")
        layout.addWidget(price_label)
        layout.addWidget(price_input)
        
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save Changes")
        save_btn.clicked.connect(
            lambda: self.manage_shares(
                dialog, selected, action_combo.currentText(), 
                qty_input.value(), price_input.value()
            )
        )
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()
        
    def manage_shares(self, dialog, row, action, qty, price):
        portfolio = self.portfolio_combo.currentText()
        stock = self.portfolios[portfolio].iloc[row].copy()
        
        if action == "Add Shares":
            total_investment = (stock['Quantity'] * stock['Purchase Price']) + (qty * price)
            new_qty = stock['Quantity'] + qty
            new_avg = total_investment / new_qty
            
            self.portfolios[portfolio].at[row, 'Quantity'] = new_qty
            self.portfolios[portfolio].at[row, 'Purchase Price'] = new_avg
            self.portfolios[portfolio].at[row, 'Investment Value'] = total_investment
            
            self.log_audit(
                "ADDED_SHARES", portfolio, stock['Stock Name'],
                f"Added {qty} @ {price:.2f}, New Qty: {new_qty}, New Avg: {new_avg:.2f}"
            )
            
            QMessageBox.information(self, "Success", f"Added {qty} shares to {stock['Stock Name']}")
        else:
            if qty > stock['Quantity']:
                QMessageBox.warning(self, "Error", "Cannot remove more shares than available!")
                return
                
            new_qty = stock['Quantity'] - qty
            if new_qty == 0:
                self.portfolios[portfolio] = self.portfolios[portfolio].drop(row).reset_index(drop=True)
                self.log_audit(
                    "REMOVED_ALL_SHARES", portfolio, stock['Stock Name'],
                    f"Removed all {stock['Quantity']} shares"
                )
                QMessageBox.information(self, "Success", f"Removed all shares of {stock['Stock Name']}")
            else:
                self.portfolios[portfolio].at[row, 'Quantity'] = new_qty
                self.portfolios[portfolio].at[row, 'Investment Value'] = new_qty * stock['Purchase Price']
                
                self.log_audit(
                    "REMOVED_SHARES", portfolio, stock['Stock Name'],
                    f"Removed {qty} shares, Remaining: {new_qty}"
                )
                QMessageBox.information(self, "Success", f"Removed {qty} shares from {stock['Stock Name']}")
        
        self.refresh_stock_table()
        dialog.accept()
        
    def create_mutual_fund_operations(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        title = QLabel("Mutual Fund Operations")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        portfolio_frame = QFrame()
        portfolio_frame.setFrameShape(QFrame.StyledPanel)
        portfolio_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 5px; padding: 10px;")
        portfolio_layout = QHBoxLayout(portfolio_frame)
        
        portfolio_label = QLabel("Selected Portfolio:")
        portfolio_label.setStyleSheet("font-size: 14px;")
        self.mf_portfolio_combo = QComboBox()
        self.mf_portfolio_combo.setStyleSheet("font-size: 14px;")
        self.mf_portfolio_combo.addItems(sorted(self.portfolios.keys()))
        self.mf_portfolio_combo.currentTextChanged.connect(self.refresh_mf_table)
        
        portfolio_layout.addWidget(portfolio_label)
        portfolio_layout.addWidget(self.mf_portfolio_combo)
        portfolio_layout.addStretch()
        layout.addWidget(portfolio_frame)
        
        table_frame = QFrame()
        table_frame.setFrameShape(QFrame.StyledPanel)
        table_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 5px;")
        table_layout = QVBoxLayout(table_frame)
        
        self.mf_table = QTableWidget()
        self.mf_table.setColumnCount(8)
        self.mf_table.setHorizontalHeaderLabels([
            "Fund Name", "Scheme Code", "Units", "Avg NAV", "Current NAV", 
            "Invested", "Current Value", "P/L"
        ])
        self.mf_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.mf_table.setSelectionMode(QTableWidget.SingleSelection)
        self.mf_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.mf_table.verticalHeader().setVisible(False)
        
        table_layout.addWidget(self.mf_table)
        layout.addWidget(table_frame)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Fund")
        add_btn.clicked.connect(self.show_add_mf_dialog)
        modify_btn = QPushButton("Modify Fund")
        modify_btn.clicked.connect(self.show_modify_mf_dialog)
        manage_btn = QPushButton("Manage Units")
        manage_btn.clicked.connect(self.show_manage_mf_units_dialog)
        refresh_btn = QPushButton("Refresh Data")
        refresh_btn.clicked.connect(self.refresh_mf_table)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(modify_btn)
        btn_layout.addWidget(manage_btn)
        btn_layout.addWidget(refresh_btn)
        layout.addLayout(btn_layout)
        
        back_btn = QPushButton("Back to Main Menu")
        back_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        layout.addWidget(back_btn)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)
        
    def refresh_mf_table(self):
        portfolio = self.mf_portfolio_combo.currentText()
        if not portfolio or portfolio not in self.portfolios:
            return
            
        # Filter mutual funds from the portfolio (they have 'Scheme Code' column)
        mf_data = self.portfolios[portfolio]
        if 'Scheme Code' not in mf_data.columns:
            mf_data = pd.DataFrame(columns=[
                'Fund Name', 'Scheme Code', 'Units', 'Avg NAV', 
                'Current NAV', 'Invested', 'Current Value', 'P/L'
            ])
        else:
            mf_data = mf_data[mf_data['Scheme Code'].notna()].copy()
            
        self.mf_table.setRowCount(len(mf_data))
        
        if len(mf_data) == 0:
            return
            
        # Fetch latest NAV for all funds
        scheme_codes = mf_data['Scheme Code'].tolist()
        self.fetch_mf_nav(scheme_codes, portfolio)
        
    def fetch_mf_nav(self, scheme_codes, portfolio):
        def fetch_nav_thread():
            nav_values = {}
            for code in scheme_codes:
                try:
                    nav = self.get_mf_nav_from_api(code)  # Replace with actual API call
                    nav_values[code] = nav
                except Exception as e:
                    print(f"Error fetching NAV for scheme {code}: {str(e)}")
                    nav_values[code] = None
            
            # Update UI with fetched NAV values
            self.update_mf_table_with_nav(portfolio, nav_values)
            
        thread = threading.Thread(target=fetch_nav_thread)
        thread.daemon = True
        thread.start()
   
    def get_mf_nav_from_api(self, scheme_code):
        """Placeholder function - replace with actual API call to get MF NAV"""
        return round(100 + (random.random() * 20 - 10), 2)
    
    def update_mf_table_with_nav(self, portfolio, nav_values):
        df = self.portfolios[portfolio].copy()
        mf_data = df[df['Scheme Code'].notna()].copy()
        
        mf_data['Current NAV'] = mf_data['Scheme Code'].map(nav_values)
        mf_data['Current Value'] = mf_data['Units'] * mf_data['Current NAV']
        mf_data['P/L'] = mf_data['Current Value'] - mf_data['Invested']
        
        for row in range(len(mf_data)):
            fund = mf_data.iloc[row]
            
            self.mf_table.setItem(row, 0, QTableWidgetItem(fund['Fund Name']))
            self.mf_table.setItem(row, 1, QTableWidgetItem(str(fund['Scheme Code'])))
            self.mf_table.setItem(row, 2, QTableWidgetItem(f"{fund['Units']:.2f}"))
            self.mf_table.setItem(row, 3, QTableWidgetItem(f"{fund['Avg NAV']:.2f}"))
            
            if pd.notna(fund['Current NAV']):
                self.mf_table.setItem(row, 4, QTableWidgetItem(f"{fund['Current NAV']:.2f}"))
                self.mf_table.setItem(row, 5, QTableWidgetItem(f"₹{fund['Invested']:,.2f}"))
                self.mf_table.setItem(row, 6, QTableWidgetItem(f"₹{fund['Current Value']:,.2f}"))
                
                pl_item = QTableWidgetItem(f"₹{fund['P/L']:+,.2f}")
                pl_item.setForeground(QColor('#4CAF50') if fund['P/L'] >= 0 else QColor('#F44336'))
                self.mf_table.setItem(row, 7, pl_item)
            else:
                for col in range(4, 8):
                    self.mf_table.setItem(row, col, QTableWidgetItem("N/A"))
    
    def show_add_mf_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Mutual Fund")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        fields = [
            ("Fund Name", QLineEdit()),
            ("Scheme Code", QLineEdit()),
            ("Units", QDoubleSpinBox()),
            ("Average NAV", QDoubleSpinBox()),
            ("Invested Amount", QDoubleSpinBox()),
            ("Category", QComboBox()),
            ("AMC", QComboBox())
        ]
        
        # Setup category and AMC options
        fields[5][1].addItems(["Equity", "Debt", "Hybrid", "Solution Oriented", "Other"])
        fields[6][1].addItems([
            "SBI Mutual Fund", "HDFC Mutual Fund", "ICICI Prudential", 
            "Nippon India", "Axis Mutual Fund", "Other"
        ])
        
        for label, widget in fields:
            field_layout = QHBoxLayout()
            label_widget = QLabel(f"{label}:")
            label_widget.setStyleSheet("font-size: 14px; min-width: 120px;")
            
            if isinstance(widget, QDoubleSpinBox):
                widget.setMinimum(0.01)
                widget.setMaximum(9999999)
                widget.setValue(1.00)
                widget.setDecimals(2)
            elif isinstance(widget, QComboBox):
                widget.setEditable(True)
                
            widget.setStyleSheet("font-size: 14px;")
            field_layout.addWidget(label_widget)
            field_layout.addWidget(widget)
            layout.addLayout(field_layout)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Fund")
        add_btn.clicked.connect(lambda: self.add_mutual_fund(dialog, fields))
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()

    def add_mutual_fund(self, dialog, fields):
        portfolio = self.mf_portfolio_combo.currentText()
        mf_data = {
            'Fund Name': fields[0][1].text().strip(),
            'Scheme Code': fields[1][1].text().strip(),
            'Units': fields[2][1].value(),
            'Avg NAV': fields[3][1].value(),
            'Invested': fields[4][1].value(),
            'Category': fields[5][1].currentText(),
            'AMC': fields[6][1].currentText(),
            'Type': 'Mutual Fund'
        }
        
        if not mf_data['Fund Name'] or not mf_data['Scheme Code']:
            QMessageBox.warning(self, "Error", "Fund name and scheme code are required!")
            return
            
        # Add to portfolio
        if portfolio in self.portfolios:
            self.portfolios[portfolio] = pd.concat([
                self.portfolios[portfolio],
                pd.DataFrame([mf_data])
            ], ignore_index=True)
        else:
            self.portfolios[portfolio] = pd.DataFrame([mf_data])
            
        self.log_audit("ADDED_MF", portfolio, mf_data['Fund Name'], 
                      f"Units: {mf_data['Units']:.2f} @ {mf_data['Avg NAV']:.2f}")
        
        self.refresh_mf_table()
        dialog.accept()
        QMessageBox.information(self, "Success", "Mutual fund added successfully!")
      
    def show_modify_mf_dialog(self):
        selected = self.mf_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Error", "Please select a mutual fund first!")
            return
            
        portfolio = self.mf_portfolio_combo.currentText()
        mf_data = self.get_mf_data(portfolio).iloc[selected]
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Modify Mutual Fund")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        fields = [
            ("Fund Name", QLineEdit(mf_data['Fund Name'])),
            ("Scheme Code", QLineEdit(str(mf_data['Scheme Code']))),
            ("Units", QDoubleSpinBox()),
            ("Average NAV", QDoubleSpinBox()),
            ("Invested Amount", QDoubleSpinBox()),
            ("Category", QComboBox()),
            ("AMC", QComboBox())
        ]
        
        fields[2][1].setValue(mf_data['Units'])
        fields[3][1].setValue(mf_data['Avg NAV'])
        fields[4][1].setValue(mf_data['Invested'])
        
        # Setup category and AMC options
        fields[5][1].addItems(["Equity", "Debt", "Hybrid", "Solution Oriented", "Other"])
        fields[5][1].setCurrentText(mf_data.get('Category', 'Equity'))
        fields[6][1].addItems([
            "SBI Mutual Fund", "HDFC Mutual Fund", "ICICI Prudential", 
            "Nippon India", "Axis Mutual Fund", "Other"
        ])
        fields[6][1].setCurrentText(mf_data.get('AMC', 'Other'))
        
        for label, widget in fields:
            field_layout = QHBoxLayout()
            label_widget = QLabel(f"{label}:")
            label_widget.setStyleSheet("font-size: 14px; min-width: 120px;")
            
            if isinstance(widget, QDoubleSpinBox):
                widget.setMinimum(0.01)
                widget.setMaximum(9999999)
                widget.setDecimals(2)
            elif isinstance(widget, QComboBox):
                widget.setEditable(True)
                
            widget.setStyleSheet("font-size: 14px;")
            field_layout.addWidget(label_widget)
            field_layout.addWidget(widget)
            layout.addLayout(field_layout)
        
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save Changes")
        save_btn.clicked.connect(lambda: self.modify_mutual_fund(dialog, selected, fields))
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()
            
    def modify_mutual_fund(self, dialog, row, fields):
        portfolio = self.mf_portfolio_combo.currentText()
        mf_data = {
            'Fund Name': fields[0][1].text().strip(),
            'Scheme Code': fields[1][1].text().strip(),
            'Units': fields[2][1].value(),
            'Avg NAV': fields[3][1].value(),
            'Invested': fields[4][1].value(),
            'Category': fields[5][1].currentText(),
            'AMC': fields[6][1].currentText(),
            'Type': 'Mutual Fund'
        }
        
        if not mf_data['Fund Name'] or not mf_data['Scheme Code']:
            QMessageBox.warning(self, "Error", "Fund name and scheme code are required!")
            return
            
        # Get the index in the full portfolio DataFrame
        full_df = self.portfolios[portfolio]
        mf_indices = full_df[full_df['Scheme Code'].notna()].index
        if row >= len(mf_indices):
            return
            
        idx = mf_indices[row]
        
        # Update the data
        for col, value in mf_data.items():
            self.portfolios[portfolio].at[idx, col] = value
            
        self.log_audit("MODIFIED_MF", portfolio, mf_data['Fund Name'])
        self.refresh_mf_table()
        dialog.accept()
        QMessageBox.information(self, "Success", "Mutual fund modified successfully!")
        
    def show_manage_mf_units_dialog(self):
        selected = self.mf_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Error", "Please select a mutual fund first!")
            return
            
        portfolio = self.mf_portfolio_combo.currentText()
        mf_data = self.get_mf_data(portfolio).iloc[selected]
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Mutual Fund Units")
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        current_units = QLabel(f"Current Units: {mf_data['Units']:.2f}")
        current_units.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(current_units)
        
        action_combo = QComboBox()
        action_combo.addItems(["Add Units", "Remove Units"])
        action_combo.setStyleSheet("font-size: 14px;")
        layout.addWidget(action_combo)
        
        units_label = QLabel("Units:")
        units_label.setStyleSheet("font-size: 14px;")
        units_input = QDoubleSpinBox()
        units_input.setMinimum(0.01)
        units_input.setMaximum(999999)
        units_input.setValue(1.00)
        units_input.setDecimals(2)
        units_input.setStyleSheet("font-size: 14px;")
        layout.addWidget(units_label)
        layout.addWidget(units_input)
        
        nav_label = QLabel("NAV (for adding units):")
        nav_label.setStyleSheet("font-size: 14px;")
        nav_input = QDoubleSpinBox()
        nav_input.setMinimum(0.01)
        nav_input.setMaximum(999999)
        nav_input.setValue(mf_data['Avg NAV'])
        nav_input.setDecimals(2)
        nav_input.setStyleSheet("font-size: 14px;")
        layout.addWidget(nav_label)
        layout.addWidget(nav_input)
        
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save Changes")
        save_btn.clicked.connect(
            lambda: self.manage_mf_units(
                dialog, selected, action_combo.currentText(), 
                units_input.value(), nav_input.value()
            )
        )
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()    
        
    def manage_mf_units(self, dialog, row, action, units, nav):
        portfolio = self.mf_portfolio_combo.currentText()
        full_df = self.portfolios[portfolio]
        mf_indices = full_df[full_df['Scheme Code'].notna()].index
        
        if row >= len(mf_indices):
            return
            
        idx = mf_indices[row]
        mf_data = full_df.loc[idx].copy()
        
        if action == "Add Units":
            total_investment = mf_data['Invested'] + (units * nav)
            new_units = mf_data['Units'] + units
            new_avg_nav = total_investment / new_units
            
            self.portfolios[portfolio].at[idx, 'Units'] = new_units
            self.portfolios[portfolio].at[idx, 'Avg NAV'] = new_avg_nav
            self.portfolios[portfolio].at[idx, 'Invested'] = total_investment
            
            self.log_audit(
                "ADDED_MF_UNITS", portfolio, mf_data['Fund Name'],
                f"Added {units:.2f} units @ {nav:.2f}, New Units: {new_units:.2f}, New Avg NAV: {new_avg_nav:.2f}"
            )
            
            QMessageBox.information(self, "Success", f"Added {units:.2f} units to {mf_data['Fund Name']}")
        else:
            if units > mf_data['Units']:
                QMessageBox.warning(self, "Error", "Cannot remove more units than available!")
                return
                
            new_units = mf_data['Units'] - units
            if new_units <= 0.01:  # Consider anything less than 0.01 as zero
                self.portfolios[portfolio] = full_df.drop(idx).reset_index(drop=True)
                self.log_audit(
                    "REMOVED_ALL_MF_UNITS", portfolio, mf_data['Fund Name'],
                    f"Removed all {mf_data['Units']:.2f} units"
                )
                QMessageBox.information(self, "Success", f"Removed all units of {mf_data['Fund Name']}")
            else:
                remaining_investment = (new_units / mf_data['Units']) * mf_data['Invested']
                
                self.portfolios[portfolio].at[idx, 'Units'] = new_units
                self.portfolios[portfolio].at[idx, 'Invested'] = remaining_investment
                
                self.log_audit(
                    "REMOVED_MF_UNITS", portfolio, mf_data['Fund Name'],
                    f"Removed {units:.2f} units, Remaining: {new_units:.2f}"
                )
                QMessageBox.information(self, "Success", f"Removed {units:.2f} units from {mf_data['Fund Name']}")
        
        self.refresh_mf_table()
        dialog.accept()    

    def get_mf_data(self, portfolio):
        """Returns DataFrame with only mutual funds for the given portfolio"""
        if portfolio not in self.portfolios or 'Scheme Code' not in self.portfolios[portfolio].columns:
            return pd.DataFrame()
        return self.portfolios[portfolio][self.portfolios[portfolio]['Scheme Code'].notna()].copy()
        
    def create_dashboard_views(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        title = QLabel("Dashboard Views")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        self.dashboard_tabs = QTabWidget()
        
        # 1. Combined Dashboard
        self.combined_dashboard = QWidget()
        self.setup_combined_dashboard()
        self.dashboard_tabs.addTab(self.combined_dashboard, "Combined")
        
        # 2. Individual Dashboard
        self.individual_dashboard = QWidget()
        self.setup_individual_dashboard()
        self.dashboard_tabs.addTab(self.individual_dashboard, "Individual")
        
        # 3. Performance Charts
        self.charts_dashboard = QWidget()
        self.setup_charts_dashboard()
        self.dashboard_tabs.addTab(self.charts_dashboard, "Performance")
        
        # 4. Advanced Analysis
        self.advanced_analysis_dashboard = QWidget()
        self.setup_analysis_tab()
        self.dashboard_tabs.addTab(self.advanced_analysis_dashboard, "Advanced Analysis")
        
        layout.addWidget(self.dashboard_tabs)
        
        refresh_btn = QPushButton("Refresh All Dashboards")
        refresh_btn.clicked.connect(self.refresh_all_dashboards)
        layout.addWidget(refresh_btn)
        
        back_btn = QPushButton("Back to Main Menu")
        back_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        layout.addWidget(back_btn)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)
        
    def setup_combined_dashboard(self):
        page = self.combined_dashboard
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        summary_layout = QHBoxLayout()
        summary_layout.setSpacing(15)
        
        self.investment_card = self.create_summary_card("Total Invested", "₹0", "#1E88E5")
        self.current_value_card = self.create_summary_card("Current Value", "₹0", "#43A047")
        self.pl_card = self.create_summary_card("Profit/Loss", "₹0", "#4CAF50")
        self.daily_pl_card = self.create_summary_card("Today's P/L", "₹0", "#2196F3")
        
        summary_layout.addWidget(self.investment_card)
        summary_layout.addWidget(self.current_value_card)
        summary_layout.addWidget(self.pl_card)
        summary_layout.addWidget(self.daily_pl_card)
        layout.addLayout(summary_layout)
        
        table_frame = QFrame()
        table_frame.setFrameShape(QFrame.StyledPanel)
        table_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 5px;")
        table_layout = QVBoxLayout(table_frame)
        
        self.portfolio_table = QTableWidget()
        self.portfolio_table.setColumnCount(8)
        self.portfolio_table.setHorizontalHeaderLabels([
            "Portfolio", "Invested", "Current", "P/L", "P/L %", "Daily P/L", "Daily P/L %", "Status"
        ])
        self.portfolio_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.portfolio_table.verticalHeader().setVisible(False)
        
        table_layout.addWidget(self.portfolio_table)
        layout.addWidget(table_frame)
        
        refresh_btn = QPushButton("Refresh Data")
        refresh_btn.clicked.connect(self.refresh_dashboard_data)
        layout.addWidget(refresh_btn)
        
        page.setLayout(layout)
        
    def create_summary_card(self, title, value, color):
        card = QWidget()
        card.setStyleSheet(f"""
            background-color: {color};
            border-radius: 8px;
            padding: 15px;
        """)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: white;
        """)
        
        value_label = QLabel(value)
        value_label.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: white;
        """)
        
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        
        return card
        
    def update_summary_card(self, card, title, value, color=None):
        layout = card.layout()
        title_label = layout.itemAt(0).widget()
        value_label = layout.itemAt(1).widget()
        
        title_label.setText(title)
        value_label.setText(value)
        
        if color:
            card.setStyleSheet(f"""
                background-color: {color};
                border-radius: 8px;
                padding: 15px;
            """)
            
    def refresh_dashboard_data(self):
        all_tickers = []
        for portfolio in self.portfolios.values():
            all_tickers.extend(portfolio['Ticker Symbol'].tolist())
        
        if not all_tickers:
            QMessageBox.information(self, "Info", "No stocks in portfolios to fetch data for.")
            return
            
        worker = Worker(all_tickers)
        worker.data_fetched.connect(self.update_dashboard_with_prices)
        worker.finished_signal.connect(lambda: self.worker_finished(worker))
        self.workers.append(worker)
        worker.start()
        
    def update_dashboard_with_prices(self, prices):
        total_investment = 0
        total_current = 0
        total_pl = 0
        total_daily_pl = 0
        
        # Update column headers to include P/L %
        self.portfolio_table.setColumnCount(8)
        self.portfolio_table.setHorizontalHeaderLabels([
            "Portfolio", "Invested", "Current", "P/L", "P/L %", "Daily P/L", "Daily P/L %", "Status"
        ])
        
        self.portfolio_table.setRowCount(len(self.portfolios))
        for row, (name, portfolio) in enumerate(self.portfolios.items()):
            portfolio['Current Price'] = portfolio['Ticker Symbol'].map(prices).astype(float)
            portfolio['Current Value'] = (portfolio['Quantity'] * portfolio['Current Price']).astype(float)
            portfolio['Investment Value'] = (portfolio['Quantity'] * portfolio['Purchase Price']).astype(float)
            portfolio['Profit/Loss'] = (portfolio['Current Value'] - portfolio['Investment Value']).astype(float)
            
            if 'Daily P/L' not in portfolio:
                portfolio['Daily P/L'] = 0.0
            else:
                portfolio['Daily P/L'] = portfolio['Daily P/L'].astype(float)
            
            for idx, ticker in enumerate(portfolio['Ticker Symbol']):
                if pd.notna(portfolio.at[idx, 'Current Price']):
                    try:
                        stock = yf.Ticker(ticker)
                        hist = stock.history(period="2d")
                        if len(hist) >= 2:
                            prev_close = hist['Close'].iloc[-2]
                            daily_pl = (portfolio.at[idx, 'Current Price'] - prev_close) * portfolio.at[idx, 'Quantity']
                            portfolio.at[idx, 'Daily P/L'] = float(daily_pl)
                    except:
                        pass
            
            investment = portfolio['Investment Value'].sum()
            current = portfolio['Current Value'].sum()
            pl = portfolio['Profit/Loss'].sum()
            daily_pl = portfolio['Daily P/L'].sum()
            pl_pct = (pl / investment * 100) if investment > 0 else 0
            daily_pl_pct = (daily_pl / current * 100) if current > 0 else 0
            
            total_investment += investment
            total_current += current
            total_pl += pl
            total_daily_pl += daily_pl
            
            self.portfolio_table.setItem(row, 0, QTableWidgetItem(name))
            self.portfolio_table.setItem(row, 1, QTableWidgetItem(f"₹{investment:,.2f}"))
            self.portfolio_table.setItem(row, 2, QTableWidgetItem(f"₹{current:,.2f}"))
            
            pl_item = QTableWidgetItem(f"₹{pl:+,.2f}")
            pl_item.setForeground(QColor('#4CAF50') if pl >= 0 else QColor('#F44336'))
            self.portfolio_table.setItem(row, 3, pl_item)
            
            pl_pct_item = QTableWidgetItem(f"{pl_pct:+,.2f}%")
            pl_pct_item.setForeground(QColor('#4CAF50') if pl >= 0 else QColor('#F44336'))
            self.portfolio_table.setItem(row, 4, pl_pct_item)
            
            daily_item = QTableWidgetItem(f"₹{daily_pl:+,.2f}")
            daily_item.setForeground(QColor('#4CAF50') if daily_pl >= 0 else QColor('#F44336'))
            self.portfolio_table.setItem(row, 5, daily_item)
            
            daily_pct_item = QTableWidgetItem(f"{daily_pl_pct:+,.2f}%")
            daily_pct_item.setForeground(QColor('#4CAF50') if daily_pl >= 0 else QColor('#F44336'))
            self.portfolio_table.setItem(row, 6, daily_pct_item)
            
            status_item = QTableWidgetItem("↑" if pl >= 0 else "↓")
            status_item.setForeground(QColor('#4CAF50') if pl >= 0 else QColor('#F44336'))
            self.portfolio_table.setItem(row, 7, status_item)
        
        self.update_summary_card(self.investment_card, "Total Invested", f"₹{total_investment:,.2f}", "#1E88E5")
        self.update_summary_card(self.current_value_card, "Current Value", f"₹{total_current:,.2f}", "#43A047")
        
        pl_color = '#4CAF50' if total_pl >= 0 else '#F44336'
        pl_text = f"₹{total_pl:+,.2f}\n({total_pl/total_investment*100:.2f}%)" if total_investment else "₹0.00"
        self.update_summary_card(self.pl_card, "Profit/Loss", pl_text, pl_color)
        
        daily_color = '#4CAF50' if total_daily_pl >= 0 else '#F44336'
        daily_text = f"₹{total_daily_pl:+,.2f}\n({total_daily_pl/total_current*100:.2f}%)" if total_current else "₹0.00"
        self.update_summary_card(self.daily_pl_card, "Today's P/L", daily_text, daily_color)
        
        
    def setup_individual_dashboard(self):
        page = self.individual_dashboard
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        portfolio_frame = QFrame()
        portfolio_frame.setFrameShape(QFrame.StyledPanel)
        portfolio_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 5px; padding: 10px;")
        portfolio_layout = QHBoxLayout(portfolio_frame)
        
        portfolio_label = QLabel("Select Portfolio:")
        portfolio_label.setStyleSheet("font-size: 14px;")
        self.dashboard_portfolio_combo = QComboBox()
        self.dashboard_portfolio_combo.setStyleSheet("font-size: 14px;")
        self.dashboard_portfolio_combo.addItems(sorted(self.portfolios.keys()))
        self.dashboard_portfolio_combo.currentTextChanged.connect(self.refresh_individual_dashboard)
        
        portfolio_layout.addWidget(portfolio_label)
        portfolio_layout.addWidget(self.dashboard_portfolio_combo)
        portfolio_layout.addStretch()
        layout.addWidget(portfolio_frame)
        
        summary_layout = QHBoxLayout()
        summary_layout.setSpacing(15)
        
        self.individual_investment_card = self.create_summary_card("Invested", "₹0", "#1E88E5")
        self.individual_current_card = self.create_summary_card("Current", "₹0", "#43A047")
        self.individual_pl_card = self.create_summary_card("P/L", "₹0", "#4CAF50")
        self.individual_daily_card = self.create_summary_card("Today's P/L", "₹0", "#2196F3")
        
        summary_layout.addWidget(self.individual_investment_card)
        summary_layout.addWidget(self.individual_current_card)
        summary_layout.addWidget(self.individual_pl_card)
        summary_layout.addWidget(self.individual_daily_card)
        layout.addLayout(summary_layout)
        
        table_frame = QFrame()
        table_frame.setFrameShape(QFrame.StyledPanel)
        table_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 5px;")
        table_layout = QVBoxLayout(table_frame)
        
        self.individual_stock_table = QTableWidget()
        self.individual_stock_table.setColumnCount(7)
        self.individual_stock_table.setHorizontalHeaderLabels([
            "Stock", "Ticker", "Qty", "Avg Price", "Curr Price", "P/L", "Daily P/L"
        ])
        self.individual_stock_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.individual_stock_table.verticalHeader().setVisible(False)
        
        table_layout.addWidget(self.individual_stock_table)
        layout.addWidget(table_frame)
        
        refresh_btn = QPushButton("Refresh Data")
        refresh_btn.clicked.connect(self.refresh_individual_dashboard)
        layout.addWidget(refresh_btn)
        
        page.setLayout(layout)
        
    def refresh_individual_dashboard(self):
        portfolio = self.dashboard_portfolio_combo.currentText()
        if not portfolio or portfolio not in self.portfolios:
            return
            
        df = self.portfolios[portfolio]
        if len(df) == 0:
            return
            
        tickers = df['Ticker Symbol'].tolist()
        worker = Worker(tickers)
        worker.data_fetched.connect(
            lambda prices: self.update_individual_dashboard(portfolio, prices)
        )
        worker.finished_signal.connect(lambda: self.worker_finished(worker))
        self.workers.append(worker)
        worker.start()
        
    def update_individual_dashboard(self, portfolio, prices):
        df = self.portfolios[portfolio].copy()
        df['Current Price'] = df['Ticker Symbol'].map(prices)
        df['Current Value'] = df['Quantity'] * df['Current Price']
        df['Profit/Loss'] = df['Current Value'] - df['Investment Value']
        
        df['Daily P/L'] = 0
        for idx, ticker in enumerate(df['Ticker Symbol']):
            if pd.notna(df.at[idx, 'Current Price']):
                try:
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period="2d")
                    if len(hist) >= 2:
                        prev_close = hist['Close'].iloc[-2]
                        daily_pl = (df.at[idx, 'Current Price'] - prev_close) * df.at[idx, 'Quantity']
                        df.at[idx, 'Daily P/L'] = daily_pl
                except:
                    pass
        
        investment = df['Investment Value'].sum()
        current = df['Current Value'].sum()
        pl = df['Profit/Loss'].sum()
        daily_pl = df['Daily P/L'].sum()
        pl_pct = (pl / investment * 100) if investment > 0 else 0
        daily_pl_pct = (daily_pl / current * 100) if current > 0 else 0
        
        self.update_summary_card(self.individual_investment_card, "Invested", f"₹{investment:,.2f}", "#1E88E5")
        self.update_summary_card(self.individual_current_card, "Current", f"₹{current:,.2f}", "#43A047")
        
        pl_color = '#4CAF50' if pl >= 0 else '#F44336'
        pl_text = f"₹{pl:+,.2f}\n({pl_pct:+.2f}%)" if investment else "₹0.00"
        self.update_summary_card(self.individual_pl_card, "P/L", pl_text, pl_color)
        
        daily_color = '#4CAF50' if daily_pl >= 0 else '#F44336'
        daily_text = f"₹{daily_pl:+,.2f}\n({daily_pl_pct:+.2f}%)" if current else "₹0.00"
        self.update_summary_card(self.individual_daily_card, "Today's P/L", daily_text, daily_color)
        
        # Update table columns
        self.individual_stock_table.setColumnCount(9)
        self.individual_stock_table.setHorizontalHeaderLabels([
            "Stock", "Ticker", "Qty", "Avg Price", "Curr Price", "P/L", "P/L %", "Daily P/L", "Daily P/L %"
        ])
        
        self.individual_stock_table.setRowCount(len(df))
        for row in range(len(df)):
            stock = df.iloc[row]
            
            self.individual_stock_table.setItem(row, 0, QTableWidgetItem(stock['Stock Name']))
            self.individual_stock_table.setItem(row, 1, QTableWidgetItem(stock['Ticker Symbol']))
            self.individual_stock_table.setItem(row, 2, QTableWidgetItem(str(stock['Quantity'])))
            self.individual_stock_table.setItem(row, 3, QTableWidgetItem(f"{stock['Purchase Price']:.2f}"))
            
            if pd.notna(stock['Current Price']):
                self.individual_stock_table.setItem(row, 4, QTableWidgetItem(f"{stock['Current Price']:.2f}"))
                
                pl_item = QTableWidgetItem(f"{stock['Profit/Loss']:+,.2f}")
                pl_item.setForeground(QColor('#4CAF50') if stock['Profit/Loss'] >= 0 else QColor('#F44336'))
                self.individual_stock_table.setItem(row, 5, pl_item)
                
                pl_pct = (stock['Profit/Loss'] / (stock['Quantity'] * stock['Purchase Price']) * 100) if (stock['Quantity'] * stock['Purchase Price']) > 0 else 0
                pl_pct_item = QTableWidgetItem(f"{pl_pct:+,.2f}%")
                pl_pct_item.setForeground(QColor('#4CAF50') if stock['Profit/Loss'] >= 0 else QColor('#F44336'))
                self.individual_stock_table.setItem(row, 6, pl_pct_item)
                
                daily_item = QTableWidgetItem(f"{stock['Daily P/L']:+,.2f}")
                daily_item.setForeground(QColor('#4CAF50') if stock['Daily P/L'] >= 0 else QColor('#F44336'))
                self.individual_stock_table.setItem(row, 7, daily_item)
                
                daily_pct = (stock['Daily P/L'] / (stock['Quantity'] * stock['Current Price']) * 100) if (stock['Quantity'] * stock['Current Price']) > 0 else 0
                daily_pct_item = QTableWidgetItem(f"{daily_pct:+,.2f}%")
                daily_pct_item.setForeground(QColor('#4CAF50') if stock['Daily P/L'] >= 0 else QColor('#F44336'))
                self.individual_stock_table.setItem(row, 8, daily_pct_item)
            else:
                for col in range(4, 9):
                    self.individual_stock_table.setItem(row, col, QTableWidgetItem("N/A"))
                    
    def setup_charts_dashboard(self):
        page = self.charts_dashboard
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        portfolio_frame = QFrame()
        portfolio_frame.setFrameShape(QFrame.StyledPanel)
        portfolio_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 5px; padding: 10px;")
        portfolio_layout = QHBoxLayout(portfolio_frame)
        
        portfolio_label = QLabel("Select Portfolio:")
        portfolio_label.setStyleSheet("font-size: 14px;")
        self.chart_portfolio_combo = QComboBox()
        self.chart_portfolio_combo.setStyleSheet("font-size: 14px;")
        self.chart_portfolio_combo.addItems(sorted(self.portfolios.keys()))
        self.chart_portfolio_combo.currentTextChanged.connect(self.update_charts)
        
        portfolio_layout.addWidget(portfolio_label)
        portfolio_layout.addWidget(self.chart_portfolio_combo)
        portfolio_layout.addStretch()
        layout.addWidget(portfolio_frame)
        
        self.chart_tabs = QTabWidget()
        
        # Allocation Chart
        allocation_tab = QWidget()
        allocation_layout = QVBoxLayout(allocation_tab)
        self.allocation_chart = FigureCanvas(Figure(figsize=(10, 6)))
        allocation_layout.addWidget(self.allocation_chart)
        self.chart_tabs.addTab(allocation_tab, "Allocation")
        
        # Performance Chart
        performance_tab = QWidget()
        performance_layout = QVBoxLayout(performance_tab)
        self.performance_chart = FigureCanvas(Figure(figsize=(10, 6)))
        performance_layout.addWidget(self.performance_chart)
        self.chart_tabs.addTab(performance_tab, "Performance")
        
        # Sector Chart
        sector_tab = QWidget()
        sector_layout = QVBoxLayout(sector_tab)
        self.sector_chart = FigureCanvas(Figure(figsize=(10, 6)))
        sector_layout.addWidget(self.sector_chart)
        self.chart_tabs.addTab(sector_tab, "Sector")
        
        # Daily P/L Chart
        daily_pl_tab = QWidget()
        daily_pl_layout = QVBoxLayout(daily_pl_tab)
        self.daily_pl_chart = FigureCanvas(Figure(figsize=(10, 6)))
        daily_pl_layout.addWidget(self.daily_pl_chart)
        self.chart_tabs.addTab(daily_pl_tab, "Daily P/L")
        
        layout.addWidget(self.chart_tabs)
        
        refresh_btn = QPushButton("Refresh Charts")
        refresh_btn.clicked.connect(self.update_charts)
        layout.addWidget(refresh_btn)
        
        page.setLayout(layout)
        self.update_charts()
            
    def update_charts(self):
        portfolio = self.chart_portfolio_combo.currentText()
        if not portfolio or portfolio not in self.portfolios:
            return
            
        df = self.portfolios[portfolio]
        
        # Ensure we have required columns
        if 'Current Price' not in df.columns:
            df['Current Price'] = df['Purchase Price']
        if 'Current Value' not in df.columns:
            df['Current Value'] = df['Quantity'] * df['Current Price']
            
        self.plot_allocation_chart(df)
        self.plot_performance_chart(df)
        self.plot_sector_chart(df)
        self.plot_daily_pl_chart(df)
        
    def plot_allocation_chart(self, data):
        fig = self.allocation_chart.figure
        fig.clear()
        fig.set_facecolor('#1E1E1E')
        
        ax = fig.add_subplot(111)
        ax.set_facecolor('#1E1E1E')
        
        try:
            # Calculate current values if not available
            if 'Current Value' not in data.columns:
                if 'Quantity' in data.columns and 'Current Price' in data.columns:
                    data['Current Value'] = data['Quantity'] * data['Current Price']
                elif 'Quantity' in data.columns and 'Purchase Price' in data.columns:
                    data['Current Value'] = data['Quantity'] * data['Purchase Price']
            else:
                    raise ValueError("Missing required columns for value calculation")
            
            # Filter out zero holdings and NaN values
            valid_data = data[
                (data['Quantity'] > 0) & 
                (data['Current Value'].notna()) & 
                (data['Current Value'] > 0)
            ].copy()
            
            if len(valid_data) == 0:
                ax.text(0.5, 0.5, "No valid holdings data available", 
                    ha='center', va='center', fontsize=12, color='white')
                    fig.tight_layout()
                    self.allocation_chart.draw()
                    return
                    
            # Sort by value and group small holdings into "Others"
            valid_data = valid_data.sort_values('Current Value', ascending=False)
            if len(valid_data) > 8:
                main_holdings = valid_data.head(7)
                others_value = valid_data['Current Value'].iloc[7:].sum()
                if others_value > 0:  # Only include "Others" if it has value
                    others = pd.DataFrame({
                        'Stock Name': ['Others'],
                        'Current Value': [others_value]
                    })
                    valid_data = pd.concat([main_holdings, others])
            
            # Create clean pie chart with improved styling
            colors = plt.cm.tab20c(np.linspace(0, 1, len(valid_data)))
                wedges, texts, autotexts = ax.pie(
                valid_data['Current Value'],
                labels=None,  # We'll use legend instead
                autopct=lambda p: f'₹{p * sum(valid_data["Current Value"])/100:,.0f}\n({p:.1f}%)' if p >= 5 else '',
                    startangle=90,
                counterclock=False,
                wedgeprops={'linewidth': 0.8, 'edgecolor': '#333'},
                    colors=colors,
                textprops={'fontsize': 9, 'color': 'white'},
                pctdistance=0.8
            )
            
            # Create legend with stock names and values
            legend_labels = [
                f"{row['Stock Name']} (₹{row['Current Value']:,.0f})" 
                for _, row in valid_data.iterrows()
            ]
            
            ax.legend(
                wedges, 
                legend_labels,
                title="Holdings",
                loc="center left",
                bbox_to_anchor=(1, 0.5),
                frameon=False,
                labelcolor='white'
            )
            
            # Style the percentage labels
                for autotext in autotexts:
                    autotext.set_color('white')
                autotext.set_fontsize(9)
                autotext.set_bbox(dict(facecolor='#333', alpha=0.7, edgecolor='none'))
                
            ax.set_title("Portfolio Allocation (Current Value)", 
                    fontsize=14, color='white', pad=20)
                
        except Exception as e:
            print(f"Error plotting allocation chart: {str(e)}")
            ax.text(0.5, 0.5, "Error displaying chart", 
                ha='center', va='center', fontsize=12, color='white')
            
        fig.tight_layout()
        self.allocation_chart.draw()


    def plot_performance_chart(self, df):
        fig = self.performance_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        ax.set_facecolor('#1E1E1E')
        
        try:
            if 'Profit/Loss' not in df.columns:
                if 'Quantity' in df.columns and 'Current Price' in df.columns and 'Purchase Price' in df.columns:
                    df['Profit/Loss'] = (df['Quantity'] * df['Current Price']) - (df['Quantity'] * df['Purchase Price'])
            else:
                    raise ValueError("Missing required columns for P/L calculation")
            
            # Filter valid data
            valid_data = df[
                (df['Quantity'] > 0) & 
                (df['Profit/Loss'].notna())
            ].copy()
            
            if len(valid_data) == 0:
                ax.text(0.5, 0.5, "No valid performance data available", 
                    ha='center', va='center', fontsize=12, color='white')
                    fig.tight_layout()
                self.performance_chart.draw()
                    return
                    
            valid_data = valid_data.sort_values('Profit/Loss', ascending=False)
            colors = ['#4CAF50' if x >= 0 else '#F44336' for x in valid_data['Profit/Loss']]
                
                bars = ax.bar(
                valid_data['Stock Name'],
                valid_data['Profit/Loss'],
                    color=colors,
                    width=0.6
                )
                
                ax.axhline(0, color='white', linestyle='--', linewidth=1)
            ax.set_title("Profit/Loss by Stock", fontsize=14, color='white', pad=20)
                ax.set_ylabel("P/L (₹)", color='white')
                ax.tick_params(axis='x', rotation=45, colors='white')
                ax.tick_params(axis='y', colors='white')
            ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'₹{x:,.0f}'))
                
                for spine in ax.spines.values():
                    spine.set_color('#333')
                
                for bar in bars:
                    height = bar.get_height()
                    ax.text(
                        bar.get_x() + bar.get_width()/2.,
                    height + (0.02 * height if height >=0 else -0.02 * height),
                        f"₹{height:+,.0f}",
                    ha='center', va='center',
                        fontsize=9,
                    color='white'
                    )
                    
        except Exception as e:
            print(f"Error plotting performance chart: {str(e)}")
            ax.text(0.5, 0.5, "Error displaying chart", 
                ha='center', va='center', fontsize=12, color='white')
            
        fig.tight_layout()
        self.performance_chart.draw()
    
    def plot_sector_chart(self, df):
        """Plot sector allocation with proper error handling"""
        try:
            fig = self.sector_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        
            # Filter out NaN values and ensure we have data
            if df is None or df.empty:
                ax.text(0.5, 0.5, "No data available", 
                    ha='center', va='center', fontsize=12)
                fig.tight_layout()
                self.sector_chart.draw()
                return
                
            # Clean the data
            df = df.copy()
            df['Current Value'] = df['Quantity'] * df['Purchase Price']
            df = df[df['Quantity'] > 0]  # Only active holdings
            
            if 'Sector' not in df.columns or df['Sector'].isnull().all():
                ax.text(0.5, 0.5, "No sector data available", 
                    ha='center', va='center', fontsize=12)
                fig.tight_layout()
                self.sector_chart.draw()
                return
            
            # Group by sector and handle NaN values
            sector_data = df.groupby('Sector', dropna=True)['Current Value'].sum()
            sector_data = sector_data[sector_data > 0]  # Remove zero values
            
            if len(sector_data) == 0:
                ax.text(0.5, 0.5, "No valid sector data", 
                        ha='center', va='center', fontsize=12)
                    fig.tight_layout()
                self.sector_chart.draw()
                    return
                    
            # Sort by value
            sector_data = sector_data.sort_values(ascending=False)
            
            # Create the pie chart
            colors = plt.cm.tab20c(range(len(sector_data)))
            wedges, texts, autotexts = ax.pie(
                sector_data.values,
                labels=sector_data.index,
                autopct=lambda p: f'₹{p * sum(sector_data)/100:,.0f}\n({p:.1f}%)',
                startangle=90,
                wedgeprops={'linewidth': 1, 'edgecolor': '#121212'},
                colors=colors,
                textprops={'fontsize': 8},
                pctdistance=0.85,
                labeldistance=1.05
            )
            
            # Style the text
            for text in texts:
                text.set_color('white')
                text.set_fontsize(9)
                text.set_bbox(dict(facecolor='#1E1E1E', alpha=0.7, edgecolor='none'))
            
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontsize(8)
            
            ax.set_title("Sector Allocation", fontsize=14, color='white', pad=20)
            
        except Exception as e:
            print(f"Error plotting sector allocation: {str(e)}")
            if 'ax' in locals():
                ax.text(0.5, 0.5, "Error displaying chart", 
                    ha='center', va='center', fontsize=12)
        
        try:
            fig.tight_layout()
            self.sector_chart.draw()
        except Exception as e:
            print(f"Error in tight_layout: {str(e)}")
            self.sector_chart.draw()
         
    def plot_daily_pl_chart(self, data):
        fig = self.daily_pl_chart.figure
        fig.clear()
        
        try:
            ax = fig.add_subplot(111)
            
            # Calculate daily P/L for each stock
            daily_pl = []
            for _, row in data.iterrows():
                try:
                    stock = yf.Ticker(row['Ticker Symbol'])
                    hist = stock.history(period="2d")
                    if len(hist) >= 2:
                        current = hist['Close'].iloc[-1]
                        prev_close = hist['Close'].iloc[-2]
                        change = (current - prev_close) * row['Quantity']
                        daily_pl.append({
                            'Stock': row['Stock Name'],
                            'Change': change,
                            'Color': '#4CAF50' if change >= 0 else '#F44336'
                        })
                except:
                    pass
            
            if not daily_pl:
                ax.text(0.5, 0.5, "No daily P/L data available", 
                    ha='center', va='center', fontsize=12)
                fig.tight_layout()
                self.daily_pl_chart.draw()
                return
                
            # Convert to DataFrame and sort
            daily_pl_df = pd.DataFrame(daily_pl).sort_values('Change', ascending=True)
            
            # Limit to top 15 performers (positive and negative)
            daily_pl_df = pd.concat([
                daily_pl_df.head(8),  # Worst performers
                daily_pl_df.tail(8)   # Best performers
            ]).drop_duplicates()
            
            # Create horizontal bar chart
            y_pos = np.arange(len(daily_pl_df))
            bars = ax.barh(
                y_pos,
                daily_pl_df['Change'],
                color=daily_pl_df['Color'],
                height=0.6
            )
            
            # Add value labels on the bars
            for i, (_, row) in enumerate(daily_pl_df.iterrows()):
                x_pos = row['Change'] * 0.95 if row['Change'] >=0 else row['Change'] * 1.05
                ax.text(
                    x_pos, 
                    i,
                    f"₹{abs(row['Change']):,.0f}",
                    va='center',
                    ha='right' if row['Change'] >=0 else 'left',
                    fontsize=9,
                    color='white'
                )
            
            # Formatting
            ax.set_yticks(y_pos)
            ax.set_yticklabels(daily_pl_df['Stock'], fontsize=9)
            ax.set_xlabel('Daily Profit/Loss (₹)', color='white')
            ax.set_title("Today's Top/Bottom Performers", fontsize=14, color='white', pad=20)
            ax.axvline(0, color='white', linestyle='--', linewidth=1)
            
            # Styling
            ax.set_facecolor('#1E1E1E')
            ax.grid(axis='x', color='#333', linestyle='--', alpha=0.3)
            for spine in ax.spines.values():
                spine.set_color('#333')
                
            fig.tight_layout()
            
        except Exception as e:
            print(f"Error plotting daily P/L chart: {str(e)}")
            ax.text(0.5, 0.5, "Error displaying chart", 
                ha='center', va='center', fontsize=12)
        
        self.daily_pl_chart.draw()

    def setup_analysis_tab(self):
        page = self.advanced_analysis_dashboard
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Tab widget for different analysis views
        analysis_tabs = QTabWidget()
        
        # 1. Portfolio Trends
        trends_tab = QWidget()
        trends_layout = QVBoxLayout(trends_tab)
        self.trends_chart = FigureCanvas(Figure(figsize=(10, 6), tight_layout=True))
        trends_layout.addWidget(self.trends_chart)
        analysis_tabs.addTab(trends_tab, "Portfolio Trends")
        
        # 2. Sector Allocation
        sector_tab = QWidget()
        sector_layout = QVBoxLayout(sector_tab)
        self.sector_chart = FigureCanvas(Figure(figsize=(10, 6), tight_layout=True))
        sector_layout.addWidget(self.sector_chart)
        analysis_tabs.addTab(sector_tab, "Sector Allocation")
        
        # 3. Company Exposure
        company_tab = QWidget()
        company_layout = QVBoxLayout(company_tab)
        self.company_chart = FigureCanvas(Figure(figsize=(10, 6), tight_layout=True))
        company_layout.addWidget(self.company_chart)
        analysis_tabs.addTab(company_tab, "Company Exposure")
        
        # 4. Historical Performance
        historical_tab = QWidget()
        historical_layout = QVBoxLayout(historical_tab)
        self.historical_chart = FigureCanvas(Figure(figsize=(10, 6), tight_layout=True))
        historical_layout.addWidget(self.historical_chart)
        analysis_tabs.addTab(historical_tab, "Historical Trends")
        
        layout.addWidget(analysis_tabs)
        
        # Add description label
        desc_label = QLabel(
            "Advanced analysis tools for portfolio optimization. "
            "Hover over charts for detailed information."
        )
        desc_label.setStyleSheet("font-size: 12px; color: #AAAAAA;")
        desc_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_label)
        
        # Add control buttons
        btn_layout = QHBoxLayout()
        
        export_btn = QPushButton("Export Analysis")
        export_btn.setIcon(QIcon.fromTheme("document-save"))
        export_btn.clicked.connect(self.export_analysis_images)
        btn_layout.addWidget(export_btn)
        
        refresh_btn = QPushButton("Refresh Analysis")
        refresh_btn.setIcon(QIcon.fromTheme("view-refresh"))
        refresh_btn.clicked.connect(self.update_analysis_charts)
        btn_layout.addWidget(refresh_btn)
        
        layout.addLayout(btn_layout)
        page.setLayout(layout)
        
        # Initial chart update
        self.update_analysis_charts()
    
    def update_analysis_charts(self):
        # Combine all portfolio data
        all_holdings = pd.DataFrame()
        for portfolio_name, portfolio_data in self.portfolios.items():
            if not portfolio_data.empty:
                temp_df = portfolio_data.copy()
                temp_df['Portfolio'] = portfolio_name
                all_holdings = pd.concat([all_holdings, temp_df])
        
        if all_holdings.empty:
            return
        
        # Calculate current values if not already present
        if 'Current Value' not in all_holdings.columns:
            all_holdings['Current Value'] = all_holdings['Quantity'] * all_holdings['Purchase Price']
        
        # 1. Plot Portfolio Trends
        self.plot_portfolio_trends(all_holdings)
        
        # 2. Plot Sector Allocation
        self.plot_sector_allocation(all_holdings)
        
        # 3. Plot Company Exposure
        self.plot_company_exposure(all_holdings)
        
        # 4. Plot Historical Performance
        self.plot_historical_performance(all_holdings)
        
    def plot_portfolio_trends(self, data):
        fig = self.trends_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        
        try:
            # Group by portfolio and calculate metrics
            portfolio_stats = data.groupby('Portfolio').agg({
                'Investment Value': 'sum',
                'Current Value': 'sum'
            }).reset_index()
            
            portfolio_stats['P/L'] = portfolio_stats['Current Value'] - portfolio_stats['Investment Value']
            portfolio_stats['P/L %'] = (portfolio_stats['P/L'] / portfolio_stats['Investment Value']) * 100
            portfolio_stats = portfolio_stats.sort_values('Current Value', ascending=False)
            
            # Portfolio Value Comparison
                bars = ax.bar(
                portfolio_stats['Portfolio'],
                portfolio_stats['Current Value'],
                color='#1E88E5'
            )
            
            # Add P/L indicators
            for i, (_, row) in enumerate(portfolio_stats.iterrows()):
                pl_color = '#4CAF50' if row['P/L'] >= 0 else '#F44336'
                ax.text(
                    i, 
                    row['Current Value'] * 1.05, 
                    f"₹{row['P/L']:+,.0f} ({row['P/L %']:+.1f}%)",
                    ha='center',
                    color=pl_color,
                    fontsize=9
                )
            
            ax.set_title("Portfolio Value Comparison", fontsize=14, color='white')
            ax.set_ylabel("Current Value (₹)", color='white')
                ax.tick_params(axis='x', rotation=45, colors='white')
                ax.tick_params(axis='y', colors='white')
                ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'₹{x:,.0f}'))
                
                for spine in ax.spines.values():
                    spine.set_color('#333')
                    
        except Exception as e:
            print(f"Error plotting portfolio trends: {str(e)}")
            ax.text(0.5, 0.5, "Error displaying chart", 
                ha='center', va='center', fontsize=12)
            
        fig.tight_layout()
        self.trends_chart.draw()
    
    def plot_sector_allocation(self, data):
        """Plot sector allocation with proper error handling"""
        try:
        fig = self.sector_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        
            # Filter out NaN values and ensure we have data
            if data is None or data.empty:
                ax.text(0.5, 0.5, "No data available", 
                    ha='center', va='center', fontsize=12)
                fig.tight_layout()
                self.sector_chart.draw()
                return
                
            # Clean the data
            df = data.copy()
                df['Current Value'] = df['Quantity'] * df['Purchase Price']
            df = df[df['Quantity'] > 0]  # Only active holdings
            
            if 'Sector' not in df.columns or df['Sector'].isnull().all():
                ax.text(0.5, 0.5, "No sector data available", 
                        ha='center', va='center', fontsize=12)
                    fig.tight_layout()
                    self.sector_chart.draw()
                    return
                    
            # Group by sector and handle NaN values
            sector_data = df.groupby('Sector', dropna=True)['Current Value'].sum()
            sector_data = sector_data[sector_data > 0]  # Remove zero values
                
                if len(sector_data) == 0:
                    ax.text(0.5, 0.5, "No valid sector data", 
                        ha='center', va='center', fontsize=12)
                    fig.tight_layout()
                    self.sector_chart.draw()
                    return
                    
            # Sort by value
            sector_data = sector_data.sort_values(ascending=False)
                
            # Create the pie chart
            colors = plt.cm.tab20c(range(len(sector_data)))
            wedges, texts, autotexts = ax.pie(
                    sector_data.values,
                labels=sector_data.index,
                autopct=lambda p: f'₹{p * sum(sector_data)/100:,.0f}\n({p:.1f}%)',
                startangle=90,
                wedgeprops={'linewidth': 1, 'edgecolor': '#121212'},
                colors=colors,
                textprops={'fontsize': 8},
                pctdistance=0.85,
                labeldistance=1.05
            )
            
            # Style the text
            for text in texts:
                text.set_color('white')
                text.set_fontsize(9)
                text.set_bbox(dict(facecolor='#1E1E1E', alpha=0.7, edgecolor='none'))
            
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontsize(8)
            
            ax.set_title("Sector Allocation", fontsize=14, color='white', pad=20)
            
        except Exception as e:
            print(f"Error plotting sector allocation: {str(e)}")
            if 'ax' in locals():
                ax.text(0.5, 0.5, "Error displaying chart", 
                    ha='center', va='center', fontsize=12)
        
        try:
            fig.tight_layout()
            self.sector_chart.draw()
        except Exception as e:
            print(f"Error in tight_layout: {str(e)}")
            self.sector_chart.draw()
    
    def plot_company_exposure(self, data):
        fig = self.company_chart.figure
        fig.clear()
        
        try:
            ax = fig.add_subplot(111)
            
            # Ensure we have the required columns
            if 'Current Value' not in data.columns:
                if 'Quantity' in data.columns and 'Purchase Price' in data.columns:
                    data['Current Value'] = data['Quantity'] * data['Purchase Price']
                else:
                    raise ValueError("Missing required columns for value calculation")
            
            if 'Stock Name' not in data.columns:
                if 'Fund Name' in data.columns:  # For mutual funds
                    data['Stock Name'] = data['Fund Name']
                else:
                    raise ValueError("Missing stock/fund name column")
            
            # Group by company name to combine holdings across portfolios
            combined_holdings = data.groupby('Stock Name')['Current Value'].sum().sort_values(ascending=False)
            
            # Limit to top 15 for readability
            top_holdings = combined_holdings.head(15)
            
            if len(top_holdings) == 0:
                ax.text(0.5, 0.5, "No holdings data available", 
                    ha='center', va='center', fontsize=12)
                fig.tight_layout()
                self.company_chart.draw()
                return
                
            # Calculate percentage of total portfolio
            total_value = top_holdings.sum()
            top_holdings = pd.DataFrame({
                'Current Value': top_holdings,
                'Percentage': (top_holdings / total_value) * 100
            })
            
            # Create horizontal bar chart
            y_pos = np.arange(len(top_holdings))
            colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(top_holdings)))
            
            bars = ax.barh(
                y_pos,
                top_holdings['Current Value'],
                color=colors,
                height=0.7,
                edgecolor='#333',
                linewidth=0.7
            )
            
            # Add value and percentage labels
            for i, (company, row) in enumerate(top_holdings.iterrows()):
                    ax.text(
                    row['Current Value'] * 1.01, 
                    i,
                    f"₹{row['Current Value']:,.0f} ({row['Percentage']:.1f}%)",
                    va='center',
                        fontsize=9,
                        color='white'
                    )
                    
            # Formatting
            ax.set_yticks(y_pos)
            ax.set_yticklabels(top_holdings.index, fontsize=10)
            ax.set_xlabel('Current Value (₹)', color='white', fontsize=11)
            ax.set_title('Top Holdings by Value (Combined Across Portfolios)', fontsize=14, color='white', pad=20)
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'₹{x:,.0f}'))
            
            # Add grid lines
            ax.grid(axis='x', color='#444', linestyle=':', alpha=0.5)
            
            # Customize spines
            for spine in ax.spines.values():
                spine.set_color('#555')
                spine.set_linewidth(0.8)
            
            # Set background color
            ax.set_facecolor('#1E1E1E')
            fig.patch.set_facecolor('#1E1E1E')
            
            # Add a subtle watermark
            ax.text(
                0.5, 0.5, 'Portfolio Tracker',
                transform=ax.transAxes,
                fontsize=40,
                color='#333',
                alpha=0.1,
                ha='center',
                va='center',
                rotation=30
            )
            
            fig.tight_layout()
                    
        except Exception as e:
            print(f"Error plotting company exposure: {str(e)}")
            ax.text(0.5, 0.5, "Error displaying chart", 
                ha='center', va='center', fontsize=12)
            ax.set_facecolor('#1E1E1E')
        
        self.company_chart.draw()

    def plot_historical_performance(self, data):
        fig = self.historical_chart.figure
        fig.clear()
        
        try:
            ax = fig.add_subplot(111)
            
            # This is a placeholder - in a real app you would fetch historical data
            # For now we'll simulate some performance data
            dates = pd.date_range(end=datetime.today(), periods=30, freq='D')
            performance = np.cumsum(np.random.randn(30) * 10000 + 5000)
            
            ax.plot(
                dates, 
                performance, 
                color='#4CAF50',
                linewidth=2,
                marker='o',
                markersize=5,
                markerfacecolor='#1E88E5'
            )
            
            # Formatting
            ax.set_title('Simulated Portfolio Performance', fontsize=14, color='white', pad=20)
            ax.set_ylabel('Portfolio Value (₹)', color='white')
            ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'₹{x:,.0f}'))
            
            # Format x-axis dates
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%b'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
            
            # Styling
            ax.set_facecolor('#1E1E1E')
            ax.grid(color='#333', linestyle='--', alpha=0.5)
            ax.tick_params(axis='x', colors='white', rotation=45)
            ax.tick_params(axis='y', colors='white')
            
            for spine in ax.spines.values():
                spine.set_color('#333')
                
        except Exception as e:
            print(f"Error plotting historical performance: {str(e)}")
            ax.text(0.5, 0.5, "Error displaying chart", 
                ha='center', va='center', fontsize=12)
            
        fig.tight_layout()
        self.historical_chart.draw()
    
    def export_analysis_images(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Analysis Report",
            "",
            "PDF Files (*.pdf);;PNG Files (*.png)",
            options=options
        )
        
        if not file_path:
            return
            
        try:
            if file_path.lower().endswith('.pdf'):
                from matplotlib.backends.backend_pdf import PdfPages
                with PdfPages(file_path) as pdf:
                    for fig in [self.trends_chart.figure, self.sector_chart.figure, 
                               self.company_chart.figure, self.historical_chart.figure]:
                        fig.savefig(pdf, format='pdf', bbox_inches='tight')
            else:
                # Save as individual PNG files
                base_path = file_path.replace('.png', '')
                self.trends_chart.figure.savefig(f"{base_path}_trends.png", bbox_inches='tight')
                self.sector_chart.figure.savefig(f"{base_path}_sector.png", bbox_inches='tight')
                self.company_chart.figure.savefig(f"{base_path}_company.png", bbox_inches='tight')
                self.historical_chart.figure.savefig(f"{base_path}_historical.png", bbox_inches='tight')
                
            QMessageBox.information(self, "Success", "Analysis exported successfully!")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to export analysis: {str(e)}")
         
    def create_market_analysis(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        title = QLabel("Market Analysis")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        self.market_tabs = QTabWidget()
        
        # Indian Market Tab
        indian_tab = QWidget()
        indian_layout = QVBoxLayout(indian_tab)
        self.indian_market_table = QTableWidget()
        self.indian_market_table.setColumnCount(6)
        self.indian_market_table.setHorizontalHeaderLabels([
            "Index", "Current", "Change", "% Change", "Status", "Market Hours"
        ])
        self.indian_market_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.indian_market_table.verticalHeader().setVisible(False)
        indian_layout.addWidget(self.indian_market_table)
        self.market_tabs.addTab(indian_tab, "Indian Market")
        
        # Global Market Tab
        global_tab = QWidget()
        global_layout = QVBoxLayout(global_tab)
        self.global_market_table = QTableWidget()
        self.global_market_table.setColumnCount(6)
        self.global_market_table.setHorizontalHeaderLabels([
            "Index", "Current", "Change", "% Change", "Status", "Market Hours"
        ])
        self.global_market_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.global_market_table.verticalHeader().setVisible(False)
        global_layout.addWidget(self.global_market_table)
        self.market_tabs.addTab(global_tab, "Global Markets")
        
        # Stock Scanner Tab
        scanner_tab = QWidget()
        scanner_layout = QVBoxLayout(scanner_tab)
        
        scanner_controls = QHBoxLayout()
        self.scanner_category = QComboBox()
        self.scanner_category.addItems(["Gainers", "Losers", "Most Active", "52 Week High", "52 Week Low"])
        scanner_controls.addWidget(QLabel("Category:"))
        scanner_controls.addWidget(self.scanner_category)
        
        self.scanner_exchange = QComboBox()
        self.scanner_exchange.addItems(["NSE", "BSE", "NASDAQ", "NYSE"])
        scanner_controls.addWidget(QLabel("Exchange:"))
        scanner_controls.addWidget(self.scanner_exchange)
        
        scan_btn = QPushButton("Scan")
        scan_btn.clicked.connect(self.run_stock_scanner)
        scanner_controls.addWidget(scan_btn)
        scanner_controls.addStretch()
        
        scanner_layout.addLayout(scanner_controls)
        
        self.scanner_table = QTableWidget()
        self.scanner_table.setColumnCount(6)
        self.scanner_table.setHorizontalHeaderLabels([
            "Symbol", "Name", "Price", "Change", "% Change", "Volume"
        ])
        self.scanner_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.scanner_table.verticalHeader().setVisible(False)
        scanner_layout.addWidget(self.scanner_table)
        
        self.market_tabs.addTab(scanner_tab, "Stock Scanner")
        
        layout.addWidget(self.market_tabs)
        
        refresh_btn = QPushButton("Refresh Market Data")
        refresh_btn.clicked.connect(self.refresh_market_data)
        layout.addWidget(refresh_btn)
        
        back_btn = QPushButton("Back to Main Menu")
        back_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        layout.addWidget(back_btn)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)
        
        # Load initial data
        self.refresh_indian_market_data()
        self.refresh_global_market_data()
        
        tech_analysis_tab = QWidget()
        tech_layout = QVBoxLayout(tech_analysis_tab)
        
        # Stock selection
        stock_select_layout = QHBoxLayout()
        stock_select_layout.addWidget(QLabel("Select Stock:"))
        
        self.ta_stock_input = QLineEdit()
        self.ta_stock_input.setPlaceholderText("Enter symbol (e.g. RELIANCE.NS, AAPL)")
        stock_select_layout.addWidget(self.ta_stock_input)
        
        self.ta_timeframe = QComboBox()
        self.ta_timeframe.addItems(["1d", "1wk", "1mo"])
        stock_select_layout.addWidget(self.ta_timeframe)
        
        analyze_btn = QPushButton("Analyze")
        analyze_btn.clicked.connect(self.run_technical_analysis)
        stock_select_layout.addWidget(analyze_btn)
        
        tech_layout.addLayout(stock_select_layout)
        
        # Results display
        self.ta_results = QTextEdit()
        self.ta_results.setReadOnly(True)
        tech_layout.addWidget(self.ta_results)
        
        # Chart display
        self.ta_chart = FigureCanvas(Figure(figsize=(10, 4)))
        tech_layout.addWidget(self.ta_chart)
        
        self.market_tabs.addTab(tech_analysis_tab, "Technical Analysis")
        
        # Initialize analyzer
        self.technical_analyzer = TechnicalAnalyzer()
    
    def run_technical_analysis(self):
            symbol = self.ta_stock_input.text().strip()
            timeframe = self.ta_timeframe.currentText()
            
            if not symbol:
                QMessageBox.warning(self, "Error", "Please enter a stock symbol")
                return
                
            self.ta_results.setPlainText("Fetching data and analyzing...")
            
            # Create and start worker
            worker = TechnicalAnalysisWorker(symbol, timeframe, self)
            worker.analysis_complete.connect(self.display_technical_analysis)
        worker.finished_signal.connect(lambda: self.worker_finished(worker))
        self.workers.append(worker)
        worker.start()
        
    def display_technical_analysis(self, results):
        symbol = results['symbol']
        historical_data = results['data']
        analysis = results['analysis']
        
        # Display text results
        report = f"Technical Analysis Report for {symbol}\n\n"
        
        # Breakout analysis
        if analysis['breakouts']['resistance_breakout']:
            report += "🟢 STRONG RESISTANCE BREAKOUT detected!\n"
            report += f"Breakout above {analysis['breakouts']['breakout_price']:.2f}\n"
            report += f"Volume: {analysis['breakouts']['breakout_volume']:,.0f} (above average)\n\n"
        elif analysis['breakouts']['support_breakout']:
            report += "🔴 SUPPORT BREAKDOWN detected!\n"
            report += f"Breakdown below {analysis['breakouts']['breakout_price']:.2f}\n"
            report += f"Volume: {analysis['breakouts']['breakout_volume']:,.0f} (above average)\n\n"
        else:
            report += "No significant breakouts detected\n\n"
        
        # Support/Resistance levels
        if analysis['support_resistance']:
            report += "Key Levels:\n"
            for level in analysis['support_resistance']:
                price = level['price']
                distance_pct = ((historical_data['Close'].iloc[-1] - price) / price) * 100
                report += f"- {level['type'].title()}: {price:.2f} ({distance_pct:+.1f}% from current)\n"
            report += "\n"
        
        # Candlestick patterns
        if analysis['candlestick_patterns']:
            report += "Candlestick Patterns:\n"
            for pattern in analysis['candlestick_patterns']:
                report += f"- {pattern.replace('_', ' ').title()}\n"
            report += "\n"
        
        # Moving averages
        if analysis['ma_crossover']:
            if analysis['ma_crossover'] == 'golden_cross':
                report += "🟢 GOLDEN CROSS detected (bullish MA crossover)\n"
            else:
                report += "🔴 DEATH CROSS detected (bearish MA crossover)\n"
        
        self.ta_results.setPlainText(report)
        
        # Plot the chart
        self.plot_technical_analysis(historical_data, analysis)

    def plot_technical_analysis(self, data, analysis):
        fig = self.ta_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        
        # Plot closing prices
        ax.plot(data.index, data['Close'], label='Price', color='#1f77b4')
        
        # Plot support/resistance levels
        for level in analysis['support_resistance']:
            ax.axhline(level['price'], 
                    color='green' if level['type'] == 'support' else 'red',
                    linestyle='--',
                    alpha=0.5,
                    label=f"{level['type'].title()} at {level['price']:.2f}")
        
        # Highlight breakouts
        if analysis['breakouts']['resistance_breakout']:
            ax.axhspan(analysis['breakouts']['consolidation_range'][0],
                    analysis['breakouts']['consolidation_range'][1],
                    color='green', alpha=0.1)
        elif analysis['breakouts']['support_breakout']:
            ax.axhspan(analysis['breakouts']['consolidation_range'][0],
                    analysis['breakouts']['consolidation_range'][1],
                    color='red', alpha=0.1)
        
        # Add moving averages
        if len(data) >= 50:
            ma20 = data['Close'].rolling(20).mean()
            ma50 = data['Close'].rolling(50).mean()
            ax.plot(data.index, ma20, label='20-day MA', color='orange')
            ax.plot(data.index, ma50, label='50-day MA', color='purple')
        
        ax.set_title(f"Technical Analysis - {data.index[-1].date()}")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Format x-axis for dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        fig.autofmt_xdate()
        
        self.ta_chart.draw()
    
    def refresh_market_data(self):
        self.refresh_indian_market_data()
        self.refresh_global_market_data()
        QMessageBox.information(self, "Refresh", "Market data refreshed successfully!")
        
    def refresh_indian_market_data(self):
        indices = {
            "NIFTY 50": "^NSEI",
            "NIFTY BANK": "^NSEBANK",
            "SENSEX": "^BSESN",
            "NIFTY IT": "^CNXIT",
            "NIFTY NEXT 50": "^NSEMDCP50"
        }
        
        worker = MarketDataWorker(indices)
        worker.data_fetched.connect(self.update_indian_market_table)
        worker.finished_signal.connect(lambda: self.worker_finished(worker))
        self.workers.append(worker)
        worker.start()
        
    def update_indian_market_table(self, data):
        self.indian_market_table.setRowCount(len(data))
        
        for row, (name, values) in enumerate(data.items()):
            if values is None:
                continue
                
            change = values['Change']
            pct_change = values['% Change']
            color = '#4CAF50' if change >= 0 else '#F44336'
            
            self.indian_market_table.setItem(row, 0, QTableWidgetItem(name))
            self.indian_market_table.setItem(row, 1, QTableWidgetItem(f"{values['Current']:,.2f}"))
            
            change_item = QTableWidgetItem(f"{change:+,.2f}")
            change_item.setForeground(QColor(color))
            self.indian_market_table.setItem(row, 2, change_item)
            
            pct_item = QTableWidgetItem(f"{pct_change:+,.2f}%")
            pct_item.setForeground(QColor(color))
            self.indian_market_table.setItem(row, 3, pct_item)
            
            status_item = QTableWidgetItem(values['Status'])
            status_item.setForeground(QColor('#4CAF50' if values['Status'] == "Open" else '#F44336'))
            self.indian_market_table.setItem(row, 4, status_item)
            
            self.indian_market_table.setItem(row, 5, QTableWidgetItem(values['Market Hours']))
    
    def refresh_global_market_data(self):
        indices = {
            "S&P 500": "^GSPC",
            "NASDAQ": "^IXIC",
            "DOW JONES": "^DJI",
            "FTSE 100": "^FTSE",
            "DAX": "^GDAXI",
            "NIKKEI 225": "^N225"
        }
        
        worker = MarketDataWorker(indices)
        worker.data_fetched.connect(self.update_global_market_table)
        worker.finished_signal.connect(lambda: self.worker_finished(worker))
        self.workers.append(worker)
        worker.start()
    
    def update_global_market_table(self, data):
        self.global_market_table.setRowCount(len(data))
        
        for row, (name, values) in enumerate(data.items()):
            if values is None:
                continue
                
            change = values['Change']
            pct_change = values['% Change']
            color = '#4CAF50' if change >= 0 else '#F44336'
            
            self.global_market_table.setItem(row, 0, QTableWidgetItem(name))
            self.global_market_table.setItem(row, 1, QTableWidgetItem(f"{values['Current']:,.2f}"))
            
            change_item = QTableWidgetItem(f"{change:+,.2f}")
            change_item.setForeground(QColor(color))
            self.global_market_table.setItem(row, 2, change_item)
            
            pct_item = QTableWidgetItem(f"{pct_change:+,.2f}%")
            pct_item.setForeground(QColor(color))
            self.global_market_table.setItem(row, 3, pct_item)
            
            status_item = QTableWidgetItem(values['Status'])
            status_item.setForeground(QColor('#4CAF50' if values['Status'] == "Open" else '#F44336'))
            self.global_market_table.setItem(row, 4, status_item)
            
            self.global_market_table.setItem(row, 5, QTableWidgetItem(values['Market Hours']))
    
    def run_stock_scanner(self):
        category = self.scanner_category.currentText()
        exchange = self.scanner_exchange.currentText()
        
        # Placeholder for actual scanner implementation
        # In a real app, this would fetch data from an API
        self.scanner_table.setRowCount(0)
        
        # Simulate data
        if exchange in ["NSE", "BSE"]:
            stocks = [
                ("RELIANCE", "Reliance Industries", 2500.50, 45.75, 1.86, "10.5M"),
                ("TCS", "Tata Consultancy", 3200.25, -32.50, -1.01, "5.2M"),
                ("HDFCBANK", "HDFC Bank", 1500.75, 22.25, 1.50, "8.1M"),
                ("INFY", "Infosys", 1600.00, -15.00, -0.93, "4.3M"),
                ("HINDUNILVR", "Hindustan Unilever", 2400.50, 12.75, 0.53, "2.7M")
            ]
        else:
            stocks = [
                ("AAPL", "Apple Inc.", 175.50, 2.75, 1.59, "25.3M"),
                ("MSFT", "Microsoft", 300.25, -1.50, -0.50, "18.7M"),
                ("AMZN", "Amazon", 3200.75, 45.25, 1.43, "5.1M"),
                ("GOOGL", "Alphabet", 2700.00, -22.00, -0.81, "3.8M"),
                ("TSLA", "Tesla", 750.50, 15.75, 2.15, "15.2M")
            ]
        
        # Filter based on category
        if category == "Gainers":
            stocks = sorted(stocks, key=lambda x: x[3], reverse=True)[:5]
        elif category == "Losers":
            stocks = sorted(stocks, key=lambda x: x[3])[:5]
        elif category == "Most Active":
            stocks = sorted(stocks, key=lambda x: float(x[5][:-1]), reverse=True)[:5]
        elif category == "52 Week High":
            stocks = [s for s in stocks if s[3] > 0][:5]
        elif category == "52 Week Low":
            stocks = [s for s in stocks if s[3] < 0][:5]
        
        self.scanner_table.setRowCount(len(stocks))
        
        for row, stock in enumerate(stocks):
            self.scanner_table.setItem(row, 0, QTableWidgetItem(stock[0]))
            self.scanner_table.setItem(row, 1, QTableWidgetItem(stock[1]))
            self.scanner_table.setItem(row, 2, QTableWidgetItem(f"{stock[2]:.2f}"))
            
            change = stock[3]
            color = '#4CAF50' if change >= 0 else '#F44336'
            
            change_item = QTableWidgetItem(f"{change:+,.2f}")
            change_item.setForeground(QColor(color))
            self.scanner_table.setItem(row, 3, change_item)
            
            pct_item = QTableWidgetItem(f"{stock[4]:+,.2f}%")
            pct_item.setForeground(QColor(color))
            self.scanner_table.setItem(row, 4, pct_item)
            
            self.scanner_table.setItem(row, 5, QTableWidgetItem(stock[5]))
        
    def create_data_operations(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        title = QLabel("Data Operations")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Backup Section
        backup_group = QFrame()
        backup_group.setFrameShape(QFrame.StyledPanel)
        backup_group.setStyleSheet("background-color: #1E1E1E; border-radius: 5px; padding: 15px;")
        backup_layout = QVBoxLayout(backup_group)
        
        backup_label = QLabel("Portfolio Backup & Restore")
        backup_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #64B5F6;")
        backup_layout.addWidget(backup_label)
        
        backup_btn = QPushButton("Backup Portfolios")
        backup_btn.clicked.connect(self.backup_portfolios)
        backup_layout.addWidget(backup_btn)
        
        restore_btn = QPushButton("Restore Portfolios")
        restore_btn.clicked.connect(self.restore_portfolios)
        backup_layout.addWidget(restore_btn)
        
        layout.addWidget(backup_group)
        
        # Import/Export Section
        import_export_group = QFrame()
        import_export_group.setFrameShape(QFrame.StyledPanel)
        import_export_group.setStyleSheet("background-color: #1E1E1E; border-radius: 5px; padding: 15px;")
        ie_layout = QVBoxLayout(import_export_group)
        
        ie_label = QLabel("Import & Export")
        ie_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #64B5F6;")
        ie_layout.addWidget(ie_label)
        
        export_btn = QPushButton("Export Portfolio Data")
        export_btn.clicked.connect(self.export_portfolio_data)
        ie_layout.addWidget(export_btn)
        
        import_btn = QPushButton("Import Portfolio Data")
        import_btn.clicked.connect(self.import_portfolio_data)
        ie_layout.addWidget(import_btn)
        
        layout.addWidget(import_export_group)
        
        # Data Management Section
        management_group = QFrame()
        management_group.setFrameShape(QFrame.StyledPanel)
        management_group.setStyleSheet("background-color: #1E1E1E; border-radius: 5px; padding: 15px;")
        mgmt_layout = QVBoxLayout(management_group)
        
        mgmt_label = QLabel("Data Management")
        mgmt_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #64B5F6;")
        mgmt_layout.addWidget(mgmt_label)
        
        clear_btn = QPushButton("Clear All Data")
        clear_btn.setStyleSheet("background-color: #F44336;")
        clear_btn.clicked.connect(self.clear_all_data)
        mgmt_layout.addWidget(clear_btn)
        
        layout.addWidget(management_group)
        
        back_btn = QPushButton("Back to Main Menu")
        back_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        layout.addWidget(back_btn)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)
        
    def backup_portfolios(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Portfolio Backup",
            "",
            "JSON Files (*.json)",
            options=options
        )
        
        if file_path:
            try:
                # Convert DataFrames to dictionaries
                backup_data = {}
                for name, df in self.portfolios.items():
                    backup_data[name] = df.to_dict(orient='records')
                
                with open(file_path, 'w') as f:
                    json.dump(backup_data, f, indent=4)
                
                self.log_audit("BACKUP_CREATED", "", "", f"File: {file_path}")
                QMessageBox.information(self, "Success", "Portfolio backup created successfully!")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to create backup: {str(e)}")
    
    def restore_portfolios(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Backup File",
            "",
            "JSON Files (*.json)",
            options=options
        )
        
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    backup_data = json.load(f)
                
                # Convert dictionaries back to DataFrames
                restored_portfolios = {}
                for name, records in backup_data.items():
                    restored_portfolios[name] = pd.DataFrame(records)
                
                self.portfolios = restored_portfolios
                self.log_audit("BACKUP_RESTORED", "", "", f"File: {file_path}")
                QMessageBox.information(self, "Success", "Portfolio data restored successfully!")
                
                # Refresh UI
                self.refresh_portfolio_list()
                if hasattr(self, 'portfolio_combo'):
                    self.portfolio_combo.clear()
                    self.portfolio_combo.addItems(sorted(self.portfolios.keys()))
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to restore backup: {str(e)}")
    
    def export_portfolio_data(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Portfolio Data",
            "",
            "CSV Files (*.csv);;Excel Files (*.xlsx)",
            options=options
        )
        
        if not file_path:
            return
            
        try:
            if file_path.lower().endswith('.csv'):
                # Export all portfolios to separate CSV files
                base_path = file_path.replace('.csv', '')
                for name, df in self.portfolios.items():
                    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '_')).rstrip()
                    df.to_csv(f"{base_path}_{safe_name}.csv", index=False)
            else:
                # Export to Excel with each portfolio as a separate sheet
                with pd.ExcelWriter(file_path) as writer:
                    for name, df in self.portfolios.items():
                        safe_name = name[:31]  # Excel sheet name limit
                        df.to_excel(writer, sheet_name=safe_name, index=False)
                        
            self.log_audit("DATA_EXPORTED", "", "", f"File: {file_path}")
            QMessageBox.information(self, "Success", "Portfolio data exported successfully!")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to export data: {str(e)}")
    
    def import_portfolio_data(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Portfolio Data",
            "",
            "CSV Files (*.csv);;Excel Files (*.xlsx)",
            options=options
        )
        
        if not file_path:
                                return
                        
        try:
            if file_path.lower().endswith('.csv'):
                # Get portfolio name from filename
                portfolio_name, ok = QInputDialog.getText(  # This is where we use QInputDialog
                    self,
                    "Portfolio Name",
                    "Enter name for the imported portfolio:"
                )
                
                if not ok or not portfolio_name:
                    return
                    
                df = pd.read_csv(file_path)
                self.portfolios[portfolio_name] = df
            else:
                # Excel file - import all sheets as separate portfolios
                xls = pd.ExcelFile(file_path)
                for sheet_name in xls.sheet_names:
                    df = pd.read_excel(xls, sheet_name=sheet_name)
                    self.portfolios[sheet_name] = df
                    
            self.log_audit("DATA_IMPORTED", "", "", f"File: {file_path}")
            QMessageBox.information(self, "Success", "Portfolio data imported successfully!")
            
            # Refresh UI
                    self.refresh_portfolio_list()
            if hasattr(self, 'portfolio_combo'):
                    self.portfolio_combo.clear()
                    self.portfolio_combo.addItems(sorted(self.portfolios.keys()))
            except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to import data: {str(e)}")
    
    def clear_all_data(self):
        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            "This will delete ALL portfolio data. Are you sure?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.portfolios = {}
            self.log_audit("DATA_CLEARED", "", "", "All data cleared")
            
            # Refresh UI
            self.refresh_portfolio_list()
            if hasattr(self, 'portfolio_combo'):
                self.portfolio_combo.clear()
                
            QMessageBox.information(self, "Success", "All data has been cleared.")
                
    def create_audit_history(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        title = QLabel("Audit History")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        filter_frame = QFrame()
        filter_frame.setFrameShape(QFrame.StyledPanel)
        filter_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 5px; padding: 10px;")
        filter_layout = QHBoxLayout(filter_frame)
        
        filter_layout.addWidget(QLabel("Filter by:"))
        
        self.audit_filter_type = QComboBox()
        self.audit_filter_type.addItems(["All", "Portfolio", "Stock", "Mutual Fund", "System"])
        filter_layout.addWidget(self.audit_filter_type)
        
        self.audit_filter_text = QLineEdit()
        self.audit_filter_text.setPlaceholderText("Search term...")
        filter_layout.addWidget(self.audit_filter_text)
        
        filter_btn = QPushButton("Apply Filter")
        filter_btn.clicked.connect(self.refresh_audit_log)
        filter_layout.addWidget(filter_btn)
        
        clear_btn = QPushButton("Clear Filter")
        clear_btn.clicked.connect(self.clear_audit_filter)
        filter_layout.addWidget(clear_btn)
        
        layout.addWidget(filter_frame)
        
        self.audit_table = QTableWidget()
        self.audit_table.setColumnCount(5)
        self.audit_table.setHorizontalHeaderLabels([
            "Timestamp", "Action", "Portfolio", "Item", "Details"
        ])
        self.audit_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.audit_table.verticalHeader().setVisible(False)
        layout.addWidget(self.audit_table)
        
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh Log")
        refresh_btn.clicked.connect(self.refresh_audit_log)
        btn_layout.addWidget(refresh_btn)
        
        export_btn = QPushButton("Export Log")
        export_btn.clicked.connect(self.export_audit_log)
        btn_layout.addWidget(export_btn)
        
        clear_btn = QPushButton("Clear Log")
        clear_btn.setStyleSheet("background-color: #F44336;")
        clear_btn.clicked.connect(self.clear_audit_log)
        btn_layout.addWidget(clear_btn)
        
        layout.addLayout(btn_layout)
        
        back_btn = QPushButton("Back to Main Menu")
        back_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        layout.addWidget(back_btn)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)
        
        # Load initial data
        self.refresh_audit_log()
        
    def refresh_audit_log(self):
        try:
            with open("portfolio_audit.log", "r") as f:
                log_entries = [line.strip().split(" | ") for line in f.readlines() if line.strip()]
        except FileNotFoundError:
            log_entries = []
            
        # Apply filters
        filter_type = self.audit_filter_type.currentText()
        filter_text = self.audit_filter_text.text().lower()
        
        filtered_entries = []
        for entry in log_entries:
            if len(entry) != 5:
                continue
                
            timestamp, action, portfolio, item, details = entry
            
            # Filter by type
            if filter_type == "Portfolio" and "PORTFOLIO" not in action:
                continue
            elif filter_type == "Stock" and "STOCK" not in action and "SHARES" not in action:
                continue
            elif filter_type == "Mutual Fund" and "MF" not in action:
                continue
            elif filter_type == "System" and "SYSTEM" not in action and "DATA" not in action and "BACKUP" not in action:
                continue
                
            # Filter by search text
            if filter_text and filter_text not in " | ".join(entry).lower():
                continue
                
            filtered_entries.append(entry)
            
        # Populate table
        self.audit_table.setRowCount(len(filtered_entries))
        for row, entry in enumerate(filtered_entries):
            timestamp, action, portfolio, item, details = entry
            
            self.audit_table.setItem(row, 0, QTableWidgetItem(timestamp))
            
            action_item = QTableWidgetItem(action)
            if "ADD" in action:
                action_item.setForeground(QColor('#4CAF50'))
            elif "REMOVE" in action or "DELETE" in action:
                action_item.setForeground(QColor('#F44336'))
            elif "MODIFY" in action:
                action_item.setForeground(QColor('#FFC107'))
            self.audit_table.setItem(row, 1, action_item)
            
            self.audit_table.setItem(row, 2, QTableWidgetItem(portfolio))
            self.audit_table.setItem(row, 3, QTableWidgetItem(item))
            self.audit_table.setItem(row, 4, QTableWidgetItem(details))
    
    def clear_audit_filter(self):
        self.audit_filter_type.setCurrentIndex(0)
        self.audit_filter_text.clear()
        self.refresh_audit_log()
    
    def export_audit_log(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Audit Log",
            "",
            "CSV Files (*.csv);;Text Files (*.txt)",
            options=options
        )
        
        if not file_path:
            return
            
        try:
            with open("portfolio_audit.log", "r") as f:
                log_data = f.read()
                
            if file_path.lower().endswith('.csv'):
                # Convert to CSV format
                rows = []
                for line in log_data.split('\n'):
                    if line.strip():
                        rows.append(line.split(" | "))
                        
                df = pd.DataFrame(rows, columns=[
                    "Timestamp", "Action", "Portfolio", "Item", "Details"
                ])
                df.to_csv(file_path, index=False)
            else:
                # Save as plain text
                with open(file_path, 'w') as f:
                    f.write(log_data)
                    
            QMessageBox.information(self, "Success", "Audit log exported successfully!")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to export audit log: {str(e)}")
                
    def clear_audit_log(self):
        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            "This will permanently delete the audit log. Are you sure?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                with open("portfolio_audit.log", "w"):
                    pass
                self.refresh_audit_log()
                QMessageBox.information(self, "Success", "Audit log cleared.")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to clear audit log: {str(e)}")
                
    def log_audit(self, action, portfolio="", item="", details=""):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"{timestamp} | {action} | {portfolio} | {item} | {details}\n"
        
        try:
            with open("portfolio_audit.log", "a") as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Error writing to audit log: {str(e)}")
            
        # Update activity log on main page if it exists
        if hasattr(self, 'activity_log'):
            self.refresh_activity_log()
            
    def load_data(self):
        try:
            if os.path.exists("portfolios.json"):
            with open("portfolios.json", "r") as f:
                data = json.load(f)
                
                self.portfolios = {}
                for name, records in data.items():
                    self.portfolios[name] = pd.DataFrame(records)
                    
                print("Portfolio data loaded successfully.")
        except Exception as e:
            print(f"Error loading portfolio data: {str(e)}")
            self.portfolios = {}
            
    def save_data(self):
        try:
            # Convert DataFrames to dictionaries
            save_data = {}
            for name, df in self.portfolios.items():
                save_data[name] = df.to_dict(orient='records')
                
            with open("portfolios.json", "w") as f:
                json.dump(save_data, f, indent=4)
                
            print("Portfolio data saved successfully.")
        except Exception as e:
            print(f"Error saving portfolio data: {str(e)}")

    def auto_refresh(self):
        current_page = self.stacked_widget.currentIndex()
        if current_page == 0:  # Main menu
            self.refresh_market_summary()
            self.refresh_portfolio_summary()
            self.refresh_activity_log()
        elif current_page == 2:  # Stock operations
            self.refresh_stock_table()
        elif current_page == 3:  # Dashboard
            self.refresh_dashboard_data()
        elif current_page == 4:  # Market analysis
            self.refresh_market_data()
        elif current_page == 7:  # Mutual funds
            self.refresh_mf_table()
            
        self.log_audit("SYSTEM", "", "", "Auto-refresh completed")

    def worker_finished(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)
        worker.deleteLater()
            
    def closeEvent(self, event):
        # Stop all running workers
        for worker in self.workers[:]:
            worker.stop()
            
        # Save data
        self.save_data()
        
        event.accept()

    def refresh_all_dashboards(self):
        self.refresh_dashboard_data()
        self.refresh_individual_dashboard()
        self.update_charts()
        self.update_analysis_charts()

    def export_all_portfolios(self):
        self.export_portfolio_data()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Set dark palette
    palette = app.palette()
    palette.setColor(palette.Window, QColor(26, 27, 38))
    palette.setColor(palette.WindowText, Qt.white)
    palette.setColor(palette.Base, QColor(15, 16, 23))
    palette.setColor(palette.AlternateBase, QColor(26, 27, 38))
    palette.setColor(palette.ToolTipBase, Qt.white)
    palette.setColor(palette.ToolTipText, Qt.white)
    palette.setColor(palette.Text, Qt.white)
    palette.setColor(palette.Button, QColor(26, 27, 38))
    palette.setColor(palette.ButtonText, Qt.white)
    palette.setColor(palette.BrightText, Qt.red)
    palette.setColor(palette.Link, QColor(42, 130, 218))
    palette.setColor(palette.Highlight, QColor(42, 130, 218))
    palette.setColor(palette.HighlightedText, Qt.black)
    app.setPalette(palette)
    
    window = PortfolioTracker()
    window.show()
    sys.exit(app.exec_())