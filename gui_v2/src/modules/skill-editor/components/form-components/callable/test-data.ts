import { CallableFunction } from '../../../typings/callable';

// 系统函数列表
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
          description: '商品数量'
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
    code: `function calculateTotal(params) {
  const { price, quantity, taxRate } = params;
  
  // 计算不含税总价
  const subtotal = price * quantity;
  
  // 计算税额
  const tax = subtotal * (taxRate / 100);
  
  // 计算含税总价
  const total = subtotal + tax;
  
  return {
    total: Number(total.toFixed(2)),
    tax: Number(tax.toFixed(2))
  };
}`
  },
  {
    name: 'formatDate',
    desc: '格式化日期字符串',
    params: {
      type: 'object',
      properties: {
        date: {
          type: 'string',
          description: '日期字符串'
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
      description: '格式化后的日期字符串'
    },
    type: 'system',
    sysId: 'format_date_v1',
    code: `function formatDate(params) {
  const { date, format } = params;
  const d = new Date(date);
  
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  
  switch (format) {
    case 'YYYY-MM-DD':
      return \`\${year}-\${month}-\${day}\`;
    case 'DD/MM/YYYY':
      return \`\${day}/\${month}/\${year}\`;
    case 'MM/DD/YYYY':
      return \`\${month}/\${day}/\${year}\`;
    default:
      throw new Error('Unsupported date format');
  }
}`
  },
  {
    name: 'validateEmail',
    desc: '验证邮箱地址格式',
    params: {
      type: 'object',
      properties: {
        email: {
          type: 'string',
          description: '邮箱地址'
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
          description: '验证结果说明'
        }
      }
    },
    type: 'system',
    sysId: 'validate_email_v1',
    code: `function validateEmail(params) {
  const { email } = params;
  const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$/;
  
  const isValid = emailRegex.test(email);
  
  return {
    isValid,
    message: isValid ? 'Valid email address' : 'Invalid email format'
  };
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
          description: '折扣类型',
          enum: ['percentage', 'fixed']
        },
        discountValue: {
          type: 'number',
          description: '折扣值（百分比或固定金额）'
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
    code: `function calculateDiscount(params) {
  const { price, discountType, discountValue } = params;
  
  let discountAmount = 0;
  
  if (discountType === 'percentage') {
    // 百分比折扣
    discountAmount = price * (discountValue / 100);
  } else {
    // 固定金额折扣
    discountAmount = Math.min(discountValue, price);
  }
  
  const finalPrice = price - discountAmount;
  
  return {
    originalPrice: Number(price.toFixed(2)),
    discountAmount: Number(discountAmount.toFixed(2)),
    finalPrice: Number(finalPrice.toFixed(2))
  };
}`
  }
];

// 自定义函数列表
export const customFunctions: CallableFunction[] = [
  {
    name: 'customGreeting',
    desc: '生成自定义问候语',
    params: {
      type: 'object',
      properties: {
        name: {
          type: 'string',
          description: '姓名'
        },
        timeOfDay: {
          type: 'string',
          description: '时间段',
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
    code: `function customGreeting(params) {
  const { name, timeOfDay } = params;
  
  const greetings = {
    morning: '早上好',
    afternoon: '下午好',
    evening: '晚上好'
  };
  
  return \`\${greetings[timeOfDay]}，\${name}！\`;
}`
  }
];

// 合并所有函数
export const allFunctions: CallableFunction[] = [
  ...systemFunctions,
  ...customFunctions
]; 