import sys
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)
import os
os.environ['QT_MAC_WANTS_LAYER'] = '1'
import random
import traceback
import json
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import threading
import warnings
import matplotlib.dates as mdates
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QListWidget, QStackedWidget, QLineEdit,
    QTableWidget, QTableWidgetItem, QComboBox, QSpinBox, 
    QDoubleSpinBox, QDateEdit, QMessageBox, QFileDialog, QDialog,
    QTabWidget, QSizePolicy, QFrame, QHeaderView, QTextEdit,
    QInputDialog, QGroupBox, QScrollArea, QProgressBar,
    QListWidgetItem, QCheckBox, QSplitter  # Added QSplitter here

)
from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal, QTimer, QSize, QUrl
from PyQt5.QtGui import QColor, QFont, QIcon, QPalette, QLinearGradient, QBrush
from PyQt5.QtWebEngineWidgets import QWebEngineView
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
    progress_updated = pyqtSignal(int)
    error_occurred = pyqtSignal(str)

    
    def __init__(self, tickers, parent=None):
        super().__init__(parent)
        self.tickers = tickers
        self._is_running = True
       
        
    def run(self):
        prices = {}
        total = len(self.tickers)
        for i, ticker in enumerate(self.tickers):
            if not self._is_running:
                break
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period="1d")
                if not hist.empty:
                    prices[ticker] = hist['Close'].iloc[-1]
                else:
                    prices[ticker] = None
            except Exception as e:
                print(f"Error fetching {ticker}: {str(e)}")
                prices[ticker] = None
                
            self.progress_updated.emit(int((i+1)/total * 100))
            
        if self._is_running:
            self.data_fetched.emit(prices)
        self.finished_signal.emit()
        
    def stop(self):
        self._is_running = False
        self.quit()
        self.wait(1000)

class MarketDataWorker(QThread):
    data_fetched = pyqtSignal(dict)
    finished_signal = pyqtSignal()
    progress_updated = pyqtSignal(int)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, indices, parent=None):
        super().__init__(parent)
        self.indices = indices
        self._is_running = True
        
    def run(self):
        prices = {}
        total = len(self.indices)
        if total == 0:
            self.finished_signal.emit()
            return

        for i, ticker in enumerate(self.indices):
            if not self._is_running:
                break
                
            try:
                # Validate ticker format first
                if not ticker or not isinstance(ticker, str):
                    print(f"Invalid ticker format: {ticker}")
                    prices[ticker] = None
                    continue

                # Fetch data with timeout protection
                stock = yf.Ticker(ticker)
                
                # Try multiple periods if needed
                hist = None
                for period in ["1d", "5d", "1mo"]:  # Try different periods
                    try:
                        hist = stock.history(period=period)
                        if not hist.empty:
                            break
                    except Exception as e:
                        print(f"Error fetching {ticker} with period {period}: {str(e)}")
                        continue

                if hist is not None and not hist.empty:
                    # Get the most recent valid closing price
                    last_valid_close = hist['Close'].dropna()
                    if not last_valid_close.empty:
                        current_price = last_valid_close.iloc[-1]
                        prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
                        change = current_price - prev_close
                        pct_change = (change / prev_close) * 100
                        
                        prices[ticker] = {
                            'Current': current_price,
                            'Change': change,
                            '% Change': pct_change,
                            'Status': 'Open' if self.is_market_open(ticker) else 'Closed',
                            'Market Hours': self.get_market_hours(ticker)
                        }
                    else:
                        prices[ticker] = None
                        print(f"No valid closing price for {ticker}")
                else:
                    prices[ticker] = None
                    print(f"No historical data for {ticker}")

            except Exception as e:
                error_msg = f"Error processing {ticker}: {str(e)}"
                print(error_msg)
                self.error_occurred.emit(error_msg)
                prices[ticker] = None
                
            # Update progress (ensure we don't divide by zero)
            progress = min(100, max(0, int((i+1)/total * 100)))
            self.progress_updated.emit(progress)

        # Only emit data if we're still running
        if self._is_running:
            self.data_fetched.emit(prices)
        else:
            print("Worker stopped before completion")
            
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
    
    def get_market_hours(self, ticker):
        if '^NSE' in ticker:  # Indian market
            return "9:15 AM - 3:30 PM IST"
        else:  # US market
            return "9:30 AM - 4:00 PM EST"

class StockHistoryWorker(QThread):
    data_fetched = pyqtSignal(str, pd.DataFrame)
    finished_signal = pyqtSignal()
    
    def __init__(self, ticker, period="1y", parent=None):
        super().__init__(parent)
        self.ticker = ticker
        self.period = period
        self._is_running = True
        
    def run(self):
        if not self._is_running:
            return
            
        try:
            stock = yf.Ticker(self.ticker)
            hist = stock.history(period=self.period)
            if not hist.empty:
                self.data_fetched.emit(self.ticker, hist)
        except Exception as e:
            print(f"Error fetching history for {self.ticker}: {str(e)}")
            
        self.finished_signal.emit()
        
    def stop(self):
        self._is_running = False
        self.quit()
        self.wait(1000)

class NewsFetcher(QThread):
    news_fetched = pyqtSignal(list)
    finished_signal = pyqtSignal()
    
    def __init__(self, tickers, parent=None):
        super().__init__(parent)
        self.tickers = tickers
        self._is_running = True
        
    def run(self):
        if not self._is_running:
            return
            
        all_news = []
        for ticker in self.tickers:
            if not self._is_running:
                break
                
            try:
                stock = yf.Ticker(ticker)
                news = stock.news
                for item in news:
                    item['ticker'] = ticker
                all_news.extend(news)
            except Exception as e:
                print(f"Error fetching news for {ticker}: {str(e)}")
                
        if self._is_running:
            self.news_fetched.emit(all_news)
        self.finished_signal.emit()
        
    def stop(self):
        self._is_running = False
        self.quit()
        self.wait(1000)

class CompanyAnalysisWorker(QThread):
    analysis_complete = pyqtSignal(str, dict)
    finished_signal = pyqtSignal()
    
    def __init__(self, ticker, parent=None):
        super().__init__(parent)
        self.ticker = ticker
        self._is_running = True
        
    def run(self):
        if not self._is_running:
            return
            
        try:
            stock = yf.Ticker(self.ticker)
            info = stock.info
            
            # Get key metrics
            analysis = {
                'info': info,
                'financials': stock.financials,
                'quarterly_financials': stock.quarterly_financials,
                'balance_sheet': stock.balance_sheet,
                'quarterly_balance_sheet': stock.quarterly_balance_sheet,
                'cashflow': stock.cashflow,
                'quarterly_cashflow': stock.quarterly_cashflow,
                'recommendations': stock.recommendations,
                'actions': stock.actions
            }
            
            if self._is_running:
                self.analysis_complete.emit(self.ticker, analysis)
        except Exception as e:
            print(f"Error analyzing {self.ticker}: {str(e)}")
            
        self.finished_signal.emit()
        
    def stop(self):
        self._is_running = False
        self.quit()
        self.wait(1000)

class PortfolioTracker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quantum Portfolio Tracker Pro")
        self.setGeometry(100, 50, 1800, 1000)
        
        # Initialize data structures
        self.portfolios = {}
        self.workers = []
        self.stock_analysis_data = {}
        self.news_data = []
        
        # Set up UI first
        self.init_ui()
        
        # Configure theme
        self.set_dark_theme()
        
        # Load data with error handling
        self.load_data()
        
        # Verify loaded data
        self.debug_portfolio_data()
        
        # Initialize UI components with data
        self.initialize_ui_with_data()
        
        # Refresh all data
        self.refresh_all_data()
        
        # Set up periodic auto-refresh
        self.setup_auto_refresh()
        
        # Set window icon
        self.setWindowIcon(QIcon(":/icons/app_icon.png"))
        
    def init_ui(self):
        # Create main container with shadow effect
        self.main_container = QWidget()
        self.main_container.setObjectName("mainContainer")
        self.setCentralWidget(self.main_container)
        
        # Main layout
        self.main_layout = QHBoxLayout(self.main_container)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Create sidebar
        self.create_sidebar()
        
        # Create main content area
        self.create_main_content()
        
        # Connect page change signal
        self.stacked_widget.currentChanged.connect(self.handle_page_change)
        
        # Initialize data loading with progress indication
        self.show_loading_overlay("Initializing application...")
        
        # Use single-shot timer to allow UI to render before loading data
        QTimer.singleShot(100, self.initialize_application_data)

    def initialize_application_data(self):
        """Initialize data after UI is rendered"""
        try:
            # Load initial data with error handling
            self.refresh_market_summary()
            self.refresh_portfolio_summary()
            self.refresh_activity_log()
            
            # Set up auto-refresh timer with configurable interval
            self.refresh_timer = QTimer()
            self.refresh_timer.timeout.connect(self.auto_refresh)
            
            # Load refresh interval from config or use default (5 minutes)
            refresh_interval = self.load_refresh_interval()
            self.refresh_timer.start(refresh_interval)
            
            # Hide loading overlay when done
            self.hide_loading_overlay()
            
        except Exception as e:
            self.hide_loading_overlay()
            QMessageBox.critical(self, "Initialization Error", 
                            f"Failed to initialize application: {str(e)}")
            print(f"Initialization error: {traceback.format_exc()}")

    def load_refresh_interval(self):
        """Load refresh interval from config file or use default"""
        try:
            if os.path.exists('portfolio_config.json'):
                with open('portfolio_config.json', 'r') as f:
                    config = json.load(f)
                    return config.get('refresh_interval', 5) * 60000  # Convert minutes to ms
        except Exception:
            pass
        return 300000  # Default 5 minutes

    def handle_page_change(self, index):
        """Handle page changes to update specific content"""
        if index == 0:  # Dashboard
            self.refresh_market_summary()
            self.refresh_portfolio_summary()
            self.refresh_activity_log()
        elif index == 1:  # Combined View
            self.update_combined_dashboard()
        elif index == 2:  # Portfolios
            self.refresh_portfolio_list()
        elif index == 3:  # Portfolio Dashboard
            self.update_portfolio_dashboard()
        elif index == 4:  # Stocks
            self.refresh_stock_table()
        elif index == 5:  # Mutual Funds
            self.refresh_mf_table()
        elif index == 6:  # Market Data
            self.update_market_indices()
        elif index == 7:  # Analysis
            self.update_analysis()
        elif index == 8:  # Company Research
            self.refresh_company_research()  # You'll need to implement this
        elif index == 9:  # News
            self.refresh_news()
        elif index == 10:  # Reports
            self.refresh_reports()  # You'll need to implement this
        elif index == 11:  # Settings
            self.refresh_settings()  # You'll need to implement this

    def refresh_company_research(self):
        """Refresh company research page"""
        if hasattr(self, 'research_stock_combo') and self.research_stock_combo.count() > 0:
            self.analyze_company()

    def refresh_reports(self):
        """Refresh reports page"""
        pass  # Add report generation logic here

    def refresh_settings(self):
        """Refresh settings page"""
        pass  # Add settings refresh logic here
    
    def show_loading_overlay(self, message):
        """Show loading overlay during initialization"""
        self.loading_overlay = QWidget(self)
        self.loading_overlay.setGeometry(self.rect())
        self.loading_overlay.setStyleSheet("background-color: rgba(0, 0, 0, 0.7);")
        
        layout = QVBoxLayout(self.loading_overlay)
        layout.setAlignment(Qt.AlignCenter)
        
        spinner = QProgressBar()
        spinner.setRange(0, 0)  # Indeterminate progress
        spinner.setFixedWidth(200)
        
        label = QLabel(message)
        label.setStyleSheet("color: white; font-size: 14px;")
        
        layout.addWidget(spinner)
        layout.addWidget(label)
        
        self.loading_overlay.show()

    def hide_loading_overlay(self):
        """Hide loading overlay"""
        if hasattr(self, 'loading_overlay'):
            self.loading_overlay.hide()
            self.loading_overlay.deleteLater()

        
    def set_dark_theme(self):
        # Custom dark theme with professional color scheme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121212;
            }
            
            /* Sidebar styling */
            #sidebar {
                background-color: #1E1E1E;
                border-right: 1px solid #333;
            }
            
            #sidebar QPushButton {
                color: #CCCCCC;
                background-color: transparent;
                border: none;
                text-align: left;
                padding: 12px 20px;
                font-size: 14px;
                border-radius: 4px;
                margin: 2px 5px;
            }
            
            #sidebar QPushButton:hover {
                background-color: #333;
                color: #FFFFFF;
            }
            
            #sidebar QPushButton:pressed {
                background-color: #444;
            }
            
            #sidebar QPushButton#exitButton {
                color: #FF6B6B;
            }
            
            #sidebar QPushButton#exitButton:hover {
                background-color: #FF6B6B;
                color: white;
            }
            
            /* Content area styling */
            #contentArea {
                background-color: #121212;
            }
            
            /* Card styling */
            .card {
                background-color: #1E1E1E;
                border-radius: 8px;
                padding: 15px;
                border: 1px solid #333;
            }
            
            .card-title {
                font-size: 16px;
                font-weight: bold;
                color: #64B5F6;
                margin-bottom: 10px;
            }
            
            /* Table styling */
            QTableWidget {
                background-color: #1E1E1E;
                border: 1px solid #333;
                border-radius: 6px;
                gridline-color: #333;
                font-size: 13px;
            }
            
            QTableWidget::item {
                padding: 8px;
            }
            
            QTableWidget::item:selected {
                background-color: #3A3A3A;
                color: white;
            }
            
            QHeaderView::section {
                background-color: #252525;
                color: #DDDDDD;
                padding: 6px;
                border: none;
                font-weight: bold;
                font-size: 13px;
            }
            
            /* Button styling */
            QPushButton {
                background-color: #3A3A3A;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 100px;
                font-size: 13px;
            }
            
            QPushButton:hover {
                background-color: #4A4A4A;
            }
            
            QPushButton:pressed {
                background-color: #2A2A2A;
            }
            
            QPushButton:disabled {
                background-color: #333;
                color: #777;
            }
            
            /* Primary action button */
            .primary-button {
                background-color: #1976D2;
            }
            
            .primary-button:hover {
                background-color: #1E88E5;
            }
            
            .primary-button:pressed {
                background-color: #1565C0;
            }
            
            /* Danger button */
            .danger-button {
                background-color: #D32F2F;
            }
            
            .danger-button:hover {
                background-color: #E53935;
            }
            
            .danger-button:pressed {
                background-color: #C62828;
            }
            
            /* Success button */
            .success-button {
                background-color: #388E3C;
            }
            
            .success-button:hover {
                background-color: #43A047;
            }
            
            .success-button:pressed {
                background-color: #2E7D32;
            }
            
            /* Input fields */
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTextEdit {
                background-color: #252525;
                color: white;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 6px;
                font-size: 13px;
                min-height: 32px;
            }
            
            QComboBox::drop-down {
                border: none;
            }
            
            QDateEdit::drop-down {
                border: none;
            }
            
            /* Tab widget styling */
            QTabWidget::pane {
                border: 1px solid #333;
                border-radius: 4px;
                background: #1E1E1E;
            }
            
            QTabBar::tab {
                background: #252525;
                color: #CCCCCC;
                padding: 8px 12px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                border: 1px solid #333;
                margin-right: 2px;
                font-size: 13px;
            }
            
            QTabBar::tab:selected {
                background: #1E1E1E;
                color: white;
                border-bottom: 2px solid #64B5F6;
            }
            
            QTabBar::tab:hover {
                background: #333;
            }
            
            /* Progress bar */
            QProgressBar {
                border: 1px solid #333;
                border-radius: 4px;
                text-align: center;
                background-color: #252525;
                color: white;
            }
            
            QProgressBar::chunk {
                background-color: #64B5F6;
                width: 10px;
            }
            
            /* Tooltip styling */
            QToolTip {
                color: #EEEEEE;
                background-color: #333;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px;
            }
            
            /* Scrollbar styling */
            QScrollBar:vertical {
                border: none;
                background: #252525;
                width: 10px;
                margin: 0px 0px 0px 0px;
            }
            
            QScrollBar::handle:vertical {
                background: #444;
                min-height: 20px;
                border-radius: 4px;
            }
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
            }
            
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            
            /* Group box styling */
            QGroupBox {
                border: 1px solid #333;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 15px;
                font-weight: bold;
                color: #64B5F6;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        # Set palette for better color consistency
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(18, 18, 18))
        palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
        palette.setColor(QPalette.Base, QColor(30, 30, 30))
        palette.setColor(QPalette.AlternateBase, QColor(40, 40, 40))
        palette.setColor(QPalette.ToolTipBase, QColor(40, 40, 40))
        palette.setColor(QPalette.ToolTipText, QColor(220, 220, 220))
        palette.setColor(QPalette.Text, QColor(220, 220, 220))
        palette.setColor(QPalette.Button, QColor(40, 40, 40))
        palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
        palette.setColor(QPalette.BrightText, QColor(255, 100, 100))
        palette.setColor(QPalette.Highlight, QColor(100, 149, 237))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.Disabled, QPalette.Text, QColor(120, 120, 120))
        self.setPalette(palette)
        
    def refresh_all_data(self):
        """Refresh all data in the application"""
        self.refresh_market_summary()
        self.refresh_portfolio_summary()
        self.refresh_activity_log()
        
        # Refresh current page data based on which page is active
        current_index = self.stacked_widget.currentIndex()
        if current_index == 1:  # Portfolio management
            self.refresh_portfolio_list()
        elif current_index == 2:  # Stock operations
            self.refresh_stock_table()
        elif current_index == 3:  # Analysis
            self.update_analysis()
        elif current_index == 4:  # Market data
            self.update_market_indices()
        elif current_index == 7:  # Mutual funds
            self.refresh_mf_table()
        elif current_index == 8:  # Combined dashboard
            self.update_combined_dashboard()
        elif current_index == 9:  # News
            self.refresh_news()
    
    def create_sidebar(self):
        # Create sidebar widget
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(220)
        
        # Sidebar layout
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(5, 10, 5, 10)
        sidebar_layout.setSpacing(5)
        
        # App title and logo
        title_container = QWidget()
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(10, 5, 10, 15)
        
        app_icon = QLabel()
        app_icon.setPixmap(QIcon(":/icons/app_icon.png").pixmap(32, 32))
        title_layout.addWidget(app_icon)
        
        app_title = QLabel("Quantum Tracker Pro")
        app_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #64B5F6;")
        title_layout.addWidget(app_title)
        title_layout.addStretch()
        
        sidebar_layout.addWidget(title_container)
        
        # Navigation buttons
        nav_buttons = [
        # Dashboard section
        ("Dashboard", ":/icons/dashboard.png", lambda: self.stacked_widget.setCurrentIndex(0)),
        ("Combined View", ":/icons/combined.png", lambda: self.stacked_widget.setCurrentIndex(1)),
        
        # Portfolio section
        ("Portfolios", ":/icons/portfolio.png", lambda: self.stacked_widget.setCurrentIndex(2)),
        ("Portfolio Dashboard", ":/icons/dashboard.png", lambda: self.stacked_widget.setCurrentIndex(3)),
        
        # Investments section
        ("Stocks", ":/icons/stock.png", lambda: self.stacked_widget.setCurrentIndex(4)),
        ("Mutual Funds", ":/icons/mutual_fund.png", lambda: self.stacked_widget.setCurrentIndex(5)),
        
        # Market section
        ("Market Data", ":/icons/market.png", lambda: self.stacked_widget.setCurrentIndex(6)),
        
        # Analysis section
        ("Analysis", ":/icons/analysis.png", lambda: self.stacked_widget.setCurrentIndex(7)),
        ("Company Research", ":/icons/research.png", lambda: self.stacked_widget.setCurrentIndex(8)),
        
        # Information section
        ("News", ":/icons/news.png", lambda: self.stacked_widget.setCurrentIndex(9)),
        ("Reports", ":/icons/report.png", lambda: self.stacked_widget.setCurrentIndex(10)),
        
        # Settings section
        ("Settings", ":/icons/settings.png", lambda: self.stacked_widget.setCurrentIndex(11))
        ]
        
        for text, icon_path, command in nav_buttons:
            btn = QPushButton(text)
            btn.setIcon(QIcon(icon_path))
            btn.setIconSize(QSize(20, 20))
            btn.clicked.connect(command)
            sidebar_layout.addWidget(btn)
        
        sidebar_layout.addStretch()
        
        # Exit button
        exit_btn = QPushButton("Exit")
        exit_btn.setObjectName("exitButton")
        exit_btn.setIcon(QIcon(":/icons/exit.png"))
        exit_btn.setIconSize(QSize(20, 20))
        exit_btn.clicked.connect(self.close)
        sidebar_layout.addWidget(exit_btn)
        
        # Add sidebar to main layout
        self.main_layout.addWidget(self.sidebar)
        
        
        
    def create_main_content(self):
        # Create main content area
        self.content_area = QWidget()
        self.content_area.setObjectName("contentArea")
        
        # Main content layout
        content_layout = QVBoxLayout(self.content_area)
        content_layout.setContentsMargins(15, 15, 15, 15)
        content_layout.setSpacing(15)
        
        # Header bar
        self.header_bar = QWidget()
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Page title
        self.page_title = QLabel("Dashboard")
        self.page_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        header_layout.addWidget(self.page_title)
        
        # Spacer
        header_layout.addStretch()
        
        # Time and date
        self.time_label = QLabel()
        self.time_label.setStyleSheet("font-size: 14px; color: #AAAAAA;")
        self.update_time()
        time_timer = QTimer(self)
        time_timer.timeout.connect(self.update_time)
        time_timer.start(1000)
        header_layout.addWidget(self.time_label)
        
        content_layout.addWidget(self.header_bar)
        
        # Create stacked widget for pages
        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget)
        
        # Create all pages
        self.create_dashboard_page()          # index 0 - Dashboard
        self.create_combined_dashboard_page() # index 1 - Combined View
        self.create_portfolio_management_page() # index 2 - Portfolios
        self.create_portfolio_dashboard_page() # index 3 - Portfolio Dashboard
        self.create_stock_operations_page()   # index 4 - Stocks
        self.create_mutual_funds_page()       # index 5 - Mutual Funds
        self.create_market_data_page()        # index 6 - Market Data
        self.create_analysis_page()           # index 7 - Analysis
        self.create_company_research_page()   # index 8 - Company Research
        self.create_news_page()               # index 9 - News
        self.create_reports_page()            # index 10 - Reports
        self.create_settings_page()           # index 11 - Settings
       

        
        # Add content area to main layout
        self.main_layout.addWidget(self.content_area, 1)
        
    def update_time(self):
        self.time_label.setText(datetime.now().strftime("%H:%M:%S | %a, %d %b %Y"))
        
    
    def debug_portfolio_data(self):
        """Print debug information about loaded portfolios"""
        print("\n=== Portfolio Data Debug ===")
        print(f"Total portfolios loaded: {len(self.portfolios)}")
        
        for name, df in self.portfolios.items():
            print(f"\nPortfolio: {name}")
            print(f"Number of holdings: {len(df)}")
            if not df.empty:
                print("Sample data:")
                print(df.head())


    def initialize_ui_with_data(self):
        """Initialize UI components with loaded data"""
        # Initialize portfolio dropdowns
        if hasattr(self, 'portfolio_combo'):
            self.portfolio_combo.clear()
            self.portfolio_combo.addItems(sorted(self.portfolios.keys()))
            
        if hasattr(self, 'analysis_portfolio_combo'):
            self.analysis_portfolio_combo.clear()
            self.analysis_portfolio_combo.addItems(sorted(self.portfolios.keys()))
            
        if hasattr(self, 'mf_portfolio_combo'):
            self.mf_portfolio_combo.clear()
            self.mf_portfolio_combo.addItems(sorted(self.portfolios.keys()))

    def setup_auto_refresh(self):
        """Set up periodic auto-refresh timer"""
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.auto_refresh)
        self.refresh_timer.start(300000)  # 5 minutes
        print("Auto-refresh timer initialized (5 minute interval)")

    
    def create_dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # Summary cards row
        summary_row = QHBoxLayout()
        summary_row.setSpacing(15)
        
        # Portfolio summary card
        portfolio_card = QWidget()
        portfolio_card.setObjectName("portfolioSummaryCard")
        portfolio_card.setStyleSheet("""
            #portfolioSummaryCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1E3D59, stop:1 #1E88E5);
                border-radius: 8px;
            }
        """)
        portfolio_layout = QVBoxLayout(portfolio_card)
        portfolio_layout.setContentsMargins(15, 15, 15, 15)
        
        portfolio_title = QLabel("PORTFOLIO VALUE")
        portfolio_title.setStyleSheet("font-size: 14px; font-weight: bold; color: white;")
        portfolio_layout.addWidget(portfolio_title)
        
        self.portfolio_value = QLabel("₹0.00")
        self.portfolio_value.setStyleSheet("font-size: 28px; font-weight: bold; color: white;")
        portfolio_layout.addWidget(self.portfolio_value)
        
        self.portfolio_change = QLabel("+0.00% (₹0.00)")
        self.portfolio_change.setStyleSheet("font-size: 14px; color: #4CAF50;")
        portfolio_layout.addWidget(self.portfolio_change)
        
        portfolio_layout.addStretch()
        
        portfolio_footer = QLabel("Across all portfolios")
        portfolio_footer.setStyleSheet("font-size: 12px; color: rgba(255,255,255,150);")
        portfolio_layout.addWidget(portfolio_footer)
        
        summary_row.addWidget(portfolio_card, 1)
        
        # Market indices card
        market_card = QWidget()
        market_card.setObjectName("marketCard")
        market_card.setStyleSheet("""
            #marketCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2C3E50, stop:1 #4CA1AF);
                border-radius: 8px;
            }
        """)
        market_layout = QVBoxLayout(market_card)
        market_layout.setContentsMargins(15, 15, 15, 15)
        
        market_title = QLabel("MARKET INDICES")
        market_title.setStyleSheet("font-size: 14px; font-weight: bold; color: white;")
        market_layout.addWidget(market_title)
        
        self.market_summary = QLabel("Loading market data...")
        self.market_summary.setStyleSheet("font-size: 13px; color: white;")
        market_layout.addWidget(self.market_summary)
        
        market_layout.addStretch()
        
        market_footer = QLabel("Real-time updates")
        market_footer.setStyleSheet("font-size: 12px; color: rgba(255,255,255,150);")
        market_layout.addWidget(market_footer)
        
        summary_row.addWidget(market_card, 1)
        
        # Performance card
        perf_card = QWidget()
        perf_card.setObjectName("perfCard")
        perf_card.setStyleSheet("""
            #perfCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0F2027, stop:1 #2C5364);
                border-radius: 8px;
            }
        """)
        perf_layout = QVBoxLayout(perf_card)
        perf_layout.setContentsMargins(15, 15, 15, 15)
        
        perf_title = QLabel("PERFORMANCE")
        perf_title.setStyleSheet("font-size: 14px; font-weight: bold; color: white;")
        perf_layout.addWidget(perf_title)
        
        self.portfolio_perf = QLabel("+0.00%")
        self.portfolio_perf.setStyleSheet("font-size: 28px; font-weight: bold; color: #4CAF50;")
        perf_layout.addWidget(self.portfolio_perf)
        
        self.portfolio_daily = QLabel("Today: +0.00%")
        self.portfolio_daily.setStyleSheet("font-size: 14px; color: #4CAF50;")
        perf_layout.addWidget(self.portfolio_daily)
        
        perf_layout.addStretch()
        
        perf_footer = QLabel("Last updated: Just now")
        perf_footer.setStyleSheet("font-size: 12px; color: rgba(255,255,255,150);")
        perf_layout.addWidget(perf_footer)
        
        summary_row.addWidget(perf_card, 1)
        
        layout.addLayout(summary_row)
        
        # Charts and tables row
        charts_row = QHBoxLayout()
        charts_row.setSpacing(15)
        
        # Portfolio allocation chart
        alloc_card = QWidget()
        alloc_card.setObjectName("card")
        alloc_layout = QVBoxLayout(alloc_card)
        alloc_layout.setContentsMargins(0, 0, 0, 0)
        
        alloc_title = QLabel("PORTFOLIO ALLOCATION")
        alloc_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #64B5F6; margin-bottom: 10px;")
        alloc_layout.addWidget(alloc_title)
        
        self.alloc_chart = FigureCanvas(Figure(figsize=(5, 3)))
        self.alloc_chart.figure.set_facecolor('#1E1E1E')
        alloc_layout.addWidget(self.alloc_chart)
        
        charts_row.addWidget(alloc_card, 1)
        
        # Recent activity
        activity_card = QWidget()
        activity_card.setObjectName("card")
        activity_layout = QVBoxLayout(activity_card)
        activity_layout.setContentsMargins(0, 0, 0, 0)
        
        activity_title = QLabel("RECENT ACTIVITY")
        activity_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #64B5F6; margin-bottom: 10px;")
        activity_layout.addWidget(activity_title)
        
        self.activity_log = QTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setStyleSheet("font-size: 12px;")
        activity_layout.addWidget(self.activity_log)
        
        charts_row.addWidget(activity_card, 1)
        
        layout.addLayout(charts_row, 1)
        
        # Quick actions
        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)
        
        quick_actions = [
            ("Add Portfolio", ":/icons/add.png", self.show_create_portfolio_dialog),
            ("Add Stock", ":/icons/stock_add.png", lambda: [self.stacked_widget.setCurrentIndex(2), self.show_add_stock_dialog()]),
            ("Refresh Data", ":/icons/refresh.png", self.refresh_all_data),
            ("Generate Report", ":/icons/report.png", self.generate_quick_report)
        ]
        
        for text, icon, command in quick_actions:
            btn = QPushButton(text)
            btn.setIcon(QIcon(icon))
            btn.setIconSize(QSize(16, 16))
            btn.clicked.connect(command)
            btn.setStyleSheet("padding: 8px 12px;")
            actions_row.addWidget(btn)
        
        actions_row.addStretch()
        
        layout.addLayout(actions_row)
        
        self.stacked_widget.addWidget(page)
        
    def create_combined_dashboard_page(self):
        # Initialize all UI elements as instance variables first
        self.combined_total_value = QLabel("₹0.00")
        self.combined_invested_value = QLabel("₹0.00")
        self.combined_pl_value = QLabel("₹0.00 (0.00%)")
        self.combined_today_pl_value = QLabel("₹0.00 (0.00%)")
        
        # Create charts
        self.combined_alloc_chart = FigureCanvas(Figure(figsize=(6, 4)))
        self.combined_sector_chart = FigureCanvas(Figure(figsize=(6, 4)))
        self.combined_perf_chart = FigureCanvas(Figure(figsize=(8, 4)))
        self.combined_risk_chart = FigureCanvas(Figure(figsize=(8, 4)))
        
        # Rest of your dashboard creation code...
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Header with title and refresh button
        header = QHBoxLayout()
        title = QLabel("Combined Portfolio Dashboard")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        header.addWidget(title)
        
        header.addStretch()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setIcon(QIcon(":/icons/refresh.png"))
        refresh_btn.setStyleSheet("""
            QPushButton {
                padding: 5px 10px;
                background-color: #2E7D32;
                color: white;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
        """)
        refresh_btn.clicked.connect(self.update_combined_dashboard)
        header.addWidget(refresh_btn)
        layout.addLayout(header)
        
        # Performance metrics row
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(15)
        
        # Portfolio Value Card
        value_card = self.create_metric_card(
            "TOTAL PORTFOLIO VALUE", 
            self.combined_total_value,
            "#1E88E5"
        )
        metrics_row.addWidget(value_card)
        
        # Invested Value Card
        invested_card = self.create_metric_card(
            "TOTAL INVESTED", 
            self.combined_invested_value,
            "#7B1FA2"
        )
        metrics_row.addWidget(invested_card)
        
        # Total P/L Card
        total_pl_card = self.create_metric_card(
            "TOTAL PROFIT/LOSS", 
            self.combined_pl_value,
            "#D32F2F"  # Default red, will update based on value
        )
        metrics_row.addWidget(total_pl_card)
        
        # Today's P/L Card
        today_pl_card = self.create_metric_card(
            "TODAY'S P/L", 
            self.combined_today_pl_value,
            "#D32F2F"  # Default red, will update based on value
        )
        metrics_row.addWidget(today_pl_card)
        
        layout.addLayout(metrics_row)
        
        # Charts Splitter
        splitter = QSplitter(Qt.Vertical)
        
        # Top Charts (Allocation)
        top_charts = QWidget()
        top_layout = QHBoxLayout(top_charts)
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        # Asset Allocation Chart
        alloc_card = self.create_chart_card(
            "ASSET ALLOCATION",
            self.combined_alloc_chart
        )
        top_layout.addWidget(alloc_card)
        
        # Sector Allocation Chart
        sector_card = self.create_chart_card(
            "SECTOR ALLOCATION",
            self.combined_sector_chart
        )
        top_layout.addWidget(sector_card)
        
        splitter.addWidget(top_charts)
        
        # Bottom Charts (Performance & Risk)
        bottom_charts = QWidget()
        bottom_layout = QHBoxLayout(bottom_charts)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        
        # Performance Chart
        perf_card = self.create_chart_card(
            "TOP HOLDINGS PERFORMANCE",
            self.combined_perf_chart
        )
        bottom_layout.addWidget(perf_card)
        
        # Risk Metrics Radar Chart
        risk_card = self.create_chart_card(
            "PORTFOLIO RISK METRICS",
            self.combined_risk_chart
        )
        bottom_layout.addWidget(risk_card)
        
        splitter.addWidget(bottom_charts)
        splitter.setSizes([400, 400])
        layout.addWidget(splitter, 1)
        
        self.stacked_widget.addWidget(page)


    def create_metric_card(self, title, value_label, color):
        """Create a standardized metric card"""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #1E1E1E;
                border-radius: 8px;
                border: 1px solid #333;
            }}
        """)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 15, 15, 15)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 14px; 
            font-weight: bold; 
            color: #64B5F6;
        """)
        layout.addWidget(title_label)
        
        value_label.setStyleSheet(f"""
            font-size: 24px; 
            font-weight: bold; 
            color: {color};
        """)
        value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(value_label)
        
        return card

    def create_pie_chart(self, title, data, colors):
        """Create an enhanced pie chart"""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border-radius: 8px;
                border: 1px solid #333;
            }
        """)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 15, 15, 15)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 14px; 
            font-weight: bold; 
            color: #64B5F6;
            margin-bottom: 10px;
        """)
        layout.addWidget(title_label)
        
        fig = Figure(figsize=(5, 4))
        fig.set_facecolor('#1E1E1E')
        ax = fig.add_subplot(111)
        
        # Create pie chart
        wedges, texts, autotexts = ax.pie(
            data.values(),
            labels=data.keys(),
            autopct='%1.1f%%',
            startangle=90,
            colors=colors,
            textprops={'color': 'white', 'fontsize': 8},
            wedgeprops={'linewidth': 0.5, 'edgecolor': '#121212'}
        )
        
        # Improve label appearance
        for text in texts:
            text.set_color('white')
            text.set_fontsize(9)
        
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(8)
        
        ax.set_title(title, color='white', pad=10)
        
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)
        
        return card
    
    def create_chart_card(self, title, chart_widget):
        """Create a card container for charts"""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border-radius: 8px;
                border: 1px solid #333;
            }
        """)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 15, 15, 15)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 14px; 
            font-weight: bold; 
            color: #64B5F6;
            margin-bottom: 10px;
        """)
        layout.addWidget(title_label)
        
        chart_widget.figure.set_facecolor('#1E1E1E')
        layout.addWidget(chart_widget)
        
        return card


    def create_performance_chart(self, title, performance_data):
        """Create enhanced performance bar chart"""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border-radius: 8px;
                border: 1px solid #333;
            }
        """)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 15, 15, 15)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 14px; 
            font-weight: bold; 
            color: #64B5F6;
            margin-bottom: 10px;
        """)
        layout.addWidget(title_label)
        
        fig = Figure(figsize=(8, 4))
        fig.set_facecolor('#1E1E1E')
        ax = fig.add_subplot(111)
        
        # Prepare data
        stocks = list(performance_data.keys())
        returns = list(performance_data.values())
        colors = ['#4CAF50' if x >= 0 else '#F44336' for x in returns]
        
        # Create bars
        bars = ax.barh(stocks, returns, color=colors)
        
        # Add value labels
        for bar in bars:
            width = bar.get_width()
            ax.text(width if width >=0 else width - 0.5,
                    bar.get_y() + bar.get_height()/2,
                    f'{width:.1f}%',
                    ha='left' if width >=0 else 'right',
                    va='center',
                    color='white')
        
        # Styling
        ax.set_xlabel('Return (%)', color='white')
        ax.tick_params(axis='x', colors='white')
        ax.tick_params(axis='y', colors='white')
        ax.grid(True, color='#333', linestyle='--', axis='x')
        ax.set_facecolor('#1E1E1E')
        
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)
        
        return card

    def create_risk_radar_chart(self, title, metrics):
        """Create enhanced radar chart for risk metrics"""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border-radius: 8px;
                border: 1px solid #333;
            }
        """)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 15, 15, 15)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 14px; 
            font-weight: bold; 
            color: #64B5F6;
            margin-bottom: 10px;
        """)
        layout.addWidget(title_label)
        
        fig = Figure(figsize=(8, 4))
        fig.set_facecolor('#1E1E1E')
        ax = fig.add_subplot(111, polar=True)
        
        # Prepare data
        categories = list(metrics.keys())
        values = list(metrics.values())
        N = len(categories)
        
        # Create radar chart
        angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
        values += values[:1]
        angles += angles[:1]
        
        ax.fill(angles, values, color='#1E88E5', alpha=0.25)
        ax.plot(angles, values, color='#1E88E5', marker='o')
        
        # Set labels
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories, color='white')
        ax.set_yticks([0, 2.5, 5, 7.5, 10])
        ax.set_yticklabels(['Low', 'Medium', 'High', 'Very High', 'Extreme'], color='white')
        
        # Styling
        ax.set_facecolor('#1E1E1E')
        ax.grid(color='#333')
        
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)
        
        return card
            
    def update_combined_dashboard(self):
        """Safe update method that checks for attribute existence"""
        if not hasattr(self, 'combined_total_value'):
            print("Dashboard elements not initialized yet")
            return
        
        try:
            # Initialize all values to zero first
            total_invested = 0
            total_current = 0
            all_holdings = []
            
            # Check if we have any portfolios with holdings
            has_holdings = False
            for portfolio_name, df in self.portfolios.items():
                if not df.empty:
                    has_holdings = True
                    break
                    
            if not has_holdings:
                # No holdings - set all values to zero
                self.combined_total_value.setText("₹0.00")
                self.combined_invested_value.setText("₹0.00")
                self.combined_pl_value.setText("₹0.00 (0.00%)")
                self.combined_today_pl_value.setText("₹0.00 (0.00%)")
                return
                
            # Calculate totals across all portfolios
            for portfolio_name, df in self.portfolios.items():
                if df.empty:
                    continue
                        
                # Ensure required columns exist with proper fallbacks
                if 'Investment Value' not in df.columns:
                    if 'Quantity' in df.columns and 'Purchase Price' in df.columns:
                        df['Investment Value'] = df['Quantity'] * df['Purchase Price']
                    else:
                        print(f"Missing required columns in {portfolio_name}")
                        continue
                        
                if 'Current Value' not in df.columns:
                    print(f"Missing current values in {portfolio_name}")
                    continue
                    
                total_invested += df['Investment Value'].sum()
                total_current += df['Current Value'].sum()
                
                # Collect all holdings for charts
                for _, row in df.iterrows():
                    all_holdings.append({
                        'Name': row.get('Stock Name', row.get('Fund Name', 'Unknown')),
                        'Value': row['Current Value'],
                        'Type': 'Stock' if 'Stock Name' in row else 'Mutual Fund',
                        'Sector': row.get('Sector', 'Unknown')
                    })
            
            # Update the dashboard values with ₹ symbol
            self.combined_total_value.setText(f"₹{total_current:,.2f}")
            self.combined_invested_value.setText(f"₹{total_invested:,.2f}")
            
            # Calculate P/L
            pl = total_current - total_invested
            pl_pct = (pl / total_invested * 100) if total_invested > 0 else 0
            
            # Update P/L display with proper currency symbol
            pl_color = "#4CAF50" if pl >= 0 else "#F44336"
            self.combined_pl_value.setText(
                f"<span style='color:{pl_color}'>₹{pl:+,.2f} ({pl_pct:+.2f}%)</span>"
            )
            
            # Calculate Today's P/L if available (replace placeholder with actual calculation)
            today_pl = 0  # Initialize to zero
            today_pct = 0  # Initialize to zero
            
            # Only calculate if we have daily change data
            if 'Daily P/L' in df.columns:
                today_pl = df['Daily P/L'].sum()
                today_pct = (today_pl / total_current * 100) if total_current > 0 else 0
            
            today_color = "#4CAF50" if today_pl >= 0 else "#F44336"
            self.combined_today_pl_value.setText(
                f"<span style='color:{today_color}'>₹{today_pl:+,.2f} ({today_pct:+.2f}%)</span>"
            )
            
            # Update charts if we have holdings
            if all_holdings:
                self.update_combined_allocation_charts(all_holdings)
                self.update_combined_performance_chart(all_holdings)
                self.update_combined_risk_metrics(all_holdings)
                
        except Exception as e:
            print(f"Error updating dashboard: {str(e)}")
            traceback.print_exc()

    def update_combined_charts(self):
        """Update all dashboard charts"""
        try:
            # Update Allocation Chart
            fig = self.combined_alloc_chart.figure
            fig.clear()
            ax = fig.add_subplot(111)
            # Add your chart drawing code here...
            
            # Update other charts similarly...
            self.combined_alloc_chart.draw()
            self.combined_sector_chart.draw()
            self.combined_perf_chart.draw()
            self.combined_risk_chart.draw()
            
        except Exception as e:
            print(f"Error updating charts: {str(e)}")
    
    def update_combined_allocation_charts(self, holdings):
        if not holdings:
            return
            
        df = pd.DataFrame(holdings)
        
        # Asset allocation chart (Stocks vs Mutual Funds)
        fig1 = self.combined_alloc_chart.figure
        fig1.clear()
        
        ax1 = fig1.add_subplot(111)
        ax1.set_facecolor('#1E1E1E')
        
        asset_values = df.groupby('Type')['Value'].sum()
        colors = ['#1E88E5', '#43A047']
        wedges, texts, autotexts = ax1.pie(
            asset_values,
            labels=asset_values.index,
            autopct='%1.1f%%',
            startangle=90,
            colors=colors,
            textprops={'color': 'white', 'fontsize': 8},
            wedgeprops={'linewidth': 0.5, 'edgecolor': '#121212'}
        )
        
        ax1.set_title("Asset Allocation", color='white', pad=10)
        
        for text in texts:
            text.set_color('white')
            text.set_fontsize(9)
            
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(8)
        
        self.combined_alloc_chart.draw()
        
        # Sector allocation chart
        fig2 = self.combined_sector_chart.figure
        fig2.clear()
        
        ax2 = fig2.add_subplot(111)
        ax2.set_facecolor('#1E1E1E')
        
        sector_values = df.groupby('Sector')['Value'].sum().sort_values(ascending=False)
        colors = plt.cm.Paired(range(len(sector_values)))
        
        if len(sector_values) > 10:  # Group smaller sectors into "Other"
            main_sectors = sector_values[:9]
            other_value = sector_values[9:].sum()
            main_sectors['Other'] = other_value
            sector_values = main_sectors
            
        wedges, texts, autotexts = ax2.pie(
            sector_values,
            labels=sector_values.index,
            autopct='%1.1f%%',
            startangle=90,
            colors=colors,
            textprops={'color': 'white', 'fontsize': 8},
            wedgeprops={'linewidth': 0.5, 'edgecolor': '#121212'}
        )
        
        ax2.set_title("Sector Allocation", color='white', pad=10)
        
        for text in texts:
            text.set_color('white')
            text.set_fontsize(8)
            
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(8)
        
        self.combined_sector_chart.draw()
    
    def update_combined_performance_chart(self, all_holdings):
        if not all_holdings:
            return
            
        fig = self.combined_perf_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        ax.set_facecolor('#1E1E1E')
        
        # Get top 10 holdings by value
        df = pd.DataFrame(all_holdings)
        top_holdings = df.sort_values('Value', ascending=False).head(10)
        
        # Calculate performance metrics for each
        performance = []
        for _, row in top_holdings.iterrows():
            # Calculate invested amount - handle both stock and MF cases
            if 'Quantity' in row and 'Purchase Price' in row:
                invested = row['Quantity'] * row['Purchase Price']
            elif 'Purchase Value' in row:
                invested = row['Purchase Value']
            else:
                invested = 0  # Default if neither is available
                
            current = row['Value']
            pl = current - invested
            pct = (pl / invested * 100) if invested > 0 else 0
            performance.append({
                'Name': row['Name'],
                'P/L %': pct
            })
            
        perf_df = pd.DataFrame(performance)
        
        # Create bar chart
        colors = ['#4CAF50' if x >= 0 else '#F44336' for x in perf_df['P/L %']]
        bars = ax.barh(perf_df['Name'], perf_df['P/L %'], color=colors)
        
        ax.set_title("Top Holdings Performance", color='white', pad=10)
        ax.set_xlabel("Return (%)", color='white')
        ax.tick_params(axis='x', colors='white')
        ax.tick_params(axis='y', colors='white')
        ax.grid(True, color='#333', linestyle='--')
        
        # Add value labels
        for bar in bars:
            width = bar.get_width()
            ax.text(width if width >= 0 else width - 1, 
                    bar.get_y() + bar.get_height()/2,
                    f'{width:.1f}%',
                    ha='left' if width >= 0 else 'right', 
                    va='center',
                    color='white')
        
        fig.tight_layout()
        self.combined_perf_chart.draw()
        
    def update_combined_risk_metrics(self, all_holdings):
        if not all_holdings:
            return
            
        fig = self.combined_risk_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        ax.set_facecolor('#1E1E1E')
        
        # Calculate risk metrics (simplified)
        df = pd.DataFrame(all_holdings)
        total_value = df['Value'].sum()
        
        # Concentration risk (Herfindahl index)
        weights = df['Value'] / total_value
        hhi = (weights ** 2).sum() * 10000  # Scale to 0-10000
        
        # Sector concentration
        sector_counts = df['Sector'].nunique()
        
        # Volatility (placeholder - would normally calculate from historical returns)
        volatility = 0.2
        
        # Beta (placeholder - would normally calculate relative to market)
        beta = 1.0
        
        # Create radar chart
        metrics = ['Concentration', 'Sectors', 'Volatility', 'Beta']
        values = [
            hhi / 1000,  # Scale HHI to 0-10
            sector_counts / 2,  # Scale sector count
            volatility * 10,  # Scale volatility
            beta * 2  # Scale beta
        ]
        
        angles = np.linspace(0, 2*np.pi, len(metrics), endpoint=False)
        values += values[:1]  # Close the radar chart
        angles = np.concatenate((angles, [angles[0]]))
        
        ax.fill(angles, values, color='#1E88E5', alpha=0.25)
        ax.plot(angles, values, color='#1E88E5', marker='o')
        
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(metrics, color='white')
        ax.set_yticks([0, 2.5, 5, 7.5, 10])
        ax.set_yticklabels(['Low', 'Medium', 'High', 'Very High', 'Extreme'], color='white')
        ax.set_title("Portfolio Risk Metrics", color='white', pad=20)
        
        fig.tight_layout()
        self.combined_risk_chart.draw()
    
    def create_portfolio_dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # Page title and portfolio selection
        header = QHBoxLayout()
        title = QLabel("Portfolio Dashboard")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        header.addWidget(title)
        
        # Portfolio selection combo
        self.portfolio_dashboard_combo = QComboBox()
        self.portfolio_dashboard_combo.addItems(sorted(self.portfolios.keys()))
        self.portfolio_dashboard_combo.currentTextChanged.connect(self.update_portfolio_dashboard)
        header.addWidget(QLabel("Portfolio:"))
        header.addWidget(self.portfolio_dashboard_combo)
        
        header.addStretch()
        
        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setIcon(QIcon(":/icons/refresh.png"))
        refresh_btn.clicked.connect(self.update_portfolio_dashboard)
        header.addWidget(refresh_btn)
        
        layout.addLayout(header)
        
        # Summary cards row
        summary_row = QHBoxLayout()
        summary_row.setSpacing(15)
        
        # Current Value Card
        self.portfolio_current_value_card = self.create_dashboard_card(
            "CURRENT VALUE", "₹0.00", "#1E88E5")
        summary_row.addWidget(self.portfolio_current_value_card)
        
        # Invested Value Card
        self.portfolio_invested_value_card = self.create_dashboard_card(
            "INVESTED AMOUNT", "₹0.00", "#7B1FA2")
        summary_row.addWidget(self.portfolio_invested_value_card)
        
        # Total Returns Card
        self.portfolio_returns_card = self.create_dashboard_card(
            "TOTAL RETURNS", "₹0.00 (0.00%)", "#388E3C")
        summary_row.addWidget(self.portfolio_returns_card)
        
        # Today's Returns Card
        self.portfolio_today_returns_card = self.create_dashboard_card(
            "TODAY'S RETURN", "₹0.00 (0.00%)", "#43A047")
        summary_row.addWidget(self.portfolio_today_returns_card)
        
        layout.addLayout(summary_row)
        
        # Allocation chart and performance
        chart_row = QHBoxLayout()
        chart_row.setSpacing(15)
        
        # Allocation pie chart
        alloc_card = QWidget()
        alloc_card.setObjectName("card")
        alloc_layout = QVBoxLayout(alloc_card)
        
        alloc_title = QLabel("HOLDINGS ALLOCATION")
        alloc_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #64B5F6; margin-bottom: 10px;")
        alloc_layout.addWidget(alloc_title)
        
        self.portfolio_alloc_chart = FigureCanvas(Figure(figsize=(5, 4)))
        self.portfolio_alloc_chart.figure.set_facecolor('#1E1E1E')
        alloc_layout.addWidget(self.portfolio_alloc_chart)
        
        chart_row.addWidget(alloc_card)
        
        # Performance chart
        perf_card = QWidget()
        perf_card.setObjectName("card")
        perf_layout = QVBoxLayout(perf_card)
        
        perf_title = QLabel("TOP PERFORMERS")
        perf_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #64B5F6; margin-bottom: 10px;")
        perf_layout.addWidget(perf_title)
        
        self.portfolio_perf_chart = FigureCanvas(Figure(figsize=(5, 4)))
        self.portfolio_perf_chart.figure.set_facecolor('#1E1E1E')
        perf_layout.addWidget(self.portfolio_perf_chart)
        
        chart_row.addWidget(perf_card)
        
        layout.addLayout(chart_row)
        
        # Holdings table
        table_card = QWidget()
        table_card.setObjectName("card")
        table_layout = QVBoxLayout(table_card)
        
        table_title = QLabel("PORTFOLIO HOLDINGS")
        table_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #64B5F6; margin-bottom: 10px;")
        table_layout.addWidget(table_title)
        
        self.portfolio_holdings_table = QTableWidget()
        self.portfolio_holdings_table.setColumnCount(9)
        self.portfolio_holdings_table.setHorizontalHeaderLabels([
            "Stock", "Ticker", "Qty", "Avg Price", "Invested", 
            "Current", "Value", "P/L (₹)", "P/L (%)"
        ])
        self.portfolio_holdings_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.portfolio_holdings_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.portfolio_holdings_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        table_layout.addWidget(self.portfolio_holdings_table)
        layout.addWidget(table_card, 1)
        
        self.stacked_widget.addWidget(page)
        return page
    
    def update_portfolio_dashboard(self):
        portfolio_name = self.portfolio_dashboard_combo.currentText()
        if not portfolio_name or portfolio_name not in self.portfolios:
            self.clear_portfolio_dashboard()
            return
            
        df = self.portfolios[portfolio_name]
        
        # Handle empty portfolio
        if df.empty:
            self.clear_portfolio_dashboard()
            return
        
        # Ensure required columns exist
        required_cols = ['Stock Name', 'Ticker Symbol', 'Quantity', 'Purchase Price']
        if not all(col in df.columns for col in required_cols):
            QMessageBox.warning(self, "Error", "Portfolio data is missing required columns!")
            return
        
        # Calculate values if missing
        if 'Investment Value' not in df.columns:
            df['Investment Value'] = df['Quantity'] * df['Purchase Price']
        
        if 'Current Value' not in df.columns:
            # Fetch current prices first
            self.fetch_current_prices(portfolio_name, df)
            return
            
        # Now update the UI
        self.update_dashboard_ui(portfolio_name, df)

    def clear_portfolio_dashboard(self):
        """Reset all dashboard elements to empty state"""
        self.portfolio_holdings_table.setRowCount(0)
        self.portfolio_current_value_card.layout().itemAt(1).widget().setText("₹0.00")
        self.portfolio_invested_value_card.layout().itemAt(1).widget().setText("₹0.00")
        self.portfolio_returns_card.layout().itemAt(1).widget().setText("₹0.00 (0.00%)")
        
        # Clear charts
        for chart in [self.portfolio_alloc_chart, self.portfolio_perf_chart]:
            fig = chart.figure
            fig.clear()
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "No data available", 
                ha='center', va='center', color='white')
            chart.draw()

    def fetch_current_prices(self, portfolio_name, df):
        """Fetch current prices with better error handling"""
        try:
            tickers = []
            valid_tickers = []
            row_indices = []
            
            # Prepare tickers list and validate
            for idx, row in df.iterrows():
                ticker = row['Ticker Symbol']
                if pd.notna(ticker) and isinstance(ticker, str) and ticker.strip():
                    ticker = ticker.strip().upper()
                    if '.' not in ticker:  # Add .NS suffix if missing
                        ticker += '.NS'
                    tickers.append(ticker)
                    valid_tickers.append(ticker)
                    row_indices.append(idx)
                else:
                    print(f"Invalid ticker at row {idx}: {ticker}")

            if not valid_tickers:
                print("No valid tickers to fetch")
                return

            # Fetch prices in batches to avoid timeouts
            batch_size = 10
            all_prices = {}
            
            for i in range(0, len(valid_tickers), batch_size):
                batch = valid_tickers[i:i + batch_size]
                try:
                    data = yf.download(batch, group_by='ticker', period="1d")
                    
                    for ticker in batch:
                        if ticker in data:
                            if not data[ticker].empty:
                                all_prices[ticker] = data[ticker]['Close'].iloc[-1]
                            else:
                                print(f"No data for {ticker}")
                                all_prices[ticker] = None
                        else:
                            print(f"Ticker {ticker} not in response")
                            all_prices[ticker] = None
                            
                except Exception as e:
                    print(f"Error fetching batch {i//batch_size}: {str(e)}")
                    for ticker in batch:
                        all_prices[ticker] = None

            # Update the DataFrame with prices
            for ticker, idx in zip(valid_tickers, row_indices):
                df.at[idx, 'Current Price'] = all_prices.get(ticker)
                
                if pd.notna(df.at[idx, 'Current Price']):
                    current_price = df.at[idx, 'Current Price']
                    purchase_price = df.at[idx, 'Purchase Price']
                    quantity = df.at[idx, 'Quantity']
                    
                    df.at[idx, 'Current Value'] = current_price * quantity
                    df.at[idx, 'Profit/Loss'] = (current_price - purchase_price) * quantity
                    if purchase_price > 0:
                        df.at[idx, 'P/L %'] = ((current_price - purchase_price) / purchase_price) * 100
                    else:
                        df.at[idx, 'P/L %'] = 0

            self.portfolios[portfolio_name] = df
            self.save_data()
            self.update_portfolio_dashboard()

        except Exception as e:
            print(f"Error in fetch_current_prices: {str(e)}")
            traceback.print_exc()

    def handle_fetched_prices(self, portfolio_name, prices, invalid_tickers=[]):
        """Process fetched prices and update portfolio"""
        try:
            if not prices:
                self.show_message("No price data received")
                return
                
            # Update the portfolio DataFrame
            df = self.portfolios[portfolio_name]
            df['Current Price'] = df['Ticker Symbol'].map(
                lambda x: prices.get(x.strip().upper() + ('' if '.' in x else '.NS'), None)
            )
            
            # Calculate current values
            df['Current Value'] = df['Quantity'] * df['Current Price']
            df['Profit/Loss'] = df['Current Value'] - df['Investment Value']
            df['P/L %'] = (df['Profit/Loss'] / df['Investment Value']) * 100
            
            # Handle invalid tickers
            if invalid_tickers:
                self.show_message(f"Could not fetch prices for: {', '.join(invalid_tickers)}")
                
            # Update UI and save data
            self.update_portfolio_dashboard()
            self.save_data()
            
        except Exception as e:
            self.show_message(f"Error processing prices: {str(e)}")
            print(f"Error in handle_fetched_prices: {traceback.format_exc()}")

    def handle_price_fetch_error(self, error_msg):
        """Handle errors during price fetching"""
        self.hide_loading_overlay()
        self.show_message(f"Price fetch error: {error_msg}")
        print(f"Price fetch error: {error_msg}")

    def calculate_portfolio_metrics(self, df):
        """Calculate all derived portfolio metrics"""
        # Basic calculations
        df['Investment Value'] = df['Quantity'] * df['Purchase Price']
        df['Current Value'] = df['Quantity'] * df['Current Price']
        df['Profit/Loss'] = df['Current Value'] - df['Investment Value']
        df['P/L %'] = (df['Profit/Loss'] / df['Investment Value']) * 100
        
        # Calculate daily change if possible
        if 'Daily P/L' not in df.columns:
            df['Daily P/L'] = 0.0  # Initialize
            
        # Calculate sector allocation if sector data exists
        if 'Sector' not in df.columns:
            df['Sector'] = 'Unknown'

    def update_dashboard_ui(self, portfolio_name, df):
        """Update all UI components with current portfolio data"""
        # Calculate totals
        total_invested = df['Investment Value'].sum()
        total_current = df['Current Value'].sum()
        total_pl = total_current - total_invested
        total_pl_pct = (total_pl / total_invested * 100) if total_invested > 0 else 0
        
        # Update summary cards with Rupee symbol
        self.portfolio_current_value_card.layout().itemAt(1).widget().setText(
            f"₹{total_current:,.2f}")
        self.portfolio_invested_value_card.layout().itemAt(1).widget().setText(
            f"₹{total_invested:,.2f}")
        
        # Set P/L color based on value
        pl_color = "#4CAF50" if total_pl >= 0 else "#F44336"
        self.portfolio_returns_card.layout().itemAt(1).widget().setText(
            f"<span style='color:{pl_color}'>₹{total_pl:+,.2f} ({total_pl_pct:+.2f}%)</span>")
        
        # Update holdings table
        self.update_holdings_table(df)
        
        # Update charts
        self.update_portfolio_allocation_chart(df)
        self.update_portfolio_performance_chart(df)
        
        # Update window title
        self.setWindowTitle(f"Quantum Tracker Pro - {portfolio_name}")

    def handle_dashboard_error(self, error):
        """Handle errors during dashboard update"""
        error_msg = str(error)
        print(f"Dashboard update error: {error_msg}\n{traceback.format_exc()}")
        
        QMessageBox.critical(
            self, 
            "Dashboard Error",
            f"Failed to update portfolio dashboard:\n{error_msg}"
        )
        
        self.clear_portfolio_dashboard()
    
    
    def update_holdings_table(self, df):
        self.portfolio_holdings_table.setRowCount(len(df))
        
        for row in range(len(df)):
            stock = df.iloc[row]
            
            self.portfolio_holdings_table.setItem(row, 0, QTableWidgetItem(stock['Stock Name']))
            self.portfolio_holdings_table.setItem(row, 1, QTableWidgetItem(stock['Ticker Symbol']))
            self.portfolio_holdings_table.setItem(row, 2, QTableWidgetItem(f"{stock['Quantity']:.2f}"))
            self.portfolio_holdings_table.setItem(row, 3, QTableWidgetItem(f"¥{stock['Purchase Price']:.2f}"))
            self.portfolio_holdings_table.setItem(row, 4, QTableWidgetItem(f"¥{stock['Investment Value']:,.2f}"))
            self.portfolio_holdings_table.setItem(row, 5, QTableWidgetItem(f"¥{stock['Current Price']:.2f}"))
            self.portfolio_holdings_table.setItem(row, 6, QTableWidgetItem(f"¥{stock['Current Value']:,.2f}"))
            
            # P/L
            pl = stock['Profit/Loss']
            pl_item = QTableWidgetItem(f"¥{pl:+,.2f}")
            pl_item.setForeground(QColor('#4CAF50') if pl >= 0 else QColor('#F44336'))
            self.portfolio_holdings_table.setItem(row, 7, pl_item)
            
            # P/L %
            pl_pct = stock['P/L %']
            pl_pct_item = QTableWidgetItem(f"{pl_pct:+.2f}%")
            pl_pct_item.setForeground(QColor('#4CAF50') if pl_pct >= 0 else QColor('#F44336'))
            self.portfolio_holdings_table.setItem(row, 8, pl_pct_item)
    
    def update_portfolio_prices(self, portfolio_name, prices):
        """Update portfolio with current prices and refresh display"""
        df = self.portfolios[portfolio_name]
        
        # Update current prices
        df['Current Price'] = df['Ticker Symbol'].map(prices)
        
        # Save the updated data
        self.portfolios[portfolio_name] = df
        self.save_data()
        
        # Refresh the dashboard
        self.update_portfolio_dashboard()
       
    def update_portfolio_allocation_chart(self, df):
        fig = self.portfolio_alloc_chart.figure
        fig.clear()
        
        if df.empty:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "No holdings data", 
                ha='center', va='center', color='white')
            self.portfolio_alloc_chart.draw()
            return
        
        # Group by stock name and sum current values
        holdings = df.groupby('Stock Name')['Current Value'].sum().sort_values(ascending=False)
        
        ax = fig.add_subplot(111)
        ax.set_facecolor('#1E1E1E')
        
        # Get top 10 holdings, group others as "Other"
        if len(holdings) > 10:
            main_holdings = holdings[:9]
            other_value = holdings[9:].sum()
            main_holdings['Other'] = other_value
            holdings = main_holdings
        
        colors = plt.cm.Paired(range(len(holdings)))
        wedges, texts, autotexts = ax.pie(
            holdings,
            labels=holdings.index,
            autopct=lambda p: f'{p:.1f}%\n(₹{p * holdings.sum()/100:,.0f})',
            startangle=90,
            colors=colors,
            textprops={'color': 'white', 'fontsize': 8},
            wedgeprops={'linewidth': 0.5, 'edgecolor': '#121212'}
        )
        
        ax.set_title("Holdings Allocation", color='white', pad=10)
        
        for text in texts:
            text.set_color('white')
            text.set_fontsize(8)
            
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(8)
        
        self.portfolio_alloc_chart.draw()

    def update_portfolio_performance_chart(self, df):
        fig = self.portfolio_perf_chart.figure
        fig.clear()
        
        if df.empty:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "No performance data", 
                ha='center', va='center', color='white')
            self.portfolio_perf_chart.draw()
            return
        
        # Calculate performance metrics for each stock
        performance = []
        for _, row in df.iterrows():
            pl = row['Current Value'] - row['Investment Value']
            pct = (pl / row['Investment Value'] * 100) if row['Investment Value'] > 0 else 0
            performance.append({
                'Stock': row['Stock Name'],
                'Return %': pct
            })
        
        perf_df = pd.DataFrame(performance).sort_values('Return %', ascending=False).head(5)
        
        ax = fig.add_subplot(111)
        ax.set_facecolor('#1E1E1E')
        
        colors = ['#4CAF50' if x >= 0 else '#F44336' for x in perf_df['Return %']]
        bars = ax.barh(perf_df['Stock'], perf_df['Return %'], color=colors)
        
        ax.set_title("Top Performers", color='white', pad=10)
        ax.set_xlabel("Return (%)", color='white')
        ax.tick_params(axis='x', colors='white')
        ax.tick_params(axis='y', colors='white')
        
        # Add value labels
        for bar in bars:
            width = bar.get_width()
            ax.text(width if width >= 0 else width - 1, 
                    bar.get_y() + bar.get_height()/2,
                    f'{width:.1f}%',
                    ha='left' if width >= 0 else 'right', 
                    va='center',
                    color='white')
        
        self.portfolio_perf_chart.draw()    
    
    def create_dashboard_card(self, title, value, color):
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #1E1E1E;
                border-radius: 8px;
                border: 1px solid #333;
                padding: 15px;
            }}
        """)
        
        layout = QVBoxLayout(card)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #64B5F6;")
        layout.addWidget(title_label)
        
        value_label = QLabel(value)
        value_label.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {color};")
        value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(value_label)
        
        return card
    
    def update_portfolio_allocation_chart(self, df):
        fig = self.portfolio_alloc_chart.figure
        fig.clear()
        
        if df.empty:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "No holdings data", 
                ha='center', va='center', color='white')
            self.portfolio_alloc_chart.draw()
            return
        
        # Group by stock name and sum current values
        holdings = df.groupby('Stock Name')['Current Value'].sum().sort_values(ascending=False)
        
        ax = fig.add_subplot(111)
        ax.set_facecolor('#1E1E1E')
        
        # Get top 10 holdings, group others as "Other"
        if len(holdings) > 10:
            main_holdings = holdings[:9]
            other_value = holdings[9:].sum()
            main_holdings['Other'] = other_value
            holdings = main_holdings
        
        colors = plt.cm.Paired(range(len(holdings)))
        wedges, texts, autotexts = ax.pie(
            holdings,
            labels=holdings.index,
            autopct=lambda p: f'{p:.1f}%\n(₹{p * holdings.sum()/100:,.0f})',
            startangle=90,
            colors=colors,
            textprops={'color': 'white', 'fontsize': 8},
            wedgeprops={'linewidth': 0.5, 'edgecolor': '#121212'}
        )
        
        ax.set_title("Holdings Allocation", color='white', pad=10)
        
        for text in texts:
            text.set_color('white')
            text.set_fontsize(8)
            
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(8)
        
        self.portfolio_alloc_chart.draw()

    def update_portfolio_performance_chart(self, df):
        fig = self.portfolio_perf_chart.figure
        fig.clear()
        
        if df.empty:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "No performance data", 
                ha='center', va='center', color='white')
            self.portfolio_perf_chart.draw()
            return
        
        # Calculate performance metrics for each stock
        performance = []
        for _, row in df.iterrows():
            pl = row['Current Value'] - row['Investment Value']
            pct = (pl / row['Investment Value'] * 100) if row['Investment Value'] > 0 else 0
            performance.append({
                'Stock': row['Stock Name'],
                'Return %': pct
            })
        
        perf_df = pd.DataFrame(performance).sort_values('Return %', ascending=False).head(5)
        
        ax = fig.add_subplot(111)
        ax.set_facecolor('#1E1E1E')
        
        colors = ['#4CAF50' if x >= 0 else '#F44336' for x in perf_df['Return %']]
        bars = ax.barh(perf_df['Stock'], perf_df['Return %'], color=colors)
        
        ax.set_title("Top Performers", color='white', pad=10)
        ax.set_xlabel("Return (%)", color='white')
        ax.tick_params(axis='x', colors='white')
        ax.tick_params(axis='y', colors='white')
        
        # Add value labels
        for bar in bars:
            width = bar.get_width()
            ax.text(width if width >= 0 else width - 1, 
                    bar.get_y() + bar.get_height()/2,
                    f'{width:.1f}%',
                    ha='left' if width >= 0 else 'right', 
                    va='center',
                    color='white')
        
        self.portfolio_perf_chart.draw()
        
    def create_news_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # Page title
        title = QLabel("Market & Portfolio News")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        layout.addWidget(title)
        
        # News source selection
        source_row = QHBoxLayout()
        source_row.setSpacing(10)
        
        source_label = QLabel("News Source:")
        self.news_source_combo = QComboBox()
        self.news_source_combo.addItems(["All", "Portfolio Stocks", "Market News"])
        self.news_source_combo.currentTextChanged.connect(self.refresh_news)
        
        source_row.addWidget(source_label)
        source_row.addWidget(self.news_source_combo)
        source_row.addStretch()
        
        refresh_btn = QPushButton("Refresh News")
        refresh_btn.setIcon(QIcon(":/icons/refresh.png"))
        refresh_btn.clicked.connect(self.refresh_news)
        source_row.addWidget(refresh_btn)
        
        layout.addLayout(source_row)
        
        # News table
        self.news_table = QTableWidget()
        self.news_table.setColumnCount(5)
        self.news_table.setHorizontalHeaderLabels(["Date", "Source", "Stock", "Title", "Link"])
        self.news_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.news_table.verticalHeader().setVisible(False)
        self.news_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.news_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        # Hide the link column (we'll use it when opening the article)
        self.news_table.setColumnHidden(4, True)
        
        layout.addWidget(self.news_table, 1)
        
        # News viewer
        self.news_viewer = QWebEngineView()
        self.news_viewer.setMinimumHeight(400)
        layout.addWidget(self.news_viewer)
        
        # Connect row selection to display article
        self.news_table.itemSelectionChanged.connect(self.display_selected_news)
        
        # Load initial news
        self.refresh_news()
        
        self.stacked_widget.addWidget(page)
        
    def refresh_news(self):
        source = self.news_source_combo.currentText()
        
        # Get tickers for portfolio stocks if needed
        tickers = []
        if source == "Portfolio Stocks" or source == "All":
            for portfolio in self.portfolios.values():
                if 'Ticker Symbol' in portfolio.columns:
                    tickers.extend(portfolio['Ticker Symbol'].tolist())
        
        # Clear existing news if switching to market news only
        if source == "Market News" and not tickers:
            self.news_data = []
            self.update_news_table()
            return
            
        # Fetch news in background
        if tickers or source == "All":
            self.news_table.setRowCount(0)
            self.news_table.setRowCount(1)
            self.news_table.setItem(0, 0, QTableWidgetItem("Loading news..."))
            
            worker = NewsFetcher(tickers)
            worker.news_fetched.connect(self.handle_news_data)
            worker.finished_signal.connect(lambda: self.worker_finished(worker))
            self.workers.append(worker)
            worker.start()
            
    def handle_news_data(self, news_items):
        self.news_data = sorted(news_items, key=lambda x: x.get('providerPublishTime', 0), reverse=True)
        self.update_news_table()
        
    def update_news_table(self):
        source_filter = self.news_source_combo.currentText()
        filtered_news = []
        
        for item in self.news_data:
            if source_filter == "All":
                filtered_news.append(item)
            elif source_filter == "Portfolio Stocks" and item.get('ticker', '') != '':
                filtered_news.append(item)
            elif source_filter == "Market News" and item.get('ticker', '') == '':
                filtered_news.append(item)
        
        self.news_table.setRowCount(len(filtered_news))
        
        for row, item in enumerate(filtered_news):
            # Convert timestamp
            timestamp = item.get('providerPublishTime', 0)
            if timestamp:
                date_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')
            else:
                date_str = "Unknown"
            
            # Get source
            source = item.get('publisher', 'Unknown')
            
            # Get stock ticker if available
            ticker = item.get('ticker', '')
            
            self.news_table.setItem(row, 0, QTableWidgetItem(date_str))
            self.news_table.setItem(row, 1, QTableWidgetItem(source))
            self.news_table.setItem(row, 2, QTableWidgetItem(ticker))
            self.news_table.setItem(row, 3, QTableWidgetItem(item.get('title', 'No title')))
            self.news_table.setItem(row, 4, QTableWidgetItem(item.get('link', '')))
            
            # Color portfolio stock news differently
            if ticker:
                for col in range(4):
                    self.news_table.item(row, col).setForeground(QColor('#64B5F6'))
        
    def display_selected_news(self):
        selected = self.news_table.currentRow()
        if selected >= 0 and selected < len(self.news_data):
            link = self.news_table.item(selected, 4).text()
            if link:
                self.news_viewer.setUrl(QUrl(link))
                
    def create_company_research_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # Page title
        title = QLabel("Company Research")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        layout.addWidget(title)
        
        # Stock selection
        stock_row = QHBoxLayout()
        stock_row.setSpacing(10)
        
        stock_label = QLabel("Stock:")
        self.research_stock_combo = QComboBox()
        
        # Populate with all stocks from portfolios
        all_stocks = set()
        for portfolio in self.portfolios.values():
            if 'Ticker Symbol' in portfolio.columns:
                all_stocks.update(zip(
                    portfolio['Stock Name'], 
                    portfolio['Ticker Symbol']
                ))
        
        for name, ticker in sorted(all_stocks):
            self.research_stock_combo.addItem(f"{name} ({ticker})", ticker)
        
        stock_row.addWidget(stock_label)
        stock_row.addWidget(self.research_stock_combo)
        stock_row.addStretch()
        
        analyze_btn = QPushButton("Analyze")
        analyze_btn.setIcon(QIcon(":/icons/analyze.png"))
        analyze_btn.setObjectName("primary-button")
        analyze_btn.clicked.connect(self.analyze_company)
        stock_row.addWidget(analyze_btn)
        
        layout.addLayout(stock_row)
        
        # Tab widget for different analysis views
        self.research_tabs = QTabWidget()
        layout.addWidget(self.research_tabs, 1)
        
        # Overview tab
        overview_tab = QWidget()
        overview_layout = QVBoxLayout(overview_tab)
        
        self.overview_text = QTextEdit()
        self.overview_text.setReadOnly(True)
        overview_layout.addWidget(self.overview_text)
        
        self.research_tabs.addTab(overview_tab, "Overview")
        
        # Financials tab
        financials_tab = QWidget()
        financials_layout = QVBoxLayout(financials_tab)
        
        self.financials_table = QTableWidget()
        financials_layout.addWidget(self.financials_table)
        
        self.research_tabs.addTab(financials_tab, "Financials")
        
        # Price chart tab
        chart_tab = QWidget()
        chart_layout = QVBoxLayout(chart_tab)
        
        self.price_chart = FigureCanvas(Figure(figsize=(10, 5)))
        self.price_chart.figure.set_facecolor('#1E1E1E')
        chart_layout.addWidget(self.price_chart)
        
        self.research_tabs.addTab(chart_tab, "Price Chart")
        
        # Recommendations tab
        rec_tab = QWidget()
        rec_layout = QVBoxLayout(rec_tab)
        
        self.rec_chart = FigureCanvas(Figure(figsize=(10, 4)))
        self.rec_chart.figure.set_facecolor('#1E1E1E')
        rec_layout.addWidget(self.rec_chart)
        
        self.research_tabs.addTab(rec_tab, "Recommendations")
        
        # Initialize with first stock if available
        if self.research_stock_combo.count() > 0:
            self.analyze_company()
        
        self.stacked_widget.addWidget(page)
        
    def analyze_company(self):
        if self.research_stock_combo.count() == 0:
            return
            
        ticker = self.research_stock_combo.currentData()
        
        # Show loading state
        self.overview_text.setPlainText(f"Loading analysis for {ticker}...")
        self.financials_table.setRowCount(1)
        self.financials_table.setItem(0, 0, QTableWidgetItem("Loading financial data..."))
        
        # Clear charts
        for fig in [self.price_chart.figure, self.rec_chart.figure]:
            fig.clear()
            fig.text(0.5, 0.5, "Loading chart...", 
                    ha='center', va='center', color='white')
            fig.canvas.draw()
        
        # Fetch data in background
        worker = CompanyAnalysisWorker(ticker)
        worker.analysis_complete.connect(self.display_company_analysis)
        worker.finished_signal.connect(lambda: self.worker_finished(worker))
        self.workers.append(worker)
        worker.start()
        
        # Fetch price history
        history_worker = StockHistoryWorker(ticker, period="5y")
        history_worker.data_fetched.connect(self.display_price_history)
        history_worker.finished_signal.connect(lambda: self.worker_finished(history_worker))
        self.workers.append(history_worker)
        history_worker.start()
        
    def display_company_analysis(self, ticker, analysis):
        info = analysis.get('info', {})
        
        # Update overview tab
        overview_html = f"""
        <style>
            body {{ font-family: Arial; color: white; }}
            h1 {{ color: #64B5F6; }}
            .section {{ margin-bottom: 15px; }}
            .label {{ font-weight: bold; color: #64B5F6; }}
            .value {{ margin-left: 10px; }}
            .negative {{ color: #F44336; }}
            .positive {{ color: #4CAF50; }}
        </style>
        <h1>{info.get('longName', ticker)} ({ticker})</h1>
        
        <div class="section">
            <div><span class="label">Sector:</span> <span class="value">{info.get('sector', 'N/A')}</span></div>
            <div><span class="label">Industry:</span> <span class="value">{info.get('industry', 'N/A')}</span></div>
            <div><span class="label">Employees:</span> <span class="value">{info.get('fullTimeEmployees', 'N/A'):,}</span></div>
            <div><span class="label">Country:</span> <span class="value">{info.get('country', 'N/A')}</span></div>
        </div>
        
        <div class="section">
            <div><span class="label">Current Price:</span> <span class="value">${info.get('currentPrice', info.get('regularMarketPrice', 'N/A')):,.2f}</span></div>
            <div><span class="label">Market Cap:</span> <span class="value">${info.get('marketCap', 'N/A'):,}</span></div>
            <div><span class="label">52 Week Range:</span> <span class="value">${info.get('fiftyTwoWeekLow', 'N/A'):,.2f} - ${info.get('fiftyTwoWeekHigh', 'N/A'):,.2f}</span></div>
            <div><span class="label">Volume (Avg):</span> <span class="value">{info.get('averageVolume', 'N/A'):,}</span></div>
        </div>
        
        <div class="section">
            <div><span class="label">P/E Ratio:</span> <span class="value">{info.get('trailingPE', 'N/A')}</span></div>
            <div><span class="label">P/B Ratio:</span> <span class="value">{info.get('priceToBook', 'N/A')}</span></div>
            <div><span class="label">EPS:</span> <span class="value">{info.get('trailingEps', 'N/A')}</span></div>
            <div><span class="label">Dividend Yield:</span> <span class="value">{info.get('dividendYield', 'N/A')}</span></div>
        </div>
        
        <div class="section">
            <h3>Company Description</h3>
            <p>{info.get('longBusinessSummary', 'No description available.')}</p>
        </div>
        """
        
        self.overview_text.setHtml(overview_html)
        
        # Update financials tab
        financials = analysis.get('financials', pd.DataFrame())
        if not financials.empty:
            self.financials_table.setRowCount(len(financials))
            self.financials_table.setColumnCount(len(financials.columns))
            self.financials_table.setHorizontalHeaderLabels([str(col) for col in financials.columns])
            
            for i, (index, row) in enumerate(financials.iterrows()):
                self.financials_table.setVerticalHeaderItem(i, QTableWidgetItem(str(index)))
                for j, value in enumerate(row):
                    self.financials_table.setItem(i, j, QTableWidgetItem(str(value)))
        
        # Update recommendations chart
        recs = analysis.get('recommendations', pd.DataFrame())
        if not recs.empty:
            fig = self.rec_chart.figure
            fig.clear()
            
            ax = fig.add_subplot(111)
            ax.set_facecolor('#1E1E1E')

            try:
                # Ensure Date column is datetime type
                if 'Date' in recs.columns:
                    recs['Date'] = pd.to_datetime(recs['Date'])
                    recs['YearMonth'] = recs['Date'].dt.to_period('M').astype(str)
                else:
                    # If no Date column, use the index if it's datetime
                    if isinstance(recs.index, pd.DatetimeIndex):
                        recs['YearMonth'] = recs.index.to_period('M').astype(str)
                    else:
                        # If no datetime data available, skip the chart
                        ax.text(0.5, 0.5, "No date information available", 
                            ha='center', va='center', color='white')
                        self.rec_chart.draw()
                        return

                # Group by year-month and count recommendations
                monthly_counts = recs.groupby(['YearMonth', 'To Grade']).size().unstack().fillna(0)
                
                # Plot stacked bar chart
                colors = {
                    'Buy': '#4CAF50',
                    'Strong Buy': '#2E7D32',
                    'Hold': '#FFC107',
                    'Underperform': '#FF9800',
                    'Sell': '#F44336',
                    'Strong Sell': '#C62828'
                }
                
                # Only use columns that exist in the data
                available_colors = {k: v for k, v in colors.items() if k in monthly_counts.columns}
                
                monthly_counts.plot(kind='bar', stacked=True, ax=ax, color=available_colors.values())
                
                ax.set_title("Analyst Recommendations Over Time", color='white', pad=10)
                ax.set_xlabel("Date", color='white')
                ax.set_ylabel("Number of Recommendations", color='white')
                ax.tick_params(axis='x', colors='white', rotation=45)
                ax.tick_params(axis='y', colors='white')
                ax.legend(title='Recommendation', facecolor='#1E1E1E', edgecolor='#1E1E1E', 
                        labelcolor='white', title_fontproperties={'weight': 'bold'})
                
                fig.tight_layout()
                self.rec_chart.draw()
                
            except Exception as e:
                print(f"Error creating recommendations chart: {str(e)}")
                ax.text(0.5, 0.5, "Error displaying recommendations", 
                    ha='center', va='center', color='white')
                self.rec_chart.draw()
        
    def display_price_history(self, ticker, history):
        if history.empty:
            return
            
        fig = self.price_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        ax.set_facecolor('#1E1E1E')
        
        # Calculate moving averages
        history['MA50'] = history['Close'].rolling(window=50).mean()
        history['MA200'] = history['Close'].rolling(window=200).mean()
        
        # Plot price and moving averages
        ax.plot(history.index, history['Close'], label='Price', color='#64B5F6', linewidth=2)
        ax.plot(history.index, history['MA50'], label='50-day MA', color='#FFC107', linestyle='--')
        ax.plot(history.index, history['MA200'], label='200-day MA', color='#4CAF50', linestyle='--')
        
        ax.set_title(f"{ticker} Price History (5 Years)", color='white', pad=10)
        ax.set_xlabel("Date", color='white')
        ax.set_ylabel("Price ($)", color='white')
        ax.tick_params(axis='x', colors='white')
        ax.tick_params(axis='y', colors='white')
        ax.grid(True, color='#333', linestyle='--')
        ax.legend(facecolor='#1E1E1E', edgecolor='#1E1E1E', labelcolor='white')
        

        
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
                    f"<div style='margin-bottom: 5px;'>"
                    f"<span style='color:white; font-weight:bold;'>{name.ljust(10)}</span> "
                    f"<span style='color:{color};'>{data['Current']:,.2f} {arrow} {pct_change:+.2f}%</span>"
                    f"</div>"
                )
            
            self.market_summary.setText(summary_text)
        
        worker = MarketDataWorker(indices)
        worker.data_fetched.connect(update_summary)
        worker.finished_signal.connect(lambda: self.worker_finished(worker))
        self.workers.append(worker)
        worker.start()

    def refresh_portfolio_summary(self):
        if not hasattr(self, 'portfolio_value'):
            return
            
        if not self.portfolios:
            self.portfolio_value.setText("₹0.00")
            self.portfolio_change.setText("+0.00% (₹0.00)")
            self.portfolio_perf.setText("+0.00%")
            self.portfolio_daily.setText("Today: +0.00%")
            return
            
        total_investment = 0
        total_current = 0
        total_daily_pl = 0
        
        for portfolio in self.portfolios.values():
            # Skip if empty
            if portfolio.empty:
                continue
                
            # Ensure required columns exist
            if 'Investment Value' not in portfolio.columns:
                portfolio['Investment Value'] = portfolio['Quantity'] * portfolio['Purchase Price']
                
            if 'Current Value' not in portfolio.columns:
                portfolio['Current Value'] = portfolio['Quantity'] * portfolio['Purchase Price']
                
            # Calculate totals
            total_investment += portfolio['Investment Value'].sum()
            total_current += portfolio['Current Value'].sum()
            
            # Calculate daily P/L if available
            if 'Daily P/L' in portfolio.columns:
                total_daily_pl += portfolio['Daily P/L'].sum()
        
        pl = total_current - total_investment
        pct_pl = (pl / total_investment * 100) if total_investment > 0 else 0
        daily_pct = (total_daily_pl / total_current * 100) if total_current > 0 else 0
        
        # Update summary cards
        self.portfolio_value.setText(f"₹{total_current:,.2f}")
        
        pl_color = "#4CAF50" if pl >= 0 else "#F44336"
        self.portfolio_change.setText(
            f"<span style='color:{pl_color};'>{pct_pl:+.2f}% (₹{pl:+,.2f})</span>"
        )
        
        perf_color = "#4CAF50" if pct_pl >= 0 else "#F44336"
        self.portfolio_perf.setText(
            f"<span style='color:{perf_color};'>{pct_pl:+.2f}%</span>"
        )
        
        daily_color = "#4CAF50" if total_daily_pl >= 0 else "#F44336"
        self.portfolio_daily.setText(
            f"<span style='color:{daily_color};'>Today: {daily_pct:+.2f}%</span>"
        )
        
        # Update allocation chart
        self.update_allocation_chart()
                
    def update_allocation_chart(self):
        fig = self.alloc_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        ax.set_facecolor('#1E1E1E')
        
        # Get all holdings across portfolios
        all_holdings = []
        for port_name, port_data in self.portfolios.items():
            if 'Current Value' not in port_data.columns:
                port_data['Current Value'] = port_data['Quantity'] * port_data['Purchase Price']
            
            for _, row in port_data.iterrows():
                all_holdings.append({
                    'Name': row.get('Stock Name', row.get('Fund Name', 'Unknown')),
                    'Value': row['Current Value'],
                    'Portfolio': port_name
                })
        
        if not all_holdings:
            ax.text(0.5, 0.5, "No holdings data", 
                   ha='center', va='center', color='white')
            self.alloc_chart.draw()
            return
            
        # Create DataFrame and group by portfolio
        df = pd.DataFrame(all_holdings)
        portfolio_values = df.groupby('Portfolio')['Value'].sum()
        
        # Plot
        colors = plt.cm.Paired(range(len(portfolio_values)))
        wedges, texts, autotexts = ax.pie(
            portfolio_values,
            labels=portfolio_values.index,
            autopct=lambda p: f'₹{p * portfolio_values.sum()/100:,.0f}',
            startangle=90,
            colors=colors,
            textprops={'color': 'white', 'fontsize': 8},
            wedgeprops={'linewidth': 0.5, 'edgecolor': '#121212'}
        )
        
        ax.set_title("Portfolio Allocation", color='white', pad=10)
        
        # Improve label visibility
        for text in texts:
            text.set_color('white')
            text.set_fontsize(9)
            
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(8)
        
        self.alloc_chart.draw()

    def refresh_activity_log(self):
        try:
            with open("portfolio_audit.log", "r") as f:
                log_entries = [line.strip() for line in f.readlines() if line.strip()]
        except FileNotFoundError:
            log_entries = []
        
        recent_entries = reversed(log_entries[-5:]) if log_entries else ["No recent activity"]
        
        html = "<style>"
        html += "body { font-family: Arial; font-size: 12px; color: #DDD; }"
        html += ".entry { margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid #333; }"
        html += ".time { color: #AAA; font-size: 11px; }"
        html += ".action { color: #64B5F6; font-weight: bold; }"
        html += ".portfolio { color: #FFC107; }"
        html += ".item { color: #4CAF50; }"
        html += ".details { color: #BBB; font-style: italic; }"
        html += "</style>"
        
        for entry in recent_entries:
            parts = entry.split(" | ")
            if len(parts) == 5:
                timestamp, action, portfolio, item, details = parts
                html += f"""
                    <div class="entry">
                        <span class="time">[{timestamp}]</span>
                        <span class="action">{action}</span>
                        <span class="portfolio">{portfolio}</span>
                        {f'<span class="item">{item}</span>' if item else ''}
                        {f'<span class="details">- {details}</span>' if details else ''}
                    </div>
                """
            else:
                html += f'<div class="entry">{entry}</div>'
        
        self.activity_log.setHtml(html)

    def generate_quick_report(self):
        # Create a simple PDF report with portfolio summary
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Report As",
            "",
            "PDF Files (*.pdf)",
            options=options
        )
        
        if not file_path:
            return
            
        try:
            from matplotlib.backends.backend_pdf import PdfPages
            
            with PdfPages(file_path) as pdf:
                # Create a title page
                plt.figure(figsize=(8.27, 11.69))  # A4 size
                plt.text(0.5, 0.7, "Portfolio Summary Report", 
                        ha='center', va='center', fontsize=20)
                plt.text(0.5, 0.6, datetime.now().strftime("%d %B %Y"), 
                        ha='center', va='center', fontsize=12)
                plt.axis('off')
                pdf.savefig()
                plt.close()
                
                # Portfolio summary page
                fig, ax = plt.subplots(figsize=(8.27, 11.69))
                
                # Portfolio summary table
                portfolio_data = []
                for name, df in self.portfolios.items():
                    invested = df['Investment Value'].sum() if 'Investment Value' in df.columns else (df['Quantity'] * df['Purchase Price']).sum()
                    current = df['Current Value'].sum() if 'Current Value' in df.columns else (df['Quantity'] * df['Purchase Price']).sum()
                    pl = current - invested
                    pct = (pl / invested * 100) if invested > 0 else 0
                    
                    portfolio_data.append([name, f"₹{invested:,.2f}", f"₹{current:,.2f}", 
                                          f"₹{pl:+,.2f}", f"{pct:+.2f}%"])
                
                if portfolio_data:
                    table = plt.table(cellText=portfolio_data,
                                    colLabels=["Portfolio", "Invested", "Current", "P/L", "P/L %"],
                                    loc='center',
                                    cellLoc='center')
                    
                    table.auto_set_font_size(False)
                    table.set_fontsize(10)
                    table.scale(1, 1.5)
                
                plt.title("Portfolio Summary", pad=20)
                plt.axis('off')
                pdf.savefig()
                plt.close()
                
            QMessageBox.information(self, "Success", "Report generated successfully!")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to generate report: {str(e)}")

    def create_portfolio_management_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # Page title
        title = QLabel("Portfolio Management")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        layout.addWidget(title)
        
        # Portfolio list card
        list_card = QWidget()
        list_card.setObjectName("card")
        list_layout = QVBoxLayout(list_card)
        
        list_title = QLabel("YOUR PORTFOLIOS")
        list_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #64B5F6; margin-bottom: 10px;")
        list_layout.addWidget(list_title)
        
        self.portfolio_list = QListWidget()
        self.portfolio_list.setStyleSheet("font-size: 14px;")
        self.portfolio_list.setSelectionMode(QListWidget.SingleSelection)
        self.refresh_portfolio_list()
        list_layout.addWidget(self.portfolio_list)
        
        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        
        create_btn = QPushButton("Create New")
        create_btn.setIcon(QIcon(":/icons/add.png"))
        create_btn.clicked.connect(self.show_create_portfolio_dialog)
        
        delete_btn = QPushButton("Delete")
        delete_btn.setIcon(QIcon(":/icons/delete.png"))
        delete_btn.setObjectName("danger-button")
        delete_btn.clicked.connect(self.delete_portfolio)
        
        view_btn = QPushButton("View Details")
        view_btn.setIcon(QIcon(":/icons/view.png"))
        view_btn.setObjectName("primary-button")
        view_btn.clicked.connect(self.view_portfolio_details)
        
          # Add refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setIcon(QIcon(":/icons/refresh.png"))
        refresh_btn.clicked.connect(self.refresh_portfolio_management_page)
        
        btn_row.addWidget(create_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addWidget(view_btn)
        btn_row.addWidget(refresh_btn)  # Add this line
        btn_row.addStretch()
        list_layout.addLayout(btn_row)
        
        layout.addWidget(list_card)
        
        # Performance card
        perf_card = QWidget()
        perf_card.setObjectName("card")
        perf_layout = QVBoxLayout(perf_card)
        
        perf_title = QLabel("PORTFOLIO PERFORMANCE")
        perf_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #64B5F6; margin-bottom: 10px;")
        perf_layout.addWidget(perf_title)
        
        self.portfolio_perf_chart = FigureCanvas(Figure(figsize=(8, 3)))
        self.portfolio_perf_chart.figure.set_facecolor('#1E1E1E')
        perf_layout.addWidget(self.portfolio_perf_chart)
        
        layout.addWidget(perf_card)
        
        self.stacked_widget.addWidget(page)
        
    def refresh_portfolio_management_page(self):
        self.refresh_portfolio_list()
        self.refresh_portfolio_summary()
        # Update the performance chart if needed
        self.update_portfolio_performance_chart()
        
    def refresh_portfolio_list(self):
        self.portfolio_list.clear()
        for portfolio in sorted(self.portfolios.keys()):
            item = QListWidgetItem(portfolio)
            item.setIcon(QIcon(":/icons/portfolio.png"))
            self.portfolio_list.addItem(item)
            
    def show_create_portfolio_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Create New Portfolio")
        dialog.setMinimumWidth(400)
        dialog.setWindowIcon(QIcon(":/icons/add.png"))
        
        layout = QVBoxLayout(dialog)
        
        # Form group
        form_group = QGroupBox("Portfolio Details")
        form_layout = QVBoxLayout(form_group)
        
        # Name field
        name_layout = QHBoxLayout()
        name_label = QLabel("Portfolio Name:")
        name_label.setStyleSheet("min-width: 120px;")
        self.portfolio_name_input = QLineEdit()
        self.portfolio_name_input.setPlaceholderText("Enter portfolio name")
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.portfolio_name_input)
        form_layout.addLayout(name_layout)
        
        # Description field
        desc_layout = QHBoxLayout()
        desc_label = QLabel("Description:")
        desc_label.setStyleSheet("min-width: 120px;")
        self.portfolio_desc_input = QLineEdit()
        self.portfolio_desc_input.setPlaceholderText("Optional description")
        desc_layout.addWidget(desc_label)
        desc_layout.addWidget(self.portfolio_desc_input)
        form_layout.addLayout(desc_layout)
        
        layout.addWidget(form_group)
        
        # Button row
        btn_layout = QHBoxLayout()
        create_btn = QPushButton("Create")
        create_btn.setObjectName("primary-button")
        create_btn.clicked.connect(lambda: self.create_portfolio(dialog))
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(create_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()

    def update_portfolio_performance_chart(self):
        """Update the performance chart in the portfolio management page"""
        portfolio = self.portfolio_list.currentItem().text() if self.portfolio_list.currentItem() else None
        if not portfolio or portfolio not in self.portfolios:
            return
            
        df = self.portfolios[portfolio]
        fig = self.portfolio_perf_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        ax.set_facecolor('#1E1E1E')
        
        # Sample chart - customize with your actual performance data
        if not df.empty:
            # Calculate performance metrics
            invested = df['Investment Value'].sum() if 'Investment Value' in df.columns else (df['Quantity'] * df['Purchase Price']).sum()
            current = df['Current Value'].sum() if 'Current Value' in df.columns else (df['Quantity'] * df['Purchase Price']).sum()
            
            # Create a simple bar chart
            metrics = ['Invested', 'Current']
            values = [invested, current]
            
            bars = ax.bar(metrics, values, color=['#1E88E5', '#4CAF50'])
            ax.set_title(f"{portfolio} Performance", color='white', pad=10)
            ax.set_ylabel("Value (₹)", color='white')
            ax.tick_params(axis='x', colors='white')
            ax.tick_params(axis='y', colors='white')
            
            # Add value labels
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                        f'₹{height:,.0f}',
                        ha='center', va='bottom', color='white')
        
        self.portfolio_perf_chart.draw()
    
    def create_portfolio(self, dialog):
        """Create a new portfolio with proper initialization and UI updates"""
        name = self.portfolio_name_input.text().strip()
        desc = self.portfolio_desc_input.text().strip()
        
        # Validation checks
        if not name:
            QMessageBox.warning(self, "Error", "Portfolio name cannot be empty!")
            return
            
        if name in self.portfolios:
            QMessageBox.warning(self, "Error", "A portfolio with this name already exists!")
            return
        
        try:
            # Create new portfolio DataFrame with all required columns
            self.portfolios[name] = pd.DataFrame(columns=[
                'Stock Name', 
                'Ticker Symbol', 
                'Quantity', 
                'Purchase Price',
                'Purchase Date', 
                'Sector', 
                'Investment Value',
                'Current Value',
                'Profit/Loss',
                'P/L %',
                'Daily P/L',
                'Notes'
            ])
            
            # Store description as an attribute
            if desc:
                self.portfolios[name].attrs['description'] = desc
            
            # Log the creation
            self.log_audit("CREATED_PORTFOLIO", name, "", f"Description: {desc}")
            
            # Update all UI components that show portfolios
            self.refresh_portfolio_ui_components()
            
            # Select the new portfolio in all relevant combo boxes
            self.select_new_portfolio(name)
            
            # Close the dialog
            dialog.accept()
            
            # Show success message
            self.show_success_message(f"Portfolio '{name}' created successfully!")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create portfolio: {str(e)}")
            print(f"Error creating portfolio: {traceback.format_exc()}")

    def refresh_portfolio_ui_components(self):
        """Refresh all UI components that display portfolios"""
        # Refresh the portfolio list widget
        if hasattr(self, 'portfolio_list'):
            self.refresh_portfolio_list()
        
        # Refresh combo boxes
        combo_boxes = [
            'portfolio_combo', 
            'portfolio_dashboard_combo',
            'analysis_portfolio_combo',
            'mf_portfolio_combo'
        ]
        
        for combo_name in combo_boxes:
            if hasattr(self, combo_name):
                combo = getattr(self, combo_name)
                current = combo.currentText()
                combo.clear()
                combo.addItems(sorted(self.portfolios.keys()))
                if current in self.portfolios:
                    combo.setCurrentText(current)

    def select_new_portfolio(self, portfolio_name):
        """Select the newly created portfolio in all relevant views"""
        # Select in main stock view
        if hasattr(self, 'portfolio_combo'):
            self.portfolio_combo.setCurrentText(portfolio_name)
        
        # Select in dashboard view
        if hasattr(self, 'portfolio_dashboard_combo'):
            self.portfolio_dashboard_combo.setCurrentText(portfolio_name)
            self.update_portfolio_dashboard()
        
        # Switch to portfolio view if not already there
        if hasattr(self, 'stacked_widget'):
            self.stacked_widget.setCurrentIndex(2)  # Assuming index 2 is portfolio view

    def show_success_message(self, message):
        """Display a styled success message"""
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Success")
        msg.setText(message)
        
        # Apply custom styling
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #1E1E1E;
            }
            QLabel {
                color: #FFFFFF;
            }
            QPushButton {
                min-width: 80px;
                padding: 5px;
            }
        """)
        
        msg.exec_()

    def delete_portfolio(self):
        selected = self.portfolio_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Error", "Please select a portfolio first!")
            return
            
        portfolio = selected.text()
        
        # Create confirmation dialog with custom styling
        confirm_dialog = QMessageBox()
        confirm_dialog.setIcon(QMessageBox.Warning)
        confirm_dialog.setWindowTitle("Confirm Deletion")
        confirm_dialog.setText(f"Are you sure you want to delete the portfolio '{portfolio}'?")
        confirm_dialog.setInformativeText("This action cannot be undone.")
        confirm_dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm_dialog.setDefaultButton(QMessageBox.No)
        
        reply = confirm_dialog.exec_()
        
        if reply == QMessageBox.Yes:
            del self.portfolios[portfolio]
            self.log_audit("DELETED_PORTFOLIO", portfolio)
            self.refresh_portfolio_list()
            
            # Show success message
            QMessageBox.information(self, "Success", f"Portfolio '{portfolio}' deleted successfully!")

    def view_portfolio_details(self):
        selected = self.portfolio_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Error", "Please select a portfolio first!")
            return
            
        portfolio = selected.text()
        
        # Switch to stock operations page and select this portfolio
        if hasattr(self, 'portfolio_combo'):
            self.portfolio_combo.setCurrentText(portfolio)
            self.stacked_widget.setCurrentIndex(2)
            self.refresh_stock_table()
            
        # Update the page title
        self.page_title.setText(f"Stocks - {portfolio}")

    def create_stock_operations_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # Page title
        self.stock_page_title = QLabel("Stock Portfolio")
        self.stock_page_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        layout.addWidget(self.stock_page_title)
        
        # Portfolio selection row
        portfolio_row = QHBoxLayout()
        portfolio_row.setSpacing(10)
        
        portfolio_label = QLabel("Portfolio:")
        self.portfolio_combo = QComboBox()
        self.portfolio_combo.addItems(sorted(self.portfolios.keys()))
        self.portfolio_combo.currentTextChanged.connect(lambda: self.on_portfolio_changed(self.portfolio_combo.currentText()))
                
        portfolio_row.addWidget(portfolio_label)
        portfolio_row.addWidget(self.portfolio_combo)
        portfolio_row.addStretch()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setIcon(QIcon(":/icons/refresh.png"))
        refresh_btn.clicked.connect(self.refresh_stock_table)
        portfolio_row.addWidget(refresh_btn)
        
        layout.addLayout(portfolio_row)
        
        # Stock table card
        table_card = QWidget()
        table_card.setObjectName("card")
        table_layout = QVBoxLayout(table_card)
        
        table_title = QLabel("STOCK HOLDINGS")
        table_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #64B5F6; margin-bottom: 10px;")
        table_layout.addWidget(table_title)
        
        # Add progress bar for data loading
        self.stock_progress = QProgressBar()
        self.stock_progress.setRange(0, 100)
        self.stock_progress.setVisible(False)
        table_layout.addWidget(self.stock_progress)
        
        self.stock_table = QTableWidget()
        self.stock_table.setColumnCount(10)
        self.stock_table.setHorizontalHeaderLabels([
            "Stocks", "Stock", "Ticker", "Qty", "Avg Price", 
            "Curr Price", "Invested", "Value", "P/L", "Daily P/L"
        ])

        self.stock_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.stock_table.setSelectionMode(QTableWidget.SingleSelection)
        self.stock_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stock_table.verticalHeader().setVisible(False)
        
        table_layout.addWidget(self.stock_table)
        layout.addWidget(table_card, 1)
        
        # Action buttons
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.add_stock_btn = QPushButton("Add Stock")  # Changed to instance variable
        self.add_stock_btn.setIcon(QIcon(":/icons/stock_add.png"))
        self.add_stock_btn.setObjectName("primary-button")
        self.add_stock_btn.clicked.connect(self.show_add_stock_dialog)
        
        
        self.modify_btn = QPushButton("Modify")  # Changed to instance variable
        self.modify_btn.setIcon(QIcon(":/icons/edit.png"))
        self.modify_btn.clicked.connect(self.show_modify_stock_dialog)
    
        
        manage_btn = QPushButton("Manage Shares")
        manage_btn.setIcon(QIcon(":/icons/shares.png"))
        manage_btn.clicked.connect(self.show_manage_shares_dialog)
        
        export_btn = QPushButton("Export")
        export_btn.setIcon(QIcon(":/icons/export.png"))
        export_btn.clicked.connect(self.export_stock_data)
        
        action_row.addWidget(self.add_stock_btn)
        action_row.addWidget(self.modify_btn)
        action_row.addWidget(manage_btn)
        action_row.addWidget(export_btn)
        action_row.addStretch()
        
        layout.addLayout(action_row)
        
        self.stacked_widget.addWidget(page)
        
    def on_portfolio_changed(self, portfolio_name):
        """Handle portfolio selection changes"""
        self.stock_page_title.setText(f"Stocks - {portfolio_name}")
        
        # Force refresh of all relevant views
        self.refresh_stock_table()
        self.update_portfolio_dashboard()
        self.update_combined_dashboard()
        
        # Enable buttons only if a portfolio is selected
        has_portfolio = bool(portfolio_name)
        self.add_stock_btn.setEnabled(has_portfolio)
        self.modify_btn.setEnabled(has_portfolio)
        
    def refresh_stock_table(self):
        portfolio = self.portfolio_combo.currentText()
        if not portfolio or portfolio not in self.portfolios:
            self.stock_table.setRowCount(0)
            return
            
        df = self.portfolios[portfolio]
        self.stock_table.setRowCount(len(df))
        
        if len(df) == 0:
            return
            
        # Show loading progress
        self.stock_progress.setVisible(True)
        self.stock_progress.setValue(0)
        
        # Ensure we have ticker symbols
        if 'Ticker Symbol' not in df.columns:
            QMessageBox.warning(self, "Error", "No ticker symbols found in portfolio!")
            self.stock_progress.setVisible(False)
            return
        
        # Get current prices
        tickers = []
        for ticker in df['Ticker Symbol'].tolist():
            if ticker and '.' not in ticker:  # Assume Indian stock if no exchange specified
                tickers.append(f"{ticker}.NS")
            else:
                tickers.append(ticker)
        
        worker = Worker(tickers)
        worker.data_fetched.connect(
            lambda prices: self.update_stock_table_with_prices(portfolio, prices)
        )
        worker.finished_signal.connect(lambda: self.worker_finished(worker))
        worker.progress_updated.connect(self.stock_progress.setValue)
        self.workers.append(worker)
        worker.start()
        
    def update_stock_table_with_prices(self, portfolio, prices):
        """Update the stock table with current prices and calculated values"""
        try:
            # Hide progress bar when done
            self.stock_progress.setVisible(False)
            
            # Get portfolio data
            df = self.portfolios[portfolio].copy()
            
            # Map current prices to the dataframe
            df['Current Price'] = df['Ticker Symbol'].map(prices)
            
            # Check if we got any prices
            if df['Current Price'].isnull().all():
                QMessageBox.warning(self, "Error", "Could not fetch current prices for any stocks!")
                return
                
            # Calculate derived values
            df['Investment Value'] = df['Quantity'] * df['Purchase Price']
            df['Current Value'] = df['Quantity'] * df['Current Price']
            df['Profit/Loss'] = df['Current Value'] - df['Investment Value']
            df['P/L %'] = (df['Profit/Loss'] / df['Investment Value']) * 100
            
            # Update the table
            self.stock_table.setRowCount(len(df))
            self.stock_table.setColumnCount(10)  # Ensure we have enough columns
            
            for row in range(len(df)):
                stock = df.iloc[row]
                
                # Convert all numeric values to strings before creating items
                self.stock_table.setItem(row, 0, QTableWidgetItem(str(stock['Stock Name'])))
                self.stock_table.setItem(row, 1, QTableWidgetItem(str(stock['Stock Name'])))  # Duplicate for your layout
                self.stock_table.setItem(row, 2, QTableWidgetItem(str(stock['Ticker Symbol'])))
                self.stock_table.setItem(row, 3, QTableWidgetItem(f"{stock['Quantity']:.2f}"))
                self.stock_table.setItem(row, 4, QTableWidgetItem(f"{stock['Purchase Price']:.2f}"))
                
                if pd.notna(stock['Current Price']):
                    # Current Price
                    self.stock_table.setItem(row, 5, QTableWidgetItem(f"{stock['Current Price']:.2f}"))
                    
                    # Investment Value
                    self.stock_table.setItem(row, 6, QTableWidgetItem(f"₹{stock['Investment Value']:,.2f}"))
                    
                    # Current Value
                    self.stock_table.setItem(row, 7, QTableWidgetItem(f"₹{stock['Current Value']:,.2f}"))
                    
                    # Profit/Loss
                    pl = stock['Profit/Loss']
                    pl_item = QTableWidgetItem(f"₹{pl:+,.2f} ({stock['P/L %']:+.2f}%)")
                    pl_item.setForeground(QColor('#4CAF50') if pl >= 0 else QColor('#F44336'))
                    self.stock_table.setItem(row, 8, pl_item)
                    
                    # Daily P/L (placeholder - will be updated async)
                    self.stock_table.setItem(row, 9, QTableWidgetItem("Loading..."))
                    
                    # Fetch daily change in background
                    self.get_daily_change(stock['Ticker Symbol'], row)
                else:
                    # Handle case where current price couldn't be fetched
                    for col in range(5, 10):
                        self.stock_table.setItem(row, col, QTableWidgetItem("N/A"))
            
            # Resize columns to fit content
            self.stock_table.resizeColumnsToContents()
            
        except KeyError as ke:
            QMessageBox.warning(self, "Data Error", f"Missing expected column: {str(ke)}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to update stock table: {str(e)}")
        finally:
            self.stock_progress.setVisible(False)
                        
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
                    self.stock_table.setItem(row, 8, item)
            except Exception as e:
                print(f"Error fetching daily change for {ticker}: {str(e)}")
                self.stock_table.setItem(row, 8, QTableWidgetItem("N/A"))
                
        thread = threading.Thread(target=fetch_daily_change)
        thread.daemon = True
        thread.start()
        
    def show_add_stock_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Stock")
        dialog.setMinimumWidth(500)
        dialog.setWindowIcon(QIcon(":/icons/stock_add.png"))
        
        layout = QVBoxLayout(dialog)
        
        # Form group
        form_group = QGroupBox("Stock Details")
        form_layout = QVBoxLayout(form_group)
        
        # Stock name
        name_layout = QHBoxLayout()
        name_label = QLabel("Stock Name:")
        name_label.setStyleSheet("min-width: 120px;")
        self.stock_name_input = QLineEdit()
        self.stock_name_input.setPlaceholderText("e.g., Reliance Industries")
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.stock_name_input)
        form_layout.addLayout(name_layout)
        
        # Ticker symbol
        ticker_layout = QHBoxLayout()
        ticker_label = QLabel("Ticker Symbol:")
        ticker_label.setStyleSheet("min-width: 120px;")
        self.ticker_input = QLineEdit()
        self.ticker_input.setPlaceholderText("e.g., RELIANCE.NS")
        ticker_layout.addWidget(ticker_label)
        ticker_layout.addWidget(self.ticker_input)
        form_layout.addLayout(ticker_layout)
        
        # Purchase details
        purchase_group = QGroupBox("Purchase Details")
        purchase_layout = QVBoxLayout(purchase_group)
        
        # Quantity
        qty_layout = QHBoxLayout()
        qty_label = QLabel("Quantity:")
        qty_label.setStyleSheet("min-width: 120px;")
        self.qty_input = QDoubleSpinBox()
        self.qty_input.setMinimum(0.01)
        self.qty_input.setMaximum(999999)
        self.qty_input.setValue(1)
        qty_layout.addWidget(qty_label)
        qty_layout.addWidget(self.qty_input)
        purchase_layout.addLayout(qty_layout)
        
        # Price
        price_layout = QHBoxLayout()
        price_label = QLabel("Price per Share:")
        price_label.setStyleSheet("min-width: 120px;")
        self.price_input = QDoubleSpinBox()
        self.price_input.setMinimum(0.01)
        self.price_input.setMaximum(999999)
        self.price_input.setValue(100)
        price_layout.addWidget(price_label)
        price_layout.addWidget(self.price_input)
        purchase_layout.addLayout(price_layout)
        
        # Date
        date_layout = QHBoxLayout()
        date_label = QLabel("Purchase Date:")
        date_label.setStyleSheet("min-width: 120px;")
        self.date_input = QDateEdit(QDate.currentDate())
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("dd-MM-yyyy")
        date_layout.addWidget(date_label)
        date_layout.addWidget(self.date_input)
        purchase_layout.addLayout(date_layout)
        
        form_layout.addWidget(purchase_group)
        
        # Additional info
        info_group = QGroupBox("Additional Information")
        info_layout = QVBoxLayout(info_group)
        
        # Sector
        sector_layout = QHBoxLayout()
        sector_label = QLabel("Sector:")
        sector_label.setStyleSheet("min-width: 120px;")
        self.sector_input = QComboBox()
        self.sector_input.setEditable(True)
        self.sector_input.addItems([
            "Technology", "Financial", "Healthcare", "Energy", 
            "Consumer", "Industrial", "Utilities", "Communication"
        ])
        sector_layout.addWidget(sector_label)
        sector_layout.addWidget(self.sector_input)
        info_layout.addLayout(sector_layout)
        
        # Notes
        notes_layout = QHBoxLayout()
        notes_label = QLabel("Notes:")
        notes_label.setStyleSheet("min-width: 120px;")
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Optional notes")
        notes_layout.addWidget(notes_label)
        notes_layout.addWidget(self.notes_input)
        info_layout.addLayout(notes_layout)
        
        form_layout.addWidget(info_group)
        
        layout.addWidget(form_group)
        
        # Button row
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Stock")
        add_btn.setObjectName("primary-button")
        add_btn.clicked.connect(lambda: self.add_stock(dialog))
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()
        
    def add_stock(self, dialog):
        """Add a new stock to the selected portfolio with robust error handling"""
        try:
            # Get current portfolio
            portfolio = self.portfolio_combo.currentText()
            if not portfolio:
                QMessageBox.warning(self, "Error", "No portfolio selected!")
                return False

            # Validate inputs
            stock_name = self.stock_name_input.text().strip()
            ticker = self.ticker_input.text().strip().upper()
            quantity = self.qty_input.value()
            price = self.price_input.value()
            
            if not stock_name:
                QMessageBox.warning(self, "Error", "Stock name cannot be empty!")
                return False
            if not ticker:
                QMessageBox.warning(self, "Error", "Ticker symbol cannot be empty!")
                return False
            if quantity <= 0:
                QMessageBox.warning(self, "Error", "Quantity must be greater than 0!")
                return False
            if price <= 0:
                QMessageBox.warning(self, "Error", "Price must be greater than 0!")
                return False

            # Prepare stock data with all required columns
            stock_data = {
                'Stock Name': stock_name,
                'Ticker Symbol': ticker + ('' if '.' in ticker else '.NS'),  # Ensure proper suffix
                'Quantity': float(quantity),
                'Purchase Price': float(price),
                'Purchase Date': self.date_input.date().toString("dd-MM-yyyy"),
                'Sector': self.sector_input.currentText(),
                'Investment Value': float(quantity * price),
                'Current Value': float(quantity * price),  # Initialize same as purchase
                'Current Price': float(price),  # Initialize same as purchase
                'Profit/Loss': 0.0,  # Initialize
                'P/L %': 0.0,  # Initialize
                'Daily P/L': 0.0,  # Initialize
                'Notes': self.notes_input.text().strip()
            }

            # Ensure portfolio exists with proper structure
            if portfolio not in self.portfolios:
                self.portfolios[portfolio] = pd.DataFrame(columns=stock_data.keys())
            else:
                # Ensure existing DataFrame has all required columns
                for col in stock_data.keys():
                    if col not in self.portfolios[portfolio].columns:
                        self.portfolios[portfolio][col] = None

            # Check if stock already exists
            existing_index = None
            if 'Ticker Symbol' in self.portfolios[portfolio].columns:
                existing = self.portfolios[portfolio][
                    self.portfolios[portfolio]['Ticker Symbol'] == stock_data['Ticker Symbol']
                ]
                if not existing.empty:
                    existing_index = existing.index[0]

            if existing_index is not None:
                # Stock exists - ask if user wants to add to existing position
                reply = QMessageBox.question(
                    self, "Stock Exists",
                    f"This stock already exists in {portfolio}. Add to existing position?",
                    QMessageBox.Yes | QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    # Calculate new average price and total quantity
                    old_qty = self.portfolios[portfolio].at[existing_index, 'Quantity']
                    old_price = self.portfolios[portfolio].at[existing_index, 'Purchase Price']
                    old_investment = old_qty * old_price
                    
                    new_qty = old_qty + quantity
                    new_investment = old_investment + (quantity * price)
                    new_avg_price = new_investment / new_qty
                    
                    # Update existing position
                    self.portfolios[portfolio].at[existing_index, 'Quantity'] = new_qty
                    self.portfolios[portfolio].at[existing_index, 'Purchase Price'] = new_avg_price
                    self.portfolios[portfolio].at[existing_index, 'Investment Value'] = new_investment
                    self.portfolios[portfolio].at[existing_index, 'Current Value'] = new_qty * price
                    
                    self.log_audit(
                        "ADDED_SHARES", portfolio, stock_name,
                        f"Added {quantity} @ {price:.2f}, New Qty: {new_qty}, New Avg: {new_avg_price:.2f}"
                    )
                else:
                    # Add as new position
                    self.portfolios[portfolio] = pd.concat([
                        self.portfolios[portfolio],
                        pd.DataFrame([stock_data])
                    ], ignore_index=True)
                    
                    self.log_audit(
                        "ADDED_STOCK", portfolio, stock_name,
                        f"New position: {quantity} @ {price:.2f}"
                    )
            else:
                # Add new stock
                self.portfolios[portfolio] = pd.concat([
                    self.portfolios[portfolio],
                    pd.DataFrame([stock_data])
                ], ignore_index=True)
                
                self.log_audit(
                    "ADDED_STOCK", portfolio, stock_name,
                    f"Initial purchase: {quantity} @ {price:.2f}"
                )

            # Refresh UI and clean up
            self.refresh_stock_table()
            dialog.accept()
            QMessageBox.information(self, "Success", "Stock added successfully!")
            self.save_data()  # Persist changes
            return True

        except ValueError as ve:
            QMessageBox.warning(self, "Input Error", f"Invalid numeric value: {str(ve)}")
            return False
        except KeyError as ke:
            QMessageBox.warning(self, "Data Error", f"Missing required field: {str(ke)}")
            return False
        except Exception as e:
            QMessageBox.critical(
                self, "Error", 
                f"Failed to add stock:\n{str(e)}\n\n{traceback.format_exc()}"
            )
            return False
        
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
        dialog.setWindowIcon(QIcon(":/icons/edit.png"))
        
        layout = QVBoxLayout(dialog)
        
        # Form group
        form_group = QGroupBox("Stock Details")
        form_layout = QVBoxLayout(form_group)
        
        # Stock name
        name_layout = QHBoxLayout()
        name_label = QLabel("Stock Name:")
        name_label.setStyleSheet("min-width: 120px;")
        self.mod_stock_name_input = QLineEdit(stock['Stock Name'])
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.mod_stock_name_input)
        form_layout.addLayout(name_layout)
        
        # Ticker symbol
        ticker_layout = QHBoxLayout()
        ticker_label = QLabel("Ticker Symbol:")
        ticker_label.setStyleSheet("min-width: 120px;")
        self.mod_ticker_input = QLineEdit(stock['Ticker Symbol'])
        ticker_layout.addWidget(ticker_label)
        ticker_layout.addWidget(self.mod_ticker_input)
        form_layout.addLayout(ticker_layout)
        
        # Purchase details
        purchase_group = QGroupBox("Purchase Details")
        purchase_layout = QVBoxLayout(purchase_group)
        
        # Quantity
        qty_layout = QHBoxLayout()
        qty_label = QLabel("Quantity:")
        qty_label.setStyleSheet("min-width: 120px;")
        self.mod_qty_input = QDoubleSpinBox()
        self.mod_qty_input.setMinimum(0.01)
        self.mod_qty_input.setMaximum(999999)
        self.mod_qty_input.setValue(stock['Quantity'])
        qty_layout.addWidget(qty_label)
        qty_layout.addWidget(self.mod_qty_input)
        purchase_layout.addLayout(qty_layout)
        
        # Price
        price_layout = QHBoxLayout()
        price_label = QLabel("Price per Share:")
        price_label.setStyleSheet("min-width: 120px;")
        self.mod_price_input = QDoubleSpinBox()
        self.mod_price_input.setMinimum(0.01)
        self.mod_price_input.setMaximum(999999)
        self.mod_price_input.setValue(stock['Purchase Price'])
        price_layout.addWidget(price_label)
        price_layout.addWidget(self.mod_price_input)
        purchase_layout.addLayout(price_layout)
        
        # Date
        date_layout = QHBoxLayout()
        date_label = QLabel("Purchase Date:")
        date_label.setStyleSheet("min-width: 120px;")
        self.mod_date_input = QDateEdit(QDate.fromString(stock['Purchase Date'], "dd-MM-yyyy"))
        self.mod_date_input.setCalendarPopup(True)
        self.mod_date_input.setDisplayFormat("dd-MM-yyyy")
        date_layout.addWidget(date_label)
        date_layout.addWidget(self.mod_date_input)
        purchase_layout.addLayout(date_layout)
        
        form_layout.addWidget(purchase_group)
        
        # Additional info
        info_group = QGroupBox("Additional Information")
        info_layout = QVBoxLayout(info_group)
        
        # Sector
        sector_layout = QHBoxLayout()
        sector_label = QLabel("Sector:")
        sector_label.setStyleSheet("min-width: 120px;")
        self.mod_sector_input = QComboBox()
        self.mod_sector_input.setEditable(True)
        self.mod_sector_input.addItems([
            "Technology", "Financial", "Healthcare", "Energy", 
            "Consumer", "Industrial", "Utilities", "Communication"
        ])
        self.mod_sector_input.setCurrentText(stock.get('Sector', ''))
        sector_layout.addWidget(sector_label)
        sector_layout.addWidget(self.mod_sector_input)
        info_layout.addLayout(sector_layout)
        
        # Notes
        notes_layout = QHBoxLayout()
        notes_label = QLabel("Notes:")
        notes_label.setStyleSheet("min-width: 120px;")
        self.mod_notes_input = QLineEdit(stock.get('Notes', ''))
        notes_layout.addWidget(notes_label)
        notes_layout.addWidget(self.mod_notes_input)
        info_layout.addLayout(notes_layout)
        
        form_layout.addWidget(info_group)
        
        layout.addWidget(form_group)
        
        # Button row
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save Changes")
        save_btn.setObjectName("primary-button")
        save_btn.clicked.connect(lambda: self.modify_stock(dialog, selected))
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()
        
    def modify_stock(self, dialog, row):
        portfolio = self.portfolio_combo.currentText()
        stock_data = {
            'Stock Name': self.mod_stock_name_input.text().strip(),
            'Ticker Symbol': self.mod_ticker_input.text().strip().upper(),
            'Quantity': self.mod_qty_input.value(),
            'Purchase Price': self.mod_price_input.value(),
            'Purchase Date': self.mod_date_input.date().toString("dd-MM-yyyy"),
            'Sector': self.mod_sector_input.currentText(),
            'Investment Value': self.mod_qty_input.value() * self.mod_price_input.value(),
            'Notes': self.mod_notes_input.text().strip()
        }
        
        if not stock_data['Stock Name'] or not stock_data['Ticker Symbol']:
            QMessageBox.warning(self, "Error", "Stock name and ticker are required!")
            return
            
        self.portfolios[portfolio].iloc[row] = stock_data
        self.log_audit("MODIFIED_STOCK", portfolio, stock_data['Stock Name'])
        self.refresh_stock_table()
        dialog.accept()
        
        # Show success notification
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
        dialog.setWindowIcon(QIcon(":/icons/shares.png"))
        
        layout = QVBoxLayout(dialog)
        
        # Current position
        current_group = QGroupBox("Current Position")
        current_layout = QVBoxLayout(current_group)
        
        current_qty = QLabel(f"Current Quantity: {stock['Quantity']}")
        current_qty.setStyleSheet("font-size: 14px;")
        current_layout.addWidget(current_qty)
        
        current_value = QLabel(f"Current Value: ₹{stock['Quantity'] * stock['Purchase Price']:,.2f}")
        current_value.setStyleSheet("font-size: 14px;")
        current_layout.addWidget(current_value)
        
        layout.addWidget(current_group)
        
        # Action selection
        action_group = QGroupBox("Action")
        action_layout = QVBoxLayout(action_group)
        
        self.shares_action_combo = QComboBox()
        self.shares_action_combo.addItems(["Add Shares", "Remove Shares"])
        action_layout.addWidget(self.shares_action_combo)
        
        layout.addWidget(action_group)
        
        # Transaction details
        trans_group = QGroupBox("Transaction Details")
        trans_layout = QVBoxLayout(trans_group)
        
        # Quantity
        qty_layout = QHBoxLayout()
        qty_label = QLabel("Quantity:")
        qty_label.setStyleSheet("min-width: 100px;")
        self.shares_qty_input = QDoubleSpinBox()
        self.shares_qty_input.setMinimum(0.01)
        self.shares_qty_input.setMaximum(999999)
        self.shares_qty_input.setValue(1)
        qty_layout.addWidget(qty_label)
        qty_layout.addWidget(self.shares_qty_input)
        trans_layout.addLayout(qty_layout)
        
        # Price (only for adding shares)
        self.price_layout = QHBoxLayout()
        price_label = QLabel("Price per Share:")
        price_label.setStyleSheet("min-width: 100px;")
        self.shares_price_input = QDoubleSpinBox()
        self.shares_price_input.setMinimum(0.01)
        self.shares_price_input.setMaximum(999999)
        self.shares_price_input.setValue(stock['Purchase Price'])
        self.price_layout.addWidget(price_label)
        self.price_layout.addWidget(self.shares_price_input)
        trans_layout.addLayout(self.price_layout)
        
        # Date
        date_layout = QHBoxLayout()
        date_label = QLabel("Transaction Date:")
        date_label.setStyleSheet("min-width: 100px;")
        self.shares_date_input = QDateEdit(QDate.currentDate())
        self.shares_date_input.setCalendarPopup(True)
        self.shares_date_input.setDisplayFormat("dd-MM-yyyy")
        date_layout.addWidget(date_label)
        date_layout.addWidget(self.shares_date_input)
        trans_layout.addLayout(date_layout)
        
        layout.addWidget(trans_group)
        
        # Toggle price visibility based on action
        def toggle_price_fields(index):
            self.price_layout.parentWidget().setVisible(index == 0)
            
        self.shares_action_combo.currentIndexChanged.connect(toggle_price_fields)
        toggle_price_fields(0)  # Initialize
        
        # Button row
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Confirm")
        save_btn.setObjectName("primary-button")
        save_btn.clicked.connect(
            lambda: self.manage_shares(
                dialog, selected, self.shares_action_combo.currentText(), 
                self.shares_qty_input.value(), self.shares_price_input.value()
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

    def export_stock_data(self):
        portfolio = self.portfolio_combo.currentText()
        if portfolio not in self.portfolios or self.portfolios[portfolio].empty:
            QMessageBox.warning(self, "Error", "No data to export!")
            return
            
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Portfolio Data",
            f"{portfolio}_holdings.csv",
            "CSV Files (*.csv)",
            options=options
        )
        
        if file_path:
            try:
                self.portfolios[portfolio].to_csv(file_path, index=False)
                QMessageBox.information(self, "Success", "Data exported successfully!")
                self.log_audit("EXPORTED_DATA", portfolio, "", f"Exported to {file_path}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to export data: {str(e)}")

    def create_analysis_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # Page title
        title = QLabel("Portfolio Analysis")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        layout.addWidget(title)
        
        # Portfolio selection
        portfolio_row = QHBoxLayout()
        portfolio_row.setSpacing(10)
        
        portfolio_label = QLabel("Portfolio:")
        self.analysis_portfolio_combo = QComboBox()
        self.analysis_portfolio_combo.addItems(sorted(self.portfolios.keys()))
        self.analysis_portfolio_combo.currentTextChanged.connect(self.update_analysis)
        
        portfolio_row.addWidget(portfolio_label)
        portfolio_row.addWidget(self.analysis_portfolio_combo)
        portfolio_row.addStretch()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setIcon(QIcon(":/icons/refresh.png"))
        refresh_btn.clicked.connect(self.update_analysis)
        portfolio_row.addWidget(refresh_btn)
        
        layout.addLayout(portfolio_row)
        
        # Tab widget for different analysis views
        self.analysis_tabs = QTabWidget()
        layout.addWidget(self.analysis_tabs)
        
        # Sector allocation tab
        sector_tab = QWidget()
        sector_layout = QVBoxLayout(sector_tab)
        
        self.sector_chart = FigureCanvas(Figure(figsize=(8, 4)))
        self.sector_chart.figure.set_facecolor('#1E1E1E')
        sector_layout.addWidget(self.sector_chart)
        
        self.analysis_tabs.addTab(sector_tab, "Sector Allocation")
        
        # Historical performance tab
        perf_tab = QWidget()
        perf_layout = QVBoxLayout(perf_tab)
        
        self.perf_chart = FigureCanvas(Figure(figsize=(8, 4)))
        self.perf_chart.figure.set_facecolor('#1E1E1E')
        perf_layout.addWidget(self.perf_chart)
        
        self.analysis_tabs.addTab(perf_tab, "Performance")
        
        # Risk analysis tab
        risk_tab = QWidget()
        risk_layout = QVBoxLayout(risk_tab)
        
        self.risk_chart = FigureCanvas(Figure(figsize=(8, 4)))
        self.risk_chart.figure.set_facecolor('#1E1E1E')
        risk_layout.addWidget(self.risk_chart)
        
        self.analysis_tabs.addTab(risk_tab, "Risk Analysis")
        
        # Update initial analysis
        self.update_analysis()
        
        self.stacked_widget.addWidget(page)

    def update_analysis(self):
        portfolio = self.analysis_portfolio_combo.currentText()
        if not portfolio or portfolio not in self.portfolios:
            return
            
        df = self.portfolios[portfolio]
        if df.empty:
            return
            
        # Update sector allocation chart
        self.update_sector_allocation(portfolio)
        
        # Update performance chart
        self.update_performance_chart(portfolio)
        
        # Update risk analysis
        self.update_risk_analysis(portfolio)

    def update_sector_allocation(self, portfolio):
        fig = self.sector_chart.figure
        fig.clear()
        
        df = self.portfolios[portfolio]
        if df.empty or 'Sector' not in df.columns or 'Current Value' not in df.columns:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "No sector data available", 
                ha='center', va='center', color='white')
            self.sector_chart.draw()
            return
            
        # Filter out rows with missing sector or zero value
        df = df[df['Sector'].notna() & (df['Current Value'] > 0)]
        
        if df.empty:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "No valid sector data", 
                ha='center', va='center', color='white')
            self.sector_chart.draw()
            return
        
        sector_values = df.groupby('Sector')['Current Value'].sum()
        
        ax = fig.add_subplot(111)
        ax.set_facecolor('#1E1E1E')
        
        colors = plt.cm.Paired(range(len(sector_values)))
        wedges, texts, autotexts = ax.pie(
            sector_values,
            labels=sector_values.index,
            autopct=lambda p: f'{p:.1f}%\n({p * sector_values.sum()/100:,.0f})',
            startangle=90,
            colors=colors,
            textprops={'color': 'white', 'fontsize': 8},
            wedgeprops={'linewidth': 0.5, 'edgecolor': '#121212'}
        )
        
        ax.set_title("Sector Allocation", color='white', pad=10)
        
        for text in texts:
            text.set_color('white')
            text.set_fontsize(9)
            
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(8)
        
        self.sector_chart.draw()

    def update_performance_chart(self, portfolio):
        fig = self.perf_chart.figure
        fig.clear()
        
        df = self.portfolios[portfolio]
        if df.empty:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "No performance data available", 
                   ha='center', va='center', color='white')
            self.perf_chart.draw()
            return
            
        # Calculate performance metrics
        invested = df['Investment Value'].sum()
        current = df['Current Value'].sum()
        pl = current - invested
        pct_pl = (pl / invested * 100) if invested > 0 else 0
        
        # Create bar chart
        ax = fig.add_subplot(111)
        ax.set_facecolor('#1E1E1E')
        
        metrics = ['Invested', 'Current', 'P/L']
        values = [invested, current, pl]
        colors = ['#1E88E5', '#43A047', '#4CAF50' if pl >= 0 else '#F44336']
        
        bars = ax.bar(metrics, values, color=colors)
        ax.set_title("Portfolio Performance", color='white', pad=10)
        ax.set_ylabel("Value (₹)", color='white')
        ax.tick_params(axis='x', colors='white')
        ax.tick_params(axis='y', colors='white')
        
        # Add value labels
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                    f'₹{height:,.0f}',
                    ha='center', va='bottom', color='white')
        
        # Add percentage label for P/L
        ax.text(2, pl, f'{pct_pl:+.1f}%',
                ha='center', va='bottom', color='white', fontsize=12)
        
        self.perf_chart.draw()

    def update_risk_analysis(self, portfolio):
        fig = self.risk_chart.figure
        fig.clear()
        
        df = self.portfolios[portfolio]
        if df.empty:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "No risk data available", 
                   ha='center', va='center', color='white')
            self.risk_chart.draw()
            return
            
        # Calculate risk metrics (simplified)
        risk_metrics = {
            'Concentration Risk': len(df) / 100,  # Fewer holdings = higher risk
            'Sector Concentration': df['Sector'].nunique() / 10,  # Fewer sectors = higher risk
            'Volatility': 0.2,  # Placeholder for actual volatility calculation
            'Beta': 1.0  # Placeholder for actual beta calculation
        }
        
        ax = fig.add_subplot(111)
        ax.set_facecolor('#1E1E1E')
        
        angles = np.linspace(0, 2*np.pi, len(risk_metrics), endpoint=False)
        values = list(risk_metrics.values())
        values += values[:1]  # Close the radar chart
        angles = np.concatenate((angles, [angles[0]]))
        
        ax.fill(angles, values, color='#1E88E5', alpha=0.25)
        ax.plot(angles, values, color='#1E88E5', marker='o')
        
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(risk_metrics.keys(), color='white')
        ax.set_yticks([0, 0.5, 1])
        ax.set_yticklabels(['Low', 'Medium', 'High'], color='white')
        ax.set_title("Risk Analysis", color='white', pad=20)
        
        self.risk_chart.draw()

    def create_market_data_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # Page title
        title = QLabel("Market Data")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        layout.addWidget(title)
        
        # Market indices card
        indices_card = QWidget()
        indices_card.setObjectName("card")
        indices_layout = QVBoxLayout(indices_card)
        
        indices_title = QLabel("MARKET INDICES")
        indices_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #64B5F6; margin-bottom: 10px;")
        indices_layout.addWidget(indices_title)
        
        self.market_indices_table = QTableWidget()
        self.market_indices_table.setColumnCount(6)
        self.market_indices_table.setHorizontalHeaderLabels([
            "Index", "Price", "Change", "% Change", "Status", "Market Hours"
        ])
        self.market_indices_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.market_indices_table.verticalHeader().setVisible(False)
        indices_layout.addWidget(self.market_indices_table)
        
        layout.addWidget(indices_card)
        
        # Stock lookup card
        lookup_card = QWidget()
        lookup_card.setObjectName("card")
        lookup_layout = QVBoxLayout(lookup_card)
        
        lookup_title = QLabel("STOCK LOOKUP")
        lookup_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #64B5F6; margin-bottom: 10px;")
        lookup_layout.addWidget(lookup_title)
        
        # Search row
        search_row = QHBoxLayout()
        self.stock_search_input = QLineEdit()
        self.stock_search_input.setPlaceholderText("Enter stock symbol (e.g., RELIANCE.NS, AAPL)")
        search_btn = QPushButton("Search")
        search_btn.setObjectName("primary-button")
        search_btn.clicked.connect(self.lookup_stock)
        search_row.addWidget(self.stock_search_input)
        search_row.addWidget(search_btn)
        lookup_layout.addLayout(search_row)
        
        # Results display
        self.stock_results = QTextEdit()
        self.stock_results.setReadOnly(True)
        self.stock_results.setStyleSheet("font-family: 'Courier New', monospace; font-size: 12px;")
        lookup_layout.addWidget(self.stock_results)
        
        layout.addWidget(lookup_card)
        
        # Update market data
        self.update_market_indices()
        
        self.stacked_widget.addWidget(page)

    def update_market_indices(self):
        indices = {
            'NIFTY 50': '^NSEI',
            'SENSEX': '^BSESN',
            'NIFTY BANK': '^NSEBANK',
            'S&P 500': '^GSPC',
            'NASDAQ': '^IXIC',
            'DOW JONES': '^DJI'
        }
        
        def update_table(data):
            self.market_indices_table.setRowCount(len(data))
            
            for row, (name, info) in enumerate(data.items()):
                if info is None:
                    continue
                    
                change = info['Change']
                pct_change = info['% Change']
                color = "#4CAF50" if change >= 0 else "#F44336"
                arrow = "↑" if change >= 0 else "↓"
                
                self.market_indices_table.setItem(row, 0, QTableWidgetItem(name))
                self.market_indices_table.setItem(row, 1, QTableWidgetItem(f"{info['Current']:,.2f}"))
                self.market_indices_table.setItem(row, 2, QTableWidgetItem(f"{change:+,.2f}"))
                self.market_indices_table.setItem(row, 3, QTableWidgetItem(f"{pct_change:+,.2f}%"))
                self.market_indices_table.setItem(row, 4, QTableWidgetItem(info['Status']))
                self.market_indices_table.setItem(row, 5, QTableWidgetItem(info['Market Hours']))
                
                # Set color for change columns
                for col in [2, 3]:
                    item = self.market_indices_table.item(row, col)
                    item.setForeground(QColor(color))
                    item.setText(f"{arrow} {item.text()}")
        
        worker = MarketDataWorker(indices)
        worker.data_fetched.connect(update_table)
        worker.finished_signal.connect(lambda: self.worker_finished(worker))
        self.workers.append(worker)
        worker.start()

    def lookup_stock(self):
        symbol = self.stock_search_input.text().strip()
        if not symbol:
            QMessageBox.warning(self, "Error", "Please enter a stock symbol!")
            return
            
        try:
            stock = yf.Ticker(symbol)
            info = stock.info
            
            if not info:
                self.stock_results.setText(f"No data found for symbol: {symbol}")
                return
                
            # Format the stock information
            result_text = f"=== {info.get('longName', symbol)} ===\n\n"
            result_text += f"Symbol: {symbol}\n"
            result_text += f"Current Price: {info.get('currentPrice', info.get('regularMarketPrice', 'N/A'))}\n"
            result_text += f"Previous Close: {info.get('previousClose', 'N/A')}\n"
            result_text += f"Day Range: {info.get('dayLow', 'N/A')} - {info.get('dayHigh', 'N/A')}\n"
            result_text += f"52 Week Range: {info.get('fiftyTwoWeekLow', 'N/A')} - {info.get('fiftyTwoWeekHigh', 'N/A')}\n"
            result_text += f"Market Cap: {info.get('marketCap', 'N/A')}\n"
            result_text += f"PE Ratio: {info.get('trailingPE', 'N/A')}\n"
            result_text += f"Sector: {info.get('sector', 'N/A')}\n"
            result_text += f"Industry: {info.get('industry', 'N/A')}\n"
            
            self.stock_results.setText(result_text)
            self.log_audit("STOCK_LOOKUP", "", symbol, "Stock information retrieved")
        except Exception as e:
            self.stock_results.setText(f"Error fetching data for {symbol}: {str(e)}")

    def create_reports_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
       
        refresh_btn = QPushButton()
        refresh_btn.setIcon(QIcon(":/icons/refresh.png"))
        refresh_btn.setToolTip("Refresh Reports")
        refresh_btn.clicked.connect(self.generate_report)
       
        
        # Page title
        title = QLabel("Reports")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        layout.addWidget(title)
        
        # Report selection card
        report_card = QWidget()
        report_card.setObjectName("card")
        report_layout = QVBoxLayout(report_card)
        
        report_title = QLabel("GENERATE REPORTS")
        report_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #64B5F6; margin-bottom: 10px;")
        report_layout.addWidget(report_title)
        
        # Report type selection
        report_type_group = QGroupBox("Report Type")
        report_type_layout = QVBoxLayout(report_type_group)
        
        self.report_type_combo = QComboBox()
        self.report_type_combo.addItems([
            "Portfolio Summary",
            "Detailed Holdings",
            "Performance Analysis",
            "Tax Report",
            "Custom Report"
        ])
        report_type_layout.addWidget(self.report_type_combo)
        report_layout.addWidget(report_type_group)
        
        # Portfolio selection
        portfolio_group = QGroupBox("Portfolio")
        portfolio_layout = QVBoxLayout(portfolio_group)
        
        self.report_portfolio_combo = QComboBox()
        self.report_portfolio_combo.addItems(["All Portfolios"] + sorted(self.portfolios.keys()))
        portfolio_layout.addWidget(self.report_portfolio_combo)
        report_layout.addWidget(portfolio_group)
        
        # Date range
        date_group = QGroupBox("Date Range")
        date_layout = QVBoxLayout(date_group)
        
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("From:"))
        self.report_from_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.report_from_date.setCalendarPopup(True)
        date_row.addWidget(self.report_from_date)
        
        date_row.addWidget(QLabel("To:"))
        self.report_to_date = QDateEdit(QDate.currentDate())
        self.report_to_date.setCalendarPopup(True)
        date_row.addWidget(self.report_to_date)
        
        date_layout.addLayout(date_row)
        report_layout.addWidget(date_group)
        
        # Generate button
        generate_btn = QPushButton("Generate Report")
        generate_btn.setObjectName("primary-button")
        generate_btn.clicked.connect(self.generate_report)
        report_layout.addWidget(generate_btn)
        
        layout.addWidget(report_card)
        
        # Report preview area
        preview_card = QWidget()
        preview_card.setObjectName("card")
        preview_layout = QVBoxLayout(preview_card)
        
        preview_title = QLabel("REPORT PREVIEW")
        preview_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #64B5F6; margin-bottom: 10px;")
        preview_layout.addWidget(preview_title)
        
        self.report_preview = QTextEdit()
        self.report_preview.setReadOnly(True)
        preview_layout.addWidget(self.report_preview)
        
        layout.addWidget(preview_card, 1)
        
        self.stacked_widget.addWidget(page)

    def generate_report(self):
        report_type = self.report_type_combo.currentText()
        portfolio = self.report_portfolio_combo.currentText()
        from_date = self.report_from_date.date().toString("yyyy-MM-dd")
        to_date = self.report_to_date.date().toString("yyyy-MM-dd")
        
        # Generate simple preview (actual implementation would create full report)
        preview = f"=== {report_type} Report ===\n"
        preview += f"Date Range: {from_date} to {to_date}\n"
        preview += f"Portfolio: {portfolio}\n\n"
        
        if portfolio == "All Portfolios":
            for name, df in self.portfolios.items():
                if df.empty:
                    continue
                    
                invested = df['Investment Value'].sum()
                current = df['Current Value'].sum()
                pl = current - invested
                pct = (pl / invested * 100) if invested > 0 else 0
                
                preview += f"{name}:\n"
                preview += f"  Invested: ₹{invested:,.2f}\n"
                preview += f"  Current: ₹{current:,.2f}\n"
                preview += f"  P/L: ₹{pl:+,.2f} ({pct:+.2f}%)\n\n"
        else:
            df = self.portfolios.get(portfolio, pd.DataFrame())
            if not df.empty:
                preview += "Holdings:\n"
                for _, row in df.iterrows():
                    preview += f"  {row['Stock Name']} ({row['Ticker Symbol']}): "
                    preview += f"{row['Quantity']} shares @ ₹{row['Purchase Price']:.2f}\n"
                    preview += f"    Current: ₹{row['Current Value']:,.2f}\n"
                    preview += f"    P/L: ₹{row['Profit/Loss']:+,.2f}\n\n"
        
        self.report_preview.setPlainText(preview)
        
        # Offer to save as PDF
        reply = QMessageBox.question(
            self, "Report Generated",
            "Would you like to save this report as a PDF file?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.save_report_as_pdf(report_type, portfolio, from_date, to_date, preview)

    def save_report_as_pdf(self, report_type, portfolio, from_date, to_date, content):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Report As",
            f"{report_type}_{portfolio}_{from_date}_to_{to_date}.pdf",
            "PDF Files (*.pdf)",
            options=options
        )
        
        if file_path:
            try:
                from matplotlib.backends.backend_pdf import PdfPages
                
                with PdfPages(file_path) as pdf:
                    # Title page
                    plt.figure(figsize=(8.27, 11.69))
                    plt.text(0.5, 0.7, f"{report_type} Report", 
                            ha='center', va='center', fontsize=20)
                    plt.text(0.5, 0.6, f"Portfolio: {portfolio}", 
                            ha='center', va='center', fontsize=14)
                    plt.text(0.5, 0.55, f"Date Range: {from_date} to {to_date}", 
                            ha='center', va='center', fontsize=12)
                    plt.text(0.5, 0.5, datetime.now().strftime("%d %B %Y"), 
                            ha='center', va='center', fontsize=12)
                    plt.axis('off')
                    pdf.savefig()
                    plt.close()
                    
                    # Content page
                    fig, ax = plt.subplots(figsize=(8.27, 11.69))
                    ax.text(0.1, 0.9, content, 
                           ha='left', va='top', fontsize=10, family='monospace')
                    ax.axis('off')
                    pdf.savefig()
                    plt.close()
                
                QMessageBox.information(self, "Success", "Report saved successfully!")
                self.log_audit("GENERATED_REPORT", portfolio, "", f"{report_type} from {from_date} to {to_date}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to save report: {str(e)}")

    def create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # Page title
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        layout.addWidget(title)
        
        # Settings tabs
        settings_tabs = QTabWidget()
        layout.addWidget(settings_tabs)
        
        # General settings tab
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        
        # Theme selection
        theme_group = QGroupBox("Appearance")
        theme_layout = QVBoxLayout(theme_group)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark Theme", "Light Theme", "System Theme"])
        theme_layout.addWidget(self.theme_combo)
        
        general_layout.addWidget(theme_group)
        
        # Auto-refresh settings
        refresh_group = QGroupBox("Auto-Refresh")
        refresh_layout = QVBoxLayout(refresh_group)
        
        refresh_row = QHBoxLayout()
        refresh_row.addWidget(QLabel("Interval (minutes):"))
        self.refresh_interval = QSpinBox()
        self.refresh_interval.setRange(1, 60)
        self.refresh_interval.setValue(5)
        refresh_row.addWidget(self.refresh_interval)
        refresh_row.addStretch()
        
        refresh_layout.addLayout(refresh_row)
        general_layout.addWidget(refresh_group)
        
        # Save button
        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("primary-button")
        save_btn.clicked.connect(self.save_settings)
        general_layout.addWidget(save_btn)
        
        settings_tabs.addTab(general_tab, "General")
        
        # Data management tab
        data_tab = QWidget()
        data_layout = QVBoxLayout(data_tab)
        
        # Backup settings
        backup_group = QGroupBox("Data Backup")
        backup_layout = QVBoxLayout(backup_group)
        
        backup_btn = QPushButton("Backup Data")
        backup_btn.setIcon(QIcon(":/icons/backup.png"))
        backup_btn.clicked.connect(self.backup_data)
        backup_layout.addWidget(backup_btn)
        
        restore_btn = QPushButton("Restore Data")
        restore_btn.setIcon(QIcon(":/icons/restore.png"))
        restore_btn.clicked.connect(self.restore_data)
        backup_layout.addWidget(restore_btn)
        
        data_layout.addWidget(backup_group)
        
        # Reset settings
        reset_group = QGroupBox("Reset Data")
        reset_layout = QVBoxLayout(reset_group)
        
        reset_btn = QPushButton("Reset All Data")
        reset_btn.setIcon(QIcon(":/icons/reset.png"))
        reset_btn.setObjectName("danger-button")
        reset_btn.clicked.connect(self.reset_data)
        reset_layout.addWidget(reset_btn)
        
        data_layout.addWidget(reset_group)
        data_layout.addStretch()
        
        settings_tabs.addTab(data_tab, "Data")
        
        self.stacked_widget.addWidget(page)

    def save_settings(self):
        # Save settings to config file
        config = {
            'theme': self.theme_combo.currentText(),
            'refresh_interval': self.refresh_interval.value()
        }
        
        try:
            with open('portfolio_config.json', 'w') as f:
                json.dump(config, f)
            
            # Update refresh timer
            self.refresh_timer.setInterval(config['refresh_interval'] * 60000)
            
            QMessageBox.information(self, "Success", "Settings saved successfully!")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save settings: {str(e)}")

    def backup_data(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Backup Portfolio Data",
            f"portfolio_backup_{datetime.now().strftime('%Y%m%d')}.json",
            "JSON Files (*.json)",
            options=options
        )
        
        if file_path:
            try:
                # Convert DataFrames to dictionaries for JSON serialization
                backup_data = {
                    'portfolios': {name: df.to_dict('records') for name, df in self.portfolios.items()},
                    'metadata': {
                        'version': '1.0',
                        'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                }
                
                with open(file_path, 'w') as f:
                    json.dump(backup_data, f)
                
                QMessageBox.information(self, "Success", "Backup created successfully!")
                self.log_audit("DATA_BACKUP", "", "", f"Backup saved to {file_path}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to create backup: {str(e)}")

    def restore_data(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Restore Portfolio Data",
            "",
            "JSON Files (*.json)",
            options=options
        )
        
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    backup_data = json.load(f)
                
                # Handle both old and new format
                if isinstance(backup_data, dict):
                    # New format (with metadata)
                    if 'portfolios' in backup_data:
                        portfolio_data = backup_data['portfolios']
                    else:
                        # Old format (direct portfolio dict)
                        portfolio_data = backup_data
                    
                    # Convert to DataFrames
                    restored_portfolios = {}
                    for name, records in portfolio_data.items():
                        try:
                            # Handle both list of dicts and direct dict
                            if isinstance(records, list):
                                df = pd.DataFrame(records)
                            elif isinstance(records, dict) and 'stocks' in records:
                                df = pd.DataFrame(records['stocks'])
                            else:
                                df = pd.DataFrame()
                            
                            # Ensure required columns exist
                            required_cols = [
                                'Stock Name', 'Ticker Symbol', 'Quantity', 
                                'Purchase Price', 'Purchase Date', 'Sector',
                                'Investment Value', 'Current Value'
                            ]
                            for col in required_cols:
                                if col not in df.columns:
                                    df[col] = None
                            
                            # Clean ticker symbols
                            if 'Ticker Symbol' in df.columns:
                                df['Ticker Symbol'] = df['Ticker Symbol'].apply(
                                    lambda x: str(x).strip().upper() + ('' if '.' in str(x) else '.NS'))
                            
                            # Calculate investment value if not present
                            if 'Investment Value' not in df.columns or df['Investment Value'].isnull().all():
                                if 'Quantity' in df.columns and 'Purchase Price' in df.columns:
                                    df['Investment Value'] = df['Quantity'] * df['Purchase Price']
                                else:
                                    df['Investment Value'] = 0.0
                            
                            restored_portfolios[name] = df
                        except Exception as e:
                            print(f"Error processing portfolio {name}: {str(e)}")
                            continue
                    
                    # Confirm restoration
                    reply = QMessageBox.question(
                        self, "Confirm Restore",
                        f"This will restore {len(restored_portfolios)} portfolios. Continue?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    
                    if reply == QMessageBox.Yes:
                        self.portfolios = restored_portfolios
                        self.save_data()
                        self.refresh_portfolio_list()
                        self.refresh_stock_table()
                        self.refresh_portfolio_summary()
                        
                        QMessageBox.information(self, "Success", "Data restored successfully!")
                        self.log_audit("DATA_RESTORE", "", "", f"Restored from {file_path}")
                else:
                    QMessageBox.warning(self, "Error", "Invalid data format in backup file")
                    
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to restore data: {str(e)}")
                print(f"Restore error: {traceback.format_exc()}")
    
    def reset_data(self):
        reply = QMessageBox.question(
            self, "Confirm Reset",
            "This will delete ALL your portfolio data. Are you sure?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.portfolios = {}
            self.save_data()
            self.refresh_portfolio_list()
            self.refresh_stock_table()
            self.refresh_portfolio_summary()
            
            QMessageBox.information(self, "Success", "All data has been reset!")
            self.log_audit("DATA_RESET", "", "", "All data cleared")

    def create_mutual_funds_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # Page title
        title = QLabel("Mutual Funds")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        layout.addWidget(title)
        
        # Portfolio selection
        portfolio_row = QHBoxLayout()
        portfolio_row.setSpacing(10)
        
        portfolio_label = QLabel("Portfolio:")
        self.mf_portfolio_combo = QComboBox()
        self.mf_portfolio_combo.addItems(sorted(self.portfolios.keys()))
        self.mf_portfolio_combo.currentTextChanged.connect(self.refresh_mf_table)
        
        portfolio_row.addWidget(portfolio_label)
        portfolio_row.addWidget(self.mf_portfolio_combo)
        portfolio_row.addStretch()
        
        add_btn = QPushButton("Add Fund")
        add_btn.setIcon(QIcon(":/icons/mutual_fund_add.png"))
        add_btn.setObjectName("primary-button")
        add_btn.clicked.connect(self.show_add_mf_dialog)
        portfolio_row.addWidget(add_btn)
        
        layout.addLayout(portfolio_row)
        
        # Mutual funds table
        table_card = QWidget()
        table_card.setObjectName("card")
        table_layout = QVBoxLayout(table_card)
        
        table_title = QLabel("MUTUAL FUND HOLDINGS")
        table_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #64B5F6; margin-bottom: 10px;")
        table_layout.addWidget(table_title)
        
        self.mf_table = QTableWidget()
        self.mf_table.setColumnCount(8)
        self.mf_table.setHorizontalHeaderLabels([
            "Fund Name", "Scheme", "Units", "NAV", "Purchase Value", "Current Value", "P/L", "XIRR"
        ])
        self.mf_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.mf_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table_layout.addWidget(self.mf_table)
        
        layout.addWidget(table_card, 1)
        
        # Action buttons
        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        
        modify_btn = QPushButton("Modify")
        modify_btn.setIcon(QIcon(":/icons/edit.png"))
        modify_btn.clicked.connect(self.show_modify_mf_dialog)
        
        delete_btn = QPushButton("Delete")
        delete_btn.setIcon(QIcon(":/icons/delete.png"))
        delete_btn.setObjectName("danger-button")
        delete_btn.clicked.connect(self.delete_mf)
        
        sip_btn = QPushButton("Add SIP")
        sip_btn.setIcon(QIcon(":/icons/sip.png"))
        sip_btn.clicked.connect(self.show_add_sip_dialog)
        
        action_row.addWidget(modify_btn)
        action_row.addWidget(delete_btn)
        action_row.addWidget(sip_btn)
        action_row.addStretch()
        
        layout.addLayout(action_row)
        
        # Initialize table
        self.refresh_mf_table()
        
        self.stacked_widget.addWidget(page)

    def refresh_mf_table(self):
        portfolio = self.mf_portfolio_combo.currentText()
        if not portfolio or portfolio not in self.portfolios:
            self.mf_table.setRowCount(0)
            return
            
        df = self.portfolios[portfolio]
        if df.empty:
            self.mf_table.setRowCount(0)
            return
            
        # Filter mutual funds (assuming they have a 'Scheme' column)
        mf_df = df[df['Scheme'].notna()] if 'Scheme' in df.columns else pd.DataFrame()
        
        self.mf_table.setRowCount(len(mf_df))
        
        for row in range(len(mf_df)):
            fund = mf_df.iloc[row]
            
            self.mf_table.setItem(row, 0, QTableWidgetItem(fund['Fund Name']))
            self.mf_table.setItem(row, 1, QTableWidgetItem(fund['Scheme']))
            self.mf_table.setItem(row, 2, QTableWidgetItem(f"{fund['Units']:.2f}"))
            self.mf_table.setItem(row, 3, QTableWidgetItem(f"{fund['NAV']:.2f}"))
            self.mf_table.setItem(row, 4, QTableWidgetItem(f"₹{fund['Purchase Value']:,.2f}"))
            
            if 'Current Value' in fund:
                current_value = fund['Current Value']
                pl = current_value - fund['Purchase Value']
                pl_pct = (pl / fund['Purchase Value'] * 100) if fund['Purchase Value'] > 0 else 0
                
                self.mf_table.setItem(row, 5, QTableWidgetItem(f"₹{current_value:,.2f}"))
                
                pl_item = QTableWidgetItem(f"₹{pl:+,.2f} ({pl_pct:+.2f}%)")
                pl_item.setForeground(QColor('#4CAF50') if pl >= 0 else QColor('#F44336'))
                self.mf_table.setItem(row, 6, pl_item)
                
                xirr_item = QTableWidgetItem("Calculating...")
                self.mf_table.setItem(row, 7, xirr_item)
            else:
                for col in range(5, 8):
                    self.mf_table.setItem(row, col, QTableWidgetItem("N/A"))

    def show_add_mf_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Mutual Fund")
        dialog.setMinimumWidth(500)
        dialog.setWindowIcon(QIcon(":/icons/mutual_fund_add.png"))
        
        layout = QVBoxLayout(dialog)
        
        # Form group
        form_group = QGroupBox("Fund Details")
        form_layout = QVBoxLayout(form_group)
        
        # Fund name
        name_layout = QHBoxLayout()
        name_label = QLabel("Fund Name:")
        name_label.setStyleSheet("min-width: 120px;")
        self.mf_name_input = QLineEdit()
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.mf_name_input)
        form_layout.addLayout(name_layout)
        
        # Scheme
        scheme_layout = QHBoxLayout()
        scheme_label = QLabel("Scheme:")
        scheme_label.setStyleSheet("min-width: 120px;")
        self.mf_scheme_input = QComboBox()
        self.mf_scheme_input.setEditable(True)
        self.mf_scheme_input.addItems([
            "Equity", "Debt", "Hybrid", "Index", "Sectoral", "ELSS"
        ])
        scheme_layout.addWidget(scheme_label)
        scheme_layout.addWidget(self.mf_scheme_input)
        form_layout.addLayout(scheme_layout)
        
        # Investment details
        invest_group = QGroupBox("Investment Details")
        invest_layout = QVBoxLayout(invest_group)
        
        # Amount
        amount_layout = QHBoxLayout()
        amount_label = QLabel("Investment Amount:")
        amount_label.setStyleSheet("min-width: 120px;")
        self.mf_amount_input = QDoubleSpinBox()
        self.mf_amount_input.setMinimum(0.01)
        self.mf_amount_input.setMaximum(99999999)
        amount_layout.addWidget(amount_label)
        amount_layout.addWidget(self.mf_amount_input)
        invest_layout.addLayout(amount_layout)
        
        # NAV
        nav_layout = QHBoxLayout()
        nav_label = QLabel("NAV at Purchase:")
        nav_label.setStyleSheet("min-width: 120px;")
        self.mf_nav_input = QDoubleSpinBox()
        self.mf_nav_input.setMinimum(0.01)
        self.mf_nav_input.setMaximum(999999)
        self.mf_nav_input.setValue(10)
        nav_layout.addWidget(nav_label)
        nav_layout.addWidget(self.mf_nav_input)
        invest_layout.addLayout(nav_layout)
        
        # Date
        date_layout = QHBoxLayout()
        date_label = QLabel("Purchase Date:")
        date_label.setStyleSheet("min-width: 120px;")
        self.mf_date_input = QDateEdit(QDate.currentDate())
        self.mf_date_input.setCalendarPopup(True)
        self.mf_date_input.setDisplayFormat("dd-MM-yyyy")
        date_layout.addWidget(date_label)
        date_layout.addWidget(self.mf_date_input)
        invest_layout.addLayout(date_layout)
        
        form_layout.addWidget(invest_group)
        
        # Additional info
        info_group = QGroupBox("Additional Information")
        info_layout = QVBoxLayout(info_group)
        
        # Folio number
        folio_layout = QHBoxLayout()
        folio_label = QLabel("Folio Number:")
        folio_label.setStyleSheet("min-width: 120px;")
        self.mf_folio_input = QLineEdit()
        folio_layout.addWidget(folio_label)
        folio_layout.addWidget(self.mf_folio_input)
        info_layout.addLayout(folio_layout)
        
        # Notes
        notes_layout = QHBoxLayout()
        notes_label = QLabel("Notes:")
        notes_label.setStyleSheet("min-width: 120px;")
        self.mf_notes_input = QLineEdit()
        notes_layout.addWidget(notes_label)
        notes_layout.addWidget(self.mf_notes_input)
        info_layout.addLayout(notes_layout)
        
        form_layout.addWidget(info_group)
        
        layout.addWidget(form_group)
        
        # Button row
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Fund")
        add_btn.setObjectName("primary-button")
        add_btn.clicked.connect(lambda: self.add_mutual_fund(dialog))
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()

    def add_mutual_fund(self, dialog):
        portfolio = self.mf_portfolio_combo.currentText()
        amount = self.mf_amount_input.value()
        nav = self.mf_nav_input.value()
        units = amount / nav if nav > 0 else 0
        
        mf_data = {
            'Fund Name': self.mf_name_input.text().strip(),
            'Scheme': self.mf_scheme_input.currentText(),
            'Units': units,
            'NAV': nav,
            'Purchase Value': amount,
            'Purchase Date': self.mf_date_input.date().toString("dd-MM-yyyy"),
            'Folio Number': self.mf_folio_input.text().strip(),
            'Notes': self.mf_notes_input.text().strip()
        }
        
        if not mf_data['Fund Name']:
            QMessageBox.warning(self, "Error", "Fund name is required!")
            return
            
        self.portfolios[portfolio] = pd.concat([
            self.portfolios[portfolio],
            pd.DataFrame([mf_data])
        ], ignore_index=True)
        
        self.log_audit("ADDED_MF", portfolio, mf_data['Fund Name'], 
                      f"Scheme: {mf_data['Scheme']}, Amount: ₹{amount:,.2f}")
        
        self.refresh_mf_table()
        dialog.accept()
        
        QMessageBox.information(self, "Success", "Mutual fund added successfully!")

    def show_modify_mf_dialog(self):
        selected = self.mf_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Error", "Please select a mutual fund first!")
            return
            
        portfolio = self.mf_portfolio_combo.currentText()
        mf = self.portfolios[portfolio].iloc[selected]
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Modify Mutual Fund")
        dialog.setMinimumWidth(500)
        dialog.setWindowIcon(QIcon(":/icons/edit.png"))
        
        layout = QVBoxLayout(dialog)
        
        # Form group
        form_group = QGroupBox("Fund Details")
        form_layout = QVBoxLayout(form_group)
        
        # Fund name
        name_layout = QHBoxLayout()
        name_label = QLabel("Fund Name:")
        name_label.setStyleSheet("min-width: 120px;")
        self.mod_mf_name_input = QLineEdit(mf['Fund Name'])
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.mod_mf_name_input)
        form_layout.addLayout(name_layout)
        
        # Scheme
        scheme_layout = QHBoxLayout()
        scheme_label = QLabel("Scheme:")
        scheme_label.setStyleSheet("min-width: 120px;")
        self.mod_mf_scheme_input = QComboBox()
        self.mod_mf_scheme_input.setEditable(True)
        self.mod_mf_scheme_input.addItems([
            "Equity", "Debt", "Hybrid", "Index", "Sectoral", "ELSS"
        ])
        self.mod_mf_scheme_input.setCurrentText(mf.get('Scheme', ''))
        scheme_layout.addWidget(scheme_label)
        scheme_layout.addWidget(self.mod_mf_scheme_input)
        form_layout.addLayout(scheme_layout)
        
        # Investment details
        invest_group = QGroupBox("Investment Details")
        invest_layout = QVBoxLayout(invest_group)
        
        # Units
        units_layout = QHBoxLayout()
        units_label = QLabel("Units:")
        units_label.setStyleSheet("min-width: 120px;")
        self.mod_mf_units_input = QDoubleSpinBox()
        self.mod_mf_units_input.setMinimum(0.0001)
        self.mod_mf_units_input.setMaximum(99999999)
        self.mod_mf_units_input.setValue(mf['Units'])
        units_layout.addWidget(units_label)
        units_layout.addWidget(self.mod_mf_units_input)
        invest_layout.addLayout(units_layout)
        
        # NAV
        nav_layout = QHBoxLayout()
        nav_label = QLabel("NAV at Purchase:")
        nav_label.setStyleSheet("min-width: 120px;")
        self.mod_mf_nav_input = QDoubleSpinBox()
        self.mod_mf_nav_input.setMinimum(0.01)
        self.mod_mf_nav_input.setMaximum(999999)
        self.mod_mf_nav_input.setValue(mf['NAV'])
        nav_layout.addWidget(nav_label)
        nav_layout.addWidget(self.mod_mf_nav_input)
        invest_layout.addLayout(nav_layout)
        
        # Date
        date_layout = QHBoxLayout()
        date_label = QLabel("Purchase Date:")
        date_label.setStyleSheet("min-width: 120px;")
        self.mod_mf_date_input = QDateEdit(QDate.fromString(mf['Purchase Date'], "dd-MM-yyyy"))
        self.mod_mf_date_input.setCalendarPopup(True)
        self.mod_mf_date_input.setDisplayFormat("dd-MM-yyyy")
        date_layout.addWidget(date_label)
        date_layout.addWidget(self.mod_mf_date_input)
        invest_layout.addLayout(date_layout)
        
        form_layout.addWidget(invest_group)
        
        # Additional info
        info_group = QGroupBox("Additional Information")
        info_layout = QVBoxLayout(info_group)
        
        # Folio number
        folio_layout = QHBoxLayout()
        folio_label = QLabel("Folio Number:")
        folio_label.setStyleSheet("min-width: 120px;")
        self.mod_mf_folio_input = QLineEdit(mf.get('Folio Number', ''))
        folio_layout.addWidget(folio_label)
        folio_layout.addWidget(self.mod_mf_folio_input)
        info_layout.addLayout(folio_layout)
        
        # Notes
        notes_layout = QHBoxLayout()
        notes_label = QLabel("Notes:")
        notes_label.setStyleSheet("min-width: 120px;")
        self.mod_mf_notes_input = QLineEdit(mf.get('Notes', ''))
        notes_layout.addWidget(notes_label)
        notes_layout.addWidget(self.mod_mf_notes_input)
        info_layout.addLayout(notes_layout)
        
        form_layout.addWidget(info_group)
        
        layout.addWidget(form_group)
        
        # Button row
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save Changes")
        save_btn.setObjectName("primary-button")
        save_btn.clicked.connect(lambda: self.modify_mutual_fund(dialog, selected))
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()

    def modify_mutual_fund(self, dialog, row):
        portfolio = self.mf_portfolio_combo.currentText()
        mf_data = {
            'Fund Name': self.mod_mf_name_input.text().strip(),
            'Scheme': self.mod_mf_scheme_input.currentText(),
            'Units': self.mod_mf_units_input.value(),
            'NAV': self.mod_mf_nav_input.value(),
            'Purchase Value': self.mod_mf_units_input.value() * self.mod_mf_nav_input.value(),
            'Purchase Date': self.mod_mf_date_input.date().toString("dd-MM-yyyy"),
            'Folio Number': self.mod_mf_folio_input.text().strip(),
            'Notes': self.mod_mf_notes_input.text().strip()
        }
        
        if not mf_data['Fund Name']:
            QMessageBox.warning(self, "Error", "Fund name is required!")
            return
            
        self.portfolios[portfolio].iloc[row] = mf_data
        self.log_audit("MODIFIED_MF", portfolio, mf_data['Fund Name'])
        self.refresh_mf_table()
        dialog.accept()
        
        QMessageBox.information(self, "Success", "Mutual fund modified successfully!")

    def delete_mf(self):
        selected = self.mf_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Error", "Please select a mutual fund first!")
            return
            
        portfolio = self.mf_portfolio_combo.currentText()
        mf_name = self.portfolios[portfolio].iloc[selected]['Fund Name']
        
        reply = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete {mf_name} from {portfolio}?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.portfolios[portfolio] = self.portfolios[portfolio].drop(selected).reset_index(drop=True)
            self.log_audit("DELETED_MF", portfolio, mf_name)
            self.refresh_mf_table()
            
            QMessageBox.information(self, "Success", "Mutual fund deleted successfully!")

    def show_add_sip_dialog(self):
        selected = self.mf_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Error", "Please select a mutual fund first!")
            return
            
        portfolio = self.mf_portfolio_combo.currentText()
        mf = self.portfolios[portfolio].iloc[selected]
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Add SIP to Mutual Fund")
        dialog.setMinimumWidth(400)
        dialog.setWindowIcon(QIcon(":/icons/sip.png"))
        
        layout = QVBoxLayout(dialog)
        
        # SIP details group
        sip_group = QGroupBox("SIP Details")
        sip_layout = QVBoxLayout(sip_group)
        
        # Amount
        amount_layout = QHBoxLayout()
        amount_label = QLabel("SIP Amount:")
        amount_label.setStyleSheet("min-width: 120px;")
        self.sip_amount_input = QDoubleSpinBox()
        self.sip_amount_input.setMinimum(500)
        self.sip_amount_input.setMaximum(999999)
        self.sip_amount_input.setValue(5000)
        amount_layout.addWidget(amount_label)
        amount_layout.addWidget(self.sip_amount_input)
        sip_layout.addLayout(amount_layout)
        
        # Frequency
        freq_layout = QHBoxLayout()
        freq_label = QLabel("Frequency:")
        freq_label.setStyleSheet("min-width: 120px;")
        self.sip_freq_combo = QComboBox()
        self.sip_freq_combo.addItems(["Monthly", "Quarterly", "Yearly"])
        freq_layout.addWidget(freq_label)
        freq_layout.addWidget(self.sip_freq_combo)
        sip_layout.addLayout(freq_layout)
        
        # Start date
        date_layout = QHBoxLayout()
        date_label = QLabel("Start Date:")
        date_label.setStyleSheet("min-width: 120px;")
        self.sip_date_input = QDateEdit(QDate.currentDate())
        self.sip_date_input.setCalendarPopup(True)
        self.sip_date_input.setDisplayFormat("dd-MM-yyyy")
        date_layout.addWidget(date_label)
        date_layout.addWidget(self.sip_date_input)
        sip_layout.addLayout(date_layout)
        
        layout.addWidget(sip_group)
        
        # Button row
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add SIP")
        add_btn.setObjectName("primary-button")
        add_btn.clicked.connect(lambda: self.add_sip(dialog, portfolio, selected))
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()

    def add_sip(self, dialog, portfolio, row):
        mf = self.portfolios[portfolio].iloc[row]
        amount = self.sip_amount_input.value()
        freq = self.sip_freq_combo.currentText()
        start_date = self.sip_date_input.date().toString("dd-MM-yyyy")
        
        # Create SIP record (simplified - would normally track each SIP installment)
        if 'SIPs' not in mf:
            self.portfolios[portfolio].at[row, 'SIPs'] = []
            
        self.portfolios[portfolio].at[row, 'SIPs'].append({
            'amount': amount,
            'frequency': freq,
            'start_date': start_date,
            'status': 'Active'
        })
        
        self.log_audit("ADDED_SIP", portfolio, mf['Fund Name'], 
                      f"Amount: ₹{amount}, Frequency: {freq}")
        
        dialog.accept()
        QMessageBox.information(self, "Success", "SIP added successfully!")

    def load_data(self):
        """Load portfolio data with comprehensive error handling"""
        try:
            if os.path.exists('portfolio_data.json'):
                with open('portfolio_data.json', 'r') as f:
                    data = json.load(f)
                    
                # Define required columns
                required_columns = [
                    'Stock Name', 'Ticker Symbol', 'Quantity',
                    'Purchase Price', 'Purchase Date', 'Sector',
                    'Investment Value', 'Current Value'
                ]
                
                for name, port_data in data.items():
                    try:
                        # Create DataFrame
                        df = pd.DataFrame(port_data.get('stocks', []))
                        
                        # Add missing columns with default values
                        for col in required_columns:
                            if col not in df.columns:
                                df[col] = None
                        
                        # Clean ticker symbols
                        if 'Ticker Symbol' in df.columns:
                            df['Ticker Symbol'] = df['Ticker Symbol'].apply(
                                lambda x: str(x).strip().upper() + ('' if '.' in str(x) else '.NS'))
                        
                        # Calculate derived values if missing
                        if 'Investment Value' not in df.columns or df['Investment Value'].isnull().all():
                            if 'Quantity' in df.columns and 'Purchase Price' in df.columns:
                                df['Investment Value'] = df['Quantity'] * df['Purchase Price']
                        
                        self.portfolios[name] = df
                    except Exception as port_error:
                        print(f"Error loading portfolio '{name}': {str(port_error)}")
                        continue
                        
            else:
                self.initialize_default_portfolios()
                
        except Exception as e:
            print(f"Error loading data: {str(e)}")
            self.initialize_default_portfolios()

    def initialize_default_portfolios(self):
        """Create default portfolio structure if loading fails"""
        print("Initializing default portfolios")
        self.portfolios = {
            'Main Portfolio': pd.DataFrame(columns=[
                'Stock Name', 'Ticker Symbol', 'Quantity', 
                'Purchase Price', 'Purchase Date', 'Sector',
                'Investment Value', 'Current Value'
            ]),
            'Mutual Funds': pd.DataFrame(columns=[
                'Fund Name', 'Scheme', 'Units', 'NAV',
                'Purchase Value', 'Purchase Date', 'Folio Number'
            ])
        }

    def migrate_data(self):
        """Convert old format data to new format"""
        if os.path.exists('portfolios.json'):
            with open('portfolios.json', 'r') as f:
                old_data = json.load(f)
            
            # Skip if already in new format
            if 'portfolios' in old_data:
                return
                
            new_data = {
                'portfolios': old_data,
                'metadata': {
                    'version': '1.0',
                    'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            }
            
            with open('portfolios.json', 'w') as f:
                json.dump(new_data, f)

    def save_data(self):
        try:
            save_data = {}
            
            for name, df in self.portfolios.items():
                # Convert DataFrame to dictionary format
                save_data[name] = {
                    'stocks': df.to_dict('records'),
                    'description': df.attrs.get('description', '')
                }
                
            with open('portfolio_data.json', 'w') as f:
                json.dump(save_data, f, indent=4)
                
            print("Data saved successfully")
        except Exception as e:
            print(f"Error saving data: {str(e)}")
            traceback.print_exc()
                
            
    def closeEvent(self, event):
        try:
            # Stop all running workers
            for worker in self.workers[:]:
                try:
                    worker.stop()
                    worker.quit()
                    worker.wait(2000)
                except Exception as e:
                    print(f"Error stopping worker: {str(e)}")
            
            # Save data before closing (keep only one save attempt)
            print("Attempting to save data before exit...")
            self.save_data()
            print("Data saved successfully")
            
            event.accept()
        except Exception as e:
            print(f"Error during shutdown: {str(e)}")
            event.accept()


    def log_audit(self, action, portfolio, item, details=""):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"{timestamp} | {action} | {portfolio} | {item} | {details}\n"
        
        try:
            with open("portfolio_audit.log", "a") as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Error writing to audit log: {str(e)}")
            
        # Refresh activity log display if on dashboard
        if self.stacked_widget.currentIndex() == 0:
            self.refresh_activity_log()

    def auto_refresh(self):
        self.refresh_market_summary()
        self.refresh_portfolio_summary()
        
        # Refresh current page data
        current_page = self.stacked_widget.currentIndex()
        if current_page == 1:  # Portfolio management
            self.refresh_portfolio_list()
        elif current_page == 2:  # Stock operations
            self.refresh_stock_table()
        elif current_page == 3:  # Analysis
            self.update_analysis()
        elif current_page == 4:  # Market data
            self.update_market_indices()
        elif current_page == 7:  # Mutual funds
            self.refresh_mf_table()

    def worker_finished(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)
        worker.deleteLater()

   
    def closeEvent(self, event):
        try:
            # Stop all running workers
            for worker in self.workers[:]:
                try:
                    worker.stop()
                    worker.quit()
                    worker.wait(2000)  # Wait up to 2 seconds
                except Exception as e:
                    print(f"Error stopping worker: {str(e)}")
            
            # Save data before closing
            try:
                print("Attempting to save data before exit...")
                self.save_data()
                print("Data saved successfully")
            except Exception as e:
                print(f"Error saving data: {str(e)}")
                traceback.print_exc()
            
            # Close the application
            event.accept()
        except Exception as e:
            print(f"Error during shutdown: {str(e)}")
            event.accept()  # Ensure window still closes
    
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set application styles and metadata
    app.setApplicationName("Quantum Portfolio Tracker")
    app.setApplicationVersion("1.0")
    app.setWindowIcon(QIcon(":/icons/app_icon.png"))
    
    # Create and show main window
    window = PortfolioTracker()
    window.show()
    
    sys.exit(app.exec_())