

sample_metrics_0 = {
  "id": "eval_system_form",
  "type": "score",
  "title": "score system",
  "components": [
    {
      "name": "price",
      "type": "integer",
      "raw_value": 125,
      "target_value": 125,
      "max_value": 150,
      "min_value": 0,
      "unit": "cents",
      "tooltip": "unit price in cents, 1.25 is the target max price",
      "score_formula": "80 + (125-price)",
      "score_lut": {},
      "weight": 0.3
    },
    {
      "name": "availability",
      "type": "integer",
      "raw_value": 0,
      "target_value": 0,
      "max_value": 150,
      "min_value": 0,
      "unit": "days",
      "tooltip": "nuber of days before the part is available",
      "score_formula": "",
      "score_lut": {
        "20": 100,
        "10": 80,
        "8": 60
      },
      "weight": 0.3
    },
    {
      "name": "performance",
      "type": "integer",
      "raw_value": {
        "power": {
          "raw_value": 3,
          "target_value": 125,
          "type": "integer",
          "unit": "mA",
          "tooltip": "power consumption in mA",
          "score_formula": "80 + (5-current)",
          "score_lut": {},
          "weight": 0.7
        },
        "clock_rate": {
          "raw_value": 10,
          "target_value": 125,
          "max_value": 120,
          "min_value": 0,
          "type": "integer",
          "unit": "MHz",
          "tooltip": "max clock speed in MHz",
          "score_formula": "80 + (speed - 10)",
          "score_lut": {},
          "weight": 0.3
        }
      },
      "unit": "",
      "tooltip": "technical performance",
      "score_formula": "100 - 5*performance",
      "score_lut": {},
      "weight": 0.4
    }
  ]
}

sample_parameters_0 = {
  "id": "mcu_config_form",
  "type": "normal",
  "title": "MCU 配置",
  "fields": [
    {
      "id": "core",
      "type": "select",
      "label": "MCU Core",
      "tooltip": "MCU Core Types",
      "options": [
        { "label": "ATmega328P", "value": "ATmega328P" },
        { "label": "ESP32", "value": "ESP32" },
        { "label": "STM32F103", "value": "STM32F103" },
        { "label": "PIC16F84A", "value": "PIC16F84A" },
        { "label": "Arduino Nano", "value": "Arduino Nano" }
      ],
      "defaultValue": "ESP32"
    },
    {
      "id": "factory",
      "type": "text",
      "label": "Factory",
      "tooltip": "Test field type text",
      "defaultValue": "ESP——32"
    },
    {
      "id": "clock_speed",
      "type": "checkbox",
      "label": "Clock Speed",
      "tooltip": "Clock Speed Options",
      "options": [
        { "label": "8", "value": "8" },
        { "label": "16", "value": "16" },
        { "label": "32", "value": "32" },
        { "label": "64", "value": "64" },
        { "label": "128", "value": "128" }
      ],
      "defaultValue": ["16", "64"]
    },
    {
      "id": "voltage",
      "type": "select",
      "label": "Operating Voltage",
      "tooltip": "Operation Voltage Options",
      "options": [
        { "label": "3.3V", "value": "3.3V" },
        { "label": "5V", "value": "5V" },
        { "label": "12V", "value": "12V" }
      ],
      "defaultValue": "3.3V"
    },
    {
      "id": "watchdog_timer",
      "type": "switch",
      "label": "Watchdog Timer",
      "tooltip": "Watchdog timer Switch",
      "defaultValue": True
    },
    {
      "id": "debug_interface",
      "type": "radio",
      "label": "Debug Interface",
      "tooltip": "Debug Radio Interface",
      "options": [
        { "label": "UART", "value": "UART" },
        { "label": "SPI", "value": "SPI" },
        { "label": "I2C", "value": "I2C" },
        { "label": "USB", "value": "USB" }
      ],
      "defaultValue": "UART"
    },
    {
      "id": "temperature",
      "type": "slider",
      "label": "温度设置",
      "tooltip": "template Settings",
      "min": 0,
      "max": 100,
      "step": 1,
      "unit": "°C",
      "defaultValue": 25,
      "required": True
    },
    {
      "id": "volume",
      "type": "slider",
      "label": "音量控制",
      "tooltip": "Volumn Slider Compontent",
      "min": 0,
      "max": 10,
      "step": 0.5,
      "unit": "",
      "defaultValue": 5
    }, {
      "id": "brand",
      "type": "select",
      "label": "Brand",
      "tooltip": "Brand And Cusotm Options",
      "custom": True,
      "options": [
        { "label": "Intel", "value": "Intel-1" },
        { "label": "AMD", "value": "AMD-2" },
        { "label": "HiSi", "value": "HiSi-3" }
      ],
      "defaultValue": "Intel"
    }
  ],
  "submit_text": "保存"
}

sample_search_result0 = {
  "id": "search_results_form",
  "title": "MCU Search Results",
  "Items": [
    {
      "product_id": "mcu",
      "product_name": "product1",
      "brand": "brand1",
      "model": "model1",
      "main_image": "img_url",
      "url": "web_site_page_url",
      "rank": 1,
      "score": 99.01,
      "highlights": [
        { "label": "size", "value": "0201", "unit": "size" },
        { "label": "price", "value": "0.01", "unit": "size" },
        { "label": "precision", "value": "100", "unit": "ppm" }
      ],
      "app_specific": [
        {
          "app": "oil_diffuser",
          "needed_criterias": [
            {
              "criteria1": "spec1",
              "required_value": "100",
              "matched_value": "120"
            }
          ]
        }
      ]
    },
    {
      "product_id": "mcu",
      "product_name": "product2",
      "brand": "brand2",
      "model": "model2",
      "main_image": "img_url",
      "url": "web_site_page_url",
      "rank": 1,
      "score": 99.01,
      "highlights": [
        { "label": "size", "value": "0201", "unit": "size" },
        { "label": "price", "value": "0.01", "unit": "size" },
        { "label": "precision", "value": "100", "unit": "ppm" }
      ],
      "app_specific": [
        {
          "app": "oil_diffuser",
          "needed_criterias": [
            {
              "criteria1": "spec1",
              "required_value": "100",
              "matched_value": "120"
            }
          ]
        }
      ]
    }
  ],
  "summary": {
    "product1": {
      "criteria1": "value",
      "criteria2": "value",
      "criteria3": "value"
    },
    "product2": {
      "criteria1": "value",
      "criteria2": "value",
      "criteria3": "value"
    },
    "product3": {
      "criteria1": "value",
      "criteria2": "value",
      "criteria3": "value"
    }
  },
  "comments": [],
  "statistics": {
    "sites_visited": 1,
    "searches": 1,
    "pages_visited": 1,
    "input_tokens": 1,
    "output_tokens": 1,
    "products_compared": 1
  },
  "behind_the_scene": "url",
  "show_feedback_options": True
}