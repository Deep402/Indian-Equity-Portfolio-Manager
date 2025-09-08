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
import requests
import webbrowser
from urllib.parse import urlparse, parse_qs
import hashlib
import hmac
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
TOKEN_FILE = "kite_token.json"
CACHE_TTL_MINUTES = 15
MAX_WORKERS = 5
REFRESH_INTERVAL = 2  # seconds

# Zerodha Kite API Configuration
KITE_API_KEY = "Your API key"
KITE_API_SECRET = ""  # Replace with your actual API secret
KITE_BASE_URL = "https://api.kite.trade"
KITE_HOLDINGS_ENDPOINT = "/portfolio/holdings"
KITE_POSITIONS_ENDPOINT = "/portfolio/positions"
KITE_TOKEN_URL = "/session/token"

# Dhan (Angel Broking) configuration
DHAN_BASE_URL = "https://api.dhan.co/v2"
DHAN_ACCESS_TOKEN = "Your Dhan Access Token"

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

# Console initialization
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

class DhanAPI:
    """Dhan (Angel Broking) API integration"""
    
    def __init__(self, access_token):
        self.access_token = access_token
        self.base_url = DHAN_BASE_URL

    def get_headers(self):
        return {
            'Content-Type': 'application/json',
            'access-token': self.access_token
        }

    def get_holdings(self):
        """Get portfolio holdings from Dhan"""
        url = f"{self.base_url}/holdings"
        try:
            response = requests.get(url, headers=self.get_headers(), timeout=15)
            if response.status_code == 200:
                return response.json()
            else:
                self._safe_print(f"[error]Dhan API get_holdings HTTP {response.status_code}: {response.text}[/error]")
        except Exception as e:
            self._safe_print(f"[error]Dhan API get_holdings error: {e}[/error]")
        return []

    def get_positions(self):
        """Get portfolio positions from Dhan"""
        url = f"{self.base_url}/positions"
        try:
            response = requests.get(url, headers=self.get_headers(), timeout=15)
            if response.status_code == 200:
                return response.json()
            else:
                self._safe_print(f"[error]Dhan API get_positions HTTP {response.status_code}: {response.text}[/error]")
        except Exception as e:
            self._safe_print(f"[error]Dhan API get_positions error: {e}[/error]")
        return []
    
    def _safe_print(self, message):
        """Thread-safe printing"""
        with console_lock:
            console.print(message)

class ZerodhaKiteAPI:
    """Fixed Zerodha Kite API class with proper authentication"""
    
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = None
        self.base_url = KITE_BASE_URL
        self.load_token()
        
    def load_token(self):
        """Load access token from file"""
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, 'r') as f:
                    token_data = json.load(f)
                    self.access_token = token_data.get('access_token')
                    # Check if token is still valid
                    if self.access_token and self.validate_token():
                        self._safe_print("[green]Found valid saved token[/green]")
                        return True
            except Exception as e:
                self._safe_print(f"[yellow]Error loading saved token: {e}[/yellow]")
        return False
    
    def save_token(self, access_token):
        """Save access token to file"""
        self.access_token = access_token
        try:
            with open(TOKEN_FILE, 'w') as f:
                json.dump({
                    'access_token': access_token,
                    'timestamp': datetime.now().isoformat(),
                    'api_key': self.api_key
                }, f, indent=2)
            self._safe_print("[green]Token saved successfully[/green]")
        except Exception as e:
            self._safe_print(f"[red]Error saving token: {e}[/red]")
    
    def validate_token(self):
        """Validate if the access token is still valid"""
        try:
            url = self.base_url + "/user/profile"
            headers = {
                "X-Kite-Version": "3",
                "Authorization": f"token {self.api_key}:{self.access_token}"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    return True
            return False
        except:
            return False
    
    def generate_checksum(self, request_token):
        """Generate checksum for API request - Multiple methods for compatibility"""
        # Create the message string for checksum
        message = self.api_key + request_token + self.api_secret
        
        # Method 1: Simple SHA256 hash (most common for Zerodha)
        checksum1 = hashlib.sha256(message.encode('utf-8')).hexdigest()
        
        # Method 2: HMAC-SHA256 with API secret as key
        checksum2 = hmac.new(
            self.api_secret.encode('utf-8'),
            (self.api_key + request_token).encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Method 3: HMAC-SHA256 with full message
        checksum3 = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        self._safe_print(f"[yellow]Trying different checksum methods:[/yellow]")
        self._safe_print(f"Method 1 (SHA256): {checksum1}")
        self._safe_print(f"Method 2 (HMAC-partial): {checksum2}")
        self._safe_print(f"Method 3 (HMAC-full): {checksum3}")
        
        # Return Method 1 first (most likely to work)
        return checksum1
    
    def get_access_token(self):
        """Get access token through login flow with improved error handling"""
        if self.access_token and self.validate_token():
            return self.access_token
            
        self._safe_print(Panel(
            "[bold]Zerodha Kite Login - Enhanced Version[/bold]\n\n"
            "1. You will be redirected to Zerodha's login page\n"
            "2. Login with your Zerodha credentials\n"
            "3. Authorize the application\n"
            "4. You will be redirected back to localhost\n"
            "5. Copy the complete redirect URL\n\n"
            "[yellow]Important: Make sure your Kite Connect app redirect URL is set to:[/yellow]\n"
            "[bold]http://127.0.0.1:8000/[/bold]\n\n"
            "[red]If you get connection errors, the redirect URL might be wrong[/red]",
            title="Zerodha Authentication",
            border_style="blue"
        ))
        
        input("Press Enter to open the login page in your browser...")
        
        # Open the login URL
        login_url = f"https://kite.trade/connect/login?api_key={self.api_key}&v=3"
        try:
            webbrowser.open(login_url)
            self._safe_print(f"[green]Opened login URL: {login_url}[/green]")
        except Exception as e:
            self._safe_print(f"[yellow]Could not open browser automatically. Please visit: {login_url}[/yellow]")
        
        # Get the request token from the user
        self._safe_print("\n[bold]After logging in, you'll be redirected to a URL like:[/bold]")
        self._safe_print("http://127.0.0.1:8000/?status=success&request_token=XXXXXXXXXX&action=login&type=login")
        self._safe_print("\n[bold red]Please paste the COMPLETE redirect URL here:[/bold red]")
        
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                redirect_url = input("Redirect URL: ").strip()
                
                if not redirect_url:
                    self._safe_print("[red]URL cannot be empty![/red]")
                    continue
                
                # Extract request token from URL
                parsed_url = urlparse(redirect_url)
                query_params = parse_qs(parsed_url.query)
                request_token = query_params.get('request_token', [None])[0]
                
                if not request_token:
                    self._safe_print("[red]Could not find request_token in the URL![/red]")
                    self._safe_print(f"[yellow]Parsed query parameters: {query_params}[/yellow]")
                    if attempt < max_attempts - 1:
                        self._safe_print("[yellow]Please try again with the complete URL[/yellow]")
                        continue
                    else:
                        return None
                        
                self._safe_print(f"[green]Extracted request token: {request_token}[/green]")
                
                # Exchange request token for access token with multiple checksum attempts
                self._safe_print("[yellow]Exchanging request token for access token...[/yellow]")
                
                # Try different checksum methods
                checksums = []
                
                # Method 1: Simple SHA256 hash
                message = self.api_key + request_token + self.api_secret
                checksum1 = hashlib.sha256(message.encode('utf-8')).hexdigest()
                checksums.append(("SHA256", checksum1))
                
                # Method 2: HMAC-SHA256 with API secret as key (partial message)
                checksum2 = hmac.new(
                    self.api_secret.encode('utf-8'),
                    (self.api_key + request_token).encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()
                checksums.append(("HMAC-partial", checksum2))
                
                # Method 3: HMAC-SHA256 with full message
                checksum3 = hmac.new(
                    self.api_secret.encode('utf-8'),
                    message.encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()
                checksums.append(("HMAC-full", checksum3))
                
                # Try each checksum method
                for method_name, checksum in checksums:
                    self._safe_print(f"[blue]Trying {method_name} checksum: {checksum}[/blue]")
                    
                    payload = {
                        "api_key": self.api_key,
                        "request_token": request_token,
                        "checksum": checksum
                    }
                    
                    headers = {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    
                    try:
                        response = requests.post(
                            self.base_url + KITE_TOKEN_URL,
                            data=payload,
                            headers=headers,
                            timeout=30
                        )
                        
                        self._safe_print(f"[blue]Response Status: {response.status_code}[/blue]")
                        
                        if response.status_code == 200:
                            try:
                                data = response.json()
                                self._safe_print(f"[blue]Response Data: {data}[/blue]")
                                
                                if data.get('status') == 'success':
                                    access_token = data.get('data', {}).get('access_token')
                                    if access_token:
                                        self.save_token(access_token)
                                        self._safe_print(Panel(
                                            f"[bold green]Success! Access Token Generated[/bold green]\n\n"
                                            f"Method used: {method_name}\n"
                                            f"Token: {access_token[:20]}...\n"
                                            f"User ID: {data.get('data', {}).get('user_id', 'N/A')}\n"
                                            f"User Name: {data.get('data', {}).get('user_name', 'N/A')}\n\n"
                                            f"Token has been saved for future use.",
                                            title="Authentication Successful",
                                            border_style="green"
                                        ))
                                        return access_token
                                    else:
                                        self._safe_print("[red]No access token in response![/red]")
                                else:
                                    error_msg = data.get('message', 'Unknown error')
                                    error_type = data.get('error_type', 'Unknown')
                                    self._safe_print(f"[yellow]{method_name} failed: {error_type} - {error_msg}[/yellow]")
                            except json.JSONDecodeError:
                                self._safe_print(f"[yellow]{method_name} - Invalid JSON response: {response.text}[/yellow]")
                        else:
                            self._safe_print(f"[yellow]{method_name} - HTTP Error {response.status_code}: {response.text}[/yellow]")
                            
                    except Exception as e:
                        self._safe_print(f"[yellow]{method_name} - Request error: {e}[/yellow]")
                        continue
                
                # If all methods failed
                self._safe_print("[red]All checksum methods failed. This might be due to:[/red]")
                self._safe_print("1. [yellow]Incorrect API Secret[/yellow]")
                self._safe_print("2. [yellow]Request token expired (tokens expire in 30 minutes)[/yellow]")
                self._safe_print("3. [yellow]Redirect URL mismatch in Kite Connect app settings[/yellow]")
                self._safe_print("4. [yellow]API Key permissions issue[/yellow]")
                
                # Debug information
                self._safe_print(Panel(
                    f"[bold]Debug Information:[/bold]\n"
                    f"API Key: {self.api_key}\n"
                    f"Request Token: {request_token}\n"
                    f"API Secret: {self.api_secret[:10]}...\n"
                    f"Message for checksum: {self.api_key + request_token + self.api_secret[:10]}...\n\n"
                    f"[yellow]Please verify:[/yellow]\n"
                    f"1. API Secret is correct\n"
                    f"2. Redirect URL in Kite app is: http://127.0.0.1:8000/\n"
                    f"3. Request token was copied immediately after login",
                    title="Troubleshooting",
                    border_style="yellow"
                ))
                
                if attempt < max_attempts - 1:
                    self._safe_print(f"[yellow]Attempt {attempt + 1} failed. Trying again...[/yellow]")
                    time.sleep(2)
                    
            except Exception as e:
                self._safe_print(f"[red]Error during authentication: {e}[/red]")
                if attempt < max_attempts - 1:
                    self._safe_print("[yellow]Retrying...[/yellow]")
                    time.sleep(2)
                else:
                    import traceback
                    self._safe_print(f"[red]Full error: {traceback.format_exc()}[/red]")
                    
        return None
    
    def make_request(self, endpoint):
        """Make a request to the Kite API with improved error handling"""
        if not self.access_token:
            self._safe_print("[yellow]No access token found, initiating login...[/yellow]")
            self.access_token = self.get_access_token()
            if not self.access_token:
                return None
                
        try:
            url = self.base_url + endpoint
            headers = {
                "X-Kite-Version": "3",
                "Authorization": f"token {self.api_key}:{self.access_token}",
                "User-Agent": "KiteConnect Python/1.0"
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    return data
                else:
                    self._safe_print(f"[red]API returned error: {data.get('message', 'Unknown error')}[/red]")
                    return None
            elif response.status_code == 403:
                # Token might be expired
                self._safe_print("[yellow]Access token expired, requesting new token...[/yellow]")
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
                self.access_token = None
                return self.make_request(endpoint)  # Retry once
            else:
                self._safe_print(f"[red]HTTP Error {response.status_code}: {response.text}[/red]")
                return None
                
        except requests.exceptions.Timeout:
            self._safe_print("[red]Request timeout - Zerodha API might be slow[/red]")
            return None
        except requests.exceptions.ConnectionError:
            self._safe_print("[red]Connection error - Check your internet connection[/red]")
            return None
        except Exception as e:
            self._safe_print(f"[red]Error making API request: {e}[/red]")
            return None
    
    def get_holdings(self):
        """Get portfolio holdings from Zerodha"""
        self._safe_print("[blue]Fetching holdings from Zerodha...[/blue]")
        data = self.make_request(KITE_HOLDINGS_ENDPOINT)
        if data:
            holdings = data.get("data", [])
            self._safe_print(f"[green]Successfully fetched {len(holdings)} holdings[/green]")
            return holdings
        return []
    
    def get_positions(self):
        """Get portfolio positions from Zerodha"""
        self._safe_print("[blue]Fetching positions from Zerodha...[/blue]")
        data = self.make_request(KITE_POSITIONS_ENDPOINT)
        if data:
            positions = data.get("data", {})
            return positions
        return {}
    
    def get_profile(self):
        """Get user profile information"""
        data = self.make_request("/user/profile")
        if data:
            return data.get("data", {})
        return {}
    
    def _safe_print(self, message):
        """Thread-safe printing"""
        with console_lock:
            console.print(message)

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
                console.print(f"[yellow]Error loading price cache: {e}[/yellow]")
    
    def save_cache(self):
        try:
            serialized = {ticker: (timestamp.isoformat(), price) 
                         for ticker, (timestamp, price) in self.cache.items()}
            with open(CACHE_FILE, 'w') as f:
                json.dump(serialized, f)
        except Exception as e:
            console.print(f"[yellow]Error saving price cache: {e}[/yellow]")

    def get_price(self, ticker):
        if ticker in self.cache:
            cached_time, price = self.cache[ticker]
            if datetime.now() - cached_time < timedelta(minutes=CACHE_TTL_MINUTES):
                return price
        return None
    
    def update_price(self, ticker, price):
        self.cache[ticker] = (datetime.now(), price)

price_cache = PriceCache()

class PortfolioManager:
    """Enhanced portfolio management class with Zerodha and Dhan integration"""
    def __init__(self, kite_api=None, dhan_api=None):
        self.portfolios = {}
        self.undo_stack = []
        self.redo_stack = []
        self.kite_api = kite_api or ZerodhaKiteAPI(KITE_API_KEY, KITE_API_SECRET)
        self.dhan_api = dhan_api or DhanAPI(DHAN_ACCESS_TOKEN)
        self.lock = Lock()
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
                        required_columns = ['Current Price', 'Current Value', 'Profit/Loss', 
                                          'Profit/Loss %', 'Daily Return %', 'Daily P/L']
                        for col in required_columns:
                            if col not in df.columns:
                                df[col] = 0.0
                        
        except Exception as e:
            self._safe_print(f"[red]Error loading portfolios: {e}[/red]")
            if os.path.exists(BACKUP_FILE):
                self._safe_print("[yellow]Attempting to load backup...[/yellow]")
                try:
                    with open(BACKUP_FILE, 'r') as f:
                        data = json.load(f)
                        self.portfolios = {name: pd.DataFrame(records) for name, records in data.items()}
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
    
    def sync_with_zerodha(self, portfolio_name="Zerodha Portfolio"):
        """Sync portfolio with Zerodha holdings with enhanced error handling"""
        self._safe_print(Panel(
            "[bold]Syncing with Zerodha Kite[/bold]\n\n"
            "This will fetch your current holdings and create/update a portfolio.\n"
            "Make sure you have completed the login process if prompted.",
            title="Zerodha Sync",
            border_style="blue"
        ))
        
        # Test API connection first
        profile = self.kite_api.get_profile()
        if profile:
            self._safe_print(f"[green]Connected to Zerodha account: {profile.get('user_name', 'Unknown')} ({profile.get('user_id', 'N/A')})[/green]")
        else:
            self._safe_print("[red]Failed to connect to Zerodha. Please check your authentication.[/red]")
            return False
        
        # Get holdings from Zerodha
        holdings = self.kite_api.get_holdings()
        
        if not holdings:
            self._safe_print("[yellow]No holdings found or failed to fetch holdings[/yellow]")
            return False
        
        # Create or update portfolio
        if portfolio_name not in self.portfolios:
            self.create_portfolio(portfolio_name)
        else:
            # Clear existing data for fresh sync
            self.portfolios[portfolio_name] = pd.DataFrame()
        
        # Convert Zerodha holdings to our format
        stocks_data = []
        for holding in holdings:
            try:
                # Extract relevant data from Zerodha response
                tradingsymbol = holding.get('tradingsymbol', '')
                instrument_token = holding.get('instrument_token', '')
                
                # Create ticker symbol for yfinance
                ticker_symbol = f"{tradingsymbol}.NS" if not tradingsymbol.endswith('.NS') else tradingsymbol
                
                stock_data = {
                    'Stock Name': holding.get('tradingsymbol', ''),
                    'Ticker Symbol': ticker_symbol,
                    'Quantity': float(holding.get('quantity', 0)),
                    'Purchase Price': float(holding.get('average_price', 0)),
                    'Purchase Date': datetime.now().strftime("%Y-%m-%d"),  # Zerodha doesn't provide purchase date
                    'Sector': '',  # Not provided by Zerodha
                    'Investment Value': float(holding.get('quantity', 0)) * float(holding.get('average_price', 0)),
                    'Current Price': 0.0,
                    'Current Value': 0.0,
                    'Profit/Loss': 0.0,
                    'Profit/Loss %': 0.0,
                    'Daily Return %': 0.0,
                    'Daily P/L': 0.0,
                    'Zerodha_Data': holding  # Store original data for reference
                }
                stocks_data.append(stock_data)
                
            except Exception as e:
                self._safe_print(f"[yellow]Error processing holding {holding.get('tradingsymbol', 'Unknown')}: {e}[/yellow]")
                continue
        
        if not stocks_data:
            self._safe_print("[yellow]No valid stock data found in holdings[/yellow]")
            return False
        
        # Update portfolio
        self.portfolios[portfolio_name] = pd.DataFrame(stocks_data)
        
        # Calculate current metrics
        self._safe_print("[blue]Calculating current prices and metrics...[/blue]")
        self.portfolios[portfolio_name] = self.calculate_all_metrics(self.portfolios[portfolio_name])
        
        # Save changes
        self.save_portfolios()
        
        # Log the sync
        log_portfolio_change(
            "ZERODHA_SYNC", 
            portfolio_name, 
            details=f"Synced {len(stocks_data)} holdings"
        )
        
        self._safe_print(Panel(
            f"[bold green]Zerodha Sync Completed Successfully![/bold green]\n\n"
            f"Portfolio: {portfolio_name}\n"
            f"Holdings Synced: {len(stocks_data)}\n"
            f"Total Investment: ₹{self.portfolios[portfolio_name]['Investment Value'].sum():,.2f}\n"
            f"Current Value: ₹{self.portfolios[portfolio_name]['Current Value'].sum():,.2f}",
            title="Sync Results",
            border_style="green"
        ))
        
        return True
    
    def sync_with_dhan(self, portfolio_name="Dhan Portfolio"):
        """Sync portfolio with Dhan holdings"""
        self._safe_print(Panel("Syncing Dhan Portfolio", title="Dhan Sync", border_style="blue"))
        
        holdings = self.dhan_api.get_holdings()
        if not holdings:
            self._safe_print("[warning]No Dhan holdings found or API error[/warning]")
            return False
        
        data = []
        for holding in holdings:
            try:
                ticker = holding.get("tradingSymbol", "")
                qty = float(holding.get("totalQty", 0))
                avg_price = float(holding.get("avgCostPrice", 0))
                
                if ticker and not ticker.endswith(".NS"):
                    ticker += ".NS"
                
                data.append({
                    "Stock Name": ticker,
                    "Ticker Symbol": ticker,
                    "Quantity": qty,
                    "Purchase Price": avg_price,
                    "Purchase Date": datetime.now().strftime("%Y-%m-%d"),
                    "Sector": "",
                    "Investment Value": qty * avg_price,
                    "Current Price": 0.0,
                    "Current Value": 0.0,
                    "Profit/Loss": 0.0,
                    "Profit/Loss %": 0.0,
                    "Daily Return %": 0.0,
                    "Daily P/L": 0.0,
                })
            except Exception as e:
                self._safe_print(f"[yellow]Error processing Dhan holding: {e}[/yellow]")
                continue
        
        df = pd.DataFrame(data)
        df = self.calculate_all_metrics(df)
        
        with self.lock:
            self.portfolios[portfolio_name] = df
            self.save_portfolios()
        
        self._safe_print(f"[success]Dhan portfolio sync complete, {len(df)} stocks loaded[/success]")
        
        # Log the sync
        log_portfolio_change(
            "DHAN_SYNC", 
            portfolio_name, 
            details=f"Synced {len(df)} holdings"
        )
        
        return True
    
    def calculate_all_metrics(self, portfolio):
        """Enhanced calculation with proper error handling"""
        if portfolio.empty:
            return portfolio
            
        # Get live prices
        tickers = portfolio['Ticker Symbol'].unique().tolist()
        tickers = [t for t in tickers if t and t.strip()]  # Remove empty tickers
        
        if not tickers:
            return portfolio
            
        prices = self.get_live_prices_concurrently(tickers)
        
        portfolio = portfolio.copy()
        portfolio['Current Price'] = portfolio['Ticker Symbol'].map(prices).fillna(0.0)
        
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
            try:
                prev_close = self.get_previous_close(row['Ticker Symbol'])
                if prev_close and row['Current Price']:
                    portfolio.at[idx, 'Daily Return %'] = ((row['Current Price'] - prev_close) / prev_close) * 100
                    portfolio.at[idx, 'Daily P/L'] = row['Quantity'] * (row['Current Price'] - prev_close)
                else:
                    portfolio.at[idx, 'Daily Return %'] = 0
                    portfolio.at[idx, 'Daily P/L'] = 0
            except:
                portfolio.at[idx, 'Daily Return %'] = 0
                portfolio.at[idx, 'Daily P/L'] = 0
                
        return portfolio
    
    def get_live_prices_concurrently(self, tickers):
        """Fetch live prices for multiple tickers with improved error handling"""
        prices = {}
        
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
                hist = stock.history(period="1d", interval="1m")
                if not hist.empty:
                    price = hist['Close'].iloc[-1]
                    price_cache.update_price(ticker, price)
                    return ticker, price
                else:
                    # Try with different period
                    hist = stock.history(period="5d")
                    if not hist.empty:
                        price = hist['Close'].iloc[-1]
                        price_cache.update_price(ticker, price)
                        return ticker, price
            except Exception as e:
                console.print(f"[yellow]Warning: Could not fetch price for {ticker}: {e}[/yellow]")
            return ticker, None
        
        # Fetch prices concurrently
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(fetch_price, ticker): ticker for ticker in missing_tickers}
            
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    ticker_result, price = future.result()
                    if price is not None:
                        prices[ticker_result] = price
                except Exception as e:
                    console.print(f"[yellow]Error processing {ticker}: {e}[/yellow]")
        
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
            console.print(f"[yellow]Error fetching previous close for {ticker}: {e}[/yellow]")
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
            
            # Store for undo functionality
            self.push_undo_action('remove', portfolio_name, stock, stock_index)
            
            # Log before removal
            log_portfolio_change(
                "REMOVED_STOCK",
                portfolio_name,
                stock['Stock Name'],
                f"Qty: {stock['Quantity']} @ ₹{stock.get('Current Price', 0):.2f}"
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
                    'Investment Value': action['stock']['Quantity'] * action['stock']['Purchase Price'],
                    'Current Price': 0.0,
                    'Current Value': 0.0,
                    'Profit/Loss': 0.0,
                    'Profit/Loss %': 0.0,
                    'Daily Return %': 0.0,
                    'Daily P/L': 0.0
                }
                
                self.portfolios[action['portfolio']] = pd.concat([
                    self.portfolios[action['portfolio']],
                    pd.DataFrame([new_stock])
                ], ignore_index=True)
                
                self.portfolios[action['portfolio']] = self.calculate_all_metrics(self.portfolios[action['portfolio']])
                
                self.redo_stack.append(action)
                self._safe_print(f"[green]Restored {action['stock']['Stock Name']}[/green]")
                return True
                
            elif action['type'] == 'add':
                # Undo an addition by removing the last added stock
                portfolio = self.portfolios[action['portfolio']]
                if len(portfolio) > 0:
                    last_index = len(portfolio) - 1
                    removed_stock = portfolio.iloc[last_index].to_dict()
                    
                    self.portfolios[action['portfolio']] = portfolio.drop(last_index).reset_index(drop=True)
                    
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
                
                self.portfolios[action['portfolio']] = self.calculate_all_metrics(self.portfolios[action['portfolio']])
                
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
                    'Investment Value': action['stock']['Quantity'] * action['stock']['Purchase Price'],
                    'Current Price': 0.0,
                    'Current Value': 0.0,
                    'Profit/Loss': 0.0,
                    'Profit/Loss %': 0.0,
                    'Daily Return %': 0.0,
                    'Daily P/L': 0.0
                }
                
                self.portfolios[action['portfolio']] = pd.concat([
                    self.portfolios[action['portfolio']],
                    pd.DataFrame([new_stock])
                ], ignore_index=True)
                
                self.portfolios[action['portfolio']] = self.calculate_all_metrics(self.portfolios[action['portfolio']])
                self._safe_print(f"[green]Re-added {action['stock']['Stock Name']}[/green]")
                return True
                
            elif action['type'] == 'remove':
                # Find and remove the stock again
                portfolio = self.portfolios[action['portfolio']]
                mask = portfolio['Ticker Symbol'] == action['stock']['Ticker Symbol']
                if mask.any():
                    index = portfolio[mask].index[0]
                    self.portfolios[action['portfolio']] = portfolio.drop(index).reset_index(drop=True)
                    self._safe_print(f"[green]Re-removed {action['stock']['Stock Name']}[/green]")
                    return True
                return False
                
            elif action['type'] == 'modify':
                current_stock = self.portfolios[action['portfolio']].iloc[action['index']].to_dict()
                
                for col in action['stock']:
                    if col in self.portfolios[action['portfolio']].columns:
                        self.portfolios[action['portfolio']].at[action['index'], col] = action['stock'][col]
                
                self.portfolios[action['portfolio']] = self.calculate_all_metrics(self.portfolios[action['portfolio']])
                self._safe_print(f"[green]Re-applied changes to {action['stock']['Stock Name']}[/green]")
                return True
                
        except Exception as e:
            self._safe_print(f"[red]Error during redo: {e}[/red]")
            return False

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
            table.add_column("Price", width=15)
            table.add_column("Change", width=15)
            table.add_column("Status", width=10)
            table.add_column("Range", width=20)

        # Populate tables
        for name, data in snapshot.items():
            # Determine style based on change
            change_style = "green" if data['change'] >= 0 else "red"
            change_symbol = "▲" if data['change'] >= 0 else "▼"
            
            # Format values
            price_str = f"{data['currency']}{data['current']:,.2f}"
            change_str = f"[{change_style}]{change_symbol} {abs(data['change']):.2f} ({data['pct_change']:+.2f}%)[/]"
            range_str = f"{data['currency']}{data['low']:,.0f} - {data['currency']}{data['high']:,.0f}"
            
            # Add to appropriate table
            if name in INDICES['Indian']:
                indian_table.add_row(name, price_str, change_str, data['status'], range_str)
            else:
                global_table.add_row(name, price_str, change_str, data['status'], range_str)

        # Display tables
        self._safe_print(Panel(indian_table, border_style="blue"))
        self._safe_print(Panel(global_table, border_style="cyan"))
        
        # Add market status summary
        indian_status = "Open" if any(is_market_open('Indian') for name in INDICES['Indian']) else "Closed"
        global_status = "Open" if any(is_market_open('Global') for name in INDICES['Global']) else "Closed"
        
        self._safe_print(Panel.fit(
            f"[bold]Market Status:[/bold] Indian: [{get_status_color(indian_status)}]{indian_status}[/] | "
            f"Global: [{get_status_color(global_status)}]{global_status}[/]",
            border_style="yellow"
        ))

    def _safe_print(self, message):
        """Thread-safe printing"""
        with console_lock:
            console.print(message)
    
    def _get_input(self, prompt):
        """Thread-safe input with validation"""
        with console_lock:
            return input(prompt)

def is_market_open(market_type):
    """Check if market is currently open based on market hours"""
    now = datetime.now(pytz.timezone('Asia/Kolkata'))
    current_time = now.time()
    current_day = now.weekday()  # Monday=0, Sunday=6
    
    # Market is closed on weekends
    if current_day >= 5:  # Saturday or Sunday
        return False
    
    if market_type == 'Indian':
        # Indian market hours: 9:15 AM to 3:30 PM IST
        return (datetime.strptime('09:15', '%H:%M').time() <= current_time <= 
                datetime.strptime('15:30', '%H:%M').time())
    
    elif market_type == 'Global':
        # US market hours: 9:30 AM to 4:00 PM ET (7:00 PM to 1:30 AM IST next day)
        et_time = now.astimezone(pytz.timezone('US/Eastern')).time()
        return (datetime.strptime('09:30', '%H:%M').time() <= et_time <= 
                datetime.strptime('16:00', '%H:%M').time())
    
    return False

def get_status_color(status):
    """Return color based on market status"""
    return "green" if status == "Open" else "red"

def log_portfolio_change(action, portfolio_name, stock_name="", details=""):
    """Log portfolio changes for audit trail"""
    try:
        with open(AUDIT_LOG_FILE, 'a') as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"{timestamp} | {action} | {portfolio_name} | {stock_name} | {details}\n"
            f.write(log_entry)
    except Exception as e:
        console.print(f"[red]Error writing to audit log: {e}[/red]")

def display_portfolio(portfolio_df, portfolio_name):
    """Display portfolio with enhanced formatting"""
    if portfolio_df.empty:
        console.print(Panel("[yellow]Portfolio is empty![/yellow]", 
                          title=f"Portfolio: {portfolio_name}", 
                          border_style="yellow"))
        return
    
    # Create summary table
    summary_table = Table(title=f"Portfolio Summary: {portfolio_name}", **TABLE_STYLE)
    summary_table.add_column("Metric", style="bold")
    summary_table.add_column("Value")
    summary_table.add_column("Daily Change", style="bold")
    
    total_investment = portfolio_df['Investment Value'].sum()
    total_current = portfolio_df['Current Value'].sum()
    total_pnl = portfolio_df['Profit/Loss'].sum()
    total_pnl_pct = (total_pnl / total_investment * 100) if total_investment > 0 else 0
    daily_pnl = portfolio_df['Daily P/L'].sum()
    daily_pnl_pct = (daily_pnl / total_current * 100) if total_current > 0 else 0
    
    summary_table.add_row(
        "Total Investment", 
        f"₹{total_investment:,.2f}", 
        ""
    )
    summary_table.add_row(
        "Current Value", 
        f"₹{total_current:,.2f}", 
        f"{daily_pnl:+,.2f} ({daily_pnl_pct:+.2f}%)"
    )
    summary_table.add_row(
        "Total P/L", 
        f"[{'green' if total_pnl >= 0 else 'red'}]{total_pnl:+,.2f}[/] ({total_pnl_pct:+.2f}%)", 
        ""
    )
    
    console.print(Panel(summary_table, border_style="blue"))
    
    # Create detailed stock table
    stock_table = Table(title="Holdings", **TABLE_STYLE)
    stock_table.add_column("#", style="dim", width=4)
    stock_table.add_column("Stock", style="bold", width=20)
    stock_table.add_column("Qty", width=8)
    stock_table.add_column("Avg Price", width=12)
    stock_table.add_column("Curr Price", width=12)
    stock_table.add_column("Invested", width=12)
    stock_table.add_column("Current", width=12)
    stock_table.add_column("P/L", width=15)
    stock_table.add_column("Daily", width=15)
    
    for idx, row in portfolio_df.iterrows():
        pnl_style = "green" if row['Profit/Loss'] >= 0 else "red"
        daily_style = "green" if row['Daily P/L'] >= 0 else "red"
        
        stock_table.add_row(
            str(idx + 1),
            f"{row['Stock Name']} ({row['Ticker Symbol']})",
            str(int(row['Quantity'])),
            f"₹{row['Purchase Price']:.2f}",
            f"₹{row['Current Price']:.2f}",
            f"₹{row['Investment Value']:,.2f}",
            f"₹{row['Current Value']:,.2f}",
            f"[{pnl_style}]₹{row['Profit/Loss']:+,.2f}[/] ({row['Profit/Loss %']:+.2f}%)",
            f"[{daily_style}]₹{row['Daily P/L']:+,.2f}[/] ({row['Daily Return %']:+.2f}%)"
        )
    
    console.print(Panel(stock_table, border_style="green"))

def get_user_input():
    """Get user input with validation"""
    console.print("\n[bold]Portfolio Management Options:[/bold]")
    console.print("1. [green]View Portfolios[/green]")
    console.print("2. [blue]Create Portfolio[/blue]")
    console.print("3. [yellow]Add Stock[/yellow]")
    console.print("4. [magenta]Modify Stock[/magenta]")
    console.print("5. [red]Remove Stock[/red]")
    console.print("6. [cyan]Delete Portfolio[/cyan]")
    console.print("7. [green]Sync with Zerodha[/green]")
    console.print("8. [blue]Sync with Dhan[/blue]")
    console.print("9. [yellow]Market Snapshot[/yellow]")
    console.print("10. [magenta]Performance Charts[/magenta]")
    console.print("11. [red]Undo Last Action[/red]")
    console.print("12. [cyan]Redo Last Undo[/cyan]")
    console.print("13. [green]Test Zerodha Connection[/green]")
    console.print("14. [blue]Test Dhan Connection[/blue]")
    console.print("0. [bold]Exit[/bold]")
    
    try:
        choice = int(console.input("\n[bold]Enter your choice (0-14): [/bold]"))
        if 0 <= choice <= 14:
            return choice
        else:
            console.print("[red]Invalid choice! Please enter a number between 0 and 14.[/red]")
            return get_user_input()
    except ValueError:
        console.print("[red]Invalid input! Please enter a number.[/red]")
        return get_user_input()

def main():
    """Main application function with enhanced error handling"""
    # Initialize APIs
    kite = ZerodhaKiteAPI(KITE_API_KEY, KITE_API_SECRET)
    dhan = DhanAPI(DHAN_ACCESS_TOKEN)
    manager = PortfolioManager(kite, dhan)
    
    console.print(Panel.fit(
        "[bold blue]💰 Enhanced Portfolio Manager with Zerodha & Dhan Integration[/bold blue]\n"
        "[dim]Track your investments across multiple brokers with real-time data[/dim]\n\n"
        "[yellow]Features:[/yellow]\n"
        "• Zerodha Kite integration with proper authentication\n"
        "• Dhan (Angel Broking) integration\n"
        "• Real-time price updates\n"
        "• Portfolio performance charts\n"
        "• Market snapshot\n"
        "• Undo/Redo functionality",
        border_style="blue"
    ))
    
    # Display market snapshot on startup
    try:
        manager.display_market_snapshot()
    except Exception as e:
        console.print(f"[yellow]Could not fetch market data: {e}[/yellow]")
    
    while True:
        try:
            choice = get_user_input()
            
            if choice == 0:
                console.print("[green]Saving portfolios and exiting...[/green]")
                manager.save_portfolios()
                break
                
            elif choice == 1:
                # View Portfolios
                if not manager.portfolios:
                    console.print("[yellow]No portfolios found![/yellow]")
                    continue
                    
                for name, portfolio in manager.portfolios.items():
                    display_portfolio(manager.calculate_all_metrics(portfolio), name)
                    
            elif choice == 2:
                # Create Portfolio
                name = console.input("Enter portfolio name: ").strip()
                if name:
                    manager.create_portfolio(name)
                else:
                    console.print("[red]Portfolio name cannot be empty![/red]")
                    
            elif choice == 3:
                # Add Stock
                if not manager.portfolios:
                    console.print("[yellow]No portfolios found! Create one first.[/yellow]")
                    continue
                    
                console.print(f"[blue]Available portfolios: {', '.join(manager.portfolios.keys())}[/blue]")
                portfolio_name = console.input("Enter portfolio name: ").strip()
                if portfolio_name not in manager.portfolios:
                    console.print(f"[red]Portfolio '{portfolio_name}' not found![/red]")
                    continue
                    
                stock_name = console.input("Enter stock name: ").strip()
                ticker = console.input("Enter ticker symbol (e.g., RELIANCE.NS): ").strip()
                try:
                    quantity = float(console.input("Enter quantity: "))
                    purchase_price = float(console.input("Enter purchase price: "))
                    purchase_date = console.input("Enter purchase date (YYYY-MM-DD) or press Enter for today: ").strip()
                    if not purchase_date:
                        purchase_date = datetime.now().strftime("%Y-%m-%d")
                    sector = console.input("Enter sector (optional): ").strip()
                    
                    stock_data = {
                        'Stock Name': stock_name,
                        'Ticker Symbol': ticker,
                        'Quantity': quantity,
                        'Purchase Price': purchase_price,
                        'Purchase Date': purchase_date,
                        'Sector': sector
                    }
                    
                    if manager.add_stock(portfolio_name, stock_data):
                        manager.save_portfolios()
                    
                except ValueError:
                    console.print("[red]Invalid input! Quantity and price must be numbers.[/red]")
                    
            elif choice == 4:
                # Modify Stock
                if not manager.portfolios:
                    console.print("[yellow]No portfolios found![/yellow]")
                    continue
                    
                console.print(f"[blue]Available portfolios: {', '.join(manager.portfolios.keys())}[/blue]")
                portfolio_name = console.input("Enter portfolio name: ").strip()
                if portfolio_name not in manager.portfolios:
                    console.print(f"[red]Portfolio '{portfolio_name}' not found![/red]")
                    continue
                    
                portfolio = manager.portfolios[portfolio_name]
                if portfolio.empty:
                    console.print("[yellow]Portfolio is empty![/yellow]")
                    continue
                    
                display_portfolio(portfolio, portfolio_name)
                
                try:
                    stock_index = int(console.input("Enter stock number to modify: ")) - 1
                    if stock_index < 0 or stock_index >= len(portfolio):
                        console.print("[red]Invalid stock number![/red]")
                        continue
                        
                    console.print("\n[bold]Leave field empty to keep current value:[/bold]")
                    updated_data = {}
                    
                    new_quantity = console.input(f"New quantity (current: {portfolio.iloc[stock_index]['Quantity']}): ")
                    if new_quantity:
                        updated_data['Quantity'] = float(new_quantity)
                        
                    new_price = console.input(f"New purchase price (current: {portfolio.iloc[stock_index]['Purchase Price']}): ")
                    if new_price:
                        updated_data['Purchase Price'] = float(new_price)
                        
                    if updated_data:
                        if manager.modify_stock(portfolio_name, stock_index, updated_data):
                            manager.save_portfolios()
                    else:
                        console.print("[yellow]No changes made.[/yellow]")
                        
                except ValueError:
                    console.print("[red]Invalid input![/red]")
                    
            elif choice == 5:
                # Remove Stock
                if not manager.portfolios:
                    console.print("[yellow]No portfolios found![/yellow]")
                    continue
                    
                console.print(f"[blue]Available portfolios: {', '.join(manager.portfolios.keys())}[/blue]")
                portfolio_name = console.input("Enter portfolio name: ").strip()
                if portfolio_name not in manager.portfolios:
                    console.print(f"[red]Portfolio '{portfolio_name}' not found![/red]")
                    continue
                    
                portfolio = manager.portfolios[portfolio_name]
                if portfolio.empty:
                    console.print("[yellow]Portfolio is empty![/yellow]")
                    continue
                    
                display_portfolio(portfolio, portfolio_name)
                
                try:
                    stock_index = int(console.input("Enter stock number to remove: ")) - 1
                    if stock_index < 0 or stock_index >= len(portfolio):
                        console.print("[red]Invalid stock number![/red]")
                        continue
                        
                    stock_name = portfolio.iloc[stock_index]['Stock Name']
                    confirm = console.input(f"Confirm removal of {stock_name}? (y/n): ").lower()
                    
                    if confirm == 'y':
                        if manager.remove_stock(portfolio_name, stock_index):
                            console.print(f"[green]Removed {stock_name}[/green]")
                            manager.save_portfolios()
                    else:
                        console.print("[yellow]Removal cancelled.[/yellow]")
                        
                except ValueError:
                    console.print("[red]Invalid input![/red]")
                    
            elif choice == 6:
                # Delete Portfolio
                if not manager.portfolios:
                    console.print("[yellow]No portfolios found![/yellow]")
                    continue
                    
                console.print(f"[blue]Available portfolios: {', '.join(manager.portfolios.keys())}[/blue]")
                portfolio_name = console.input("Enter portfolio name to delete: ").strip()
                if manager.delete_portfolio(portfolio_name):
                    manager.save_portfolios()
                
            elif choice == 7:
                # Sync with Zerodha
                portfolio_name = console.input("Enter portfolio name for Zerodha sync (or press Enter for 'Zerodha Portfolio'): ").strip()
                if not portfolio_name:
                    portfolio_name = "Zerodha Portfolio"
                    
                if manager.sync_with_zerodha(portfolio_name):
                    manager.save_portfolios()
            
            elif choice == 8:
                # Sync with Dhan
                portfolio_name = console.input("Enter portfolio name for Dhan sync (or press Enter for 'Dhan Portfolio'): ").strip()
                if not portfolio_name:
                    portfolio_name = "Dhan Portfolio"
                    
                if manager.sync_with_dhan(portfolio_name):
                    manager.save_portfolios()
                
            elif choice == 9:
                # Market Snapshot
                manager.display_market_snapshot()
                
            elif choice == 10:
                # Performance Charts
                if not manager.portfolios:
                    console.print("[yellow]No portfolios found![/yellow]")
                    continue
                    
                console.print(f"[blue]Available portfolios: {', '.join(manager.portfolios.keys())}[/blue]")
                portfolio_name = console.input("Enter portfolio name: ").strip()
                if portfolio_name not in manager.portfolios:
                    console.print(f"[red]Portfolio '{portfolio_name}' not found![/red]")
                    continue
                    
                console.print("\n[bold]Chart Types:[/bold]")
                console.print("1. [blue]Allocation Pie Chart[/blue]")
                console.print("2. [green]Profit/Loss Bar Chart[/green]")
                console.print("3. [yellow]Daily Performance Chart[/yellow]")
                console.print("4. [cyan]Historical Performance Chart[/cyan]")
                
                try:
                    chart_choice = int(console.input("Enter chart type (1-4): "))
                    chart_types = {
                        1: "allocation",
                        2: "profit_loss",
                        3: "daily",
                        4: "historical"
                    }
                    
                    if chart_choice in chart_types:
                        manager.get_portfolio_performance_chart(portfolio_name, chart_types[chart_choice])
                    else:
                        console.print("[red]Invalid choice![/red]")
                except ValueError:
                    console.print("[red]Invalid input![/red]")
                    
            elif choice == 11:
                # Undo Last Action
                if manager.undo_last_action():
                    manager.save_portfolios()
                    
            elif choice == 12:
                # Redo Last Undo
                if manager.redo_last_undo():
                    manager.save_portfolios()
                    
            elif choice == 13:
                # Test Zerodha Connection
                console.print("[blue]Testing Zerodha connection...[/blue]")
                
                # Test basic connection
                profile = manager.kite_api.get_profile()
                if profile:
                    console.print(Panel(
                        f"[bold green]Connection Successful![/bold green]\n\n"
                        f"User ID: {profile.get('user_id', 'N/A')}\n"
                        f"User Name: {profile.get('user_name', 'N/A')}\n"
                        f"Email: {profile.get('email', 'N/A')}\n"
                        f"Broker: {profile.get('broker', 'N/A')}\n"
                        f"Exchanges: {', '.join(profile.get('exchanges', []))}",
                        title="Zerodha Profile",
                        border_style="green"
                    ))
                    
                    # Test holdings fetch
                    console.print("[blue]Testing holdings fetch...[/blue]")
                    holdings = manager.kite_api.get_holdings()
                    console.print(f"[green]Successfully fetched {len(holdings)} holdings[/green]")
                    
                    if holdings:
                        console.print("\n[bold]Sample Holdings:[/bold]")
                        for i, holding in enumerate(holdings[:3]):  # Show first 3
                            console.print(f"{i+1}. {holding.get('tradingsymbol', 'N/A')} - Qty: {holding.get('quantity', 0)} @ ₹{holding.get('average_price', 0):.2f}")
                        if len(holdings) > 3:
                            console.print(f"... and {len(holdings) - 3} more")
                else:
                    console.print("[red]Connection failed! Please check your authentication.[/red]")
                    console.print("[yellow]Try option 7 to re-authenticate with Zerodha.[/yellow]")
            
            elif choice == 14:
                # Test Dhan Connection
                console.print("[blue]Testing Dhan connection...[/blue]")
                
                holdings = manager.dhan_api.get_holdings()
                if holdings:
                    console.print(Panel(
                        f"[bold green]Dhan Connection Successful![/bold green]\n\n"
                        f"Successfully fetched {len(holdings)} holdings",
                        title="Dhan Connection",
                        border_style="green"
                    ))
                    
                    if holdings:
                        console.print("\n[bold]Sample Holdings:[/bold]")
                        for i, holding in enumerate(holdings[:3]):  # Show first 3
                            ticker = holding.get("tradingSymbol", "N/A")
                            qty = holding.get("totalQty", 0)
                            avg_price = holding.get("avgCostPrice", 0)
                            console.print(f"{i+1}. {ticker} - Qty: {qty} @ ₹{avg_price:.2f}")
                        if len(holdings) > 3:
                            console.print(f"... and {len(holdings) - 3} more")
                else:
                    console.print("[red]Dhan connection failed! Please check your access token.[/red]")
                    
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupt received, saving portfolios...[/yellow]")
            manager.emergency_save()
            break
        except Exception as e:
            console.print(f"[red]Unexpected error: {e}[/red]")
            console.print("[yellow]Please try again or restart the application.[/yellow]")

if __name__ == "__main__":
    main()
