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


async def pirate_shipping_purchase_labels(mainwin, args):  # type: ignore
    try:
        logger.debug("pirate_shipping_purchase_label started....")
        orders = args["input"]["orders"]
        labels = []
        web_driver = mainwin.getWebDriver()

        msg = f"completed in purchsing labels from pirate shipping: {len(labels)} labels purchased."
        tool_result = TextContent(type="text", text=msg)
        tool_result.meta = {"labels": labels}
        return [tool_result]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorPirateShippingPurchaseLabel")
        logger.debug(err_trace)
        return [TextContent(type="text", text=err_trace)]


def add_pirate_shipping_purchase_labels_tool_schema(tool_schemas):
    import mcp.types as types

    tool_schema = types.Tool(
        name="pirate_shipping_purchase_labels",
        description="Answer ebay messages with text, attachments, and related actions if any (for example, handle return, cancel, refund/partial refund, send replacement items, etc",
        inputSchema={
            "type": "object",
            "required": ["input"],  # the root requires *input*
            "properties": {
                "input": {  # nested object
                    "type": "object",
                    "required": ["orders"],
                    "properties": {
                        "type": "array",
                        "description": "list of json objects with basic attributes of order_id, dimension, weight, and sender and recipient name and address info.",
                        "items": {
                            "type": "object",
                            "required": ["message_id", "reply_text", "reply_attachments", "actions"],
                            "properties": {
                                "order_id": {"type": "string"},
                                "platform": {"type": "string"},
                                "total_dimensions": {"type": "array"},
                                "shipping_vendor": {"type": "string"},
                                "shipping_service": {"type": "string"},
                                "recipient_name": {"type": "string"},
                                "recipient_address": {"type": "string"},
                                "recipient_city": {"type": "string"},
                                "recipient_state": {"type": "string"},
                                "recipient_zip": {"type": "string"},
                                "recipient_country": {"type": "string"},
                                "recipient_phone": {"type": "string"},
                                "recipient_email": {"type": "string"},
                                "shipping_dimension_unit": {"type": "string"},
                                "shipping_weight_unit": {"type": "string"},
                                "sender_name": {"type": "string"},
                                "sender_address": {"type": "string"},
                                "sender_city":{"type": "string"},
                                "sender_state": {"type": "string"},
                                "sender_zip": {"type": "string"},
                                "sender_country": {"type": "string"},
                                "sender_phone": {"type": "string"},
                                "sender_email": {"type": "string"},
                            }
                        }
                    }
                }
            }
        },
    )

    tool_schemas.append(tool_schema)