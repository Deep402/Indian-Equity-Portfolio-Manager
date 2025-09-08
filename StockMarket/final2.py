import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import json
import os
import sys
import time
import signal
import atexit
import pytz
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.style import Style
from rich.theme import Theme
from rich import box
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import plotly.subplots as sp

# Constants
PORTFOLIO_FILE = "portfolios.json"
BACKUP_FILE = "portfolios_backup.json"
AUDIT_LOG_FILE = "portfolio_audit.log"
CACHE_FILE = "price_cache.json"
CACHE_TTL_MINUTES = 15
MAX_WORKERS = 5
REFRESH_INTERVAL = 2  # seconds

TABLE_STYLE = {
    "width": 120,
    "padding": (0, 2),
    "expand": True,
    "box": box.ROUNDED,
    "show_header": True,
    "header_style": "bold white",
    "border_style": "blue",
    "row_styles": ["none", "dim"],
    "title_style": "bold white on blue"
}

# Theme Configuration
THEME = {
    "primary": "#4CC9F0",
    "secondary": "#F72585",
    "success": "#4AD66D",
    "warning": "#F7B801",
    "danger": "#EF233C",
    "info": "#7209B7",
    "light": "#F8F9FA",
    "dark": "#212529",
    "background": "#1A1B26",
    "text": "#E0E0E0"
}

custom_theme = Theme({
    "header": f"bold {THEME['primary']}",
    "menu": f"bold bright_white on {THEME['dark']}",
    "option": "bold bright_white",
    "description": "dim bright_white",
    "prompt": f"bold {THEME['primary']}",
    "success": f"bold {THEME['success']}",
    "warning": f"bold {THEME['warning']}",
    "error": f"bold {THEME['danger']}",
    "info": f"bold {THEME['info']}"
})

# Initialize console
console = Console(theme=custom_theme, width=120)
console_lock = Lock()

# Market Indices Data
INDICES = {
    'Indian': {
        'Nifty 50': {'ticker': '^NSEI', 'market_hours': '09:15-15:30 IST'},
        'Nifty Bank': {'ticker': '^NSEBANK', 'market_hours': '09:15-15:30 IST'},
        'Nifty Next 50': {'ticker': '^NSEMDCP50', 'market_hours': '09:15-15:30 IST'},
        'Sensex': {'ticker': '^BSESN', 'market_hours': '09:15-15:30 IST'}
    },
    'Global': {
        'S&P 500': {'ticker': '^GSPC', 'market_hours': '09:30-16:00 ET'},
        'NASDAQ': {'ticker': '^IXIC', 'market_hours': '09:30-16:00 ET'},
        'Dow Jones': {'ticker': '^DJI', 'market_hours': '09:30-16:00 ET'},
        'FTSE 100': {'ticker': '^FTSE', 'market_hours': '08:00-16:30 GMT'}
    }
}

class PriceCache:
    """Cache for stock prices with time-to-live"""
    def __init__(self):
        self.cache = {}
        self.load_cache()
        atexit.register(self.save_cache)
        
    def load_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r') as f:
                    data = json.load(f)
                    for ticker, (timestamp, price) in data.items():
                        self.cache[ticker] = (datetime.fromisoformat(timestamp)), price
            except Exception as e:
                self._safe_print(f"Error loading price cache: {e}")
    
    def save_cache(self):
        try:
            serialized = {ticker: (timestamp.isoformat(), price) 
                         for ticker, (timestamp, price) in self.cache.items()}
            with open(CACHE_FILE, 'w') as f:
                json.dump(serialized, f)
        except Exception as e:
            self._safe_print(f"Error saving price cache: {e}")

    def get_price(self, ticker):
        if ticker in self.cache:
            cached_time, price = self.cache[ticker]
            if datetime.now() - cached_time < timedelta(minutes=CACHE_TTL_MINUTES):
                return price
        return None
    
    def update_price(self, ticker, price):
        self.cache[ticker] = (datetime.now(), price)
    
    def _safe_print(self, message):
        with console_lock:
            console.print(message)

price_cache = PriceCache()

class PortfolioManager:
    """Enhanced portfolio management class with complete undo/redo functionality"""
    def __init__(self):
        self.portfolios = {}
        self.undo_stack = []  # Stores all reversible actions
        self.redo_stack = []  # Stores undone actions for redo
        self.load_portfolios()
        self.setup_signal_handlers()
        
    def setup_signal_handlers(self):
        """Handle interrupt signals gracefully"""
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)
        atexit.register(self.save_portfolios)
        
    def _handle_interrupt(self, signum, frame):
        """Handle interrupt signals"""
        self._safe_print("\n[yellow]Interrupt received, saving portfolios...[/yellow]")
        self.emergency_save()
        sys.exit(1)
        
    def emergency_save(self):
        """Save portfolios in emergency situations"""
        try:
            with open(BACKUP_FILE, 'w') as f:
                json.dump(self.serialize_portfolios(), f, indent=4)
            self._safe_print(f"[green]Emergency backup saved to {BACKUP_FILE}[/green]")
        except Exception as e:
            self._safe_print(f"[red]Error during emergency save: {e}[/red]")
    
    def serialize_portfolios(self):
        """Convert portfolios to serializable format"""
        return {name: self.calculate_all_metrics(df).to_dict('records') 
                for name, df in self.portfolios.items()}
    
    def load_portfolios(self):
        """Load portfolios from file with validation"""
        try:
            if os.path.exists(PORTFOLIO_FILE):
                with open(PORTFOLIO_FILE, 'r') as f:
                    data = json.load(f)
                    self.portfolios = {name: pd.DataFrame(records) for name, records in data.items()}
                    
                    # Initialize metrics columns
                    for name, df in self.portfolios.items():
                        df['Current Price'] = df.get('Current Price', 0.0)
                        df['Current Value'] = df.get('Current Value', 0.0)
                        df['Profit/Loss'] = df.get('Profit/Loss', 0.0)
                        df['Profit/Loss %'] = df.get('Profit/Loss %', 0.0)
                        df['Daily Return %'] = df.get('Daily Return %', 0.0)
                        df['Daily P/L'] = df.get('Daily P/L', 0.0)
                        
        except Exception as e:
            self._safe_print(f"[red]Error loading portfolios: {e}[/red]")
            if os.path.exists(BACKUP_FILE):
                self._safe_print("[yellow]Attempting to load backup...[/yellow]")
                try:
                    with open(BACKUP_FILE, 'r') as f:
                        data = json.load(f)
                        self.portfolios = {name: pd.DataFrame(records) for name, records in data.items()}
                        # Same initialization for backup
                        for name, df in self.portfolios.items():
                            df['Current Price'] = df.get('Current Price', 0.0)
                            df['Current Value'] = df.get('Current Value', 0.0)
                            df['Profit/Loss'] = df.get('Profit/Loss', 0.0)
                            df['Profit/Loss %'] = df.get('Profit/Loss %', 0.0)
                            df['Daily Return %'] = df.get('Daily Return %', 0.0)
                            df['Daily P/L'] = df.get('Daily P/L', 0.0)
                except Exception as e:
                    self._safe_print(f"[red]Error loading backup: {e}[/red]")
                    self.portfolios = {}
    
    def save_portfolios(self):
        """Save portfolios to file"""
        try:
            with open(PORTFOLIO_FILE, 'w') as f:
                json.dump(self.serialize_portfolios(), f, indent=4)
        except Exception as e:
            self._safe_print(f"[red]Error saving portfolios: {e}[/red]")
            self.emergency_save()
    
    def calculate_all_metrics(self, portfolio):
        """Enhanced calculation with proper averaging"""
        if portfolio.empty:
            return portfolio
            
        # Get live prices
        tickers = portfolio['Ticker Symbol'].unique().tolist()
        prices = self.get_live_prices_concurrently(tickers)
        
        portfolio = portfolio.copy()
        portfolio['Current Price'] = portfolio['Ticker Symbol'].map(prices)
        
        # Calculate values
        portfolio['Current Value'] = portfolio['Quantity'] * portfolio['Current Price']
        portfolio['Investment Value'] = portfolio['Quantity'] * portfolio['Purchase Price']
        portfolio['Profit/Loss'] = portfolio['Current Value'] - portfolio['Investment Value']
        
        # Handle division by zero
        portfolio['Profit/Loss %'] = portfolio.apply(
            lambda x: (x['Profit/Loss'] / x['Investment Value'] * 100) if x['Investment Value'] != 0 else 0,
            axis=1
        )
        
        # Calculate daily returns
        for idx, row in portfolio.iterrows():
            prev_close = self.get_previous_close(row['Ticker Symbol'])
            if prev_close and row['Current Price']:
                portfolio.at[idx, 'Daily Return %'] = ((row['Current Price'] - prev_close) / prev_close) * 100
                portfolio.at[idx, 'Daily P/L'] = row['Quantity'] * (row['Current Price'] - prev_close)
            else:
                portfolio.at[idx, 'Daily Return %'] = 0
                portfolio.at[idx, 'Daily P/L'] = 0
                
        return portfolio
    
    def get_live_prices_concurrently(self, tickers):
        """Fetch live prices for multiple tickers with caching"""
        prices = {}
        tickers = [t for t in tickers if t]  # Remove empty tickers
        
        # Check cache first
        for ticker in tickers:
            cached_price = price_cache.get_price(ticker)
            if cached_price is not None:
                prices[ticker] = cached_price
                
        # Only fetch missing tickers
        missing_tickers = [t for t in tickers if t not in prices]
        
        if not missing_tickers:
            return prices
            
        def fetch_price(ticker):
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period="1d")
                if not hist.empty:
                    price = hist['Close'].iloc[-1]
                    price_cache.update_price(ticker, price)
                    return ticker, price
            except Exception as e:
                self._safe_print(f"[red]Error fetching price for {ticker}: {e}[/red]")
            return ticker, None
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(fetch_price, ticker): ticker for ticker in missing_tickers}
            
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    ticker, price = future.result()
                    if price is not None:
                        prices[ticker] = price
                except Exception as e:
                    self._safe_print(f"[red]Error processing {ticker}: {e}[/red]")
        
        return prices
    
    def get_previous_close(self, ticker):
        """Get previous close price with caching"""
        cached = price_cache.get_price(ticker + "_prev")
        if cached is not None:
            return cached
            
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if len(hist) < 2:
                return None
            prev_close = hist['Close'].iloc[-2]
            price_cache.update_price(ticker + "_prev", prev_close)
            return prev_close
        except Exception as e:
            self._safe_print(f"[red]Error fetching previous close for {ticker}: {e}[/red]")
            return None

    def create_portfolio(self, name):
        """Create a new portfolio"""
        normalized_name = name.strip().lower()
        for existing_name in self.portfolios.keys():
            if existing_name.strip().lower() == normalized_name:
                self._safe_print(f"[red]Portfolio '{existing_name}' already exists![/red]")
                return False
                
        self.portfolios[name] = pd.DataFrame(columns=[
            'Stock Name', 'Ticker Symbol', 'Quantity', 'Purchase Price',
            'Purchase Date', 'Sector', 'Investment Value', 'Current Price',
            'Current Value', 'Profit/Loss', 'Profit/Loss %', 'Daily Return %', 'Daily P/L'
        ])
        log_portfolio_change("CREATED_PORTFOLIO", name)
        self._safe_print(f"[green]Portfolio '{name}' created successfully![/green]")
        return True
    
    def delete_portfolio(self, name):
        """Delete a portfolio"""
        if name not in self.portfolios:
            self._safe_print(f"[red]Portfolio '{name}' not found![/red]")
            return False
            
        # Show confirmation
        if not self.portfolios[name].empty:
            self._safe_print(f"[yellow]Portfolio '{name}' contains {len(self.portfolios[name])} stocks[/yellow]")
        
        confirm = self._get_input(f"Confirm delete portfolio '{name}'? (y/n): ").lower()
        if confirm != 'y':
            self._safe_print("[yellow]Deletion cancelled[/yellow]")
            return False
            
        log_portfolio_change("DELETED_PORTFOLIO", name, 
                           details=f"Stocks deleted: {len(self.portfolios[name])}")
        del self.portfolios[name]
        self._safe_print(f"[green]Portfolio '{name}' deleted[/green]")
        return True
    
    def add_stock(self, portfolio_name, stock_data):
        """Add a stock to a portfolio with undo support"""
        if portfolio_name not in self.portfolios:
            self._safe_print(f"[red]Portfolio '{portfolio_name}' not found![/red]")
            return False
            
        # Check if ticker already exists
        portfolio = self.portfolios[portfolio_name]
        if not portfolio[portfolio['Ticker Symbol'] == stock_data['Ticker Symbol']].empty:
            self._safe_print("[yellow]Stock with this ticker already exists in portfolio[/yellow]")
            return False
            
        # Create new stock entry
        new_stock = {
            'Stock Name': stock_data['Stock Name'],
            'Ticker Symbol': stock_data['Ticker Symbol'],
            'Quantity': stock_data['Quantity'],
            'Purchase Price': stock_data['Purchase Price'],
            'Purchase Date': stock_data['Purchase Date'],
            'Sector': stock_data.get('Sector', ''),
            'Investment Value': stock_data['Quantity'] * stock_data['Purchase Price'],
            'Current Price': 0.0,
            'Current Value': 0.0,
            'Profit/Loss': 0.0,
            'Profit/Loss %': 0.0,
            'Daily Return %': 0.0,
            'Daily P/L': 0.0
        }
        
        # Add to portfolio and recalculate
        self.portfolios[portfolio_name] = pd.concat([
            portfolio, 
            pd.DataFrame([new_stock])
        ], ignore_index=True)
        self.portfolios[portfolio_name] = self.calculate_all_metrics(self.portfolios[portfolio_name])
        
        # Push to undo stack
        self.push_undo_action('add', portfolio_name, new_stock)
        
        log_portfolio_change(
            "ADDED_STOCK", 
            portfolio_name,
            stock_data['Stock Name'],
            f"Qty: {stock_data['Quantity']} @ ₹{stock_data['Purchase Price']:.2f}"
        )
        
        self._safe_print(f"[green]Stock '{stock_data['Stock Name']}' added to '{portfolio_name}'[/green]")
        return True
    
    def modify_stock(self, portfolio_name, stock_index, updated_data):
        """Modify an existing stock with undo support"""
        if portfolio_name not in self.portfolios:
            self._safe_print(f"[red]Portfolio '{portfolio_name}' not found![/red]")
            return False
            
        portfolio = self.portfolios[portfolio_name]
        if stock_index >= len(portfolio):
            self._safe_print("[red]Invalid stock index![/red]")
            return False
            
        # Store original state for undo
        original_stock = portfolio.iloc[stock_index].to_dict()
        
        # Update the stock data
        for key, value in updated_data.items():
            if key in portfolio.columns:
                portfolio.at[stock_index, key] = value
                
        # Recalculate investment value if quantity or price changed
        if 'Quantity' in updated_data or 'Purchase Price' in updated_data:
            portfolio.at[stock_index, 'Investment Value'] = (
                portfolio.at[stock_index, 'Quantity'] * 
                portfolio.at[stock_index, 'Purchase Price']
            )
        
        # Recalculate all metrics
        self.portfolios[portfolio_name] = self.calculate_all_metrics(portfolio)
        
        # Push to undo stack
        self.push_undo_action('modify', portfolio_name, original_stock, stock_index)
        
        log_portfolio_change(
            "MODIFIED_STOCK",
            portfolio_name,
            portfolio.at[stock_index, 'Stock Name'],
            f"Updated fields: {', '.join(updated_data.keys())}"
        )
        
        self._safe_print(f"[green]Stock updated successfully![/green]")
        return True
    
    def remove_stock(self, portfolio_name, stock_index):
        """Remove a stock from portfolio with proper logging"""
        try:
            if portfolio_name not in self.portfolios:
                self._safe_print(f"[red]Portfolio '{portfolio_name}' not found![/red]")
                return False
                
            portfolio = self.portfolios[portfolio_name]
            if stock_index >= len(portfolio):
                self._safe_print("[red]Invalid stock index![/red]")
                return False
                
            # Get the stock before removal
            stock = portfolio.iloc[stock_index].copy()
            
            # Convert numpy types to Python native types
            stock = {k: (int(v) if isinstance(v, (np.int64, np.int32)) 
                    else float(v) if isinstance(v, (np.float64, np.float32)) 
                    else v) for k, v in stock.items()}
            
            # Store for possible undo
            self.last_removed_stock = {
                'portfolio': portfolio_name,
                'stock': stock,
                'timestamp': datetime.now()
            }
            
            # Log before removal
            log_portfolio_change(
                "REMOVED_STOCK",
                portfolio_name,
                stock['Stock Name'],
                f"Qty: {stock['Quantity']} @ ₹{stock['Current Price']:.2f} (Value: ₹{stock['Current Value']:.2f})"
            )
            
            # Perform removal
            self.portfolios[portfolio_name] = portfolio.drop(stock_index).reset_index(drop=True)
            return True
        except Exception as e:
            self._safe_print(f"[red]Error removing stock: {e}[/red]")
            return False
    
    def push_undo_action(self, action_type, portfolio_name, stock_data=None, index=None):
        """Store an action that can be undone"""
        self.undo_stack.append({
            'type': action_type,
            'portfolio': portfolio_name,
            'stock': stock_data.copy() if stock_data is not None else None,
            'index': index,
            'timestamp': datetime.now()
        })
        self.redo_stack = []  # Clear redo stack on new action

    def undo_last_action(self):
        """Undo the last reversible action"""
        if not self.undo_stack:
            self._safe_print("[yellow]Nothing to undo![/yellow]")
            return False
            
        action = self.undo_stack.pop()
        
        try:
            if action['type'] == 'remove':
                # Undo a removal by adding the stock back
                new_stock = {
                    'Stock Name': action['stock']['Stock Name'],
                    'Ticker Symbol': action['stock']['Ticker Symbol'],
                    'Quantity': action['stock']['Quantity'],
                    'Purchase Price': action['stock']['Purchase Price'],
                    'Purchase Date': action['stock']['Purchase Date'],
                    'Sector': action['stock'].get('Sector', ''),
                    'Investment Value': action['stock']['Quantity'] * action['stock']['Purchase Price']
                }
                
                self.portfolios[action['portfolio']] = pd.concat([
                    self.portfolios[action['portfolio']],
                    pd.DataFrame([new_stock])
                ], ignore_index=True)
                
                self.redo_stack.append(action)
                self._safe_print(f"[green]Restored {action['stock']['Stock Name']}[/green]")
                return True
                
            elif action['type'] == 'add':
                # Undo an addition by removing the last added stock
                portfolio = self.portfolios[action['portfolio']]
                if len(portfolio) > 0:
                    last_index = len(portfolio) - 1
                    removed_stock = portfolio.iloc[last_index].to_dict()
                    
                    self.portfolios[action['portfolio']] = portfolio.drop(last_index)
                    
                    self.redo_stack.append({
                        'type': 'add',
                        'portfolio': action['portfolio'],
                        'stock': removed_stock,
                        'timestamp': datetime.now()
                    })
                    self._safe_print(f"[green]Removed {removed_stock['Stock Name']}[/green]")
                    return True
                return False
                
            elif action['type'] == 'modify':
                # Revert to previous state
                current_stock = self.portfolios[action['portfolio']].iloc[action['index']].to_dict()
                
                for col in action['stock']:
                    if col in self.portfolios[action['portfolio']].columns:
                        self.portfolios[action['portfolio']].at[action['index'], col] = action['stock'][col]
                
                self.redo_stack.append({
                    'type': 'modify',
                    'portfolio': action['portfolio'],
                    'stock': current_stock,
                    'index': action['index'],
                    'timestamp': datetime.now()
                })
                self._safe_print(f"[green]Reverted changes to {action['stock']['Stock Name']}[/green]")
                return True
                
        except Exception as e:
            self._safe_print(f"[red]Error during undo: {e}[/red]")
            return False

    def redo_last_undo(self):
        """Redo the last undone action"""
        if not self.redo_stack:
            self._safe_print("[yellow]Nothing to redo![/yellow]")
            return False
            
        action = self.redo_stack.pop()
        self.undo_stack.append(action)  # Make it undoable again
        
        try:
            if action['type'] == 'add':
                new_stock = {
                    'Stock Name': action['stock']['Stock Name'],
                    'Ticker Symbol': action['stock']['Ticker Symbol'],
                    'Quantity': action['stock']['Quantity'],
                    'Purchase Price': action['stock']['Purchase Price'],
                    'Purchase Date': action['stock']['Purchase Date'],
                    'Sector': action['stock'].get('Sector', ''),
                    'Investment Value': action['stock']['Quantity'] * action['stock']['Purchase Price']
                }
                
                self.portfolios[action['portfolio']] = pd.concat([
                    self.portfolios[action['portfolio']],
                    pd.DataFrame([new_stock])
                ], ignore_index=True)
                self._safe_print(f"[green]Re-added {action['stock']['Stock Name']}[/green]")
                return True
                
            elif action['type'] == 'remove':
                # Find and remove the stock again
                portfolio = self.portfolios[action['portfolio']]
                mask = portfolio['Ticker Symbol'] == action['stock']['Ticker Symbol']
                if mask.any():
                    index = portfolio[mask].index[0]
                    self.portfolios[action['portfolio']] = portfolio.drop(index)
                    self._safe_print(f"[green]Re-removed {action['stock']['Stock Name']}[/green]")
                    return True
                return False
                
            elif action['type'] == 'modify':
                current_stock = self.portfolios[action['portfolio']].iloc[action['index']].to_dict()
                
                for col in action['stock']:
                    if col in self.portfolios[action['portfolio']].columns:
                        self.portfolios[action['portfolio']].at[action['index'], col] = action['stock'][col]
                
                self._safe_print(f"[green]Re-applied changes to {action['stock']['Stock Name']}[/green]")
                return True
                
        except Exception as e:
            self._safe_print(f"[red]Error during redo: {e}[/red]")
            return False
    

    def _safe_print(self, message):
        """Thread-safe printing"""
        with console_lock:
            console.print(message)
    
    def _get_input(self, prompt):
        """Thread-safe input with validation"""
        with console_lock:
            return input(prompt)

    def get_portfolio_performance_chart(self, portfolio_name, chart_type):
        """Generate performance charts for a portfolio with enhanced visuals"""
        portfolio = self.calculate_all_metrics(self.portfolios.get(portfolio_name, pd.DataFrame()))
        
        if portfolio.empty:
            self._safe_print("[red]Portfolio is empty![/red]")
            return

        if chart_type == "allocation":
            # Create interactive pie chart with current allocations
            fig = px.pie(portfolio, 
                        values='Current Value', 
                        names='Stock Name',
                        title=f"Portfolio Allocation: {portfolio_name}",
                        hole=0.3,
                        hover_data=['Ticker Symbol', 'Current Value'])
            fig.update_traces(textposition='inside', 
                            textinfo='percent+label',
                            hovertemplate="<b>%{label}</b><br>%{percent}<br>Value: ₹%{value:,.2f}")
            fig.update_layout(legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.2,
                xanchor="center",
                x=0.5
            ))

        elif chart_type == "profit_loss":
            # Create bar chart with profit/loss visualization
            portfolio = portfolio.sort_values('Profit/Loss', ascending=False)
            fig = px.bar(portfolio, 
                         x='Stock Name', 
                         y='Profit/Loss',
                         color='Profit/Loss',
                         color_continuous_scale=['red', 'green'],
                         title=f"Profit/Loss: {portfolio_name}",
                         hover_data=['Ticker Symbol', 'Current Value', 'Profit/Loss %'])
            fig.add_hline(y=0, line_width=2, line_dash="dash")
            fig.update_layout(xaxis_tickangle=-45)

        elif chart_type == "daily":
            # Create bar chart with daily performance
            portfolio = portfolio.sort_values('Daily Return %', ascending=False)
            fig = px.bar(portfolio, 
                        x='Stock Name', 
                        y='Daily Return %',
                        color='Daily Return %',
                        color_continuous_scale=['red', 'green'],
                        title=f"Daily Performance: {portfolio_name}",
                        hover_data=['Ticker Symbol', 'Daily P/L'])
            fig.add_hline(y=0, line_width=2, line_dash="dash")
            fig.update_layout(xaxis_tickangle=-45)

        elif chart_type == "historical":
            # Create line chart with historical performance
            tickers = portfolio['Ticker Symbol'].tolist()
            historical_data = self.get_historical_prices(tickers)
            
            if historical_data.empty:
                self._safe_print("[red]Could not fetch historical data[/red]")
                return
                
            fig = px.line(historical_data, 
                         x=historical_data.index, 
                         y=historical_data.columns,
                         title=f"Historical Performance: {portfolio_name}",
                         labels={'value': 'Price (₹)', 'variable': 'Stock'})
            fig.update_layout(hovermode="x unified")

        # Apply consistent theme
        fig.update_layout(
            paper_bgcolor=THEME['background'],
            plot_bgcolor=THEME['background'],
            font=dict(color=THEME['text']),
            margin=dict(l=20, r=20, t=40, b=20),
            height=600
        )
        fig.show()

    def get_historical_prices(self, tickers, period="1mo"):
        """Get historical prices for multiple tickers"""
        try:
            data = yf.download(tickers, period=period, progress=False)['Close']
            if len(tickers) == 1:  # Handle single stock case
                data = data.to_frame()
                data.columns = tickers
            return data
        except Exception as e:
            self._safe_print(f"[red]Error fetching historical data: {e}[/red]")
            return pd.DataFrame()

    def get_market_snapshot(self):
        """Get comprehensive market snapshot with enhanced data"""
        snapshot = {}
        
        def get_index_info(ticker, market_type):
            try:
                index = yf.Ticker(ticker)
                hist = index.history(period="2d")
                
                if len(hist) < 1:
                    return None
                    
                current = hist['Close'].iloc[-1]
                prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else current
                change = current - prev_close
                pct_change = (change / prev_close) * 100
                
                return {
                    'current': current,
                    'change': change,
                    'pct_change': pct_change,
                    'status': "Open" if is_market_open(market_type) else "Closed",
                    'high': hist['High'].iloc[-1],
                    'low': hist['Low'].iloc[-1]
                }
            except:
                return None

        # Indian indices with more detailed data
        for name, info in INDICES['Indian'].items():
            data = get_index_info(info['ticker'], 'Indian')
            if data:
                snapshot[name] = {
                    **data,
                    'market_hours': info['market_hours'],
                    'currency': '₹'
                }

        # Global indices with more detailed data
        for name, info in INDICES['Global'].items():
            data = get_index_info(info['ticker'], 'Global')
            if data:
                snapshot[name] = {
                    **data,
                    'market_hours': info['market_hours'],
                    'currency': '$'
                }

        return snapshot

    def display_market_snapshot(self):
        """Display enhanced market snapshot with visual indicators"""
        snapshot = self.get_market_snapshot()
        
        if not snapshot:
            self._safe_print(Panel("[red]Failed to fetch market data[/red]",
                                border_style="red"))
            return

        # Create tables for Indian and Global markets
        indian_table = Table(title="\nIndian Indices", box=box.ROUNDED)
        global_table = Table(title="\nGlobal Indices", box=box.ROUNDED)
        
        # Common columns
        for table in [indian_table, global_table]:
            table.add_column("Index", style="bold", width=20)
            table.add_column("Price", justify="right", width=15)
            table.add_column("Change", justify="right", width=20)
            table.add_column("Range", justify="right", width=20)
            table.add_column("Status", justify="center", width=15)

        # Populate tables
        for name, data in snapshot.items():
            change_color = "green" if data['change'] >= 0 else "red"
            status_color = "green" if data['status'] == "Open" else "red"
            range_str = f"{data['low']:,.2f}-{data['high']:,.2f}"
            
            row_data = [
                name,
                f"{data['currency']}{data['current']:,.2f}",
                f"[{change_color}]{data['change']:+,.2f} ({data['pct_change']:+.2f}%)[/]",
                f"{data['currency']}{range_str}",
                f"[{status_color}]{data['status']}[/]"
            ]
            
            if name in INDICES['Indian']:
                indian_table.add_row(*row_data)
            else:
                global_table.add_row(*row_data)

        # Display with market hours information
        self._safe_print(Panel(indian_table))
        self._safe_print(Panel(global_table))
        
        # Show market hours legend
        legend = Table.grid(expand=True, padding=(1, 2))
        legend.add_column(justify="left")
        legend.add_column(justify="left")
        
        legend.add_row(
            Panel("[green]● Open[/green]  [red]● Closed[/red]", border_style="dim"),
            Panel(f"Indian Market Hours: {INDICES['Indian']['Nifty 50']['market_hours']}\n"
                 f"US Market Hours: {INDICES['Global']['S&P 500']['market_hours']}",
                 border_style="dim")
        )
        
        self._safe_print(legend)

    def export_portfolio_to_excel(self, portfolio_name, filename=None):
        """Export portfolio to Excel with formatting"""
        if portfolio_name not in self.portfolios:
            self._safe_print(f"[red]Portfolio '{portfolio_name}' not found![/red]")
            return False
            
        if not filename:
            filename = f"{portfolio_name.replace(' ', '_')}_portfolio.xlsx"
            
        try:
            # Create a styled DataFrame
            portfolio = self.calculate_all_metrics(self.portfolios[portfolio_name])
            
            # Format numeric columns
            format_mapping = {
                'Current Price': '{:,.2f}',
                'Current Value': '{:,.2f}',
                'Profit/Loss': '{:+,.2f}',
                'Profit/Loss %': '{:+.2f}%',
                'Daily Return %': '{:+.2f}%',
                'Daily P/L': '{:+,.2f}'
            }
            
            styled_df = portfolio.style
            for col, fmt in format_mapping.items():
                if col in portfolio.columns:
                    styled_df = styled_df.format({col: fmt})
            
            # Export to Excel
            with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
                styled_df.to_excel(writer, index=False)
                
                # Get workbook and worksheet objects
                workbook = writer.book
                worksheet = writer.sheets['Sheet1']
                
                # Add conditional formatting
                format_green = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
                format_red = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
                
                # Apply to Profit/Loss columns
                last_row = len(portfolio)
                for col in ['Profit/Loss', 'Profit/Loss %', 'Daily Return %', 'Daily P/L']:
                    if col in portfolio.columns:
                        col_idx = portfolio.columns.get_loc(col)
                        worksheet.conditional_format(1, col_idx, last_row, col_idx, {
                            'type': 'cell',
                            'criteria': '>=',
                            'value': 0,
                            'format': format_green
                        })
                        worksheet.conditional_format(1, col_idx, last_row, col_idx, {
                            'type': 'cell',
                            'criteria': '<',
                            'value': 0,
                            'format': format_red
                        })
                
                # Auto-adjust columns
                for i, col in enumerate(portfolio.columns):
                    max_len = max(
                        portfolio[col].astype(str).map(len).max(),
                        len(str(col))
                    )
                    worksheet.set_column(i, i, max_len + 2)
            
            log_portfolio_change("EXPORTED_PORTFOLIO", portfolio_name, details=f"Exported to {filename}")
            self._safe_print(f"[green]Portfolio exported to {filename}[/green]")
            return True
            
        except Exception as e:
            self._safe_print(f"[red]Error exporting portfolio: {e}[/red]")
            return False

def is_market_open(market_type):
    """Check if market is open"""
    if market_type == 'Indian':
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        if now.weekday() >= 5:  # Weekend
            return False
        current_time = now.strftime('%H:%M')
        return '09:15' <= current_time <= '15:30'
    return False

def display_loading_animation(message="Loading..."):
    """Show loading animation"""
    with Progress(
        SpinnerColumn(spinner_name="dots", style="bold blue"),
        TextColumn(f"[bold blue]{message}"),
        transient=True
    ) as progress:
        task = progress.add_task("", total=None)
        time.sleep(0.5)

def log_portfolio_change(action, portfolio_name, stock_name="", details=""):
    """Log changes to audit log with proper formatting"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"{timestamp} | {action} | {portfolio_name} | {stock_name} | {details}\n"
    
    try:
        with open(AUDIT_LOG_FILE, 'a') as f:
            f.write(log_entry)
    except Exception as e:
        with console_lock:
            console.print(f"[red]Error writing to audit log: {e}[/red]")

def validate_date(date_str):
    """Validate date format DD-MM-YYYY"""
    try:
        datetime.strptime(date_str, "%d-%m-%Y")
        return True
    except ValueError:
        return False

def validate_ticker(ticker):
    """Validate stock ticker"""
    try:
        stock = yf.Ticker(ticker)
        # Try to access some basic info to check if ticker is valid
        stock.info.get('shortName', '')
        return True
    except:
        return False

def apply_custom_theme():
    """Configure Plotly theme"""
    pio.templates["custom"] = go.layout.Template(
        layout=go.Layout(
            paper_bgcolor=THEME["background"],
            plot_bgcolor=THEME["background"],
            font=dict(color=THEME["text"], family="Arial", size=14),
            title=dict(x=0.5, font=dict(size=18)),
            xaxis=dict(showgrid=False, title_font=dict(size=14)),
            yaxis=dict(showgrid=False, title_font=dict(size=14)),
            colorway=px.colors.qualitative.Vivid,
            hoverlabel=dict(font_size=14),
            legend=dict(font_size=12)
        )
    )
    pio.templates.default = "custom"

def show_portfolio_overview(portfolio_manager, portfolio_name):
    """Show portfolio overview with correct numbering"""
    portfolio = portfolio_manager.calculate_all_metrics(
        portfolio_manager.portfolios[portfolio_name]
    )
    
    if portfolio.empty:
        console.print(Panel(f"[yellow]Portfolio '{portfolio_name}' is empty![/yellow]",
                          border_style="yellow"))
        return False
    
    # Sort by current value (descending) and reset index
    portfolio = portfolio.sort_values('Current Value', ascending=False).reset_index(drop=True)
    
    # Display overview
    console.print(Panel.fit(
        f"[bold]{portfolio_name.upper()} - CURRENT HOLDINGS[/bold]",
        style="bold white on blue",
        padding=(1, 2))
    )
    
    # Create table with correct numbering
    table = Table(show_header=True, header_style="bold white", box=box.ROUNDED)
    table.add_column("#", style="bold", width=15)
    table.add_column("Stock", style="bold", width=40)
    table.add_column("Ticker", width=25)
    table.add_column("Qty", justify="right", width=18)
    table.add_column("Curr Price", justify="right", width=22)
    table.add_column("Value", justify="right", width=25)
    table.add_column("P/L", justify="right", width=35)
    
    for index, row in portfolio.iterrows():
        pl_color = "green" if row['Profit/Loss'] >= 0 else "red"
        
        table.add_row(
            str(index + 1),  # Display as 1-based index
            row['Stock Name'],
            row['Ticker Symbol'],
            f"{row['Quantity']:,}",
            f"₹{row['Current Price']:,.2f}",
            f"₹{row['Current Value']:,.2f}",
            f"[{pl_color}]₹{row['Profit/Loss']:+,.2f} ({row['Profit/Loss %']:+.2f}%)[/]"
        )
    
    console.print(table)
    return True

def remove_stock_enhanced(portfolio_manager, portfolio_name):
    """Enhanced remove stock flow with correct numbering"""
    while True:
        console.clear()
        
        # Get and sort portfolio consistently by Current Value (descending)
        portfolio = portfolio_manager.calculate_all_metrics(
            portfolio_manager.portfolios[portfolio_name]
        ).sort_values('Current Value', ascending=False).reset_index(drop=True)
        
        if portfolio.empty:
            console.print(Panel(f"[yellow]Portfolio '{portfolio_name}' is empty![/yellow]",
                            border_style="yellow"))
            return False
            
        # Display overview with correct numbering
        console.print(Panel.fit(
            f"[bold]{portfolio_name.upper()} - CURRENT HOLDINGS[/bold]",
            style="bold white on blue",
            padding=(1, 2)))
        
        # Create table with 1-based display numbering
        table = Table(show_header=True, header_style="bold white", box=box.ROUNDED)
        table.add_column("#", style="bold", width=10)
        table.add_column("Stock", style="bold", width=30)
        table.add_column("Ticker", width=15)
        table.add_column("Qty", justify="right", width=10)
        table.add_column("Curr Price", justify="right", width=15)
        table.add_column("Value", justify="right", width=20)
        table.add_column("P/L", justify="right", width=30)
        
        # Display stocks with 1-based indexing
        for display_index, (actual_index, row) in enumerate(portfolio.iterrows(), 1):
            pl_color = "green" if row['Profit/Loss'] >= 0 else "red"
            
            table.add_row(
                str(display_index),
                row['Stock Name'],
                row['Ticker Symbol'],
                f"{row['Quantity']:,}",
                f"₹{row['Current Price']:,.2f}",
                f"₹{row['Current Value']:,.2f}",
                f"[{pl_color}]₹{row['Profit/Loss']:+,.2f} ({row['Profit/Loss %']:+.2f}%)[/]"
            )
        
        console.print(table)
        
        console.print("\n[bold]Select Stock to Remove:[/bold]")
        console.print("Enter stock number (or 'b' to go back)")
        
        while True:
            choice = input("\nYour selection: ").strip().lower()
            
            if choice == 'b':
                return
            
            try:
                display_index = int(choice)
                if 1 <= display_index <= len(portfolio):
                    # Convert display index (1-based) to actual index (0-based)
                    actual_index = display_index - 1
                    selected_stock = portfolio.iloc[actual_index]
                    break
                else:
                    console.print("[red]Invalid selection! Please choose a number from the list.[/red]")
            except ValueError:
                console.print("[red]Please enter a valid number or 'b' to go back[/red]")
        
        # Show confirmation with correct stock details
        console.print(Panel.fit(
            f"[bold]CONFIRM REMOVAL[/bold]\n"
            f"Stock: {selected_stock['Stock Name']} ({selected_stock['Ticker Symbol']})\n"
            f"Quantity: {selected_stock['Quantity']:,}\n"
            f"Current Value: ₹{selected_stock['Current Value']:,.2f}",
            border_style="red"
        ))
        
        confirm = input("\nAre you sure you want to remove this stock? (y/n): ").lower()
        if confirm == 'y':
            # Get the actual index from the original unsorted portfolio
            original_portfolio = portfolio_manager.portfolios[portfolio_name]
            mask = original_portfolio['Ticker Symbol'] == selected_stock['Ticker Symbol']
            
            if mask.any():
                actual_index_to_remove = original_portfolio[mask].index[0]
                
                if portfolio_manager.remove_stock(portfolio_name, actual_index_to_remove):
                    console.print(f"[green]Stock '{selected_stock['Stock Name']}' removed successfully![/green]")
                    
                    # Offer undo option
                    undo = input("Undo this removal? (y/n): ").lower()
                    if undo == 'y':
                        if portfolio_manager.undo_last_removal():
                            console.print("[green]Removal successfully undone![/green]")
                        else:
                            console.print("[red]Failed to undo removal![/red]")
                else:
                    console.print("[red]Failed to remove stock![/red]")
            else:
                console.print("[red]Stock not found in portfolio![/red]")
        else:
            console.print("[yellow]Removal cancelled.[/yellow]")
        
        # Ask if user wants to remove another stock
        another = input("\nRemove another stock? (y/n): ").lower()
        if another != 'y':
            break

def modify_stock_enhanced(portfolio_manager, portfolio_name):
    """Complete stock modification flow with proper quantity, price, name and ticker updates"""
    while True:
        # Refresh and sort portfolio by current value
        portfolio_manager.portfolios[portfolio_name] = portfolio_manager.calculate_all_metrics(
            portfolio_manager.portfolios[portfolio_name]
        ).sort_values('Current Value', ascending=False).reset_index(drop=True)
        
        portfolio = portfolio_manager.portfolios[portfolio_name]
        
        if portfolio.empty:
            console.print(Panel("[yellow]Portfolio is empty![/yellow]", 
                              border_style="yellow"))
            return False
            
        # Display portfolio with current rankings
        console.clear()
        show_portfolio_overview(portfolio_manager, portfolio_name)
        
        # Get user selection
        console.print("\n[bold]Select Stock to Modify:[/bold]")
        console.print("Enter stock number (or 'b' to go back)")
        
        try:
            choice = input("\nYour selection: ").strip().lower()
            if choice == 'b':
                return
                
            display_index = int(choice) - 1  # Convert to 0-based index
            if not 0 <= display_index < len(portfolio):
                raise ValueError
                
            selected_stock = portfolio.iloc[display_index]
            ticker = selected_stock['Ticker Symbol']
            
            # Find actual index in case sorting changed
            actual_index = portfolio[portfolio['Ticker Symbol'] == ticker].index[0]
            
            # Modification menu
            updated_data = {}
            while True:
                console.clear()
                current_stock = portfolio.iloc[actual_index]
                
                # Display current values with fresh data
                current_values = Table.grid(padding=(0, 2))
                current_values.add_column(style="bold", width=25)
                current_values.add_column(width=35)
                
                current_values.add_row("Stock Name:", current_stock['Stock Name'])
                current_values.add_row("Ticker Symbol:", current_stock['Ticker Symbol'])
                current_values.add_row("Quantity:", f"{current_stock['Quantity']:,}")
                current_values.add_row("Avg Price:", f"₹{current_stock['Purchase Price']:,.2f}")
                current_values.add_row("Current Price:", f"₹{current_stock['Current Price']:,.2f}")
                current_values.add_row("Current Value:", f"₹{current_stock['Current Value']:,.2f}")
                current_values.add_row("Position Rank:", f"#{display_index + 1}")
                
                console.print(current_values)
                
                # Modification options
                console.print("\n[bold]Modification Options:[/bold]")
                console.print("1. Update Quantity/Price")
                console.print("2. Change Stock Name/Ticker")
                console.print("3. Edit Purchase Date")
                console.print("4. Change Sector")
                console.print("5. Save Changes")
                console.print("6. Cancel Without Saving")
                
                mod_choice = input("\nEnter choice (1-6): ").strip()
                
                if mod_choice == "1":
                    # Quantity modification flow
                    while True:
                        console.print("\n[bold]Quantity/Price Adjustment:[/bold]")
                        console.print("a. Add shares to position")
                        console.print("r. Reduce current position")
                        console.print("s. Set exact quantity")
                        console.print("p. Change average purchase price")
                        console.print("b. Back to main options")
                        
                        qty_choice = input("\nChoose operation (a/r/s/p/b): ").lower()
                        
                        if qty_choice == 'a':
                            try:
                                add_qty = int(input("Additional shares to purchase: ").strip())
                                if add_qty <= 0:
                                    raise ValueError("Must be positive number")
                                    
                                add_price = float(input("Purchase price per share (₹): ").strip())
                                if add_price <= 0:
                                    raise ValueError("Price must be positive")
                                
                                new_qty = current_stock['Quantity'] + add_qty
                                new_avg = ((current_stock['Quantity'] * current_stock['Purchase Price']) + 
                                          (add_qty * add_price)) / new_qty
                                
                                console.print("\n[bold]Transaction Summary:[/bold]")
                                console.print(f"Current: {current_stock['Quantity']:,} @ ₹{current_stock['Purchase Price']:,.2f}")
                                console.print(f"Adding: {add_qty:,} @ ₹{add_price:,.2f}")
                                console.print(f"New Position: {new_qty:,} @ ₹{new_avg:,.2f}")
                                console.print(f"Estimated New Value: ₹{new_qty * current_stock['Current Price']:,.2f}")
                                
                                confirm = input("\nConfirm this change? (y/n): ").lower()
                                if confirm == 'y':
                                    updated_data.update({
                                        'Quantity': new_qty,
                                        'Purchase Price': new_avg
                                    })
                                    break
                                    
                            except ValueError as e:
                                console.print(f"[red]Error: {e}[/red]")
                                time.sleep(1)
                        
                        elif qty_choice == 'r':
                            try:
                                reduce_qty = int(input("Shares to sell: ").strip())
                                if reduce_qty <= 0:
                                    raise ValueError("Must be positive number")
                                if reduce_qty > current_stock['Quantity']:
                                    raise ValueError(f"Cannot sell more than {current_stock['Quantity']:,}")
                                
                                new_qty = current_stock['Quantity'] - reduce_qty
                                
                                console.print("\n[bold]Transaction Summary:[/bold]")
                                console.print(f"Current: {current_stock['Quantity']:,} shares")
                                console.print(f"Reducing by: {reduce_qty:,} shares")
                                console.print(f"New Quantity: {new_qty:,} shares")
                                console.print(f"Estimated New Value: ₹{new_qty * current_stock['Current Price']:,.2f}")
                                
                                confirm = input("\nConfirm this change? (y/n): ").lower()
                                if confirm == 'y':
                                    updated_data['Quantity'] = new_qty
                                    break
                                    
                            except ValueError as e:
                                console.print(f"[red]Error: {e}[/red]")
                                time.sleep(1)
                        
                        elif qty_choice == 's':
                            try:
                                new_qty = int(input(f"New total quantity (current: {current_stock['Quantity']:,}): ").strip())
                                if new_qty <= 0:
                                    raise ValueError("Must be positive number")
                                
                                if new_qty > current_stock['Quantity']:
                                    add_qty = new_qty - current_stock['Quantity']
                                    add_price = float(input("Purchase price per new share (₹): ").strip())
                                    if add_price <= 0:
                                        raise ValueError("Price must be positive")
                                    
                                    new_avg = ((current_stock['Quantity'] * current_stock['Purchase Price']) + 
                                              (add_qty * add_price)) / new_qty
                                    
                                    updated_data.update({
                                        'Quantity': new_qty,
                                        'Purchase Price': new_avg
                                    })
                                else:
                                    updated_data['Quantity'] = new_qty
                                
                                break
                                
                            except ValueError as e:
                                console.print(f"[red]Error: {e}[/red]")
                                time.sleep(1)
                        
                        elif qty_choice == 'p':
                            try:
                                new_avg_price = float(input(f"New average purchase price (current: ₹{current_stock['Purchase Price']:,.2f}): ").strip())
                                if new_avg_price <= 0:
                                    raise ValueError("Price must be positive")
                                
                                console.print("\n[bold]Price Change Summary:[/bold]")
                                console.print(f"Current: {current_stock['Quantity']:,} @ ₹{current_stock['Purchase Price']:,.2f}")
                                console.print(f"New: {current_stock['Quantity']:,} @ ₹{new_avg_price:,.2f}")
                                console.print(f"Total Investment Change: ₹{(new_avg_price - current_stock['Purchase Price']) * current_stock['Quantity']:,.2f}")
                                
                                confirm = input("\nConfirm this change? (y/n): ").lower()
                                if confirm == 'y':
                                    updated_data['Purchase Price'] = new_avg_price
                                    break
                                    
                            except ValueError as e:
                                console.print(f"[red]Error: {e}[/red]")
                                time.sleep(1)
                        
                        elif qty_choice == 'b':
                            break
                            
                        else:
                            console.print("[red]Invalid choice![/red]")
                            time.sleep(1)
                
                elif mod_choice == "2":
                    # Stock name and ticker modification flow
                    while True:
                        console.print("\n[bold]Stock Identification Update:[/bold]")
                        console.print(f"Current Name: {current_stock['Stock Name']}")
                        console.print(f"Current Ticker: {current_stock['Ticker Symbol']}")
                        console.print("\nOptions:")
                        console.print("n. Change Stock Name")
                        console.print("t. Change Ticker Symbol")
                        console.print("b. Back to main options")
                        
                        id_choice = input("\nChoose operation (n/t/b): ").lower()
                        
                        if id_choice == 'n':
                            new_name = input("Enter new stock name: ").strip()
                            if new_name:
                                console.print(f"\nChange stock name from '{current_stock['Stock Name']}' to '{new_name}'?")
                                confirm = input("Confirm (y/n): ").lower()
                                if confirm == 'y':
                                    updated_data['Stock Name'] = new_name
                                    break
                        
                        elif id_choice == 't':
                            new_ticker = input("Enter new ticker symbol: ").strip().upper()
                            if new_ticker:
                                # Check if ticker already exists in portfolio
                                if new_ticker in portfolio['Ticker Symbol'].values and new_ticker != current_stock['Ticker Symbol']:
                                    console.print(f"[red]Error: Ticker {new_ticker} already exists in portfolio![/red]")
                                    time.sleep(1)
                                    continue
                                    
                                console.print(f"\nChange ticker from '{current_stock['Ticker Symbol']}' to '{new_ticker}'?")
                                confirm = input("Confirm (y/n): ").lower()
                                if confirm == 'y':
                                    updated_data['Ticker Symbol'] = new_ticker
                                    ticker = new_ticker  # Update current ticker reference
                                    break
                        
                        elif id_choice == 'b':
                            break
                            
                        else:
                            console.print("[red]Invalid choice![/red]")
                            time.sleep(1)
                
                elif mod_choice == "3":
                    # Purchase date modification
                    try:
                        console.print("\n[bold]Purchase Date Update:[/bold]")
                        console.print(f"Current Purchase Date: {current_stock['Purchase Date']}")
                        new_date = input("Enter new purchase date (YYYY-MM-DD): ").strip()
                        
                        if new_date:  # Basic date validation
                            from datetime import datetime
                            try:
                                datetime.strptime(new_date, '%Y-%m-%d')
                                console.print(f"\nChange purchase date from {current_stock['Purchase Date']} to {new_date}?")
                                confirm = input("Confirm (y/n): ").lower()
                                if confirm == 'y':
                                    updated_data['Purchase Date'] = new_date
                            except ValueError:
                                console.print("[red]Invalid date format! Use YYYY-MM-DD[/red]")
                                time.sleep(1)
                    except Exception as e:
                        console.print(f"[red]Error updating date: {e}[/red]")
                        time.sleep(1)
                
                elif mod_choice == "4":
                    # Sector modification
                    try:
                        console.print("\n[bold]Sector Update:[/bold]")
                        console.print(f"Current Sector: {current_stock.get('Sector', 'Not specified')}")
                        new_sector = input("Enter new sector: ").strip()
                        
                        if new_sector:
                            console.print(f"\nChange sector to '{new_sector}'?")
                            confirm = input("Confirm (y/n): ").lower()
                            if confirm == 'y':
                                updated_data['Sector'] = new_sector
                    except Exception as e:
                        console.print(f"[red]Error updating sector: {e}[/red]")
                        time.sleep(1)
                
                elif mod_choice == "5":
                    if updated_data:
                        # Apply changes and force save
                        if portfolio_manager.modify_stock(portfolio_name, actual_index, updated_data):
                            portfolio_manager.save_portfolios()
                            
                            # Refresh data and show new position
                            portfolio_manager.load_portfolios()
                            updated_portfolio = portfolio_manager.calculate_all_metrics(
                                portfolio_manager.portfolios[portfolio_name]
                            ).sort_values('Current Value', ascending=False).reset_index(drop=True)
                            
                            # Find the stock again (ticker might have changed)
                            if 'Ticker Symbol' in updated_data:
                                ticker = updated_data['Ticker Symbol']
                            
                            new_index = updated_portfolio[
                                updated_portfolio['Ticker Symbol'] == ticker
                            ].index[0]
                            
                            console.print(f"\n[green]✓ Changes saved successfully![/green]")
                            if 'Stock Name' in updated_data:
                                console.print(f"New Name: {updated_data['Stock Name']}")
                            if 'Ticker Symbol' in updated_data:
                                console.print(f"New Ticker: {updated_data['Ticker Symbol']}")
                            console.print(f"New Position: #{new_index + 1}")
                            console.print(f"New Quantity: {updated_data.get('Quantity', current_stock['Quantity']):,}")
                            console.print(f"New Avg Price: ₹{updated_data.get('Purchase Price', current_stock['Purchase Price']):,.2f}")
                            console.print(f"New Value: ₹{updated_portfolio.iloc[new_index]['Current Value']:,.2f}")
                            
                            # Verify JSON update
                            try:
                                with open(PORTFOLIO_FILE, 'r') as f:
                                    data = json.load(f)
                                    if portfolio_name in data:
                                        for stock in data[portfolio_name]:
                                            if stock['Ticker Symbol'] == ticker:
                                                console.print(f"\nJSON verification:")
                                                if 'Stock Name' in updated_data:
                                                    console.print(f"Name: {stock['Stock Name']}")
                                                console.print(f"Ticker: {stock['Ticker Symbol']}")
                                                console.print(f"Quantity: {stock['Quantity']}")
                                                console.print(f"Purchase Price: {stock['Purchase Price']}")
                            except Exception as e:
                                console.print(f"[yellow]JSON verification failed: {e}[/yellow]")
                            
                            input("\nPress Enter to continue...")
                            break
                        else:
                            console.print("[red]Failed to save changes![/red]")
                            time.sleep(1)
                    else:
                        console.print("[yellow]No changes to save[/yellow]")
                        time.sleep(1)
                        break
                
                elif mod_choice == "6":
                    console.print("[yellow]Changes discarded[/yellow]")
                    time.sleep(1)
                    break
                    
                else:
                    console.print("[red]Invalid choice![/red]")
                    time.sleep(1)
                    
        except ValueError:
            console.print("[red]Invalid selection![/red]")
            time.sleep(1)
            
        # Continue modifying?
        if input("\nModify another stock? (y/n): ").lower() != 'y':
            break

def view_audit_log():
    """Display complete audit log with all actions"""
    if not os.path.exists(AUDIT_LOG_FILE):
        console.print(Panel("[yellow]No audit log found![/yellow]",
                          border_style="yellow"))
        return
        
    try:
        # Read all log entries
        with open(AUDIT_LOG_FILE, 'r') as f:
            log_entries = []
            for line in f:
                if line.strip():
                    # Split into components with proper error handling
                    parts = line.strip().split(" | ", 4)
                    # Ensure we have exactly 5 parts (pad with empty strings if needed)
                    while len(parts) < 5:
                        parts.append("")
                    log_entries.append(parts)
            
            if not log_entries:
                console.print(Panel("[yellow]No audit entries found![/yellow]",
                                  border_style="yellow"))
                return
                
            # Display all entries (newest first)
            log_table = Table(title="\nCOMPLETE AUDIT LOG", 
                            show_header=True, header_style="bold white",
                            box=box.ROUNDED)
            
            log_table.add_column("Timestamp", style="dim", width=20)
            log_table.add_column("Action", width=20)
            log_table.add_column("Portfolio", width=20)
            log_table.add_column("Stock", width=20)
            log_table.add_column("Details", width=40)
            
            for entry in reversed(log_entries):  # Show newest first
                # Color code based on action type
                action = entry[1]
                if action == "ADDED_STOCK":
                    action_style = "green"
                elif action == "REMOVED_STOCK":
                    action_style = "red"
                elif action == "MODIFIED_STOCK":
                    action_style = "yellow"
                else:
                    action_style = "blue"
                
                log_table.add_row(
                    entry[0],
                    f"[{action_style}]{entry[1]}[/]",
                    entry[2],
                    entry[3],
                    entry[4]
                )
                
            console.print(log_table)
    except Exception as e:
        console.print(f"[red]Error reading audit log: {e}[/red]")

def view_portfolio_history(portfolio_name):
    """View complete history for a specific portfolio"""
    if not os.path.exists(AUDIT_LOG_FILE):
        console.print(Panel("[yellow]No audit log found[/yellow]",
                          border_style="yellow"))
        return
    
    try:
        with open(AUDIT_LOG_FILE, 'r') as f:
            entries = []
            for line in f:
                if line.strip():
                    parts = line.strip().split(" | ", 4)
                    # Check if this entry belongs to the requested portfolio
                    if len(parts) > 2 and parts[2] == portfolio_name:
                        # Ensure we have exactly 5 parts
                        while len(parts) < 5:
                            parts.append("")
                        entries.append(parts)
            
            if not entries:
                console.print(Panel(f"[yellow]No history for {portfolio_name}[/yellow]",
                                  border_style="yellow"))
                return
                
            history_table = Table(title=f"\nHistory: {portfolio_name}",
                                box=box.ROUNDED)
            history_table.add_column("Timestamp", style="dim", width=20)
            history_table.add_column("Action", width=20)
            history_table.add_column("Stock", width=20)
            history_table.add_column("Details", width=40)
            
            for entry in reversed(entries):  # Show newest first
                # Color code based on action type
                action = entry[1]
                if action == "ADDED_STOCK":
                    action_style = "green"
                elif action == "REMOVED_STOCK":
                    action_style = "red"
                elif action == "MODIFIED_STOCK":
                    action_style = "yellow"
                else:
                    action_style = "blue"
                
                history_table.add_row(
                    entry[0],
                    f"[{action_style}]{entry[1]}[/]",
                    entry[3],
                    entry[4]
                )
                
            console.print(history_table)
    except Exception as e:
        console.print(f"[red]Error reading history: {e}[/red]")

def stock_operations_menu(portfolio_manager):
    """Stock operations menu with enhanced flow"""
    while True:
        console.clear()
        console.print(Panel(
            "[bold]STOCK OPERATIONS[/bold]",
            border_style="green"
        ))
        
        console.print("1. Add Stock")
        console.print("2. Modify Stock")
        console.print("3. Remove Stock")
        console.print("4. Undo Last Action")
        console.print("5. Redo Last Undo")
        console.print("6. Back to Main Menu")
        
        choice = input("\nEnter choice (1-6): ")
        
        if choice == "1":
            add_stock_menu(portfolio_manager)
        elif choice == "2":
            portfolio_name = select_portfolio(portfolio_manager)
            if portfolio_name:
                modify_stock_enhanced(portfolio_manager, portfolio_name)
        elif choice == "3":
            portfolio_name = select_portfolio(portfolio_manager)
            if portfolio_name:
                remove_stock_enhanced(portfolio_manager, portfolio_name)
        elif choice == "4":
            if portfolio_manager.undo_last_action():
                console.print("[green]Undo successful![/green]")
            else:
                console.print("[yellow]Nothing to undo![/yellow]")
            input("Press Enter to continue...")
        elif choice == "5":
            if portfolio_manager.redo_last_undo():
                console.print("[green]Redo successful![/green]")
            else:
                console.print("[yellow]Nothing to redo![/yellow]")
            input("Press Enter to continue...")
        elif choice == "6":
            break
        else:
            console.print("[red]Invalid choice![/red]")
            time.sleep(1)

def select_portfolio(portfolio_manager):
    """Select a portfolio from list"""
    if not portfolio_manager.portfolios:
        console.print(Panel("[red]No portfolios found![/red]",
                          border_style="red"))
        return None
        
    console.print("\n[bold]Select Portfolio:[/bold]")
    portfolios = list(portfolio_manager.portfolios.keys())
    for i, name in enumerate(portfolios, 1):
        console.print(f"{i}. {name}")
    console.print(f"{len(portfolios)+1}. Back")
    
    while True:
        choice = input("\nEnter portfolio number: ")
        try:
            choice = int(choice)
            if 1 <= choice <= len(portfolios):
                return portfolios[choice-1]
            elif choice == len(portfolios)+1:
                return None
            else:
                console.print("[red]Invalid selection![/red]")
        except ValueError:
            console.print("[red]Please enter a number![/red]")

def add_stock_menu(portfolio_manager):
    """Complete stock addition with proper averaging"""
    portfolio_name = select_portfolio(portfolio_manager)
    if not portfolio_name:
        return
    
    # Get existing tickers for validation
    existing_tickers = portfolio_manager.portfolios[portfolio_name]['Ticker Symbol'].tolist()
    
    while True:
        console.clear()
        console.print(Panel.fit("[bold]ADD NEW STOCK[/bold]", style="bold blue"))
        
        # Stock information collection
        stock_name = input("Stock Name: ").strip()
        if not stock_name:
            console.print("[red]Stock name cannot be empty![/red]")
            continue
            
        ticker = input("Ticker Symbol (e.g., RELIANCE.NS): ").strip().upper()
        if not ticker:
            console.print("[red]Ticker cannot be empty![/red]")
            continue
            
        # Check if ticker exists
        if ticker in existing_tickers:
            console.print("[yellow]Stock already exists - adding to existing position[/yellow]")
            return modify_existing_position(portfolio_manager, portfolio_name, ticker)
            
        # New stock flow
        try:
            qty = int(input("Quantity: ").strip())
            if qty <= 0:
                raise ValueError
                
            price = float(input("Purchase Price: ").strip())
            if price <= 0:
                raise ValueError
                
            date = input("Purchase Date (DD-MM-YYYY): ").strip()
            if not validate_date(date):
                raise ValueError("Invalid date format")
                
            sector = input("Sector (optional): ").strip()
            
            # Confirmation
            console.print(f"\n[bold]Adding {qty} shares of {stock_name} at ₹{price:.2f}[/bold]")
            confirm = input("Confirm? (y/n): ").lower()
            if confirm == 'y':
                stock_data = {
                    'Stock Name': stock_name,
                    'Ticker Symbol': ticker,
                    'Quantity': qty,
                    'Purchase Price': price,
                    'Purchase Date': datetime.strptime(date, "%d-%m-%Y").strftime("%Y-%m-%d"),
                    'Sector': sector
                }
                portfolio_manager.add_stock(portfolio_name, stock_data)
                console.print("[green]Stock added successfully![/green]")
            else:
                console.print("[yellow]Addition cancelled[/yellow]")
                
        except ValueError as e:
            console.print(f"[red]Invalid input: {e}[/red]")
            time.sleep(1)
            continue
            
        another = input("\nAdd another stock? (y/n): ").lower()
        if another != 'y':
            break

def modify_existing_position(portfolio_manager, portfolio_name, ticker):
    """Handle adding to existing positions with proper averaging"""
    portfolio = portfolio_manager.portfolios[portfolio_name]
    stock_index = portfolio[portfolio['Ticker Symbol'] == ticker].index[0]
    current = portfolio.iloc[stock_index]
    
    console.print(f"\nExisting Position: {current['Quantity']} shares @ ₹{current['Purchase Price']:.2f}")
    
    try:
        additional_qty = int(input("Additional Quantity: ").strip())
        if additional_qty <= 0:
            raise ValueError
            
        new_price = float(input("Purchase Price for new shares: ").strip())
        if new_price <= 0:
            raise ValueError
            
        # Calculate weighted average price
        total_qty = current['Quantity'] + additional_qty
        avg_price = ((current['Quantity'] * current['Purchase Price']) + 
                    (additional_qty * new_price)) / total_qty
        
        console.print(f"\nNew average price will be: ₹{avg_price:.2f}")
        confirm = input("Confirm? (y/n): ").lower()
        
        if confirm == 'y':
            updated_data = {
                'Quantity': total_qty,
                'Purchase Price': avg_price
            }
            portfolio_manager.modify_stock(portfolio_name, stock_index, updated_data)
            console.print("[green]Position updated successfully![/green]")
        else:
            console.print("[yellow]Update cancelled[/yellow]")
            
    except ValueError:
        console.print("[red]Invalid quantity/price![/red]")
        time.sleep(1)

def portfolio_management_menu(portfolio_manager):
    """Portfolio management menu"""
    while True:
        console.clear()
        console.print(Panel(
            "[bold]PORTFOLIO MANAGEMENT[/bold]",
            border_style="blue"
        ))
        
        console.print("1. Create New Portfolio")
        console.print("2. Delete Portfolio")
        console.print("3. View All Portfolios")
        console.print("4. Back to Main Menu")
        
        choice = input("\nEnter your choice: ")
        
        if choice == "1":
            name = input("Enter portfolio name: ").strip()
            if name:
                portfolio_manager.create_portfolio(name)
            else:
                console.print("[red]Portfolio name cannot be empty![/red]")
            input("\nPress Enter to continue...")
        elif choice == "2":
            portfolio_name = select_portfolio(portfolio_manager)
            if portfolio_name:
                portfolio_manager.delete_portfolio(portfolio_name)
            input("\nPress Enter to continue...")
        elif choice == "3":
            if not portfolio_manager.portfolios:
                console.print(Panel("[yellow]No portfolios found![/yellow]",
                                  border_style="yellow"))
            else:
                for name in portfolio_manager.portfolios:
                    console.print(f"- {name}")
            input("\nPress Enter to continue...")
        elif choice == "4":
            break
        else:
            console.print("[red]Invalid choice![/red]")
            time.sleep(1)

def dashboard_menu(portfolio_manager):
    """Dashboard viewing menu"""
    while True:
        console.clear()
        console.print(Panel(
            "[bold]DASHBOARD VIEWS[/bold]",
            border_style="yellow"
        ))
        
        console.print("1. Combined Dashboard (All Portfolios)")
        console.print("2. Individual Portfolio Dashboard")
        console.print("3. Performance Visualizations")
        console.print("4. Back to Main Menu")
        
        choice = input("\nEnter your choice: ")
        
        if choice == "1":
            while True:
                action = display_combined_dashboard(portfolio_manager)
                if action == 'r':
                    continue
                elif action == 'v':
                    portfolio_name = select_portfolio(portfolio_manager)
                    if portfolio_name:
                        while True:
                            action = display_individual_dashboard(portfolio_manager, portfolio_name)
                            if action == 'r':
                                continue
                            else:
                                break
                else:
                    break
        elif choice == "2":
            portfolio_name = select_portfolio(portfolio_manager)
            if portfolio_name:
                while True:
                    action = display_individual_dashboard(portfolio_manager, portfolio_name)
                    if action == 'r':
                        continue
                    else:
                        break
        elif choice == "3":
            visualize_portfolio_performance(portfolio_manager)
        elif choice == "4":
            break
        else:
            console.print("[red]Invalid choice![/red]")
            time.sleep(1)

def display_combined_dashboard(portfolio_manager):
    """Display dashboard showing all portfolios with refresh capability"""
    last_refresh_time = datetime.now()
    
    while True:
        # Calculate time since last refresh
        time_since_refresh = datetime.now() - last_refresh_time
        refresh_status = f"Last refresh: {last_refresh_time.strftime('%H:%M:%S')} ({time_since_refresh.seconds}s ago)"
        
        display_loading_animation("Calculating portfolio performance...")
        
        if not portfolio_manager.portfolios:
            console.print(Panel("[red]No portfolios found![/red]", 
                             title="Error", border_style="red"))
            return 'q'
        
        # Clear price cache to force fresh data
        price_cache.cache = {}
        
        # Calculate metrics
        total_metrics = {
            'investment': 0,
            'current_value': 0,
            'profit_loss': 0,
            'profit_loss_pct': 0,
            'daily_pl': 0,
            'daily_return': 0,
            'portfolio_metrics': {}
        }
        
        for name, portfolio in portfolio_manager.portfolios.items():
            portfolio = portfolio_manager.calculate_all_metrics(portfolio[portfolio['Quantity'] > 0])
            if portfolio.empty:
                continue
                
            investment = portfolio['Investment Value'].sum()
            current = portfolio['Current Value'].sum()
            pl = portfolio['Profit/Loss'].sum()
            pl_pct = (pl / investment) * 100 if investment != 0 else 0
            daily_pl = portfolio['Daily P/L'].sum()
            daily_return = (daily_pl / current) * 100 if current != 0 else 0
            
            pl_color = "green" if pl >= 0 else "red"
            daily_color = "green" if daily_pl >= 0 else "red"
            
            total_metrics['portfolio_metrics'][name] = {
                'investment': investment,
                'current_value': current,
                'profit_loss': pl,
                'profit_loss_pct': pl_pct,
                'daily_pl': daily_pl,
                'daily_return': daily_return,
                'pl_color': pl_color,
                'daily_color': daily_color
            }
            
            total_metrics['investment'] += investment
            total_metrics['current_value'] += current
            total_metrics['profit_loss'] += pl
            total_metrics['daily_pl'] += daily_pl
        
        if total_metrics['investment'] != 0:
            total_metrics['profit_loss_pct'] = (total_metrics['profit_loss'] / total_metrics['investment']) * 100
        if total_metrics['current_value'] != 0:
            total_metrics['daily_return'] = (total_metrics['daily_pl'] / total_metrics['current_value']) * 100
        
        total_metrics['pl_color'] = "green" if total_metrics['profit_loss'] >= 0 else "red"
        total_metrics['daily_color'] = "green" if total_metrics['daily_pl'] >= 0 else "red"
        
        # Display dashboard
        console.clear()
        console.print(Panel.fit("[bold]PORTFOLIO DASHBOARD[/bold]", 
                              style="bold white on blue", padding=(1, 2)))
        
        # Refresh status
        console.print(Panel.fit(f"[dim]{refresh_status}[/dim]", 
                              border_style="dim"))
        
        # Summary cards
        summary = Table.grid(expand=True, padding=(0, 2))
        summary.add_column(justify="center", ratio=1)
        summary.add_column(justify="center", ratio=1)
        summary.add_column(justify="center", ratio=1)
        summary.add_column(justify="center", ratio=1)
        
        summary.add_row(
            Panel(f"[bold]Total Invested[/bold]\n[green]₹{total_metrics['investment']:,.2f}[/green]",
                  border_style="green"),
            Panel(f"[bold]Current Value[/bold]\n[blue]₹{total_metrics['current_value']:,.2f}[/blue]",
                  border_style="blue"),
            Panel(f"[bold]Total P/L[/bold]\n[{total_metrics['pl_color']}]₹{total_metrics['profit_loss']:+,.2f}[/]",
                  border_style=total_metrics['pl_color']),
            Panel(f"[bold]Today's P/L[/bold]\n[{total_metrics['daily_color']}]₹{total_metrics['daily_pl']:+,.2f}[/]",
                  border_style=total_metrics['daily_color'])
        )
        console.print(summary)
        
        # Portfolio performance table
        portfolio_table = Table(show_header=True, header_style="bold white", box=box.ROUNDED)
        portfolio_table.add_column("Portfolio", style="bold", width=30)
        portfolio_table.add_column("Invested", justify="right", width=25)
        portfolio_table.add_column("Current", justify="right", width=25)
        portfolio_table.add_column("P/L", justify="right", width=30)
        portfolio_table.add_column("Today", justify="right", width=30)
        
        for name, metrics in total_metrics['portfolio_metrics'].items():
            portfolio_table.add_row(
                name,
                f"₹{metrics['investment']:,.2f}",
                f"₹{metrics['current_value']:,.2f}",
                f"[{metrics['pl_color']}]₹{metrics['profit_loss']:+,.2f} ({metrics['profit_loss_pct']:+.2f}%)[/]",
                f"[{metrics['daily_color']}]₹{metrics['daily_pl']:+,.2f} ({metrics['daily_return']:+.2f}%)[/]"
            )
        
        console.print(portfolio_table)
        
        # Display options
        console.print("\n[bold]Options:[/bold]")
        console.print("[r] Refresh   [v] View Details   [m] Market   [q] Quit")
        
        while True:
            choice = input("\nEnter option: ").lower()
            if choice == 'r':
                last_refresh_time = datetime.now()
                break  # Break out of the input loop to refresh
            elif choice in ['v', 'm', 'q']:
                return choice
            console.print("[red]Invalid option![/red]")


def display_individual_dashboard(portfolio_manager, portfolio_name):
    """Display dashboard for a single portfolio with refresh capability"""
    last_refresh_time = datetime.now()
    
    while True:
        # Calculate time since last refresh
        time_since_refresh = datetime.now() - last_refresh_time
        refresh_status = f"Last refresh: {last_refresh_time.strftime('%H:%M:%S')} ({time_since_refresh.seconds}s ago)"
        
        if portfolio_name not in portfolio_manager.portfolios:
            console.print(Panel(f"[red]Portfolio '{portfolio_name}' not found![/red]",
                              border_style="red"))
            return 'b'
        
        # Clear price cache to force fresh data
        price_cache.cache = {}
        
        portfolio = portfolio_manager.calculate_all_metrics(
            portfolio_manager.portfolios[portfolio_name][portfolio_manager.portfolios[portfolio_name]['Quantity'] > 0]
        )
        
        if portfolio.empty:
            console.print(Panel(f"[yellow]Portfolio '{portfolio_name}' is empty![/yellow]",
                              border_style="yellow"))
            return 'b'
        
        # Calculate totals
        total_investment = portfolio['Investment Value'].sum()
        total_current = portfolio['Current Value'].sum()
        total_pl = portfolio['Profit/Loss'].sum()
        total_pl_pct = (total_pl / total_investment) * 100 if total_investment != 0 else 0
        daily_pl = portfolio['Daily P/L'].sum()
        daily_return = (daily_pl / total_current) * 100 if total_current != 0 else 0
        
        pl_color = "green" if total_pl >= 0 else "red"
        daily_color = "green" if daily_pl >= 0 else "red"
        
        # Display dashboard
        console.clear()
        console.print(Panel.fit(f"[bold]{portfolio_name.upper()} PORTFOLIO[/bold]", 
                              style="bold white on blue", padding=(1, 2)))
        
        # Refresh status
        console.print(Panel.fit(f"[dim]{refresh_status}[/dim]", 
                              border_style="dim"))
        
        # Summary cards
        summary = Table.grid(expand=True, padding=(0, 2))
        summary.add_column(justify="center", ratio=1)
        summary.add_column(justify="center", ratio=1)
        summary.add_column(justify="center", ratio=1)
        summary.add_column(justify="center", ratio=1)
        
        summary.add_row(
            Panel(f"[bold]Total Invested[/bold]\n[green]₹{total_investment:,.2f}[/green]",
                  border_style="green"),
            Panel(f"[bold]Current Value[/bold]\n[blue]₹{total_current:,.2f}[/blue]",
                  border_style="blue"),
            Panel(f"[bold]Total P/L[/bold]\n[{pl_color}]₹{total_pl:+,.2f} ({total_pl_pct:+.2f}%)[/]",
                  border_style=pl_color),
            Panel(f"[bold]Today's P/L[/bold]\n[{daily_color}]₹{daily_pl:+,.2f} ({daily_return:+.2f}%)[/]",
                  border_style=daily_color)
        )
        console.print(summary)
        
        # Stock performance table
        stock_table = Table(show_header=True, header_style="bold white", box=box.ROUNDED)
        stock_table.add_column("Stock", style="bold", width=40)
        stock_table.add_column("Ticker", width=25)
        stock_table.add_column("Qty", justify="right", width=15)
        stock_table.add_column("Price", justify="right", width=25)
        stock_table.add_column("Today %", justify="right", width=25)
        stock_table.add_column("Today ₹", justify="right", width=25)
        stock_table.add_column("P/L", justify="right", width=40)
        
        for _, row in portfolio.iterrows():
            pl_color = "green" if row['Profit/Loss'] >= 0 else "red"
            daily_color = "green" if row['Daily P/L'] >= 0 else "red"
            
            stock_table.add_row(
                row['Stock Name'],
                row['Ticker Symbol'],
                f"{row['Quantity']:,}",
                f"₹{row['Current Price']:,.2f}",
                f"[{daily_color}]{row['Daily Return %']:+.2f}%[/]",
                f"[{daily_color}]{row['Daily P/L']:+,.2f}[/]",
                f"[{pl_color}]₹{row['Profit/Loss']:+,.2f} ({row['Profit/Loss %']:+.2f}%)[/]"
            )
        
        console.print(stock_table)
        
        # Display options
        console.print("\n[bold]Options:[/bold]")
        console.print("[r] Refresh   [b] Back")
        
        while True:
            choice = input("\nEnter option: ").lower()
            if choice == 'r':
                last_refresh_time = datetime.now()
                break  # Break out of the input loop to refresh
            elif choice == 'b':
                return choice
            console.print("[red]Invalid option![/red]")
            
def visualize_portfolio_performance(portfolio_manager):
    """Menu for portfolio visualization options"""
    portfolio_name = select_portfolio(portfolio_manager)
    if not portfolio_name:
        return
        
    portfolio = portfolio_manager.calculate_all_metrics(
        portfolio_manager.portfolios[portfolio_name]
    )
    
    while True:
        console.print(Panel(
            "[bold]VISUALIZATION OPTIONS[/bold]",
            border_style="blue"
        ))
        
        console.print("1. Portfolio Allocation (Pie Chart)")
        console.print("2. Profit/Loss by Stock (Bar Chart)")
        console.print("3. Daily Performance (Bar Chart)")
        console.print("4. Back to Main Menu")
        
        choice = input("\nEnter your choice: ")
        
        if choice == "1":
            portfolio_manager.get_portfolio_performance_chart(portfolio_name, "allocation")
        elif choice == "2":
            portfolio_manager.get_portfolio_performance_chart(portfolio_name, "profit_loss")
        elif choice == "3":
            portfolio_manager.get_portfolio_performance_chart(portfolio_name, "daily")
        elif choice == "4":
            break
        else:
            console.print("[red]Invalid choice![/red]")

def market_analysis_menu(portfolio_manager):
    """Market analysis menu"""
    while True:
        console.clear()
        console.print(Panel(
            "[bold]MARKET ANALYSIS[/bold]",
            border_style="magenta"
        ))
        
        console.print("1. Indian Market Indices")
        console.print("2. Global Market Indices")
        console.print("3. Back to Main Menu")
        
        choice = input("\nEnter your choice: ")
        
        if choice == "1":
            show_market_snapshot(portfolio_manager)
            input("\nPress Enter to continue...")
        elif choice == "2":
            show_market_snapshot(portfolio_manager)
            input("\nPress Enter to continue...")
        elif choice == "3":
            break
        else:
            console.print("[red]Invalid choice![/red]")
            time.sleep(1)

def show_market_snapshot(portfolio_manager):
    """Display enhanced market snapshot"""
    snapshot = portfolio_manager.get_market_snapshot()
    
    if not snapshot:
        console.print(Panel("[red]Failed to fetch market data[/red]",
                          border_style="red"))
        return
    
    # Indian Markets
    indian_table = Table(title="\nIndian Indices", box=box.ROUNDED)
    indian_table.add_column("Index", style="bold")
    indian_table.add_column("Price", justify="right")
    indian_table.add_column("Change", justify="right")
    indian_table.add_column("Status", justify="center")
    
    for name in INDICES['Indian']:
        if name in snapshot:
            data = snapshot[name]
            change_color = "green" if data['change'] >= 0 else "red"
            status_color = "green" if data['status'] == "Open" else "red"
            
            indian_table.add_row(
                name,
                f"₹{data['current']:,.2f}",
                f"[{change_color}]{data['change']:+,.2f} ({data['pct_change']:+.2f}%)[/]",
                f"[{status_color}]{data['status']}[/]"
            )
    
    # Global Markets
    global_table = Table(title="\nGlobal Indices", box=box.ROUNDED)
    global_table.add_column("Index", style="bold")
    global_table.add_column("Price", justify="right")
    global_table.add_column("Change", justify="right")
    global_table.add_column("Status", justify="center")
    
    for name in INDICES['Global']:
        if name in snapshot:
            data = snapshot[name]
            change_color = "green" if data['change'] >= 0 else "red"
            status_color = "green" if data['status'] == "Open" else "red"
            
            global_table.add_row(
                name,
                f"${data['current']:,.2f}",
                f"[{change_color}]{data['change']:+,.2f} ({data['pct_change']:+.2f}%)[/]",
                f"[{status_color}]{data['status']}[/]"
            )
    
    console.print(Panel(indian_table))
    console.print(Panel(global_table))

def data_operations_menu(portfolio_manager):
    """Data import/export menu"""
    while True:
        console.clear()
        console.print(Panel(
            "[bold]DATA OPERATIONS[/bold]",
            border_style="cyan"
        ))
        
        console.print("1. Export Portfolio to Excel")
        console.print("2. Export All Portfolios to Excel")
        console.print("3. View Audit Log")
        console.print("4. Back to Main Menu")
        
        choice = input("\nEnter your choice: ")
        
        if choice == "1":
            export_individual_portfolio(portfolio_manager)
            input("\nPress Enter to continue...")
        elif choice == "2":
            export_all_portfolios(portfolio_manager)
            input("\nPress Enter to continue...")
        elif choice == "3":
            view_audit_log()
            input("\nPress Enter to continue...")
        elif choice == "4":
            break
        else:
            console.print("[red]Invalid choice![/red]")
            time.sleep(1)

def export_individual_portfolio(portfolio_manager):
    """Export single portfolio to Excel"""
    portfolio_name = select_portfolio(portfolio_manager)
    if not portfolio_name:
        return
        
    filename = f"{portfolio_name.replace(' ', '_')}_portfolio.xlsx"
    try:
        portfolio_manager.portfolios[portfolio_name].to_excel(filename, index=False)
        console.print(f"[green]Portfolio exported to {filename}[/green]")
        log_portfolio_change("EXPORTED_PORTFOLIO", portfolio_name, 
                           details=f"Exported to {filename}")
    except Exception as e:
        console.print(f"[red]Error exporting portfolio: {e}[/red]")

def export_all_portfolios(portfolio_manager):
    """Export all portfolios to Excel"""
    if not portfolio_manager.portfolios:
        console.print("[red]No portfolios to export![/red]")
        return
        
    filename = "all_portfolios.xlsx"
    try:
        with pd.ExcelWriter(filename) as writer:
            for name, portfolio in portfolio_manager.portfolios.items():
                portfolio.to_excel(writer, sheet_name=name[:31], index=False)
        console.print(f"[green]All portfolios exported to {filename}[/green]")
        log_portfolio_change("EXPORTED_ALL", "ALL", 
                           details=f"Exported to {filename}")
    except Exception as e:
        console.print(f"[red]Error exporting portfolios: {e}[/red]")

def portfolio_history_menu(portfolio_manager):
    """Complete history menu with all original features"""
    while True:
        console.clear()
        console.print(Panel(
            "[bold]PORTFOLIO HISTORY[/bold]",
            border_style="blue"
        ))
        
        console.print("1. View Full Audit Log")
        console.print("2. Portfolio-Specific History")
        console.print("3. Export History Report")
        console.print("4. Back to Main Menu")
        
        choice = input("\nEnter choice: ")
        
        if choice == "1":
            view_audit_log()
            input("\nPress Enter to continue...")
        elif choice == "2":
            portfolio_name = select_portfolio(portfolio_manager)
            if portfolio_name:
                view_portfolio_history(portfolio_name)
                input("\nPress Enter to continue...")
        elif choice == "3":
            export_history_report()
            input("\nPress Enter to continue...")
        elif choice == "4":
            break
        else:
            console.print("[red]Invalid choice![/red]")
            time.sleep(1)

def export_history_report():
    """Export complete history report"""
    if not os.path.exists(AUDIT_LOG_FILE):
        console.print(Panel("[yellow]No audit log found[/yellow]",
                          border_style="yellow"))
        return
    
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"portfolio_history_{timestamp}.txt"
        
        with open(AUDIT_LOG_FILE, 'r') as f_in, open(filename, 'w') as f_out:
            f_out.write("PORTFOLIO HISTORY REPORT\n")
            f_out.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f_out.write("="*50 + "\n\n")
            
            for line in reversed(f_in.readlines()):  # Newest first
                if line.strip():
                    f_out.write(line)
        
        console.print(f"[green]Report saved to {filename}[/green]")
    except Exception as e:
        console.print(f"[red]Error exporting report: {e}[/red]")

def main():
    """Main application entry point"""
    # Apply plotly theme
    apply_custom_theme()
    
    # Initialize portfolio manager
    portfolio_manager = PortfolioManager()
    
    try:
        while True:
            console.clear()
            console.print(Panel.fit(
                "[bold]STOCK PORTFOLIO MANAGER[/bold]",
                style="bold white on blue",
                padding=(1, 2)
            ))
            
            # Main menu
            menu = Table.grid(expand=True, padding=(0, 2))
            menu.add_column(justify="left", width=30)
            menu.add_column(justify="left", width=30)
            
            menu.add_row(
                Panel("[bold]1. Portfolio Management[/bold]\nCreate/delete portfolios",
                     border_style="blue"),
                Panel("[bold]2. Stock Operations[/bold]\nAdd/edit/remove stocks",
                     border_style="green")
            )
            menu.add_row(
                Panel("[bold]3. Dashboard Views[/bold]\nPerformance analytics",
                     border_style="yellow"),
                Panel("[bold]4. Market Analysis[/bold]\nIndices & trends",
                     border_style="magenta")
            )
            menu.add_row(
                Panel("[bold]5. Visualizations[/bold]\nCharts & graphs",
                     border_style="cyan"),
                Panel("[bold]6. Data Operations[/bold]\nExport/import",
                     border_style="bright_white")
            )
            menu.add_row(
                Panel("[bold]7. History & Audit[/bold]\nChange tracking",
                     border_style="bright_blue"),
                Panel("[bold]8. Exit[/bold]\nSave & quit",
                     border_style="red")
            )
            
            console.print(menu)
            
            choice = input("\nEnter choice (1-8): ").strip()
            
            if choice == "1":
                portfolio_management_menu(portfolio_manager)
            elif choice == "2":
                stock_operations_menu(portfolio_manager)
            elif choice == "3":
                dashboard_menu(portfolio_manager)
            elif choice == "4":
                market_analysis_menu(portfolio_manager)
            elif choice == "5":
                visualize_portfolio_performance(portfolio_manager)
            elif choice == "6":
                data_operations_menu(portfolio_manager)
            elif choice == "7":
                portfolio_history_menu(portfolio_manager)
            elif choice == "8":
                console.print("[green]Saving and exiting...[/green]")
                portfolio_manager.save_portfolios()
                break
            else:
                console.print("[red]Invalid choice![/red]")
                time.sleep(1)
                
    except Exception as e:
        console.print(f"[red]Fatal error: {e}[/red]")
        portfolio_manager.emergency_save()
        sys.exit(1)

if __name__ == "__main__":
    main()
