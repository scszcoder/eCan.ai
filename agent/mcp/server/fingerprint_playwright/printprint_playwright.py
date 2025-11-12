from playwright.sync_api import sync_playwright
import random

def launch_stealth_playwright():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Make it visible
        context = browser.new_context(
            user_agent=random.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15"
            ]),
            locale="en-US",
            timezone_id="America/New_York",
            viewport={"width": 1280, "height": 800},
            device_scale_factor=1,
        )

        # Inject anti-fingerprint scripts
        context.add_init_script("""
            // Navigator Webdriver
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

            // Languages
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

            // Plugins
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });

            // Platform
            Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

            // Hardware Concurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });

            // WebGL Vendor
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.'; // UNMASKED_VENDOR_WEBGL
                if (parameter === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
                return getParameter.call(this, parameter);
            };

            // Canvas fingerprinting
            const getContext = HTMLCanvasElement.prototype.getContext;
            HTMLCanvasElement.prototype.getContext = function(type) {
                const ctx = getContext.call(this, type);
                const getImageData = ctx.getImageData;
                ctx.getImageData = function(...args) {
                    const data = getImageData.apply(this, args);
                    // Optional: Modify pixel data to poison canvas fingerprint
                    return data;
                };
                return ctx;
            };

            // WebRTC leak prevent
            Object.defineProperty(window, 'RTCPeerConnection', {
                get: () => undefined,
            });
        """)

        page = context.new_page()

        # Test site to validate fingerprint
        page.goto("https://bot.sannysoft.com/")
        input("Press ENTER to close...")  # Keeps browser open until you manually close

        browser.close()


    # browser = p.chromium.launch(
    #     headless=False,
    #     proxy={
    #         "server": "http://my-proxy.example.com:3128",  # or socks5://...
    #         "username": "myUsername",       # optional
    #         "password": "myPassword",       # optional
    #     }
    # )

# context = browser.new_context(
#     cookies=[
#         {
#             "name": "sessionid",
#             "value": "abc123xyz",
#             "domain": ".example.com",
#             "path": "/",
#             "httpOnly": True,
#             "secure": True,
#             "sameSite": "Lax",
#         }
#     ],
#     user_agent="your_user_agent",
#     locale="en-US",
#     timezone_id="America/New_York"
# )

# # Save cookies
# cookies = context.cookies()
# with open("cookies.json", "w") as f:
#     import json
#     json.dump(cookies, f)
#
# # Load cookies
# with open("cookies.json", "r") as f:
#     cookies = json.load(f)
# context.add_cookies(cookies)


# from playwright.sync_api import sync_playwright
# import json
#
# def launch_stealth_browser():
#     with sync_playwright() as p:
#         browser = p.chromium.launch(
#             headless=False,
#             proxy={
#                 "server": "http://proxy.example.com:8080",
#                 "username": "user",
#                 "password": "pass"
#             }
#         )
#
#         # Load cookies if available
#         try:
#             with open("cookies.json", "r") as f:
#                 cookies = json.load(f)
#         except FileNotFoundError:
#             cookies = []
#
#         context = browser.new_context(
#             user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/118 Safari/537.36",
#             locale="en-US",
#             timezone_id="America/New_York",
#             cookies=cookies,
#             viewport={"width": 1280, "height": 800},
#         )
#
#         # Anti-detection JS injection
#         context.add_init_script("""
#             Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
#             Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
#         """)
#
#         page = context.new_page()
#         page.goto("https://bot.sannysoft.com/")
#
#         input("Press ENTER to exit and save cookies...")
#         with open("cookies.json", "w") as f:
#             json.dump(context.cookies(), f)
#
#         browser.close()

# 📝 Note: This approach doesn't allow new_context(), because launch_persistent_context() returns a BrowserContext.
browser = p.chromium.launch_persistent_context(
    user_data_dir="./user_data",
    headless=False,
    proxy={"server": "http://proxy.example.com:8080"}
)

# HAR Capture (Network Activity Logging)
# To record all network traffic like a browser devtool HAR:
context = browser.new_context(record_har_path="network.har")
page = context.new_page()
page.goto("https://example.com")
context.close()  # HAR will

# if __name__ == "__main__":
#     launch_stealth_browser()
