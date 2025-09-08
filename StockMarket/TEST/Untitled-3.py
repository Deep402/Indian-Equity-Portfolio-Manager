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
                            QTabWidget, QSizePolicy, QFrame, QHeaderView, QTextEdit)
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
    
    def __init__(self, tickers, parent=None):
        super().__init__(parent)
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
        
    def stop(self):
        self.quit()
        self.wait()

class MarketDataWorker(QThread):
    data_fetched = pyqtSignal(dict)
    
    def __init__(self, indices, parent=None):
        super().__init__(parent)
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
        
    def stop(self):
        self.quit()
        self.wait()
        
    def is_market_open(self, ticker):
        now = datetime.now()
        if '^NSE' in ticker:  # Indian market
            return (now.weekday() < 5 and 
                    9 <= now.hour < 15 or 
                    (now.hour == 15 and now.minute <= 30))
        else:  # US market
            return (now.weekday() < 5 and 
                    9 <= (now.hour - 4) < 16)  # Adjusting for timezone


        
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
        self.setWindowTitle("Portfolio Tracker - Bloomberg Terminal Style")
        self.setGeometry(100, 100, 1400, 900)
        self.portfolios = {}
        self.workers = []  # Add this line to track active workers
        self.load_data()
        self.init_ui()
        self.set_dark_theme()
        
    def start_worker(self, worker):
        self.workers.append(worker)
        worker.finished.connect(lambda: self.worker_finished(worker))
        worker.start()
        
    def worker_finished(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)
        worker.deleteLater()
        
    def stop_all_workers(self):
        for worker in self.workers[:]:  # Create a copy of the list
            worker.stop()
        self.workers.clear()
    
        
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
        
        self.stacked_widget.setCurrentIndex(0)
        
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
                font-family: 'Consolas', 'Monaco', monospace;
            }
            QLabel, QPushButton, QListWidget, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit {
                color: #E0E0E0;
                font-size: 12px;
            }
            QPushButton {
                background-color: #1A1B26;
                border: 1px solid #333;
                padding: 8px 12px;
                border-radius: 2px;
                min-width: 120px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #2A2B36;
            }
            QPushButton:pressed {
                background-color: #3A3B46;
            }
            QListWidget {
                background-color: #1E1E1E;
                border: 1px solid #333;
                border-radius: 2px;
                padding: 5px;
            }
            QTableWidget {
                background-color: #1E1E1E;
                gridline-color: #333;
                border: 1px solid #333;
                border-radius: 2px;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #1A1B26;
                color: #E0E0E0;
                padding: 6px;
                border: none;
                font-weight: bold;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {
                background-color: #1E1E1E;
                border: 1px solid #333;
                padding: 5px;
                border-radius: 2px;
                min-height: 30px;
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
        ]
        
        self.menu_btns = []
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
            self.menu_btns.append(btn)
        
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
        right_content.setStyleSheet("background-color: #121212;")
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
        self.workers.append(worker)  # Add worker to tracking list
        worker.data_fetched.connect(
            lambda prices: self.update_stock_table_with_prices(portfolio, prices)
        )
        worker.finished.connect(lambda: self.worker_finished(worker))  # Clean up when done
        worker.start()
        
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
                
                daily_item = QTableWidgetItem("Fetching...")
                self.stock_table.setItem(row, 6, daily_item)
                
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
        self.portfolio_table.setColumnCount(6)
        self.portfolio_table.setHorizontalHeaderLabels([
            "Portfolio", "Invested", "Current", "P/L", "Daily P/L", "Status"
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
        
        self.update_summary_card(self.individual_investment_card, "Invested", f"₹{investment:,.2f}", "#1E88E5")
        self.update_summary_card(self.individual_current_card, "Current", f"₹{current:,.2f}", "#43A047")
        
        pl_color = '#4CAF50' if pl >= 0 else '#F44336'
        pl_text = f"₹{pl:+,.2f}\n({pl/investment*100:.2f}%)" if investment else "₹0.00"
        self.update_summary_card(self.individual_pl_card, "P/L", pl_text, pl_color)
        
        daily_color = '#4CAF50' if daily_pl >= 0 else '#F44336'
        daily_text = f"₹{daily_pl:+,.2f}\n({daily_pl/current*100:.2f}%)" if current else "₹0.00"
        self.update_summary_card(self.individual_daily_card, "Today's P/L", daily_text, daily_color)
        
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
        
        self.allocation_chart = FigureCanvas(Figure(figsize=(10, 6), tight_layout=True))
        self.chart_tabs.addTab(self.allocation_chart, "Allocation")
        
        self.performance_chart = FigureCanvas(Figure(figsize=(10, 6), tight_layout=True))
        self.chart_tabs.addTab(self.performance_chart, "Performance")
        
        self.sector_chart = FigureCanvas(Figure(figsize=(10, 6), tight_layout=True))
        self.chart_tabs.addTab(self.sector_chart, "Sector Exposure")
        
        self.daily_pl_chart = FigureCanvas(Figure(figsize=(10, 6), tight_layout=True))
        self.chart_tabs.addTab(self.daily_pl_chart, "Today's P/L")
        
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
        if len(df) == 0:
            return
            
        self.plot_allocation_chart(df)
        self.plot_performance_chart(df)
        self.plot_sector_chart(df)
        self.plot_daily_pl_chart(df)
        
    def plot_allocation_chart(self, df):
        fig = self.allocation_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        
        try:
            if 'Current Value' not in df.columns:
                df['Current Value'] = df['Quantity'] * df['Purchase Price']
                
            df = df[df['Quantity'] > 0]
            
            if len(df) == 0:
                ax.text(0.5, 0.5, "No active holdings", 
                    ha='center', va='center', fontsize=12)
            else:
                df = df.dropna(subset=['Current Value'])
                
                if len(df) == 0:
                    ax.text(0.5, 0.5, "No valid data to display", 
                        ha='center', va='center', fontsize=12)
                    fig.tight_layout()
                    self.allocation_chart.draw()
                    return
                    
                df = df.sort_values('Current Value', ascending=False)
                
                colors = plt.cm.tab20c(range(len(df)))
                
                wedges, texts, autotexts = ax.pie(
                    df['Current Value'],
                    labels=df['Stock Name'],
                    autopct=lambda p: f'₹{p * sum(df["Current Value"])/100:,.0f}\n({p:.1f}%)',
                    startangle=90,
                    wedgeprops={'linewidth': 1, 'edgecolor': '#121212'},
                    colors=colors,
                    textprops={'fontsize': 8},
                    pctdistance=0.85,
                    labeldistance=1.05
                )
                
                for text in texts:
                    text.set_color('white')
                    text.set_fontsize(9)
                    text.set_bbox(dict(facecolor='#1E1E1E', alpha=0.7, edgecolor='none'))
                    
                for autotext in autotexts:
                    autotext.set_color('white')
                    autotext.set_fontsize(8)
                
                ax.set_title("Portfolio Allocation", fontsize=14, color='white', pad=20)
                
        except Exception as e:
            print(f"Error plotting allocation chart: {str(e)}")
            ax.text(0.5, 0.5, "Error displaying chart", 
                ha='center', va='center', fontsize=12)
            
        fig.tight_layout()
        self.allocation_chart.draw()

    def plot_daily_pl_chart(self, df):
        fig = self.daily_pl_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        
        try:
            if 'Daily P/L' not in df.columns:
                df['Daily P/L'] = 0.0
                
            df = df[df['Quantity'] > 0]
            
            if len(df) == 0:
                ax.text(0.5, 0.5, "No active holdings", 
                    ha='center', va='center', fontsize=12)
            else:
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
                
                df = df.dropna(subset=['Daily P/L'])
                
                if len(df) == 0:
                    ax.text(0.5, 0.5, "No valid data to display", 
                        ha='center', va='center', fontsize=12)
                    fig.tight_layout()
                    self.daily_pl_chart.draw()
                    return
                    
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
                
                for spine in ax.spines.values():
                    spine.set_color('#333')
                
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
                    
        except Exception as e:
            print(f"Error plotting daily P/L chart: {str(e)}")
            ax.text(0.5, 0.5, "Error displaying chart", 
                ha='center', va='center', fontsize=12)
            
        fig.tight_layout()
        self.daily_pl_chart.draw()

    def plot_performance_chart(self, df):
        fig = self.performance_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        
        try:
            if 'Profit/Loss' not in df.columns:
                df['Profit/Loss'] = (df['Quantity'] * df['Purchase Price']) - df['Investment Value']
                
            df = df[df['Quantity'] > 0]
            
            if len(df) == 0:
                ax.text(0.5, 0.5, "No active holdings", 
                    ha='center', va='center', fontsize=12)
            else:
                df = df.dropna(subset=['Profit/Loss'])
                
                if len(df) == 0:
                    ax.text(0.5, 0.5, "No valid data to display", 
                        ha='center', va='center', fontsize=12)
                    fig.tight_layout()
                    self.performance_chart.draw()
                    return
                    
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
                ha='center', va='center', fontsize=12)
            
        fig.tight_layout()
        self.performance_chart.draw()
    
    def plot_sector_chart(self, df):
        fig = self.sector_chart.figure
        fig.clear()
        
        ax = fig.add_subplot(111)
        
        try:
            if 'Sector' not in df.columns or df['Sector'].isnull().all():
                ax.text(0.5, 0.5, "No sector data available", 
                    ha='center', va='center', fontsize=12)
                fig.tight_layout()
                self.sector_chart.draw()
                return
                
            if 'Current Value' not in df.columns:
                df['Current Value'] = df['Quantity'] * df['Purchase Price']
                
            df = df[df['Quantity'] > 0]
            
            if len(df) == 0:
                ax.text(0.5, 0.5, "No active holdings", 
                    ha='center', va='center', fontsize=12)
            else:
                df = df.dropna(subset=['Sector', 'Current Value'])
                
                if len(df) == 0:
                    ax.text(0.5, 0.5, "No valid data to display", 
                        ha='center', va='center', fontsize=12)
                    fig.tight_layout()
                    self.sector_chart.draw()
                    return
                    
                sector_data = df.groupby('Sector')['Current Value'].sum().sort_values(ascending=False)
                
                if len(sector_data) == 0:
                    ax.text(0.5, 0.5, "No valid sector data", 
                        ha='center', va='center', fontsize=12)
                    fig.tight_layout()
                    self.sector_chart.draw()
                    return
                    
                colors = plt.cm.tab20c(range(len(sector_data)))
                
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
                
                for spine in ax.spines.values():
                    spine.set_color('#333')
                
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
                    
        except Exception as e:
            print(f"Error plotting sector chart: {str(e)}")
            ax.text(0.5, 0.5, "Error displaying chart", 
                ha='center', va='center', fontsize=12)
            
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
        
        self.indian_market_tab = QWidget()
        self.setup_indian_market_tab()
        self.market_tabs.addTab(self.indian_market_tab, "Indian Indices")
        
        self.global_market_tab = QWidget()
        self.setup_global_market_tab()
        self.market_tabs.addTab(self.global_market_tab, "Global Indices")
        
        layout.addWidget(self.market_tabs)
        
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
        
        self.indian_chart = FigureCanvas(Figure(figsize=(10, 4)))
        layout.addWidget(self.indian_chart)
        
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
        
        self.global_chart = FigureCanvas(Figure(figsize=(10, 4)))
        layout.addWidget(self.global_chart)
        
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
            
            prices.append(index_data['Current'])
            changes.append(index_data['% Change'])
            labels.append(index_name)
        
        self.plot_market_performance(self.global_chart.figure, labels, prices, changes, "Global Market Overview")
        self.global_status_label.setText(f"Global market data updated at {datetime.now().strftime('%H:%M:%S')}")
        
    def plot_market_performance(self, fig, labels, prices, changes, title):
        fig.clear()
        
        ax1 = fig.add_subplot(121)
        ax2 = fig.add_subplot(122)
        
        for ax in [ax1, ax2]:
            ax.set_facecolor('#1E1E1E')
            ax.tick_params(colors='white')
            for spine in ax.spines.values():
                spine.set_color('#333')
        
        colors = ['#1E88E5' if p >= 0 else '#F44336' for p in changes]
        bars1 = ax1.bar(labels, prices, color=colors, width=0.6)
        ax1.set_title("Index Prices", color='white', pad=20)
        ax1.set_ylabel("Price", color='white')
        ax1.tick_params(axis='x', rotation=45)
        
        if prices and prices[0] > 1000:
            ax1.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'${x:,.0f}'))
        else:
            ax1.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'₹{x:,.0f}'))
        
        for bar in bars1:
            height = bar.get_height()
            ax1.text(
                bar.get_x() + bar.get_width()/2.,
                height + (0.01 * height),
                f"{height:,.0f}",
                ha='center', va='center',
                fontsize=8,
                color='white'
            )
        
        colors = ['#4CAF50' if c >= 0 else '#F44336' for c in changes]
        bars2 = ax2.bar(labels, changes, color=colors, width=0.6)
        ax2.set_title("Daily Change", color='white', pad=20)
        ax2.set_ylabel("% Change", color='white')
        ax2.tick_params(axis='x', rotation=45)
        ax2.axhline(0, color='white', linestyle='--', linewidth=1)
        
        for bar in bars2:
            height = bar.get_height()
            ax2.text(
                bar.get_x() + bar.get_width()/2.,
                height + (0.1 if height >=0 else -0.1),
                f"{height:+.1f}%",
                ha='center', va='center',
                fontsize=8,
                color='white'
            )
        
        fig.suptitle(title, fontsize=14, color='white', y=0.98)
        fig.tight_layout()
        fig.canvas.draw()
        
    def create_data_operations(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        title = QLabel("Data Operations")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #64B5F6;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
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
                    if 'metadata' in data and 'stocks' in data:
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
        
        if current_page == 2:
            self.refresh_stock_table()
        elif current_page == 3:
            self.refresh_dashboard_data()
        elif current_page == 4:
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
        self.stop_all_workers()
        self.save_data()
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    font = QFont()
    font.setPointSize(10)
    app.setFont(font)
    
    try:
        app.setWindowIcon(QIcon('stock_icon.png'))
    except:
        pass
    
    window = PortfolioTracker()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()