import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import yfinance as yf
from datetime import datetime, timedelta
import json
import os
import sys
import time
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import plotly.subplots as sp
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import pytz
from rich.style import Style
from rich.console import Console
from rich.theme import Theme



# Initialize rich console with larger font size
console = Console(style=None, width=120)

# File to store portfolios data
PORTFOLIO_FILE = "portfolios.json"

# Create a thread-safe console
console_lock = Lock()

def safe_print(message, style=None):
    """Thread-safe printing with larger font"""
    with console_lock:
        if style:
            console.print(message, style=style + " bold" if "bold" not in style else style)
        else:
            console.print(message, style="bold")

# Custom theme with larger padding to simulate bigger text
custom_theme = Theme({
    "header": "bold #4CC9F0",
    "menu": "bold bright_white on #1A1B26",
    "option": "bold bright_white",
    "description": "dim bright_white",
    "prompt": "bold #4CC9F0"
})

# Create console with wider spacing
console = Console(
    theme=custom_theme,
    width=100,
    highlight=False,
    soft_wrap=True
)

# Enhanced color scheme
THEME = {
    "primary": "white",       # Bright cyan
    "secondary": "Blue",     # Bright pink
    "success": "#4AD66D",       # Green
    "warning": "#F7B801",       # Yellow
    "danger": "#EF233C",        # Red
    "info": "#7209B7",          # Purple
    "light": "#F8F9FA",         # Light gray
    "dark": "#212529",          # Dark gray
    "background": "#1A1B26",    # Dark background
    "text": "#E0E0E0"           # Light text
}

# Apply custom theme for Plotly with larger fonts
def apply_custom_theme():
    pio.templates["custom"] = go.layout.Template(
        layout=go.Layout(
            paper_bgcolor=THEME["background"],
            plot_bgcolor=THEME["background"],
            font=dict(color=THEME["text"], family="Arial", size=24),  # Increased font size
            title=dict(x=0.5, font=dict(size=34)),  # Larger title
            xaxis=dict(showgrid=False, title_font=dict(size=18)),  # Larger axis titles
            yaxis=dict(showgrid=False, title_font=dict(size=18)),
            colorway=px.colors.qualitative.Vivid,  # More vibrant colors
            hoverlabel=dict(font_size=18),  # Larger hover text
            legend=dict(font_size=16, orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)  # Better legend
        )
    )
    pio.templates.default = "custom"

apply_custom_theme()

def normalize_portfolio_name(name):
    return name.strip().lower()

def get_live_prices_concurrently(tickers):
    """Fetch live prices for multiple tickers concurrently using threads"""
    prices = {}
    
    def fetch_price(ticker):
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d")
            if not hist.empty:
                return ticker, hist['Close'].iloc[-1]
        except Exception as e:
            safe_print(f"[{THEME['danger']}]Error fetching price for {ticker}: {e}[/]", style="bold")
        return ticker, None
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_price, ticker): ticker for ticker in tickers}
        
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                ticker, price = future.result()
                prices[ticker] = price
            except Exception as e:
                safe_print(f"[{THEME['danger']}]Error processing {ticker}: {e}[/]", style="bold")
                prices[ticker] = None
    
    return prices

def get_previous_close(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="2d")
        if len(hist) < 2:
            return None
        return hist['Close'].iloc[-2]
    except Exception as e:
        safe_print(f"[{THEME['danger']}]Error fetching previous close for {ticker}: {e}[/]", style="bold")
        return None

def validate_date(date_str):
    try:
        datetime.strptime(date_str, "%d-%m-%Y")
        return True
    except ValueError:
        return False

def validate_ticker(ticker):
    try:
        stock = yf.Ticker(ticker)
        # Try to access some basic info to check if ticker is valid
        stock.info.get('shortName', '')
        return True
    except:
        return False

def calculate_metrics(portfolio):
    """Calculate portfolio metrics using multi-threading"""
    if portfolio.empty:
        return portfolio
    
    # Get unique tickers
    tickers = portfolio['Ticker Symbol'].unique().tolist()
    
    # Fetch all prices concurrently
    with console.status(f"[{THEME['primary']} bold]Fetching live prices...[/]", spinner="dots"):
        prices = get_live_prices_concurrently(tickers)
    
    # Calculate metrics for each row
    for index, row in portfolio.iterrows():
        ticker = row['Ticker Symbol']
        live_price = prices.get(ticker)
        
        if live_price is not None:
            portfolio.at[index, 'Current Price'] = round(live_price, 2)
            portfolio.at[index, 'Current Value'] = row['Quantity'] * live_price
            portfolio.at[index, 'Profit/Loss'] = portfolio.at[index, 'Current Value'] - row['Investment Value']
            if row['Investment Value'] != 0:
                portfolio.at[index, 'Profit/Loss %'] = (portfolio.at[index, 'Profit/Loss'] / row['Investment Value']) * 100
            else:
                portfolio.at[index, 'Profit/Loss %'] = 0
        else:
            portfolio.at[index, 'Current Price'] = 0.0
            portfolio.at[index, 'Current Value'] = 0.0
            portfolio.at[index, 'Profit/Loss'] = 0.0
            portfolio.at[index, 'Profit/Loss %'] = 0.0
    
    return portfolio

def calculate_daily_returns(portfolio):
    for index, row in portfolio.iterrows():
        ticker = row['Ticker Symbol']
        current_price = row['Current Price']
        prev_close = get_previous_close(ticker)
        
        if current_price is not None and prev_close is not None and prev_close != 0:
            daily_return = (current_price - prev_close) / prev_close * 100
            portfolio.at[index, 'Daily Return %'] = daily_return
            portfolio.at[index, 'Daily P/L'] = row['Quantity'] * (current_price - prev_close)
        else:
            portfolio.at[index, 'Daily Return %'] = 0
            portfolio.at[index, 'Daily P/L'] = 0
    return portfolio

def refresh_dashboard(portfolios, portfolio_name=None):
    try:
        while True:
            console.clear()
            if portfolio_name:
                user_input = display_individual_dashboard(portfolio_name, portfolios[portfolio_name])
            else:
                user_input = display_combined_dashboard(portfolios)
            
            if user_input != 'r':
                break
            time.sleep(2)  # Add small delay between refreshes
    except KeyboardInterrupt:
        console.print("\n[{THEME['success']} bold]Stopped refreshing dashboard.[/]")

def display_loading_animation(message="Loading portfolio data..."):
    """Display a loading animation with rich"""
    with Progress(
        SpinnerColumn(spinner_name="dots", style=f"{THEME['primary']} bold"),
        TextColumn(f"[{THEME['primary']} bold]{{task.description}}[/]"),
        transient=True,
    ) as progress:
        progress.add_task(description=message, total=None)
        time.sleep(1.5)  # Simulate loading time

def calculate_total_metrics(portfolios):
    """Calculate metrics for all portfolios (excluding zero quantity stocks)"""
    total_metrics = {
        'investment': 0,
        'current_value': 0,
        'profit_loss': 0,
        'profit_loss_pct': 0,
        'daily_pl': 0,
        'daily_return': 0,
        'portfolio_metrics': {}
    }
    
    for name, portfolio in portfolios.items():
        # Filter out zero quantity stocks
        portfolio = portfolio[portfolio['Quantity'] > 0]
        if portfolio.empty:
            continue
            
        portfolio = calculate_metrics(portfolio)
        portfolio = calculate_daily_returns(portfolio)
        
        investment = portfolio['Investment Value'].sum()
        current = portfolio['Current Value'].sum()
        pl = portfolio['Profit/Loss'].sum()
        pl_pct = (pl / investment) * 100 if investment != 0 else 0
        daily_pl = portfolio['Daily P/L'].sum()
        daily_return = (daily_pl / current) * 100 if current != 0 else 0
        
        # Determine colors
        pl_color = THEME['success'] if pl >= 0 else THEME['danger']
        daily_color = THEME['success'] if daily_pl >= 0 else THEME['danger']
        
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
        
        # Update totals
        total_metrics['investment'] += investment
        total_metrics['current_value'] += current
        total_metrics['profit_loss'] += pl
        total_metrics['daily_pl'] += daily_pl
    
    # Calculate percentages
    if total_metrics['investment'] != 0:
        total_metrics['profit_loss_pct'] = (total_metrics['profit_loss'] / total_metrics['investment']) * 100
    if total_metrics['current_value'] != 0:
        total_metrics['daily_return'] = (total_metrics['daily_pl'] / total_metrics['current_value']) * 100
    
    # Determine total colors
    total_metrics['pl_color'] = THEME['success'] if total_metrics['profit_loss'] >= 0 else THEME['danger']
    total_metrics['daily_color'] = THEME['success'] if total_metrics['daily_pl'] >= 0 else THEME['danger']
    
    return total_metrics

def show_market_snapshot():
    """Display a quick market snapshot with enhanced UI"""
    try:
        # Get key indices
        nifty = yf.Ticker("^NSEI").history(period="1d")['Close'].iloc[-1]
        sensex = yf.Ticker("^BSESN").history(period="1d")['Close'].iloc[-1]
        nasdaq = yf.Ticker("^IXIC").history(period="1d")['Close'].iloc[-1]
        
        snapshot = Table(show_header=False, box=box.ROUNDED, border_style=THEME['primary'], 
                        padding=(1, 4), expand=True)
        snapshot.add_column(style=f"bold {THEME['light']}", justify="center", min_width=30)
        snapshot.add_column(style=f"bold {THEME['light']}", justify="center", min_width=30)
        
        snapshot.add_row(
            f"[{THEME['primary']}]Nifty 50:[/] [bold {THEME['success']}]₹{nifty:,.2f}[/]",
            f"[{THEME['primary']}]S&P 500:[/] [bold {THEME['success']}]${nasdaq:,.2f}[/]"
        )
        snapshot.add_row(
            f"[{THEME['primary']}]Sensex:[/] [bold {THEME['success']}]₹{sensex:,.2f}[/]",
            f"[{THEME['primary']}]Gold:[/] [bold {THEME['warning']}]₹{get_commodity_price('GC=F')}/oz[/]"
        )
        
        # Wrap in a panel for better visual
        console.print(Panel(snapshot, title="[bold]Market Snapshot[/]", 
                          border_style=THEME['primary'], padding=(1, 2)))
    except Exception as e:
        console.print(Panel(f"[{THEME['danger']}]Couldn't fetch market data: {str(e)}[/]", 
                          title="[bold]Error[/]", border_style=THEME['danger']))

def get_commodity_price(ticker):
    try:
        commodity = yf.Ticker(ticker)
        hist = commodity.history(period="1d")
        return f"{hist['Close'].iloc[-1]:,.2f}" if not hist.empty else "N/A"
    except:
        return "N/A"

# Add to the constants section
AUDIT_LOG_FILE = "portfolio_audit.log"

def log_portfolio_change(action, portfolio_name, stock_name="", details=""):
    """Log all portfolio changes to a file with consistent 5-field format"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"{timestamp} | {action} | {portfolio_name} | {stock_name} | {details}\n"
    
    with open(AUDIT_LOG_FILE, "a") as f:
        f.write(log_entry)
        
def show_audit_log():
    """Display the audit log in a formatted table"""
    if not os.path.exists(AUDIT_LOG_FILE):
        console.print("[yellow]No audit records found.[/yellow]")
        return

    with open(AUDIT_LOG_FILE, "r") as f:
        log_entries = f.readlines()

    if not log_entries:
        console.print("[yellow]No audit records found.[/yellow]")
        return

    # Create a rich table
    log_table = Table(
        title="\n📜 Portfolio Audit Log",
        show_header=True,
        header_style="bold bright_white",
        box=box.ROUNDED,
        border_style="bright_blue"
    )
    
    log_table.add_column("Timestamp", style="dim", width=20)
    log_table.add_column("Action", style="bright_cyan", width=15)
    log_table.add_column("Portfolio", style="bright_green", width=20)
    log_table.add_column("Stock", style="bright_yellow", width=20)
    log_table.add_column("Details", style="bright_white", min_width=30)

    for entry in reversed(log_entries[-100:]):  # Show last 100 entries in reverse order
        parts = entry.strip().split(" | ", 4)
        if len(parts) == 5:
            log_table.add_row(*parts)

    console.print(log_table)
    console.print("\n[dim]Note: Showing last 100 entries. Full log available in 'portfolio_audit.log'[/dim]")
    
def display_combined_dashboard(portfolios):
    """Display an enhanced combined dashboard with multiple sections"""
    display_loading_animation("Calculating portfolio performance...")
    
    if not portfolios:
        console.print(Panel("[bold red]⚠️ No portfolios found. Create one first![/]", 
                          border_style=THEME['danger']))
        return 'q'

    # Calculate all metrics first
    total_metrics = calculate_total_metrics(portfolios)
    
    # Clear screen and build dashboard
    console.clear()
    
    # Dashboard header with improved styling
    console.print(Panel.fit(
        "[bold]📈 PORTFOLIO DASHBOARD[/]", 
        style=f"bold {THEME['light']} on {THEME['dark']}",
        padding=(1, 2)
    ))
    console.print(f"[{THEME['primary']}]{'━' * 60}[/]\n")
    
    # Enhanced summary cards with better spacing
    summary = Table.grid(expand=True, padding=(0, 2))
    summary.add_column(justify="center", ratio=1)
    summary.add_column(justify="center", ratio=1)
    summary.add_column(justify="center", ratio=1)
    summary.add_column(justify="center", ratio=1)
    
    # Modified summary panels to show full values
    summary.add_row(
        Panel(
            f"[bold {THEME['light']}]Total Invested[/]\n[bold {THEME['success']}]₹{total_metrics['investment']:,.2f}[/]",
            border_style=THEME['success'],
            padding=(1, 5),
            style=f"on {THEME['dark']}"
        ),
        Panel(
            f"[bold {THEME['light']}]Current Value[/]\n[bold {THEME['primary']}]₹{total_metrics['current_value']:,.2f}[/]",
            border_style=THEME['primary'],
            padding=(1, 5),
            style=f"on {THEME['dark']}"
        ),
        Panel(
            f"[bold {THEME['light']}]Total P/L[/]\n[bold {total_metrics['pl_color']}]₹{total_metrics['profit_loss']:+,.2f} ({total_metrics['profit_loss_pct']:+.2f}%)[/]",
            border_style=total_metrics['pl_color'],
            padding=(1, 5),
            style=f"on {THEME['dark']}"
        ),
        Panel(
            f"[bold {THEME['light']}]Today's P/L[/]\n[bold {total_metrics['daily_color']}]₹{total_metrics['daily_pl']:+,.2f} ({total_metrics['daily_return']:+.2f}%)[/]",
            border_style=total_metrics['daily_color'],
            padding=(1, 5),
            style=f"on {THEME['dark']}"
        )
    )
    console.print(summary)
    
    # Portfolio performance table with improved styling
    console.print(f"\n[bold {THEME['secondary']}]⟦ PORTFOLIO PERFORMANCE ⟧[/]")
    portfolio_table = Table(
        title=None,
        show_header=True,
        header_style=f"bold {THEME['light']} on {THEME['dark']}",
        box=box.ROUNDED,
        border_style=THEME['primary'],
        show_lines=True,
        padding=(0, 1),
        expand=True,
        width=None  # Allow table to use full available width
    )
    
    # Configure columns with sufficient width to show full values
    columns = [
        ("Portfolio", THEME['primary'], 35),
        ("Invested", THEME['success'], 32),  # Increased width
        ("Current", THEME['primary'], 32),   # Increased width
        ("Total P/L", THEME['info'], 38),    # Increased width
        ("Today P/L", THEME['warning'], 38), # Increased width
        ("Status", THEME['light'], 32)
    ]
    
    for col in columns:
        portfolio_table.add_column(
            col[0], 
            style=f"bold {col[1]}", 
            width=col[2], 
            justify="right" if col[0] != "Portfolio" else "left"
        )
    
    # Add portfolio rows with full values
    for portfolio_name, metrics in total_metrics['portfolio_metrics'].items():
        portfolio_table.add_row(
            f"[bold {THEME['light']}]{portfolio_name}[/]",
            f"₹{metrics['investment']:,.2f}",
            f"₹{metrics['current_value']:,.2f}",
            f"[{metrics['pl_color']}]₹{metrics['profit_loss']:+,.2f} ({metrics['profit_loss_pct']:+.2f}%)[/]",
            f"[{metrics['daily_color']}]₹{metrics['daily_pl']:+,.2f} ({metrics['daily_return']:+.2f}%)[/]",
            f"[{THEME['success']}]↑[/]" if metrics['profit_loss'] > 0 else f"[{THEME['danger']}]↓[/]"
        )
    
    console.print(portfolio_table)
    
    # Market snapshot section with better integration
    console.print(f"\n[bold {THEME['secondary']}]⟦ MARKET SNAPSHOT ⟧[/]")
    show_market_snapshot()
    
    # Footer with options in a more organized way
    console.print(f"\n[{THEME['primary']}]{'━' * 60}[/]")
    options = Table.grid(expand=True, padding=(0, 2))
    options.add_column(justify="left")
    options.add_column(justify="center")
    options.add_column(justify="right")
    
    options.add_row(
        f"[{THEME['warning']}][r][/] Refresh",
        f"[{THEME['primary']}][v][/] View Details",
        f"[{THEME['info']}][m][/] Market Analysis",
        f"[{THEME['danger']}][q][/] Quit"
    )
    console.print(options)
    
    return input("\nEnter option: ").lower()

def display_individual_dashboard(portfolio_name, portfolio):
    """Display enhanced individual portfolio dashboard"""
     # Filter out zero quantity stocks
    portfolio = portfolio[portfolio['Quantity'] > 0]
    if portfolio.empty:
        console.print(Panel(f"[{THEME['warning']}]Portfolio '{portfolio_name}' is empty.[/]", 
                          border_style=THEME['warning']))
        return 'b'
    display_loading_animation(f"Analyzing {portfolio_name}...")
    
    # Calculate metrics
    portfolio = calculate_metrics(portfolio)
    portfolio = calculate_daily_returns(portfolio)
    
    # Prepare data
    total_investment = portfolio['Investment Value'].sum()
    total_current = portfolio['Current Value'].sum()
    total_pl = portfolio['Profit/Loss'].sum()
    total_pl_pct = (total_pl / total_investment) * 100 if total_investment != 0 else 0
    daily_pl = portfolio['Daily P/L'].sum()
    daily_return = (daily_pl / total_current) * 100 if total_current != 0 else 0
    
    # Determine colors
    pl_color = THEME['success'] if total_pl >= 0 else THEME['danger']
    daily_color = THEME['success'] if daily_pl >= 0 else THEME['danger']
    
    # Clear and display with improved layout
    console.clear()
    
    # Header with portfolio name
    console.print(Panel.fit(
        f"[bold]🏦 {portfolio_name.upper()} PORTFOLIO[/]", 
        style=f"bold {THEME['light']} on {THEME['dark']}",
        padding=(1, 2)
    ))
    console.print(f"[{THEME['primary']}]{'━' * 60}[/]\n")
    
    # Summary cards - Added Total P/L card
    summary = Table.grid(expand=True, padding=(0, 2))
    summary.add_column(justify="center", ratio=1)
    summary.add_column(justify="center", ratio=1)
    summary.add_column(justify="center", ratio=1)
    summary.add_column(justify="center", ratio=1)

    summary.add_row(
        Panel(
            f"[bold {THEME['light']}]Total Invested[/]\n[bold {THEME['success']}]₹{total_investment:,.2f}[/]",
            border_style=THEME['success'],
            padding=(1, 5),
            style=f"on {THEME['dark']}"
        ),
        Panel(
            f"[bold {THEME['light']}]Current Value[/]\n[bold {THEME['primary']}]₹{total_current:,.2f}[/]",
            border_style=THEME['primary'],
            padding=(1, 5),
            style=f"on {THEME['dark']}"
        ),
        Panel(
            f"[bold {THEME['light']}]Total P/L[/]\n[bold {pl_color}]₹{total_pl:+,.2f} ({total_pl_pct:+.2f}%)[/]",
            border_style=pl_color,
            padding=(1, 5),
            style=f"on {THEME['dark']}"
        ),
        Panel(
            f"[bold {THEME['light']}]Today's P/L[/]\n[bold {daily_color}]₹{daily_pl:+,.2f} ({daily_return:+.2f}%)[/]",
            border_style=daily_color,
            padding=(1, 5),
            style=f"on {THEME['dark']}"
        )
    )
    console.print(summary)
    
    # Stock performance table - simplified without status column
    console.print(f"\n[bold {THEME['secondary']}]⟦ STOCK PERFORMANCE ⟧[/]")
    stock_table = Table(
        show_header=True,
        header_style=f"bold {THEME['light']} on {THEME['dark']}",
        box=box.ROUNDED,
        border_style=THEME['primary'],
        show_lines=True,
        padding=(0, 1),
        expand=True,
        row_styles=[""]  # Remove alternating row colors
    )
    
    # Configure columns - removed status column
    columns = [
        ("Stock", THEME['primary'], 30),
        ("Qty", THEME['success'], 32),
        ("Price", THEME['primary'], 38),
        ("Today %", THEME['warning'], 38),
        ("Today ₹", THEME['warning'], 38),
        ("Total P/L", THEME['info'], 35)
    ]
    
    for col in columns:
        stock_table.add_column(
            col[0], 
            style=f"bold {col[1]}", 
            width=col[2], 
            justify="right" if col[0] != "Stock" else "left"
        )
    
    # Add stock rows with consistent styling
    for _, row in portfolio.iterrows():
        total_color = THEME['success'] if row['Profit/Loss'] >= 0 else THEME['danger']
        daily_color = THEME['success'] if row['Daily P/L'] >= 0 else THEME['danger']
        
        stock_table.add_row(
            f"[bold {THEME['light']}]{row['Stock Name']}[/]",
            f"{row['Quantity']:,}",
            f"₹{row['Current Price']:,.2f}",
            f"[{daily_color}]{row['Daily Return %']:+.2f}%[/]",
            f"[{daily_color}]{row['Daily P/L']:+,.2f}[/]",
            f"[{total_color}]{row['Profit/Loss']:+,.2f} ({row['Profit/Loss %']:+.2f}%)[/]"
        )
    
    console.print(stock_table)
    
    # Simplified footer options
    console.print(f"\n[{THEME['primary']}]{'━' * 60}[/]")
    console.print(f"[{THEME['light']}][r] Refresh   [b] Back[/]")
    
    return input("\nEnter option: ").lower()

def plot_portfolio_allocation(portfolio, portfolio_name):
    if portfolio.empty:
        console.print(Panel(f"[{THEME['warning']}]Portfolio '{portfolio_name}' is empty. No allocation to plot.[/]", 
                          border_style=THEME['warning']))
        return

    fig = px.pie(portfolio, values='Current Value', names='Stock Name', 
                 title=f"Portfolio Allocation: {portfolio_name}",
                 hole=0.3)  # Add a hole for donut chart
    fig.update_traces(textposition='inside', textinfo='percent+label', 
                     marker=dict(line=dict(color=THEME['background'], width=2)))
    fig.update_layout(
        font_size=16,  # Larger font size
        legend_font_size=14,
        title_font_size=20
    )
    fig.show()

def plot_profit_loss(portfolio, portfolio_name):
    if portfolio.empty:
        console.print(Panel(f"[{THEME['warning']}]Portfolio '{portfolio_name}' is empty. No profit/loss to plot.[/]", 
                          border_style=THEME['warning']))
        return

    fig = px.bar(portfolio, x='Stock Name', y='Profit/Loss', color='Profit/Loss',
                 color_continuous_scale=[THEME['danger'], THEME['success']], 
                 title=f"Profit/Loss by Stock: {portfolio_name}")
    fig.update_layout(
        xaxis_title="Stock Name", 
        yaxis_title="Profit/Loss (₹)",
        font_size=16,
        title_font_size=20
    )
    fig.add_hline(y=0, line_width=2, line_dash="dash", line_color=THEME['light'])
    fig.show()

def plot_daily_performance(portfolio, portfolio_name):
    if portfolio.empty:
        console.print(Panel(f"[{THEME['warning']}]Portfolio '{portfolio_name}' is empty. No daily performance to plot.[/]", 
                          border_style=THEME['warning']))
        return

    portfolio = portfolio.sort_values('Daily Return %', ascending=False)
    
    fig = px.bar(portfolio, x='Stock Name', y='Daily Return %', 
                 color='Daily Return %',
                 color_continuous_scale=[THEME['danger'], THEME['success']],
                 title=f"Today's Performance: {portfolio_name}")
    fig.update_layout(
        xaxis_title="Stock Name", 
        yaxis_title="Daily Return (%)",
        font_size=16,
        title_font_size=20
    )
    fig.add_hline(y=0, line_width=2, line_dash="dash", line_color=THEME['light'])
    fig.show()

def visualize_portfolio_performance(portfolios):
    portfolio_name = select_portfolio(portfolios)
    if not portfolio_name:
        return

    portfolio = portfolios[portfolio_name]
    if portfolio.empty:
        console.print(Panel(f"[{THEME['warning']}]Portfolio '{portfolio_name}' is empty. Nothing to visualize.[/]", 
                          border_style=THEME['warning']))
        return

    while True:
        console.print(Panel(
            "[bold]--- Visualization Options ---[/]",
            border_style=THEME['primary'],
            padding=(1, 2)
        ))
        menu = Table.grid(expand=True, padding=(0, 2))
        menu.add_column(justify="left")
        
        menu.add_row(f"1. [{THEME['primary']}]Portfolio Allocation (Pie Chart)[/]")
        menu.add_row(f"2. [{THEME['info']}]Profit/Loss by Stock (Bar Chart)[/]")
        menu.add_row(f"3. [{THEME['warning']}]Daily Performance (Bar Chart)[/]")
        menu.add_row(f"4. [{THEME['danger']}]Back to Main Menu[/]")
        
        console.print(menu)
        
        choice = input("\nEnter your choice: ")
        
        if choice == "1":
            plot_portfolio_allocation(portfolio, portfolio_name)
        elif choice == "2":
            plot_profit_loss(portfolio, portfolio_name)
        elif choice == "3":
            plot_daily_performance(portfolio, portfolio_name)
        elif choice == "4":
            break
        else:
            console.print(Panel(f"[{THEME['danger']}]Invalid choice![/]", 
                              border_style=THEME['danger']))

def create_portfolio(portfolios):
    """Create a new portfolio with audit logging"""
    while True:
        console.clear()
        console.print(Panel(
            "[bold]CREATE NEW PORTFOLIO[/]",
            style=f"bold {THEME['primary']}",
            border_style=THEME['primary']
        ))
        
        portfolio_name = input(f"\n[{THEME['primary']}]Enter portfolio name (or 'b' to go back): [/]").strip()
        
        if portfolio_name.lower() == 'b':
            return
        
        if not portfolio_name:
            console.print(Panel(f"[{THEME['danger']}]Portfolio name cannot be empty.[/]", 
                              border_style=THEME['danger']))
            continue
            
        normalized_name = normalize_portfolio_name(portfolio_name)
        existing_portfolio = next((name for name in portfolios.keys() 
                                 if normalize_portfolio_name(name) == normalized_name), None)
        
        if existing_portfolio:
            console.print(Panel(f"[{THEME['danger']}]Portfolio '{existing_portfolio}' already exists.[/]", 
                              border_style=THEME['danger']))
            time.sleep(1)
        else:
            # Create new portfolio dataframe
            portfolios[portfolio_name] = pd.DataFrame(columns=[
                'Portfolio Name', 'Stock Name', 'Ticker Symbol', 'Quantity', 
                'Purchase Price', 'Purchase Date', 'Sector', 'Investment Value',
                'Current Price', 'Current Value', 'Profit/Loss', 'Profit/Loss %',
                'Daily Return %', 'Daily P/L'
            ])
            
            # Log the creation
            log_portfolio_change("CREATED_PORTFOLIO", portfolio_name)
            
            console.print(Panel(
                f"[{THEME['success']}]Portfolio '{portfolio_name}' created successfully.[/]",
                border_style=THEME['success']
            ))
            time.sleep(1)
            return
        
def add_stock(portfolios):
    """Add new stock to portfolio with comprehensive logging"""
    if not portfolios:
        console.print(Panel("[red]No portfolios found. Create one first![/red]", 
                          border_style=THEME['danger']))
        return

    # Portfolio selection
    portfolio_name = select_portfolio(portfolios)
    if not portfolio_name:
        return

    portfolio = portfolios[portfolio_name]
    
    # Display existing stocks
    if not portfolio.empty:
        console.print("\n[bold]Existing Stocks:[/bold]")
        stock_table = Table(show_header=True, header_style="bold magenta")
        stock_table.add_column("Stock", style="bright_white", min_width=20)
        stock_table.add_column("Ticker", style="green", width=12)
        stock_table.add_column("Qty", style="bright_green", width=8)
        stock_table.add_column("Avg Price", style="bright_yellow", width=12)
        
        for _, row in portfolio.iterrows():
            stock_table.add_row(
                row['Stock Name'],
                row['Ticker Symbol'],
                f"{row['Quantity']:,}",
                f"₹{row['Purchase Price']:.2f}"
            )
        
        console.print(stock_table)

    console.print("\n[bold]ADD NEW STOCK[/bold]")
    
    # Stock details collection
    while True:
        stock_name = input("\nEnter stock name (or 'b' to cancel): ").strip()
        if stock_name.lower() == 'b':
            return
            
        if not stock_name:
            console.print("[red]Stock name cannot be empty.[/red]")
            continue
        break

    while True:
        ticker = input("Enter ticker symbol (e.g., RELIANCE.NS): ").strip().upper()
        if ticker.lower() == 'b':
            return
            
        if not ticker:
            console.print("[red]Ticker cannot be empty.[/red]")
            continue
            
        # Check if ticker exists
        if not validate_ticker(ticker):
            console.print("[red]Invalid ticker symbol. Please verify.[/red]")
            continue
            
        # Check if ticker already in portfolio
        if not portfolio.empty and ticker in portfolio['Ticker Symbol'].values:
            existing = portfolio[portfolio['Ticker Symbol'] == ticker].iloc[0]
            console.print(f"[yellow]This ticker already exists as: {existing['Stock Name']}[/yellow]")
            console.print("[yellow]Consider using 'Manage Shares' instead.[/yellow]")
            continue
            
        break

    while True:
        qty = input("Enter quantity: ").strip()
        if qty.lower() == 'b':
            return
            
        if not qty.isdigit() or int(qty) <= 0:
            console.print("[red]Invalid quantity. Must be positive integer.[/red]")
            continue
        qty = int(qty)
        break

    while True:
        price = input("Enter purchase price per share: ").strip()
        if price.lower() == 'b':
            return
            
        try:
            price = float(price)
            if price <= 0:
                console.print("[red]Price must be positive.[/red]")
                continue
            break
        except ValueError:
            console.print("[red]Invalid price. Must be a number.[/red]")

    while True:
        date = input("Enter purchase date (DD-MM-YYYY): ").strip()
        if date.lower() == 'b':
            return
            
        if not validate_date(date):
            console.print("[red]Invalid date format. Use DD-MM-YYYY.[/red]")
            continue
        break

    sector = input("Enter sector (optional): ").strip()
    if sector.lower() == 'b':
        return

    # Create new stock entry
    new_stock = {
        'Portfolio Name': portfolio_name,
        'Stock Name': stock_name,
        'Ticker Symbol': ticker,
        'Quantity': qty,
        'Purchase Price': price,
        'Purchase Date': datetime.strptime(date, "%d-%m-%Y").strftime("%Y-%m-%d"),
        'Sector': sector,
        'Investment Value': qty * price,
        'Current Price': 0.0,
        'Current Value': 0.0,
        'Profit/Loss': 0.0,
        'Profit/Loss %': 0.0,
        'Daily Return %': 0.0,
        'Daily P/L': 0.0
    }

    # Add to portfolio
    portfolios[portfolio_name] = pd.concat([portfolio, pd.DataFrame([new_stock])], ignore_index=True)
    
    # Log the addition
    log_portfolio_change(
        "ADDED_STOCK", 
        portfolio_name, 
        stock_name,
        f"Qty: {qty} @ ₹{price:.2f} | Total: ₹{qty*price:.2f} | Sector: {sector or 'N/A'}"
    )
    
    console.print(Panel(
        f"[{THEME['success']}]Successfully added {stock_name} ({ticker}) to {portfolio_name}[/]",
        border_style=THEME['success']
    ))
    time.sleep(1)


def remove_zero_quantity_stocks(portfolios):
    """Remove all stocks with 0 quantity from all portfolios"""
    for portfolio_name in list(portfolios.keys()):
        portfolio = portfolios[portfolio_name]
        # Remove rows where Quantity is 0
        portfolios[portfolio_name] = portfolio[portfolio['Quantity'] > 0]
        # If portfolio becomes empty, remove it
        if portfolios[portfolio_name].empty:
            del portfolios[portfolio_name]

def manage_shares(portfolios):
    """Enhanced share management with complete audit logging"""
    while True:
        # Select portfolio (only show those with stocks)
        active_portfolios = {
            k: v for k, v in portfolios.items() 
            if not v[v['Quantity'] > 0].empty
        }
        
        if not active_portfolios:
            console.print(
                Panel("[yellow]No portfolios with active stocks found.[/yellow]", 
                     border_style=THEME['warning'])
            )
            time.sleep(1)
            return

        # Portfolio selection
        console.print("\n[bold]📂 Select Portfolio[/bold]")
        for i, name in enumerate(active_portfolios.keys(), 1):
            p = active_portfolios[name]
            total_value = p['Current Value'].sum()
            console.print(f"{i}. {name} [dim](₹{total_value:,.2f})[/]")
        console.print(f"{len(active_portfolios)+1}. ↩ Back")

        try:
            choice = input("\n[bold]» Select portfolio: [/]").strip()
            if choice.lower() in ('b', 'back') or choice == str(len(active_portfolios)+1):
                return
            
            choice = int(choice)
            if 1 <= choice <= len(active_portfolios):
                portfolio_name = list(active_portfolios.keys())[choice-1]
                portfolio = portfolios[portfolio_name].copy()
                break
            else:
                console.print("[red]Invalid selection![/red]")
                time.sleep(1)
        except ValueError:
            console.print("[red]Please enter a valid number![/red]")
            time.sleep(1)

    while True:
        # Filter out zero quantity stocks
        portfolio = portfolio[portfolio['Quantity'] > 0].reset_index(drop=True)
        if portfolio.empty:
            console.print(
                Panel(f"[yellow]Portfolio '{portfolio_name}' has no active stocks.[/yellow]", 
                     border_style=THEME['warning'])
            )
            del portfolios[portfolio_name]
            return

        # Stock selection table
        console.print(f"\n[bold]📊 Portfolio: {portfolio_name}[/bold]")
        stock_table = Table(
            show_header=True,
            header_style="bold bright_white",
            box=box.ROUNDED,
            border_style="bright_blue"
        )
        
        stock_table.add_column("#", style="cyan", width=4)
        stock_table.add_column("Stock", style="bright_white", min_width=20)
        stock_table.add_column("Ticker", style="green", width=10)
        stock_table.add_column("Qty", style="bright_green", width=8)
        stock_table.add_column("Avg ₹", style="bright_yellow", width=10)
        stock_table.add_column("Curr ₹", style="bright_blue", width=10)
        stock_table.add_column("P/L", style="bright_magenta", width=15)
        
        for idx, row in portfolio.iterrows():
            pl_color = "bright_green" if row['Profit/Loss'] >= 0 else "bright_red"
            stock_table.add_row(
                str(idx+1),
                row['Stock Name'],
                row['Ticker Symbol'],
                f"{row['Quantity']:,}",
                f"₹{row['Purchase Price']:.2f}",
                f"₹{row['Current Price']:.2f}",
                f"[{pl_color}]₹{row['Profit/Loss']:+,.2f} ({row['Profit/Loss %']:+.2f}%)[/{pl_color}]"
            )
        
        console.print(stock_table)
        console.print(f"\n{len(portfolio)+1}. ↩ Back")

        # Stock selection
        try:
            stock_choice = input("\n[bold]» Select stock: [/]").strip()
            if stock_choice.lower() in ('b', 'back') or stock_choice == str(len(portfolio)+1):
                break
                
            stock_choice = int(stock_choice)
            if 1 <= stock_choice <= len(portfolio):
                stock_idx = stock_choice - 1
                stock_row = portfolio.iloc[stock_idx]
                break
            else:
                console.print("[red]Invalid selection![/red]")
                time.sleep(1)
        except ValueError:
            console.print("[red]Please enter a valid number![/red]")
            time.sleep(1)

    # Stock management actions
    stock_name = stock_row['Stock Name']
    ticker = stock_row['Ticker Symbol']
    current_qty = stock_row['Quantity']
    avg_price = stock_row['Purchase Price']
    current_price = stock_row['Current Price']
    current_value = stock_row['Current Value']
    profit_loss = stock_row['Profit/Loss']
    
    console.print(f"\n[bold]📝 Managing: {stock_name} ({ticker})[/bold]")
    console.print(f"│ Quantity: [bold]{current_qty:,}[/bold] shares")
    console.print(f"│ Avg Price: [bold]₹{avg_price:.2f}[/bold]")
    console.print(f"│ Current Price: [bold]₹{current_price:.2f}[/bold]")
    console.print(f"│ Current Value: [bold]₹{current_value:,.2f}[/bold]")
    
    pl_color = "green" if profit_loss >= 0 else "red"
    console.print(f"│ P/L: [{pl_color}][bold]₹{profit_loss:+,.2f}[/bold][/{pl_color}]")
    
    console.print("\n1. ➕ Add Shares")
    console.print("2. ➖ Remove Shares")
    console.print("3. ↩ Back")

    while True:
        action = input("\n[bold]» Select action: [/]").strip()
        
        if action == "1":  # Add shares
            while True:
                add_qty = input("\n[bold]» Quantity to add: [/]").strip()
                if add_qty.lower() == 'b':
                    break
                    
                if not add_qty.isdigit() or int(add_qty) <= 0:
                    console.print("[red]Invalid quantity! Must be positive integer.[/red]")
                    continue
                    
                add_qty = int(add_qty)
                
                while True:
                    buy_price = input("[bold]» Purchase price per share: ₹[/]").strip()
                    if buy_price.lower() == 'b':
                        break
                        
                    try:
                        buy_price = float(buy_price)
                        if buy_price <= 0:
                            console.print("[red]Price must be positive![/red]")
                            continue
                            
                        # Calculate new average
                        total_investment = (current_qty * avg_price) + (add_qty * buy_price)
                        new_qty = current_qty + add_qty
                        new_avg = total_investment / new_qty
                        
                        # Update portfolio
                        portfolio.at[stock_idx, 'Quantity'] = new_qty
                        portfolio.at[stock_idx, 'Purchase Price'] = new_avg
                        portfolio.at[stock_idx, 'Investment Value'] = total_investment
                        portfolios[portfolio_name] = portfolio
                        
                        # Log the change
                        log_portfolio_change(
                            "ADDED_SHARES",
                            portfolio_name,
                            stock_name,
                            f"Added {add_qty} @ ₹{buy_price:.2f} | New Qty: {new_qty} | New Avg: ₹{new_avg:.2f}"
                        )
                        
                        console.print(
                            Panel(f"[green]✔ Added {add_qty} shares at ₹{buy_price:.2f}[/green]\n"
                                f"New quantity: [bold]{new_qty:,}[/bold]\n"
                                f"New average price: [bold]₹{new_avg:.2f}[/bold]",
                                border_style="green"
                            )
                        )
                        input("\nPress Enter to continue...")
                        return
                        
                    except ValueError:
                        console.print("[red]Invalid price! Must be a number.[/red]")
                break
                
        elif action == "2":  # Remove shares
            while True:
                remove_qty = input(f"\n[bold]» Quantity to remove (max {current_qty}): [/]").strip()
                if remove_qty.lower() == 'b':
                    break
                    
                if not remove_qty.isdigit() or int(remove_qty) <= 0:
                    console.print("[red]Invalid quantity! Must be positive integer.[/red]")
                    continue
                    
                remove_qty = int(remove_qty)
                
                if remove_qty > current_qty:
                    console.print(f"[red]Cannot remove more than {current_qty} shares![/red]")
                    continue
                    
                new_qty = current_qty - remove_qty
                
                # Update portfolio
                portfolio.at[stock_idx, 'Quantity'] = new_qty
                portfolio.at[stock_idx, 'Investment Value'] = new_qty * avg_price
                
                if new_qty == 0:
                    # Remove stock completely
                    portfolio = portfolio.drop(stock_idx).reset_index(drop=True)
                    
                    console.print(f"[red]Removed all shares of {stock_name} from portfolio[/red]")
                    
                    # Log the complete removal
                    log_portfolio_change("REMOVED_STOCK", portfolio_name, stock_name, 
                           f"Removed all shares (previously held {current_qty})")
                    
                    action_type = "REMOVED_ALL_SHARES"
                    msg = f"Removed all {current_qty} shares"
                else:
                    action_type = "REMOVED_SHARES"
                    msg = f"Removed {remove_qty} shares | Remaining: {new_qty}"
                
                portfolios[portfolio_name] = portfolio
                
                # Log the change
                log_portfolio_change(
                    action_type,
                    portfolio_name,
                    stock_name,
                    msg
                )
                
                console.print(Panel(
                    f"[green]✔ {msg}[/green]",
                    border_style="green"
                ))
                
                # If portfolio becomes empty, remove it
                if portfolio.empty:
                    del portfolios[portfolio_name]
                    console.print(
                        Panel(f"[yellow]Portfolio '{portfolio_name}' is now empty and has been removed.[/yellow]",
                             border_style="yellow")
                    )
                
                input("\nPress Enter to continue...")
                return
                
        elif action == "3":
            return
        else:
            console.print("[red]Invalid choice![/red]")
            time.sleep(1)

def clean_zero_quantity_stocks(portfolios):
    """Remove all zero-quantity stocks from all portfolios"""
    for name in list(portfolios.keys()):
        # Filter out zero-quantity stocks
        portfolios[name] = portfolios[name][portfolios[name]['Quantity'] > 0]
        
        # Remove empty portfolios
        if portfolios[name].empty:
            del portfolios[name]
            log_portfolio_change("REMOVED_EMPTY_PORTFOLIO", name)

def add_stock(portfolios):
    if not portfolios:
        console.print("[red]No portfolios found. Please create a portfolio first.[/red]")
        return

    while True:
        console.print("\n[bold]--- Select a Portfolio ---[/bold]")
        portfolio_names = list(portfolios.keys())
        for i, name in enumerate(portfolio_names, start=1):
            console.print(f"{i}. {name}")
        console.print(f"{len(portfolio_names)+1}. Go Back")

        choice = input("\nEnter your choice (number or 'b' to go back): ")
        
        if choice.lower() == 'b' or choice == str(len(portfolio_names)+1):
            return
            
        try:
            choice = int(choice)
            if 1 <= choice <= len(portfolio_names):
                portfolio_name = portfolio_names[choice - 1]
                break
            else:
                console.print("[red]Invalid choice. Please enter a valid number.[/red]")
        except ValueError:
            console.print("[red]Invalid input. Please enter a number.[/red]")

    # Display existing stocks in the portfolio with quantities
    portfolio = portfolios[portfolio_name]
    if not portfolio.empty:
        console.print(f"\n[bold]Existing stocks in '{portfolio_name}':[/bold]")
        stock_table = Table(show_header=True, header_style="bold magenta")
        stock_table.add_column("No.", style="cyan", width=4)
        stock_table.add_column("Stock Name", style="bright_white", min_width=20)
        stock_table.add_column("Ticker", style="green", width=12)
        stock_table.add_column("Qty", style="bright_green", width=8)
        stock_table.add_column("Avg Price", style="bright_yellow", width=12)
        stock_table.add_column("Value", style="bright_cyan", width=12)
        
        for index, row in portfolio.iterrows():
            stock_table.add_row(
                str(index + 1),
                row['Stock Name'],
                row['Ticker Symbol'],
                f"{row['Quantity']:,}",
                f"₹{row['Purchase Price']:.2f}",
                f"₹{row['Investment Value']:,.2f}"
            )
        
        console.print(stock_table)
    else:
        console.print(f"[yellow]Portfolio '{portfolio_name}' is currently empty.[/yellow]")

    console.print("\n[bold]--- Add New Stock ---[/bold]")

    while True:
        stock_name = input("\nEnter stock name (or 'b' to go back): ")
        
        if stock_name.lower() == 'b':
            return
            
        if not stock_name.strip():
            console.print("[red]Stock name cannot be empty.[/red]")
            continue
            
        break

    while True:
        ticker_symbol = input("Enter ticker symbol (e.g., RELIANCE.NS, or 'b' to go back): ")
        
        if ticker_symbol.lower() == 'b':
            return
            
        if validate_ticker(ticker_symbol):
            # Check if ticker already exists in portfolio
            if not portfolio.empty and ticker_symbol in portfolio['Ticker Symbol'].values:
                existing_row = portfolio[portfolio['Ticker Symbol'] == ticker_symbol].iloc[0]
                console.print(f"[yellow]This stock already exists with {existing_row['Quantity']} shares at average price ₹{existing_row['Purchase Price']:.2f}[/yellow]")
                console.print("[yellow]Consider using 'Manage Shares' option instead.[/yellow]")
                continue
            break
        else:
            console.print("[red]Invalid ticker symbol. Please try again.[/red]")

    while True:
        quantity = input("Enter quantity (or 'b' to go back): ")
        
        if quantity.lower() == 'b':
            return
            
        if quantity.isdigit() and int(quantity) > 0:
            quantity = int(quantity)
            break
        else:
            console.print("[red]Invalid quantity. Please enter a positive integer.[/red]")

    while True:
        purchase_price = input("Enter purchase price (or 'b' to go back): ")
        
        if purchase_price.lower() == 'b':
            return
            
        try:
            purchase_price = float(purchase_price)
            if purchase_price > 0:
                break
            else:
                console.print("[red]Invalid purchase price. Please enter a positive number.[/red]")
        except ValueError:
            console.print("[red]Invalid purchase price. Please enter a valid number.[/red]")

    while True:
        purchase_date = input("Enter purchase date (DD-MM-YYYY, or 'b' to go back): ")
        
        if purchase_date.lower() == 'b':
            return
            
        if validate_date(purchase_date):
            break
        else:
            console.print("[red]Invalid date format. Please enter the date in DD-MM-YYYY format.[/red]")

    sector = input("Enter sector (or 'b' to go back): ")
    if sector.lower() == 'b':
        return

    purchase_date = datetime.strptime(purchase_date, "%d-%m-%Y").strftime("%Y-%m-%d")

    new_stock = {
        'Portfolio Name': portfolio_name,
        'Stock Name': stock_name,
        'Ticker Symbol': ticker_symbol,
        'Quantity': quantity,
        'Purchase Price': purchase_price,
        'Purchase Date': purchase_date,
        'Sector': sector,
        'Investment Value': quantity * purchase_price,
        'Current Price': 0.0,
        'Current Value': 0.0,
        'Profit/Loss': 0.0,
        'Profit/Loss %': 0.0,
        'Daily Return %': 0.0,
        'Daily P/L': 0.0
    }

    if portfolio_name in portfolios:
        portfolios[portfolio_name] = pd.concat([portfolios[portfolio_name], pd.DataFrame([new_stock])], ignore_index=True)
    else:
        portfolios[portfolio_name] = pd.DataFrame([new_stock])

    console.print(f"\n[green]✔ Successfully added {stock_name} to portfolio '{portfolio_name}'[/green]")
    console.print(f"  Quantity: {quantity} @ ₹{purchase_price:.2f}")
    console.print(f"  Total Investment: ₹{quantity*purchase_price:,.2f}")
    
def delete_portfolio(portfolios):
    """Delete a portfolio with confirmation and audit logging"""
    while True:
        portfolio_name = select_portfolio(portfolios)
        if not portfolio_name:
            return

        # Show portfolio contents before deletion
        if not portfolios[portfolio_name].empty:
            console.print(f"\n[yellow]Contents of '{portfolio_name}':[/yellow]")
            console.print(portfolios[portfolio_name][['Stock Name', 'Ticker Symbol', 'Quantity']])
        
        confirm = input(f"\n[{THEME['danger']}]CONFIRM: Delete portfolio '{portfolio_name}'? (y/n/b): [/]").lower()
        
        if confirm == 'y':
            # Log before actual deletion
            log_portfolio_change("DELETED_PORTFOLIO", portfolio_name, 
                               details=f"Stocks deleted: {len(portfolios[portfolio_name])}")
            
            del portfolios[portfolio_name]
            console.print(Panel(
                f"[{THEME['success']}]Portfolio '{portfolio_name}' deleted.[/]",
                border_style=THEME['success']
            ))
            time.sleep(1)
            break
        elif confirm == 'b':
            return
        else:
            console.print("[yellow]Deletion cancelled.[/yellow]")
            time.sleep(1)
            break

def modify_stock(portfolios):
    while True:
        portfolio_name = select_portfolio(portfolios)
        if not portfolio_name:
            return

        portfolio = portfolios[portfolio_name]
        if portfolio.empty:
            console.print(f"[yellow]Portfolio '{portfolio_name}' is empty. No stocks to modify.[/yellow]")
            return

        console.print("\n[bold]--- Select a Stock to Modify ---[/bold]")
        for i, row in portfolio.iterrows():
            console.print(f"{i + 1}. {row['Stock Name']} (Ticker: {row['Ticker Symbol']})")
        console.print(f"{len(portfolio)+1}. Go Back")

        while True:
            stock_choice = input("\nEnter the number corresponding to the stock (or 'b' to go back): ")
            
            if stock_choice.lower() == 'b':
                return
                
            try:
                stock_choice = int(stock_choice)
                if 1 <= stock_choice <= len(portfolio):
                    stock_index = stock_choice - 1
                    break
                elif stock_choice == len(portfolio)+1:
                    return
                else:
                    console.print("[red]Invalid choice. Please enter a valid number.[/red]")
            except ValueError:
                console.print("[red]Invalid input. Please enter a number.[/red]")

        stock_name = portfolio.at[stock_index, 'Stock Name']
        ticker_symbol = portfolio.at[stock_index, 'Ticker Symbol']

        console.print(f"\nSelected Stock: {stock_name} (Ticker: {ticker_symbol})")

        while True:
            console.print("\n[bold]Select field to modify:[/bold]")
            console.print("1. Stock Name")
            console.print("2. Ticker Symbol")
            console.print("3. Quantity")
            console.print("4. Purchase Price")
            console.print("5. Purchase Date")
            console.print("6. Sector")
            console.print("7. Go Back")
            choice = input("Enter your choice: ")

            if choice == "1":
                new_name = input("Enter new stock name (or 'b' to go back): ")
                if new_name.lower() == 'b':
                    continue
                portfolio.at[stock_index, 'Stock Name'] = new_name
                console.print(f"[green]Stock name updated to '{new_name}'.[/green]")
                break
                
            elif choice == "2":
                while True:
                    new_ticker = input("Enter new ticker symbol (or 'b' to go back): ")
                    if new_ticker.lower() == 'b':
                        break
                    if validate_ticker(new_ticker):
                        portfolio.at[stock_index, 'Ticker Symbol'] = new_ticker
                        console.print(f"[green]Ticker symbol updated to '{new_ticker}'.[/green]")
                        break
                    else:
                        console.print("[red]Invalid ticker symbol. Please try again.[/red]")
                break
                
            elif choice == "3":
                while True:
                    new_quantity = input("Enter new quantity (or 'b' to go back): ")
                    if new_quantity.lower() == 'b':
                        break
                    if new_quantity.isdigit() and int(new_quantity) > 0:
                        new_quantity = int(new_quantity)
                        portfolio.at[stock_index, 'Quantity'] = new_quantity
                        portfolio.at[stock_index, 'Investment Value'] = new_quantity * portfolio.at[stock_index, 'Purchase Price']
                        console.print(f"[green]Quantity updated to {new_quantity}.[/green]")
                        break
                    else:
                        console.print("[red]Invalid quantity. Please enter a positive integer.[/red]")
                break
                
            elif choice == "4":
                while True:
                    new_price = input("Enter new purchase price (or 'b' to go back): ")
                    if new_price.lower() == 'b':
                        break
                    try:
                        new_price = float(new_price)
                        if new_price > 0:
                            portfolio.at[stock_index, 'Purchase Price'] = new_price
                            portfolio.at[stock_index, 'Investment Value'] = portfolio.at[stock_index, 'Quantity'] * new_price
                            console.print(f"[green]Purchase price updated to {new_price}.[/green]")
                            break
                        else:
                            console.print("[red]Invalid purchase price. Please enter a positive number.[/red]")
                    except ValueError:
                        console.print("[red]Invalid purchase price. Please enter a valid number.[/red]")
                break
                
            elif choice == "5":
                while True:
                    new_date = input("Enter new purchase date (DD-MM-YYYY, or 'b' to go back): ")
                    if new_date.lower() == 'b':
                        break
                    if validate_date(new_date):
                        new_date = datetime.strptime(new_date, "%d-%m-%Y").strftime("%Y-%m-%d")
                        portfolio.at[stock_index, 'Purchase Date'] = new_date
                        console.print(f"[green]Purchase date updated to {new_date}.[/green]")
                        break
                    else:
                        console.print("[red]Invalid date format. Please enter the date in DD-MM-YYYY format.[/red]")
                break
                
            elif choice == "6":
                new_sector = input("Enter new sector (or 'b' to go back): ")
                if new_sector.lower() == 'b':
                    continue
                portfolio.at[stock_index, 'Sector'] = new_sector
                console.print(f"[green]Sector updated to '{new_sector}'.[/green]")
                break
                
            elif choice == "7":
                return
                
            else:
                console.print("[red]Invalid choice.[/red]")
                continue

        console.print(f"[green]Stock '{stock_name}' in portfolio '{portfolio_name}' updated.[/green]")
        break

def view_portfolio_stocks(portfolio):
    """Display stocks in portfolio, excluding zero-quantity positions"""
    # Filter out zero-quantity stocks
    active_stocks = portfolio[portfolio['Quantity'] > 0]
    
    if active_stocks.empty:
        console.print("[yellow]No active holdings in this portfolio.[/yellow]")
        return

    # Create table with only active holdings
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("No.", style="cyan", width=4)
    table.add_column("Stock", style="bright_white", min_width=20)
    table.add_column("Ticker", style="green", width=12)
    table.add_column("Qty", style="bright_green", width=8)
    table.add_column("Avg Price", style="bright_yellow", width=12)
    table.add_column("Value", style="bright_cyan", width=12)

    for i, (_, row) in enumerate(active_stocks.iterrows(), 1):
        table.add_row(
            str(i),
            row['Stock Name'],
            row['Ticker Symbol'],
            f"{row['Quantity']:,}",
            f"₹{row['Purchase Price']:.2f}",
            f"₹{row['Current Value']:,.2f}"
        )
    
    console.print(table)
    

def view_portfolio_history(portfolio_name=None):
    """View change history with error handling"""
    if not os.path.exists(AUDIT_LOG_FILE):
        console.print(Panel("[yellow]No audit history found.[/yellow]", 
                          border_style=THEME['warning']))
        return

    with open(AUDIT_LOG_FILE, "r") as f:
        log_entries = []
        for line in f.readlines():
            try:
                # Split with maxsplit=4 to handle details containing pipes
                parts = line.strip().split(" | ", 4)
                if len(parts) == 5:
                    log_entries.append(parts)
                else:
                    console.print(f"[yellow]Skipping malformed log entry: {line}[/yellow]")
            except Exception as e:
                console.print(f"[red]Error parsing log entry: {e}[/red]")
                continue

    if not log_entries:
        console.print(Panel("[yellow]No valid historical records found.[/yellow]", 
                          border_style=THEME['warning']))
        return

    # Filter for specific portfolio if requested
    if portfolio_name:
        log_entries = [entry for entry in log_entries if entry[2] == portfolio_name]
        if not log_entries:
            console.print(Panel(f"[yellow]No history found for portfolio '{portfolio_name}'[/yellow]", 
                              border_style=THEME['warning']))
            return

    # Create table
    history_table = Table(
        title=f"\n📜 {'Portfolio' if not portfolio_name else portfolio_name} Change History",
        show_header=True,
        header_style="bold bright_white",
        box=box.ROUNDED,
        border_style="bright_blue"
    )
    
    history_table.add_column("Timestamp", style="dim", width=20)
    history_table.add_column("Action", style="bright_cyan", width=15)
    history_table.add_column("Portfolio", style="bright_green", width=20)
    history_table.add_column("Stock", style="bright_yellow", width=20)
    history_table.add_column("Details", style="bright_white", min_width=40)

    for entry in reversed(log_entries[-200:]):  # Show last 200 entries
        timestamp, action, portfolio, stock, details = entry
        history_table.add_row(timestamp, action, portfolio, stock, details)

    console.print(history_table)
    console.print(f"\n[dim]Showing last {min(len(log_entries), 200)} entries. Full history in {AUDIT_LOG_FILE}[/dim]")
 
def view_all_portfolios(portfolios):
    """Show only portfolios that have at least one stock with quantity > 0"""
    if not portfolios:
        console.print("[red]No portfolios found.[/red]")
        return

    console.print("\n[bold]--- All Portfolios ---[/bold]")
    valid_portfolios = {k:v for k,v in portfolios.items() if not v[v['Quantity'] > 0].empty}
    
    if not valid_portfolios:
        console.print("[yellow]No portfolios with active stocks found.[/yellow]")
        return
        
    for i, portfolio_name in enumerate(valid_portfolios, start=1):
        console.print(f"{i}. {portfolio_name}")

def select_portfolio(portfolios):
    if not portfolios:
        console.print("[red]No portfolios found.[/red]")
        return None

    while True:
        view_all_portfolios(portfolios)
        console.print(f"{len(portfolios)+1}. Go Back")
        
        portfolio_choice = input("\nEnter the number corresponding to the portfolio (or 'b' to go back): ")
        
        if portfolio_choice.lower() == 'b':
            return None
            
        try:
            portfolio_choice = int(portfolio_choice)
            if 1 <= portfolio_choice <= len(portfolios):
                portfolio_name = list(portfolios.keys())[portfolio_choice - 1]
                return portfolio_name
            elif portfolio_choice == len(portfolios)+1:
                return None
            else:
                console.print("[red]Invalid choice. Please enter a valid number.[/red]")
        except ValueError:
            console.print("[red]Invalid input. Please enter a number.[/red]")

def export_portfolio(portfolios, portfolio_name=None):
    """Export portfolio data with metadata including creation/modification history"""
    if portfolio_name:
        # Single portfolio export
        if portfolio_name not in portfolios:
            console.print(Panel(f"[red]Portfolio '{portfolio_name}' not found.[/red]", 
                              border_style=THEME['danger']))
            return

        # Get creation and modification history
        history = get_portfolio_history(portfolio_name)
        
        # Prepare export data
        export_data = {
            'metadata': {
                'portfolio_name': portfolio_name,
                'created_at': next((h[0] for h in history if h[1] == "CREATED_PORTFOLIO"), "Unknown"),
                'last_modified': history[0][0] if history else "Unknown",
                'stock_count': len(portfolios[portfolio_name])
            },
            'stocks': portfolios[portfolio_name].to_dict('records'),
            'history': history
        }

        filename = f"{portfolio_name.replace(' ','_')}_export_{datetime.now().strftime('%Y%m%d')}.json"
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=4)

        log_portfolio_change("EXPORTED_PORTFOLIO", portfolio_name, 
                           details=f"Exported {len(portfolios[portfolio_name])} stocks to {filename}")
        
        console.print(Panel(
            f"[{THEME['success']}]Successfully exported '{portfolio_name}' to {filename}[/]",
            border_style=THEME['success']
        ))
    else:
        # Full portfolio export
        export_data = {}
        for name, data in portfolios.items():
            history = get_portfolio_history(name)
            export_data[name] = {
                'metadata': {
                    'created_at': next((h[0] for h in history if h[1] == "CREATED_PORTFOLIO"), "Unknown"),
                    'last_modified': history[0][0] if history else "Unknown",
                    'stock_count': len(data)
                },
                'stocks': data.to_dict('records'),
                'history': history
            }

        filename = f"full_portfolio_export_{datetime.now().strftime('%Y%m%d')}.json"
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=4)

        log_portfolio_change("EXPORTED_ALL", "ALL_PORTFOLIOS", 
                           details=f"Exported {len(portfolios)} portfolios to {filename}")
        
        console.print(Panel(
            f"[{THEME['success']}]Successfully exported all portfolios to {filename}[/]",
            border_style=THEME['success']
        ))

def repair_audit_log():
    """Clean up malformed entries in audit log"""
    if not os.path.exists(AUDIT_LOG_FILE):
        return

    with open(AUDIT_LOG_FILE, "r") as f:
        lines = f.readlines()

    clean_entries = []
    for line in lines:
        if line.count(" | ") >= 4:  # Verify it has all required fields
            clean_entries.append(line)

    with open(AUDIT_LOG_FILE, "w") as f:
        f.writelines(clean_entries)
        
def get_portfolio_history(portfolio_name):
    """Retrieve history for a specific portfolio"""
    if not os.path.exists(AUDIT_LOG_FILE):
        return []

    with open(AUDIT_LOG_FILE, "r") as f:
        return [line.strip().split(" | ") for line in f.readlines() 
               if line.strip() and line.split(" | ")[2] == portfolio_name]
        
def export_individual_portfolio(portfolios):
    portfolio_name = select_portfolio(portfolios)
    if not portfolio_name:
        return

    portfolio = portfolios[portfolio_name]
    file_name = f"{portfolio_name.replace(' ', '_')}_portfolio.xlsx"
    portfolio.to_excel(file_name, index=False)
    console.print(f"[green]Portfolio '{portfolio_name}' exported to '{file_name}'.[/green]")

def export_all_portfolios(portfolios):
    if not portfolios:
        console.print("[red]No portfolios found to export.[/red]")
        return

    with pd.ExcelWriter("all_portfolios.xlsx") as writer:
        for portfolio_name, portfolio in portfolios.items():
            portfolio.to_excel(writer, sheet_name=portfolio_name[:31], index=False)  # Sheet name max 31 chars
    console.print("[green]All portfolios exported to 'all_portfolios.xlsx'.[/green]")

def portfolio_history_menu(portfolios):
    """Dedicated menu for portfolio history features"""
    while True:
        console.clear()
        console.print(Panel(
            "[bold]PORTFOLIO HISTORY & AUDIT[/]",
            style=f"bold {THEME['light']}",
            border_style=THEME['light']
        ))
        
        options = Table.grid(expand=True, padding=(0, 2))
        options.add_column(justify="left", width=30)
        options.add_column(justify="left", width=30)

        options.add_row(
            Panel(
                "[bold]1. View Full Audit Log[/]\n"
                "[dim]Complete system change history[/dim]",
                border_style=THEME['info']
            ),
            Panel(
                "[bold]2. Portfolio-Specific History[/]\n"
                "[dim]Changes for selected portfolio[/dim]",
                border_style=THEME['primary']
            )
        )
        options.add_row(
            Panel(
                "[bold]3. Export History Report[/]\n"
                "[dim]Save history to file[/dim]",
                border_style=THEME['success']
            ),
            Panel(
                "[bold]4. Back to Main Menu[/]\n"
                "[dim]Return to main interface[/dim]",
                border_style=THEME['danger']
            )
        )

        console.print(options)
        
        choice = input("\n[bold]Select history option (1-4): [/]").strip()
        
        try:  # WRAP THE MENU OPTIONS IN TRY-EXCEPT
            if choice == "1":
                try:
                    view_portfolio_history()
                except Exception as e:
                    console.print(Panel(
                        f"[red]Error: {str(e)}[/red]\n"
                        f"[yellow]Try running repair_audit_log() if this persists.[/yellow]",
                        border_style="red"
                    ))
                    if input("Attempt repair now? (y/n): ").lower() == 'y':
                        repair_audit_log()
                input("\nPress Enter to continue...")
                
            elif choice == "2":
                portfolio_name = select_portfolio(portfolios)
                if portfolio_name:
                    try:
                        view_portfolio_history(portfolio_name)
                    except Exception as e:
                        console.print(Panel(
                            f"[red]Error: {str(e)}[/red]\n"
                            f"[yellow]Try running repair_audit_log() if this persists.[/yellow]",
                            border_style="red"
                        ))
                        if input("Attempt repair now? (y/n): ").lower() == 'y':
                            repair_audit_log()
                    input("\nPress Enter to continue...")
                    
            elif choice == "3":
                export_history_report()
                
            elif choice == "4":
                return
            else:
                console.print("[red]Invalid choice.[/red]")
                time.sleep(1)
                
        except KeyboardInterrupt:  # SEPARATE HANDLING FOR CTRL+C
            console.print("\n[yellow]Operation cancelled by user.[/yellow]")
            time.sleep(1)
            return

def export_history_report():
    """Export complete audit history to a formatted report with repair capabilities"""
    # Check if audit log exists
    if not os.path.exists(AUDIT_LOG_FILE):
        console.print(Panel(
            "[red]Error: No audit log file found[/red]\n"
            "[yellow]No history has been recorded yet.[/yellow]",
            border_style="red"
        ))
        time.sleep(1.5)
        return

    # Attempt to read and parse the log
    try:
        with open(AUDIT_LOG_FILE, 'r') as f:
            raw_entries = [line.strip() for line in f.readlines() if line.strip()]
        
        # Validate entries
        valid_entries = []
        malformed_entries = 0
        
        for entry in raw_entries:
            parts = entry.split(" | ", 4)  # Split into exactly 5 parts
            if len(parts) == 5:
                valid_entries.append(parts)
            else:
                malformed_entries += 1

        # If too many malformed entries, suggest repair
        if malformed_entries > 0 and malformed_entries / len(raw_entries) > 0.1:
            console.print(Panel(
                f"[yellow]Warning: {malformed_entries} malformed entries found ({malformed_entries/len(raw_entries):.0%})[/yellow]\n"
                "[red]Export may be incomplete.[/red]",
                border_style="yellow"
            ))
            if input("Attempt to repair before exporting? (y/n): ").lower() == 'y':
                repair_audit_log()
                return export_history_report()  # Recursive retry after repair

        if not valid_entries:
            console.print(Panel(
                "[red]Error: No valid log entries found[/red]\n"
                "[yellow]The audit log may be corrupted.[/yellow]",
                border_style="red"
            ))
            return

        # Generate report filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"portfolio_audit_report_{timestamp}.txt"
        
        # Create report content
        report_content = [
            "PORTFOLIO MANAGEMENT SYSTEM - AUDIT HISTORY REPORT",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total entries: {len(valid_entries)}",
            f"Time range: {valid_entries[-1][0]} to {valid_entries[0][0]}",  # First to last timestamp
            "\n" + "="*80 + "\n"
        ]

        # Add formatted entries (newest first)
        for entry in reversed(valid_entries):
            timestamp, action, portfolio, stock, details = entry
            report_content.append(
                f"[{timestamp}] {action.upper()}\n"
                f"Portfolio: {portfolio}\n"
                f"{f'Stock: {stock} | ' if stock else ''}{details}\n"
                + "-"*40
            )

        # Write to file
        with open(report_filename, 'w') as f:
            f.write("\n".join(report_content))

        # Success message
        console.print(Panel(
            f"[green]✓ Successfully exported audit report[/green]\n"
            f"File: [bold]{report_filename}[/bold]\n"
            f"Entries: {len(valid_entries)}\n"
            f"Size: {os.path.getsize(report_filename)/1024:.1f} KB",
            border_style="green"
        ))

        # Open file option
        if sys.platform == "win32":
            if input("Open report file? (y/n): ").lower() == 'y':
                os.startfile(report_filename)
        else:
            console.print("[dim]Use your preferred text viewer to open the report[/dim]")

    except Exception as e:
        console.print(Panel(
            f"[red]Export failed![/red]\n"
            f"Error: {str(e)}\n\n"
            f"[yellow]Suggested fixes:[/yellow]\n"
            f"1. Run [bold]repair_audit_log()[/bold]\n"
            f"2. Check file permissions\n"
            f"3. Verify disk space",
            border_style="red"
        ))
        
        # Attempt automatic repair for certain errors
        if "malformed" in str(e).lower() or "decode" in str(e).lower():
            if input("Attempt automatic repair? (y/n): ").lower() == 'y':
                repair_audit_log()
                export_history_report()  # Retry after repair
                
def save_portfolios(portfolios):
    with open(PORTFOLIO_FILE, "w") as file:
        json.dump({k: v.to_dict(orient="records") for k, v in portfolios.items()}, file, indent=4)
    console.print("[green]Portfolios saved to file.[/green]")

def load_portfolios():
    if os.path.exists(PORTFOLIO_FILE):
        if os.path.getsize(PORTFOLIO_FILE) == 0:
            console.print("[yellow]Portfolios file is empty. Initializing empty portfolios.[/yellow]")
            return {}
        
        with open(PORTFOLIO_FILE, "r") as file:
            try:
                data = json.load(file)
                return {k: pd.DataFrame(v) for k, v in data.items()}
            except json.JSONDecodeError:
                console.print("[red]Error: Invalid JSON in portfolios file. Initializing empty portfolios.[/red]")
                return {}
    else:
        console.print("[yellow]Portfolios file not found. Initializing empty portfolios.[/yellow]")
        return {}

# Market indices data
INDICES = {
    'Indian': {
        'Nifty 50': {'ticker': '^NSEI', 'market_hours': '09:15-15:30 IST'},
        'Nifty Bank': {'ticker': '^NSEBANK', 'market_hours': '09:15-15:30 IST'},
        'Nifty Next 50': {'ticker': '^NSEMDCP50', 'market_hours': '09:15-15:30 IST'},
        'Nifty Midcap 100': {'ticker': 'NIFTY_MIDCAP_100.NS', 'market_hours': '09:15-15:30 IST'},
        'Nifty Smallcap 100': {'ticker': 'NIFTY_SMLCAP_100.NS', 'market_hours': '09:15-15:30 IST'},
        'India VIX': {'ticker': '^INDIAVIX', 'market_hours': '09:15-15:30 IST'}
    },
    'Global': {
        'Dow Jones': {'ticker': '^DJI', 'market_hours': '09:30-16:00 ET'},
        'S&P 500': {'ticker': '^GSPC', 'market_hours': '09:30-16:00 ET'},
        'NASDAQ': {'ticker': '^IXIC', 'market_hours': '09:30-16:00 ET'},
        'SGX Nifty': {'ticker': 'NQ1!', 'market_hours': '06:30-23:30 SGT'},
        'Nikkei 225': {'ticker': '^N225', 'market_hours': '09:00-11:30, 12:30-15:00 JST'},
        'Hang Seng': {'ticker': '^HSI', 'market_hours': '09:30-12:00, 13:00-16:00 HKT'},
        'DAX (Germany)': {'ticker': '^GDAXI', 'market_hours': '09:00-17:30 CET'},
        'FTSE 100 (UK)': {'ticker': '^FTSE', 'market_hours': '08:00-16:30 GMT'},
        'CAC 40 (France)': {'ticker': '^FCHI', 'market_hours': '09:00-17:30 CET'}
    }
}

def is_indian_market_open():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    # Check if it's a weekday (Monday to Friday)
    if now.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False
    
    # Check current time against market hours
    current_time = now.strftime('%H:%M')
    market_open = '09:15'
    market_close = '15:30'
    
    return market_open <= current_time <= market_close

def get_market_status(ticker, market_hours, is_indian_index=False):
    if is_indian_index:
        return "🟢 Open" if is_indian_market_open() else "🔴 Closed"
    
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d", interval="1m")
        return "🟢 Open" if not hist.empty else "🔴 Closed"
    except:
        return "🔴 Closed"

def fetch_index_data(index_name, ticker, market_hours, is_indian_index=False):
    try:
        index = yf.Ticker(ticker)
        
        # For Indian indices, we'll use the last available price
        if is_indian_index:
            data = index.history(period='5d')
            if data.empty:
                return None
            
            current_price = data['Close'].iloc[-1]
            prev_close = data['Close'].iloc[-2] if len(data) > 1 else current_price
            
            # If market is closed, show previous close as current price
            if not is_indian_market_open():
                current_price = prev_close
        else:
            # For global indices, try to get latest price
            data = index.history(period='1d', interval='1m')
            if data.empty:
                data = index.history(period='5d')
                if data.empty:
                    return None
            
            current_price = data['Close'].iloc[-1]
            prev_close = data['Close'].iloc[-2] if len(data) > 1 else current_price
        
        day_change = current_price - prev_close
        percent_change = (day_change / prev_close) * 100
        
        market_status = get_market_status(ticker, market_hours, is_indian_index)
        
        return {
            'Index': index_name,
            'Current': current_price,
            'Change': day_change,
            '% Change': percent_change,
            'Previous Close': prev_close,
            'Market Hours': market_hours,
            'Status': market_status
        }
    except Exception as e:
        console.print(f"[red]Error fetching data for {index_name}: {str(e)}[/red]")
        return None

def display_market_dashboard(indices_group):
    """Display market dashboard with multi-threaded data fetching and rich table display"""
    display_loading_animation(f"Fetching {indices_group} market data...")
    
    # Fetch data concurrently with progress tracking
    indices_data = []
    failed_indices = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task("Loading indices...", total=len(INDICES[indices_group]))
        
        def fetch_with_progress(index_name, index_info):
            is_indian = indices_group == 'Indian'
            data = fetch_index_data(
                index_name, 
                index_info['ticker'],
                index_info['market_hours'],
                is_indian
            )
            progress.update(task, advance=1)
            return index_name, data
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for index_name, index_info in INDICES[indices_group].items():
                futures.append(
                    executor.submit(
                        fetch_with_progress,
                        index_name,
                        index_info
                    )
                )
            
            for future in as_completed(futures):
                index_name, data = future.result()
                if data:
                    indices_data.append(data)
                else:
                    failed_indices.append(index_name)
    
    if not indices_data:
        console.print("[red]Failed to fetch all market data. Please check your internet connection.[/red]")
        return
    
    if failed_indices:
        console.print(f"[yellow]Warning: Could not fetch data for: {', '.join(failed_indices)}[/yellow]")
    
    # Create table with market status
    table = Table(title=f"\n🌍 {indices_group} Market Indices", show_header=True, 
                 header_style="bold bright_white on dark_blue", border_style="dim blue")
    
    # Add columns including market status
    columns = [
        ("Index", "bright_cyan", 25),
        ("Price", "bright_green", 15),
        ("Change", "bright_magenta", 15),
        ("% Change", "bright_magenta", 12),
        ("Prev Close", "bright_yellow", 15),
        ("Market Hours", "bright_white", 20),
        ("Status", None, 15)
    ]
    
    for col in columns:
        table.add_column(col[0], style=col[1], width=col[2])
    
    # Add rows with color coding and status
    for data in sorted(indices_data, key=lambda x: x['Index']):
        change_color = "bright_green" if data['Change'] >= 0 else "bright_red"
        pct_color = "bright_green" if data['% Change'] >= 0 else "bright_red"
        status_color = "bright_green" if "Open" in data['Status'] else "bright_red"
        
        table.add_row(
            data['Index'],
            f"{data['Current']:,.2f}",
            f"[{change_color}]{data['Change']:+,.2f}[/{change_color}]",
            f"[{pct_color}]{data['% Change']:+.2f}%[/{pct_color}]",
            f"{data['Previous Close']:,.2f}",
            data['Market Hours'],
            f"[{status_color}]{data['Status']}[/{status_color}]"
        )
    
    console.print(table)
    
    # Optional: Plot the data
    if input("\nShow visual performance chart? (y/n): ").lower() == 'y':
        plot_market_performance(indices_data, indices_group)

def plot_market_performance(indices_data, indices_group):
    df = pd.DataFrame(indices_data)
    df = df.sort_values('% Change', ascending=False)
    
    fig = sp.make_subplots(rows=1, cols=2, subplot_titles=[
        f"{indices_group} Index Prices",
        f"{indices_group} Daily Performance"
    ])
    
    # Price comparison
    fig.add_trace(
        go.Bar(
            x=df['Index'],
            y=df['Current'],
            name='Current Price',
            marker_color='cyan',
            text=df['Current'].apply(lambda x: f"{x:,.0f}"),
            textposition='auto'
        ),
        row=1, col=1
    )
    
    # Percentage change
    fig.add_trace(
        go.Bar(
            x=df['Index'],
            y=df['% Change'],
            name='% Change',
            marker_color=np.where(df['% Change'] >= 0, 'green', 'red'),
            text=df['% Change'].apply(lambda x: f"{x:+.2f}%"),
            textposition='auto'
        ),
        row=1, col=2
    )
    
    # Update layout
    fig.update_layout(
        title_text=f"{indices_group} Market Overview",
        height=600,
        showlegend=False,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color="white"),
        margin=dict(t=100, b=100, l=50, r=50)
    )
    
    # Update axes
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="% Change", row=1, col=2)
    fig.update_xaxes(tickangle=45)
    
    fig.show()

def market_analysis_menu():
    """Display the enhanced market analysis menu"""
    while True:
        console.clear()
        
        # Header
        console.print("\n[bold bright_white on dark_blue]  🌐 MARKET ANALYSIS  [/bold bright_white on dark_blue]")
        console.print("[dim]━" * 40 + "[/dim]")
        
        # Menu options
        menu = Table.grid(expand=True)
        menu.add_column(justify="center")
        
        menu.add_row(
            Panel(
                "[bright_white]1. Indian Market Indices[/bright_white]",
                border_style="bright_green",
                padding=(1, 10)
            )
        )
        menu.add_row(
            Panel(
                "[bright_white]2. Global Market Indices[/bright_white]",
                border_style="bright_blue",
                padding=(1, 10)
            )
        )
        menu.add_row(
            Panel(
                "[bright_white]3. Back to Main Menu[/bright_white]",
                border_style="bright_red",
                padding=(1, 10)
            )
        )
        
        console.print(menu)
        console.print("[dim]━" * 40 + "[/dim]")
        
        choice = input("\nEnter your choice: ")
        
        if choice == "1":
            display_market_dashboard('Indian')
            input("\nPress Enter to continue...")
        elif choice == "2":
            display_market_dashboard('Global')
            input("\nPress Enter to continue...")
        elif choice == "3":
            break
        else:
            console.print("[red]Invalid choice![/red]")
            time.sleep(1)

def main_menu():
    """Enhanced main menu with audit logging options"""
    console.clear()
    
    # Header with current time
    current_time = datetime.now().strftime("%a, %d %b %Y %H:%M:%S")
    console.print(
        Panel.fit(
            f"[bold #4CC9F0] STOCK PORTFOLIO MANAGER [/] [dim]{current_time}[/]",
            border_style="#4CC9F0",
            padding=(1, 2)
        ),
        justify="center"
    )

    # Portfolio summary
    with console.status("[bold #4CC9F0]Loading portfolio summary...[/]", spinner="dots"):
        time.sleep(0.5)  # Simulate loading
    
    # Main menu options
    menu_grid = Table.grid(expand=True, padding=(0, 3))
    menu_grid.add_column(justify="left", width=35)
    menu_grid.add_column(justify="left", width=35)

    menu_grid.add_row(
        Panel(
            "[bold #4CC9F0]1. Portfolio Management[/]\n"
            "[dim]Create/delete/modify portfolios[/]",
            border_style="#4CC9F0",
            padding=(1, 3)
        ),
        Panel(
            "[bold #F72585]2. Stock Operations[/]\n"
            "[dim]Add/edit/manage stocks[/]",
            border_style="#F72585",
            padding=(1, 3)
        )
    )
    
    menu_grid.add_row(
        Panel(
            "[bold #7209B7]3. Dashboard Views[/]\n"
            "[dim]Performance metrics & charts[/]",
            border_style="#7209B7",
            padding=(1, 3)
        ),
        Panel(
            "[bold #4AD66D]4. Market Analysis[/]\n"
            "[dim]Market indices & trends[/]",
            border_style="#4AD66D",
            padding=(1, 3)
        )
    )
    
    menu_grid.add_row(
        Panel(
            "[bold #F7B801]5. Data Operations[/]\n"
            "[dim]Import/export portfolio data[/]",
            border_style="#F7B801",
            padding=(1, 3)
        ),
        Panel(
            "[bold #4361EE]6. Audit & History[/]\n"
            "[dim]View change history[/]",
            border_style="#4361EE",
            padding=(1, 3)
        )
    )
    
    menu_grid.add_row(
        Panel(
            "[bold #EF233C]7. Exit Program[/]\n"
            "[dim]Save and quit[/]",
            border_style="#EF233C",
            padding=(1, 3)
        ),
        Panel("", border_style="black")  # Empty for layout
    )
    
    console.print(menu_grid)
    
    # Quick actions footer
    console.print("\n[bold #4CC9F0]Quick Navigation:[/]")
    quick_actions = Table.grid(expand=True, padding=(0, 2))
    quick_actions.add_column(width=18)
    quick_actions.add_column(width=18)
    quick_actions.add_column(width=18)
    quick_actions.add_column(width=18)
    
    quick_actions.add_row(
        "[dim][F1][/] Help",
        "[dim][F2][/] Refresh",
        "[dim][F3][/] Quick View",
        "[dim][F5][/] Export"
    )
    
    console.print(quick_actions)
    
    # Input with validation
    while True:
        try:
            console.print("\n[dim]Use number keys to select options[/]")
            choice = input("[bold #4CC9F0]» Select option (1-7): [/]").strip()
            if choice in {'1', '2', '3', '4', '5', '6', '7'}:
                return choice
            console.print("[red]Invalid choice! Please enter 1-7.[/red]")
            time.sleep(1)
            console.clear()
            return main_menu()  # Refresh menu on invalid input
        except KeyboardInterrupt:
            return "7"  # Exit on Ctrl+C

def main():
    """Enhanced main function with integrated audit logging and new features"""
    # Initialize with loading animation
    display_loading_animation("Loading Portfolio Tracker...")
    
    # Load portfolios with progress indication
    with console.status(f"[bold {THEME['primary']}]Loading your portfolios...[/]", spinner="dots"):
        portfolios = load_portfolios()
    
    try:
        while True:
            choice = main_menu()
            
            if choice == "1":  # Portfolio Management
                while True:
                    console.clear()
                    console.print(Panel(
                        "[bold]PORTFOLIO MANAGEMENT[/]",
                        style=f"bold {THEME['primary']}",
                        border_style=THEME['primary'],
                        subtitle="[dim]Create, organize, and manage portfolios[/dim]"
                    ))
                    
                    options = Table.grid(expand=True, padding=(0, 2))
                    options.add_column(justify="left", width=30)
                    options.add_column(justify="left", width=30)
                    
                    options.add_row(
                        Panel(
                            "[bold]1. Create Portfolio[/]\n"
                            "[dim]Start new investment portfolio[/dim]",
                            border_style=THEME['primary'],
                            padding=(1, 2)
                        ),
                        Panel(
                            "[bold]2. Delete Portfolio[/]\n"
                            "[dim]Remove existing portfolio[/dim]",
                            border_style=THEME['danger'],
                            padding=(1, 2)
                        )
                    )
                    options.add_row(
                        Panel(
                            "[bold]3. View All Portfolios[/]\n"
                            "[dim]List all portfolios[/dim]",
                            border_style=THEME['info'],
                            padding=(1, 2)
                        ),
                        Panel(
                            "[bold]4. Back to Main Menu[/]\n"
                            "[dim]Return to main interface[/dim]",
                            border_style=THEME['warning'],
                            padding=(1, 2)
                        )
                    )
                    
                    console.print(options)
                    
                    try:
                        sub_choice = input(f"\n[bold {THEME['primary']}]» Select option (1-4): [/]")
                    except KeyboardInterrupt:
                        break
                    
                    if sub_choice == "1":
                        create_portfolio(portfolios)
                    elif sub_choice == "2":
                        delete_portfolio(portfolios)
                    elif sub_choice == "3":
                        view_all_portfolios(portfolios)
                        input("\nPress Enter to continue...")
                    elif sub_choice == "4":
                        break
                    else:
                        console.print(Panel(
                            f"[{THEME['danger']}]Invalid choice! Please try again.[/]",
                            border_style=THEME['danger']
                        ))
                        time.sleep(1)
            
            elif choice == "2":  # Stock Operations
                while True:
                    console.clear()
                    console.print(Panel(
                        "[bold]STOCK OPERATIONS[/]",
                        style=f"bold {THEME['primary']}",
                        border_style=THEME['primary'],
                        subtitle="[dim]Manage individual stock holdings[/dim]"
                    ))
                    
                    options = Table.grid(expand=True, padding=(0, 2))
                    options.add_column(justify="left", width=30)
                    options.add_column(justify="left", width=30)
                    
                    options.add_row(
                        Panel(
                            "[bold]1. Add Stock[/]\n"
                            "[dim]Add new holding to portfolio[/dim]",
                            border_style=THEME['success'],
                            padding=(1, 2)
                        ),
                        Panel(
                            "[bold]2. Modify Stock[/]\n"
                            "[dim]Edit existing stock details[/dim]",
                            border_style=THEME['warning'],
                            padding=(1, 2)
                        )
                    )
                    options.add_row(
                        Panel(
                            "[bold]3. Manage Shares[/]\n"
                            "[dim]Add/remove shares of stock[/dim]",
                            border_style=THEME['info'],
                            padding=(1, 2)
                        ),
                        Panel(
                            "[bold]4. Back to Main Menu[/]\n"
                            "[dim]Return to main interface[/dim]",
                            border_style=THEME['danger'],
                            padding=(1, 2)
                        )
                    )
                    
                    console.print(options)
                    
                    try:
                        sub_choice = input(f"\n[bold {THEME['primary']}]» Select option (1-4): [/]")
                    except KeyboardInterrupt:
                        break
                    
                    if sub_choice == "1":
                        add_stock(portfolios)
                    elif sub_choice == "2":
                        modify_stock(portfolios)
                    elif sub_choice == "3":
                        manage_shares(portfolios)
                    elif sub_choice == "4":
                        break
                    else:
                        console.print(Panel(
                            f"[{THEME['danger']}]Invalid choice! Please try again.[/]",
                            border_style=THEME['danger']
                        ))
                        time.sleep(1)
            
            elif choice == "3":  # Dashboard Views
                while True:
                    console.clear()
                    console.print(Panel(
                        "[bold]DASHBOARD VIEWS[/]",
                        style=f"bold {THEME['primary']}",
                        border_style=THEME['primary'],
                        subtitle="[dim]Visualize portfolio performance[/dim]"
                    ))
                    
                    options = Table.grid(expand=True, padding=(0, 2))
                    options.add_column(justify="left", width=30)
                    options.add_column(justify="left", width=30)
                    
                    options.add_row(
                        Panel(
                            "[bold]1. Combined Dashboard[/]\n"
                            "[dim]All portfolios summary view[/dim]",
                            border_style=THEME['info'],
                            padding=(1, 2)
                        ),
                        Panel(
                            "[bold]2. Individual Dashboard[/]\n"
                            "[dim]Single portfolio detailed view[/dim]",
                            border_style=THEME['primary'],
                            padding=(1, 2)
                        )
                    )
                    options.add_row(
                        Panel(
                            "[bold]3. Performance Charts[/]\n"
                            "[dim]Interactive visualizations[/dim]",
                            border_style=THEME['secondary'],
                            padding=(1, 2)
                        ),
                        Panel(
                            "[bold]4. Back to Main Menu[/]\n"
                            "[dim]Return to main interface[/dim]",
                            border_style=THEME['danger'],
                            padding=(1, 2)
                        )
                    )
                    
                    console.print(options)
                    
                    try:
                        sub_choice = input(f"\n[bold {THEME['primary']}]» Select option (1-4): [/]")
                    except KeyboardInterrupt:
                        break
                    
                    if sub_choice == "1":
                        refresh_dashboard(portfolios)
                    elif sub_choice == "2":
                        portfolio_name = select_portfolio(portfolios)
                        if portfolio_name:
                            refresh_dashboard(portfolios, portfolio_name)
                    elif sub_choice == "3":
                        visualize_portfolio_performance(portfolios)
                    elif sub_choice == "4":
                        break
                    else:
                        console.print(Panel(
                            f"[{THEME['danger']}]Invalid choice! Please try again.[/]",
                            border_style=THEME['danger']
                        ))
                        time.sleep(1)
            
            elif choice == "4":  # Market Analysis
                market_analysis_menu()
            
            elif choice == "5":  # Data Operations
                while True:
                    console.clear()
                    console.print(Panel(
                        "[bold]DATA OPERATIONS[/]",
                        style=f"bold {THEME['primary']}",
                        border_style=THEME['primary'],
                        subtitle="[dim]Import/export portfolio data[/dim]"
                    ))
                    
                    options = Table.grid(expand=True, padding=(0, 2))
                    options.add_column(justify="left", width=30)
                    options.add_column(justify="left", width=30)
                    
                    options.add_row(
                        Panel(
                            "[bold]1. Export Portfolio[/]\n"
                            "[dim]Save single portfolio to file[/dim]",
                            border_style=THEME['success'],
                            padding=(1, 2)
                        ),
                        Panel(
                            "[bold]2. Export All Data[/]\n"
                            "[dim]Backup all portfolios[/dim]",
                            border_style=THEME['info'],
                            padding=(1, 2)
                        )
                    )
                    options.add_row(
                        Panel(
                            "[bold]3. Back to Main Menu[/]\n"
                            "[dim]Return to main interface[/dim]",
                            border_style=THEME['danger'],
                            padding=(1, 2)
                        ),
                        Panel("", border_style="black")  # Empty panel for layout
                    )
                    
                    console.print(options)
                    
                    try:
                        sub_choice = input(f"\n[bold {THEME['primary']}]» Select option (1-3): [/]")
                    except KeyboardInterrupt:
                        break
                    
                    if sub_choice == "1":
                        export_individual_portfolio(portfolios)
                        input("\nPress Enter to continue...")
                    elif sub_choice == "2":
                        export_all_portfolios(portfolios)
                        input("\nPress Enter to continue...")
                    elif sub_choice == "3":
                        break
                    else:
                        console.print(Panel(
                            f"[{THEME['danger']}]Invalid choice! Please try again.[/]",
                            border_style=THEME['danger']
                        ))
                        time.sleep(1)
            
            elif choice == "6":  # Audit & History
                portfolio_history_menu(portfolios)
            
            elif choice == "7":  # Exit
                save_portfolios(portfolios)
                console.print(Panel(
                    f"[{THEME['success']} bold]Portfolios saved. Exiting...[/]",
                    border_style=THEME['success']
                ))
                break
            
            else:
                console.print(Panel(
                    f"[{THEME['danger']} bold]Invalid choice! Please try again.[/]",
                    border_style=THEME['danger']
                ))
                time.sleep(1)
    
    except KeyboardInterrupt:
        save_portfolios(portfolios)
        console.print(Panel(
            f"[{THEME['success']} bold]Portfolios saved. Exiting...[/]",
            border_style=THEME['success']
        ))
        sys.exit(0)

if __name__ == "__main__":
    # Set terminal title and larger font
    console.print("\033]0;Stock Portfolio Tracker\007", end="")
    console.print("\033]50;{}\007".format("xft:DejaVu Sans Mono:size=14"), end="")
    
    main()