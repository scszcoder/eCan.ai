/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { CallableFunction } from '../../typings/callable';

// SystemFunctionList
export const systemFunctions: CallableFunction[] = [
  {
    name: 'calculateTotal',
    desc: '计算商品总价（含税）',
    params: {
      type: 'object',
      properties: {
        price: {
          type: 'number',
          description: '商品单价'
        },
        quantity: {
          type: 'number',
          description: '商品Count'
        },
        taxRate: {
          type: 'number',
          description: '税率（百分比）'
        }
      },
      required: ['price', 'quantity', 'taxRate']
    },
    returns: {
      type: 'object',
      properties: {
        total: {
          type: 'number',
          description: '含税总价'
        },
        tax: {
          type: 'number',
          description: '税额'
        }
      }
    },
    type: 'system',
    sysId: 'calc_total_v1',
    code: `def calculate_total(params):
    price = params['price']
    quantity = params['quantity']
    tax_rate = params['taxRate']
    
    # 计算不含税总价
    subtotal = price * quantity
    
    # 计算税额
    tax = subtotal * (tax_rate / 100)
    
    # 计算含税总价
    total = subtotal + tax
    
    return {
        'total': round(total, 2),
        'tax': round(tax, 2)
    }`
  },
  {
    name: 'formatDate',
    desc: 'FormatDate字符串',
    params: {
      type: 'object',
      properties: {
        date: {
          type: 'string',
          description: 'Date字符串'
        },
        format: {
          type: 'string',
          description: '目标格式',
          enum: ['YYYY-MM-DD', 'DD/MM/YYYY', 'MM/DD/YYYY']
        }
      },
      required: ['date', 'format']
    },
    returns: {
      type: 'string',
      description: 'Format后的Date字符串'
    },
    type: 'system',
    sysId: 'format_date_v1',
    code: `from datetime import datetime

def format_date(params):
    date_str = params['date']
    format_type = params['format']
    
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    
    if format_type == 'YYYY-MM-DD':
        return date_obj.strftime('%Y-%m-%d')
    elif format_type == 'DD/MM/YYYY':
        return date_obj.strftime('%d/%m/%Y')
    elif format_type == 'MM/DD/YYYY':
        return date_obj.strftime('%m/%d/%Y')
    else:
        raise ValueError('Unsupported date format')`
  },
  {
    name: 'validateEmail',
    desc: 'Validate邮箱Address格式',
    params: {
      type: 'object',
      properties: {
        email: {
          type: 'string',
          description: '邮箱Address'
        }
      },
      required: ['email']
    },
    returns: {
      type: 'object',
      properties: {
        isValid: {
          type: 'boolean',
          description: '是否有效'
        },
        message: {
          type: 'string',
          description: 'ValidateResult说明'
        }
      }
    },
    type: 'system',
    sysId: 'validate_email_v1',
    code: `import re

def validate_email(params):
    email = params['email']
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
    
    is_valid = bool(re.match(email_regex, email))
    
    return {
        'isValid': is_valid,
        'message': 'Valid email address' if is_valid else 'Invalid email format'
    }`
  },
  {
    name: 'calculateDiscount',
    desc: '计算商品折扣价格',
    params: {
      type: 'object',
      properties: {
        price: {
          type: 'number',
          description: '原价'
        },
        discountType: {
          type: 'string',
          description: '折扣Type',
          enum: ['percentage', 'fixed']
        },
        discountValue: {
          type: 'number',
          description: '折扣Value（百分比或固定金额）'
        }
      },
      required: ['price', 'discountType', 'discountValue']
    },
    returns: {
      type: 'object',
      properties: {
        originalPrice: {
          type: 'number',
          description: '原价'
        },
        discountAmount: {
          type: 'number',
          description: '折扣金额'
        },
        finalPrice: {
          type: 'number',
          description: '最终价格'
        }
      }
    },
    type: 'system',
    sysId: 'calc_discount_v1',
    code: `def calculate_discount(params):
    price = params['price']
    discount_type = params['discountType']
    discount_value = params['discountValue']
    
    if discount_type == 'percentage':
        # 百分比折扣
        discount_amount = price * (discount_value / 100)
    else:
        # 固定金额折扣
        discount_amount = min(discount_value, price)
    
    final_price = price - discount_amount
    
    return {
        'originalPrice': round(price, 2),
        'discountAmount': round(discount_amount, 2),
        'finalPrice': round(final_price, 2)
    }`
  }
];

// CustomFunctionList
export const customFunctions: CallableFunction[] = [
  {
    name: 'customGreeting',
    desc: '生成Custom问候语',
    params: {
      type: 'object',
      properties: {
        name: {
          type: 'string',
          description: '姓名'
        },
        timeOfDay: {
          type: 'string',
          description: 'Time段',
          enum: ['morning', 'afternoon', 'evening']
        }
      },
      required: ['name', 'timeOfDay']
    },
    returns: {
      type: 'string',
      description: '问候语'
    },
    type: 'custom',
    code: `def custom_greeting(params):
    name = params['name']
    time_of_day = params['timeOfDay']
    
    greetings = {
        'morning': '早上好',
        'afternoon': '下午好',
        'evening': '晚上好'
    }
    
    return f"{greetings[time_of_day]}，{name}！"`
  }
];

// 合并AllFunction
export const allFunctions: CallableFunction[] = [
  ...systemFunctions,
  ...customFunctions
]; 