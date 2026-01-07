import os
import requests
from woocommerce import API
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

WC_API_URL = os.getenv("WC_API_URL")
WC_CONSUMER_KEY = os.getenv("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = os.getenv("WC_CONSUMER_SECRET")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
DAYS_RANGE = int(os.getenv("DAYS_RANGE", "30"))  # Default to 30 days


def get_woocommerce_data():
    """Fetch data from WooCommerce API using official library."""
    
    # Initialize WooCommerce API
    # Remove trailing slash from URL if present
    api_url = WC_API_URL.rstrip('/')
    
    wcapi = API(
        url=api_url,
        consumer_key=WC_CONSUMER_KEY,
        consumer_secret=WC_CONSUMER_SECRET,
        version="wc/v3",
        timeout=30,
        wp_api=True,  # Use WordPress API path
        query_string_auth=True  # Force query string auth for HTTPS
    )
    
    try:
        # Get orders from configured date range
        days_ago = (datetime.now() - timedelta(days=DAYS_RANGE)).isoformat()
        
        # Fetch all orders (paginated)
        all_orders = []
        page = 1
        per_page = 100
        
        print(f"Fetching orders from last {DAYS_RANGE} days (after {days_ago})...")
        
        while True:
            print(f"Fetching page {page}...")
            response = wcapi.get("orders", params={
                "per_page": per_page,
                "page": page,
                "after": days_ago
            })
            
            if response.status_code != 200:
                print(f"Error fetching orders: {response.status_code}")
                print(f"Response: {response.json()}")
                break
            
            orders = response.json()
            if not orders:
                print(f"No more orders found. Total fetched: {len(all_orders)}")
                break
                
            all_orders.extend(orders)
            print(f"Fetched {len(orders)} orders (total so far: {len(all_orders)})")
            page += 1
            
            # Increased safety limit - adjust if you have even more orders
            if page > 100:  # Now allows up to 10,000 orders
                print(f"WARNING: Reached safety limit of 100 pages. Total orders: {len(all_orders)}")
                break
        
        # Calculate metrics
        total_sales = sum(float(order.get("total", 0)) for order in all_orders)
        total_orders = len(all_orders)
        
        # Count order statuses
        pending_orders = sum(1 for order in all_orders if order.get("status") == "pending")
        processing_orders = sum(1 for order in all_orders if order.get("status") == "processing")
        completed_orders = sum(1 for order in all_orders if order.get("status") == "completed")
        fulfilled_orders = completed_orders  # Completed = Fulfilled
        
        # Calculate products sold
        products_sold = 0
        for order in all_orders:
            for item in order.get("line_items", []):
                products_sold += item.get("quantity", 0)
        
        # Get low stock products
        print("Fetching product inventory data...")
        
        # Fetch all products with stock management enabled
        all_products = []
        page = 1
        
        while True:
            products_response = wcapi.get("products", params={
                "per_page": 100,
                "page": page,
                "stock_status": "instock",
                "manage_stock": True  # Only products with stock management
            })
            
            if products_response.status_code != 200:
                print(f"Error fetching products: {products_response.status_code}")
                break
            
            products = products_response.json()
            if not products:
                break
                
            all_products.extend(products)
            page += 1
            
            # Limit to 5 pages (500 products) for performance
            if page > 5:
                break
        
        print(f"Found {len(all_products)} products with stock management")
        
        # Filter and sort products by stock quantity
        low_stock_products = []
        for product in all_products:
            stock_qty = product.get("stock_quantity")
            # Include products with stock quantity (not None) that are low
            if stock_qty is not None and isinstance(stock_qty, (int, float)):
                low_stock_threshold = product.get("low_stock_amount")
                # If no threshold set, use default of 5
                if low_stock_threshold is None:
                    low_stock_threshold = 5
                
                if stock_qty <= low_stock_threshold and stock_qty >= 0:
                    low_stock_products.append({
                        "name": product.get("name", "Unknown"),
                        "stock": int(stock_qty),
                        "threshold": int(low_stock_threshold)
                    })
        
        # Sort by stock quantity (lowest first)
        low_stock_products.sort(key=lambda x: x["stock"])
        
        print(f"Found {len(low_stock_products)} low stock items")
        
        # Prepare data for TRMNL
        data = {
            "merge_variables": {
                "total_sales": f"${total_sales:,.2f}",
                "total_orders": total_orders,
                "products_sold": products_sold,
                "pending_orders": pending_orders,
                "processing_orders": processing_orders,
                "fulfilled_orders": fulfilled_orders,
                "low_stock_count": len(low_stock_products),
                "low_stock_items": low_stock_products[:5],  # Top 5 for display
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
        }
        
        return data
        
    except Exception as e:
        print(f"Error fetching WooCommerce data: {str(e)}")
        return None


def send_to_trmnl(data):
    """Send data to TRMNL webhook."""
    
    if DEBUG:
        print("DEBUG MODE: Would send to TRMNL:")
        print(data)
        return True
    
    try:
        response = requests.post(
            WEBHOOK_URL,
            json=data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            print("Successfully sent data to TRMNL")
            return True
        else:
            print(f"Error sending to TRMNL: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"Error sending to TRMNL: {str(e)}")
        return False


def main():
    """Main function to run the plugin."""
    
    print("Fetching WooCommerce data...")
    data = get_woocommerce_data()
    
    if data:
        print("Sending data to TRMNL...")
        send_to_trmnl(data)
    else:
        print("Failed to fetch WooCommerce data")


if __name__ == "__main__":
    main()
