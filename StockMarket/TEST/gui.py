import sys
import json
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import threading
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QPushButton, QListWidget, QStackedWidget, QLineEdit,
                            QTableWidget, QTableWidgetItem, QComboBox, QSpinBox, 
                            QDoubleSpinBox, QDateEdit, QMessageBox, QFileDialog, QDialog,
                            QTabWidget)
from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

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
            except:
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
                        'Market Hours': '09:15-15:30 IST',
                        'Status': "Open" if self.is_market_open() else "Closed"
                    }
            except Exception as e:
                print(f"Error fetching {name}: {str(e)}")
        
        self.data_fetched.emit(results)
        
    def is_market_open(self):
        now = datetime.now()
        return (now.weekday() < 5 and 
                now.hour >= 9 and 
                not (now.hour == 15 and now.minute > 30))

class PortfolioTracker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stock Portfolio Tracker")
        self.setGeometry(100, 100, 1200, 800)
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
        
    def set_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1A1B26;
            }
            QLabel, QPushButton, QListWidget, QComboBox, QLineEdit {
                color: #E0E0E0;
                font-size: 12px;
            }
            QPushButton {
                background-color: #4361EE;
                border: 1px solid #3A86FF;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #3A86FF;
            }
            QTableWidget {
                background-color: #0F1017;
                gridline-color: #2D2E3A;
            }
            QHeaderView::section {
                background-color: #1A1B26;
                color: #E0E0E0;
                padding: 5px;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {
                background-color: #0F1017;
                border: 1px solid #2D2E3A;
                padding: 3px;
            }
        """)
        
    def create_main_menu(self):
        page = QWidget()
        layout = QVBoxLayout()
        
        title = QLabel("Stock Portfolio Tracker")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        buttons = [
            ("Portfolio Management", lambda: self.stacked_widget.setCurrentIndex(1)),
            ("Stock Operations", lambda: self.stacked_widget.setCurrentIndex(2)),
            ("Dashboard Views", lambda: self.stacked_widget.setCurrentIndex(3)),
            ("Market Analysis", lambda: self.stacked_widget.setCurrentIndex(4)),
            ("Data Operations", lambda: self.stacked_widget.setCurrentIndex(5)),
            ("Audit & History", lambda: self.stacked_widget.setCurrentIndex(6)),
            ("Exit", self.close)
        ]
        
        for text, command in buttons:
            btn = QPushButton(text)
            btn.clicked.connect(command)
            btn.setMinimumHeight(40)
            layout.addWidget(btn)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)
        
    def create_portfolio_management(self):
        page = QWidget()
        layout = QVBoxLayout()
        
        title = QLabel("Portfolio Management")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        self.portfolio_list = QListWidget()
        self.refresh_portfolio_list()
        layout.addWidget(self.portfolio_list)
        
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
        
    def show_create_portfolio_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Portfolio")
        layout = QVBoxLayout()
        
        name_label = QLabel("Portfolio Name:")
        self.portfolio_name_input = QLineEdit()
        
        btn_layout = QHBoxLayout()
        create_btn = QPushButton("Create")
        create_btn.clicked.connect(lambda: self.create_portfolio(dialog))
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(create_btn)
        btn_layout.addWidget(cancel_btn)
        
        layout.addWidget(name_label)
        layout.addWidget(self.portfolio_name_input)
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
            else:
                QMessageBox.warning(self, "Error", "Portfolio already exists!")
        else:
            QMessageBox.warning(self, "Error", "Portfolio name cannot be empty!")
            
    def refresh_portfolio_list(self):
        self.portfolio_list.clear()
        for portfolio in self.portfolios.keys():
            self.portfolio_list.addItem(portfolio)
            
    def delete_portfolio(self):
        selected = self.portfolio_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "Error", "Please select a portfolio first!")
            return
            
        portfolio = selected.text()
        reply = QMessageBox.question(
            self, "Confirm", 
            f"Are you sure you want to delete {portfolio}?", 
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            del self.portfolios[portfolio]
            self.log_audit("DELETED_PORTFOLIO", portfolio)
            self.refresh_portfolio_list()
            
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
        
        title = QLabel("Stock Operations")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        portfolio_label = QLabel("Select Portfolio:")
        self.portfolio_combo = QComboBox()
        self.portfolio_combo.addItems(self.portfolios.keys())
        self.portfolio_combo.currentTextChanged.connect(self.refresh_stock_table)
        layout.addWidget(portfolio_label)
        layout.addWidget(self.portfolio_combo)
        
        self.stock_table = QTableWidget()
        self.stock_table.setColumnCount(7)
        self.stock_table.setHorizontalHeaderLabels([
            "Stock", "Ticker", "Qty", "Avg Price", "Curr Price", "P/L", "Daily P/L"
        ])
        self.stock_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.stock_table)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Stock")
        add_btn.clicked.connect(self.show_add_stock_dialog)
        modify_btn = QPushButton("Modify Stock")
        modify_btn.clicked.connect(self.show_modify_stock_dialog)
        manage_btn = QPushButton("Manage Shares")
        manage_btn.clicked.connect(self.show_manage_shares_dialog)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(modify_btn)
        btn_layout.addWidget(manage_btn)
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
        df['Profit/Loss'] = df['Current Value'] - df['Investment Value']
        
        for row in range(len(df)):
            stock = df.iloc[row]
            
            self.stock_table.setItem(row, 0, QTableWidgetItem(stock['Stock Name']))
            self.stock_table.setItem(row, 1, QTableWidgetItem(stock['Ticker Symbol']))
            self.stock_table.setItem(row, 2, QTableWidgetItem(str(stock['Quantity'])))
            self.stock_table.setItem(row, 3, QTableWidgetItem(f"{stock['Purchase Price']:.2f}"))
            
            if pd.notna(stock['Current Price']):
                self.stock_table.setItem(row, 4, QTableWidgetItem(f"{stock['Current Price']:.2f}"))
                
                pl_item = QTableWidgetItem(f"{stock['Profit/Loss']:+.2f}")
                pl_item.setForeground(QColor('#4AD66D') if stock['Profit/Loss'] >= 0 else QColor('#EF233C'))
                self.stock_table.setItem(row, 5, pl_item)
                
                # Daily P/L would need previous close data
                self.stock_table.setItem(row, 6, QTableWidgetItem("N/A"))
            else:
                for col in range(4, 7):
                    self.stock_table.setItem(row, col, QTableWidgetItem("N/A"))
                    
    def show_add_stock_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Stock")
        layout = QVBoxLayout()
        
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
            field_layout.addWidget(QLabel(f"{label}:"))
            if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setMinimum(1)
                widget.setMaximum(999999)
            field_layout.addWidget(widget)
            layout.addLayout(field_layout)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add")
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
            'Stock Name': fields[0][1].text(),
            'Ticker Symbol': fields[1][1].text().upper(),
            'Quantity': fields[2][1].value(),
            'Purchase Price': fields[3][1].value(),
            'Purchase Date': fields[4][1].date().toString("dd-MM-yyyy"),
            'Sector': fields[5][1].text(),
            'Investment Value': fields[2][1].value() * fields[3][1].value()
        }
        
        if not stock_data['Stock Name'] or not stock_data['Ticker Symbol']:
            QMessageBox.warning(self, "Error", "Stock name and ticker are required!")
            return
            
        self.portfolios[portfolio] = pd.concat([
            self.portfolios[portfolio],
            pd.DataFrame([stock_data])
        ], ignore_index=True)
        
        self.log_audit("ADDED_STOCK", portfolio, stock_data['Stock Name'], 
                      f"Qty: {stock_data['Quantity']} @ {stock_data['Purchase Price']}")
        
        self.refresh_stock_table()
        dialog.accept()
        
    def show_modify_stock_dialog(self):
        selected = self.stock_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Error", "Please select a stock first!")
            return
            
        portfolio = self.portfolio_combo.currentText()
        stock = self.portfolios[portfolio].iloc[selected]
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Modify Stock")
        layout = QVBoxLayout()
        
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
            field_layout.addWidget(QLabel(f"{label}:"))
            if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setMinimum(1)
                widget.setMaximum(999999)
            field_layout.addWidget(widget)
            layout.addLayout(field_layout)
        
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
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
            'Stock Name': fields[0][1].text(),
            'Ticker Symbol': fields[1][1].text().upper(),
            'Quantity': fields[2][1].value(),
            'Purchase Price': fields[3][1].value(),
            'Purchase Date': fields[4][1].date().toString("dd-MM-yyyy"),
            'Sector': fields[5][1].text(),
            'Investment Value': fields[2][1].value() * fields[3][1].value()
        }
        
        if not stock_data['Stock Name'] or not stock_data['Ticker Symbol']:
            QMessageBox.warning(self, "Error", "Stock name and ticker are required!")
            return
            
        self.portfolios[portfolio].iloc[row] = stock_data
        self.log_audit("MODIFIED_STOCK", portfolio, stock_data['Stock Name'])
        self.refresh_stock_table()
        dialog.accept()
        
    def show_manage_shares_dialog(self):
        selected = self.stock_table.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Error", "Please select a stock first!")
            return
            
        portfolio = self.portfolio_combo.currentText()
        stock = self.portfolios[portfolio].iloc[selected]
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Shares")
        layout = QVBoxLayout()
        
        current_qty = QLabel(f"Current Quantity: {stock['Quantity']}")
        layout.addWidget(current_qty)
        
        action_combo = QComboBox()
        action_combo.addItems(["Add Shares", "Remove Shares"])
        layout.addWidget(action_combo)
        
        qty_label = QLabel("Quantity:")
        qty_input = QSpinBox()
        qty_input.setMinimum(1)
        qty_input.setMaximum(999999)
        layout.addWidget(qty_label)
        layout.addWidget(qty_input)
        
        price_label = QLabel("Price (for adding shares):")
        price_input = QDoubleSpinBox()
        price_input.setMinimum(0.01)
        price_input.setMaximum(999999)
        price_input.setValue(stock['Purchase Price'])
        layout.addWidget(price_label)
        layout.addWidget(price_input)
        
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
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
            else:
                self.portfolios[portfolio].at[row, 'Quantity'] = new_qty
                self.portfolios[portfolio].at[row, 'Investment Value'] = new_qty * stock['Purchase Price']
                
                self.log_audit(
                    "REMOVED_SHARES", portfolio, stock['Stock Name'],
                    f"Removed {qty} shares, Remaining: {new_qty}"
                )
        
        self.refresh_stock_table()
        dialog.accept()
        
    def create_dashboard_views(self):
        page = QWidget()
        layout = QVBoxLayout()
        
        title = QLabel("Dashboard Views")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
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
        
        # Summary cards
        summary_layout = QHBoxLayout()
        
        self.investment_card = self.create_summary_card("Total Invested", "0")
        self.current_value_card = self.create_summary_card("Current Value", "0")
        self.pl_card = self.create_summary_card("Profit/Loss", "0")
        self.daily_pl_card = self.create_summary_card("Today's P/L", "0")
        
        summary_layout.addWidget(self.investment_card)
        summary_layout.addWidget(self.current_value_card)
        summary_layout.addWidget(self.pl_card)
        summary_layout.addWidget(self.daily_pl_card)
        layout.addLayout(summary_layout)
        
        # Portfolio performance table
        self.portfolio_table = QTableWidget()
        self.portfolio_table.setColumnCount(6)
        self.portfolio_table.setHorizontalHeaderLabels([
            "Portfolio", "Invested", "Current", "P/L", "Daily P/L", "Status"
        ])
        layout.addWidget(self.portfolio_table)
        
        # Refresh button
        refresh_btn = QPushButton("Refresh Data")
        refresh_btn.clicked.connect(self.refresh_dashboard_data)
        layout.addWidget(refresh_btn)
        
        page.setLayout(layout)
        
    def refresh_dashboard_data(self):
        all_tickers = []
        for portfolio in self.portfolios.values():
            all_tickers.extend(portfolio['Ticker Symbol'].tolist())
        
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
            portfolio['Current Price'] = portfolio['Ticker Symbol'].map(prices)
            portfolio['Current Value'] = portfolio['Quantity'] * portfolio['Current Price']
            portfolio['Profit/Loss'] = portfolio['Current Value'] - portfolio['Investment Value']
            portfolio['Daily P/L'] = 0  # Would need previous close data
            
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
            pl_item.setForeground(QColor('#4AD66D') if pl >= 0 else QColor('#EF233C'))
            self.portfolio_table.setItem(row, 3, pl_item)
            
            daily_item = QTableWidgetItem(f"₹{daily_pl:+,.2f}")
            daily_item.setForeground(QColor('#4AD66D') if daily_pl >= 0 else QColor('#EF233C'))
            self.portfolio_table.setItem(row, 4, daily_item)
            
            status_item = QTableWidgetItem("↑" if pl >= 0 else "↓")
            status_item.setForeground(QColor('#4AD66D') if pl >= 0 else QColor('#EF233C'))
            self.portfolio_table.setItem(row, 5, status_item)
        
        self.update_summary_card(self.investment_card, "Total Invested", f"₹{total_investment:,.2f}")
        self.update_summary_card(self.current_value_card, "Current Value", f"₹{total_current:,.2f}")
        
        pl_text = f"₹{total_pl:+,.2f}\n({total_pl/total_investment*100:.2f}%)" if total_investment else "₹0.00"
        self.update_summary_card(self.pl_card, "Profit/Loss", pl_text, 
                               '#4AD66D' if total_pl >= 0 else '#EF233C')
        
        daily_text = f"₹{total_daily_pl:+,.2f}\n({total_daily_pl/total_current*100:.2f}%)" if total_current else "₹0.00"
        self.update_summary_card(self.daily_pl_card, "Today's P/L", daily_text,
                               '#4AD66D' if total_daily_pl >= 0 else '#EF233C')
        
    def create_summary_card(self, title, value):
        card = QWidget()
        card.setStyleSheet("background-color: #0F1017; border-radius: 5px;")
        layout = QVBoxLayout(card)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold;")
        value_label = QLabel(value)
        value_label.setStyleSheet("font-size: 14px;")
        
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
            value_label.setStyleSheet(f"font-size: 14px; color: {color};")
            
    def setup_individual_dashboard(self):
        page = self.individual_dashboard
        layout = QVBoxLayout()
        
        # Portfolio selection
        portfolio_label = QLabel("Select Portfolio:")
        self.dashboard_portfolio_combo = QComboBox()
        self.dashboard_portfolio_combo.addItems(self.portfolios.keys())
        self.dashboard_portfolio_combo.currentTextChanged.connect(self.refresh_individual_dashboard)
        
        layout.addWidget(portfolio_label)
        layout.addWidget(self.dashboard_portfolio_combo)
        
        # Summary cards
        summary_layout = QHBoxLayout()
        
        self.individual_investment_card = self.create_summary_card("Invested", "0")
        self.individual_current_card = self.create_summary_card("Current", "0")
        self.individual_pl_card = self.create_summary_card("P/L", "0")
        self.individual_daily_card = self.create_summary_card("Today's P/L", "0")
        
        summary_layout.addWidget(self.individual_investment_card)
        summary_layout.addWidget(self.individual_current_card)
        summary_layout.addWidget(self.individual_pl_card)
        summary_layout.addWidget(self.individual_daily_card)
        layout.addLayout(summary_layout)
        
        # Stock table
        self.individual_stock_table = QTableWidget()
        self.individual_stock_table.setColumnCount(7)
        self.individual_stock_table.setHorizontalHeaderLabels([
            "Stock", "Ticker", "Qty", "Avg Price", "Curr Price", "P/L", "Daily P/L"
        ])
        layout.addWidget(self.individual_stock_table)
        
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
        
        # Update summary cards
        investment = df['Investment Value'].sum()
        current = df['Current Value'].sum()
        pl = df['Profit/Loss'].sum()
        daily_pl = 0  # Would need previous close data
        
        self.update_summary_card(self.individual_investment_card, "Invested", f"₹{investment:,.2f}")
        self.update_summary_card(self.individual_current_card, "Current", f"₹{current:,.2f}")
        
        pl_text = f"₹{pl:+,.2f}\n({pl/investment*100:.2f}%)" if investment else "₹0.00"
        self.update_summary_card(self.individual_pl_card, "P/L", pl_text,
                               '#4AD66D' if pl >= 0 else '#EF233C')
        
        daily_text = f"₹{daily_pl:+,.2f}\n({daily_pl/current*100:.2f}%)" if current else "₹0.00"
        self.update_summary_card(self.individual_daily_card, "Today's P/L", daily_text,
                               '#4AD66D' if daily_pl >= 0 else '#EF233C')
        
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
                pl_item.setForeground(QColor('#4AD66D') if stock['Profit/Loss'] >= 0 else QColor('#EF233C'))
                self.individual_stock_table.setItem(row, 5, pl_item)
                
                # Daily P/L would need previous close data
                self.individual_stock_table.setItem(row, 6, QTableWidgetItem("N/A"))
            else:
                for col in range(4, 7):
                    self.individual_stock_table.setItem(row, col, QTableWidgetItem("N/A"))
                    
    def setup_charts_dashboard(self):
        page = self.charts_dashboard
        layout = QVBoxLayout()
        
        # Portfolio selection
        portfolio_label = QLabel("Select Portfolio:")
        self.chart_portfolio_combo = QComboBox()
        self.chart_portfolio_combo.addItems(self.portfolios.keys())
        self.chart_portfolio_combo.currentTextChanged.connect(self.update_charts)
        
        layout.addWidget(portfolio_label)
        layout.addWidget(self.chart_portfolio_combo)
        
        # Chart tabs
        self.chart_tabs = QTabWidget()
        
        # Allocation Chart
        self.allocation_chart = FigureCanvas(Figure(figsize=(10, 4)))
        self.chart_tabs.addTab(self.allocation_chart, "Allocation")
        
        # Performance Chart
        self.performance_chart = FigureCanvas(Figure(figsize=(10, 4)))
        self.chart_tabs.addTab(self.performance_chart, "Performance")
        
        layout.addWidget(self.chart_tabs)
        
        # Refresh button
        refresh_btn = QPushButton("Refresh Charts")
        refresh_btn.clicked.connect(self.update_charts)
        layout.addWidget(refresh_btn)
        
        page.setLayout(layout)
        
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
            ax.pie(
                df['Current Value'],
                labels=df['Stock Name'],
                autopct='%1.1f%%',
                startangle=90,
                wedgeprops={'linewidth': 1, 'edgecolor': 'white'}
            )
            ax.set_title("Portfolio Allocation", fontsize=12)
            
        fig.tight_layout()
        self.allocation_chart.draw()
        
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
            colors = ['#4AD66D' if x >= 0 else '#EF233C' for x in df['Profit/Loss']]
            
            bars = ax.bar(
                df['Stock Name'],
                df['Profit/Loss'],
                color=colors
            )
            
            ax.axhline(0, color='white', linestyle='--', linewidth=1)
            ax.set_title("Profit/Loss by Stock", fontsize=12)
            ax.set_ylabel("P/L (₹)")
            ax.tick_params(axis='x', rotation=45)
            
            # Add value labels
            for bar in bars:
                height = bar.get_height()
                ax.text(
                    bar.get_x() + bar.get_width()/2.,
                    height + (0.1 if height >=0 else -0.1),
                    f"₹{height:+,.2f}",
                    ha='center', va='center',
                    fontsize=8
                )
                
        fig.tight_layout()
        self.performance_chart.draw()
        
    def create_market_analysis(self):
        page = QWidget()
        layout = QVBoxLayout()
        
        title = QLabel("Market Analysis")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
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
        
        back_btn = QPushButton("Back to Main Menu")
        back_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        layout.addWidget(back_btn)
        
        page.setLayout(layout)
        self.stacked_widget.addWidget(page)
        
    def setup_indian_market_tab(self):
        page = self.indian_market_tab
        layout = QVBoxLayout()
        
        self.indian_status_label = QLabel("Loading market data...")
        layout.addWidget(self.indian_status_label)
        
        self.indian_market_table = QTableWidget()
        self.indian_market_table.setColumnCount(7)
        self.indian_market_table.setHorizontalHeaderLabels([
            "Index", "Price", "Change", "% Change", "Prev Close", "Market Hours", "Status"
        ])
        layout.addWidget(self.indian_market_table)
        
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
            'India VIX': '^INDIAVIX'
        }
        
        self.indian_worker = MarketDataWorker(indices)
        self.indian_worker.data_fetched.connect(self.update_indian_market_tab)
        self.indian_worker.start()
        
    def update_indian_market_tab(self, data):
        self.indian_market_table.setRowCount(len(data))
        
        prices = []
        changes = []
        labels = []
        
        for row, (index_name, index_data) in enumerate(data.items()):
            self.indian_market_table.setItem(row, 0, QTableWidgetItem(index_name))
            self.indian_market_table.setItem(row, 1, QTableWidgetItem(f"₹{index_data['Current']:,.2f}"))
            
            change_item = QTableWidgetItem(f"{index_data['Change']:+,.2f}")
            change_item.setForeground(QColor('#4AD66D') if index_data['Change'] >= 0 else QColor('#EF233C'))
            self.indian_market_table.setItem(row, 2, change_item)
            
            pct_item = QTableWidgetItem(f"{index_data['% Change']:+.2f}%")
            pct_item.setForeground(QColor('#4AD66D') if index_data['% Change'] >= 0 else QColor('#EF233C'))
            self.indian_market_table.setItem(row, 3, pct_item)
            
            self.indian_market_table.setItem(row, 4, QTableWidgetItem(f"₹{index_data['Previous Close']:,.2f}"))
            self.indian_market_table.setItem(row, 5, QTableWidgetItem(index_data['Market Hours']))
            
            status_item = QTableWidgetItem(index_data['Status'])
            status_item.setForeground(QColor('#4AD66D') if "Open" in index_data['Status'] else QColor('#EF233C'))
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
        
        self.global_status_label = QLabel("Loading market data...")
        layout.addWidget(self.global_status_label)
        
        self.global_market_table = QTableWidget()
        self.global_market_table.setColumnCount(7)
        self.global_market_table.setHorizontalHeaderLabels([
            "Index", "Price", "Change", "% Change", "Prev Close", "Market Hours", "Status"
        ])
        layout.addWidget(self.global_market_table)
        
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
            'Nikkei 225': '^N225'
        }
        
        self.global_worker = MarketDataWorker(indices)
        self.global_worker.data_fetched.connect(self.update_global_market_tab)
        self.global_worker.start()
        
    def update_global_market_tab(self, data):
        self.global_market_table.setRowCount(len(data))
        
        prices = []
        changes = []
        labels = []
        
        for row, (index_name, index_data) in enumerate(data.items()):
            self.global_market_table.setItem(row, 0, QTableWidgetItem(index_name))
            self.global_market_table.setItem(row, 1, QTableWidgetItem(f"${index_data['Current']:,.2f}"))
            
            change_item = QTableWidgetItem(f"{index_data['Change']:+,.2f}")
            change_item.setForeground(QColor('#4AD66D') if index_data['Change'] >= 0 else QColor('#EF233C'))
            self.global_market_table.setItem(row, 2, change_item)
            
            pct_item = QTableWidgetItem(f"{index_data['% Change']:+.2f}%")
            pct_item.setForeground(QColor('#4AD66D') if index_data['% Change'] >= 0 else QColor('#EF233C'))
            self.global_market_table.setItem(row, 3, pct_item)
            
            self.global_market_table.setItem(row, 4, QTableWidgetItem(f"${index_data['Previous Close']:,.2f}"))
            self.global_market_table.setItem(row, 5, QTableWidgetItem(index_data['Market Hours']))
            
            status_item = QTableWidgetItem(index_data['Status'])
            status_item.setForeground(QColor('#4AD66D') if "Open" in index_data['Status'] else QColor('#EF233C'))
            self.global_market_table.setItem(row, 6, status_item)
            
            # Prepare data for chart
            prices.append(index_data['Current'])
            changes.append(index_data['% Change'])
            labels.append(index_name)
        
        self.plot_market_performance(self.global_chart.figure, labels, prices, changes, "Global Market Overview")
        self.global_status_label.setText(f"Global market data updated at {datetime.now().strftime('%H:%M:%S')}")
        
    def plot_market_performance(self, fig, labels, prices, changes, title):
        fig.clear()
        
        ax1 = fig.add_subplot(121)
        ax2 = fig.add_subplot(122)
        
        # Price comparison
        ax1.bar(labels, prices, color='#4361EE')
        ax1.set_title("Index Prices")
        ax1.set_ylabel("Price")
        ax1.tick_params(axis='x', rotation=45)
        
        # Percentage change
        colors = ['#4AD66D' if x >= 0 else '#EF233C' for x in changes]
        ax2.bar(labels, changes, color=colors)
        ax2.set_title("Daily Change")
        ax2.set_ylabel("% Change")
        ax2.tick_params(axis='x', rotation=45)
        
        fig.suptitle(title, fontsize=12)
        fig.tight_layout()
        fig.canvas.draw()
        
    def create_data_operations(self):
        page = QWidget()
        layout = QVBoxLayout()
        
        title = QLabel("Data Operations")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        export_layout = QHBoxLayout()
        export_current_btn = QPushButton("Export Current Portfolio")
        export_current_btn.clicked.connect(self.export_current_portfolio)
        export_all_btn = QPushButton("Export All Portfolios")
        export_all_btn.clicked.connect(self.export_all_portfolios)
        
        export_layout.addWidget(export_current_btn)
        export_layout.addWidget(export_all_btn)
        layout.addLayout(export_layout)
        
        import_layout = QHBoxLayout()
        import_btn = QPushButton("Import Portfolios")
        import_btn.clicked.connect(self.import_portfolios)
        layout.addLayout(import_layout)
        
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
                    # Single portfolio or multiple portfolios
                    if 'metadata' in data and 'stocks' in data:
                        # Single portfolio format
                        portfolio_name = data['metadata']['portfolio_name']
                        self.portfolios[portfolio_name] = pd.DataFrame(data['stocks'])
                        self.log_audit("IMPORTED_PORTFOLIO", portfolio_name)
                    else:
                        # Multiple portfolios format
                        for name, portfolio_data in data.items():
                            self.portfolios[name] = pd.DataFrame(portfolio_data['stocks'])
                            self.log_audit("IMPORTED_PORTFOLIO", name)
                    
                    self.refresh_portfolio_list()
                    QMessageBox.information(self, "Success", "Portfolios imported successfully!")
                else:
                    QMessageBox.warning(self, "Error", "Invalid file format!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import: {str(e)}")
                
    def create_audit_history(self):
        page = QWidget()
        layout = QVBoxLayout()
        
        title = QLabel("Audit History")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        self.audit_table = QTableWidget()
        self.audit_table.setColumnCount(5)
        self.audit_table.setHorizontalHeaderLabels([
            "Timestamp", "Action", "Portfolio", "Stock", "Details"
        ])
        self.audit_table.setSortingEnabled(True)
        layout.addWidget(self.audit_table)
        
        filter_layout = QHBoxLayout()
        self.audit_filter_combo = QComboBox()
        self.audit_filter_combo.addItems(["All", "Portfolio Changes", "Stock Changes"])
        self.audit_filter_combo.currentIndexChanged.connect(self.refresh_audit_log)
        
        filter_layout.addWidget(QLabel("Filter:"))
        filter_layout.addWidget(self.audit_filter_combo)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
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
        except:
            log_entries = []
            
        filter_text = self.audit_filter_combo.currentText()
        if filter_text == "Portfolio Changes":
            log_entries = [entry for entry in log_entries 
                         if entry[1] in ["CREATED_PORTFOLIO", "DELETED_PORTFOLIO", "IMPORTED_PORTFOLIO", "EXPORTED_PORTFOLIO"]]
        elif filter_text == "Stock Changes":
            log_entries = [entry for entry in log_entries 
                         if entry[1] not in ["CREATED_PORTFOLIO", "DELETED_PORTFOLIO", "IMPORTED_PORTFOLIO", "EXPORTED_PORTFOLIO"]]
        
        self.audit_table.setRowCount(len(log_entries))
        for row, entry in enumerate(reversed(log_entries)):
            for col, value in enumerate(entry):
                self.audit_table.setItem(row, col, QTableWidgetItem(value))
                
    def log_audit(self, action, portfolio, stock="", details=""):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"{timestamp} | {action} | {portfolio} | {stock} | {details}\n"
        
        try:
            with open("portfolio_audit.log", "a") as f:
                f.write(log_entry)
        except:
            pass
            
        self.refresh_audit_log()
        
    def load_data(self):
        try:
            with open("portfolios.json", "r") as f:
                data = json.load(f)
                self.portfolios = {k: pd.DataFrame(v) for k, v in data.items()}
        except:
            self.portfolios = {}
            
    def save_data(self):
        with open("portfolios.json", "w") as f:
            json.dump({k: v.to_dict(orient='records') for k, v in self.portfolios.items()}, f, indent=4)
            
    def closeEvent(self, event):
        self.save_data()
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = PortfolioTracker()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()