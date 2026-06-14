import base64
import json
import os
import requests
from datetime import datetime, timedelta

# Function to generate an OAuth2 access token
def get_access_token(CLIENT_ID, CLIENT_SECRET):
    TOKEN_FILE = "nameOfTokenToStoreUrEbayToken.json"
    # Check if the token already exists and is valid
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as file:
            token_data = json.load(file)
            expiration_time = datetime.fromisoformat(token_data["expires_at"])
            if expiration_time > datetime.now():
                return token_data["access_token"]

    # If the token is expired or doesn't exist, generate a new one
    auth = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_auth = base64.b64encode(auth.encode()).decode()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_auth}",
    }

    sandbox = os.environ.get("EBAY_SANDBOX", "false").lower() == "true"
    base = "api.sandbox.ebay.com" if sandbox else "api.ebay.com"
    API_SCOPE = "https://api.ebay.com/oauth/api_scope"
    OAUTH_URL = f"https://{base}/identity/v1/oauth2/token"

    data = {
        "grant_type": "client_credentials",
        "scope": API_SCOPE,
    }

    response = requests.post(OAUTH_URL, headers=headers, data=data)
    if response.status_code == 200:
        token_response = response.json()
        access_token = token_response["access_token"]
        expires_in = token_response["expires_in"]

        # Store the token and expiration time locally
        token_data = {
            "access_token": access_token,
            "expires_at": (datetime.now() + timedelta(seconds=expires_in)).isoformat(),
        }
        with open("ebay_token.json", "w") as file:
            json.dump(token_data, file)

        return access_token
    else:
        raise Exception(f"Error generating token: {response.status_code} {response.text}")


def _base_url():
    sandbox = os.environ.get("EBAY_SANDBOX", "false").lower() == "true"
    return "api.sandbox.ebay.com" if sandbox else "api.ebay.com"


def _auth_headers(access_token):
    return {"Authorization": f"Bearer {access_token}"}


# Function to make an authenticated eBay API request (auction-only, kept for backward compat)
def make_ebay_api_request(access_token, query=str, ammount=int):
    base = _base_url()
    url = f"https://{base}/buy/browse/v1/item_summary/search"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    params = {
        "q": query,
        "filter": "buyingOptions:{AUCTION}",
        "limit": ammount,
    }

    response = requests.get(url, headers=headers, params=params)
    ebay_search_results = []

    if response.status_code == 200:
        results = response.json().get("itemSummaries", [])
        if not results:
            return "No auctions found"

        for item in results:
            title = item.get("title", "N/A")
            price = item.get("currentBidPrice", {}).get("value")
            currency = item.get("currentBidPrice", {}).get("currency", "N/A")
            end_date = item.get("itemEndDate", "N/A")

            if end_date != "N/A":
                end_time = datetime.fromisoformat(end_date[:-1]).strftime("%Y-%m-%d %H:%M:%S")
            else:
                end_time = "N/A"

            ebay_search_results.append([title, price, currency, end_date, item.get('itemWebUrl', 'N/A'), item.get('itemId', 'N/A')])

        return ebay_search_results
    else:
        print(f"Error: {response.status_code} - {response.text}")


def get_item_detail(access_token, item_id):
    base = _base_url()
    headers = _auth_headers(access_token)

    candidates = [item_id]
    if not item_id.startswith("v1|") and item_id.isdigit():
        candidates.append(f"v1|{item_id}|0")

    last_response = None
    for candidate in candidates:
        url = f"https://{base}/buy/browse/v1/item/{requests.utils.quote(candidate, safe='')}"
        last_response = requests.get(url, headers=headers)
        print(f"get_item_detail: tried {candidate} -> {last_response.status_code}")
        if last_response.status_code == 200:
            return last_response.json()

    return {"error": f"{last_response.status_code} {last_response.text}"}


def search_listings(access_token, query, amount=10, buying_options=None, category_ids=None):
    """Search eBay listings with optional buying format and category filters."""
    base = _base_url()
    url = f"https://{base}/buy/browse/v1/item_summary/search"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    params = {"q": query, "limit": amount}
    filters = []
    if buying_options:
        filters.append(f"buyingOptions:{{{buying_options}}}")
    if filters:
        params["filter"] = ",".join(filters)
    if category_ids:
        params["category_ids"] = category_ids

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json().get("itemSummaries", [])
    return {"error": f"{response.status_code} {response.text}"}


def get_items_batch(access_token, item_ids):
    """Fetch up to 20 items in a single API call."""
    base = _base_url()
    headers = _auth_headers(access_token)
    params = {"item_ids": ",".join(item_ids)}
    url = f"https://{base}/buy/browse/v1/item/get_items"
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    return {"error": f"{response.status_code} {response.text}"}


def get_item_group(access_token, item_group_id):
    """Get all items in an item group (e.g. all color/size variants of a product)."""
    base = _base_url()
    headers = _auth_headers(access_token)
    params = {"item_group_id": item_group_id}
    url = f"https://{base}/buy/browse/v1/item/get_items_by_item_group"
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    return {"error": f"{response.status_code} {response.text}"}


def get_item_by_legacy_id(access_token, legacy_item_id, legacy_variation_id=None):
    """Get an item by its legacy numeric eBay item ID."""
    base = _base_url()
    headers = _auth_headers(access_token)
    params = {"legacy_item_id": legacy_item_id}
    if legacy_variation_id:
        params["legacy_variation_id"] = legacy_variation_id
    url = f"https://{base}/buy/browse/v1/item/get_item_by_legacy_id"
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    return {"error": f"{response.status_code} {response.text}"}


def get_deal_items(access_token, category_ids=None, limit=10):
    """Get eBay daily deal items."""
    base = _base_url()
    headers = _auth_headers(access_token)
    params = {"limit": limit}
    if category_ids:
        params["category_ids"] = category_ids
    url = f"https://{base}/buy/deal/v1/deal_item"
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    return {"error": f"{response.status_code} {response.text}"}


def get_deal_events(access_token, limit=10):
    """Get active eBay sale events."""
    base = _base_url()
    headers = _auth_headers(access_token)
    params = {"limit": limit}
    url = f"https://{base}/buy/deal/v1/event"
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    return {"error": f"{response.status_code} {response.text}"}


def get_deal_event_items(access_token, event_id, limit=10):
    """Get items associated with a specific eBay sale event."""
    base = _base_url()
    headers = _auth_headers(access_token)
    params = {"event_id": event_id, "limit": limit}
    url = f"https://{base}/buy/deal/v1/event_item"
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    return {"error": f"{response.status_code} {response.text}"}


def search_sold_items(access_token, query, limit=10):
    """Search historical sold listings for price research (Marketplace Insights API)."""
    base = _base_url()
    headers = _auth_headers(access_token)
    params = {"q": query, "limit": limit}
    url = f"https://{base}/buy/marketplace_insights/v1_beta/item_sales/search"
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()
    return {"error": f"{response.status_code} {response.text}"}
