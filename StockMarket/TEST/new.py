import sys
import os
os.environ['QT_LOGGING_RULES'] = 'qt.qpa.inputmethods=false'
import json
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import threading
import warnings
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QPushButton, QListWidget, QStackedWidget, QLineEdit,
                            QTableWidget, QTableWidgetItem, QComboBox, QSpinBox, 
                            QDoubleSpinBox, QDateEdit, QMessageBox, QFileDialog, QDialog,
                            QTabWidget, QSizePolicy, QFrame, QHeaderView, QGroupBox)
from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal, QTimer, QSettings
from PyQt5.QtGui import QColor, QFont, QIcon, QPalette
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

# Suppress warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=UserWarning)

plt.style.use('seaborn')

class Worker(QThread):
    data_fetched = pyqtSignal(dict)
    
    def __init__(self, tickers):
        super().__init__()
        self.tickers = tickers
        
    def run(self):
        prices = {}
        for ticker in self.tickers:
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
        self.data_fetched.emit(prices)

class MarketDataWorker(QThread):
    data_fetched = pyqtSignal(dict)
    
    def __init__(self, indices):
        super().__init__()
        self.indices = indices
        
    def run(self):
        results = {}
        for name, ticker in self.indices.items():
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
        
        self.data_fetched.emit(results)
        
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
        self.setWindowTitle("Stock Portfolio Tracker")
        self.setGeometry(100, 100, 1400, 900)
        self.portfolios = {}
        self.settings = QSettings("StockTracker", "PortfolioTracker")
        self.load_data()
        self.init_ui()
        self.load_theme()
        
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
        
        # Set default page
        self.stacked_widget.setCurrentIndex(0)
        
        # Auto-refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.auto_refresh)
        self.refresh_timer.start(300000)  # 5 minutes
        
    def set_light_theme(self):
        self.current_theme = "light"
        self.settings.setValue("theme", "light")
        
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(240, 240, 240))
        palette.setColor(QPalette.WindowText, QColor(50, 50, 50))
        palette.setColor(QPalette.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.AlternateBase, QColor(230, 230, 230))
        palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
        palette.setColor(QPalette.ToolTipText, QColor(50, 50, 50))
        palette.setColor(QPalette.Text, QColor(50, 50, 50))
        palette.setColor(QPalette.Button, QColor(240, 240, 240))
        palette.setColor(QPalette.ButtonText, QColor(50, 50, 50))
        palette.setColor(QPalette.BrightText, QColor(255, 255, 255))
        palette.setColor(QPalette.Highlight, QColor(30, 136, 229))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.Link, QColor(30, 136, 229))
        
        self.setPalette(palette)
        
        self.setStyleSheet("""
            QMainWindow {
                background-color: #F5F5F5;
            }
            QWidget {
                background-color: #F5F5F5;
                color: #333333;
            }
            QLabel, QPushButton, QListWidget, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit {
                color: #333333;
                font-size: 14px;
            }
            QPushButton {
                background-color: #E0E0E0;
                border: 1px solid #BDBDBD;
                padding: 8px 12px;
                border-radius: 6px;
                min-width: 120px;
                min-height: 35px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #BDBDBD;
            }
            QPushButton:pressed {
                background-color: #9E9E9E;
            }
            QPushButton:checked {
                background-color: #1E88E5;
                color: white;
            }
            QListWidget {
                background-color: #FFFFFF;
                border: 1px solid #BDBDBD;
                border-radius: 6px;
                padding: 5px;
            }
            QTableWidget {
                background-color: #FFFFFF;
                gridline-color: #E0E0E0;
                border: 1px solid #BDBDBD;
                border-radius: 6px;
                font-size: 13px;
            }
            QHeaderView::section {
                background-color: #E0E0E0;
                color: #333333;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {
                background-color: #FFFFFF;
                border: 1px solid #BDBDBD;
                padding: 6px;
                border-radius: 6px;
                min-height: 35px;
            }
            QTabWidget::pane {
                border: 1px solid #BDBDBD;
                border-radius: 6px;
                padding: 5px;
                background: #FFFFFF;
            }
            QTabBar::tab {
                background: #E0E0E0;
                color: #333333;
                padding: 8px 12px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                border: 1px solid #BDBDBD;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #1E88E5;
                color: white;
                border-bottom: 2px solid #0D47A1;
            }
            QTabBar::tab:hover {
                background: #BDBDBD;
            }
            QDialog {
                background-color: #F5F5F5;
            }
            QGroupBox {
                border: 1px solid #BDBDBD;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 15px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
        """)
        
        plt.style.use('seaborn')
        
    def set_dark_theme(self):
        self.current_theme = "dark"
        self.settings.setValue("theme", "dark")
        
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
        palette.setColor(QPalette.Base, QColor(40, 40, 40))
        palette.setColor(QPalette.AlternateBase, QColor(50, 50, 50))
        palette.setColor(QPalette.ToolTipBase, QColor(40, 40, 40))
        palette.setColor(QPalette.ToolTipText, QColor(220, 220, 220))
        palette.setColor(QPalette.Text, QColor(220, 220, 220))
        palette.setColor(QPalette.Button, QColor(50, 50, 50))
        palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
        palette.setColor(QPalette.BrightText, QColor(255, 255, 255))
        palette.setColor(QPalette.Highlight, QColor(30, 136, 229))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.Link, QColor(30, 136, 229))
        
        self.setPalette(palette)
        
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121212;
            }
            QWidget {
                background-color: #121212;
                color: #E0E0E0;
            }
            QLabel, QPushButton, QListWidget, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit {
                color: #E0E0E0;
                font-size: 14px;
            }
            QPushButton {
                background-color: #1E1E1E;
                border: 1px solid #333;
                padding: 8px 12px;
                border-radius: 6px;
                min-width: 120px;
                min-height: 35px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #333;
            }
            QPushButton:pressed {
                background-color: #222;
            }
            QPushButton:checked {
                background-color: #1E88E5;
            }
            QListWidget {
                background-color: #1E1E1E;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 5px;
            }
            QTableWidget {
                background-color: #1E1E1E;
                gridline-color: #333;
                border: 1px solid #333;
                border-radius: 6px;
                font-size: 13px;
            }
            QHeaderView::section {
                background-color: #1A1B26;
                color: #E0E0E0;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {
                background-color: #1E1E1E;
                border: 1px solid #333;
                padding: 6px;
                border-radius: 6px;
                min-height: 35px;
            }
            QTabWidget::pane {
                border: 1px solid #333;
                border-radius: 6px;
                padding: 5px;
                background: #1E1E1E;
            }
            QTabBar::tab {
                background: #1E1E1E;
                color: #E0E0E0;
                padding: 8px 12px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                border: 1px solid #333;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #1E88E5;
                border-bottom: 2px solid #64B5F6;
            }
            QTabBar::tab:hover {
                background: #333;
            }
            QDialog {
                background-color: #121212;
            }
            QGroupBox {
                border: 1px solid #333;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 15px;
                font-weight: bold;
            }
            QGroupBox::title {
                color: #E0E0E0;
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
        """)
        
        plt.style.use('dark_background')
        
    def load_theme(self):
        theme = self.settings.value("theme", "dark")
        if theme == "light":
            self.set_light_theme()
        else:
            self.set_dark_theme()
            
    def toggle_theme(self):
        if self.current_theme == "light":
            self.set_dark_theme()
        else:
            self.set_light_theme()
            
    def create_main_menu(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Header with theme toggle
        header = QHBoxLayout()
        
        title = QLabel("Stock Portfolio Tracker")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #1E88E5;")
        header.addWidget(title)
        
        header.addStretch()
        
        theme_btn = QPushButton()
        theme_btn.setCheckable(True)
        theme_btn.setChecked(self.current_theme == "dark")
        theme_btn.setIcon(QIcon.fromTheme("color-scheme"))
        theme_btn.setToolTip("Toggle Dark/Light Mode")
        theme_btn.clicked.connect(self.toggle_theme)
        theme_btn.setStyleSheet("""
            QPushButton {
                border: none;
                padding: 8px;
                min-width: 40px;
                min-height: 40px;
                border-radius: 20px;
            }
            QPushButton:hover {
                background-color: #333;
            }
        """)
        header.addWidget(theme_btn)
        
        layout.addLayout(header)
        
        # Subtitle
        subtitle = QLabel("Track, analyze, and optimize your investments with ease")
        subtitle.setStyleSheet("font-size: 16px; color: #757575;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        
        # Add some spacing
        layout.addSpacing(30)
        
        # Feature cards
        features_layout = QHBoxLayout()
        features_layout.setSpacing(20)
        
        # Card 1: Portfolio Management
        card1 = self.create_feature_card(
            "Portfolio Management", 
            "Organize and manage your investment portfolios", 
            "folder-multiple",
            lambda: self.stacked_widget.setCurrentIndex(1)
        )
        features_layout.addWidget(card1)
        
        # Card 2: Stock Operations
        card2 = self.create_feature_card(
            "Stock Operations", 
            "Add, modify, and track your stock holdings", 
            "chart-line",
            lambda: self.stacked_widget.setCurrentIndex(2)
        )
        features_layout.addWidget(card2)
        
        # Card 3: Dashboard
        card3 = self.create_feature_card(
            "Dashboard Views", 
            "Visualize your portfolio performance", 
            "view-dashboard",
            lambda: self.stacked_widget.setCurrentIndex(3)
        )
        features_layout.addWidget(card3)
        
        layout.addLayout(features_layout)
        
        # Second row of cards
        features_layout2 = QHBoxLayout()
        features_layout2.setSpacing(20)
        
        # Card 4: Market Analysis
        card4 = self.create_feature_card(
            "Market Analysis", 
            "Track market indices and trends", 
            "trending-up",
            lambda: self.stacked_widget.setCurrentIndex(4)
        )
        features_layout2.addWidget(card4)
        
        # Card 5: Data Operations
        card5 = self.create_feature_card(
            "Data Operations", 
            "Import/export your portfolio data", 
            "database",
            lambda: self.stacked_widget.setCurrentIndex(5)
        )
        features_layout2.addWidget(card5)
        
        # Card 6: Audit History
        card6 = self.create_feature_card(
            "Audit History", 
            "Review all your portfolio activities", 
            "history",
            lambda: self.stacked_widget.setCurrentIndex(6)
        )
        features_layout2.addWidget(card6)
        
        layout.addLayout(features_layout2)
        
        # Add some spacing
        layout.addSpacing(30)
        
        # Quick actions
        quick_actions = QHBoxLayout()
        quick_actions.setSpacing(15)
        
        refresh_btn = QPushButton("Refresh All Data")
        refresh_btn.setIcon(QIcon.fromTheme("view-refresh"))
        refresh_btn.clicked.connect(self.refresh_all_data)
        quick_actions.addWidget(refresh_btn)
        
        quick_actions.addStretch()
        
        exit_btn = QPushButton("Exit")
        exit_btn.setIcon(QIcon.fromTheme("application-exit"))
        exit_btn.clicked.connect(self.close)
        exit_btn.setStyleSheet("background-color: #D32F2F; color: white;")
        quick_actions.addWidget(exit_btn)
        
        layout.addLayout(quick_actions)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)
        
    def create_feature_card(self, title, description, icon_name, callback):
        card = QPushButton()
        card.setMinimumHeight(150)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        card.clicked.connect(callback)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(15)
        
        # Icon
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignCenter)
        icon_pixmap = QIcon.fromTheme(icon_name).pixmap(48, 48)
        icon_label.setPixmap(icon_pixmap)
        card_layout.addWidget(icon_label)
        
        # Title
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        card_layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel(description)
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setStyleSheet("font-size: 14px; color: #757575;")
        desc_label.setWordWrap(True)
        card_layout.addWidget(desc_label)
        
        # Stretch to push content to top
        card_layout.addStretch()
        
        # Style based on theme
        if self.current_theme == "light":
            card.setStyleSheet("""
                QPushButton {
                    background-color: #FFFFFF;
                    border: 1px solid #E0E0E0;
                    border-radius: 10px;
                }
                QPushButton:hover {
                    background-color: #F5F5F5;
                    border: 1px solid #BDBDBD;
                }
            """)
        else:
            card.setStyleSheet("""
                QPushButton {
                    background-color: #1E1E1E;
                    border: 1px solid #333;
                    border-radius: 10px;
                }
                QPushButton:hover {
                    background-color: #252525;
                    border: 1px solid #444;
                }
            """)
        
        return card
        
    def refresh_all_data(self):
        # Refresh current page data based on which page is active
        current_page = self.stacked_widget.currentIndex()
        
        if current_page == 1:  # Portfolio Management
            self.refresh_portfolio_list()
        elif current_page == 2:  # Stock Operations
            self.refresh_stock_table()
        elif current_page == 3:  # Dashboard Views
            self.refresh_dashboard_data()
        elif current_page == 4:  # Market Analysis
            self.refresh_indian_market_data()
            self.refresh_global_market_data()
        elif current_page == 6:  # Audit History
            self.refresh_audit_log()
            
        QMessageBox.information(self, "Refresh Complete", "All data has been refreshed!")