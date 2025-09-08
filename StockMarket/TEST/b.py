import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime
import json
import os
import sys

# File to store portfolios data
PORTFOLIO_FILE = "portfolios.json"

# Function to fetch live stock price using Yahoo Finance
def get_live_price_yahoo(ticker):
    try:
        stock = yf.Ticker(ticker)
        live_price = stock.history(period="1d")['Close'].iloc[-1]
        return live_price
    except Exception as e:
        print(f"Error fetching price for {ticker}: {e}")
        return None

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
    total_investment = 0
    total_current_value = 0
    total_profit_loss = 0

    print("\n--- Combined Dashboard for All Portfolios ---")
    print("{:<20} {:<15} {:<15} {:<15} {:<15}".format(
        "Portfolio", "Investment", "Current Value", "Profit/Loss", "Profit/Loss %"
    ))
    print("-" * 80)

    for portfolio_name, portfolio in portfolios.items():
        portfolio = calculate_metrics(portfolio)
        portfolio_investment = portfolio['Investment Value'].sum()
        portfolio_current_value = portfolio['Current Value'].sum()
        portfolio_profit_loss = portfolio['Profit/Loss'].sum()
        portfolio_profit_loss_percent = (portfolio_profit_loss / portfolio_investment) * 100 if portfolio_investment != 0 else 0

        total_investment += portfolio_investment
        total_current_value += portfolio_current_value
        total_profit_loss += portfolio_profit_loss

        print("{:<20} ₹{:<14,.2f} ₹{:<14,.2f} ₹{:<14,.2f} {:<15.2f}%".format(
            portfolio_name, portfolio_investment, portfolio_current_value, portfolio_profit_loss, portfolio_profit_loss_percent
        ))

    if total_investment != 0:
        total_profit_loss_percent = (total_profit_loss / total_investment) * 100
    else:
        total_profit_loss_percent = 0

    print("\n--- Combined Metrics ---")
    print(f"Total Investment: ₹{total_investment:,.2f}")
    print(f"Total Current Value: ₹{total_current_value:,.2f}")
    print(f"Total Profit/Loss: ₹{total_profit_loss:,.2f} ({total_profit_loss_percent:.2f}%)")

    # Visualizations
    plot_combined_portfolio_allocation(portfolios)
    plot_combined_profit_loss(portfolios)

# Function to display individual dashboard
def display_individual_dashboard(portfolios):
    portfolio_name = select_portfolio(portfolios)
    if not portfolio_name:
        return

    portfolio = calculate_metrics(portfolios[portfolio_name])
    total_investment = portfolio['Investment Value'].sum()
    total_current_value = portfolio['Current Value'].sum()
    total_profit_loss = portfolio['Profit/Loss'].sum()
    total_profit_loss_percent = (total_profit_loss / total_investment) * 100 if total_investment != 0 else 0

    print(f"\n--- Individual Dashboard: {portfolio_name} ---")
    print(f"Total Investment: ₹{total_investment:,.2f}")
    print(f"Total Current Value: ₹{total_current_value:,.2f}")
    print(f"Total Profit/Loss: ₹{total_profit_loss:,.2f} ({total_profit_loss_percent:.2f}%)")

    print("\n--- Stock-wise Performance ---")
    print(portfolio[['Stock Name', 'Quantity', 'Purchase Price', 'Current Price', 'Investment Value', 'Current Value', 'Profit/Loss', 'Profit/Loss %']])

    # Visualizations
    plot_portfolio_allocation(portfolio, portfolio_name)
    plot_profit_loss(portfolio, portfolio_name)

# Function to plot combined portfolio allocation
def plot_combined_portfolio_allocation(portfolios):
    combined_data = pd.concat(portfolios.values())
    plt.figure(figsize=(8, 5))
    plt.pie(combined_data['Current Value'], labels=combined_data['Stock Name'], autopct='%1.1f%%', startangle=140)
    plt.title("Combined Portfolio Allocation")
    plt.show(block=False)  # Non-blocking plot
    plt.pause(1)  # Pause to display the plot

# Function to plot combined profit/loss by stock
def plot_combined_profit_loss(portfolios):
    combined_data = pd.concat(portfolios.values())
    plt.figure(figsize=(10, 6))
    plt.bar(combined_data['Stock Name'], combined_data['Profit/Loss'], color=['green' if x >= 0 else 'red' for x in combined_data['Profit/Loss']])
    plt.title("Combined Profit/Loss by Stock")
    plt.xlabel("Stock Name")
    plt.ylabel("Profit/Loss (₹)")
    plt.xticks(rotation=45)
    plt.show(block=False)  # Non-blocking plot
    plt.pause(1)  # Pause to display the plot

# Function to plot individual portfolio allocation
def plot_portfolio_allocation(portfolio, portfolio_name):
    plt.figure(figsize=(8, 5))
    plt.pie(portfolio['Current Value'], labels=portfolio['Stock Name'], autopct='%1.1f%%', startangle=140)
    plt.title(f"Portfolio Allocation: {portfolio_name}")
    plt.show(block=False)  # Non-blocking plot
    plt.pause(1)  # Pause to display the plot

# Function to plot individual profit/loss by stock
def plot_profit_loss(portfolio, portfolio_name):
    plt.figure(figsize=(10, 6))
    plt.bar(portfolio['Stock Name'], portfolio['Profit/Loss'], color=['green' if x >= 0 else 'red' for x in portfolio['Profit/Loss']])
    plt.title(f"Profit/Loss by Stock: {portfolio_name}")
    plt.xlabel("Stock Name")
    plt.ylabel("Profit/Loss (₹)")
    plt.xticks(rotation=45)
    plt.show(block=False)  # Non-blocking plot
    plt.pause(1)  # Pause to display the plot

# Function to add a stock to a portfolio
def add_stock(portfolios):
    portfolio_name = input("Enter portfolio name: ")
    stock_name = input("Enter stock name: ")
    ticker_symbol = input("Enter ticker symbol (e.g., RELIANCE.NS): ")
    quantity = int(input("Enter quantity: "))
    purchase_price = float(input("Enter purchase price: "))
    purchase_date = input("Enter purchase date (DD-MM-YYYY): ")
    sector = input("Enter sector: ")

    # Convert date format from DD-MM-YYYY to YYYY-MM-DD for internal storage
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

    print(f"Stock '{stock_name}' added to portfolio '{portfolio_name}'.")

# Function to manage shares (add/remove)
def manage_shares(portfolios):
    portfolio_name = select_portfolio(portfolios)
    if not portfolio_name:
        return

    stock_name = input("Enter stock name: ")
    portfolio = portfolios[portfolio_name]
    stock_index = portfolio.index[portfolio['Stock Name'] == stock_name].tolist()

    if not stock_index:
        print(f"Stock '{stock_name}' not found in portfolio '{portfolio_name}'.")
        return

    print("\n1. Add Shares")
    print("2. Remove Shares")
    choice = input("Enter your choice: ")

    if choice == "1":
        quantity_to_add = int(input("Enter quantity to add: "))
        portfolio.at[stock_index[0], 'Quantity'] += quantity_to_add
        portfolio.at[stock_index[0], 'Investment Value'] = portfolio.at[stock_index[0], 'Quantity'] * portfolio.at[stock_index[0], 'Purchase Price']
        print(f"Added {quantity_to_add} shares to '{stock_name}' in portfolio '{portfolio_name}'.")
    elif choice == "2":
        quantity_to_remove = int(input("Enter quantity to remove: "))
        if quantity_to_remove > portfolio.at[stock_index[0], 'Quantity']:
            print("Cannot remove more shares than available.")
            return
        portfolio.at[stock_index[0], 'Quantity'] -= quantity_to_remove
        portfolio.at[stock_index[0], 'Investment Value'] = portfolio.at[stock_index[0], 'Quantity'] * portfolio.at[stock_index[0], 'Purchase Price']
        print(f"Removed {quantity_to_remove} shares from '{stock_name}' in portfolio '{portfolio_name}'.")
    else:
        print("Invalid choice.")

# Function to delete a portfolio
def delete_portfolio(portfolios):
    portfolio_name = select_portfolio(portfolios)
    if not portfolio_name:
        return

    confirm = input(f"Are you sure you want to delete portfolio '{portfolio_name}'? (y/n): ")
    if confirm.lower() == 'y':
        del portfolios[portfolio_name]
        print(f"Portfolio '{portfolio_name}' deleted.")

# Function to modify stock details
def modify_stock(portfolios):
    portfolio_name = select_portfolio(portfolios)
    if not portfolio_name:
        return

    stock_name = input("Enter stock name: ")
    portfolio = portfolios[portfolio_name]
    stock_index = portfolio.index[portfolio['Stock Name'] == stock_name].tolist()

    if not stock_index:
        print(f"Stock '{stock_name}' not found in portfolio '{portfolio_name}'.")
        return

    print("\nSelect field to modify:")
    print("1. Stock Name")
    print("2. Ticker Symbol")
    print("3. Quantity")
    print("4. Purchase Price")
    print("5. Purchase Date")
    print("6. Sector")
    choice = input("Enter your choice: ")

    if choice == "1":
        new_name = input("Enter new stock name: ")
        portfolio.at[stock_index[0], 'Stock Name'] = new_name
    elif choice == "2":
        new_ticker = input("Enter new ticker symbol: ")
        portfolio.at[stock_index[0], 'Ticker Symbol'] = new_ticker
    elif choice == "3":
        new_quantity = int(input("Enter new quantity: "))
        portfolio.at[stock_index[0], 'Quantity'] = new_quantity
        portfolio.at[stock_index[0], 'Investment Value'] = new_quantity * portfolio.at[stock_index[0], 'Purchase Price']
    elif choice == "4":
        new_price = float(input("Enter new purchase price: "))
        portfolio.at[stock_index[0], 'Purchase Price'] = new_price
        portfolio.at[stock_index[0], 'Investment Value'] = portfolio.at[stock_index[0], 'Quantity'] * new_price
    elif choice == "5":
        new_date = input("Enter new purchase date (DD-MM-YYYY): ")
        new_date = datetime.strptime(new_date, "%d-%m-%Y").strftime("%Y-%m-%d")
        portfolio.at[stock_index[0], 'Purchase Date'] = new_date
    elif choice == "6":
        new_sector = input("Enter new sector: ")
        portfolio.at[stock_index[0], 'Sector'] = new_sector
    else:
        print("Invalid choice.")

    print(f"Stock '{stock_name}' in portfolio '{portfolio_name}' updated.")

# Function to view all portfolios
def view_all_portfolios(portfolios):
    if not portfolios:
        print("No portfolios found.")
        return

    print("\n--- All Portfolios ---")
    for portfolio_name in portfolios:
        print(f"- {portfolio_name}")

# Function to select a portfolio
def select_portfolio(portfolios):
    view_all_portfolios(portfolios)
    portfolio_name = input("Enter portfolio name to select: ")
    if portfolio_name in portfolios:
        return portfolio_name
    else:
        print(f"Portfolio '{portfolio_name}' not found.")
        return None

# Function to export portfolio to Excel
def export_to_excel(portfolios):
    with pd.ExcelWriter("portfolios_summary.xlsx") as writer:
        for portfolio_name, portfolio in portfolios.items():
            portfolio.to_excel(writer, sheet_name=portfolio_name, index=False)
    print("Portfolios exported to 'portfolios_summary.xlsx'.")

# Function to save portfolios to a file
def save_portfolios(portfolios):
    with open(PORTFOLIO_FILE, "w") as file:
        json.dump({k: v.to_dict(orient="records") for k, v in portfolios.items()}, file)
    print("Portfolios saved to file.")

# Function to load portfolios from a file
def load_portfolios():
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, "r") as file:
            data = json.load(file)
            return {k: pd.DataFrame(v) for k, v in data.items()}
    return {}

# Main function
def main():
    portfolios = load_portfolios()  # Load portfolios from file

    try:
        while True:
            print("\n--- Stock Portfolio Tracker ---")
            print("1. Add Stock to Portfolio")
            print("2. Manage Shares (Add/Remove)")
            print("3. Modify Stock Details")
            print("4. Delete Portfolio")
            print("5. View Combined Dashboard")
            print("6. View Individual Dashboard")
            print("7. Export to Excel")
            print("8. Exit")
            choice = input("Enter your choice: ")

            if choice == "1":
                add_stock(portfolios)
            elif choice == "2":
                manage_shares(portfolios)
            elif choice == "3":
                modify_stock(portfolios)
            elif choice == "4":
                delete_portfolio(portfolios)
            elif choice == "5":
                display_combined_dashboard(portfolios)
            elif choice == "6":
                display_individual_dashboard(portfolios)
            elif choice == "7":
                export_to_excel(portfolios)
            elif choice == "8":
                save_portfolios(portfolios)  # Save portfolios before exiting
                print("Exiting...")
                break
            else:
                print("Invalid choice. Please try again.")
    except KeyboardInterrupt:
        save_portfolios(portfolios)  # Save portfolios on keyboard interrupt
        print("\nPortfolios saved. Exiting...")
        sys.exit(0)

if __name__ == "__main__":
    main()