import pandas as pd
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

# Initialize rich console
console = Console()

# File to store portfolios data
PORTFOLIO_FILE = "portfolios.json"

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

def normalize_portfolio_name(name):
    return name.strip().lower()

def get_live_price_yahoo(ticker):
    try:
        stock = yf.Ticker(ticker)
        live_price = stock.history(period="1d")['Close'].iloc[-1]
        return round(live_price, 2)
    except Exception as e:
        console.print(f"[red]Error fetching price for {ticker}: {e}[/red]")
        return None

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
                user_input = display_individual_dashboard(portfolios, portfolio_name)
            else:
                user_input = display_combined_dashboard(portfolios)
            
            if user_input != 'r':
                break
    except KeyboardInterrupt:
        console.print("\n[bold green]Stopped refreshing dashboard.[/bold green]")

def display_combined_dashboard(portfolios):
    if not portfolios:
        console.print("[yellow]No portfolios found. Please create a portfolio first.[/yellow]")
        return 'q'

    total_investment = 0
    total_current_value = 0
    total_profit_loss = 0
    total_daily_pl = 0

    table = Table(title="\n📊 Combined Portfolio Dashboard", show_header=True, header_style="bold magenta")
    table.add_column("No.", justify="left", style="cyan", no_wrap=True)
    table.add_column("Portfolio", justify="left", style="cyan", no_wrap=True)
    table.add_column("Invested (₹)", justify="right", style="green")
    table.add_column("Current (₹)", justify="right", style="green")
    table.add_column("Total P/L (₹)", justify="right", style="magenta")
    table.add_column("Total P/L %", justify="right", style="magenta")
    table.add_column("Today's P/L", justify="right", style="yellow")
    table.add_column("Today's %", justify="right", style="yellow")

    for i, (portfolio_name, portfolio) in enumerate(track(portfolios.items(), description="Processing portfolios..."), start=1):
        if portfolio.empty:
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

        profit_loss_color = "green" if portfolio_profit_loss >= 0 else "red"
        daily_color = "green" if portfolio_daily_pl >= 0 else "red"
        
        table.add_row(
            str(i),
            portfolio_name,
            f"{portfolio_investment:,.2f}",
            f"{portfolio_current_value:,.2f}",
            f"[{profit_loss_color}]{portfolio_profit_loss:,.2f}[/]",
            f"[{profit_loss_color}]{portfolio_profit_loss_percent:.2f}%[/]",
            f"[{daily_color}]{portfolio_daily_pl:,.2f}[/]",
            f"[{daily_color}]{portfolio_daily_return:.2f}%[/]"
        )

    if total_investment == 0:
        console.print("[yellow]No stocks found in any portfolio.[/yellow]")
        return 'q'

    console.print(table)

    total_profit_loss_percent = (total_profit_loss / total_investment) * 100 if total_investment != 0 else 0
    total_daily_return = (total_daily_pl / total_current_value) * 100 if total_current_value != 0 else 0
    
    total_profit_loss_color = "green" if total_profit_loss >= 0 else "red"
    total_daily_color = "green" if total_daily_pl >= 0 else "red"

    console.print("\n[bold]📈 Combined Portfolio Metrics[/bold]")
    console.print(f"💰 Total Invested: [green]₹{total_investment:,.2f}[/green]")
    console.print(f"📈 Current Value: [green]₹{total_current_value:,.2f}[/green]")
    console.print(f"📊 Total P/L: [{total_profit_loss_color}]₹{total_profit_loss:,.2f} ({total_profit_loss_percent:.2f}%)[/]")
    console.print(f"📅 Today's P/L: [{total_daily_color}]₹{total_daily_pl:,.2f}[/]")
    console.print(f"📅 Today's Return: [{total_daily_color}]{total_daily_return:.2f}%[/]")

    console.print("\n[r]Refresh  [q]Quit  [b]Go Back")
    user_input = input("Enter your choice: ").lower()
    return user_input

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

def plot_portfolio_allocation(portfolio, portfolio_name):
    if portfolio.empty:
        console.print(f"[yellow]Portfolio '{portfolio_name}' is empty. No allocation to plot.[/yellow]")
        return

    fig = px.pie(portfolio, values='Current Value', names='Stock Name', title=f"Portfolio Allocation: {portfolio_name}")
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.show()

def plot_profit_loss(portfolio, portfolio_name):
    if portfolio.empty:
        console.print(f"[yellow]Portfolio '{portfolio_name}' is empty. No profit/loss to plot.[/yellow]")
        return

    fig = px.bar(portfolio, x='Stock Name', y='Profit/Loss', color='Profit/Loss',
                 color_continuous_scale=['red', 'green'], title=f"Profit/Loss by Stock: {portfolio_name}")
    fig.update_layout(xaxis_title="Stock Name", yaxis_title="Profit/Loss (₹)")
    fig.show()

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

    while True:
        console.print("\n[bold]--- Add Stock to Portfolio ---[/bold]")
        stock_name = input("Enter stock name (or 'b' to go back): ")
        
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
            break
        else:
            console.print("[red]Invalid ticker symbol. Please try again.[/red]")

    if portfolio_name in portfolios:
        if not portfolios[portfolio_name].empty and ticker_symbol in portfolios[portfolio_name]['Ticker Symbol'].values:
            console.print(f"[red]Stock with ticker symbol '{ticker_symbol}' already exists in portfolio '{portfolio_name}'.[/red]")
            return

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

    console.print(f"[green]Stock '{stock_name}' added to portfolio '{portfolio_name}'.[/green]")

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

def view_all_portfolios(portfolios):
    if not portfolios:
        console.print("[red]No portfolios found.[/red]")
        return

    console.print("\n[bold]--- All Portfolios ---[/bold]")
    for i, portfolio_name in enumerate(portfolios, start=1):
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

def export_individual_portfolio(portfolios):
    portfolio_name = select_portfolio(portfolios)
    if not portfolio_name:
        return

    portfolio = portfolios[portfolio_name]
    file_name = f"{portfolio_name}_portfolio.xlsx"
    portfolio.to_excel(file_name, index=False)
    console.print(f"[green]Portfolio '{portfolio_name}' exported to '{file_name}'.[/green]")

def export_all_portfolios(portfolios):
    if not portfolios:
        console.print("[red]No portfolios found to export.[/red]")
        return

    with pd.ExcelWriter("all_portfolios.xlsx") as writer:
        for portfolio_name, portfolio in portfolios.items():
            portfolio.to_excel(writer, sheet_name=portfolio_name, index=False)
    console.print("[green]All portfolios exported to 'all_portfolios.xlsx'.[/green]")

def view_graphs(portfolios):
    portfolio_name = select_portfolio(portfolios)
    if not portfolio_name:
        return

    portfolio = portfolios[portfolio_name]
    if portfolio.empty:
        console.print(f"[yellow]Portfolio '{portfolio_name}' is empty.[/yellow]")
        return

    portfolio = calculate_metrics(portfolio)
    portfolio = calculate_daily_returns(portfolio)

    while True:
        console.print("\n[bold]📈 Graph Options:[/bold]")
        console.print("1. Portfolio Allocation")
        console.print("2. Total Performance")
        console.print("3. Today's Performance")
        console.print("4. Go Back")
        choice = input("Enter your choice: ")

        if choice == "1":
            plot_portfolio_allocation(portfolio, portfolio_name)
        elif choice == "2":
            plot_profit_loss(portfolio, portfolio_name)
        elif choice == "3":
            plot_daily_performance(portfolio, portfolio_name)
        elif choice == "4":
            return
        else:
            console.print("[red]Invalid choice.[/red]")

def save_portfolios(portfolios):
    with open(PORTFOLIO_FILE, "w") as file:
        json.dump({k: v.to_dict(orient="records") for k, v in portfolios.items()}, file)
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
            console.print("8. View Graphs")
            console.print("9. Export Individual Portfolio to Excel")
            console.print("10. Export All Portfolios to Excel")
            console.print("11. Exit")
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
                view_graphs(portfolios)
            elif choice == "9":
                export_individual_portfolio(portfolios)
            elif choice == "10":
                export_all_portfolios(portfolios)
            elif choice == "11":
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