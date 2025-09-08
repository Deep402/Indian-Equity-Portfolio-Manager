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
                            QTabWidget, QSizePolicy, QFrame, QHeaderView, QGraphicsDropShadowEffect)
from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QColor, QFont, QIcon, QPixmap, QLinearGradient, QBrush, QPainter
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

# Suppress MacOS input method warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=UserWarning)

plt.style.use('dark_background')

class GradientWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.start_color = QColor(30, 136, 229)  # Blue
        self.end_color = QColor(76, 175, 80)     # Green
        self.setMinimumHeight(150)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0, self.start_color)
        gradient.setColorAt(1, self.end_color)
        painter.fillRect(self.rect(), gradient)
        
    def setColors(self, start, end):
        self.start_color = start
        self.end_color = end
        self.update()

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
        
        # Set default page
        self.stacked_widget.setCurrentIndex(0)
        
        # Auto-refresh timer
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.auto_refresh)
        self.refresh_timer.start(300000)  # 5 minutes
        
    def set_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121212;
            }
            QWidget {
                background-color: #121212;
                color: #E0E0E0;
                font-size: 14px;
                selection-background-color: #1E88E5;
                selection-color: white;
            }
            QPushButton {
                background-color: #1E88E5;
                border: none;
                padding: 10px 15px;
                border-radius: 5px;
                min-width: 120px;
                min-height: 40px;
                font-weight: bold;
                color: white;
            }
            QPushButton:hover {
                background-color: #2196F3;
            }
            QPushButton:pressed {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #616161;
                color: #9E9E9E;
            }
            QListWidget, QTableWidget, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTabWidget::pane {
                background-color: #1E1E1E;
                border: 1px solid #333;
                border-radius: 5px;
                padding: 5px;
            }
            QListWidget::item, QTableWidget::item {
                padding: 8px;
            }
            QListWidget::item:selected, QTableWidget::item:selected {
                background-color: #1E88E5;
                color: white;
            }
            QHeaderView::section {
                background-color: #1A1B26;
                color: #E0E0E0;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {
                padding: 8px;
                min-height: 40px;
            }
            QTabBar::tab {
                background: #1E1E1E;
                color: #E0E0E0;
                padding: 10px 15px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                border: 1px solid #333;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #1E88E5;
                border-bottom: 2px solid #64B5F6;
                color: white;
            }
            QTabBar::tab:hover {
                background: #2196F3;
            }
            QDialog {
                background-color: #121212;
            }
            QFrame {
                border-radius: 5px;
            }
            QScrollBar:vertical {
                border: none;
                background: #1E1E1E;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #424242;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

    def add_shadow_effect(self, widget):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(5)
        shadow.setColor(QColor(0, 0, 0, 150))
        widget.setGraphicsEffect(shadow)
        
    def create_main_menu(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header with gradient
        header = GradientWidget()
        header.setColors(QColor(30, 136, 229), QColor(76, 175, 80))
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(30, 30, 30, 30)
        
        title = QLabel("Manage Your Stock Portfolio Effortlessly")
        title.setStyleSheet("""
            font-size: 28px; 
            font-weight: bold; 
            color: white;
            margin-bottom: 10px;
        """)
        
        subtitle = QLabel("Track, analyze, and optimize your investments with ease")
        subtitle.setStyleSheet("""
            font-size: 16px; 
            color: rgba(255, 255, 255, 0.8);
            margin-bottom: 20px;
        """)
        
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)
        
        # Main content
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(30)
        
        # Features section
        features_title = QLabel("Key Features")
        features_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        content_layout.addWidget(features_title)
        
        # Feature cards
        features_grid = QHBoxLayout()
        features_grid.setSpacing(20)
        
        # Feature 1
        feature1 = self.create_feature_card(
            "Portfolio Management", 
            "Organize and manage multiple investment portfolios", 
            "#1E88E5"
        )
        feature1.mousePressEvent = lambda e: self.stacked_widget.setCurrentIndex(1)
        features_grid.addWidget(feature1)
        
        # Feature 2
        feature2 = self.create_feature_card(
            "Stock Operations", 
            "Add, modify and track your stock holdings", 
            "#43A047"
        )
        feature2.mousePressEvent = lambda e: self.stacked_widget.setCurrentIndex(2)
        features_grid.addWidget(feature2)
        
        # Feature 3
        feature3 = self.create_feature_card(
            "Dashboard Views", 
            "Visualize your portfolio performance", 
            "#FF9800"
        )
        feature3.mousePressEvent = lambda e: self.stacked_widget.setCurrentIndex(3)
        features_grid.addWidget(feature3)
        
        content_layout.addLayout(features_grid)
        
        # Second row of features
        features_grid2 = QHBoxLayout()
        features_grid2.setSpacing(20)
        
        # Feature 4
        feature4 = self.create_feature_card(
            "Market Analysis", 
            "Analyze market trends and indices", 
            "#9C27B0"
        )
        feature4.mousePressEvent = lambda e: self.stacked_widget.setCurrentIndex(4)
        features_grid2.addWidget(feature4)
        
        # Feature 5
        feature5 = self.create_feature_card(
            "Data Operations", 
            "Import/export your portfolio data", 
            "#00ACC1"
        )
        feature5.mousePressEvent = lambda e: self.stacked_widget.setCurrentIndex(5)
        features_grid2.addWidget(feature5)
        
        # Feature 6
        feature6 = self.create_feature_card(
            "Audit History", 
            "Review all your portfolio activities", 
            "#E53935"
        )
        feature6.mousePressEvent = lambda e: self.stacked_widget.setCurrentIndex(6)
        features_grid2.addWidget(feature6)
        
        content_layout.addLayout(features_grid2)
        
        # Get Started section
        get_started = QWidget()
        get_started_layout = QHBoxLayout(get_started)
        get_started_layout.setContentsMargins(0, 20, 0, 0)
        
        get_started_label = QLabel("Ready to get started?")
        get_started_label.setStyleSheet("font-size: 16px;")
        
        get_started_btn = QPushButton("Explore Features")
        get_started_btn.setStyleSheet("font-size: 16px; padding: 12px 24px;")
        get_started_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        
        get_started_layout.addWidget(get_started_label)
        get_started_layout.addStretch()
        get_started_layout.addWidget(get_started_btn)
        
        content_layout.addWidget(get_started)
        
        layout.addWidget(content)
        
        # Footer
        footer = QWidget()
        footer.setStyleSheet("background-color: #1E1E1E;")
        footer.setFixedHeight(60)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(30, 0, 30, 0)
        
        copyright = QLabel("© 2023 Stock Portfolio Tracker")
        copyright.setStyleSheet("color: #9E9E9E;")
        
        exit_btn = QPushButton("Exit")
        exit_btn.setStyleSheet("background-color: #D32F2F;")
        exit_btn.clicked.connect(self.close)
        
        footer_layout.addWidget(copyright)
        footer_layout.addStretch()
        footer_layout.addWidget(exit_btn)
        
        layout.addWidget(footer)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)
        
    def create_feature_card(self, title, description, color):
        card = QWidget()
        card.setStyleSheet(f"""
            background-color: {color};
            border-radius: 8px;
            padding: 20px;
        """)
        self.add_shadow_effect(card)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: white;
        """)
        
        desc_label = QLabel(description)
        desc_label.setStyleSheet("""
            font-size: 14px;
            color: rgba(255, 255, 255, 0.9);
        """)
        desc_label.setWordWrap(True)
        
        icon_label = QLabel()
        icon_label.setFixedSize(40, 40)
        icon_label.setStyleSheet("background-color: rgba(255, 255, 255, 0.2); border-radius: 20px;")
        
        arrow_icon = QLabel("➔")
        arrow_icon.setStyleSheet("font-size: 20px; color: white;")
        arrow_icon.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(title_label)
        layout.addWidget(desc_label)
        layout.addStretch()
        
        icon_layout = QHBoxLayout()
        icon_layout.addWidget(icon_label)
        icon_layout.addStretch()
        icon_layout.addWidget(arrow_icon)
        layout.addLayout(icon_layout)
        
        # Add hover animation
        def enterEvent(event):
            anim = QPropertyAnimation(card, b"geometry")
            anim.setDuration(200)
            anim.setEasingCurve(QEasingCurve.OutQuad)
            anim.setStartValue(card.geometry())
            anim.setEndValue(card.geometry().adjusted(-5, -5, 5, 5))
            anim.start()
            
        def leaveEvent(event):
            anim = QPropertyAnimation(card, b"geometry")
            anim.setDuration(200)
            anim.setEasingCurve(QEasingCurve.OutQuad)
            anim.setStartValue(card.geometry())
            anim.setEndValue(card.geometry().adjusted(5, 5, -5, -5))
            anim.start()
            
        card.enterEvent = enterEvent
        card.leaveEvent = leaveEvent
        
        return card
        
    def create_portfolio_management(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Header
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title = QLabel("Portfolio Management")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #64B5F6;")
        
        back_btn = QPushButton("Back to Main Menu")
        back_btn.setStyleSheet("padding: 8px 16px;")
        back_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(back_btn)
        layout.addWidget(header)
        
        # Content
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(20)
        
        # Left panel - Portfolio list
        left_panel = QWidget()
        left_panel.setStyleSheet("background-color: #1E1E1E; border-radius: 8px;")
        left_panel_layout = QVBoxLayout(left_panel)
        left_panel_layout.setContentsMargins(20, 20, 20, 20)
        left_panel_layout.setSpacing(15)
        
        list_title = QLabel("Your Portfolios")
        list_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        self.portfolio_list = QListWidget()
        self.portfolio_list.setStyleSheet("font-size: 14px;")
        self.portfolio_list.setSelectionMode(QListWidget.SingleSelection)
        self.refresh_portfolio_list()
        
        btn_layout = QHBoxLayout()
        create_btn = QPushButton("Create New")
        create_btn.clicked.connect(self.show_create_portfolio_dialog)
        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self.delete_portfolio)
        view_btn = QPushButton("View Details")
        view_btn.clicked.connect(self.view_portfolio_details)
        
        btn_layout.addWidget(create_btn)
        btn_layout.addWidget(delete_btn)
        btn_layout.addWidget(view_btn)
        
        left_panel_layout.addWidget(list_title)
        left_panel_layout.addWidget(self.portfolio_list)
        left_panel_layout.addLayout(btn_layout)
        
        # Right panel - Portfolio stats
        right_panel = QWidget()
        right_panel.setStyleSheet("background-color: #1E1E1E; border-radius: 8px;")
        right_panel_layout = QVBoxLayout(right_panel)
        right_panel_layout.setContentsMargins(20, 20, 20, 20)
        right_panel_layout.setSpacing(15)
        
        stats_title = QLabel("Portfolio Statistics")
        stats_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        # Stats cards
        stats_grid = QHBoxLayout()
        stats_grid.setSpacing(15)
        
        count_card = self.create_stat_card("Portfolios", "0", "#1E88E5")
        stocks_card = self.create_stat_card("Total Stocks", "0", "#43A047")
        value_card = self.create_stat_card("Total Value", "₹0", "#FF9800")
        
        stats_grid.addWidget(count_card)
        stats_grid.addWidget(stocks_card)
        stats_grid.addWidget(value_card)
        
        # Recent activity
        activity_title = QLabel("Recent Activity")
        activity_title.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 20px;")
        
        activity_list = QListWidget()
        activity_list.setStyleSheet("font-size: 13px;")
        activity_list.addItems([
            "Added 10 shares of AAPL",
            "Created portfolio 'Tech Stocks'",
            "Updated TSLA purchase price",
            "Exported portfolio data"
        ])
        
        right_panel_layout.addWidget(stats_title)
        right_panel_layout.addLayout(stats_grid)
        right_panel_layout.addWidget(activity_title)
        right_panel_layout.addWidget(activity_list)
        
        content_layout.addWidget(left_panel, 1)
        content_layout.addWidget(right_panel, 2)
        layout.addWidget(content)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)
        
    def create_stat_card(self, title, value, color):
        card = QWidget()
        card.setStyleSheet(f"""
            background-color: {color};
            border-radius: 8px;
            padding: 15px;
        """)
        self.add_shadow_effect(card)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 14px;
            color: rgba(255, 255, 255, 0.9);
        """)
        
        value_label = QLabel(value)
        value_label.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: white;
        """)
        
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        
        return card

        
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
            
    def refresh_portfolio_list(self):
        self.portfolio_list.clear()
        for portfolio in sorted(self.portfolios.keys()):
            self.portfolio_list.addItem(portfolio)
            
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
        self.stacked_widget.setCurrentIndex(2)  # Go to stock operations page
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
        
        # Portfolio selection
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
        
        # Stock table with frame
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
        
        # Buttons layout
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
        
        # Back button
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
            
        # Get live prices
        tickers = df['Ticker Symbol'].tolist()
        self.worker = Worker(tickers)
        self.worker.data_fetched.connect(
            lambda prices: self.update_stock_table_with_prices(portfolio, prices)
        )
        self.worker.start()
        
    def update_stock_table_with_prices(self, portfolio, prices):
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
                
                pl_item = QTableWidgetItem(f"{stock['Profit/Loss']:+,.2f}")
                pl_item.setForeground(QColor('#4CAF50') if stock['Profit/Loss'] >= 0 else QColor('#F44336'))
                self.stock_table.setItem(row, 5, pl_item)
                
                # Daily P/L would need previous close data
                daily_item = QTableWidgetItem("Fetching...")
                self.stock_table.setItem(row, 6, daily_item)
                
                # Start a thread to get daily change
                self.get_daily_change(stock['Ticker Symbol'], row)
            else:
                for col in range(4, 7):
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
                    
                    # Update the table
                    item = QTableWidgetItem(f"{change:+,.2f}")
                    item.setForeground(QColor('#4CAF50') if change >= 0 else QColor('#F44336'))
                    self.stock_table.setItem(row, 6, item)
            except Exception as e:
                print(f"Error fetching daily change for {ticker}: {str(e)}")
                self.stock_table.setItem(row, 6, QTableWidgetItem("N/A"))
                
        # Start a thread to avoid blocking the UI
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
            'Stock Name': fields[0][1].text().strip(),
            'Ticker Symbol': fields[1][1].text().strip().upper(),
            'Quantity': fields[2][1].value(),
            'Purchase Price': fields[3][1].value(),
            'Purchase Date': fields[4][1].date().toString("dd-MM-yyyy"),
            'Sector': fields[5][1].text().strip(),
            'Investment Value': fields[2][1].value() * fields[3][1].value()
        }
        
        if not stock_data['Stock Name'] or not stock_data['Ticker Symbol']:
            QMessageBox.warning(self, "Error", "Stock name and ticker are required!")
            return
            
        # Check if stock already exists in portfolio
        existing_stocks = self.portfolios[portfolio]['Ticker Symbol'].tolist()
        if stock_data['Ticker Symbol'] in existing_stocks:
            reply = QMessageBox.question(
                self, "Stock Exists",
                "This stock already exists in the portfolio. Would you like to add these shares to the existing position?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                # Find the existing stock and update it
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
        
        # Add new stock
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
            'Stock Name': fields[0][1].text().strip(),
            'Ticker Symbol': fields[1][1].text().strip().upper(),
            'Quantity': fields[2][1].value(),
            'Purchase Price': fields[3][1].value(),
            'Purchase Date': fields[4][1].date().toString("dd-MM-yyyy"),
            'Sector': fields[5][1].text().strip(),
            'Investment Value': fields[2][1].value() * fields[3][1].value()
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
        
        # Combined Dashboard
        self.combined_dashboard = QWidget()
        self.setup_combined_dashboard()
        self.dashboard_tabs.addTab(self.combined_dashboard, "Combined")
        
        # Individual Dashboard
        self.individual_dashboard = QWidget()
        self.setup_individual_dashboard()
        self.dashboard_tabs.addTab(self.individual_dashboard, "Individual")
        
        # Charts Dashboard
        self.charts_dashboard = QWidget()
        self.setup_charts_dashboard()
        self.dashboard_tabs.addTab(self.charts_dashboard, "Charts")
        
        layout.addWidget(self.dashboard_tabs)
        
        # Back button
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
        
        # Summary cards
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
        
        # Portfolio performance table
        table_frame = QFrame()
        table_frame.setFrameShape(QFrame.StyledPanel)
        table_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 5px;")
        table_layout = QVBoxLayout(table_frame)
        
        self.portfolio_table = QTableWidget()
        self.portfolio_table.setColumnCount(6)
        self.portfolio_table.setHorizontalHeaderLabels([
            "Portfolio", "Invested", "Current", "P/L", "Daily P/L", "Status"
        ])
        self.portfolio_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.portfolio_table.verticalHeader().setVisible(False)
        
        table_layout.addWidget(self.portfolio_table)
        layout.addWidget(table_frame)
        
        # Refresh button
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
            
        self.worker = Worker(all_tickers)
        self.worker.data_fetched.connect(self.update_dashboard_with_prices)
        self.worker.start()
        
    def update_dashboard_with_prices(self, prices):
        total_investment = 0
        total_current = 0
        total_pl = 0
        total_daily_pl = 0
        
        self.portfolio_table.setRowCount(len(self.portfolios))
        for row, (name, portfolio) in enumerate(self.portfolios.items()):
            # Ensure we have float columns for financial data
            portfolio['Current Price'] = portfolio['Ticker Symbol'].map(prices).astype(float)
            portfolio['Current Value'] = (portfolio['Quantity'] * portfolio['Current Price']).astype(float)
            portfolio['Investment Value'] = (portfolio['Quantity'] * portfolio['Purchase Price']).astype(float)
            portfolio['Profit/Loss'] = (portfolio['Current Value'] - portfolio['Investment Value']).astype(float)
            
            # Initialize Daily P/L as float column if it doesn't exist
            if 'Daily P/L' not in portfolio:
                portfolio['Daily P/L'] = 0.0
            else:
                portfolio['Daily P/L'] = portfolio['Daily P/L'].astype(float)
            
            # Calculate daily P/L (this would be better with a separate thread per stock)
            for idx, ticker in enumerate(portfolio['Ticker Symbol']):
                if pd.notna(portfolio.at[idx, 'Current Price']):
                    try:
                        stock = yf.Ticker(ticker)
                        hist = stock.history(period="2d")
                        if len(hist) >= 2:
                            prev_close = hist['Close'].iloc[-2]
                            daily_pl = (portfolio.at[idx, 'Current Price'] - prev_close) * portfolio.at[idx, 'Quantity']
                            portfolio.at[idx, 'Daily P/L'] = float(daily_pl)  # Explicitly cast to float
                    except:
                        pass
            
            investment = portfolio['Investment Value'].sum()
            current = portfolio['Current Value'].sum()
            pl = portfolio['Profit/Loss'].sum()
            daily_pl = portfolio['Daily P/L'].sum()
            
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
            
            daily_item = QTableWidgetItem(f"₹{daily_pl:+,.2f}")
            daily_item.setForeground(QColor('#4CAF50') if daily_pl >= 0 else QColor('#F44336'))
            self.portfolio_table.setItem(row, 4, daily_item)
            
            status_item = QTableWidgetItem("↑" if pl >= 0 else "↓")
            status_item.setForeground(QColor('#4CAF50') if pl >= 0 else QColor('#F44336'))
            self.portfolio_table.setItem(row, 5, status_item)
        
        # Update summary cards
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
        
        # Portfolio selection
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
        
        # Summary cards
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
        
        # Stock table
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
        
        # Refresh button
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
            
        # Get live prices
        tickers = df['Ticker Symbol'].tolist()
        self.worker = Worker(tickers)
        self.worker.data_fetched.connect(
            lambda prices: self.update_individual_dashboard(portfolio, prices)
        )
        self.worker.start()
        
    def update_individual_dashboard(self, portfolio, prices):
        df = self.portfolios[portfolio].copy()
        df['Current Price'] = df['Ticker Symbol'].map(prices)
        df['Current Value'] = df['Quantity'] * df['Current Price']
        df['Profit/Loss'] = df['Current Value'] - df['Investment Value']
        
        # Calculate daily P/L (this would be better with a separate thread per stock)
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
        
        # Update summary cards
        investment = df['Investment Value'].sum()
        current = df['Current Value'].sum()
        pl = df['Profit/Loss'].sum()
        daily_pl = df['Daily P/L'].sum()
        
        self.update_summary_card(self.individual_investment_card, "Invested", f"₹{investment:,.2f}", "#1E88E5")
        self.update_summary_card(self.individual_current_card, "Current", f"₹{current:,.2f}", "#43A047")
        
        pl_color = '#4CAF50' if pl >= 0 else '#F44336'
        pl_text = f"₹{pl:+,.2f}\n({pl/investment*100:.2f}%)" if investment else "₹0.00"
        self.update_summary_card(self.individual_pl_card, "P/L", pl_text, pl_color)
        
        daily_color = '#4CAF50' if daily_pl >= 0 else '#F44336'
        daily_text = f"₹{daily_pl:+,.2f}\n({daily_pl/current*100:.2f}%)" if current else "₹0.00"
        self.update_summary_card(self.individual_daily_card, "Today's P/L", daily_text, daily_color)
        
        # Update stock table
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
                
                daily_item = QTableWidgetItem(f"{stock['Daily P/L']:+,.2f}")
                daily_item.setForeground(QColor('#4CAF50') if stock['Daily P/L'] >= 0 else QColor('#F44336'))
                self.individual_stock_table.setItem(row, 6, daily_item)
            else:
                for col in range(4, 7):
                    self.individual_stock_table.setItem(row, col, QTableWidgetItem("N/A"))
                    
    def setup_charts_dashboard(self):
        page = self.charts_dashboard
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Portfolio selection
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
        
        # Chart tabs
        self.chart_tabs = QTabWidget()
        
        # Allocation Chart
        self.allocation_chart = FigureCanvas(Figure(figsize=(10, 6), tight_layout=True))
        self.chart_tabs.addTab(self.allocation_chart, "Allocation")
        
        # Performance Chart
        self.performance_chart = FigureCanvas(Figure(figsize=(10, 6), tight_layout=True))
        self.chart_tabs.addTab(self.performance_chart, "Performance")
        
        # Sector Chart
        self.sector_chart = FigureCanvas(Figure(figsize=(10, 6), tight_layout=True))
        self.chart_tabs.addTab(self.sector_chart, "Sector Exposure")
        
        # Today's P/L Chart
        self.daily_pl_chart = FigureCanvas(Figure(figsize=(10, 6), tight_layout=True))
        self.chart_tabs.addTab(self.daily_pl_chart, "Today's P/L")
        
        layout.addWidget(self.chart_tabs)
        
        # Refresh button
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
        if len(df) == 0:
            return
            
        # Update allocation pie chart
        self.plot_allocation_chart(df)
        
        # Update performance bar chart
        self.plot_performance_chart(df)
        
        # Update sector exposure chart
        self.plot_sector_chart(df)
        
        # Update today's P/L chart
        self.plot_daily_pl_chart(df)
        
    def plot_allocation_chart(self, df):
        fig = self.allocation_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        if 'Current Value' not in df.columns:
            df['Current Value'] = df['Quantity'] * df['Purchase Price']
            
        df = df[df['Quantity'] > 0]  # Filter out zero quantity
        
        if len(df) == 0:
            ax.text(0.5, 0.5, "No active holdings", 
                ha='center', va='center', fontsize=12)
        else:
            df = df.sort_values('Current Value', ascending=False)
            
            # Use a color palette
            colors = plt.cm.tab20c(range(len(df)))
            
            # Plot pie chart with adjusted layout
            wedges, texts, autotexts = ax.pie(
                df['Current Value'],
                labels=df['Stock Name'],
                autopct=lambda p: f'₹{p * sum(df["Current Value"])/100:,.0f}\n({p:.1f}%)',
                startangle=90,
                wedgeprops={'linewidth': 1, 'edgecolor': '#121212'},
                colors=colors,
                textprops={'fontsize': 8},
                pctdistance=0.85,  # Move percentage text inward
                labeldistance=1.05  # Move labels outward
            )
            
            # Make labels more readable
            for text in texts:
                text.set_color('white')
                text.set_fontsize(9)
                text.set_bbox(dict(facecolor='#1E1E1E', alpha=0.7, edgecolor='none'))
                
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontsize(8)
            
            ax.set_title("Portfolio Allocation", fontsize=14, color='white', pad=20)
            
        fig.tight_layout()
        self.allocation_chart.draw()

    def plot_daily_pl_chart(self, df):
        fig = self.daily_pl_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        
        if 'Daily P/L' not in df.columns:
            df['Daily P/L'] = 0.0
            
        df = df[df['Quantity'] > 0]  # Filter out zero quantity
        
        if len(df) == 0:
            ax.text(0.5, 0.5, "No active holdings", 
                ha='center', va='center', fontsize=12)
        else:
            # Calculate daily P/L if not already available
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
            
            df = df.sort_values('Daily P/L', ascending=False)
            colors = ['#4CAF50' if x >= 0 else '#F44336' for x in df['Daily P/L']]
            
            bars = ax.bar(
                df['Stock Name'],
                df['Daily P/L'],
                color=colors,
                width=0.6
            )
            
            ax.axhline(0, color='white', linestyle='--', linewidth=1)
            ax.set_title("Today's Profit/Loss", fontsize=14, color='white', pad=20)
            ax.set_ylabel("P/L (₹)", color='white')
            ax.tick_params(axis='x', rotation=45, colors='white')
            ax.tick_params(axis='y', colors='white')
            ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'₹{x:+,.0f}'))
            
            # Customize the spines
            for spine in ax.spines.values():
                spine.set_color('#333')
            
            # Add value labels with better positioning
            for bar in bars:
                height = bar.get_height()
                va = 'bottom' if height >= 0 else 'top'
                y_pos = height + (0.01 * max(df['Daily P/L']) if height >=0 else -0.01 * max(df['Daily P/L']))
                
                ax.text(
                    bar.get_x() + bar.get_width()/2.,
                    y_pos,
                    f"₹{height:+,.0f}",
                    ha='center', 
                    va=va,
                    fontsize=9,
                    color='white',
                    bbox=dict(facecolor='#1E1E1E', alpha=0.7, edgecolor='none')
                )
                
        fig.tight_layout()
        self.daily_pl_chart.draw()
        
    def plot_performance_chart(self, df):
        fig = self.performance_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        if 'Profit/Loss' not in df.columns:
            df['Profit/Loss'] = (df['Quantity'] * df['Purchase Price']) - df['Investment Value']
            
        df = df[df['Quantity'] > 0]  # Filter out zero quantity
        
        if len(df) == 0:
            ax.text(0.5, 0.5, "No active holdings", 
                   ha='center', va='center', fontsize=12)
        else:
            df = df.sort_values('Profit/Loss', ascending=False)
            colors = ['#4CAF50' if x >= 0 else '#F44336' for x in df['Profit/Loss']]
            
            bars = ax.bar(
                df['Stock Name'],
                df['Profit/Loss'],
                color=colors,
                width=0.6
            )
            
            ax.axhline(0, color='white', linestyle='--', linewidth=1)
            ax.set_title("Profit/Loss by Stock", fontsize=14, color='white', pad=20)
            ax.set_ylabel("P/L (₹)", color='white')
            ax.tick_params(axis='x', rotation=45, colors='white')
            ax.tick_params(axis='y', colors='white')
            ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'₹{x:,.0f}'))
            
            # Customize the spines
            for spine in ax.spines.values():
                spine.set_color('#333')
            
            # Add value labels
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
                
        fig.tight_layout()
        self.performance_chart.draw()
        
    def plot_sector_chart(self, df):
        fig = self.sector_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        
        if 'Sector' not in df.columns or df['Sector'].isnull().all():
            ax.text(0.5, 0.5, "No sector data available", 
                   ha='center', va='center', fontsize=12)
            fig.tight_layout()
            self.sector_chart.draw()
            return
            
        if 'Current Value' not in df.columns:
            df['Current Value'] = df['Quantity'] * df['Purchase Price']
            
        df = df[df['Quantity'] > 0]  # Filter out zero quantity
        
        if len(df) == 0:
            ax.text(0.5, 0.5, "No active holdings", 
                   ha='center', va='center', fontsize=12)
        else:
            # Group by sector
            sector_data = df.groupby('Sector')['Current Value'].sum().sort_values(ascending=False)
            
            # Use a color palette
            colors = plt.cm.tab20c(range(len(sector_data)))
            
            # Plot bar chart
            bars = ax.bar(
                sector_data.index,
                sector_data.values,
                color=colors,
                width=0.6
            )
            
            ax.set_title("Sector Exposure", fontsize=14, color='white', pad=20)
            ax.set_ylabel("Value (₹)", color='white')
            ax.tick_params(axis='x', rotation=45, colors='white')
            ax.tick_params(axis='y', colors='white')
            ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'₹{x:,.0f}'))
            
            # Customize the spines
            for spine in ax.spines.values():
                spine.set_color('#333')
            
            # Add value labels
            for bar in bars:
                height = bar.get_height()
                ax.text(
                    bar.get_x() + bar.get_width()/2.,
                    height + (0.01 * height),
                    f"₹{height:,.0f}",
                    ha='center', va='center',
                    fontsize=9,
                    color='white'
                )
                
        fig.tight_layout()
        self.sector_chart.draw()
        
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
        self.indian_market_tab = QWidget()
        self.setup_indian_market_tab()
        self.market_tabs.addTab(self.indian_market_tab, "Indian Indices")
        
        # Global Market Tab
        self.global_market_tab = QWidget()
        self.setup_global_market_tab()
        self.market_tabs.addTab(self.global_market_tab, "Global Indices")
        
        layout.addWidget(self.market_tabs)
        
        # Back button
        back_btn = QPushButton("Back to Main Menu")
        back_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        layout.addWidget(back_btn)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)
        
    def setup_indian_market_tab(self):
        page = self.indian_market_tab
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        self.indian_status_label = QLabel("Loading market data...")
        self.indian_status_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.indian_status_label)
        
        # Market table with frame
        table_frame = QFrame()
        table_frame.setFrameShape(QFrame.StyledPanel)
        table_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 5px;")
        table_layout = QVBoxLayout(table_frame)
        
        self.indian_market_table = QTableWidget()
        self.indian_market_table.setColumnCount(7)
        self.indian_market_table.setHorizontalHeaderLabels([
            "Index", "Price", "Change", "% Change", "Prev Close", "Market Hours", "Status"
        ])
        self.indian_market_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.indian_market_table.verticalHeader().setVisible(False)
        
        table_layout.addWidget(self.indian_market_table)
        layout.addWidget(table_frame)
        
        # Chart
        self.indian_chart = FigureCanvas(Figure(figsize=(10, 4)))
        layout.addWidget(self.indian_chart)
        
        # Refresh button
        refresh_btn = QPushButton("Refresh Data")
        refresh_btn.clicked.connect(self.refresh_indian_market_data)
        layout.addWidget(refresh_btn)
        
        page.setLayout(layout)
        self.refresh_indian_market_data()
        
    def refresh_indian_market_data(self):
        self.indian_status_label.setText("Fetching Indian market data...")
        
        indices = {
            'Nifty 50': '^NSEI',
            'Nifty Bank': '^NSEBANK',
            'Sensex': '^BSESN',
            'India VIX': '^INDIAVIX',
            'Nifty IT': '^CNXIT',
            'Nifty Pharma': '^CNXPHARMA'
        }
        
        self.indian_worker = MarketDataWorker(indices)
        self.indian_worker.data_fetched.connect(self.update_indian_market_tab)
        self.indian_worker.start()
        
    def update_indian_market_tab(self, data):
        # Filter out None values
        data = {k: v for k, v in data.items() if v is not None}
        
        self.indian_market_table.setRowCount(len(data))
        
        prices = []
        changes = []
        labels = []
        
        for row, (index_name, index_data) in enumerate(data.items()):
            self.indian_market_table.setItem(row, 0, QTableWidgetItem(index_name))
            self.indian_market_table.setItem(row, 1, QTableWidgetItem(f"₹{index_data['Current']:,.2f}"))
            
            change_item = QTableWidgetItem(f"{index_data['Change']:+,.2f}")
            change_item.setForeground(QColor('#4CAF50') if index_data['Change'] >= 0 else QColor('#F44336'))
            self.indian_market_table.setItem(row, 2, change_item)
            
            pct_item = QTableWidgetItem(f"{index_data['% Change']:+.2f}%")
            pct_item.setForeground(QColor('#4CAF50') if index_data['% Change'] >= 0 else QColor('#F44336'))
            self.indian_market_table.setItem(row, 3, pct_item)
            
            self.indian_market_table.setItem(row, 4, QTableWidgetItem(f"₹{index_data['Previous Close']:,.2f}"))
            self.indian_market_table.setItem(row, 5, QTableWidgetItem(index_data['Market Hours']))
            
            status_item = QTableWidgetItem(index_data['Status'])
            status_item.setForeground(QColor('#4CAF50') if "Open" in index_data['Status'] else QColor('#F44336'))
            self.indian_market_table.setItem(row, 6, status_item)
            
            # Prepare data for chart
            prices.append(index_data['Current'])
            changes.append(index_data['% Change'])
            labels.append(index_name)
        
        self.plot_market_performance(self.indian_chart.figure, labels, prices, changes, "Indian Market Overview")
        self.indian_status_label.setText(f"Indian market data updated at {datetime.now().strftime('%H:%M:%S')}")
        
    def setup_global_market_tab(self):
        page = self.global_market_tab
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        self.global_status_label = QLabel("Loading market data...")
        self.global_status_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.global_status_label)
        
        # Market table with frame
        table_frame = QFrame()
        table_frame.setFrameShape(QFrame.StyledPanel)
        table_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 5px;")
        table_layout = QVBoxLayout(table_frame)
        
        self.global_market_table = QTableWidget()
        self.global_market_table.setColumnCount(7)
        self.global_market_table.setHorizontalHeaderLabels([
            "Index", "Price", "Change", "% Change", "Prev Close", "Market Hours", "Status"
        ])
        self.global_market_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.global_market_table.verticalHeader().setVisible(False)
        
        table_layout.addWidget(self.global_market_table)
        layout.addWidget(table_frame)
        
        # Chart
        self.global_chart = FigureCanvas(Figure(figsize=(10, 4)))
        layout.addWidget(self.global_chart)
        
        # Refresh button
        refresh_btn = QPushButton("Refresh Data")
        refresh_btn.clicked.connect(self.refresh_global_market_data)
        layout.addWidget(refresh_btn)
        
        page.setLayout(layout)
        self.refresh_global_market_data()
        
    def refresh_global_market_data(self):
        self.global_status_label.setText("Fetching global market data...")
        
        indices = {
            'S&P 500': '^GSPC',
            'NASDAQ': '^IXIC',
            'Dow Jones': '^DJI',
            'FTSE 100': '^FTSE',
            'DAX': '^GDAXI',
            'Nikkei 225': '^N225',
            'Hang Seng': '^HSI',
            'Shanghai Comp': '000001.SS'
        }
        
        self.global_worker = MarketDataWorker(indices)
        self.global_worker.data_fetched.connect(self.update_global_market_tab)
        self.global_worker.start()
        
    def update_global_market_tab(self, data):
        # Filter out None values
        data = {k: v for k, v in data.items() if v is not None}
        
        self.global_market_table.setRowCount(len(data))
        
        prices = []
        changes = []
        labels = []
        
        for row, (index_name, index_data) in enumerate(data.items()):
            self.global_market_table.setItem(row, 0, QTableWidgetItem(index_name))
            self.global_market_table.setItem(row, 1, QTableWidgetItem(f"${index_data['Current']:,.2f}"))
            
            change_item = QTableWidgetItem(f"{index_data['Change']:+,.2f}")
            change_item.setForeground(QColor('#4CAF50') if index_data['Change'] >= 0 else QColor('#F44336'))
            self.global_market_table.setItem(row, 2, change_item)
            
            pct_item = QTableWidgetItem(f"{index_data['% Change']:+.2f}%")
            pct_item.setForeground(QColor('#4CAF50') if index_data['% Change'] >= 0 else QColor('#F44336'))
            self.global_market_table.setItem(row, 3, pct_item)
            
            self.global_market_table.setItem(row, 4, QTableWidgetItem(f"${index_data['Previous Close']:,.2f}"))
            self.global_market_table.setItem(row, 5, QTableWidgetItem(index_data['Market Hours']))
            
            status_item = QTableWidgetItem(index_data['Status'])
            status_item.setForeground(QColor('#4CAF50') if "Open" in index_data['Status'] else QColor('#F44336'))
            self.global_market_table.setItem(row, 6, status_item)
            
            # Prepare data for chart
            prices.append(index_data['Current'])
            changes.append(index_data['% Change'])
            labels.append(index_name)
        
        self.plot_market_performance(self.global_chart.figure, labels, prices, changes, "Global Market Overview")
        self.global_status_label.setText(f"Global market data updated at {datetime.now().strftime('%H:%M:%S')}")
        
    def plot_market_performance(self, fig, labels, prices, changes, title):
        if not labels or not prices or not changes:
            return
            
        fig.clear()
        
        try:
            ax1 = fig.add_subplot(121)
            ax2 = fig.add_subplot(122)
            
            # Customize the appearance
            for ax in [ax1, ax2]:
                ax.set_facecolor('#1E1E1E')
                ax.tick_params(colors='white')
                for spine in ax.spines.values():
                    spine.set_color('#333')
            
            # Price comparison
            colors = ['#1E88E5' if p >= 0 else '#F44336' for p in changes]
            bars1 = ax1.bar(labels, prices, color=colors)
            ax1.set_title("Index Prices", color='white', pad=20)
            ax1.set_ylabel("Price", color='white')
            ax1.tick_params(axis='x', rotation=45)
            
            # Format y-axis with appropriate symbols
            if prices and prices[0] > 1000:  # Likely in dollars
                ax1.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'${x:,.0f}'))
            else:  # Likely in rupees
                ax1.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'₹{x:,.0f}'))
            
            # Percentage change
            colors = ['#4CAF50' if c >= 0 else '#F44336' for c in changes]
            bars2 = ax2.bar(labels, changes, color=colors)
            ax2.set_title("Daily Change", color='white', pad=20)
            ax2.set_ylabel("% Change", color='white')
            ax2.tick_params(axis='x', rotation=45)
            ax2.axhline(0, color='white', linestyle='--', linewidth=1)
            
            fig.suptitle(title, fontsize=14, color='white', y=0.98)
            fig.tight_layout()
            fig.canvas.draw()
        except Exception as e:
            print(f"Error plotting market performance: {str(e)}")

        
    def create_data_operations(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        title = QLabel("Data Operations")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Export section
        export_group = QFrame()
        export_group.setFrameShape(QFrame.StyledPanel)
        export_group.setStyleSheet("background-color: #1E1E1E; border-radius: 5px; padding: 15px;")
        export_layout = QVBoxLayout(export_group)
        
        export_label = QLabel("Export Portfolios:")
        export_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        export_layout.addWidget(export_label)
        
        export_btn_layout = QHBoxLayout()
        export_current_btn = QPushButton("Export Current Portfolio")
        export_current_btn.clicked.connect(self.export_current_portfolio)
        export_all_btn = QPushButton("Export All Portfolios")
        export_all_btn.clicked.connect(self.export_all_portfolios)
        
        export_btn_layout.addWidget(export_current_btn)
        export_btn_layout.addWidget(export_all_btn)
        export_layout.addLayout(export_btn_layout)
        layout.addWidget(export_group)
        
        # Import section
        import_group = QFrame()
        import_group.setFrameShape(QFrame.StyledPanel)
        import_group.setStyleSheet("background-color: #1E1E1E; border-radius: 5px; padding: 15px;")
        import_layout = QVBoxLayout(import_group)
        
        import_label = QLabel("Import Portfolios:")
        import_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        import_layout.addWidget(import_label)
        
        import_btn = QPushButton("Import from File")
        import_btn.clicked.connect(self.import_portfolios)
        import_layout.addWidget(import_btn)
        layout.addWidget(import_group)
        
        # Back button
        back_btn = QPushButton("Back to Main Menu")
        back_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        layout.addWidget(back_btn)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)
        
    def export_current_portfolio(self):
        portfolio = self.portfolio_combo.currentText()
        if not portfolio:
            QMessageBox.warning(self, "Error", "No portfolio selected!")
            return
            
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Portfolio", 
            f"{portfolio.replace(' ', '_')}_export.json", 
            "JSON Files (*.json)"
        )
        
        if file_path:
            try:
                data = {
                    'metadata': {
                        'portfolio_name': portfolio,
                        'export_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'stock_count': len(self.portfolios[portfolio])
                    },
                    'stocks': self.portfolios[portfolio].to_dict('records')
                }
                
                with open(file_path, 'w') as f:
                    json.dump(data, f, indent=4)
                
                self.log_audit("EXPORTED_PORTFOLIO", portfolio)
                QMessageBox.information(self, "Success", f"Portfolio exported to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export: {str(e)}")
                
    def export_all_portfolios(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export All Portfolios", 
            "portfolios_export.json", 
            "JSON Files (*.json)"
        )
        
        if file_path:
            try:
                export_data = {}
                for name, data in self.portfolios.items():
                    export_data[name] = {
                        'metadata': {
                            'export_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            'stock_count': len(data)
                        },
                        'stocks': data.to_dict('records')
                    }
                
                with open(file_path, 'w') as f:
                    json.dump(export_data, f, indent=4)
                
                self.log_audit("EXPORTED_ALL", "ALL_PORTFOLIOS")
                QMessageBox.information(self, "Success", f"All portfolios exported to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export: {str(e)}")
                
    def import_portfolios(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Portfolios", 
            "", 
            "JSON Files (*.json)"
        )
        
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                if isinstance(data, dict):
                    # Check if it's a single portfolio or multiple
                    if 'metadata' in data and 'stocks' in data:
                        # Single portfolio format
                        portfolio_name = data['metadata']['portfolio_name']
                        if portfolio_name in self.portfolios:
                            reply = QMessageBox.question(
                                self, "Portfolio Exists",
                                f"Portfolio '{portfolio_name}' already exists. Overwrite?",
                                QMessageBox.Yes | QMessageBox.No
                            )
                            if reply == QMessageBox.No:
                                return
                        
                        self.portfolios[portfolio_name] = pd.DataFrame(data['stocks'])
                        self.log_audit("IMPORTED_PORTFOLIO", portfolio_name)
                        QMessageBox.information(self, "Success", f"Portfolio '{portfolio_name}' imported successfully!")
                    else:
                        # Multiple portfolios format
                        imported_count = 0
                        for name, portfolio_data in data.items():
                            if name in self.portfolios:
                                reply = QMessageBox.question(
                                    self, "Portfolio Exists",
                                    f"Portfolio '{name}' already exists. Overwrite?",
                                    QMessageBox.Yes | QMessageBox.No
                                )
                                if reply == QMessageBox.No:
                                    continue
                            
                            self.portfolios[name] = pd.DataFrame(portfolio_data['stocks'])
                            self.log_audit("IMPORTED_PORTFOLIO", name)
                            imported_count += 1
                        
                        QMessageBox.information(self, "Success", f"Successfully imported {imported_count} portfolios!")
                    
                    # Refresh UI components
                    self.refresh_portfolio_list()
                    self.portfolio_combo.clear()
                    self.portfolio_combo.addItems(sorted(self.portfolios.keys()))
                    self.dashboard_portfolio_combo.clear()
                    self.dashboard_portfolio_combo.addItems(sorted(self.portfolios.keys()))
                    self.chart_portfolio_combo.clear()
                    self.chart_portfolio_combo.addItems(sorted(self.portfolios.keys()))
                else:
                    QMessageBox.warning(self, "Error", "Invalid file format!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import: {str(e)}")
                
    def create_audit_history(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        title = QLabel("Audit History")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Filter controls
        filter_frame = QFrame()
        filter_frame.setFrameShape(QFrame.StyledPanel)
        filter_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 5px; padding: 10px;")
        filter_layout = QHBoxLayout(filter_frame)
        
        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet("font-size: 14px;")
        self.audit_filter_combo = QComboBox()
        self.audit_filter_combo.setStyleSheet("font-size: 14px;")
        self.audit_filter_combo.addItems(["All", "Portfolio Changes", "Stock Changes", "Data Operations"])
        self.audit_filter_combo.currentIndexChanged.connect(self.refresh_audit_log)
        
        clear_btn = QPushButton("Clear Log")
        clear_btn.setStyleSheet("background-color: #D32F2F;")
        clear_btn.clicked.connect(self.clear_audit_log)
        
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.audit_filter_combo)
        filter_layout.addStretch()
        filter_layout.addWidget(clear_btn)
        layout.addWidget(filter_frame)
        
        # Audit table
        table_frame = QFrame()
        table_frame.setFrameShape(QFrame.StyledPanel)
        table_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 5px;")
        table_layout = QVBoxLayout(table_frame)
        
        self.audit_table = QTableWidget()
        self.audit_table.setColumnCount(5)
        self.audit_table.setHorizontalHeaderLabels([
            "Timestamp", "Action", "Portfolio", "Stock", "Details"
        ])
        self.audit_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.audit_table.verticalHeader().setVisible(False)
        self.audit_table.setSortingEnabled(True)
        
        table_layout.addWidget(self.audit_table)
        layout.addWidget(table_frame)
        
        # Back button
        back_btn = QPushButton("Back to Main Menu")
        back_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        layout.addWidget(back_btn)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)
        self.refresh_audit_log()
        
    def refresh_audit_log(self):
        try:
            with open("portfolio_audit.log", "r") as f:
                log_entries = [line.strip().split(" | ", 4) for line in f.readlines() 
                             if line.strip() and len(line.split(" | ")) == 5]
        except FileNotFoundError:
            log_entries = []
            
        filter_text = self.audit_filter_combo.currentText()
        if filter_text == "Portfolio Changes":
            log_entries = [entry for entry in log_entries 
                         if entry[1] in ["CREATED_PORTFOLIO", "DELETED_PORTFOLIO", "IMPORTED_PORTFOLIO", "EXPORTED_PORTFOLIO"]]
        elif filter_text == "Stock Changes":
            log_entries = [entry for entry in log_entries 
                         if entry[1] in ["ADDED_STOCK", "MODIFIED_STOCK", "ADDED_SHARES", "REMOVED_SHARES", "REMOVED_ALL_SHARES"]]
        elif filter_text == "Data Operations":
            log_entries = [entry for entry in log_entries 
                         if entry[1] in ["EXPORTED_PORTFOLIO", "EXPORTED_ALL", "IMPORTED_PORTFOLIO"]]
        
        self.audit_table.setRowCount(len(log_entries))
        for row, entry in enumerate(reversed(log_entries)):
            for col, value in enumerate(entry):
                item = QTableWidgetItem(value)
                # Color code different action types
                if entry[1] in ["CREATED_PORTFOLIO", "ADDED_STOCK", "ADDED_SHARES"]:
                    item.setForeground(QColor('#4CAF50'))
                elif entry[1] in ["DELETED_PORTFOLIO", "REMOVED_SHARES", "REMOVED_ALL_SHARES"]:
                    item.setForeground(QColor('#F44336'))
                elif entry[1] in ["MODIFIED_STOCK"]:
                    item.setForeground(QColor('#FFC107'))
                elif entry[1] in ["EXPORTED_PORTFOLIO", "EXPORTED_ALL", "IMPORTED_PORTFOLIO"]:
                    item.setForeground(QColor('#2196F3'))
                
                self.audit_table.setItem(row, col, item)
                
    def clear_audit_log(self):
        reply = QMessageBox.question(
            self, "Confirm Clear",
            "Are you sure you want to clear the audit log? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                with open("portfolio_audit.log", "w") as f:
                    f.write("")
                self.refresh_audit_log()
                QMessageBox.information(self, "Success", "Audit log cleared successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear audit log: {str(e)}")
                
    def log_audit(self, action, portfolio, stock="", details=""):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"{timestamp} | {action} | {portfolio} | {stock} | {details}\n"
        
        try:
            with open("portfolio_audit.log", "a") as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Error writing to audit log: {str(e)}")
            
        self.refresh_audit_log()
        
    def auto_refresh(self):
        current_page = self.stacked_widget.currentIndex()
        
        if current_page == 2:  # Stock Operations
            self.refresh_stock_table()
        elif current_page == 3:  # Dashboard Views
            self.refresh_dashboard_data()
        elif current_page == 4:  # Market Analysis
            self.refresh_indian_market_data()
            self.refresh_global_market_data()
            
    def load_data(self):
        try:
            with open("portfolios.json", "r") as f:
                data = json.load(f)
                self.portfolios = {k: pd.DataFrame(v) for k, v in data.items()}
        except (FileNotFoundError, json.JSONDecodeError):
            self.portfolios = {}
            
    def save_data(self):
        try:
            with open("portfolios.json", "w") as f:
                json.dump({k: v.to_dict(orient='records') for k, v in self.portfolios.items()}, f, indent=4)
        except Exception as e:
            print(f"Error saving data: {str(e)}")
            
    def closeEvent(self, event):
        self.save_data()
        event.accept()

def main():
    app = QApplication(sys.argv)
    
    # Set application style and font
    app.setStyle('Fusion')
    font = QFont()
    font.setFamily("Arial")  # Changed from Segoe UI to Arial for macOS compatibility
    font.setPointSize(10)
    app.setFont(font)
    
    # Set window icon
    try:
        app.setWindowIcon(QIcon('stock_icon.png'))
    except:
        pass
    
    window = PortfolioTracker()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()