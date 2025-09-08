# %%
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
from rich.progress import track
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from rich.progress import Progress, SpinnerColumn, TextColumn
import time
import plotly.subplots as sp
import plotly.figure_factory as ff

# Initialize rich console
console = Console()

# File to store portfolios data
PORTFOLIO_FILE = "portfolios.json"


# %%
# Apply custom theme for Plotly
def apply_custom_theme():
    pio.templates["custom"] = go.layout.Template(
        layout=go.Layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="white", family="Arial", size=14),
            title=dict(x=0.5, font=dict(size=20)),
            xaxis=dict(showgrid=False, title_font=dict(size=16)),
            yaxis=dict(showgrid=False, title_font=dict(size=16)),
            colorway=px.colors.qualitative.Plotly,
            hoverlabel=dict(font_size=16),
            legend=dict(font_size=14)
        )
    )
    pio.templates.default = "custom"

apply_custom_theme()

# %%
def normalize_portfolio_name(name):
    return name.strip().lower()


# %%
def get_live_price_yahoo(ticker):
    try:
        stock = yf.Ticker(ticker)
        live_price = stock.history(period="1d")['Close'].iloc[-1]
        return round(live_price, 2)
    except Exception as e:
        console.print(f"[red]Error fetching price for {ticker}: {e}[/red]")
        return None

# %%
def get_previous_close(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="2d")
        if len(hist) < 2:
            return None
        return hist['Close'].iloc[-2]
    except Exception as e:
        console.print(f"[red]Error fetching previous close for {ticker}: {e}[/red]")
        return None


# %%
def validate_date(date_str):
    try:
        datetime.strptime(date_str, "%d-%m-%Y")
        return True
    except ValueError:
        return False

def validate_ticker(ticker):
    try:
        stock = yf.Ticker(ticker)
        stock.info
        return True
    except:
        return False

# %%
def calculate_metrics(portfolio):
    for index, row in portfolio.iterrows():
        ticker = row['Ticker Symbol']
        live_price = get_live_price_yahoo(ticker)
        if live_price is not None:
            portfolio.at[index, 'Current Price'] = live_price
            portfolio.at[index, 'Current Value'] = row['Quantity'] * live_price
            portfolio.at[index, 'Profit/Loss'] = portfolio.at[index, 'Current Value'] - row['Investment Value']
            if row['Investment Value'] != 0:
                portfolio.at[index, 'Profit/Loss %'] = (portfolio.at[index, 'Profit/Loss'] / row['Investment Value']) * 100
            else:
                portfolio.at[index, 'Profit/Loss %'] = 0
    return portfolio

# %%
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

# %%
def refresh_dashboard(portfolios, portfolio_name=None):
    try:
        while True:
            console.clear()
            if portfolio_name:
                user_input = display_individual_dashboard(portfolios, portfolio_name)
            else:
                user_input = display_combined_dashboard(portfolios)
            
            if user_input != 'r':
                break
    except KeyboardInterrupt:
        console.print("\n[bold green]Stopped refreshing dashboard.[/bold green]")

# %%
def display_loading_animation(message="Loading portfolio data..."):
    """Display a loading animation with rich"""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description=message, total=None)
        time.sleep(1.5)  # Simulate loading time

# %%
def display_combined_dashboard(portfolios):
    # Show loading animation
    display_loading_animation("Calculating combined portfolio performance...")
    
    if not portfolios:
        console.print("[yellow]No portfolios found. Please create a portfolio first.[/yellow]")
        return 'q'

    total_investment = 0
    total_current_value = 0
    total_profit_loss = 0
    total_daily_pl = 0

    # Animated table creation
    with console.status("[bold green]Building dashboard...[/]", spinner="dots"):
        table = Table(title="\n📊 [bold cyan]Combined Portfolio Dashboard[/bold cyan]", 
                     show_header=True, 
                     header_style="bold bright_white on dark_blue",
                     border_style="dim blue")
        
        # Add columns with slight delay for animation effect
        columns = [
            ("No.", "bright_cyan", 4),
            ("Portfolio", "bold bright_white", 20),
            ("Invested (₹)", "bright_green", 12),
            ("Current (₹)", "bright_green", 12),
            ("Total P/L (₹)", "bright_magenta", 14),
            ("Total P/L %", "bright_magenta", 12),
            ("Today's P/L", "bright_yellow", 12),
            ("Today's %", "bright_yellow", 10)
        ]
        
        for col in columns:
            table.add_column(col[0], style=col[1], width=col[2])
            time.sleep(0.1)  # Animation effect

    # Calculate metrics with progress animation
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task("Analyzing portfolios...", total=len(portfolios))
        
        for i, (portfolio_name, portfolio) in enumerate(portfolios.items(), start=1):
            if portfolio.empty:
                progress.update(task, advance=1)
                continue

            portfolio = calculate_metrics(portfolio)
            portfolio = calculate_daily_returns(portfolio)
            
            portfolio_investment = portfolio['Investment Value'].sum()
            portfolio_current_value = portfolio['Current Value'].sum()
            portfolio_profit_loss = portfolio['Profit/Loss'].sum()
            portfolio_profit_loss_percent = (portfolio_profit_loss / portfolio_investment) * 100 if portfolio_investment != 0 else 0
            portfolio_daily_pl = portfolio['Daily P/L'].sum()
            portfolio_daily_return = (portfolio_daily_pl / portfolio_current_value) * 100 if portfolio_current_value != 0 else 0

            total_investment += portfolio_investment
            total_current_value += portfolio_current_value
            total_profit_loss += portfolio_profit_loss
            total_daily_pl += portfolio_daily_pl

            # Color thresholds
            if portfolio_profit_loss >= portfolio_investment * 0.1:
                profit_loss_color = "bold bright_green"
            elif portfolio_profit_loss >= 0:
                profit_loss_color = "green"
            elif portfolio_profit_loss <= -portfolio_investment * 0.1:
                profit_loss_color = "bold bright_red"
            else:
                profit_loss_color = "red"

            if portfolio_daily_pl >= portfolio_current_value * 0.02:
                daily_color = "bold bright_green"
            elif portfolio_daily_pl >= 0:
                daily_color = "green"
            elif portfolio_daily_pl <= -portfolio_current_value * 0.02:
                daily_color = "bold bright_red"
            else:
                daily_color = "red"
            
            table.add_row(
                f"[bright_white]{i}[/bright_white]",
                f"[bright_cyan]{portfolio_name}[/bright_cyan]",
                f"[bright_green]{portfolio_investment:,.2f}[/bright_green]",
                f"[bright_green]{portfolio_current_value:,.2f}[/bright_green]",
                f"[{profit_loss_color}]{portfolio_profit_loss:+,.2f}[/{profit_loss_color}]",
                f"[{profit_loss_color}]{portfolio_profit_loss_percent:+.2f}%[/{profit_loss_color}]",
                f"[{daily_color}]{portfolio_daily_pl:+,.2f}[/{daily_color}]",
                f"[{daily_color}]{portfolio_daily_return:+.2f}%[/{daily_color}]"
            )
            progress.update(task, advance=1)
            time.sleep(0.2)  # Animation effect between rows

    if total_investment == 0:
        console.print("[yellow]No stocks found in any portfolio.[/yellow]")
        return 'q'

    console.print(table)

    # Animated summary calculation
    with console.status("[bold green]Calculating summary metrics...[/]", spinner="bouncingBall"):
        total_profit_loss_percent = (total_profit_loss / total_investment) * 100 if total_investment != 0 else 0
        total_daily_return = (total_daily_pl / total_current_value) * 100 if total_current_value != 0 else 0
        time.sleep(1)

    # Summary with color animation
    console.print("\n[bold bright_white on dark_blue]📈 Portfolio Summary[/bold bright_white on dark_blue]")
    for metric in [
        f"💰 [bold]Total Invested:[/bold] [bright_green]₹{total_investment:,.2f}[/bright_green]",
        f"📈 [bold]Current Value:[/bold] [bright_green]₹{total_current_value:,.2f}[/bright_green]",
        f"📊 [bold]Total P/L:[/bold] [{'bold bright_green' if total_profit_loss >= 0 else 'bold bright_red'}]{total_profit_loss:+,.2f} ({total_profit_loss_percent:+.2f}%)[/]",
        f"📅 [bold]Today's P/L:[/bold] [{'bold bright_green' if total_daily_pl >= 0 else 'bold bright_red'}]{total_daily_pl:+,.2f}[/]",
        f"📅 [bold]Today's Return:[/bold] [{'bold bright_green' if total_daily_return >= 0 else 'bold bright_red'}]{total_daily_return:+.2f}%[/]"
    ]:
        console.print(metric)
        time.sleep(0.3)  # Animate summary items

    # Animated menu
    console.print("\n[bold bright_white on dark_blue] OPTIONS [/bold bright_white on dark_blue]")
    for option in [
        "[bright_cyan][r][/bright_cyan] Refresh",
        "[bright_yellow][q][/bright_yellow] Quit",
        "[bright_magenta][b][/bright_magenta] Go Back"
    ]:
        console.print(option, end="  ")
        time.sleep(0.15)
    console.print()  # New line after options
    
    user_input = input("Enter your choice: ").lower()
    return user_input

def display_individual_dashboard(portfolios, portfolio_name):
    # Show loading animation
    display_loading_animation(f"Analyzing {portfolio_name} portfolio...")
    
    if portfolio_name not in portfolios:
        console.print(f"[red]Portfolio '{portfolio_name}' not found.[/red]")
        return 'q'

    portfolio = portfolios[portfolio_name]
    if portfolio.empty:
        console.print(f"[yellow]Portfolio '{portfolio_name}' is empty.[/yellow]")
        return 'q'

    # Calculate metrics with animation
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description="Processing stocks...", total=len(portfolio))
        portfolio = calculate_metrics(portfolio)
        portfolio = calculate_daily_returns(portfolio)
        time.sleep(1)  # Simulate processing time
    
    # Animated table creation
    with console.status("[bold green]Building stock table...[/]", spinner="dots"):
        stock_table = Table(title=f"\n📋 [bold blue]{portfolio_name} Performance[/bold blue]", 
                          show_header=True, 
                          header_style="bold bright_white on blue",
                          border_style="dim blue")
        
        # Add columns with animation
        columns = [
            ("No.", "bright_cyan", 4),
            ("Stock", "bright_white", 20),
            ("Qty", "bright_green", 8),
            ("Price", "bright_green", 10),
            ("Today %", "bright_yellow", 10),
            ("Today ₹", "bright_yellow", 12),
            ("Total P/L ₹", "bright_magenta", 14),
            ("Total P/L %", "bright_magenta", 12)
        ]
        
        for col in columns:
            stock_table.add_column(col[0], style=col[1], width=col[2])
            time.sleep(0.1)

    # Add rows with animation
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task("Adding stocks...", total=len(portfolio))
        
        for index, row in portfolio.iterrows():
            total_color = ("bold bright_green" if row['Profit/Loss'] >= row['Investment Value'] * 0.1 
                          else "green" if row['Profit/Loss'] >= 0 
                          else "bold bright_red" if row['Profit/Loss'] <= -row['Investment Value'] * 0.1 
                          else "red")
            
            daily_color = ("bold bright_green" if row['Daily P/L'] >= row['Current Value'] * 0.02 
                         else "green" if row['Daily P/L'] >= 0 
                         else "bold bright_red" if row['Daily P/L'] <= -row['Current Value'] * 0.02 
                         else "red")
            
            stock_table.add_row(
                f"[bright_white]{index + 1}[/bright_white]",
                f"[bright_cyan]{row['Stock Name']}[/bright_cyan]",
                f"[green]{row['Quantity']}[/green]",
                f"[bright_green]{row['Current Price']:.2f}[/bright_green]",
                f"[{daily_color}]{row['Daily Return %']:+.2f}%[/{daily_color}]",
                f"[{daily_color}]{row['Daily P/L']:+,.2f}[/{daily_color}]",
                f"[{total_color}]{row['Profit/Loss']:+,.2f}[/{total_color}]",
                f"[{total_color}]{row['Profit/Loss %']:+.2f}%[/{total_color}]"
            )
            progress.update(task, advance=1)
            time.sleep(0.15)

    console.print(stock_table)

    # Calculate and animate summary
    with console.status("[bold green]Calculating portfolio summary...[/]", spinner="bouncingBall"):
        total_investment = portfolio['Investment Value'].sum()
        total_current_value = portfolio['Current Value'].sum()
        total_profit_loss = portfolio['Profit/Loss'].sum()
        total_profit_loss_percent = (total_profit_loss / total_investment) * 100 if total_investment != 0 else 0
        total_daily_pl = portfolio['Daily P/L'].sum()
        total_daily_return = (total_daily_pl / total_current_value) * 100 if total_current_value != 0 else 0
        time.sleep(1)

    # Animated summary display
    console.print("\n[bold bright_white on blue]📊 Portfolio Summary[/bold bright_white on blue]")
    summary_items = [
        f"💰 [bold]Invested:[/bold] [bright_green]₹{total_investment:,.2f}[/bright_green]",
        f"📈 [bold]Current Value:[/bold] [bright_green]₹{total_current_value:,.2f}[/bright_green]",
        f"📊 [bold]Total P/L:[/bold] [{'bold bright_green' if total_profit_loss >= 0 else 'bold bright_red'}]{total_profit_loss:+,.2f} ({total_profit_loss_percent:+.2f}%)[/]",
        f"📅 [bold]Today's P/L:[/bold] [{'bold bright_green' if total_daily_pl >= 0 else 'bold bright_red'}]{total_daily_pl:+,.2f}[/]",
        f"📅 [bold]Today's Return:[/bold] [{'bold bright_green' if total_daily_return >= 0 else 'bold bright_red'}]{total_daily_return:+.2f}%[/]"
    ]
    
    for item in summary_items:
        console.print(item)
        time.sleep(0.3)

    # Animated options menu
    console.print("\n[bold bright_white on blue] OPTIONS [/bold bright_white on blue]")
    options = [
        "[bright_cyan][r][/bright_cyan] Refresh",
        "[bright_yellow][q][/bright_yellow] Quit",
        "[bright_magenta][b][/bright_magenta] Go Back"
    ]
    for option in options:
        console.print(option, end="  ")
        time.sleep(0.15)
    console.print()
    
    user_input = input("Enter your choice: ").lower()
    return user_input

# %%
def display_individual_dashboard(portfolios, portfolio_name):
    if portfolio_name not in portfolios:
        console.print(f"[red]Portfolio '{portfolio_name}' not found.[/red]")
        return 'q'

    portfolio = portfolios[portfolio_name]
    if portfolio.empty:
        console.print(f"[yellow]Portfolio '{portfolio_name}' is empty.[/yellow]")
        return 'q'

    portfolio = calculate_metrics(portfolio)
    portfolio = calculate_daily_returns(portfolio)
    
    total_investment = portfolio['Investment Value'].sum()
    total_current_value = portfolio['Current Value'].sum()
    total_profit_loss = portfolio['Profit/Loss'].sum()
    total_profit_loss_percent = (total_profit_loss / total_investment) * 100 if total_investment != 0 else 0
    total_daily_pl = portfolio['Daily P/L'].sum()
    total_daily_return = (total_daily_pl / total_current_value) * 100 if total_current_value != 0 else 0

    profit_loss_color = "green" if total_profit_loss >= 0 else "red"
    daily_color = "green" if total_daily_pl >= 0 else "red"

    console.print(f"\n[bold]📊 Individual Dashboard: {portfolio_name}[/bold]")
    console.print(f"💰 Invested: [green]₹{total_investment:,.2f}[/green]")
    console.print(f"📈 Current Value: [green]₹{total_current_value:,.2f}[/green]")
    console.print(f"📊 Total P/L: [{profit_loss_color}]₹{total_profit_loss:,.2f} ({total_profit_loss_percent:.2f}%)[/]")
    console.print(f"📅 Today's P/L: [{daily_color}]₹{total_daily_pl:,.2f}[/]")
    console.print(f"📅 Today's Return: [{daily_color}]{total_daily_return:.2f}%[/]")

    stock_table = Table(title=f"\n📋 Stock Performance", show_header=True, header_style="bold blue")
    stock_table.add_column("No.", justify="left", style="cyan", no_wrap=True)
    stock_table.add_column("Stock", justify="left", style="cyan", no_wrap=True)
    stock_table.add_column("Qty", justify="right", style="green")
    stock_table.add_column("Price", justify="right", style="green")
    stock_table.add_column("Today %", justify="right", style="yellow")
    stock_table.add_column("Today ₹", justify="right", style="yellow")
    stock_table.add_column("Total P/L ₹", justify="right", style="magenta")
    stock_table.add_column("Total P/L %", justify="right", style="magenta")

    for index, row in portfolio.iterrows():
        total_color = "green" if row['Profit/Loss'] >= 0 else "red"
        daily_color = "green" if row['Daily P/L'] >= 0 else "red"
        
        stock_table.add_row(
            str(index + 1),
            row['Stock Name'],
            str(row['Quantity']),
            f"{row['Current Price']:.2f}",
            f"[{daily_color}]{row['Daily Return %']:.2f}%[/]",
            f"[{daily_color}]{row['Daily P/L']:,.2f}[/]",
            f"[{total_color}]{row['Profit/Loss']:,.2f}[/]",
            f"[{total_color}]{row['Profit/Loss %']:.2f}%[/]"
        )

    console.print(stock_table)

    console.print("\n[r]Refresh  [q]Quit  [b]Go Back")
    user_input = input("Enter your choice: ").lower()
    return user_input

# %%
def plot_portfolio_allocation(portfolio, portfolio_name):
    if portfolio.empty:
        console.print(f"[yellow]Portfolio '{portfolio_name}' is empty. No allocation to plot.[/yellow]")
        return

    fig = px.pie(portfolio, values='Current Value', names='Stock Name', title=f"Portfolio Allocation: {portfolio_name}")
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.show()

# %%
def plot_profit_loss(portfolio, portfolio_name):
    if portfolio.empty:
        console.print(f"[yellow]Portfolio '{portfolio_name}' is empty. No profit/loss to plot.[/yellow]")
        return

    fig = px.bar(portfolio, x='Stock Name', y='Profit/Loss', color='Profit/Loss',
                 color_continuous_scale=['red', 'green'], title=f"Profit/Loss by Stock: {portfolio_name}")
    fig.update_layout(xaxis_title="Stock Name", yaxis_title="Profit/Loss (₹)")
    fig.show()

# %%
def plot_daily_performance(portfolio, portfolio_name):
    if portfolio.empty:
        console.print(f"[yellow]Portfolio '{portfolio_name}' is empty. No daily performance to plot.[/yellow]")
        return

    portfolio = portfolio.sort_values('Daily Return %', ascending=False)
    
    fig = px.bar(portfolio, x='Stock Name', y='Daily Return %', 
                 color='Daily Return %',
                 color_continuous_scale=['red', 'green'],
                 title=f"Today's Performance: {portfolio_name}")
    fig.update_layout(xaxis_title="Stock Name", yaxis_title="Daily Return (%)")
    fig.add_hline(y=0, line_width=1, line_dash="dash", line_color="white")
    fig.show()


# %%
def create_portfolio(portfolios):
    while True:
        console.print("\n[bold]--- Create New Portfolio ---[/bold]")
        portfolio_name = input("Enter a name for the new portfolio (or 'b' to go back): ")
        
        if portfolio_name.lower() == 'b':
            return
        
        if not portfolio_name.strip():
            console.print("[red]Portfolio name cannot be empty.[/red]")
            continue
            
        normalized_portfolio_name = normalize_portfolio_name(portfolio_name)
        existing_portfolio_name = next((name for name in portfolios.keys() if normalize_portfolio_name(name) == normalized_portfolio_name), None)
        
        if existing_portfolio_name:
            console.print(f"[red]Portfolio '{existing_portfolio_name}' already exists.[/red]")
        else:
            portfolios[portfolio_name] = pd.DataFrame(columns=[
                'Portfolio Name', 'Stock Name', 'Ticker Symbol', 'Quantity', 'Purchase Price',
                'Purchase Date', 'Sector', 'Investment Value', 'Current Price', 'Current Value',
                'Profit/Loss', 'Profit/Loss %', 'Daily Return %', 'Daily P/L'
            ])
            console.print(f"[green]Portfolio '{portfolio_name}' created successfully.[/green]")
            return

# %%
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

    # Display existing stocks in the portfolio
    portfolio = portfolios[portfolio_name]
    if not portfolio.empty:
        console.print(f"\n[bold]Existing stocks in '{portfolio_name}':[/bold]")
        stock_table = Table(show_header=True, header_style="bold magenta")
        stock_table.add_column("No.", style="cyan", width=4)
        stock_table.add_column("Stock Name", style="bright_white", min_width=20)
        stock_table.add_column("Ticker", style="green", width=12)
        stock_table.add_column("Qty", style="bright_green", width=8)
        stock_table.add_column("Avg Price", style="bright_yellow", width=12)
        
        for index, row in portfolio.iterrows():
            stock_table.add_row(
                str(index + 1),
                row['Stock Name'],
                row['Ticker Symbol'],
                str(row['Quantity']),
                f"{row['Purchase Price']:.2f}"
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
                console.print(f"[red]This ticker already exists in the portfolio.[/red]")
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
    console.print(f"  Quantity: {quantity} @ ₹{purchase_price:.2f} (Total: ₹{quantity*purchase_price:.2f})")

# %%
def manage_shares(portfolios):
    while True:
        portfolio_name = select_portfolio(portfolios)
        if not portfolio_name:
            return

        portfolio = portfolios[portfolio_name]
        if portfolio.empty:
            console.print(f"[yellow]Portfolio '{portfolio_name}' is empty. No shares to manage.[/yellow]")
            return

        console.print("\n[bold]--- Select a Stock ---[/bold]")
        for i, row in portfolio.iterrows():
            console.print(f"{i + 1}. {row['Stock Name']} (Ticker: {row['Ticker Symbol']})")
        console.print(f"{len(portfolio)+1}. Go Back")

        while True:
            stock_choice = input("\nEnter the number corresponding to the stock (or 'b' to go back): ")
            
            if stock_choice.lower() == 'b':
                break  # Exit the stock selection loop and go back to portfolio selection
                
            try:
                stock_choice = int(stock_choice)
                if 1 <= stock_choice <= len(portfolio):
                    stock_index = stock_choice - 1
                    
                    stock_name = portfolio.at[stock_index, 'Stock Name']
                    ticker_symbol = portfolio.at[stock_index, 'Ticker Symbol']

                    console.print(f"\nSelected Stock: {stock_name} (Ticker: {ticker_symbol})")

                    console.print("\n1. Add Shares")
                    console.print("2. Remove Shares")
                    console.print("3. Go Back")
                    choice = input("Enter your choice: ")

                    if choice == "1":
                        while True:
                            quantity_to_add = input("Enter quantity to add (or 'b' to go back): ")
                            
                            if quantity_to_add.lower() == 'b':
                                break
                                
                            if quantity_to_add.isdigit() and int(quantity_to_add) > 0:
                                quantity_to_add = int(quantity_to_add)
                                break
                            else:
                                console.print("[red]Invalid quantity. Please enter a positive integer.[/red]")

                        while True:
                            purchase_price = input("Enter purchase price (or 'b' to go back): ")
                            
                            if purchase_price.lower() == 'b':
                                break
                                
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
                                break
                                
                            if validate_date(purchase_date):
                                break
                            else:
                                console.print("[red]Invalid date format. Please enter the date in DD-MM-YYYY format.[/red]")

                        existing_quantity = portfolio.at[stock_index, 'Quantity']
                        existing_investment = portfolio.at[stock_index, 'Investment Value']
                        new_quantity = existing_quantity + quantity_to_add
                        new_investment = existing_investment + (quantity_to_add * purchase_price)
                        new_purchase_price = new_investment / new_quantity

                        portfolio.at[stock_index, 'Quantity'] = new_quantity
                        portfolio.at[stock_index, 'Purchase Price'] = new_purchase_price
                        portfolio.at[stock_index, 'Investment Value'] = new_investment
                        portfolio.at[stock_index, 'Purchase Date'] = purchase_date

                        console.print(f"[green]Added {quantity_to_add} shares to '{stock_name}' in portfolio '{portfolio_name}'.[/green]")
                        break

                    elif choice == "2":
                        while True:
                            quantity_to_remove = input("Enter quantity to remove (or 'b' to go back): ")
                            
                            if quantity_to_remove.lower() == 'b':
                                break
                                
                            if quantity_to_remove.isdigit() and int(quantity_to_remove) > 0:
                                quantity_to_remove = int(quantity_to_remove)
                                break
                            else:
                                console.print("[red]Invalid quantity. Please enter a positive integer.[/red]")

                        if quantity_to_remove > portfolio.at[stock_index, 'Quantity']:
                            console.print("[red]Cannot remove more shares than available.[/red]")
                            continue

                        portfolio.at[stock_index, 'Quantity'] -= quantity_to_remove
                        portfolio.at[stock_index, 'Investment Value'] = portfolio.at[stock_index, 'Quantity'] * portfolio.at[stock_index, 'Purchase Price']
                        console.print(f"[green]Removed {quantity_to_remove} shares from '{stock_name}' in portfolio '{portfolio_name}'.[/green]")
                        break
                        
                    elif choice == "3":
                        break  # Go back to stock selection
                    else:
                        console.print("[red]Invalid choice.[/red]")
                        continue
                        
                elif stock_choice == len(portfolio)+1:
                    return  # Go back to main menu
                else:
                    console.print("[red]Invalid choice. Please enter a valid number.[/red]")
            except ValueError:
                console.print("[red]Invalid input. Please enter a number.[/red]")
                

# %%
def delete_portfolio(portfolios):
    while True:
        portfolio_name = select_portfolio(portfolios)
        if not portfolio_name:
            return

        confirm = input(f"Are you sure you want to delete portfolio '{portfolio_name}'? (y/n/b): ").lower()
        if confirm == 'y':
            del portfolios[portfolio_name]
            console.print(f"[green]Portfolio '{portfolio_name}' deleted.[/green]")
            break
        elif confirm == 'b':
            return
        else:
            console.print("[yellow]Deletion cancelled.[/yellow]")
            break
        

# %%
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


# %%
def view_all_portfolios(portfolios):
    if not portfolios:
        console.print("[red]No portfolios found.[/red]")
        return

    console.print("\n[bold]--- All Portfolios ---[/bold]")
    for i, portfolio_name in enumerate(portfolios, start=1):
        console.print(f"{i}. {portfolio_name}")


# %%
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


# %%
def export_individual_portfolio(portfolios):
    portfolio_name = select_portfolio(portfolios)
    if not portfolio_name:
        return

    portfolio = portfolios[portfolio_name]
    file_name = f"{portfolio_name}_portfolio.xlsx"
    portfolio.to_excel(file_name, index=False)
    console.print(f"[green]Portfolio '{portfolio_name}' exported to '{file_name}'.[/green]")


# %%
def export_all_portfolios(portfolios):
    if not portfolios:
        console.print("[red]No portfolios found to export.[/red]")
        return

    with pd.ExcelWriter("all_portfolios.xlsx") as writer:
        for portfolio_name, portfolio in portfolios.items():
            portfolio.to_excel(writer, sheet_name=portfolio_name, index=False)
    console.print("[green]All portfolios exported to 'all_portfolios.xlsx'.[/green]")


# %%
def save_portfolios(portfolios):
    with open(PORTFOLIO_FILE, "w") as file:
        json.dump({k: v.to_dict(orient="records") for k, v in portfolios.items()}, file)
    console.print("[green]Portfolios saved to file.[/green]")


# %%
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

# %%
def main():
    portfolios = load_portfolios()

    try:
        while True:
            console.print("\n[bold]--- Stock Portfolio Tracker ---[/bold]")
            console.print("1. Create Portfolio")
            console.print("2. Add Stock to Portfolio")
            console.print("3. Manage Shares (Add/Remove)")
            console.print("4. Modify Stock Details")
            console.print("5. Delete Portfolio")
            console.print("6. View Combined Dashboard")
            console.print("7. View Individual Dashboard")
            console.print("8. Export Individual Portfolio to Excel")
            console.print("9. Export All Portfolios to Excel")
            console.print("10. Exit")
            choice = input("\nEnter your choice: ")

            if choice == "1":
                create_portfolio(portfolios)
            elif choice == "2":
                add_stock(portfolios)
            elif choice == "3":
                manage_shares(portfolios)
            elif choice == "4":
                modify_stock(portfolios)
            elif choice == "5":
                delete_portfolio(portfolios)
            elif choice == "6":
                refresh_dashboard(portfolios)
            elif choice == "7":
                portfolio_name = select_portfolio(portfolios)
                if portfolio_name:
                    refresh_dashboard(portfolios, portfolio_name)
            elif choice == "8":
                export_individual_portfolio(portfolios)
            elif choice == "9":
                export_all_portfolios(portfolios)
            elif choice == "10":
                save_portfolios(portfolios)
                console.print("[bold green]Exiting...[/bold green]")
                break
            else:
                console.print("[bold red]Invalid choice. Please try again.[/bold red]")
    except KeyboardInterrupt:
        save_portfolios(portfolios)
        console.print("\n[bold green]Portfolios saved. Exiting...[/bold green]")
        sys.exit(0)

if __name__ == "__main__":
    main()

# %%



