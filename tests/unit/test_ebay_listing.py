"""eBay listing: OAuth, the Inventory API publish flow (mocked HTTP), the bulk CSV, the MCP tools."""

import asyncio
import csv
import json

import httpx
import pytest

from agent.ec_skills.listing.ebay_api import auth, config, listing
from agent.ec_skills.listing.ebay_csv import bulk_csv
from agent.mcp.server.integrations import ebay_listing_tools as tools


@pytest.fixture
def secrets(monkeypatch):
    store = {}
    monkeypatch.setattr(config, "_store_get", lambda k: store.get(k))
    monkeypatch.setattr(config, "_store_set", lambda k, v: store.__setitem__(k, v) or True)
    monkeypatch.setattr(config, "_store_delete", lambda k: store.pop(k, None))
    for k in ("ECAN_EBAY_ENV", "ECAN_EBAY_CLIENT_ID", "ECAN_EBAY_CLIENT_SECRET", "ECAN_EBAY_RU_NAME"):
        monkeypatch.delenv(k, raising=False)
    auth._access.clear()
    auth._pending_state.clear()
    return store


@pytest.fixture
def connected(secrets, monkeypatch):
    config.save_credentials("production", "app-id", "cert-id", "My-RuName")

    async def tok(env=None):
        return "ACCESS"
    monkeypatch.setattr(auth, "access_token", tok)
    return secrets


# --- OAuth -------------------------------------------------------------------

def test_consent_url_asks_for_the_listing_scopes(secrets):
    config.save_credentials("production", "app-id", "cert-id", "My-RuName")
    url = auth.consent_url()
    assert url.startswith("https://auth.ebay.com/oauth2/authorize?")
    assert "client_id=app-id" in url and "redirect_uri=My-RuName" in url
    assert "sell.inventory" in url and "sell.account" in url and "state=" in url


def test_missing_app_credentials_say_how_to_store_them(secrets):
    with pytest.raises(auth.EbayAuthError, match="ebay_api.config set"):
        auth.consent_url()


def test_consent_code_is_exchanged_and_only_status_comes_back(secrets, monkeypatch):
    config.save_credentials("production", "app-id", "cert-id", "My-RuName")
    auth.consent_url()
    state = auth._pending_state["production"]
    seen = {}

    async def fake_token(env, data):
        seen.update(data)
        return {"access_token": "A", "expires_in": 7200, "refresh_token": "R",
                "refresh_token_expires_in": 47304000}
    monkeypatch.setattr(auth, "_token_request", fake_token)
    redirect = ("https://signin.ebay.com/ws/eBayISAPI.dll?ThirdPartyAuthSucessFailure"
                f"&isAuthSuccessful=true&code=v%5E1.1%23abc&state={state}")
    st = asyncio.run(auth.complete_consent(redirect))
    assert seen == {"grant_type": "authorization_code", "code": "v^1.1#abc", "redirect_uri": "My-RuName"}
    assert st["connected"] and st["connection_expires_in_days"] > 500
    assert set(st) == {"env", "app_configured", "connected", "connection_expires_in_days"}, "no tokens out"
    assert secrets[config.key("production", "REFRESH_TOKEN")] == "R"


def test_declined_consent_is_an_error():
    with pytest.raises(auth.EbayAuthError, match="declined"):
        auth.code_from_url("https://x/?isAuthSuccessful=false")
    assert auth.code_from_url("https://www.ebay.com/signin") is None


# --- Inventory API publish ---------------------------------------------------

class Api:
    """A scripted eBay: routes (method, path) -> (status, json)."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def transport(self):
        def handle(req: httpx.Request):
            key = (req.method, req.url.path)
            self.calls.append((req.method, req.url.path, req.headers, req.content))
            status, body = self.routes.get(key, (404, {"errors": [{"errorId": 1, "message": f"no route {key}"}]}))
            return httpx.Response(status, json=body) if body is not None else httpx.Response(status)
        return httpx.MockTransport(handle)

    def body(self, method, path):
        return next(json.loads(c[3]) for c in self.calls if c[0] == method and c[1] == path)


SPEC = {"marketplace": "EBAY_GB", "category_id": "11450", "merchant_location_key": "WH1",
        "listing_policies": {"fulfillment_policy_id": "F", "payment_policy_id": "P", "return_policy_id": "R"},
        "items": [{"sku": "MUG-1", "title": "Blue mug", "description": "A mug", "price": 9.5,
                   "quantity": 3, "aspects": {"Brand": "ACME", "Colour": ["Blue"]},
                   "image_urls": ["https://i.ebayimg.com/x.jpg"]}]}


def test_a_single_item_is_created_offered_and_published(connected):
    api = Api({("PUT", "/sell/inventory/v1/inventory_item/MUG-1"): (204, None),
               ("GET", "/sell/inventory/v1/offer"): (404, {"errors": [{"errorId": 25713}]}),
               ("POST", "/sell/inventory/v1/offer"): (201, {"offerId": "O1"}),
               ("POST", "/sell/inventory/v1/offer/O1/publish"): (200, {"listingId": "L1"})})
    res = asyncio.run(listing.publish_listing(SPEC, transport=api.transport()))
    assert res["ok"] and res["listing_ids"] == {"MUG-1": "L1"}
    item = api.body("PUT", "/sell/inventory/v1/inventory_item/MUG-1")
    assert item["product"]["aspects"] == {"Brand": ["ACME"], "Colour": ["Blue"]}
    assert item["availability"]["shipToLocationAvailability"]["quantity"] == 3
    offer = api.body("POST", "/sell/inventory/v1/offer")
    assert offer["pricingSummary"]["price"] == {"value": "9.5", "currency": "GBP"}
    assert offer["marketplaceId"] == "EBAY_GB" and offer["listingPolicies"]["returnPolicyId"] == "R"
    assert api.calls[0][2]["content-language"] == "en-GB"
    assert api.calls[0][2]["authorization"] == "Bearer ACCESS"


def test_an_existing_offer_is_updated_not_duplicated(connected):
    api = Api({("PUT", "/sell/inventory/v1/inventory_item/MUG-1"): (204, None),
               ("GET", "/sell/inventory/v1/offer"): (200, {"offers": [{"offerId": "O9", "format": "FIXED_PRICE"}]}),
               ("PUT", "/sell/inventory/v1/offer/O9"): (204, None),
               ("POST", "/sell/inventory/v1/offer/O9/publish"): (200, {"listingId": "L9"})})
    res = asyncio.run(listing.publish_listing(SPEC, transport=api.transport()))
    assert res["ok"] and res["offers"] == {"MUG-1": "O9"}
    assert not any(c[0] == "POST" and c[1] == "/sell/inventory/v1/offer" for c in api.calls)


def test_a_variation_family_publishes_by_group(connected):
    spec = {**SPEC, "items": [
        {"sku": "TS-R", "price": 10, "quantity": 1, "aspects": {"Colour": "Red"}},
        {"sku": "TS-B", "price": 11, "quantity": 2, "aspects": {"Colour": "Blue"}}],
        "group": {"key": "TS", "title": "T-shirt", "description": "Cotton", "aspects": {"Brand": "ACME"},
                  "varies_by": {"Colour": ["Red", "Blue"]}, "image_varies_by": ["Colour"]}}
    routes = {("PUT", f"/sell/inventory/v1/inventory_item/{s}"): (204, None) for s in ("TS-R", "TS-B")}
    routes.update({("PUT", "/sell/inventory/v1/inventory_item_group/TS"): (204, None),
                   ("GET", "/sell/inventory/v1/offer"): (404, {}),
                   ("POST", "/sell/inventory/v1/offer"): (201, {"offerId": "O"}),
                   ("POST", "/sell/inventory/v1/offer/publish_by_inventory_item_group"): (200, {"listingId": "LG"})})
    api = Api(routes)
    res = asyncio.run(listing.publish_listing(spec, transport=api.transport()))
    assert res["ok"] and res["listing_ids"] == {"TS": "LG"}
    grp = api.body("PUT", "/sell/inventory/v1/inventory_item_group/TS")
    assert grp["variantSKUs"] == ["TS-R", "TS-B"]
    assert grp["variesBy"]["specifications"] == [{"name": "Colour", "values": ["Red", "Blue"]}]
    assert api.body("PUT", "/sell/inventory/v1/inventory_item/TS-R")["product"]["title"] == "T-shirt"


def test_rejections_come_back_by_step_and_sku_and_nothing_is_published(connected):
    api = Api({("PUT", "/sell/inventory/v1/inventory_item/MUG-1"): (400, {"errors": [
        {"errorId": 25002, "message": "Missing item specific", "parameters": [{"name": "aspect", "value": "Type"}]}]})})
    res = asyncio.run(listing.publish_listing(SPEC, transport=api.transport()))
    assert not res["ok"] and res["stage"] == "inventory_item"
    assert res["errors"] == [{"step": "inventory_item", "sku": "MUG-1", "error_id": 25002, "severity": "error",
                              "message": "Missing item specific", "detail": None,
                              "parameters": {"aspect": "Type"}}]
    assert [c[0] for c in api.calls] == ["PUT"]


def test_an_incomplete_spec_is_refused_before_any_call(connected):
    res = asyncio.run(listing.publish_listing({"items": [{"sku": "X"}]}))
    msgs = " ".join(e["message"] for e in res["errors"])
    assert not res["ok"] and "category_id" in msgs and "merchant_location_key" in msgs and "price" in msgs


def test_an_expired_token_is_refreshed_once(connected, monkeypatch):
    n = {"calls": 0}

    def handle(req):
        n["calls"] += 1
        return httpx.Response(401 if n["calls"] == 1 else 200, json={"categoryTreeId": "3"})
    from agent.ec_skills.listing.ebay_api.client import EbayClient
    out = asyncio.run(EbayClient(transport=httpx.MockTransport(handle)).get_json(
        "/commerce/taxonomy/v1/get_default_category_tree_id"))
    assert out == {"categoryTreeId": "3"} and n["calls"] == 2


def test_category_aspects_list_required_ones_with_values(connected):
    api = Api({("GET", "/commerce/taxonomy/v1/get_default_category_tree_id"): (200, {"categoryTreeId": "0"}),
               ("GET", "/commerce/taxonomy/v1/category_tree/0/get_item_aspects_for_category"): (200, {"aspects": [
                   {"localizedAspectName": "Brand", "aspectConstraint": {"aspectRequired": True, "aspectMode": "FREE_TEXT"},
                    "aspectValues": [{"localizedValue": v} for v in ("A", "B", "C")]},
                   {"localizedAspectName": "Colour", "aspectConstraint": {"aspectUsage": "RECOMMENDED",
                                                                          "aspectEnabledForVariations": True}},
                   {"localizedAspectName": "Style", "aspectConstraint": {}}]})})
    out = asyncio.run(listing.category_aspects("11450", max_values=2, transport=api.transport()))
    assert out["required"] == [{"name": "Brand", "mode": "FREE_TEXT", "multiple": False, "variation_ok": False,
                                "values": ["A", "B", "... (1 more)"]}]
    assert out["recommended"][0]["variation_ok"] and out["optional_names"] == ["Style"]


def test_local_images_are_uploaded_to_ebay(connected, tmp_path):
    img = tmp_path / "front.jpg"
    img.write_bytes(b"\xff\xd8jpeg")
    api = Api({("POST", "/commerce/media/v1_beta/image/create_image_from_file"):
               (201, {"imageUrl": "https://i.ebayimg.com/images/g/abc/s-l1600.jpg"})})
    out = asyncio.run(listing.upload_media([str(img), str(tmp_path / "missing.png")], transport=api.transport()))
    assert out["media"][0]["image_url"].startswith("https://i.ebayimg.com/")
    assert "error" in out["media"][1]


# --- bulk CSV ----------------------------------------------------------------

def _template(tmp_path):
    p = tmp_path / "ebay_template.csv"
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["#INFO", "Version=1.0", "Template=fx_category_template_EBAY_US"])
        w.writerow(["*Action(SiteID=US|Country=US|Currency=USD|Version=1193)", "CustomLabel", "*Category",
                    "*Title", "*ConditionID", "*C:Brand", "C:Colour", "PicURL", "*Description", "*Format",
                    "*Duration", "*StartPrice", "*Quantity", "Relationship", "RelationshipDetails",
                    "ShippingProfileName"])
    return str(p)


def _read(path):
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    return rows[1], [dict(zip(rows[1], r)) for r in rows[2:]]


def test_csv_inspect_reads_site_and_required_columns(tmp_path):
    info = bulk_csv.inspect_template(_template(tmp_path))
    assert info["site"] == {"SiteID": "US", "Country": "US", "Currency": "USD", "Version": "1193"}
    assert "StartPrice" in info["required"] and info["item_specifics"] == ["Brand", "Colour"]


def test_csv_fill_single_and_variation_family(tmp_path):
    t = _template(tmp_path)
    res = bulk_csv.fill_template(t, {"listings": [
        {"sku": "MUG-1", "category_id": 20625, "title": "Mug", "condition_id": 1000, "description": "d",
         "price": 9.5, "quantity": 3, "aspects": {"Brand": "ACME"}, "pic_urls": ["https://a/1.jpg", "https://a/2.jpg"],
         "shipping_profile": "Std"},
        {"sku": "TS", "category_id": 15687, "title": "Tee", "condition_id": 1000, "description": "d",
         "aspects": {"Brand": "ACME"},
         "variations": [{"sku": "TS-R", "specifics": {"Colour": "Red"}, "price": 10, "quantity": 1},
                        {"sku": "TS-B", "specifics": {"Colour": "Blue"}, "price": 11, "quantity": 2}]}]})
    header, rows = _read(res["upload_file"])
    assert res["rows"] == 4 and not res["warnings"]
    act = header[0]
    single, parent, red, blue = rows
    assert single[act] == "Add" and single["*StartPrice"] == "9.5" and single["PicURL"] == "https://a/1.jpg|https://a/2.jpg"
    assert single["*Format"] == "FixedPrice" and single["*Duration"] == "GTC" and single["*C:Brand"] == "ACME"
    assert parent["RelationshipDetails"] == "Colour=Red;Blue" and parent["*StartPrice"] == ""
    assert red[act] == "" and red["Relationship"] == "Variation" and red["RelationshipDetails"] == "Colour=Red"
    assert red["CustomLabel"] == "TS-R" and blue["*Quantity"] == "2"


def test_csv_fill_warns_on_empty_required_and_adds_unknown_specifics(tmp_path):
    res = bulk_csv.fill_template(_template(tmp_path), {"listings": [
        {"sku": "X", "title": "t", "aspects": {"Material": "Steel"}}]})
    header, rows = _read(res["upload_file"])
    assert "C:Material" in header and rows[0]["C:Material"] == "Steel"
    assert any("required column(s) empty" in w and "StartPrice" in w for w in res["warnings"])


def test_csv_results_give_errors_and_item_ids(tmp_path):
    p = tmp_path / "results.csv"
    p.write_text("Line Number,Action,Status,ErrorCode,ErrorMessage,Item ID,CustomLabel\n"
                 "1,Add,Success,,,1234567890,MUG-1\n"
                 "2,Add,Failure,21919303,Item specific Brand is missing.,,TS\n", encoding="utf-8")
    out = bulk_csv.parse_results(str(p))
    assert out["errors"] == 1 and out["listed_item_ids"] == ["1234567890"] and not out["done"]
    assert out["items"][1] == {"status": "Failure", "sku": "TS", "item_id": None, "error_code": "21919303",
                               "message": "Item specific Brand is missing.", "severity": "error"}


# --- MCP tools ---------------------------------------------------------------

def _call(fn, **inp):
    return json.loads(asyncio.run(fn(None, {"input": inp}))[0].text)


def test_status_tells_what_is_missing(secrets):
    out = _call(tools.ebay_api_status)
    assert out["ok"] and not out["app_configured"] and "config set" in out["next"]
    config.save_credentials("production", "a", "b", "c")
    assert "ebay_connect_account" in _call(tools.ebay_api_status)["next"]


def test_publish_tool_returns_spec_problems(connected):
    out = _call(tools.ebay_publish_listing, spec={"items": []})
    assert not out["ok"] and out["stage"] == "spec" and "fix exactly" in out["next"]


def test_the_tools_are_registered_desktop_only():
    from agent.mcp.server.server import tool_function_mapping
    schemas = []
    tools.add_ebay_listing_tool_schemas(schemas)
    assert len(schemas) == 9
    for s in schemas:
        assert s.name in tool_function_mapping and s.meta == {"run_in_cloud": False}
