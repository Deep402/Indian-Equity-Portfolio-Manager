import sys
import json
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np
import yfinance as yf
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QDialog, QLineEdit, QComboBox,
    QDoubleSpinBox, QDateEdit, QSpinBox, QGroupBox, QGridLayout,
    QScrollArea, QFrame, QSplitter, QFileDialog, QStackedWidget,
    QSizePolicy, QSpacerItem, QCheckBox, QFormLayout, QRadioButton
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QDate, QSize
from PyQt5.QtGui import QColor, QPalette, QFont, QIcon, QPixmap
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import seaborn as sns
from matplotlib.ticker import FuncFormatter
import os
import csv
import shutil

class Worker(QThread):
    """Worker thread for fetching data"""
    data_fetched = pyqtSignal(dict)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)
    
    def __init__(self, tickers: List[str]):
        super().__init__()
        self.tickers = tickers
        self._last_request_time = {}
        self._request_count = {}
        
    def run(self):
        prices = {}
        for ticker in self.tickers:
            try:
                # Rate limiting
                current_time = time.time()
                if ticker in self._last_request_time:
                    time_since_last = current_time - self._last_request_time[ticker]
                    if time_since_last < 2:  # Minimum 2 seconds between requests
                        time.sleep(2 - time_since_last)
                
                stock = yf.Ticker(ticker)
                hist = stock.history(period="1d")
                if not hist.empty:
                    prices[ticker] = hist['Close'].iloc[-1]
                else:
                    prices[ticker] = None
                    
                self._last_request_time[ticker] = time.time()
                self._request_count[ticker] = self._request_count.get(ticker, 0) + 1
                
            except Exception as e:
                self.error_signal.emit(f"Error fetching {ticker}: {str(e)}")
                prices[ticker] = None
                time.sleep(2)  # Additional delay after error
                
        self.data_fetched.emit(prices)
        self.finished_signal.emit()

class MarketDataFetcher:
    """Class to handle market data fetching operations"""
    def __init__(self):
        self.cache = {}
        self.last_update = {}
        
    def get_stock_data(self, ticker: str, force_refresh: bool = False) -> Optional[pd.DataFrame]:
        """Get stock data with caching"""
        current_time = time.time()
        if not force_refresh and ticker in self.cache and current_time - self.last_update.get(ticker, 0) < 300:  # 5 min cache
            return self.cache[ticker]
            
        try:
            data = yf.download(ticker, period="1d", interval="1m")
            if not data.empty:
                self.cache[ticker] = data
                self.last_update[ticker] = current_time
                return data
        except Exception as e:
            print(f"Error fetching data for {ticker}: {str(e)}")
        return None

class PortfolioTracker(QMainWindow):
    """Main application window for portfolio tracking and management.
    
    This class provides a comprehensive interface for managing investment portfolios,
    including stocks and mutual funds. It features:
    - Portfolio management (create, modify, delete)
    - Stock operations (add, modify, trade)
    - Mutual fund operations (add, modify, trade)
    - Dashboard views (overview, performance, allocation)
    - Market analysis
    - Data operations (import/export, backup)
    - Audit history
    """
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Portfolio Tracker")
        self.setGeometry(100, 100, 1400, 900)
        
        # Initialize core data structures
        self.portfolios = {}  # Dict[str, Dict]: Portfolio name -> Portfolio data
        self.workers = []     # List[Worker]: Active background workers
        self.data_fetcher = MarketDataFetcher()
        
        # Load data and initialize UI
        self.load_data()
        self.init_ui()
        self.setup_refresh_timer()
        
        # Set up status bar
        self.statusBar().showMessage("Ready")
        self.statusBar().setStyleSheet("color: white;")
        
    def load_data(self):
        """Load portfolio data from JSON file and update current prices."""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    self.portfolios = json.load(f)
                
                # Update current prices for all stocks
                for portfolio_name, portfolio in self.portfolios.items():
                    if 'stocks' in portfolio:
                        for stock in portfolio['stocks']:
                            try:
                                ticker = stock.get('ticker')
                                if ticker:
                                    # Fetch current price using yfinance
                                    stock_data = yf.Ticker(ticker)
                                    current_price = stock_data.history(period='1d')['Close'].iloc[-1]
                                    stock['current_price'] = current_price
                                    
                                    # Calculate current value and P/L
                                    quantity = float(stock.get('quantity', 0))
                                    avg_price = float(stock.get('average_price', 0))
                                    current_value = quantity * current_price
                                    total_cost = quantity * avg_price
                                    pl_amount = current_value - total_cost
                                    pl_percent = (pl_amount / total_cost * 100) if total_cost > 0 else 0
                                    
                                    stock['current_value'] = current_value
                                    stock['pl_amount'] = pl_amount
                                    stock['pl_percent'] = pl_percent
                            except Exception as e:
                                self.log_audit_entry("ERROR", ticker, "", f"Error fetching price: {str(e)}")
                                stock['current_price'] = 0
                                stock['current_value'] = 0
                                stock['pl_amount'] = 0
                                stock['pl_percent'] = 0
                    
                    # Update mutual funds similarly if needed
                    if 'mutual_funds' in portfolio:
                        for fund in portfolio['mutual_funds']:
                            try:
                                ticker = fund.get('ticker')
                                if ticker:
                                    fund_data = yf.Ticker(ticker)
                                    current_price = fund_data.history(period='1d')['Close'].iloc[-1]
                                    fund['current_price'] = current_price
                                    
                                    quantity = float(fund.get('quantity', 0))
                                    avg_price = float(fund.get('average_price', 0))
                                    current_value = quantity * current_price
                                    total_cost = quantity * avg_price
                                    pl_amount = current_value - total_cost
                                    pl_percent = (pl_amount / total_cost * 100) if total_cost > 0 else 0
                                    
                                    fund['current_value'] = current_value
                                    fund['pl_amount'] = pl_amount
                                    fund['pl_percent'] = pl_percent
                            except Exception as e:
                                self.log_audit_entry("ERROR", ticker, "", f"Error fetching fund price: {str(e)}")
                                fund['current_price'] = 0
                                fund['current_value'] = 0
                                fund['pl_amount'] = 0
                                fund['pl_percent'] = 0
                
                # Update portfolio totals
                self.update_portfolio_totals()
                # Refresh the view
                self.refresh_portfolio_view()
                self.log_audit_entry("INFO", "", "", "Data loaded successfully")
            else:
                self.portfolios = {}
                self.log_audit_entry("INFO", "", "", "No data file found, starting with empty portfolios")
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error loading data: {str(e)}")
            self.portfolios = {}

    def update_portfolio_totals(self):
        """Update total values for all portfolios."""
        for portfolio_name, portfolio in self.portfolios.items():
            total_value = 0
            total_cost = 0
            
            # Calculate totals for stocks
            if 'stocks' in portfolio:
                for stock in portfolio['stocks']:
                    total_value += float(stock.get('current_value', 0))
                    total_cost += float(stock.get('quantity', 0)) * float(stock.get('average_price', 0))
            
            # Calculate totals for mutual funds
            if 'mutual_funds' in portfolio:
                for fund in portfolio['mutual_funds']:
                    total_value += float(fund.get('current_value', 0))
                    total_cost += float(fund.get('quantity', 0)) * float(fund.get('average_price', 0))
            
            # Update portfolio totals
            portfolio['total_value'] = total_value
            portfolio['total_cost'] = total_cost
            portfolio['total_pl'] = total_value - total_cost
            portfolio['total_pl_percent'] = (portfolio['total_pl'] / total_cost * 100) if total_cost > 0 else 0

    def save_data(self):
        """Save portfolio data to JSON file with proper error handling."""
        try:
            # Create backup of current file
            if os.path.exists("Portfolios.json"):
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_path = f"Portfolios_backup_{timestamp}.json"
                shutil.copy2("Portfolios.json", backup_path)

            # Save portfolios
            with open("Portfolios.json", 'w') as f:
                json.dump(self.portfolios, f, indent=4)

            # Log successful save
            self.log_audit_entry("INFO", "", "", "Portfolio data saved successfully")

        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error saving data: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to save data: {str(e)}")

    def log_audit_entry(self, action: str, portfolio: str, symbol: str, details: str):
        """Log an audit entry with proper error handling."""
        try:
            # Create audit entry
            entry = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'action': action,
                'portfolio': portfolio,
                'symbol': symbol,
                'details': details
            }

            # Load existing audit log
            try:
                with open("audit_log.json", 'r') as f:
                    audit_log = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                audit_log = []

            # Add new entry
            audit_log.append(entry)

            # Save audit log
            with open("audit_log.json", 'w') as f:
                json.dump(audit_log, f, indent=4)

        except Exception as e:
            print(f"Error logging audit entry: {str(e)}")

    def setup_refresh_timer(self):
        """Set up timer for periodic data refresh."""
        try:
            self.refresh_timer = QTimer()
            self.refresh_timer.timeout.connect(self.refresh_all_tables)
            self.refresh_timer.start(300000)  # Refresh every 5 minutes
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error setting up refresh timer: {str(e)}")
            print(f"Error setting up refresh timer: {str(e)}")
        
    def init_ui(self):
        """Initialize the user interface with proper styling and error handling."""
        try:
            # Create central widget and main layout
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            main_layout = QVBoxLayout(central_widget)
            main_layout.setContentsMargins(10, 10, 10, 10)
            main_layout.setSpacing(10)
            
            # Create stacked widget for different pages
            self.stacked_widget = QStackedWidget()
            main_layout.addWidget(self.stacked_widget)
            
            # Create all pages
            self.create_main_menu()
            self.create_portfolio_management()
            self.create_stock_operations()
            self.create_mutual_fund_operations()
            self.create_dashboard_views()
            self.create_market_analysis()
            self.create_data_operations()
            self.create_audit_history()
            
            # Show main menu by default
            self.stacked_widget.setCurrentIndex(0)
            
            # Set up status bar
            self.statusBar().showMessage("Ready")
            self.statusBar().setStyleSheet("""
                QStatusBar {
                    background-color: #2b2b2b;
                    color: white;
                    padding: 5px;
                }
            """)
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error initializing UI: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to initialize UI: {str(e)}")
            
    def create_main_menu(self):
        """Create the main menu page with consistent styling."""
        try:
            # Create main menu page
            main_menu_page = QWidget()
            layout = QVBoxLayout(main_menu_page)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(15)
            
            # Add title
            title_label = QLabel("Portfolio Tracker")
            title_label.setStyleSheet("""
                QLabel {
                    color: #ffffff;
                    font-size: 32px;
                    font-weight: bold;
                    padding: 20px;
                }
            """)
            title_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(title_label)
            
            # Create menu buttons with consistent styling
            button_style = """
                QPushButton {
                    background-color: #2b2b2b;
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 15px;
                    font-size: 16px;
                    min-height: 50px;
                }
                QPushButton:hover {
                    background-color: #3daee9;
                    color: white;
                }
                QPushButton:pressed {
                    background-color: #2980b9;
                }
            """
            
            # Create buttons for each section
            sections = [
                ("Portfolio Management", self.show_portfolio_management),
                ("Stock Operations", self.show_stock_operations),
                ("Mutual Fund Operations", self.show_mutual_fund_operations),
                ("Dashboard Views", self.show_dashboard_views),
                ("Market Analysis", self.show_market_analysis),
                ("Data Operations", self.show_data_operations),
                ("Audit History", self.show_audit_history)
            ]
            
            for text, slot in sections:
                button = QPushButton(text)
                button.setStyleSheet(button_style)
                button.clicked.connect(slot)
                layout.addWidget(button)
                
            # Add stretch to push buttons to the top
            layout.addStretch()
            
            # Add version info
            version_label = QLabel("Version 1.0.0")
            version_label.setStyleSheet("color: #666666;")
            version_label.setAlignment(Qt.AlignRight)
            layout.addWidget(version_label)
            
            # Add page to stacked widget
            self.stacked_widget.addWidget(main_menu_page)
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error creating main menu: {str(e)}")
            raise
            
    def create_portfolio_management(self):
        """Create the portfolio management page with proper error handling."""
        try:
            # Create portfolio management page
            portfolio_page = QWidget()
            layout = QVBoxLayout(portfolio_page)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(15)
            
            # Add header with back button
            header_layout = QHBoxLayout()
            
            back_button = QPushButton("← Back to Menu")
            back_button.setStyleSheet("""
                QPushButton {
                    background-color: #2b2b2b;
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #3daee9;
                }
            """)
            back_button.clicked.connect(self.show_main_menu)
            header_layout.addWidget(back_button)
            
            title_label = QLabel("Portfolio Management")
            title_label.setStyleSheet("""
                QLabel {
                    color: white;
                    font-size: 24px;
                    font-weight: bold;
                }
            """)
            title_label.setAlignment(Qt.AlignCenter)
            header_layout.addWidget(title_label)
            
            # Add stretch to push title to center
            header_layout.addStretch()
            layout.addLayout(header_layout)
            
            # Create portfolio selection section
            selection_layout = QHBoxLayout()
            
            # Portfolio combo box
            self.portfolio_combo = QComboBox()
            self.portfolio_combo.setStyleSheet("""
                QComboBox {
                    background-color: #2b2b2b;
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 5px;
                    min-width: 200px;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox::down-arrow {
                    image: url(down_arrow.png);
                    width: 12px;
                    height: 12px;
                }
                QComboBox QAbstractItemView {
                    background-color: #2b2b2b;
                    color: white;
                    selection-background-color: #3daee9;
                }
            """)
            self.portfolio_combo.currentIndexChanged.connect(self.on_portfolio_selected)
            selection_layout.addWidget(self.portfolio_combo)
            
            # Add portfolio button
            add_button = QPushButton("Add Portfolio")
            add_button.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #219a52;
                }
            """)
            add_button.clicked.connect(self.show_add_portfolio_dialog)
            selection_layout.addWidget(add_button)
            
            # Delete portfolio button
            delete_button = QPushButton("Delete Portfolio")
            delete_button.setStyleSheet("""
                QPushButton {
                    background-color: #c0392b;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #a93226;
                }
            """)
            delete_button.clicked.connect(self.delete_portfolio)
            selection_layout.addWidget(delete_button)
            
            layout.addLayout(selection_layout)
            
            # Create portfolio info section
            info_group = QGroupBox("Portfolio Information")
            info_group.setStyleSheet("""
                QGroupBox {
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    margin-top: 10px;
                    padding-top: 15px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                }
            """)
            info_layout = QGridLayout(info_group)
            
            # Add portfolio info labels
            self.total_value_label = QLabel("Total Value: $0.00")
            self.total_value_label.setStyleSheet("color: white; font-size: 16px;")
            info_layout.addWidget(self.total_value_label, 0, 0)
            
            self.total_gain_label = QLabel("Total Gain/Loss: $0.00 (0.00%)")
            self.total_gain_label.setStyleSheet("color: white; font-size: 16px;")
            info_layout.addWidget(self.total_gain_label, 0, 1)
            
            self.stock_count_label = QLabel("Stocks: 0")
            self.stock_count_label.setStyleSheet("color: white; font-size: 16px;")
            info_layout.addWidget(self.stock_count_label, 1, 0)
            
            self.fund_count_label = QLabel("Mutual Funds: 0")
            self.fund_count_label.setStyleSheet("color: white; font-size: 16px;")
            info_layout.addWidget(self.fund_count_label, 1, 1)
            
            layout.addWidget(info_group)
            
            # Create risk analysis section
            risk_group = QGroupBox("Risk Analysis")
            risk_group.setStyleSheet("""
                QGroupBox {
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    margin-top: 10px;
                    padding-top: 15px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                }
            """)
            risk_layout = QVBoxLayout(risk_group)
            
            # Add risk analysis labels
            self.risk_score_label = QLabel("Risk Score: N/A")
            self.risk_score_label.setStyleSheet("color: white; font-size: 16px;")
            risk_layout.addWidget(self.risk_score_label)
            
            self.risk_level_label = QLabel("Risk Level: N/A")
            self.risk_level_label.setStyleSheet("color: white; font-size: 16px;")
            risk_layout.addWidget(self.risk_level_label)
            
            self.diversification_label = QLabel("Diversification: N/A")
            self.diversification_label.setStyleSheet("color: white; font-size: 16px;")
            risk_layout.addWidget(self.diversification_label)
            
            layout.addWidget(risk_group)
            
            # Add stretch to push everything to the top
            layout.addStretch()
            
            # Add page to stacked widget
            self.stacked_widget.addWidget(portfolio_page)
            
            # Initial refresh
            self.refresh_portfolio_view()
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error creating portfolio management: {str(e)}")
            raise
            
    def refresh_portfolio_view(self):
        """Refresh the portfolio management view with current data."""
        try:
            # Update portfolio combo box safely to avoid recursion
            self.portfolio_combo.blockSignals(True)
            self.portfolio_combo.clear()
            self.portfolio_combo.addItems(sorted(self.portfolios.keys()))
            self.portfolio_combo.blockSignals(False)
            portfolio_name = self.portfolio_combo.currentText()
            if not portfolio_name or portfolio_name not in self.portfolios:
                self.total_value_label.setText("Total Value: $0.00")
                self.total_gain_label.setText("Total Gain/Loss: $0.00 (0.00%)")
                self.stock_count_label.setText("Stocks: 0")
                self.fund_count_label.setText("Mutual Funds: 0")
                self.risk_score_label.setText("Risk Score: N/A")
                self.risk_level_label.setText("Risk Level: N/A")
                self.diversification_label.setText("Diversification: N/A")
                return

            portfolio = self.portfolios[portfolio_name]
            # Calculate values (dummy values for now)
            total_value = 0.0
            total_gain = 0.0
            stock_count = len(portfolio.get('stocks', []))
            fund_count = len(portfolio.get('mutual_funds', []))
            # Update labels
            self.total_value_label.setText(f"Total Value: ${total_value:.2f}")
            self.total_gain_label.setText(f"Total Gain/Loss: ${total_gain:.2f} (0.00%)")
            self.stock_count_label.setText(f"Stocks: {stock_count}")
            self.fund_count_label.setText(f"Mutual Funds: {fund_count}")
            self.risk_score_label.setText("Risk Score: N/A")
            self.risk_level_label.setText("Risk Level: N/A")
            self.diversification_label.setText("Diversification: N/A")
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error refreshing portfolio view: {str(e)}")
            
    def show_main_menu(self):
        """Show the main menu page."""
        try:
            self.stacked_widget.setCurrentIndex(0)
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error showing main menu: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to show main menu: {str(e)}")
            
    def show_portfolio_management(self):
        """Show the portfolio management page."""
        try:
            self.stacked_widget.setCurrentIndex(1)
            self.refresh_portfolio_view()
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error showing portfolio management: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to show portfolio management: {str(e)}")
            
    def on_portfolio_selected(self, index):
        """Handle portfolio selection change."""
        try:
            if index >= 0:
                self.refresh_portfolio_view()
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error handling portfolio selection: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to handle portfolio selection: {str(e)}")
            
    def delete_portfolio(self):
        """Delete the selected portfolio with confirmation."""
        try:
            portfolio_name = self.portfolio_combo.currentText()
            if not portfolio_name:
                QMessageBox.warning(self, "Warning", "Please select a portfolio to delete")
                return
                
            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Are you sure you want to delete portfolio '{portfolio_name}'?\n\n"
                "This action cannot be undone and all portfolio data will be permanently lost.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                # Log the deletion before removing the portfolio
                self.log_audit_entry("DELETE_PORTFOLIO", portfolio_name, "", "Deleted portfolio")
                
                # Remove the portfolio
                del self.portfolios[portfolio_name]
                self.save_data()
                
                # Update UI
                self.refresh_portfolio_view()
                
                QMessageBox.information(
                    self,
                    "Success",
                    f"Portfolio '{portfolio_name}' has been deleted successfully"
                )
                
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error deleting portfolio: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to delete portfolio: {str(e)}")

    def show_add_portfolio_dialog(self):
        """Show dialog to add a new portfolio"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Portfolio")
        dialog.setModal(True)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #1E1E1E;
            }
            QLabel {
                color: white;
            }
            QLineEdit {
                background-color: #2D2D2D;
                color: white;
                border: 1px solid #333;
                border-radius: 3px;
                padding: 5px;
            }
            QPushButton {
                padding: 8px 20px;
                border-radius: 3px;
                font-size: 14px;
            }
        """)
        
        layout = QVBoxLayout()
        
        # Form fields
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("Portfolio Name")
        description_edit = QLineEdit()
        description_edit.setPlaceholderText("Description (optional)")
        
        layout.addWidget(name_edit)
        layout.addWidget(description_edit)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        add_btn = QPushButton("Add Portfolio")
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #616161;
            }
        """)
        
        button_layout.addWidget(add_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        def add_portfolio():
            try:
                name = name_edit.text().strip()
                description = description_edit.text().strip()
                
                if not name:
                    QMessageBox.warning(
                        dialog,
                        "Error",
                        "Please enter a portfolio name",
                        QMessageBox.Ok
                    )
                    return
                    
                if name in self.portfolios:
                    QMessageBox.warning(
                        dialog,
                        "Error",
                        "Portfolio already exists",
                        QMessageBox.Ok
                    )
                    return
                
                # Add new portfolio
                self.portfolios[name] = {
                    'name': name,
                    'description': description,
                    'created_date': datetime.now().strftime('%Y-%m-%d'),
                    'stocks': [],
                    'mutual_funds': []
                }
                
                self.save_portfolios()
                self.refresh_portfolio_view()
                self.log_audit_entry("ADD_PORTFOLIO", name, "", f"Created portfolio: {description}")
                dialog.accept()
                
            except Exception as e:
                QMessageBox.warning(
                    dialog,
                    "Error",
                    f"Error adding portfolio: {str(e)}",
                    QMessageBox.Ok
                )
                
        add_btn.clicked.connect(add_portfolio)
        cancel_btn.clicked.connect(dialog.reject)
        
        dialog.exec_()
        
    def create_stock_operations(self):
        """Create the stock operations page with proper error handling."""
        try:
            # Create stock operations page
            stock_page = QWidget()
            layout = QVBoxLayout(stock_page)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(15)
            
            # Add header with back button
            header_layout = QHBoxLayout()
            
            back_button = QPushButton("← Back to Menu")
            back_button.setStyleSheet("""
                QPushButton {
                    background-color: #2b2b2b;
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #3daee9;
                }
            """)
            back_button.clicked.connect(self.show_main_menu)
            header_layout.addWidget(back_button)
            
            title_label = QLabel("Stock Operations")
            title_label.setStyleSheet("""
                QLabel {
                    color: white;
                    font-size: 24px;
                    font-weight: bold;
                }
            """)
            title_label.setAlignment(Qt.AlignCenter)
            header_layout.addWidget(title_label)
            
            # Add stretch to push title to center
            header_layout.addStretch()
            layout.addLayout(header_layout)
            
            # Create portfolio selection section
            selection_layout = QHBoxLayout()
            
            # Portfolio combo box
            self.stock_ops_portfolio_combo = QComboBox()
            self.stock_ops_portfolio_combo.setStyleSheet("""
                QComboBox {
                    background-color: #2b2b2b;
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 5px;
                    min-width: 200px;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox::down-arrow {
                    image: url(down_arrow.png);
                    width: 12px;
                    height: 12px;
                }
                QComboBox QAbstractItemView {
                    background-color: #2b2b2b;
                    color: white;
                    selection-background-color: #3daee9;
                }
            """)
            self.stock_ops_portfolio_combo.currentIndexChanged.connect(self.on_stock_portfolio_selected)
            selection_layout.addWidget(self.stock_ops_portfolio_combo)
            
            # Add stock button
            add_button = QPushButton("Add Stock")
            add_button.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #219a52;
                }
            """)
            add_button.clicked.connect(self.show_add_stock_dialog)
            selection_layout.addWidget(add_button)
            
            # Modify stock button
            modify_button = QPushButton("Modify Stock")
            modify_button.setStyleSheet("""
                QPushButton {
                    background-color: #2980b9;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #2471a3;
                }
            """)
            modify_button.clicked.connect(self.show_modify_stock_dialog)
            selection_layout.addWidget(modify_button)
            
            # Manage shares button
            manage_button = QPushButton("Manage Shares")
            manage_button.setStyleSheet("""
                QPushButton {
                    background-color: #8e44ad;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #7d3c98;
                }
            """)
            manage_button.clicked.connect(self.show_manage_shares_dialog)
            selection_layout.addWidget(manage_button)
            
            layout.addLayout(selection_layout)
            
            # Create stock table
            self.stock_table = QTableWidget()
            self.stock_table.setStyleSheet("""
                QTableWidget {
                    background-color: #2b2b2b;
                    color: white;
                    gridline-color: #3daee9;
                    border: none;
                }
                QTableWidget::item {
                    padding: 5px;
                }
                QTableWidget::item:selected {
                    background-color: #3daee9;
                }
                QHeaderView::section {
                    background-color: #2b2b2b;
                    color: white;
                    padding: 5px;
                    border: 1px solid #3daee9;
                }
            """)
            
            # Set up table columns
            columns = [
                "Name", "Ticker", "Quantity", "Avg Price", "Current Price",
                "P/L", "P/L %", "Daily P/L", "Daily P/L %"
            ]
            self.stock_table.setColumnCount(len(columns))
            self.stock_table.setHorizontalHeaderLabels(columns)
            
            # Set column widths
            self.stock_table.setColumnWidth(0, 150)  # Name
            self.stock_table.setColumnWidth(1, 100)  # Ticker
            self.stock_table.setColumnWidth(2, 100)  # Quantity
            self.stock_table.setColumnWidth(3, 100)  # Avg Price
            self.stock_table.setColumnWidth(4, 100)  # Current Price
            self.stock_table.setColumnWidth(5, 100)  # P/L
            self.stock_table.setColumnWidth(6, 100)  # P/L %
            self.stock_table.setColumnWidth(7, 100)  # Daily P/L
            self.stock_table.setColumnWidth(8, 100)  # Daily P/L %
            
            # Enable sorting
            self.stock_table.setSortingEnabled(True)
            
            # Enable selection
            self.stock_table.setSelectionBehavior(QTableWidget.SelectRows)
            self.stock_table.setSelectionMode(QTableWidget.SingleSelection)
            
            layout.addWidget(self.stock_table)
            
            # Add page to stacked widget
            self.stacked_widget.addWidget(stock_page)
            
            # Initial refresh
            self.refresh_stock_table()
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error creating stock operations: {str(e)}")
            raise
            
    def show_stock_operations(self):
        """Show the stock operations page."""
        try:
            self.stacked_widget.setCurrentIndex(2)
            self.refresh_stock_table()
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error showing stock operations: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to show stock operations: {str(e)}")
            
    def on_stock_portfolio_selected(self, index):
        """Handle stock portfolio selection change."""
        try:
            if index >= 0:
                self.refresh_stock_table()
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error handling stock portfolio selection: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to handle stock portfolio selection: {str(e)}")
            
    def refresh_stock_table(self):
        """Refresh the stock operations table with proper error handling."""
        try:
            portfolio_name = self.stock_ops_portfolio_combo.currentText()
            if not portfolio_name or portfolio_name not in self.portfolios:
                self.stock_table.setRowCount(0)
                return
                
            portfolio = self.portfolios[portfolio_name]
            self.stock_table.setRowCount(0)
            
            # Handle both list and dictionary portfolio structures
            stocks = []
            if isinstance(portfolio, dict):
                stocks = portfolio.get('stocks', [])
            elif isinstance(portfolio, list):
                stocks = portfolio
            else:
                self.log_audit_entry("WARNING", portfolio_name, "", f"Unexpected portfolio type: {type(portfolio)}")
                return
                
            for stock in stocks:
                try:
                    # Get current stock data
                    data = self.data_fetcher.get_stock_data(stock.get('ticker', ''))
                    if data is not None and not data.empty:
                        current_price = data['Close'].iloc[-1]
                        stock['current_price'] = current_price
                        stock['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        
                        # Calculate metrics
                        quantity = stock.get('quantity', 0)
                        avg_price = stock.get('average_price', 0.0)
                        
                        value = current_price * quantity
                        investment = avg_price * quantity
                        pl = value - investment
                        pl_pct = (pl / investment * 100) if investment > 0 else 0
                        
                        # Calculate daily change
                        daily_pl = 0
                        daily_return_pct = 0
                        if 'Open' in data:
                            daily_pl = (current_price - data['Open'].iloc[0]) * quantity
                            daily_return_pct = ((current_price - data['Open'].iloc[0]) / data['Open'].iloc[0] * 100)
                        
                        # Add row to table
                        row = self.stock_table.rowCount()
                        self.stock_table.insertRow(row)
                        
                        # Add items to the table
                        items = [
                            stock.get('name', ''),
                            stock.get('ticker', ''),
                            str(quantity),
                            f"₹{avg_price:.2f}",
                            f"₹{current_price:.2f}",
                            f"₹{pl:.2f}",
                            f"{pl_pct:.2f}%",
                            f"₹{daily_pl:.2f}",
                            f"{daily_return_pct:.2f}%"
                        ]
                        
                        for col, text in enumerate(items):
                            item = QTableWidgetItem(text)
                            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                            
                            # Color P/L values
                            if col in [5, 6, 7, 8]:  # P/L columns
                                value = float(text.replace('₹', '').replace('%', ''))
                                item.setForeground(QColor('#4CAF50' if value >= 0 else '#f44336'))
                                
                            self.stock_table.setItem(row, col, item)
                            
                except Exception as e:
                    self.log_audit_entry(
                        "ERROR",
                        portfolio_name,
                        stock.get('ticker', 'unknown'),
                        f"Error updating stock: {str(e)}"
                    )
                    print(f"Error updating stock {stock.get('ticker', 'unknown')}: {str(e)}")
                    
            # Update portfolio combo box
            self.stock_ops_portfolio_combo.clear()
            self.stock_ops_portfolio_combo.addItems(sorted(self.portfolios.keys()))
            if portfolio_name:
                self.stock_ops_portfolio_combo.setCurrentText(portfolio_name)
                
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error refreshing stock table: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to refresh stock table: {str(e)}")

    def create_mutual_fund_operations(self):
        """Create the mutual fund operations page with proper error handling."""
        try:
            # Create mutual fund operations page
            fund_page = QWidget()
            layout = QVBoxLayout(fund_page)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(15)
            
            # Add header with back button
            header_layout = QHBoxLayout()
            
            back_button = QPushButton("← Back to Menu")
            back_button.setStyleSheet("""
                QPushButton {
                    background-color: #2b2b2b;
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #3daee9;
                }
            """)
            back_button.clicked.connect(self.show_main_menu)
            header_layout.addWidget(back_button)
            
            title_label = QLabel("Mutual Fund Operations")
            title_label.setStyleSheet("""
                QLabel {
                    color: white;
                    font-size: 24px;
                    font-weight: bold;
                }
            """)
            title_label.setAlignment(Qt.AlignCenter)
            header_layout.addWidget(title_label)
            
            # Add stretch to push title to center
            header_layout.addStretch()
            layout.addLayout(header_layout)
            
            # Create portfolio selection section
            selection_layout = QHBoxLayout()
            
            # Portfolio combo box
            self.fund_ops_portfolio_combo = QComboBox()
            self.fund_ops_portfolio_combo.setStyleSheet("""
                QComboBox {
                    background-color: #2b2b2b;
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 5px;
                    min-width: 200px;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox::down-arrow {
                    image: url(down_arrow.png);
                    width: 12px;
                    height: 12px;
                }
                QComboBox QAbstractItemView {
                    background-color: #2b2b2b;
                    color: white;
                    selection-background-color: #3daee9;
                }
            """)
            self.fund_ops_portfolio_combo.currentIndexChanged.connect(self.on_fund_portfolio_selected)
            selection_layout.addWidget(self.fund_ops_portfolio_combo)
            
            # Add fund button
            add_button = QPushButton("Add Fund")
            add_button.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #219a52;
                }
            """)
            add_button.clicked.connect(self.show_add_fund_dialog)
            selection_layout.addWidget(add_button)
            
            # Modify fund button
            modify_button = QPushButton("Modify Fund")
            modify_button.setStyleSheet("""
                QPushButton {
                    background-color: #2980b9;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #2471a3;
                }
            """)
            modify_button.clicked.connect(self.show_modify_fund_dialog)
            selection_layout.addWidget(modify_button)
            
            # Manage units button
            manage_button = QPushButton("Manage Units")
            manage_button.setStyleSheet("""
                QPushButton {
                    background-color: #8e44ad;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #7d3c98;
                }
            """)
            manage_button.clicked.connect(self.show_manage_units_dialog)
            selection_layout.addWidget(manage_button)
            
            layout.addLayout(selection_layout)
            
            # Create fund table
            self.fund_table = QTableWidget()
            self.fund_table.setStyleSheet("""
                QTableWidget {
                    background-color: #2b2b2b;
                    color: white;
                    gridline-color: #3daee9;
                    border: none;
                }
                QTableWidget::item {
                    padding: 5px;
                }
                QTableWidget::item:selected {
                    background-color: #3daee9;
                }
                QHeaderView::section {
                    background-color: #2b2b2b;
                    color: white;
                    padding: 5px;
                    border: 1px solid #3daee9;
                }
            """)
            
            # Set up table columns
            columns = [
                "Name", "ISIN", "Units", "Avg NAV", "Current NAV",
                "Value", "P/L", "P/L %", "Last Updated"
            ]
            self.fund_table.setColumnCount(len(columns))
            self.fund_table.setHorizontalHeaderLabels(columns)
            
            # Set column widths
            self.fund_table.setColumnWidth(0, 200)  # Name
            self.fund_table.setColumnWidth(1, 150)  # ISIN
            self.fund_table.setColumnWidth(2, 100)  # Units
            self.fund_table.setColumnWidth(3, 100)  # Avg NAV
            self.fund_table.setColumnWidth(4, 100)  # Current NAV
            self.fund_table.setColumnWidth(5, 100)  # Value
            self.fund_table.setColumnWidth(6, 100)  # P/L
            self.fund_table.setColumnWidth(7, 100)  # P/L %
            self.fund_table.setColumnWidth(8, 150)  # Last Updated
            
            # Enable sorting
            self.fund_table.setSortingEnabled(True)
            
            # Enable selection
            self.fund_table.setSelectionBehavior(QTableWidget.SelectRows)
            self.fund_table.setSelectionMode(QTableWidget.SingleSelection)
            
            layout.addWidget(self.fund_table)
            
            # Add page to stacked widget
            self.stacked_widget.addWidget(fund_page)
            
            # Initial refresh
            self.refresh_fund_table()
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error creating mutual fund operations: {str(e)}")
            raise
            
    def show_mutual_fund_operations(self):
        """Show the mutual fund operations page."""
        try:
            self.stacked_widget.setCurrentIndex(7)
            self.refresh_fund_table()
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error showing mutual fund operations: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to show mutual fund operations: {str(e)}")
            
    def on_fund_portfolio_selected(self, index):
        """Handle mutual fund portfolio selection change."""
        try:
            if index >= 0:
                self.refresh_fund_table()
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error handling mutual fund portfolio selection: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to handle mutual fund portfolio selection: {str(e)}")
            
    def refresh_fund_table(self):
        """Refresh the mutual fund operations table with proper error handling."""
        try:
            portfolio_name = self.fund_ops_portfolio_combo.currentText()
            if not portfolio_name or portfolio_name not in self.portfolios:
                self.fund_table.setRowCount(0)
                return
                
            portfolio = self.portfolios[portfolio_name]
            self.fund_table.setRowCount(0)
            
            # Handle both list and dictionary portfolio structures
            funds = []
            if isinstance(portfolio, dict):
                funds = portfolio.get('mutual_funds', [])
            elif isinstance(portfolio, list):
                funds = portfolio
            else:
                self.log_audit_entry("WARNING", portfolio_name, "", f"Unexpected portfolio type: {type(portfolio)}")
                return
                
            for fund in funds:
                try:
                    # Get current NAV
                    nav = self.get_mutual_fund_nav(fund.get('isin', ''))
                    if nav is not None:
                        fund['current_nav'] = nav
                        fund['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        
                        # Calculate metrics
                        units = fund.get('units', 0.0)
                        avg_nav = fund.get('average_nav', 0.0)
                        
                        value = nav * units
                        investment = avg_nav * units
                        pl = value - investment
                        pl_pct = (pl / investment * 100) if investment > 0 else 0
                        
                        # Add row to table
                        row = self.fund_table.rowCount()
                        self.fund_table.insertRow(row)
                        
                        # Add items to the table
                        items = [
                            fund.get('name', ''),
                            fund.get('isin', ''),
                            f"{units:.4f}",
                            f"₹{avg_nav:.4f}",
                            f"₹{nav:.4f}",
                            f"₹{value:.2f}",
                            f"₹{pl:.2f}",
                            f"{pl_pct:.2f}%",
                            fund.get('last_updated', '')
                        ]
                        
                        for col, text in enumerate(items):
                            item = QTableWidgetItem(text)
                            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                            
                            # Color P/L values
                            if col in [6, 7]:  # P/L columns
                                value = float(text.replace('₹', '').replace('%', ''))
                                item.setForeground(QColor('#4CAF50' if value >= 0 else '#f44336'))
                                
                            self.fund_table.setItem(row, col, item)
                            
                except Exception as e:
                    self.log_audit_entry(
                        "ERROR",
                        portfolio_name,
                        fund.get('isin', 'unknown'),
                        f"Error updating fund: {str(e)}"
                    )
                    print(f"Error updating fund {fund.get('isin', 'unknown')}: {str(e)}")
                    
            # Update portfolio combo box
            self.fund_ops_portfolio_combo.clear()
            self.fund_ops_portfolio_combo.addItems(sorted(self.portfolios.keys()))
            if portfolio_name:
                self.fund_ops_portfolio_combo.setCurrentText(portfolio_name)
                
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error refreshing fund table: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to refresh fund table: {str(e)}")

    def create_dashboard_views(self):
        """Create the dashboard views with proper error handling."""
        try:
            # Create dashboard page
            dashboard_page = QWidget()
            layout = QVBoxLayout(dashboard_page)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(15)
            
            # Add header with back button
            header_layout = QHBoxLayout()
            
            back_button = QPushButton("← Back to Menu")
            back_button.setStyleSheet("""
                QPushButton {
                    background-color: #2b2b2b;
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #3daee9;
                }
            """)
            back_button.clicked.connect(self.show_main_menu)
            header_layout.addWidget(back_button)
            
            title_label = QLabel("Portfolio Dashboard")
            title_label.setStyleSheet("""
                QLabel {
                    color: white;
                    font-size: 24px;
                    font-weight: bold;
                }
            """)
            title_label.setAlignment(Qt.AlignCenter)
            header_layout.addWidget(title_label)
            
            # Add stretch to push title to center
            header_layout.addStretch()
            layout.addLayout(header_layout)
            
            # Create portfolio selection section
            selection_layout = QHBoxLayout()
            
            # Portfolio combo box
            self.dashboard_portfolio_combo = QComboBox()
            self.dashboard_portfolio_combo.setStyleSheet("""
                QComboBox {
                    background-color: #2b2b2b;
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 5px;
                    min-width: 200px;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox::down-arrow {
                    image: url(down_arrow.png);
                    width: 12px;
                    height: 12px;
                }
                QComboBox QAbstractItemView {
                    background-color: #2b2b2b;
                    color: white;
                    selection-background-color: #3daee9;
                }
            """)
            self.dashboard_portfolio_combo.currentIndexChanged.connect(self.on_dashboard_portfolio_selected)
            selection_layout.addWidget(self.dashboard_portfolio_combo)
            
            # Add refresh button
            refresh_button = QPushButton("Refresh")
            refresh_button.setStyleSheet("""
                QPushButton {
                    background-color: #2980b9;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #2471a3;
                }
            """)
            refresh_button.clicked.connect(self.refresh_dashboard)
            selection_layout.addWidget(refresh_button)
            
            layout.addLayout(selection_layout)
            
            # Create tab widget for different views
            self.dashboard_tabs = QTabWidget()
            self.dashboard_tabs.setStyleSheet("""
                QTabWidget::pane {
                    border: 1px solid #3daee9;
                    background-color: #2b2b2b;
                }
                QTabBar::tab {
                    background-color: #2b2b2b;
                    color: white;
                    padding: 8px 15px;
                    border: 1px solid #3daee9;
                    border-bottom: none;
                    border-top-left-radius: 5px;
                    border-top-right-radius: 5px;
                }
                QTabBar::tab:selected {
                    background-color: #3daee9;
                }
                QTabBar::tab:hover {
                    background-color: #2980b9;
                }
            """)
            
            # Create overview tab
            overview_tab = QWidget()
            overview_layout = QVBoxLayout(overview_tab)
            
            # Add summary cards
            cards_layout = QHBoxLayout()
            
            # Total value card
            self.total_value_card = QFrame()
            self.total_value_card.setStyleSheet("""
                QFrame {
                    background-color: #2b2b2b;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 15px;
                }
            """)
            total_value_layout = QVBoxLayout(self.total_value_card)
            
            total_value_label = QLabel("Total Portfolio Value")
            total_value_label.setStyleSheet("color: white; font-size: 16px;")
            total_value_layout.addWidget(total_value_label)
            
            self.total_value_amount = QLabel("₹0.00")
            self.total_value_amount.setStyleSheet("color: #4CAF50; font-size: 24px; font-weight: bold;")
            total_value_layout.addWidget(self.total_value_amount)
            
            cards_layout.addWidget(self.total_value_card)
            
            # Total P/L card
            self.total_pl_card = QFrame()
            self.total_pl_card.setStyleSheet("""
                QFrame {
                    background-color: #2b2b2b;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 15px;
                }
            """)
            total_pl_layout = QVBoxLayout(self.total_pl_card)
            
            total_pl_label = QLabel("Total Profit/Loss")
            total_pl_label.setStyleSheet("color: white; font-size: 16px;")
            total_pl_layout.addWidget(total_pl_label)
            
            self.total_pl_amount = QLabel("₹0.00 (0.00%)")
            self.total_pl_amount.setStyleSheet("color: #4CAF50; font-size: 24px; font-weight: bold;")
            total_pl_layout.addWidget(self.total_pl_amount)
            
            cards_layout.addWidget(self.total_pl_card)
            
            # Asset allocation card
            self.allocation_card = QFrame()
            self.allocation_card.setStyleSheet("""
                QFrame {
                    background-color: #2b2b2b;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 15px;
                }
            """)
            allocation_layout = QVBoxLayout(self.allocation_card)
            
            allocation_label = QLabel("Asset Allocation")
            allocation_label.setStyleSheet("color: white; font-size: 16px;")
            allocation_layout.addWidget(allocation_label)
            
            self.allocation_chart = QLabel("Chart will be displayed here")
            self.allocation_chart.setStyleSheet("color: white; font-size: 14px;")
            self.allocation_chart.setAlignment(Qt.AlignCenter)
            allocation_layout.addWidget(self.allocation_chart)
            
            cards_layout.addWidget(self.allocation_card)
            
            overview_layout.addLayout(cards_layout)
            
            # Add performance chart
            self.performance_chart = QLabel("Performance chart will be displayed here")
            self.performance_chart.setStyleSheet("""
                QLabel {
                    background-color: #2b2b2b;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 15px;
                    color: white;
                    font-size: 14px;
                }
            """)
            self.performance_chart.setAlignment(Qt.AlignCenter)
            self.performance_chart.setMinimumHeight(300)
            overview_layout.addWidget(self.performance_chart)
            
            # Add tab to tab widget
            self.dashboard_tabs.addTab(overview_tab, "Overview")
            
            # Create performance tab
            performance_tab = QWidget()
            performance_layout = QVBoxLayout(performance_tab)
            
            # Add performance metrics
            metrics_layout = QGridLayout()
            
            # Add metric cards
            metrics = [
                ("Total Return", "0.00%"),
                ("Annualized Return", "0.00%"),
                ("Sharpe Ratio", "0.00"),
                ("Max Drawdown", "0.00%"),
                ("Volatility", "0.00%"),
                ("Beta", "0.00")
            ]
            
            for i, (label, value) in enumerate(metrics):
                card = QFrame()
                card.setStyleSheet("""
                    QFrame {
                        background-color: #2b2b2b;
                        border: 2px solid #3daee9;
                        border-radius: 5px;
                        padding: 15px;
                    }
                """)
                card_layout = QVBoxLayout(card)
                
                metric_label = QLabel(label)
                metric_label.setStyleSheet("color: white; font-size: 14px;")
                card_layout.addWidget(metric_label)
                
                metric_value = QLabel(value)
                metric_value.setStyleSheet("color: #4CAF50; font-size: 18px; font-weight: bold;")
                card_layout.addWidget(metric_value)
                
                metrics_layout.addWidget(card, i // 3, i % 3)
                
            performance_layout.addLayout(metrics_layout)
            
            # Add detailed performance chart
            self.detailed_performance_chart = QLabel("Detailed performance chart will be displayed here")
            self.detailed_performance_chart.setStyleSheet("""
                QLabel {
                    background-color: #2b2b2b;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 15px;
                    color: white;
                    font-size: 14px;
                }
            """)
            self.detailed_performance_chart.setAlignment(Qt.AlignCenter)
            self.detailed_performance_chart.setMinimumHeight(300)
            performance_layout.addWidget(self.detailed_performance_chart)
            
            # Add tab to tab widget
            self.dashboard_tabs.addTab(performance_tab, "Performance")
            
            # Create allocation tab
            allocation_tab = QWidget()
            allocation_layout = QVBoxLayout(allocation_tab)
            
            # Add allocation charts
            charts_layout = QHBoxLayout()
            
            # Asset type allocation
            self.asset_type_chart = QLabel("Asset type allocation chart will be displayed here")
            self.asset_type_chart.setStyleSheet("""
                QLabel {
                    background-color: #2b2b2b;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 15px;
                    color: white;
                    font-size: 14px;
                }
            """)
            self.asset_type_chart.setAlignment(Qt.AlignCenter)
            self.asset_type_chart.setMinimumHeight(300)
            charts_layout.addWidget(self.asset_type_chart)
            
            # Sector allocation
            self.sector_chart = QLabel("Sector allocation chart will be displayed here")
            self.sector_chart.setStyleSheet("""
                QLabel {
                    background-color: #2b2b2b;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 15px;
                    color: white;
                    font-size: 14px;
                }
            """)
            self.sector_chart.setAlignment(Qt.AlignCenter)
            self.sector_chart.setMinimumHeight(300)
            charts_layout.addWidget(self.sector_chart)
            
            allocation_layout.addLayout(charts_layout)
            
            # Add tab to tab widget
            self.dashboard_tabs.addTab(allocation_tab, "Allocation")
            
            layout.addWidget(self.dashboard_tabs)
            
            # Add page to stacked widget
            self.stacked_widget.addWidget(dashboard_page)
            
            # Initial refresh
            self.refresh_dashboard()
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error creating dashboard views: {str(e)}")
            raise
            
    def show_dashboard_views(self):
        """Show the dashboard views page."""
        try:
            # Find the index of the dashboard page in the stacked widget
            for i in range(self.stacked_widget.count()):
                if isinstance(self.stacked_widget.widget(i), QWidget) and hasattr(self.stacked_widget.widget(i), 'layout'):
                    if self.stacked_widget.widget(i).layout().itemAt(0) and isinstance(self.stacked_widget.widget(i).layout().itemAt(0).widget(), QHBoxLayout):
                        if isinstance(self.stacked_widget.widget(i).layout().itemAt(0).widget().itemAt(1).widget(), QLabel):
                            if self.stacked_widget.widget(i).layout().itemAt(0).widget().itemAt(1).widget().text() == "Portfolio Dashboard":
                                self.stacked_widget.setCurrentIndex(i)
                                self.refresh_dashboard()
                                return
            
            # If we get here, we couldn't find the dashboard page
            self.log_audit_entry("ERROR", "", "", "Dashboard page not found in stacked widget")
            QMessageBox.warning(self, "Error", "Failed to show dashboard views: Dashboard page not found")
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error showing dashboard views: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to show dashboard views: {str(e)}")

    def show_dashboard(self):
        """Show the dashboard page."""
        try:
            self.stacked_widget.setCurrentIndex(8)
            self.refresh_dashboard()
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error showing dashboard: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to show dashboard: {str(e)}")
            
    def on_dashboard_portfolio_selected(self, index):
        """Handle dashboard portfolio selection change."""
        try:
            if index >= 0:
                self.refresh_dashboard()
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error handling dashboard portfolio selection: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to handle dashboard portfolio selection: {str(e)}")
            
    def refresh_dashboard(self):
        """Refresh the dashboard with proper error handling."""
        try:
            portfolio_name = self.dashboard_portfolio_combo.currentText()
            if not portfolio_name or portfolio_name not in self.portfolios:
                self.clear_dashboard()
                return
                
            portfolio = self.portfolios[portfolio_name]
            
            # Calculate portfolio metrics
            total_value = 0.0
            total_investment = 0.0
            asset_allocation = {
                'stocks': 0.0,
                'mutual_funds': 0.0
            }
            sector_allocation = {}
            
            # Handle both list and dictionary portfolio structures
            stocks = []
            funds = []
            if isinstance(portfolio, dict):
                stocks = portfolio.get('stocks', [])
                funds = portfolio.get('mutual_funds', [])
            elif isinstance(portfolio, list):
                stocks = portfolio
            else:
                self.log_audit_entry("WARNING", portfolio_name, "", f"Unexpected portfolio type: {type(portfolio)}")
                return
                
            # Process stocks
            for stock in stocks:
                try:
                    # Get current price
                    price = self.get_stock_price(stock.get('ticker', ''))
                    if price is not None:
                        stock['current_price'] = price
                        stock['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        
                        # Calculate metrics
                        quantity = stock.get('quantity', 0)
                        avg_price = stock.get('average_price', 0.0)
                        
                        value = price * quantity
                        investment = avg_price * quantity
                        
                        total_value += value
                        total_investment += investment
                        asset_allocation['stocks'] += value
                        
                        # Update sector allocation
                        sector = stock.get('sector', 'Unknown')
                        sector_allocation[sector] = sector_allocation.get(sector, 0.0) + value
                        
                except Exception as e:
                    self.log_audit_entry(
                        "ERROR",
                        portfolio_name,
                        stock.get('ticker', 'unknown'),
                        f"Error updating stock: {str(e)}"
                    )
                    print(f"Error updating stock {stock.get('ticker', 'unknown')}: {str(e)}")
                    
            # Process mutual funds
            for fund in funds:
                try:
                    # Get current NAV
                    nav = self.get_mutual_fund_nav(fund.get('isin', ''))
                    if nav is not None:
                        fund['current_nav'] = nav
                        fund['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        
                        # Calculate metrics
                        units = fund.get('units', 0.0)
                        avg_nav = fund.get('average_nav', 0.0)
                        
                        value = nav * units
                        investment = avg_nav * units
                        
                        total_value += value
                        total_investment += investment
                        asset_allocation['mutual_funds'] += value
                        
                except Exception as e:
                    self.log_audit_entry(
                        "ERROR",
                        portfolio_name,
                        fund.get('isin', 'unknown'),
                        f"Error updating fund: {str(e)}"
                    )
                    print(f"Error updating fund {fund.get('isin', 'unknown')}: {str(e)}")
                    
            # Update UI
            self.total_value_amount.setText(f"₹{total_value:.2f}")
            
            total_pl = total_value - total_investment
            total_pl_pct = (total_pl / total_investment * 100) if total_investment > 0 else 0
            
            self.total_pl_amount.setText(
                f"₹{total_pl:.2f} ({total_pl_pct:.2f}%)"
            )
            self.total_pl_amount.setStyleSheet(
                f"color: {'#4CAF50' if total_pl >= 0 else '#f44336'}; "
                "font-size: 24px; font-weight: bold;"
            )
            
            # Update charts
            self.update_allocation_charts(asset_allocation, sector_allocation)
            self.update_performance_chart(portfolio_name)
            
            # Update portfolio combo box
            self.dashboard_portfolio_combo.clear()
            self.dashboard_portfolio_combo.addItems(sorted(self.portfolios.keys()))
            if portfolio_name:
                self.dashboard_portfolio_combo.setCurrentText(portfolio_name)
                
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error refreshing dashboard: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to refresh dashboard: {str(e)}")
            
    def clear_dashboard(self):
        """Clear the dashboard display."""
        try:
            self.total_value_amount.setText("₹0.00")
            self.total_pl_amount.setText("₹0.00 (0.00%)")
            self.total_pl_amount.setStyleSheet("color: #4CAF50; font-size: 24px; font-weight: bold;")
            
            self.allocation_chart.setText("No data available")
            self.performance_chart.setText("No data available")
            self.detailed_performance_chart.setText("No data available")
            self.asset_type_chart.setText("No data available")
            self.sector_chart.setText("No data available")
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error clearing dashboard: {str(e)}")
            print(f"Error clearing dashboard: {str(e)}")
            
    def update_allocation_charts(self, asset_allocation, sector_allocation):
        """Update the allocation charts with proper error handling."""
        try:
            # Update asset type allocation
            total = sum(asset_allocation.values())
            if total > 0:
                asset_labels = []
                asset_values = []
                asset_colors = ['#4CAF50', '#2196F3']  # Green for stocks, Blue for mutual funds
                
                for asset_type, value in asset_allocation.items():
                    if value > 0:
                        asset_labels.append(asset_type.replace('_', ' ').title())
                        asset_values.append(value / total * 100)
                        
                # TODO: Create and display pie chart for asset allocation
                self.asset_type_chart.setText(
                    "Asset Allocation:\n" +
                    "\n".join(f"{label}: {value:.1f}%" for label, value in zip(asset_labels, asset_values))
                )
            else:
                self.asset_type_chart.setText("No asset allocation data available")
                
            # Update sector allocation
            total = sum(sector_allocation.values())
            if total > 0:
                sector_labels = []
                sector_values = []
                sector_colors = [
                    '#4CAF50', '#2196F3', '#FFC107', '#F44336', '#9C27B0',
                    '#00BCD4', '#FF9800', '#795548', '#607D8B', '#E91E63'
                ]
                
                # Sort sectors by value
                sorted_sectors = sorted(
                    sector_allocation.items(),
                    key=lambda x: x[1],
                    reverse=True
                )
                
                for sector, value in sorted_sectors:
                    if value > 0:
                        sector_labels.append(sector)
                        sector_values.append(value / total * 100)
                        
                # TODO: Create and display pie chart for sector allocation
                self.sector_chart.setText(
                    "Sector Allocation:\n" +
                    "\n".join(f"{label}: {value:.1f}%" for label, value in zip(sector_labels, sector_values))
                )
            else:
                self.sector_chart.setText("No sector allocation data available")
                
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error updating allocation charts: {str(e)}")
            print(f"Error updating allocation charts: {str(e)}")
            
    def update_performance_chart(self, portfolio_name):
        """Update the performance chart with proper error handling."""
        try:
            # TODO: Implement performance chart using historical data
            self.performance_chart.setText("Performance chart will be implemented")
            self.detailed_performance_chart.setText("Detailed performance chart will be implemented")
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error updating performance chart: {str(e)}")
            print(f"Error updating performance chart: {str(e)}")

    def create_market_analysis(self):
        """Create the market analysis page"""
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title
        title = QLabel("Market Analysis")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #64B5F6;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Create tab widget
        self.market_tabs = QTabWidget()
        self.market_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #333;
                background: #1E1E1E;
            }
            QTabBar::tab {
                background: #2D2D2D;
                color: white;
                padding: 8px 20px;
                border: 1px solid #333;
            }
            QTabBar::tab:selected {
                background: #64B5F6;
                color: black;
            }
        """)
        
        # Portfolio selection
        portfolio_frame = QFrame()
        portfolio_frame.setFrameShape(QFrame.StyledPanel)
        portfolio_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 5px; padding: 10px;")
        portfolio_layout = QHBoxLayout(portfolio_frame)
        
        portfolio_label = QLabel("Selected Portfolio:")
        portfolio_label.setStyleSheet("font-size: 14px;")
        self.market_portfolio_combo = QComboBox()
        self.market_portfolio_combo.setStyleSheet("font-size: 14px; min-width: 200px;")
        self.market_portfolio_combo.addItems(sorted(self.portfolios.keys()))
        self.market_portfolio_combo.currentTextChanged.connect(self.refresh_market_data)
        
        portfolio_layout.addWidget(portfolio_label)
        portfolio_layout.addWidget(self.market_portfolio_combo)
        portfolio_layout.addStretch()
        
        layout.addWidget(portfolio_frame)
        
        # Add tabs
        # 1. Overview Tab
        overview_tab = QWidget()
        overview_layout = QVBoxLayout()
        
        # Summary metrics
        metrics_frame = QFrame()
        metrics_frame.setStyleSheet("""
            QFrame {
                background-color: #2D2D2D;
                border-radius: 5px;
                padding: 15px;
            }
            QLabel {
                color: white;
                font-size: 14px;
            }
            QLabel[class="metric-label"] {
                color: #888;
                font-size: 12px;
            }
            QLabel[class="metric-value"] {
                font-size: 16px;
                font-weight: bold;
            }
        """)
        metrics_layout = QGridLayout()
        
        # Create metric labels
        metrics = [
            ('Total Value', 'market_total_value'),
            ('Total Investment', 'market_total_investment'),
            ('Total Return', 'market_total_return'),
            ('Total Return %', 'market_total_return_pct'),
            ('Daily Change', 'market_daily_change'),
            ('Daily Change %', 'market_daily_change_pct')
        ]
        
        for i, (label_text, attr_name) in enumerate(metrics):
            # Label
            label = QLabel(label_text)
            label.setProperty("class", "metric-label")
            metrics_layout.addWidget(label, i // 3, (i % 3) * 2)
            
            # Value
            value_label = QLabel("₹0.00")
            value_label.setProperty("class", "metric-value")
            setattr(self, attr_name, value_label)
            metrics_layout.addWidget(value_label, i // 3, (i % 3) * 2 + 1)
        
        metrics_frame.setLayout(metrics_layout)
        overview_layout.addWidget(metrics_frame)
        
        # Holdings table
        holdings_frame = QFrame()
        holdings_frame.setStyleSheet("background-color: #2D2D2D; border-radius: 5px;")
        holdings_layout = QVBoxLayout()
        
        holdings_label = QLabel("Current Holdings")
        holdings_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        holdings_layout.addWidget(holdings_label)
        
        self.holdings_table = QTableWidget()
        self.holdings_table.setColumnCount(6)
        self.holdings_table.setHorizontalHeaderLabels([
            "Asset", "Type", "Quantity", "Avg Price", "Current Value", "P/L"
        ])
        self.holdings_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.holdings_table.verticalHeader().setVisible(False)
        self.holdings_table.setStyleSheet("""
            QTableWidget {
                background-color: #1E1E1E;
                color: white;
                gridline-color: #333;
                border: none;
            }
            QHeaderView::section {
                background-color: #2D2D2D;
                color: white;
                padding: 5px;
                border: 1px solid #333;
            }
        """)
        
        holdings_layout.addWidget(self.holdings_table)
        holdings_frame.setLayout(holdings_layout)
        overview_layout.addWidget(holdings_frame)
        
        overview_tab.setLayout(overview_layout)
        self.market_tabs.addTab(overview_tab, "Overview")
        
        # 2. Performance Tab
        performance_tab = QWidget()
        performance_layout = QVBoxLayout()
        
        # Performance chart
        chart_frame = QFrame()
        chart_frame.setStyleSheet("background-color: #2D2D2D; border-radius: 5px;")
        chart_layout = QVBoxLayout()
        
        chart_label = QLabel("Portfolio Performance")
        chart_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        chart_layout.addWidget(chart_label)
        
        self.performance_chart = FigureCanvas(Figure(figsize=(8, 4)))
        self.performance_chart.figure.patch.set_facecolor('#2D2D2D')
        chart_layout.addWidget(self.performance_chart)
        
        chart_frame.setLayout(chart_layout)
        performance_layout.addWidget(chart_frame)
        
        performance_tab.setLayout(performance_layout)
        self.market_tabs.addTab(performance_tab, "Performance")
        
        # 3. Allocation Tab
        allocation_tab = QWidget()
        allocation_layout = QVBoxLayout()
        
        # Allocation charts
        charts_frame = QFrame()
        charts_frame.setStyleSheet("background-color: #2D2D2D; border-radius: 5px;")
        charts_layout = QHBoxLayout()
        
        # Asset type pie chart
        pie_frame = QFrame()
        pie_layout = QVBoxLayout()
        pie_label = QLabel("Asset Allocation")
        pie_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        pie_layout.addWidget(pie_label)
        
        self.asset_pie_chart = FigureCanvas(Figure(figsize=(4, 4)))
        self.asset_pie_chart.figure.patch.set_facecolor('#2D2D2D')
        pie_layout.addWidget(self.asset_pie_chart)
        
        pie_frame.setLayout(pie_layout)
        charts_layout.addWidget(pie_frame)
        
        # Sector pie chart
        sector_frame = QFrame()
        sector_layout = QVBoxLayout()
        sector_label = QLabel("Sector Allocation")
        sector_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        sector_layout.addWidget(sector_label)
        
        self.sector_pie_chart = FigureCanvas(Figure(figsize=(4, 4)))
        self.sector_pie_chart.figure.patch.set_facecolor('#2D2D2D')
        sector_layout.addWidget(self.sector_pie_chart)
        
        sector_frame.setLayout(sector_layout)
        charts_layout.addWidget(sector_frame)
        
        charts_frame.setLayout(charts_layout)
        allocation_layout.addWidget(charts_frame)
        
        allocation_tab.setLayout(allocation_layout)
        self.market_tabs.addTab(allocation_tab, "Allocation")
        
        layout.addWidget(self.market_tabs)
        
        # Refresh button
        refresh_btn = QPushButton("Refresh Market Data")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 3px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        refresh_btn.clicked.connect(self.refresh_market_data)
        layout.addWidget(refresh_btn)
        
        # Back button
        back_btn = QPushButton("Back to Main Menu")
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 3px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
        """)
        back_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        layout.addWidget(back_btn)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)
        
    def create_data_operations(self):
        """Create the data operations page with proper error handling."""
        try:
            # Create data operations page
            data_page = QWidget()
            layout = QVBoxLayout(data_page)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(15)
            
            # Add header with back button
            header_layout = QHBoxLayout()
            
            back_button = QPushButton("← Back to Menu")
            back_button.setStyleSheet("""
                QPushButton {
                    background-color: #2b2b2b;
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #3daee9;
                }
            """)
            back_button.clicked.connect(self.show_main_menu)
            header_layout.addWidget(back_button)
            
            title_label = QLabel("Data Operations")
            title_label.setStyleSheet("""
                QLabel {
                    color: white;
                    font-size: 24px;
                    font-weight: bold;
                }
            """)
            title_label.setAlignment(Qt.AlignCenter)
            header_layout.addWidget(title_label)
            
            # Add stretch to push title to center
            header_layout.addStretch()
            layout.addLayout(header_layout)
            
            # Create operations grid
            operations_grid = QGridLayout()
            operations_grid.setSpacing(15)
            
            # Export data button
            export_button = QPushButton("Export Portfolio Data")
            export_button.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 15px;
                    font-size: 16px;
                    min-width: 200px;
                }
                QPushButton:hover {
                    background-color: #219a52;
                }
            """)
            export_button.clicked.connect(self.export_portfolio_data)
            operations_grid.addWidget(export_button, 0, 0)
            
            # Import data button
            import_button = QPushButton("Import Portfolio Data")
            import_button.setStyleSheet("""
                QPushButton {
                    background-color: #2980b9;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 15px;
                    font-size: 16px;
                    min-width: 200px;
                }
                QPushButton:hover {
                    background-color: #2471a3;
                }
            """)
            import_button.clicked.connect(self.import_portfolio_data)
            operations_grid.addWidget(import_button, 0, 1)
            
            # Create backup button
            backup_button = QPushButton("Create Backup")
            backup_button.setStyleSheet("""
                QPushButton {
                    background-color: #8e44ad;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 15px;
                    font-size: 16px;
                    min-width: 200px;
                }
                QPushButton:hover {
                    background-color: #7d3c98;
                }
            """)
            backup_button.clicked.connect(self.create_backup)
            operations_grid.addWidget(backup_button, 1, 0)
            
            # Restore backup button
            restore_button = QPushButton("Restore from Backup")
            restore_button.setStyleSheet("""
                QPushButton {
                    background-color: #d35400;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 15px;
                    font-size: 16px;
                    min-width: 200px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
            """)
            restore_button.clicked.connect(self.restore_from_backup)
            operations_grid.addWidget(restore_button, 1, 1)
            
            # Clear data button
            clear_button = QPushButton("Clear All Data")
            clear_button.setStyleSheet("""
                QPushButton {
                    background-color: #c0392b;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 15px;
                    font-size: 16px;
                    min-width: 200px;
                }
                QPushButton:hover {
                    background-color: #a93226;
                }
            """)
            clear_button.clicked.connect(self.clear_all_data)
            operations_grid.addWidget(clear_button, 2, 0, 1, 2)
            
            layout.addLayout(operations_grid)
            
            # Add status label
            self.data_ops_status = QLabel("")
            self.data_ops_status.setStyleSheet("""
                QLabel {
                    color: white;
                    font-size: 14px;
                    padding: 10px;
                    border-radius: 5px;
                }
            """)
            self.data_ops_status.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.data_ops_status)
            
            # Add page to stacked widget
            self.stacked_widget.addWidget(data_page)
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error creating data operations page: {str(e)}")
            raise
            
    def show_data_operations(self):
        """Show the data operations page."""
        try:
            self.stacked_widget.setCurrentIndex(9)
            self.data_ops_status.setText("")
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error showing data operations: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to show data operations: {str(e)}")
            
    def export_portfolio_data(self):
        """Export portfolio data to a JSON file."""
        try:
            # Get save file path
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Portfolio Data",
                "",
                "JSON Files (*.json);;All Files (*)"
            )
            
            if not file_path:
                return
                
            # Create backup of current file
            backup_path = f"{file_path}.backup"
            if os.path.exists(file_path):
                shutil.copy2(file_path, backup_path)
                
            # Export data
            with open(file_path, 'w') as f:
                json.dump(self.portfolios, f, indent=4)
                
            self.data_ops_status.setText("Portfolio data exported successfully")
            self.data_ops_status.setStyleSheet("""
                QLabel {
                    color: white;
                    background-color: #27ae60;
                    font-size: 14px;
                    padding: 10px;
                    border-radius: 5px;
                }
            """)
            
            self.log_audit_entry("INFO", "", "", "Portfolio data exported successfully")
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error exporting portfolio data: {str(e)}")
            self.data_ops_status.setText(f"Error exporting portfolio data: {str(e)}")
            self.data_ops_status.setStyleSheet("""
                QLabel {
                    color: white;
                    background-color: #c0392b;
                    font-size: 14px;
                    padding: 10px;
                    border-radius: 5px;
                }
            """)
            QMessageBox.warning(self, "Error", f"Failed to export portfolio data: {str(e)}")
            
    def import_portfolio_data(self):
        """Import portfolio data from a JSON file."""
        try:
            # Get file path
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Import Portfolio Data",
                "",
                "JSON Files (*.json);;All Files (*)"
            )
            
            if not file_path:
                return
                
            # Confirm import
            reply = QMessageBox.question(
                self,
                "Confirm Import",
                "This will replace all current portfolio data. Are you sure?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.No:
                return
                
            # Create backup of current data
            backup_path = "Portfolios.json.backup"
            if os.path.exists("Portfolios.json"):
                shutil.copy2("Portfolios.json", backup_path)
                
            # Import data
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            # Validate data structure
            if not isinstance(data, dict):
                raise ValueError("Invalid data structure: expected dictionary")
                
            # Update portfolios
            self.portfolios = data
            
            # Save data
            self.save_data()
            
            self.data_ops_status.setText("Portfolio data imported successfully")
            self.data_ops_status.setStyleSheet("""
                QLabel {
                    color: white;
                    background-color: #27ae60;
                    font-size: 14px;
                    padding: 10px;
                    border-radius: 5px;
                }
            """)
            
            self.log_audit_entry("INFO", "", "", "Portfolio data imported successfully")
            
            # Refresh UI
            self.refresh_all_tables()
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error importing portfolio data: {str(e)}")
            self.data_ops_status.setText(f"Error importing portfolio data: {str(e)}")
            self.data_ops_status.setStyleSheet("""
                QLabel {
                    color: white;
                    background-color: #c0392b;
                    font-size: 14px;
                    padding: 10px;
                    border-radius: 5px;
                }
            """)
            QMessageBox.warning(self, "Error", f"Failed to import portfolio data: {str(e)}")
            
    def create_backup(self):
        """Create a backup of the portfolio data."""
        try:
            # Get backup file path
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            default_path = f"Portfolios_{timestamp}.json"
            
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Create Backup",
                default_path,
                "JSON Files (*.json);;All Files (*)"
            )
            
            if not file_path:
                return
                
            # Create backup
            shutil.copy2("Portfolios.json", file_path)
            
            self.data_ops_status.setText("Backup created successfully")
            self.data_ops_status.setStyleSheet("""
                QLabel {
                    color: white;
                    background-color: #27ae60;
                    font-size: 14px;
                    padding: 10px;
                    border-radius: 5px;
                }
            """)
            
            self.log_audit_entry("INFO", "", "", f"Backup created: {file_path}")
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error creating backup: {str(e)}")
            self.data_ops_status.setText(f"Error creating backup: {str(e)}")
            self.data_ops_status.setStyleSheet("""
                QLabel {
                    color: white;
                    background-color: #c0392b;
                    font-size: 14px;
                    padding: 10px;
                    border-radius: 5px;
                }
            """)
            QMessageBox.warning(self, "Error", f"Failed to create backup: {str(e)}")
            
    def restore_from_backup(self):
        """Restore portfolio data from a backup file."""
        try:
            # Get backup file path
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Restore from Backup",
                "",
                "JSON Files (*.json);;All Files (*)"
            )
            
            if not file_path:
                return
                
            # Confirm restore
            reply = QMessageBox.question(
                self,
                "Confirm Restore",
                "This will replace all current portfolio data. Are you sure?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.No:
                return
                
            # Create backup of current data
            backup_path = "Portfolios.json.backup"
            if os.path.exists("Portfolios.json"):
                shutil.copy2("Portfolios.json", backup_path)
                
            # Restore data
            shutil.copy2(file_path, "Portfolios.json")
            
            # Reload data
            self.load_data()
            
            self.data_ops_status.setText("Portfolio data restored successfully")
            self.data_ops_status.setStyleSheet("""
                QLabel {
                    color: white;
                    background-color: #27ae60;
                    font-size: 14px;
                    padding: 10px;
                    border-radius: 5px;
                }
            """)
            
            self.log_audit_entry("INFO", "", "", f"Portfolio data restored from: {file_path}")
            
            # Refresh UI
            self.refresh_all_tables()
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error restoring from backup: {str(e)}")
            self.data_ops_status.setText(f"Error restoring from backup: {str(e)}")
            self.data_ops_status.setStyleSheet("""
                QLabel {
                    color: white;
                    background-color: #c0392b;
                    font-size: 14px;
                    padding: 10px;
                    border-radius: 5px;
                }
            """)
            QMessageBox.warning(self, "Error", f"Failed to restore from backup: {str(e)}")
            
    def clear_all_data(self):
        """Clear all portfolio data."""
        try:
            # Confirm clear
            reply = QMessageBox.question(
                self,
                "Confirm Clear Data",
                "This will delete all portfolio data. This action cannot be undone. Are you sure?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.No:
                return
                
            # Create backup
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = f"Portfolios_{timestamp}_before_clear.json"
            if os.path.exists("Portfolios.json"):
                shutil.copy2("Portfolios.json", backup_path)
                
            # Clear data
            self.portfolios = {}
            self.save_data()
            
            self.data_ops_status.setText("All portfolio data cleared successfully")
            self.data_ops_status.setStyleSheet("""
                QLabel {
                    color: white;
                    background-color: #27ae60;
                    font-size: 14px;
                    padding: 10px;
                    border-radius: 5px;
                }
            """)
            
            self.log_audit_entry("INFO", "", "", "All portfolio data cleared")
            
            # Refresh UI
            self.refresh_all_tables()
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error clearing portfolio data: {str(e)}")
            self.data_ops_status.setText(f"Error clearing portfolio data: {str(e)}")
            self.data_ops_status.setStyleSheet("""
                QLabel {
                    color: white;
                    background-color: #c0392b;
                    font-size: 14px;
                    padding: 10px;
                    border-radius: 5px;
                }
            """)
            QMessageBox.warning(self, "Error", f"Failed to clear portfolio data: {str(e)}")
            
    def refresh_all_tables(self):
        """Refresh all tables in the application."""
        try:
            self.refresh_stock_table()
            self.refresh_fund_table()
            self.refresh_dashboard()
            self.refresh_audit_log()
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error refreshing tables: {str(e)}")
            print(f"Error refreshing tables: {str(e)}")

    def create_audit_history(self):
        """Create the audit history page with proper error handling."""
        try:
            # Create audit history page
            audit_page = QWidget()
            layout = QVBoxLayout(audit_page)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(15)
            
            # Add header with back button
            header_layout = QHBoxLayout()
            
            back_button = QPushButton("← Back to Menu")
            back_button.setStyleSheet("""
                QPushButton {
                    background-color: #2b2b2b;
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #3daee9;
                }
            """)
            back_button.clicked.connect(self.show_main_menu)
            header_layout.addWidget(back_button)
            
            title_label = QLabel("Audit History")
            title_label.setStyleSheet("""
                QLabel {
                    color: white;
                    font-size: 24px;
                    font-weight: bold;
                }
            """)
            title_label.setAlignment(Qt.AlignCenter)
            header_layout.addWidget(title_label)
            
            # Add stretch to push title to center
            header_layout.addStretch()
            layout.addLayout(header_layout)
            
            # Create filter section
            filter_layout = QHBoxLayout()
            
            # Action type filter
            action_label = QLabel("Action Type:")
            action_label.setStyleSheet("color: white; font-size: 14px;")
            filter_layout.addWidget(action_label)
            
            self.audit_action_combo = QComboBox()
            self.audit_action_combo.setStyleSheet("""
                QComboBox {
                    background-color: #2b2b2b;
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 5px;
                    min-width: 150px;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox::down-arrow {
                    image: url(down_arrow.png);
                    width: 12px;
                    height: 12px;
                }
                QComboBox QAbstractItemView {
                    background-color: #2b2b2b;
                    color: white;
                    selection-background-color: #3daee9;
                }
            """)
            self.audit_action_combo.addItem("All Actions")
            self.audit_action_combo.addItems([
                "ADD_STOCK", "MODIFY_STOCK", "DELETE_STOCK",
                "ADD_FUND", "MODIFY_FUND", "DELETE_FUND",
                "ADD_PORTFOLIO", "MODIFY_PORTFOLIO", "DELETE_PORTFOLIO",
                "IMPORT_DATA", "EXPORT_DATA", "CREATE_BACKUP", "RESTORE_BACKUP",
                "CLEAR_DATA", "ERROR", "INFO", "WARNING"
            ])
            self.audit_action_combo.currentTextChanged.connect(self.refresh_audit_log)
            filter_layout.addWidget(self.audit_action_combo)
            
            # Portfolio filter
            portfolio_label = QLabel("Portfolio:")
            portfolio_label.setStyleSheet("color: white; font-size: 14px;")
            filter_layout.addWidget(portfolio_label)
            
            self.audit_portfolio_combo = QComboBox()
            self.audit_portfolio_combo.setStyleSheet("""
                QComboBox {
                    background-color: #2b2b2b;
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 5px;
                    min-width: 150px;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox::down-arrow {
                    image: url(down_arrow.png);
                    width: 12px;
                    height: 12px;
                }
                QComboBox QAbstractItemView {
                    background-color: #2b2b2b;
                    color: white;
                    selection-background-color: #3daee9;
                }
            """)
            self.audit_portfolio_combo.addItem("All Portfolios")
            self.audit_portfolio_combo.currentTextChanged.connect(self.refresh_audit_log)
            filter_layout.addWidget(self.audit_portfolio_combo)
            
            # Date range filter
            date_label = QLabel("Date Range:")
            date_label.setStyleSheet("color: white; font-size: 14px;")
            filter_layout.addWidget(date_label)
            
            self.audit_date_from = QDateEdit()
            self.audit_date_from.setStyleSheet("""
                QDateEdit {
                    background-color: #2b2b2b;
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 5px;
                    min-width: 120px;
                }
                QDateEdit::drop-down {
                    border: none;
                }
                QDateEdit::down-arrow {
                    image: url(down_arrow.png);
                    width: 12px;
                    height: 12px;
                }
            """)
            self.audit_date_from.setCalendarPopup(True)
            self.audit_date_from.setDate(QDate.currentDate().addDays(-30))
            self.audit_date_from.dateChanged.connect(self.refresh_audit_log)
            filter_layout.addWidget(self.audit_date_from)
            
            to_label = QLabel("to")
            to_label.setStyleSheet("color: white; font-size: 14px;")
            filter_layout.addWidget(to_label)
            
            self.audit_date_to = QDateEdit()
            self.audit_date_to.setStyleSheet("""
                QDateEdit {
                    background-color: #2b2b2b;
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 5px;
                    min-width: 120px;
                }
                QDateEdit::drop-down {
                    border: none;
                }
                QDateEdit::down-arrow {
                    image: url(down_arrow.png);
                    width: 12px;
                    height: 12px;
                }
            """)
            self.audit_date_to.setCalendarPopup(True)
            self.audit_date_to.setDate(QDate.currentDate())
            self.audit_date_to.dateChanged.connect(self.refresh_audit_log)
            filter_layout.addWidget(self.audit_date_to)
            
            # Clear filters button
            clear_button = QPushButton("Clear Filters")
            clear_button.setStyleSheet("""
                QPushButton {
                    background-color: #2b2b2b;
                    color: white;
                    border: 2px solid #3daee9;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #3daee9;
                }
            """)
            clear_button.clicked.connect(self.clear_audit_filter)
            filter_layout.addWidget(clear_button)
            
            layout.addLayout(filter_layout)
            
            # Create audit log table
            self.audit_table = QTableWidget()
            self.audit_table.setStyleSheet("""
                QTableWidget {
                    background-color: #2b2b2b;
                    color: white;
                    gridline-color: #3daee9;
                    border: none;
                }
                QTableWidget::item {
                    padding: 5px;
                }
                QTableWidget::item:selected {
                    background-color: #3daee9;
                }
                QHeaderView::section {
                    background-color: #2b2b2b;
                    color: white;
                    padding: 5px;
                    border: 1px solid #3daee9;
                }
            """)
            
            # Set up table columns
            columns = [
                "Timestamp", "Action", "Portfolio", "Symbol/ISIN", "Details"
            ]
            self.audit_table.setColumnCount(len(columns))
            self.audit_table.setHorizontalHeaderLabels(columns)
            
            # Set column widths
            self.audit_table.setColumnWidth(0, 150)  # Timestamp
            self.audit_table.setColumnWidth(1, 150)  # Action
            self.audit_table.setColumnWidth(2, 150)  # Portfolio
            self.audit_table.setColumnWidth(3, 150)  # Symbol/ISIN
            self.audit_table.setColumnWidth(4, 400)  # Details
            
            # Enable sorting
            self.audit_table.setSortingEnabled(True)
            
            # Enable selection
            self.audit_table.setSelectionBehavior(QTableWidget.SelectRows)
            self.audit_table.setSelectionMode(QTableWidget.SingleSelection)
            
            layout.addWidget(self.audit_table)
            
            # Add export button
            export_button = QPushButton("Export Audit Log")
            export_button.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #219a52;
                }
            """)
            export_button.clicked.connect(self.export_audit_log)
            layout.addWidget(export_button)
            
            # Add page to stacked widget
            self.stacked_widget.addWidget(audit_page)
            
            # Initial refresh
            self.refresh_audit_log()
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error creating audit history page: {str(e)}")
            raise
            
    def show_audit_history(self):
        """Show the audit history page."""
        try:
            self.stacked_widget.setCurrentIndex(10)
            self.refresh_audit_log()
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error showing audit history: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to show audit history: {str(e)}")
            
    def clear_audit_filter(self):
        """Clear all audit log filters."""
        try:
            self.audit_action_combo.setCurrentText("All Actions")
            self.audit_portfolio_combo.setCurrentText("All Portfolios")
            self.audit_date_from.setDate(QDate.currentDate().addDays(-30))
            self.audit_date_to.setDate(QDate.currentDate())
            self.refresh_audit_log()
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error clearing audit filters: {str(e)}")
            print(f"Error clearing audit filters: {str(e)}")
            
    def refresh_audit_log(self):
        """Refresh the audit log table with proper error handling."""
        try:
            # Get filter values
            action_filter = self.audit_action_combo.currentText()
            portfolio_filter = self.audit_portfolio_combo.currentText()
            date_from = self.audit_date_from.date().toPyDate()
            date_to = self.audit_date_to.date().toPyDate()
            
            # Clear table
            self.audit_table.setRowCount(0)
            
            # Update portfolio combo box
            self.audit_portfolio_combo.clear()
            self.audit_portfolio_combo.addItem("All Portfolios")
            self.audit_portfolio_combo.addItems(sorted(self.portfolios.keys()))
            if portfolio_filter != "All Portfolios":
                self.audit_portfolio_combo.setCurrentText(portfolio_filter)
                
            # Load audit log
            try:
                with open("audit_log.json", 'r') as f:
                    audit_log = json.load(f)
            except FileNotFoundError:
                audit_log = []
            except json.JSONDecodeError:
                self.log_audit_entry("ERROR", "", "", "Invalid audit log file format")
                audit_log = []
                
            # Filter and sort entries
            filtered_entries = []
            for entry in audit_log:
                try:
                    # Parse timestamp
                    timestamp = datetime.strptime(entry.get('timestamp', ''), '%Y-%m-%d %H:%M:%S')
                    entry_date = timestamp.date()
                    
                    # Apply filters
                    if action_filter != "All Actions" and entry.get('action') != action_filter:
                        continue
                    if portfolio_filter != "All Portfolios" and entry.get('portfolio') != portfolio_filter:
                        continue
                    if not (date_from <= entry_date <= date_to):
                        continue
                        
                    filtered_entries.append(entry)
                    
                except ValueError as e:
                    print(f"Error parsing timestamp in audit log: {str(e)}")
                    continue
                    
            # Sort entries by timestamp (newest first)
            filtered_entries.sort(
                key=lambda x: datetime.strptime(x.get('timestamp', ''), '%Y-%m-%d %H:%M:%S'),
                reverse=True
            )
            
            # Add entries to table
            for entry in filtered_entries:
                try:
                    row = self.audit_table.rowCount()
                    self.audit_table.insertRow(row)
                    
                    # Add items to the table
                    items = [
                        entry.get('timestamp', ''),
                        entry.get('action', ''),
                        entry.get('portfolio', ''),
                        entry.get('symbol', ''),
                        entry.get('details', '')
                    ]
                    
                    for col, text in enumerate(items):
                        item = QTableWidgetItem(text)
                        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        
                        # Color action types
                        if col == 1:  # Action column
                            action = text.upper()
                            if action in ['ERROR', 'DELETE_STOCK', 'DELETE_FUND', 'DELETE_PORTFOLIO', 'CLEAR_DATA']:
                                item.setForeground(QColor('#f44336'))  # Red
                            elif action in ['WARNING', 'MODIFY_STOCK', 'MODIFY_FUND', 'MODIFY_PORTFOLIO']:
                                item.setForeground(QColor('#FFC107'))  # Yellow
                            elif action in ['INFO', 'ADD_STOCK', 'ADD_FUND', 'ADD_PORTFOLIO']:
                                item.setForeground(QColor('#4CAF50'))  # Green
                            else:
                                item.setForeground(QColor('#2196F3'))  # Blue
                                
                        self.audit_table.setItem(row, col, item)
                        
                except Exception as e:
                    print(f"Error adding audit entry to table: {str(e)}")
                    continue
                    
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error refreshing audit log: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to refresh audit log: {str(e)}")
            
    def export_audit_log(self):
        """Export the audit log to a CSV file."""
        try:
            # Get save file path
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Audit Log",
                "",
                "CSV Files (*.csv);;All Files (*)"
            )
            
            if not file_path:
                return
                
            # Get filter values
            action_filter = self.audit_action_combo.currentText()
            portfolio_filter = self.audit_portfolio_combo.currentText()
            date_from = self.audit_date_from.date().toPyDate()
            date_to = self.audit_date_to.date().toPyDate()
            
            # Load audit log
            try:
                with open("audit_log.json", 'r') as f:
                    audit_log = json.load(f)
            except FileNotFoundError:
                audit_log = []
            except json.JSONDecodeError:
                self.log_audit_entry("ERROR", "", "", "Invalid audit log file format")
                audit_log = []
                
            # Filter entries
            filtered_entries = []
            for entry in audit_log:
                try:
                    # Parse timestamp
                    timestamp = datetime.strptime(entry.get('timestamp', ''), '%Y-%m-%d %H:%M:%S')
                    entry_date = timestamp.date()
                    
                    # Apply filters
                    if action_filter != "All Actions" and entry.get('action') != action_filter:
                        continue
                    if portfolio_filter != "All Portfolios" and entry.get('portfolio') != portfolio_filter:
                        continue
                    if not (date_from <= entry_date <= date_to):
                        continue
                        
                    filtered_entries.append(entry)
                    
                except ValueError as e:
                    print(f"Error parsing timestamp in audit log: {str(e)}")
                    continue
                    
            # Sort entries by timestamp (newest first)
            filtered_entries.sort(
                key=lambda x: datetime.strptime(x.get('timestamp', ''), '%Y-%m-%d %H:%M:%S'),
                reverse=True
            )
            
            # Export to CSV
            with open(file_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Timestamp', 'Action', 'Portfolio', 'Symbol/ISIN', 'Details'])
                
                for entry in filtered_entries:
                    writer.writerow([
                        entry.get('timestamp', ''),
                        entry.get('action', ''),
                        entry.get('portfolio', ''),
                        entry.get('symbol', ''),
                        entry.get('details', '')
                    ])
                    
            QMessageBox.information(
                self,
                "Success",
                "Audit log exported successfully",
                QMessageBox.Ok
            )
            
            self.log_audit_entry("INFO", "", "", f"Audit log exported to: {file_path}")
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error exporting audit log: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to export audit log: {str(e)}")

    def update_performance_chart(self, portfolio_name: str):
        """Update the performance chart for a portfolio"""
        if not hasattr(self, 'performance_chart'):
            return
            
        portfolio = self.portfolios[portfolio_name]
        
        # Get historical data for stocks
        dates = []
        values = []
        
        # For now, just plot current values
        current_date = datetime.now()
        current_value = 0
        
        # Add stock values
        for stock in portfolio.get('stocks', []):
            try:
                if 'current_price' in stock:
                    value = stock['current_price'] * stock['quantity']
                    current_value += value
            except Exception as e:
                print(f"Error calculating stock value: {str(e)}")
                
        # Add mutual fund values
        for fund in portfolio.get('mutual_funds', []):
            try:
                if 'current_nav' in fund:
                    value = fund['current_nav'] * fund['units']
                    current_value += value
            except Exception as e:
                print(f"Error calculating fund value: {str(e)}")
                
        dates.append(current_date)
        values.append(current_value)
        
        # Plot the data
        ax = self.performance_chart.figure.subplots()
        ax.clear()
        ax.plot(dates, values, 'b-', linewidth=2)
        
        # Style the chart
        ax.set_facecolor('#2D2D2D')
        ax.grid(True, color='#333')
        ax.set_title('Portfolio Performance', color='white')
        ax.set_xlabel('Date', color='white')
        ax.set_ylabel('Value (₹)', color='white')
        
        # Format y-axis as currency
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f'₹{x:,.0f}'))
        
        # Rotate x-axis labels
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
        
        # Adjust layout
        self.performance_chart.figure.tight_layout()
        self.performance_chart.draw()

    def update_allocation_charts(self, portfolio_name: str):
        """Update the allocation charts for a portfolio"""
        if not hasattr(self, 'asset_pie_chart') or not hasattr(self, 'sector_pie_chart'):
            return
            
        portfolio = self.portfolios[portfolio_name]
        
        # Calculate asset allocation
        asset_values = {
            'Stocks': 0,
            'Mutual Funds': 0
        }
        
        # Add stock values
        for stock in portfolio.get('stocks', []):
            try:
                if 'current_price' in stock:
                    value = stock['current_price'] * stock['quantity']
                    asset_values['Stocks'] += value
            except Exception as e:
                print(f"Error calculating stock value: {str(e)}")
                
        # Add mutual fund values
        for fund in portfolio.get('mutual_funds', []):
            try:
                if 'current_nav' in fund:
                    value = fund['current_nav'] * fund['units']
                    asset_values['Mutual Funds'] += value
            except Exception as e:
                print(f"Error calculating fund value: {str(e)}")
                
        # Calculate sector allocation (stocks only)
        sector_values = {}
        for stock in portfolio.get('stocks', []):
            try:
                if 'current_price' in stock and 'sector' in stock:
                    value = stock['current_price'] * stock['quantity']
                    sector = stock['sector']
                    sector_values[sector] = sector_values.get(sector, 0) + value
            except Exception as e:
                print(f"Error calculating sector value: {str(e)}")
                
        # Plot asset allocation
        ax1 = self.asset_pie_chart.figure.subplots()
        ax1.clear()
        
        if sum(asset_values.values()) > 0:
            ax1.pie(
                asset_values.values(),
                labels=asset_values.keys(),
                autopct='%1.1f%%',
                colors=['#4CAF50', '#2196F3']
            )
            ax1.set_title('Asset Allocation', color='white')
        else:
            ax1.text(0.5, 0.5, 'No Data', ha='center', va='center', color='white')
            
        # Plot sector allocation
        ax2 = self.sector_pie_chart.figure.subplots()
        ax2.clear()
        
        if sector_values:
            ax2.pie(
                sector_values.values(),
                labels=sector_values.keys(),
                autopct='%1.1f%%',
                colors=plt.cm.Set3.colors
            )
            ax2.set_title('Sector Allocation', color='white')
        else:
            ax2.text(0.5, 0.5, 'No Data', ha='center', va='center', color='white')
            
        # Adjust layout
        self.asset_pie_chart.figure.tight_layout()
        self.sector_pie_chart.figure.tight_layout()
        
        # Redraw
        self.asset_pie_chart.draw()
        self.sector_pie_chart.draw()

    def show_market_analysis(self):
        """Show the market analysis page."""
        try:
            # The market analysis page is added last before data operations and audit history, so its index is likely 6 (0-based)
            # But to be robust, let's find it by looking for the QTabWidget with self.market_tabs
            for i in range(self.stacked_widget.count()):
                widget = self.stacked_widget.widget(i)
                if hasattr(self, 'market_tabs') and hasattr(widget, 'layout'):
                    layout = widget.layout()
                    for j in range(layout.count()):
                        item = layout.itemAt(j)
                        if item and hasattr(item.widget(), 'objectName'):
                            if item.widget() is self.market_tabs:
                                self.stacked_widget.setCurrentIndex(i)
                                self.refresh_market_data()
                                return
            # Fallback: just set to index 6 (if not found)
            if self.stacked_widget.count() > 6:
                self.stacked_widget.setCurrentIndex(6)
                self.refresh_market_data()
            else:
                self.log_audit_entry("ERROR", "", "", "Market analysis page not found in stacked widget")
                QMessageBox.warning(self, "Error", "Failed to show market analysis: Page not found")
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error showing market analysis: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to show market analysis: {str(e)}")

    def update_stock_table(self, portfolio_name):
        """Update the stock table with current portfolio data."""
        try:
            self.stock_table.setRowCount(0)  # Clear existing rows
            if portfolio_name not in self.portfolios:
                return

            portfolio = self.portfolios[portfolio_name]
            if 'stocks' not in portfolio:
                return

            for stock in portfolio['stocks']:
                row_position = self.stock_table.rowCount()
                self.stock_table.insertRow(row_position)

                # Get values with proper error handling
                name = stock.get('name', 'N/A')
                ticker = stock.get('ticker', 'N/A')
                quantity = float(stock.get('quantity', 0))
                avg_price = float(stock.get('average_price', 0))
                current_price = float(stock.get('current_price', 0))
                current_value = float(stock.get('current_value', 0))
                pl_amount = float(stock.get('pl_amount', 0))
                pl_percent = float(stock.get('pl_percent', 0))

                # Format numbers for display
                quantity_str = f"{quantity:,.0f}"
                avg_price_str = f"₹{avg_price:,.2f}"
                current_price_str = f"₹{current_price:,.2f}"
                current_value_str = f"₹{current_value:,.2f}"
                pl_amount_str = f"₹{pl_amount:,.2f}"
                pl_percent_str = f"{pl_percent:,.2f}%"

                # Set items in the table
                self.stock_table.setItem(row_position, 0, QTableWidgetItem(name))
                self.stock_table.setItem(row_position, 1, QTableWidgetItem(ticker))
                self.stock_table.setItem(row_position, 2, QTableWidgetItem(quantity_str))
                self.stock_table.setItem(row_position, 3, QTableWidgetItem(avg_price_str))
                self.stock_table.setItem(row_position, 4, QTableWidgetItem(current_price_str))
                self.stock_table.setItem(row_position, 5, QTableWidgetItem(current_value_str))
                self.stock_table.setItem(row_position, 6, QTableWidgetItem(pl_amount_str))
                self.stock_table.setItem(row_position, 7, QTableWidgetItem(pl_percent_str))

                # Color the P/L cells based on profit/loss
                if pl_amount > 0:
                    self.stock_table.item(row_position, 6).setForeground(QColor('green'))
                    self.stock_table.item(row_position, 7).setForeground(QColor('green'))
                elif pl_amount < 0:
                    self.stock_table.item(row_position, 6).setForeground(QColor('red'))
                    self.stock_table.item(row_position, 7).setForeground(QColor('red'))

            # Resize columns to content
            self.stock_table.resizeColumnsToContents()
            
        except Exception as e:
            self.log_audit_entry("ERROR", "", "", f"Error updating stock table: {str(e)}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = PortfolioTracker()
    window.show()
    sys.exit(app.exec_()) 