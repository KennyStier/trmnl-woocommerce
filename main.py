#!/usr/bin/env python3

import requests
import json
from dotenv import load_dotenv
from datetime import datetime
import os

load_dotenv()

# WooCommerce API-Konfiguration
WC_API_URL = os.getenv("WC_API_URL")
WC_CONSUMER_KEY = os.getenv("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = os.getenv("WC_CONSUMER_SECRET")

# Webhook URL
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

DEBUG = os.getenv("DEBUG") == "True"

# Währungssymbol-Mapping
CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "AUD": "A$",
    "CAD": "C$",
    "CHF": "CHF",
    "CNY": "¥",
    "SEK": "kr",
    "NZD": "NZ$",
}


# Funktion zur Paginierung
def fetch_all_pages(url, auth):
    results = []
    page = 1

    while True:
        response = requests.get(url, auth=auth, params={"per_page": 100, "page": page})
        response.raise_for_status()
        data = response.json()

        if not data:  # Keine weiteren Seiten
            break

        results.extend(data)
        page += 1

    return results


# Funktion, um WooCommerce-Daten zu holen
def get_woocommerce_data():
    try:
        # API-Endpunkte
        orders_url = f"{WC_API_URL}/orders"
        products_url = f"{WC_API_URL}/products"
        settings_url = f"{WC_API_URL}/settings/general"

        # Authentifizierung
        auth = (WC_CONSUMER_KEY, WC_CONSUMER_SECRET)

        # Alle Bestellungen abrufen
        orders = fetch_all_pages(orders_url, auth)

        # Shop-Einstellungen abrufen (für die Währung)
        settings_response = requests.get(settings_url, auth=auth)
        settings_response.raise_for_status()
        settings = settings_response.json()

        # Währung ermitteln und das entsprechende Symbol nutzen
        store_currency = next((setting["value"] for setting in settings if setting["id"] == "woocommerce_currency"),
                              "USD")
        currency_symbol = CURRENCY_SYMBOLS.get(store_currency, store_currency)

        # Produkte abrufen und Lagerbestand analysieren
        products = fetch_all_pages(products_url, auth)

        # Nur aktive Produkte berücksichtigen
        active_products = [product for product in products if product["status"] == "publish"]

        stock_overview = []

        # Produktinformationen und Lagerstatus extrahieren
        for product in active_products:
            if product["type"] == "simple":
                # Für einfache Produkte
                stock_overview.append({
                    "name": product["name"],
                    "instock": "✓" if product["stock_status"] == "instock" else "X",
                    "stock": product["stock_quantity"] if product["stock_quantity"] is not None else 0
                })

            elif product["type"] == "variable":
                # Für variable Produkte: Gesamtanzahl der Varianten ermitteln
                variants_url = f"{WC_API_URL}/products/{product['id']}/variations"
                variants = fetch_all_pages(variants_url, auth)

                total_variant_stock = sum(
                    variant["stock_quantity"] for variant in variants if variant["stock_quantity"] is not None)
                in_stock = any(variant["stock_status"] == "instock" for variant in variants)

                stock_overview.append({
                    "name": product["name"],
                    "instock": "✓" if in_stock else "X",
                    "stock": total_variant_stock if total_variant_stock > 0 else 0
                })

        # Stock overview nach Lagerbestand sortieren (absteigend)
        stock_overview = sorted(stock_overview, key=lambda x: x["stock"], reverse=True)

        # Metriken berechnen
        total_sales = sum([float(order['total']) for order in orders if order['status'] != 'cancelled'])
        total_sales_with_currency = f"{currency_symbol}{total_sales:.2f}"

        # `total_orders` ohne stornierte Bestellungen
        total_orders = len([order for order in orders if order['status'] != 'cancelled'])

        # `pending_orders` nur Bestellungen im Status "processing"
        pending_orders = len([order for order in orders if order['status'] == 'processing'])

        # `fulfilled_orders` für abgeschlossene Bestellungen
        fulfilled_orders = len([order for order in orders if order['status'] == 'completed'])

        # Gesamtzahl der verkauften Produkte
        total_sold_products = sum(
            sum(item["quantity"] for item in order["line_items"])
            for order in orders if order['status'] != 'cancelled'
        )

        return {
            "total_sales": total_sales_with_currency,
            "total_orders": total_orders,
            "pending_orders": pending_orders,
            "fulfilled_orders": fulfilled_orders,
            "total_sold_products": total_sold_products,
            "stock_overview": stock_overview,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        print(f"Fehler beim Abrufen der Daten: {e}")
        return None


# Funktion, um Daten an den Webhook zu senden
def send_to_webhook(data):
    try:
        webhook_body = {
            "merge_variables": {
                "updated_at": data["updated_at"],
                "total_sales": data["total_sales"],
                "total_orders": data["total_orders"],
                "pending_orders": data["pending_orders"],
                "fulfilled_orders": data["fulfilled_orders"],
                "total_sold_products": data["total_sold_products"],
                "stock_overview": data["stock_overview"],
            }
        }
        json_string = json.dumps(webhook_body, indent=4)

        # Debugging
        DEBUG = True
        if DEBUG:
            print(json_string)

        # Webhook senden
        response = requests.post(WEBHOOK_URL, json=webhook_body)
        response.raise_for_status()
        print(f"Webhook erfolgreich gesendet: {response.status_code}")
    except Exception as e:
        print(f"Fehler beim Senden an den Webhook: {e}")


# Hauptprogramm
if __name__ == "__main__":
    data = get_woocommerce_data()
    if data:
        send_to_webhook(data)