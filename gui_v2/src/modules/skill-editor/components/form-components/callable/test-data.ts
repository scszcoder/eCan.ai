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
    sysId: 'calc_total_v1'
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
    sysId: 'format_date_v1'
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
    sysId: 'validate_email_v1'
  }
];

// 自定义函数示例
export const customFunctions: CallableFunction[] = [
  {
    name: 'calculateDiscount',
    desc: '根据用户等级计算折扣',
    params: {
      type: 'object',
      properties: {
        price: {
          type: 'number',
          description: '原价'
        },
        userLevel: {
          type: 'string',
          description: '用户等级',
          enum: ['normal', 'silver', 'gold', 'platinum']
        }
      },
      required: ['price', 'userLevel']
    },
    returns: {
      type: 'object',
      properties: {
        finalPrice: {
          type: 'number',
          description: '折扣后价格'
        },
        discount: {
          type: 'number',
          description: '折扣金额'
        }
      }
    },
    type: 'custom',
    code: `function calculateDiscount(price, userLevel) {
  const discounts = {
    normal: 0,
    silver: 0.1,
    gold: 0.2,
    platinum: 0.3
  };
  
  const discount = price * (discounts[userLevel] || 0);
  return {
    finalPrice: price - discount,
    discount: discount
  };
}`
  },
  {
    name: 'processOrder',
    desc: '处理订单状态',
    params: {
      type: 'object',
      properties: {
        orderId: {
          type: 'string',
          description: '订单ID'
        },
        status: {
          type: 'string',
          description: '新状态',
          enum: ['pending', 'processing', 'shipped', 'delivered', 'cancelled']
        }
      },
      required: ['orderId', 'status']
    },
    returns: {
      type: 'object',
      properties: {
        success: {
          type: 'boolean',
          description: '是否成功'
        },
        message: {
          type: 'string',
          description: '处理结果'
        },
        timestamp: {
          type: 'string',
          description: '处理时间'
        }
      }
    },
    type: 'custom',
    code: `async function processOrder(orderId, status) {
  try {
    // 模拟数据库操作
    const timestamp = new Date().toISOString();
    
    // 验证状态转换是否合法
    const validTransitions = {
      pending: ['processing', 'cancelled'],
      processing: ['shipped', 'cancelled'],
      shipped: ['delivered'],
      delivered: [],
      cancelled: []
    };
    
    const currentStatus = await getOrderStatus(orderId);
    if (!validTransitions[currentStatus].includes(status)) {
      throw new Error('Invalid status transition');
    }
    
    // 更新订单状态
    await updateOrderStatus(orderId, status);
    
    return {
      success: true,
      message: 'Order status updated successfully',
      timestamp
    };
  } catch (error) {
    return {
      success: false,
      message: error.message,
      timestamp: new Date().toISOString()
    };
  }
}`
  }
];

// 合并所有函数
export const allFunctions: CallableFunction[] = [
  ...systemFunctions,
  ...customFunctions
]; 