from datetime import datetime
import base64
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from mcp.types import CallToolResult, TextContent



# orders schema
#[
# {
#     "order_id": "123456789",
#     "platform": "amazon/ebay/etsy"
#     "total_dimensions": [12, 6, 6]
#     "shipping_vendor": "usps",
#     "shipping_service": "ground advantage",
#     "recipient_name": "John Doe",
#     "recipient_address": "123 Main St",
#     "recipient_city": "Anytown",
#     "recipient_state": "CA",
#     "recipient_zip": "12345",
#     "recipient_country": "US",
#     "recipient_phone": "123-456-7890",
#     "recipient_email": "john.doe@example.com",
#     "shipping_dimension_unit": "in",
#     "shipping_weight_unit": "oz",
#     "sender_name": "John Doe",
#     "sender_address": "123 Main St",
#     "sender_city": "Anytown",
#     "sender_state": "CA",
#     "sender_zip": "12345",
#     "sender_country": "US",
#     "sender_phone": "123-456-7890",
#     "sender_email": "john.doe@example.com",
# }
#]


# labels schema
#[
# {
#     "order_id": "123456789",
#     "label_pdf_full_path": "../../abc.pdf",
#     "label_price": 10.00,
#     "status": "success/failed"
#     "failed_reason": "success/failed"
# }
#]


async def pirate_shipping_purchase_label(mainwin, args):  # type: ignore
    try:
        logger.debug("pirate_shipping_purchase_label started....")
        orders = args["input"]["orders"]
        web_driver = mainwin.getWebDriver()

        msg = f"completed in purchsing labels from pirate shipping: {len(labels)} labels purchased."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"labels": labels}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorPirateShippingPurchaseLabel")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]