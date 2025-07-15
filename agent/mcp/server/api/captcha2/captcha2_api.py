import os
from twocaptcha import TwoCaptcha

TWO_CAPTCHA_API_KEY = os.getenv('TWO_CAPTCHA_API_KEY', '')
print("TWO_CAPTCHA_API_KEY:", TWO_CAPTCHA_API_KEY)

solver = TwoCaptcha(TWO_CAPTCHA_API_KEY)
config = {
            'server':           '2captcha.com',
            'apiKey':           TWO_CAPTCHA_API_KEY,
            'softId':            4580,
            'callback':         'https://your.site/result-receiver',
            'defaultTimeout':    120,
            'recaptchaTimeout':  600,
            'pollingInterval':   10,
            'extendedResponse':  False
        }
solver = TwoCaptcha(**config)

result = solver.normal('https://site-with-captcha.com/path/to/captcha.jpg', param1=..., ...)


