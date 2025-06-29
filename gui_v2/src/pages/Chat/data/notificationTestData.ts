/**
 * 通知测试数据文件
 * 
 * 本文件包含各种类型的通知测试数据，用于开发和测试通知功能。
 * 
 * 测试数据类型：
 * - 'mcuConfig': MCU 配置数据
 * - 'sensorConfig': 传感器配置数据
 * - 'networkConfig': 网络配置数据
 * - 'motorConfig': 电机配置数据
 * - 'displayConfig': 显示配置数据
 * - 'robotConfig': 机器人配置数据
 * - 'iotConfig': IoT 配置数据
 * - 'errorData': 错误数据（无效 JSON）
 * - 'emptyData': 空数据
 * - 'complexConfig': 复杂嵌套配置
 */

// 通知测试数据集合
export const notificationTestData = {
  // MCU 配置数据
  mcuConfig: {
    "core": {
      "name": "MCU Core",
      "unit": "",
      "type": "selection_list",
      "options": ["ATmega328P", "ESP32", "STM32F103", "PIC16F84A", "Arduino Nano"],
      "default": "ESP32"
    },
    "clock_speed": {
      "name": "Clock Speed",
      "unit": "MHz",
      "type": "range_scale",
      "options": ["8", "16", "32", "64", "128"],
      "default": ["16", "64"]
    },
    "voltage": {
      "name": "Operating Voltage",
      "unit": "V",
      "type": "selection_list",
      "options": ["3.3V", "5V", "12V"],
      "default": "3.3V"
    },
    "watchdog_timer": {
      "name": "Watchdog Timer",
      "unit": "",
      "type": "check_box",
      "options": [],
      "default": "checked"
    },
    "debug_interface": {
      "name": "Debug Interface",
      "unit": "",
      "type": "radio_button_group",
      "options": ["UART", "SPI", "I2C", "USB"],
      "default": "UART"
    }
  },

  // 传感器配置数据
  sensorConfig: {
    "sensor_type": {
      "name": "Sensor Type",
      "unit": "",
      "type": "selection_list",
      "options": ["Temperature", "Humidity", "Pressure", "Accelerometer", "Gyroscope"],
      "default": "Temperature"
    },
    "sampling_rate": {
      "name": "Sampling Rate",
      "unit": "Hz",
      "type": "range_scale",
      "options": ["1", "10", "100", "1000"],
      "default": ["10", "100"]
    },
    "calibration": {
      "name": "Auto Calibration",
      "unit": "",
      "type": "check_box",
      "options": [],
      "default": "unchecked"
    },
    "communication": {
      "name": "Communication Protocol",
      "unit": "",
      "type": "radio_button_group",
      "options": ["Analog", "Digital", "I2C", "SPI"],
      "default": "I2C"
    }
  },

  // 网络配置数据
  networkConfig: {
    "connection_type": {
      "name": "Connection Type",
      "unit": "",
      "type": "radio_button_group",
      "options": ["WiFi", "Ethernet", "Cellular", "Bluetooth"],
      "default": "WiFi"
    },
    "ssid": {
      "name": "Network SSID",
      "unit": "",
      "type": "text_input",
      "options": [],
      "default": "TestNetwork"
    },
    "security": {
      "name": "Security Type",
      "unit": "",
      "type": "selection_list",
      "options": ["Open", "WEP", "WPA", "WPA2", "WPA3"],
      "default": "WPA2"
    },
    "auto_reconnect": {
      "name": "Auto Reconnect",
      "unit": "",
      "type": "check_box",
      "options": [],
      "default": "checked"
    }
  },

  // 电机控制配置
  motorConfig: {
    "motor_type": {
      "name": "Motor Type",
      "unit": "",
      "type": "selection_list",
      "options": ["DC Motor", "Stepper Motor", "Servo Motor", "Brushless DC"],
      "default": "DC Motor"
    },
    "voltage_rating": {
      "name": "Voltage Rating",
      "unit": "V",
      "type": "range_scale",
      "options": ["3.3", "5", "12", "24", "48"],
      "default": ["5", "12"]
    },
    "speed_control": {
      "name": "Speed Control",
      "unit": "",
      "type": "check_box",
      "options": [],
      "default": "checked"
    },
    "direction_control": {
      "name": "Direction Control",
      "unit": "",
      "type": "radio_button_group",
      "options": ["Forward Only", "Bidirectional", "Multi-direction"],
      "default": "Bidirectional"
    }
  },

  // 显示配置
  displayConfig: {
    "display_type": {
      "name": "Display Type",
      "unit": "",
      "type": "selection_list",
      "options": ["LCD", "OLED", "TFT", "E-Paper", "LED Matrix"],
      "default": "OLED"
    },
    "resolution": {
      "name": "Resolution",
      "unit": "pixels",
      "type": "selection_list",
      "options": ["128x64", "240x320", "480x320", "800x600", "1024x768"],
      "default": "128x64"
    },
    "color_depth": {
      "name": "Color Depth",
      "unit": "bit",
      "type": "radio_button_group",
      "options": ["1", "8", "16", "24"],
      "default": "16"
    },
    "backlight": {
      "name": "Backlight Control",
      "unit": "",
      "type": "check_box",
      "options": [],
      "default": "checked"
    }
  },

  // 机器人配置
  robotConfig: {
    "robot_type": {
      "name": "Robot Type",
      "unit": "",
      "type": "selection_list",
      "options": ["Mobile Robot", "Articulated Robot", "Delta Robot", "SCARA Robot"],
      "default": "Mobile Robot"
    },
    "degrees_of_freedom": {
      "name": "Degrees of Freedom",
      "unit": "",
      "type": "range_scale",
      "options": ["2", "3", "4", "5", "6", "7"],
      "default": ["3", "6"]
    },
    "payload_capacity": {
      "name": "Payload Capacity",
      "unit": "kg",
      "type": "range_scale",
      "options": ["1", "5", "10", "20", "50", "100"],
      "default": ["5", "20"]
    },
    "precision": {
      "name": "Positioning Precision",
      "unit": "mm",
      "type": "selection_list",
      "options": ["±0.1", "±0.5", "±1.0", "±2.0", "±5.0"],
      "default": "±0.5"
    }
  },

  // IoT 设备配置
  iotConfig: {
    "device_type": {
      "name": "Device Type",
      "unit": "",
      "type": "selection_list",
      "options": ["Smart Sensor", "Actuator", "Gateway", "Controller"],
      "default": "Smart Sensor"
    },
    "protocol": {
      "name": "Communication Protocol",
      "unit": "",
      "type": "radio_button_group",
      "options": ["MQTT", "HTTP", "CoAP", "WebSocket"],
      "default": "MQTT"
    },
    "data_format": {
      "name": "Data Format",
      "unit": "",
      "type": "selection_list",
      "options": ["JSON", "XML", "CSV", "Binary"],
      "default": "JSON"
    },
    "encryption": {
      "name": "Data Encryption",
      "unit": "",
      "type": "check_box",
      "options": [],
      "default": "checked"
    }
  },

  // 错误数据（无效 JSON）
  errorData: {
    "invalid_field": {
      "name": "Invalid Field",
      "unit": "",
      "type": "invalid_type",
      "options": "invalid_options",
      "default": null
    }
  },

  // 空数据
  emptyData: {},

  // 复杂嵌套配置
  complexConfig: {
    "system": {
      "name": "System Configuration",
      "unit": "",
      "type": "selection_list",
      "options": ["Basic", "Advanced", "Expert"],
      "default": "Advanced"
    },
    "subsystems": {
      "name": "Subsystems",
      "unit": "",
      "type": "check_box",
      "options": [],
      "default": "checked"
    },
    "advanced_settings": {
      "name": "Advanced Settings",
      "unit": "",
      "type": "radio_button_group",
      "options": ["Performance", "Efficiency", "Balanced"],
      "default": "Balanced"
    }
  }
};

// 获取随机测试数据
export const getRandomNotificationData = () => {
  const dataTypes = Object.keys(notificationTestData);
  const randomType = dataTypes[Math.floor(Math.random() * dataTypes.length)] as keyof typeof notificationTestData;
  
  return {
    text: `随机测试数据 - ${randomType}`,
    type: 'custom',
    code: {
      value: JSON.stringify(notificationTestData[randomType], null, 2)
    }
  };
};

// 获取指定类型的测试数据
export const getNotificationTestData = (type: keyof typeof notificationTestData) => {
  if (!notificationTestData[type]) {
    console.warn(`Unknown test data type: ${type}`);
    return getRandomNotificationData();
  }

  return {
    text: `${type} 配置数据`,
    type: 'custom',
    code: {
      value: JSON.stringify(notificationTestData[type], null, 2)
    }
  };
}; 