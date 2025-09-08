import pandas as pd
import yfinance as yf
from datetime import datetime
import json
import os
import sys
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
            font=dict(color="white"),
            title=dict(x=0.5),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=False)
        )
    )
    pio.templates.default = "custom"

apply_custom_theme()

# Function to normalize portfolio name (convert to lowercase)
def normalize_portfolio_name(name):
    return name.strip().lower()

# Function to fetch live stock price using Yahoo Finance
def get_live_price_yahoo(ticker):
    try:
        stock = yf.Ticker(ticker)
        live_price = stock.history(period="1d")['Close'].iloc[-1]
        return live_price
    except Exception as e:
        console.print(f"[red]Error fetching price for {ticker}: {e}[/red]")
        return None

# Function to validate date format
def validate_date(date_str):
    try:
        datetime.strptime(date_str, "%d-%m-%Y")
        return True
    except ValueError:
        return False

# Function to validate ticker symbol
def validate_ticker(ticker):
    try:
        stock = yf.Ticker(ticker)
        stock.info  # Check if the ticker is valid
        return True
    except:
        return False

# Function to calculate portfolio metrics
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

# Function to display combined dashboard
def display_combined_dashboard(portfolios):
    if not portfolios:
        console.print("[yellow]No portfolios found. Please create a portfolio first.[/yellow]")
        return

    total_investment = 0
    total_current_value = 0
    total_profit_loss = 0

    table = Table(title="Combined Dashboard for All Portfolios")
    table.add_column("Portfolio", justify="left", style="cyan", no_wrap=True)
    table.add_column("Invested", justify="right", style="green")
    table.add_column("Current", justify="right", style="green")
    table.add_column("Profit/Loss", justify="right", style="magenta")
    table.add_column("Profit/Loss %", justify="right", style="magenta")

    for portfolio_name, portfolio in track(portfolios.items(), description="Processing portfolios..."):
        if portfolio.empty:
            console.print(f"[yellow]Portfolio '{portfolio_name}' is empty.[/yellow]")
            continue

        portfolio = calculate_metrics(portfolio)
        portfolio_investment = portfolio['Investment Value'].sum()
        portfolio_current_value = portfolio['Current Value'].sum()
        portfolio_profit_loss = portfolio['Profit/Loss'].sum()
        portfolio_profit_loss_percent = (portfolio_profit_loss / portfolio_investment) * 100 if portfolio_investment != 0 else 0

        total_investment += portfolio_investment
        total_current_value += portfolio_current_value
        total_profit_loss += portfolio_profit_loss

        profit_loss_color = "green" if portfolio_profit_loss >= 0 else "red"
        table.add_row(
            portfolio_name,
            f"₹{portfolio_investment:,.2f}",
            f"₹{portfolio_current_value:,.2f}",
            f"[{profit_loss_color}]₹{portfolio_profit_loss:,.2f}[/]",
            f"[{profit_loss_color}]{portfolio_profit_loss_percent:.2f}%[/]"
        )

    if total_investment == 0:
        console.print("[yellow]No stocks found in any portfolio.[/yellow]")
        return

    console.print(table)

    total_profit_loss_percent = (total_profit_loss / total_investment) * 100 if total_investment != 0 else 0
    total_profit_loss_color = "green" if total_profit_loss >= 0 else "red"

    console.print("\n[bold]--- Combined Metrics ---[/bold]")
    console.print(f"Total Invested: [green]₹{total_investment:,.2f}[/green]")
    console.print(f"Total Current Value: [green]₹{total_current_value:,.2f}[/green]")
    console.print(f"Total Profit/Loss: [{total_profit_loss_color}]₹{total_profit_loss:,.2f} ({total_profit_loss_percent:.2f}%)[/]")

    plot_combined_portfolio_allocation(portfolios)
    plot_combined_profit_loss(portfolios)

# Function to display individual dashboard
def display_individual_dashboard(portfolios, portfolio_name):
    if portfolio_name not in portfolios:
        console.print(f"[red]Portfolio '{portfolio_name}' not found.[/red]")
        return

    portfolio = portfolios[portfolio_name]
    if portfolio.empty:
        console.print(f"[yellow]Portfolio '{portfolio_name}' is empty. No stocks to display.[/yellow]")
        return

    portfolio = calculate_metrics(portfolio)
    total_investment = portfolio['Investment Value'].sum()
    total_current_value = portfolio['Current Value'].sum()
    total_profit_loss = portfolio['Profit/Loss'].sum()
    total_profit_loss_percent = (total_profit_loss / total_investment) * 100 if total_investment != 0 else 0

    profit_loss_color = "green" if total_profit_loss >= 0 else "red"

    console.print(f"\n[bold]--- Individual Dashboard: {portfolio_name} ---[/bold]")
    console.print(f"Total Invested: [green]₹{total_investment:,.2f}[/green]")
    console.print(f"Total Current Value: [green]₹{total_current_value:,.2f}[/green]")
    console.print(f"Total Profit/Loss: [{profit_loss_color}]₹{total_profit_loss:,.2f} ({total_profit_loss_percent:.2f}%)[/]")

    # Display stock-wise performance in a table
    stock_table = Table(title=f"Stock-wise Performance: {portfolio_name}")
    stock_table.add_column("Stock Name", justify="left", style="cyan", no_wrap=True)
    stock_table.add_column("Quantity", justify="right", style="green")
    stock_table.add_column("Purchase Price", justify="right", style="green")
    stock_table.add_column("Current Price", justify="right", style="green")
    stock_table.add_column("Investment Value", justify="right", style="green")
    stock_table.add_column("Current Value", justify="right", style="green")
    stock_table.add_column("Profit/Loss", justify="right", style="magenta")
    stock_table.add_column("Profit/Loss %", justify="right", style="magenta")

    for index, row in portfolio.iterrows():
        color = "green" if row['Profit/Loss'] >= 0 else "red"
        stock_table.add_row(
            row['Stock Name'],
            str(row['Quantity']),
            f"₹{row['Purchase Price']:.2f}",
            f"₹{row['Current Price']:.2f}",
            f"₹{row['Investment Value']:.2f}",
            f"₹{row['Current Value']:.2f}",
            f"[{color}]₹{row['Profit/Loss']:.2f}[/]",
            f"[{color}]{row['Profit/Loss %']:.2f}%[/]"
        )

    console.print(stock_table)

    plot_portfolio_allocation(portfolio, portfolio_name)
    plot_profit_loss(portfolio, portfolio_name)

# Function to plot combined portfolio allocation
def plot_combined_portfolio_allocation(portfolios):
    combined_data = pd.concat(portfolios.values())
    if combined_data.empty:
        console.print("[yellow]No stocks found to plot allocation.[/yellow]")
        return

    fig = px.pie(combined_data, values='Current Value', names='Stock Name', title="Combined Portfolio Allocation")
    fig.show()

# Function to plot combined profit/loss by stock
def plot_combined_profit_loss(portfolios):
    combined_data = pd.concat(portfolios.values())
    if combined_data.empty:
        console.print("[yellow]No stocks found to plot profit/loss.[/yellow]")
        return

    fig = px.bar(combined_data, x='Stock Name', y='Profit/Loss', color='Profit/Loss',
                 color_continuous_scale=['red', 'green'], title="Combined Profit/Loss by Stock")
    fig.show()

# Function to plot individual portfolio allocation
def plot_portfolio_allocation(portfolio, portfolio_name):
    if portfolio.empty:
        console.print(f"[yellow]Portfolio '{portfolio_name}' is empty. No allocation to plot.[/yellow]")
        return

    fig = px.pie(portfolio, values='Current Value', names='Stock Name', title=f"Portfolio Allocation: {portfolio_name}")
    fig.show()

# Function to plot individual profit/loss by stock
def plot_profit_loss(portfolio, portfolio_name):
    if portfolio.empty:
        console.print(f"[yellow]Portfolio '{portfolio_name}' is empty. No profit/loss to plot.[/yellow]")
        return

    fig = px.bar(portfolio, x='Stock Name', y='Profit/Loss', color='Profit/Loss',
                 color_continuous_scale=['red', 'green'], title=f"Profit/Loss by Stock: {portfolio_name}")
    fig.show()

# Function to create a new portfolio
def create_portfolio(portfolios):
    portfolio_name = input("Enter a name for the new portfolio: ")
    normalized_portfolio_name = normalize_portfolio_name(portfolio_name)

    # Check if portfolio already exists (case-insensitive)
    existing_portfolio_name = next((name for name in portfolios.keys() if normalize_portfolio_name(name) == normalized_portfolio_name), None)
    if existing_portfolio_name:
        console.print(f"[red]Portfolio '{existing_portfolio_name}' already exists.[/red]")
    else:
        portfolios[portfolio_name] = pd.DataFrame(columns=[
            'Portfolio Name', 'Stock Name', 'Ticker Symbol', 'Quantity', 'Purchase Price',
            'Purchase Date', 'Sector', 'Investment Value', 'Current Price', 'Current Value',
            'Profit/Loss', 'Profit/Loss %'
        ])
        console.print(f"[green]Portfolio '{portfolio_name}' created successfully.[/green]")

# Function to add a stock to a portfolio
def add_stock(portfolios):
    if not portfolios:
        console.print("[red]No portfolios found. Please create a portfolio first.[/red]")
        return

    # Display existing portfolios with numbers
    console.print("\n[bold]--- Select a Portfolio ---[/bold]")
    portfolio_names = list(portfolios.keys())
    for i, name in enumerate(portfolio_names, start=1):
        console.print(f"{i}. {name}")

    # Ask user to select a portfolio
    while True:
        try:
            choice = int(input("Enter the number corresponding to the portfolio: "))
            if 1 <= choice <= len(portfolio_names):
                portfolio_name = portfolio_names[choice - 1]
                break
            else:
                console.print("[red]Invalid choice. Please enter a valid number.[/red]")
        except ValueError:
            console.print("[red]Invalid input. Please enter a number.[/red]")

    stock_name = input("Enter stock name: ")

    while True:
        ticker_symbol = input("Enter ticker symbol (e.g., RELIANCE.NS): ")
        if validate_ticker(ticker_symbol):
            break
        else:
            console.print("[red]Invalid ticker symbol. Please try again.[/red]")

    # Check if the portfolio is empty or if the ticker symbol already exists
    if portfolio_name in portfolios:
        if not portfolios[portfolio_name].empty and ticker_symbol in portfolios[portfolio_name]['Ticker Symbol'].values:
            console.print(f"[red]Stock with ticker symbol '{ticker_symbol}' already exists in portfolio '{portfolio_name}'.[/red]")
            return

    while True:
        quantity = input("Enter quantity: ")
        if quantity.isdigit() and int(quantity) > 0:
            quantity = int(quantity)
            break
        else:
            console.print("[red]Invalid quantity. Please enter a positive integer.[/red]")

    while True:
        purchase_price = input("Enter purchase price: ")
        try:
            purchase_price = float(purchase_price)
            if purchase_price > 0:
                break
            else:
                console.print("[red]Invalid purchase price. Please enter a positive number.[/red]")
        except ValueError:
            console.print("[red]Invalid purchase price. Please enter a valid number.[/red]")

    while True:
        purchase_date = input("Enter purchase date (DD-MM-YYYY): ")
        if validate_date(purchase_date):
            break
        else:
            console.print("[red]Invalid date format. Please enter the date in DD-MM-YYYY format.[/red]")

    sector = input("Enter sector: ")
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
        'Profit/Loss %': 0.0
    }

    if portfolio_name in portfolios:
        portfolios[portfolio_name] = pd.concat([portfolios[portfolio_name], pd.DataFrame([new_stock])], ignore_index=True)
    else:
        portfolios[portfolio_name] = pd.DataFrame([new_stock])

    console.print(f"[green]Stock '{stock_name}' added to portfolio '{portfolio_name}'.[/green]")

# Function to manage shares (add/remove)
def manage_shares(portfolios):
    portfolio_name = select_portfolio(portfolios)
    if not portfolio_name:
        return

    stock_name = input("Enter stock name: ")
    portfolio = portfolios[portfolio_name]
    stock_index = portfolio.index[portfolio['Stock Name'] == stock_name].tolist()

    if not stock_index:
        console.print(f"[red]Stock '{stock_name}' not found in portfolio '{portfolio_name}'.[/red]")
        return

    console.print("\n1. Add Shares")
    console.print("2. Remove Shares")
    choice = input("Enter your choice: ")

    if choice == "1":
        while True:
            quantity_to_add = input("Enter quantity to add: ")
            if quantity_to_add.isdigit() and int(quantity_to_add) > 0:
                quantity_to_add = int(quantity_to_add)
                break
            else:
                console.print("[red]Invalid quantity. Please enter a positive integer.[/red]")
        portfolio.at[stock_index[0], 'Quantity'] += quantity_to_add
        portfolio.at[stock_index[0], 'Investment Value'] = portfolio.at[stock_index[0], 'Quantity'] * portfolio.at[stock_index[0], 'Purchase Price']
        console.print(f"[green]Added {quantity_to_add} shares to '{stock_name}' in portfolio '{portfolio_name}'.[/green]")
    elif choice == "2":
        while True:
            quantity_to_remove = input("Enter quantity to remove: ")
            if quantity_to_remove.isdigit() and int(quantity_to_remove) > 0:
                quantity_to_remove = int(quantity_to_remove)
                break
            else:
                console.print("[red]Invalid quantity. Please enter a positive integer.[/red]")
        if quantity_to_remove > portfolio.at[stock_index[0], 'Quantity']:
            console.print("[red]Cannot remove more shares than available.[/red]")
            return
        portfolio.at[stock_index[0], 'Quantity'] -= quantity_to_remove
        portfolio.at[stock_index[0], 'Investment Value'] = portfolio.at[stock_index[0], 'Quantity'] * portfolio.at[stock_index[0], 'Purchase Price']
        console.print(f"[green]Removed {quantity_to_remove} shares from '{stock_name}' in portfolio '{portfolio_name}'.[/green]")
    else:
        console.print("[red]Invalid choice.[/red]")

# Function to delete a portfolio
def delete_portfolio(portfolios):
    portfolio_name = select_portfolio(portfolios)
    if not portfolio_name:
        return

    confirm = input(f"Are you sure you want to delete portfolio '{portfolio_name}'? (y/n): ")
    if confirm.lower() == 'y':
        del portfolios[portfolio_name]
        console.print(f"[green]Portfolio '{portfolio_name}' deleted.[/green]")

# Function to modify stock details
def modify_stock(portfolios):
    portfolio_name = select_portfolio(portfolios)
    if not portfolio_name:
        return

    stock_name = input("Enter stock name: ")
    portfolio = portfolios[portfolio_name]
    stock_index = portfolio.index[portfolio['Stock Name'] == stock_name].tolist()

    if not stock_index:
        console.print(f"[red]Stock '{stock_name}' not found in portfolio '{portfolio_name}'.[/red]")
        return

    console.print("\nSelect field to modify:")
    console.print("1. Stock Name")
    console.print("2. Ticker Symbol")
    console.print("3. Quantity")
    console.print("4. Purchase Price")
    console.print("5. Purchase Date")
    console.print("6. Sector")
    choice = input("Enter your choice: ")

    if choice == "1":
        new_name = input("Enter new stock name: ")
        portfolio.at[stock_index[0], 'Stock Name'] = new_name
    elif choice == "2":
        while True:
            new_ticker = input("Enter new ticker symbol: ")
            if validate_ticker(new_ticker):
                break
            else:
                console.print("[red]Invalid ticker symbol. Please try again.[/red]")
        portfolio.at[stock_index[0], 'Ticker Symbol'] = new_ticker
    elif choice == "3":
        while True:
            new_quantity = input("Enter new quantity: ")
            if new_quantity.isdigit() and int(new_quantity) > 0:
                new_quantity = int(new_quantity)
                break
            else:
                console.print("[red]Invalid quantity. Please enter a positive integer.[/red]")
        portfolio.at[stock_index[0], 'Quantity'] = new_quantity
        portfolio.at[stock_index[0], 'Investment Value'] = new_quantity * portfolio.at[stock_index[0], 'Purchase Price']
    elif choice == "4":
        while True:
            new_price = input("Enter new purchase price: ")
            try:
                new_price = float(new_price)
                if new_price > 0:
                    break
                else:
                    console.print("[red]Invalid purchase price. Please enter a positive number.[/red]")
            except ValueError:
                console.print("[red]Invalid purchase price. Please enter a valid number.[/red]")
        portfolio.at[stock_index[0], 'Purchase Price'] = new_price
        portfolio.at[stock_index[0], 'Investment Value'] = portfolio.at[stock_index[0], 'Quantity'] * new_price
    elif choice == "5":
        while True:
            new_date = input("Enter new purchase date (DD-MM-YYYY): ")
            if validate_date(new_date):
                break
            else:
                console.print("[red]Invalid date format. Please enter the date in DD-MM-YYYY format.[/red]")
        new_date = datetime.strptime(new_date, "%d-%m-%Y").strftime("%Y-%m-%d")
        portfolio.at[stock_index[0], 'Purchase Date'] = new_date
    elif choice == "6":
        new_sector = input("Enter new sector: ")
        portfolio.at[stock_index[0], 'Sector'] = new_sector
    else:
        console.print("[red]Invalid choice.[/red]")

    console.print(f"[green]Stock '{stock_name}' in portfolio '{portfolio_name}' updated.[/green]")

# Function to view all portfolios
def view_all_portfolios(portfolios):
    if not portfolios:
        console.print("[red]No portfolios found.[/red]")
        return

    console.print("\n[bold]--- All Portfolios ---[/bold]")
    for portfolio_name in portfolios:
        console.print(f"- {portfolio_name}")

# Function to select a portfolio
def select_portfolio(portfolios):
    view_all_portfolios(portfolios)
    portfolio_name = input("Enter portfolio name to select: ")
    normalized_portfolio_name = normalize_portfolio_name(portfolio_name)

    # Find the portfolio name (case-insensitive)
    existing_portfolio_name = next((name for name in portfolios.keys() if normalize_portfolio_name(name) == normalized_portfolio_name), None)
    if existing_portfolio_name:
        return existing_portfolio_name
    else:
        console.print(f"[red]Portfolio '{portfolio_name}' not found.[/red]")
        return None

# Function to export individual portfolio to Excel
def export_individual_portfolio(portfolios):
    portfolio_name = select_portfolio(portfolios)
    if not portfolio_name:
        return

    portfolio = portfolios[portfolio_name]
    file_name = f"{portfolio_name}_portfolio.xlsx"
    portfolio.to_excel(file_name, index=False)
    console.print(f"[green]Portfolio '{portfolio_name}' exported to '{file_name}'.[/green]")

# Function to export all portfolios to Excel
def export_all_portfolios(portfolios):
    with pd.ExcelWriter("all_portfolios.xlsx") as writer:
        for portfolio_name, portfolio in portfolios.items():
            portfolio.to_excel(writer, sheet_name=portfolio_name, index=False)
    console.print("[green]All portfolios exported to 'all_portfolios.xlsx'.[/green]")

# Function to save portfolios to a file
def save_portfolios(portfolios):
    with open(PORTFOLIO_FILE, "w") as file:
        json.dump({k: v.to_dict(orient="records") for k, v in portfolios.items()}, file)
    console.print("[green]Portfolios saved to file.[/green]")

# Function to load portfolios from a file
def load_portfolios():
    if os.path.exists(PORTFOLIO_FILE):
        # Check if the file is empty
        if os.path.getsize(PORTFOLIO_FILE) == 0:
            console.print("[yellow]Portfolios file is empty. Initializing empty portfolios.[/yellow]")
            return {}
        
        # Load portfolios from file
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

# Main function
def main():
    portfolios = load_portfolios()  # Load portfolios from file

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
            choice = input("Enter your choice: ")

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
                display_combined_dashboard(portfolios)
            elif choice == "7":
                portfolio_name = select_portfolio(portfolios)
                if portfolio_name:
                    display_individual_dashboard(portfolios, portfolio_name)
            elif choice == "8":
                export_individual_portfolio(portfolios)
            elif choice == "9":
                export_all_portfolios(portfolios)
            elif choice == "10":
                save_portfolios(portfolios)  # Save portfolios before exiting
                console.print("[bold green]Exiting...[/bold green]")
                break
            else:
                console.print("[bold red]Invalid choice. Please try again.[/bold red]")
    except KeyboardInterrupt:
        save_portfolios(portfolios)  # Save portfolios on keyboard interrupt
        console.print("\n[bold green]Portfolios saved. Exiting...[/bold green]")
        sys.exit(0)

if __name__ == "__main__":
    main()