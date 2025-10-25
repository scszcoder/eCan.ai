import requests
from datetime import datetime, timedelta

# Define the base URL of your Flask API
LOCALDB_HOST_NAME = "DESKTOP-DLLV0"
LOCALDB_IP = "192.168.0.31"
LOCALDB_PORT = "5000"
API_BASE_URL = "http://"+LOCALDB_IP+":"+LOCALDB_PORT+"/api/data"  # Adjust if running on a different host/port

def localBusinessAddRow(data):
    """
    Adds a new row to the BUSINESSES table.

    Args:
        data (dict): A dictionary of data to add, e.g.,
            {
                "uid": 1,
                "mid": 2,
                "order_asin": "B07XYZ",
                "order_pay_amount": 100,
                "order_pay_date": "2024-11-09",
                "status": "in progress"
                # add other fields as needed
            }
    Returns:
        Response JSON with status or error message.
    """
    try:
        response = requests.post(API_BASE_URL, json=data, timeout=10)
        response.raise_for_status()  # Raises an error for non-2xx responses
        return response.json()
    except requests.RequestException as e:
        print("Failed to add row:", e)
        return None


def localBusinessUpdateRow(bid, data):
    """
    Updates an existing row in the BUSINESSES table.

    Args:
        bid (int): The primary key (id) of the row to update.
        data (dict): A dictionary of data to update, e.g.,
            {
                "order_asin": "B07XYZ",
                "status": "completed",
                "last_action_date": "2024-11-09"
                # add other fields as needed
            }
    Returns:
        Response JSON with status or error message.
    """
    try:
        url = f"{API_BASE_URL}/{bid}"
        response = requests.put(url, json=data, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print("Failed to update row:", e)
        return None


def localBusinessQueryByAsin(order_asin):
    """
    Queries rows in the BUSINESSES table by the order_asin value.

    Args:
        order_asin (str): The ASIN to search for.
    Returns:
        List of matching rows or None if an error occurs.
    """
    try:
        url = f"{API_BASE_URL}/query"
        params = {"order_asin": order_asin}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print("Failed to query by ASIN:", e)
        return None


def localBusinessQueryAcctForPast7Days():
    """
    Queries rows in the ACCOUNTS table that were created within the past 7 days.

    Returns:
        List of matching rows or None if an error occurs.
    """
    try:
        # Calculate the date range (last 7 days)
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

        url = f"{API_BASE_URL}/ACCOUNTS/query"
        params = {
            "startDate": start_date,
            "endDate": end_date
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print("Failed to query accounts created in the past 7 days:", e)
        return None


# Example usage
def localDBUnitTest():
    # 1. Adding a new row
    new_data = {
        "uid": 1,
        "mid": 2,
        "order_asin": "B07XYZ",
        "order_pay_amount": 100,
        "order_pay_date": "2024-11-09",
        "status": "in progress"
    }
    add_result = localBusinessAddRow(new_data)
    print("Add Result:", add_result)

    # 2. Updating a row with a specific `bid`
    update_data = {
        "status": "completed",
        "last_action_date": "2024-11-09"
    }
    update_result = localBusinessUpdateRow(bid=1, data=update_data)  # Replace `bid=1` with the actual `bid` value you want to update
    print("Update Result:", update_result)

    # 3. Querying rows by `order_asin`
    query_result = localBusinessUpdateRow(order_asin="B07XYZ")
    print("Query Result:", query_result)
