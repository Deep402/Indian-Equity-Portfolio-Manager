import sys
import os
os.environ['QT_MAC_WANTS_LAYER'] = '1'
import random
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
    QListWidgetItem, QCheckBox
)
from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal, QTimer, QSize, QMetaType
from PyQt5.QtGui import QColor, QFont, QIcon, QPalette, QLinearGradient, QBrush
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
        self.setWindowTitle("Quantum Portfolio Tracker")
        self.setGeometry(100, 50, 1600, 950)
        self.portfolios = {}
        self.workers = []
        
        # Initialize refresh timer here
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.auto_refresh)
        
        self.load_data()
        self.init_ui()
        self.set_dark_theme()
        
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
        
        # Load initial data
        self.refresh_market_summary()
        self.refresh_portfolio_summary()
        self.refresh_activity_log()
        
        # Set up auto-refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.auto_refresh)
        self.refresh_timer.start(300000)  # 5 minutes
        
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
        
        app_title = QLabel("Quantum Tracker")
        app_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #64B5F6;")
        title_layout.addWidget(app_title)
        title_layout.addStretch()
        
        sidebar_layout.addWidget(title_container)
        
        # Navigation buttons
        nav_buttons = [
            ("Dashboard", ":/icons/dashboard.png", lambda: self.stacked_widget.setCurrentIndex(0)),
            ("Portfolios", ":/icons/portfolio.png", lambda: self.stacked_widget.setCurrentIndex(1)),
            ("Stocks", ":/icons/stock.png", lambda: self.stacked_widget.setCurrentIndex(2)),
            ("Mutual Funds", ":/icons/mutual_fund.png", lambda: self.stacked_widget.setCurrentIndex(7)),
            ("Market Data", ":/icons/market.png", lambda: self.stacked_widget.setCurrentIndex(4)),
            ("Analysis", ":/icons/analysis.png", lambda: self.stacked_widget.setCurrentIndex(3)),
            ("Reports", ":/icons/report.png", lambda: self.stacked_widget.setCurrentIndex(5)),
            ("Settings", ":/icons/settings.png", lambda: self.stacked_widget.setCurrentIndex(6))
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
        self.create_dashboard_page()
        self.create_portfolio_management_page()
        self.create_stock_operations_page()
        self.create_analysis_page()
        self.create_market_data_page()
        self.create_reports_page()
        self.create_settings_page()
        self.create_mutual_funds_page()
        
        # Add content area to main layout
        self.main_layout.addWidget(self.content_area, 1)
        
    def update_time(self):
        self.time_label.setText(datetime.now().strftime("%H:%M:%S | %a, %d %b %Y"))
        
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

    def update_allocation_chart(self):
        fig = self.alloc_chart.figure
        fig.clear()
        
        # Get all holdings across portfolios
        all_holdings = []
        for port_name, port_data in self.portfolios.items():
            # Ensure we have numeric values
            port_data['Current Value'] = pd.to_numeric(port_data['Current Value'], errors='coerce')
            
            for _, row in port_data.iterrows():
                # Skip NaN values and zero values
                if pd.isna(row['Current Value']) or row['Current Value'] <= 0:
                    continue
                    
                all_holdings.append({
                    'Name': row.get('Stock Name', row.get('Fund Name', 'Unknown')),
                    'Value': row['Current Value'],
                    'Portfolio': port_name
                })
        
        if not all_holdings:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "No valid holdings data", 
                ha='center', va='center', color='white')
            self.alloc_chart.draw()
            return
            
        # Create DataFrame and group by portfolio
        df = pd.DataFrame(all_holdings)
        portfolio_values = df.groupby('Portfolio')['Value'].sum()
        
        # Remove any NaN values that might still exist
        portfolio_values = portfolio_values.dropna()
        
        if portfolio_values.empty or portfolio_values.sum() <= 0:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "No valid holdings data", 
                ha='center', va='center', color='white')
            self.alloc_chart.draw()
            return
        
        # Plot
        ax = fig.add_subplot(111)
        ax.set_facecolor('#1E1E1E')
        
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
        
    def refresh_portfolio_summary(self):
        if not self.portfolios:
            self.portfolio_value.setText("₹0.00")
            self.portfolio_change.setText("+0.00% (₹0.00)")
            self.portfolio_perf.setText("+0.00%")
            self.portfolio_daily.setText("Today: +0.00%")
            return
            
        total_investment = 0
        total_current = 0
        total_daily_pl = 0
        
        for portfolio_name, portfolio in self.portfolios.items():
            # Ensure numeric columns
            portfolio['Investment Value'] = pd.to_numeric(portfolio['Investment Value'], errors='coerce')
            portfolio['Current Value'] = pd.to_numeric(portfolio['Current Value'], errors='coerce')
            if 'Daily P/L' in portfolio.columns:
                portfolio['Daily P/L'] = pd.to_numeric(portfolio['Daily P/L'], errors='coerce')
            
            # Sum values, ignoring NaN
            total_investment += portfolio['Investment Value'].sum(skipna=True)
            total_current += portfolio['Current Value'].sum(skipna=True)
            
            # Calculate daily P/L if available
            if 'Daily P/L' in portfolio.columns:
                total_daily_pl += portfolio['Daily P/L'].sum(skipna=True)
        
        # Handle division by zero cases
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
        
        btn_row.addWidget(create_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addWidget(view_btn)
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

    def create_portfolio(self, dialog):
        name = self.portfolio_name_input.text().strip()
        if name:
            if name not in self.portfolios:
                self.portfolios[name] = pd.DataFrame(columns=[
                    'Stock Name', 'Ticker Symbol', 'Quantity', 'Purchase Price',
                    'Purchase Date', 'Sector', 'Investment Value', 'Description'
                ])
                
                # Add description if provided
                desc = self.portfolio_desc_input.text().strip()
                if desc:
                    self.portfolios[name].attrs['description'] = desc
                
                self.log_audit("CREATED_PORTFOLIO", name, "", f"Description: {desc}")
                self.refresh_portfolio_list()
                dialog.accept()
                
                # Show success message with nice styling
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("Success")
                msg.setText(f"Portfolio '{name}' created successfully!")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()
            else:
                QMessageBox.warning(self, "Error", "A portfolio with this name already exists!")
        else:
            QMessageBox.warning(self, "Error", "Portfolio name cannot be empty!")

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
        self.portfolio_combo.currentTextChanged.connect(self.on_portfolio_changed)
        
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
        self.stock_table.setColumnCount(9)
        self.stock_table.setHorizontalHeaderLabels([
            "Stock", "Ticker", "Qty", "Avg Price", "Curr Price", "Invested", "Value", "P/L", "Daily P/L"
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
        
        add_btn = QPushButton("Add Stock")
        add_btn.setIcon(QIcon(":/icons/stock_add.png"))
        add_btn.setObjectName("primary-button")
        add_btn.clicked.connect(self.show_add_stock_dialog)
        
        modify_btn = QPushButton("Modify")
        modify_btn.setIcon(QIcon(":/icons/edit.png"))
        modify_btn.clicked.connect(self.show_modify_stock_dialog)
        
        manage_btn = QPushButton("Manage Shares")
        manage_btn.setIcon(QIcon(":/icons/shares.png"))
        manage_btn.clicked.connect(self.show_manage_shares_dialog)
        
        export_btn = QPushButton("Export")
        export_btn.setIcon(QIcon(":/icons/export.png"))
        export_btn.clicked.connect(self.export_stock_data)
        
        action_row.addWidget(add_btn)
        action_row.addWidget(modify_btn)
        action_row.addWidget(manage_btn)
        action_row.addWidget(export_btn)
        action_row.addStretch()
        
        layout.addLayout(action_row)
        
        self.stacked_widget.addWidget(page)
        
    def on_portfolio_changed(self, portfolio_name):
        self.stock_page_title.setText(f"Stocks - {portfolio_name}")
        self.refresh_stock_table()
        
    def refresh_stock_table(self):
        portfolio = self.portfolio_combo.currentText()
        if not portfolio or portfolio not in self.portfolios:
            return
            
        df = self.portfolios[portfolio]
        self.stock_table.setRowCount(len(df))
        
        if len(df) == 0:
            return
            
        # Show progress bar
        self.stock_progress.setVisible(True)
        self.stock_progress.setValue(0)
        
        tickers = df['Ticker Symbol'].tolist()
        worker = Worker(tickers)
        worker.data_fetched.connect(
            lambda prices: self.update_stock_table_with_prices(portfolio, prices)
        )
        worker.finished_signal.connect(lambda: self.worker_finished(worker))
        worker.progress_updated.connect(self.stock_progress.setValue)
        self.workers.append(worker)
        worker.start()
        
    def update_stock_table_with_prices(self, portfolio, prices):
        self.stock_progress.setVisible(False)
        
        df = self.portfolios[portfolio].copy()
        df['Current Price'] = df['Ticker Symbol'].map(prices)
        df['Current Value'] = df['Quantity'] * df['Current Price']
        df['Investment Value'] = df['Quantity'] * df['Purchase Price']
        df['Profit/Loss'] = df['Current Value'] - df['Investment Value']
        
        for row in range(len(df)):
            stock = df.iloc[row]
            
            self.stock_table.setItem(row, 0, QTableWidgetItem(stock['Stock Name']))
            self.stock_table.setItem(row, 1, QTableWidgetItem(stock['Ticker Symbol']))
            self.stock_table.setItem(row, 2, QTableWidgetItem(str(stock['Quantity'])))
            self.stock_table.setItem(row, 3, QTableWidgetItem(f"{stock['Purchase Price']:.2f}"))
            
            if pd.notna(stock['Current Price']):
                self.stock_table.setItem(row, 4, QTableWidgetItem(f"{stock['Current Price']:.2f}"))
                self.stock_table.setItem(row, 5, QTableWidgetItem(f"₹{stock['Investment Value']:,.2f}"))
                self.stock_table.setItem(row, 6, QTableWidgetItem(f"₹{stock['Current Value']:,.2f}"))
                
                pl_item = QTableWidgetItem(f"₹{stock['Profit/Loss']:+,.2f}")
                pl_item.setForeground(QColor('#4CAF50') if stock['Profit/Loss'] >= 0 else QColor('#F44336'))
                self.stock_table.setItem(row, 7, pl_item)
                
                daily_item = QTableWidgetItem("Fetching...")
                self.stock_table.setItem(row, 8, daily_item)
                
                # Get daily change in background
                self.get_daily_change(stock['Ticker Symbol'], row)
            else:
                for col in range(4, 9):
                    self.stock_table.setItem(row, col, QTableWidgetItem("N/A"))
                    
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
        portfolio = self.portfolio_combo.currentText()
        stock_data = {
            'Stock Name': self.stock_name_input.text().strip(),
            'Ticker Symbol': self.ticker_input.text().strip().upper(),
            'Quantity': self.qty_input.value(),
            'Purchase Price': self.price_input.value(),
            'Purchase Date': self.date_input.date().toString("dd-MM-yyyy"),
            'Sector': self.sector_input.currentText(),
            'Investment Value': self.qty_input.value() * self.price_input.value(),
            'Notes': self.notes_input.text().strip()
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
        
        # Show success notification
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
        if 'Sector' not in df.columns or df.empty:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "No sector data available", 
                ha='center', va='center', color='white')
            self.sector_chart.draw()
            return
            
        # Calculate current value if it doesn't exist
        if 'Current Value' not in df.columns:
            if 'Purchase Price' in df.columns and 'Quantity' in df.columns:
                df['Current Value'] = df['Purchase Price'] * df['Quantity']
            else:
                ax = fig.add_subplot(111)
                ax.text(0.5, 0.5, "No valuation data available", 
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
            autopct='%1.1f%%',
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
                
                # Convert dictionaries back to DataFrames
                restored_portfolios = {}
                for name, records in backup_data['portfolios'].items():
                    restored_portfolios[name] = pd.DataFrame(records)
                
                # Confirm restoration
                reply = QMessageBox.question(
                    self, "Confirm Restore",
                    "This will overwrite your current data. Continue?",
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
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to restore data: {str(e)}")

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
        try:
            if os.path.exists('portfolios.json'):
                with open('portfolios.json', 'r') as f:
                    data = json.load(f)
                
                self.portfolios = {}
                
                # Get the portfolios data - handles both direct and nested formats
                portfolios_data = data.get('portfolios', data)
                
                for portfolio_name, portfolio_info in portfolios_data.items():
                    # Check if this is the new format with description and stocks
                    if isinstance(portfolio_info, dict) and 'stocks' in portfolio_info:
                        stocks_data = portfolio_info['stocks']
                        description = portfolio_info.get('description', '')
                    else:
                        # Old format - assume the value is the stocks list
                        stocks_data = portfolio_info
                        description = ''
                    
                    # Create DataFrame from stocks data
                    try:
                        df = pd.DataFrame(stocks_data)
                        
                        # Ensure required numeric columns are properly typed
                        numeric_cols = ['Quantity', 'Purchase Price', 'Investment Value', 
                                    'Current Value', 'Profit/Loss', 'Daily P/L']
                        for col in numeric_cols:
                            if col in df.columns:
                                df[col] = pd.to_numeric(df[col], errors='coerce')
                        
                        # Store the portfolio with its description
                        df.attrs['description'] = description
                        self.portfolios[portfolio_name] = df
                        
                    except Exception as e:
                        print(f"Error processing portfolio {portfolio_name}: {str(e)}")
                        continue
                
                print("Successfully loaded portfolios:", list(self.portfolios.keys()))
                
            else:
                print("No portfolios.json file found - starting with empty data")
                self.portfolios = {}
                
        except Exception as e:
            print(f"Fatal error loading data: {str(e)}")
            self.portfolios = {}
            
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
            save_data = {
                'portfolios': {},
                'metadata': {
                    'version': '1.0',
                    'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            }
            
            for name, df in self.portfolios.items():
                save_data['portfolios'][name] = {
                    'description': df.attrs.get('description', ''),
                    'stocks': df.where(pd.notnull(df), None).to_dict('records')
                }
            
            with open('portfolios.json', 'w') as f:
                json.dump(save_data, f, indent=4)
                
            print("Data saved successfully")
            
        except Exception as e:
            print(f"Error saving data: {str(e)}")
            
    def print_portfolio_debug(self):
        """Debug method to print portfolio structure"""
        for name, df in self.portfolios.items():
            print(f"\nPortfolio: {name}")
            print(f"Description: {df.attrs.get('description', '')}")
            print("Columns:", df.columns.tolist())
            print("First stock:", df.iloc[0].to_dict() if len(df) > 0 else "Empty")
    
    def closeEvent(self, event):
        try:
            # Stop all running workers
            for worker in self.workers:
                try:
                    worker.quit()
                    worker.wait(500)  # Wait up to 500ms
                except Exception as e:
                    print(f"Error stopping worker: {str(e)}")
            
            # Save data before closing
            try:
                self.save_data()
            except Exception as e:
                print(f"Error saving data: {str(e)}")
            
            event.accept()
        except Exception as e:
            print(f"Error during shutdown: {str(e)}")
            event.accept()  # Ensure window still closes


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
        # Stop all running workers
        for worker in self.workers:
            worker.stop()
            
        # Save data before closing
        self.save_data()
        
        event.accept()

    def set_light_theme(self):
        # Implement light theme styling
        pass

    def set_system_theme(self):
        # Implement system theme styling
        pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set application styles and metadata
    app.setApplicationName("Quantum Portfolio Tracker")
    app.setApplicationVersion("1.0")
    app.setWindowIcon(QIcon(":/icons/app_icon.png"))
    
    # Create and show main window
    window = PortfolioTracker()
    window.show()
    
