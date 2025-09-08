import json
from datetime import datetime, timedelta
import math

def parse_date(date_str):
    """Parse date string in either YYYY-MM-DD or DD-MM-YYYY format"""
    try:
        # Try YYYY-MM-DD format first
        return datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        try:
            # Try DD-MM-YYYY format
            return datetime.strptime(date_str, '%d-%m-%Y')
        except ValueError:
            # If both fail, return current date
            print(f"Warning: Invalid date format '{date_str}', using current date")
            return datetime.now()

def clean_portfolio_data():
    # Read the current portfolio data
    with open('Portfolios.json', 'r') as f:
        portfolios = json.load(f)
    
    # Get current date
    current_date = datetime.now()
    
    # Clean each portfolio
    for portfolio_name, holdings in portfolios.items():
        for holding in holdings:
            # Fix future dates
            purchase_date = parse_date(holding['Purchase Date'])
            if purchase_date > current_date:
                # Set to 30 days ago if future date
                holding['Purchase Date'] = (current_date - timedelta(days=30)).strftime('%Y-%m-%d')
            else:
                # Standardize date format to YYYY-MM-DD
                holding['Purchase Date'] = purchase_date.strftime('%Y-%m-%d')
            
            # Standardize number formats
            holding['Purchase Price'] = round(float(holding['Purchase Price']), 2)
            holding['Investment Value'] = round(float(holding['Investment Value']), 2)
            
            # Clean NaN and recalculate
            for key in ['Current Price', 'Current Value', 'Profit/Loss', 'Profit/Loss %', 'Daily Return %', 'Daily P/L']:
                val = holding.get(key)
                if val is None or (isinstance(val, str) and val.lower() == 'nan') or (isinstance(val, float) and math.isnan(val)):
                    holding[key] = None
            
            # Recalculate if needed
            if holding['Current Price'] is None:
                holding['Current Price'] = holding['Purchase Price']
            if holding['Current Value'] is None:
                holding['Current Value'] = round(holding['Current Price'] * holding['Quantity'], 2)
            if holding['Profit/Loss'] is None:
                holding['Profit/Loss'] = round(holding['Current Value'] - holding['Investment Value'], 2)
            if holding['Profit/Loss %'] is None:
                if holding['Investment Value'] > 0:
                    holding['Profit/Loss %'] = round((holding['Profit/Loss'] / holding['Investment Value']) * 100, 2)
                else:
                    holding['Profit/Loss %'] = 0.0
            if holding['Daily Return %'] is None:
                holding['Daily Return %'] = 0.0
            if holding['Daily P/L'] is None:
                holding['Daily P/L'] = 0.0
            
            # Add delay to avoid rate limiting
            time.sleep(1)
    
    # Save the cleaned data
    with open('Portfolios.json', 'w') as f:
        json.dump(portfolios, f, indent=4)
    
    print("Portfolio data cleaned successfully!")

if __name__ == "__main__":
    clean_portfolio_data() 