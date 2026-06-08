import React from 'react';
import {
  Badge,
  Button,
  Card,
  Input,
  Progress,
  Segmented,
  Slider,
  Space,
  Switch,
  Tag,
  Typography,
  Statistic,
} from 'antd';
import {
  ClockCircleOutlined,
  MessageOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  SendOutlined,
  CopyOutlined,
  UserOutlined,
  MailOutlined,
  ShopOutlined,
  GlobalOutlined,
  HistoryOutlined,
  CrownOutlined,
  FireOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import styled from '@emotion/styled';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

type SessionStatus = 'urgent' | 'active' | 'waiting' | 'resolved';
type ScenarioMode = 'normal' | 'burst' | 'refund_wave' | 'multilingual';
type KnowledgeSource = 'faq' | 'rag' | 'db';
type Channel = 'Shopify' | 'Amazon' | 'eBay' | 'WhatsApp' | 'Web';
type AccountTier = 'Standard' | 'Premium' | 'VIP';
type Locale = 'en' | 'zh';
type Intent = 'shipping' | 'refund' | 'product';

interface Customer {
  id: string;
  name: string;
  email: string;
  locale: Locale;
  channel: Channel;
  accountTier: AccountTier;
  previousTickets: number;
}

interface SupportSession {
  id: string;
  customer: Customer;
  status: SessionStatus;
  priority: 'low' | 'medium' | 'high';
  unreadCount: number;
  waitingSeconds: number;
  orderId: string;
  lastMessage: string;
  lastMessageAt: number;
  intent: Intent;
  slaSeconds: number;
}

interface SupportMessage {
  id: string;
  sessionId: string;
  sender: 'customer' | 'agent' | 'system';
  content: string;
  timestamp: number;
}

interface KnowledgeHit {
  id: string;
  source: KnowledgeSource;
  title: string;
  content: string;
  score: number;
}

interface TimelineEvent {
  id: string;
  sessionId: string;
  label: string;
  timestamp: number;
  type: 'incoming' | 'auto_reply' | 'lookup' | 'manual_reply' | 'session_switch' | 'sla_warning' | 'escalation';
}

interface Metrics {
  concurrentSessions: number;
  autoRepliesSent: number;
  knowledgeLookups: number;
  avgReplyLatencyMs: number;
}

// ============================================================================
// MOCK DATA
// ============================================================================

const LOCALE_FLAGS: Record<Locale, string> = {
  en: '🇺🇸',
  zh: '🇨🇳',
};

const CHANNEL_COLORS: Record<Channel, string> = {
  Shopify: '#96bf48',
  Amazon: '#ff9900',
  eBay: '#e53238',
  WhatsApp: '#25d366',
  Web: '#3b82f6',
};

const ENGLISH_MESSAGES: Record<Intent, string[]> = {
  shipping: [
    'Where is my package now? It was supposed to arrive 3 days ago.',
    'My tracking hasn\'t updated in 5 days. Can you check?',
    'Can I change my delivery address?',
    'The delivery person left without delivering my order.',
    'I need to schedule a redelivery.',
    'My package shows delivered but I didn\'t receive anything.',
    'How long does standard shipping take to California?',
    'Is there express shipping available for my order?',
    'Package arrived damaged, need help with replacement.',
    'Can I track my order with the tracking number?',
    'Delivery was attempted but nobody was home.',
    'Need to update shipping address before it ships.',
    'Order says delivered but mailbox is empty.',
    'When will my order be shipped?',
    'Can I pick up my order at the warehouse?',
  ],
  refund: [
    'I received a damaged item. Can I get a full refund?',
    'The product is different from what was shown on the website.',
    'I want to return this item and get my money back.',
    'Can I get a partial refund for my order?',
    'I never received my refund. It\'s been 10 days.',
    'The item doesn\'t fit. I\'d like to exchange or refund.',
    'My item arrived broken. Requesting immediate refund.',
    'I want to cancel my order and get a refund.',
    'Wrong item was sent. Need refund ASAP.',
    'Product stopped working after 2 days.',
    'Package was opened and item was missing.',
    'Item quality is very poor, requesting refund.',
    'I want to cancel before it ships.',
    'Need refund for duplicate charge.',
    'Refund status shows pending for 2 weeks.',
  ],
  product: [
    'Do you have this item in size M?',
    'Is this product available in blue?',
    'What sizes are available for this shirt?',
    'Can you check if size L is in stock?',
    'I\'m looking for the wireless headphones you sell.',
    'Does this come with a warranty?',
    'What\'s the battery life of this product?',
    'Are there any discounts on bulk orders?',
    'Is this the latest model?',
    'Can I see more photos of this product?',
    'What colors does this come in?',
    'Is this item eco-friendly?',
    'Does this have free returns?',
    'What materials is this made of?',
    'Is there a size guide for this product?',
  ],
};

const CHINESE_MESSAGES: Record<Intent, string[]> = {
  shipping: [
    '我的包裹现在到哪里了？已经等了5天了。',
    '物流信息好几天没更新了，能帮我查一下吗？',
    '我可以修改收货地址吗？',
    '快递员没打电话就直接把包裹放在门口了。',
    '需要预约重新派送。',
    '物流显示已签收，但我没收到。',
    '标准配送到北京需要多久？',
    '有没有加急配送的选项？',
    '收到的包裹破损了，需要帮助处理。',
    '可以用快递单号查一下物流吗？',
    '派送时家里没人。',
    '发货前需要修改地址。',
    '显示已签收但我没收到件。',
    '订单什么时候能发货？',
    '可以自己去仓库提货吗？',
  ],
  refund: [
    '收到的商品有破损，可以全额退款吗？',
    '实物和网站上展示的不一样。',
    '我想退货并退款。',
    '可以给我部分退款吗？',
    '退款申请已经10天了，钱还没到账。',
    '尺码不合适，想要换货或退款。',
    '收到的东西坏了，要求立即退款。',
    '我要取消订单并退款。',
    '发错货了，请尽快处理退款。',
    '产品用了2天就坏了。',
    '包裹被拆开，里面的东西少了。',
    '商品质量很差，要求退款。',
    '想在发货前取消订单。',
    '被重复扣款了，需要退款。',
    '退款状态显示pending两周了。',
  ],
  product: [
    '这件商品有M码吗？',
    '这个产品有蓝色的吗？',
    '这款衬衫有哪些尺码可选？',
    '能帮我查一下L码有没有货吗？',
    '我想找你们卖的无线耳机。',
    '这个有保修期吗？',
    '这个产品的电池续航是多久？',
    '批量购买有折扣吗？',
    '这是最新款吗？',
    '能发一下这个产品的更多照片吗？',
    '这个产品有哪些颜色？',
    '这个是环保产品吗？',
    '这个可以免费退货吗？',
    '这个是什么材质做的？',
    '有这款产品的尺码表吗？',
  ],
};

const AGENT_REPLIES_ENGLISH: Record<Intent, string[]> = [
  'I\'ve checked your order status. Your package is currently at the regional sorting center and should arrive within 2-3 business days.',
  'Let me look into your tracking information. It appears there was a delay due to weather conditions in your area.',
  'Your package is out for delivery today. Please ensure someone is available to receive it.',
  'I\'ve updated your delivery address. The new estimated delivery date is shown in your order details.',
  'I\'ve reviewed your case and approved a full refund. You should see the credit within 5-7 business days.',
  'Our refund team is processing your request. Standard processing time is 3-5 business days after approval.',
  'I\'ve escalated your refund case to our finance team for priority processing.',
  'Your refund has been processed. Please check your original payment method within 3-5 days.',
  'Size M is currently in stock. Would you like me to reserve one for you?',
  'I\'ve checked our inventory system. The blue variant is available and ready to ship.',
  'Based on our stock system, here are the available sizes: S, M, L, XL. Which would you prefer?',
  'This product comes with a 12-month manufacturer warranty. Would you like more details?',
];

const AGENT_REPLIES_CHINESE: Record<Intent, string[]> = [
  '我已经查询了您的订单状态。您的包裹目前在区域分拣中心，预计2-3个工作日内送达。',
  '让我帮您查看物流信息。由于您所在地区天气原因，包裹有些延误。',
  '您的包裹今天正在派送中。请确保有人在家接收。',
  '我已经更新了您的收货地址。新的预计送达日期已显示在订单详情中。',
  '我已经审核了您的情况，批准了全额退款。款项将在5-7个工作日内到账。',
  '我们的退款团队正在处理您的请求。标准处理时间为审批后3-5个工作日。',
  '我已经将您的退款案例转交给财务团队优先处理。',
  '您的退款已处理完毕。请在3-5天内查看您的原始支付账户。',
  'M码目前有货。需要我帮您预留一件吗？',
  '我已经查了库存系统。蓝色款有货，可以立即发货。',
  '根据我们的库存系统，以下是可选尺码：S、M、L、XL。请问您想要哪个？',
  '此产品享有12个月厂家保修。需要了解更多详情吗？',
];

const KNOWLEDGE_LIBRARY: Record<Intent, KnowledgeHit[]> = {
  shipping: [
    { id: 'faq-ship-1', source: 'faq', title: 'Standard Shipping Policy', content: 'Standard shipping updates within 24 hours. Delivery typically takes 5-7 business days for domestic orders.', score: 0.96 },
    { id: 'rag-ship-1', source: 'rag', title: 'Delay Pattern Analysis', content: 'Carrier scans may batch update during weekends. Tracking usually resumes Monday morning.', score: 0.89 },
    { id: 'db-ship-1', source: 'db', title: 'Regional Hub Status', content: 'Order is at Pacific Northwest Hub. Current backlog: 12 hours. Estimated departure: tomorrow AM.', score: 0.94 },
  ],
  refund: [
    { id: 'faq-refund-1', source: 'faq', title: 'Refund Processing SLA', content: 'Refunds are processed within 3-5 business days after approval. Bank processing may add 2-3 days.', score: 0.97 },
    { id: 'db-refund-1', source: 'db', title: 'Refund Case Status', content: 'Case #RF-2847 is currently in Finance queue. Expected approval within 24 hours.', score: 0.91 },
    { id: 'rag-refund-1', source: 'rag', title: 'Partial Refund Policy', content: 'Partial refunds are considered for items with minor defects. Assessment takes 1-2 business days.', score: 0.85 },
  ],
  product: [
    { id: 'faq-prod-1', source: 'faq', title: 'Size Availability Guide', content: 'Alternative size suggestions are based on latest inventory snapshot. Stock updates every 30 minutes.', score: 0.94 },
    { id: 'db-prod-1', source: 'db', title: 'Real-time Inventory Check', content: 'Size M in Black: 12 units available. Size L in Black: 3 units available. Size XL: Out of stock.', score: 0.96 },
    { id: 'rag-prod-1', source: 'rag', title: 'Fit Recommendation Engine', content: 'Based on similar customer feedback, customers typically size up for this product line.', score: 0.79 },
  ],
};

const SUGGESTED_REPLIES: Record<Locale, string[]> = {
  en: [
    'I\'ve checked your tracking and found your package. It will arrive soon.',
    'Your refund has been approved and is being processed.',
    'Good news! This item is available in your preferred size.',
    'Let me look into this for you right away.',
    'Is there anything else I can help you with today?',
  ],
  zh: [
    '我已经查询了您的物流信息，包裹正在派送中。',
    '您的退款申请已批准，正在处理中。',
    '好消息！您要的尺码我们还有货。',
    '让我立即帮您查看这个问题。',
    '还有其他我可以帮您的吗？',
  ],
};

const SEED_CUSTOMERS: Customer[] = [
  { id: 'cust-1', name: 'Emma Johnson', email: 'emma.johnson@gmail.com', locale: 'en', channel: 'Shopify', accountTier: 'VIP', previousTickets: 8 },
  { id: 'cust-2', name: 'Liam Brown', email: 'liam.brown@yahoo.com', locale: 'en', channel: 'Amazon', accountTier: 'Premium', previousTickets: 3 },
  { id: 'cust-3', name: 'Olivia Davis', email: 'olivia.davis@outlook.com', locale: 'en', channel: 'Web', accountTier: 'Standard', previousTickets: 1 },
  { id: 'cust-4', name: '王小雨', email: 'xiaoyu.wang@qq.com', locale: 'zh', channel: 'eBay', accountTier: 'Premium', previousTickets: 5 },
  { id: 'cust-5', name: '陈明', email: 'chen.ming@163.com', locale: 'zh', channel: 'WhatsApp', accountTier: 'VIP', previousTickets: 12 },
  { id: 'cust-6', name: 'Sophia Miller', email: 'sophia.m@gmail.com', locale: 'en', channel: 'Shopify', accountTier: 'Standard', previousTickets: 2 },
  { id: 'cust-7', name: 'Lucas Wilson', email: 'lucas.wilson@hotmail.com', locale: 'en', channel: 'Amazon', accountTier: 'Premium', previousTickets: 4 },
  { id: 'cust-8', name: '赵可欣', email: 'kexin.zhao@gmail.com', locale: 'zh', channel: 'Web', accountTier: 'Standard', previousTickets: 0 },
];

const SCENARIO_OPTIONS: Array<{ label: string; value: ScenarioMode }> = [
  { label: 'Normal Traffic', value: 'normal' },
  { label: 'Promo Burst', value: 'burst' },
  { label: 'Refund Wave', value: 'refund_wave' },
  { label: 'Mixed Languages', value: 'multilingual' },
];

const INTENT_TAGS: Record<Intent, string> = {
  shipping: 'shipping',
  refund: 'refund',
  product: 'product',
};

const EVENT_LABELS: Record<TimelineEvent['type'], string> = {
  incoming: 'incoming message',
  auto_reply: 'auto reply sent',
  lookup: 'knowledge lookup',
  manual_reply: 'agent reply',
  session_switch: 'session switched',
  sla_warning: 'SLA warning',
  escalation: 'escalated',
};

// ============================================================================
// STYLED COMPONENTS
// ============================================================================

const Page = styled.div`
  min-height: 100vh;
  padding: 20px;
  background: linear-gradient(180deg, #020617 0%, #0f172a 100%);
  color: #e5e7eb;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
`;

const ControlBar = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 16px;
`;

const ControlBarLeft = styled.div``;

const ControlBarRight = styled.div`
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
`;

const SliderLabel = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  color: #cbd5e1;
`;

const MetricsRow = styled.div`
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
`;

const MetricCard = styled(Card)`
  background: rgba(15, 23, 42, 0.88) !important;
  border: 1px solid rgba(148, 163, 184, 0.16) !important;
  border-radius: 12px;
  
  .ant-card-head {
    border-bottom-color: rgba(148, 163, 184, 0.16) !important;
    color: #e5e7eb;
  }
  
  .ant-card-body {
    color: #e5e7eb;
  }
  
  .ant-statistic-title {
    color: #94a3b8 !important;
  }
  
  .ant-statistic-content {
    color: #f8fafc !important;
  }
`;

const MainContent = styled.div`
  display: grid;
  grid-template-columns: 320px 1fr 340px;
  gap: 16px;
  align-items: start;
`;

const SessionPoolCard = styled(Card)`
  height: 100%;
  background: rgba(15, 23, 42, 0.88) !important;
  border: 1px solid rgba(148, 163, 184, 0.16) !important;
  border-radius: 12px;
  
  .ant-card-head {
    border-bottom-color: rgba(148, 163, 184, 0.16) !important;
    color: #e5e7eb;
  }
`;

const SessionTabs = styled.div`
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
  background: rgba(30, 41, 59, 0.5);
  padding: 4px;
  border-radius: 8px;
`;

const SessionTab = styled.button<{ $active: boolean; $status: SessionStatus }>`
  flex: 1;
  padding: 8px 12px;
  border: none;
  border-radius: 6px;
  background: ${({ $active }) => ($active ? 'rgba(59, 130, 246, 0.8)' : 'transparent')};
  color: ${({ $active }) => ($active ? '#fff' : '#94a3b8')};
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.2s;
  
  &:hover {
    background: ${({ $active }) => ($active ? 'rgba(59, 130, 246, 0.8)' : 'rgba(148, 163, 184, 0.2)')};
  }
`;

const TabBadge = styled.span<{ $count: number }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  margin-left: 4px;
  border-radius: 9px;
  background: ${({ $count }) => ($count > 0 ? '#ef4444' : '#64748b')};
  color: white;
  font-size: 10px;
  font-weight: 600;
`;

const SessionList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 600px;
  overflow-y: auto;
  
  &::-webkit-scrollbar {
    width: 6px;
  }
  
  &::-webkit-scrollbar-track {
    background: rgba(30, 41, 59, 0.3);
    border-radius: 3px;
  }
  
  &::-webkit-scrollbar-thumb {
    background: rgba(148, 163, 184, 0.3);
    border-radius: 3px;
  }
`;

const SessionItem = styled.button<{ $active: boolean }>`
  width: 100%;
  text-align: left;
  border-radius: 10px;
  padding: 12px;
  border: 1px solid ${({ $active }) => ($active ? 'rgba(59, 130, 246, 0.8)' : 'rgba(148, 163, 184, 0.16)')};
  background: ${({ $active }) => ($active ? 'rgba(30, 58, 138, 0.4)' : 'rgba(15, 23, 42, 0.75)')};
  cursor: pointer;
  color: inherit;
  transition: all 0.2s;
  
  &:hover {
    border-color: rgba(59, 130, 246, 0.5);
    background: ${({ $active }) => ($active ? 'rgba(30, 58, 138, 0.4)' : 'rgba(30, 41, 59, 0.8)')};
  }
`;

const SessionHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
`;

const CustomerInfo = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

const CustomerAvatar = styled.div<{ $color: string }>`
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: ${({ $color }) => $color};
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: white;
`;

const CustomerName = styled(Text)`
  font-weight: 600;
  color: #f8fafc !important;
`;

const LocaleFlag = styled.span`
  font-size: 14px;
`;

const SessionMeta = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
`;

const ChannelBadge = styled(Tag)`
  font-size: 10px;
  padding: 0 6px;
  height: 18px;
  line-height: 16px;
`;

const PriorityBadge = styled(Tag)<{ $priority: 'low' | 'medium' | 'high' }>`
  font-size: 10px;
  padding: 0 6px;
  height: 18px;
  line-height: 16px;
  background: ${({ $priority }) =>
    $priority === 'high' ? '#dc2626' : $priority === 'medium' ? '#d97706' : '#2563eb'};
  border: none;
  color: white;
`;

const SessionPreview = styled(Text)`
  display: block;
  color: #cbd5e1 !important;
  font-size: 12px;
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
`;

const SessionFooter = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: #64748b;
`;

const SLATimer = styled.span<{ $level: 'green' | 'yellow' | 'red' }>`
  color: ${({ $level }) =>
    $level === 'red' ? '#ef4444' : $level === 'yellow' ? '#eab308' : '#22c55e'};
  font-weight: 500;
`;

const ConversationCard = styled(Card)`
  height: 100%;
  background: rgba(15, 23, 42, 0.88) !important;
  border: 1px solid rgba(148, 163, 184, 0.16) !important;
  border-radius: 12px;
  
  .ant-card-head {
    border-bottom-color: rgba(148, 163, 184, 0.16) !important;
    color: #e5e7eb;
  }
`;

const ConversationHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
`;

const CustomerProfile = styled.div`
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  padding: 12px;
  margin-bottom: 12px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 8px;
`;

const ProfileItem = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #cbd5e1;
`;

const ProfileLabel = styled.span`
  color: #64748b;
`;

const ProfileValue = styled.span`
  color: #f8fafc;
  font-weight: 500;
`;

const TierBadge = styled(Tag)<{ $tier: AccountTier }>`
  background: ${({ $tier }) =>
    $tier === 'VIP' ? '#7c3aed' : $tier === 'Premium' ? '#0891b2' : '#64748b'};
  border: none;
  color: white;
`;

const MessageColumn = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 380px;
  max-height: 380px;
  overflow-y: auto;
  padding: 12px;
  background: rgba(15, 23, 42, 0.5);
  border-radius: 8px;
  margin-bottom: 12px;
  
  &::-webkit-scrollbar {
    width: 6px;
  }
  
  &::-webkit-scrollbar-track {
    background: rgba(30, 41, 59, 0.3);
    border-radius: 3px;
  }
  
  &::-webkit-scrollbar-thumb {
    background: rgba(148, 163, 184, 0.3);
    border-radius: 3px;
  }
`;

const MessageBubble = styled.div<{ $sender: 'customer' | 'agent' | 'system' }>`
  align-self: ${({ $sender }) => ($sender === 'customer' ? 'flex-start' : 'flex-end')};
  max-width: 80%;
  min-width: 200px;
  border-radius: 14px;
  padding: 12px 14px;
  background: ${({ $sender }) =>
    $sender === 'customer'
      ? '#1e293b'
      : $sender === 'system'
        ? '#581c87'
        : '#1d4ed8'};
  border: 1px solid ${({ $sender }) =>
    $sender === 'customer'
      ? 'rgba(148, 163, 184, 0.16)'
      : $sender === 'system'
        ? 'rgba(168, 85, 247, 0.3)'
        : 'rgba(96, 165, 250, 0.3)'};
`;

const MessageHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  font-size: 11px;
`;

const MessageSender = styled.span`
  color: #94a3b8;
  font-weight: 500;
`;

const MessageTime = styled.span`
  color: #64748b;
`;

const MessageContent = styled.div`
  color: #f8fafc;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
`;

const ReplyArea = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const ReplyHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`;

const CharCount = styled.span<{ $exceeded: boolean }>`
  font-size: 11px;
  color: ${({ $exceeded }) => ($exceeded ? '#ef4444' : '#64748b')};
`;

const SuggestedReplies = styled.div`
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 8px 0;
  
  &::-webkit-scrollbar {
    height: 4px;
  }
  
  &::-webkit-scrollbar-track {
    background: rgba(30, 41, 59, 0.3);
    border-radius: 2px;
  }
  
  &::-webkit-scrollbar-thumb {
    background: rgba(148, 163, 184, 0.3);
    border-radius: 2px;
  }
`;

const SuggestedReplyButton = styled.button`
  flex-shrink: 0;
  padding: 6px 12px;
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 16px;
  background: rgba(30, 41, 59, 0.6);
  color: #cbd5e1;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  
  &:hover {
    border-color: rgba(59, 130, 246, 0.6);
    background: rgba(59, 130, 246, 0.2);
    color: #f8fafc;
  }
`;

const RightPanel = styled.div`
  display: flex;
  flex-direction: column;
  gap: 16px;
`;

const KnowledgeCard = styled(Card)`
  background: rgba(15, 23, 42, 0.88) !important;
  border: 1px solid rgba(148, 163, 184, 0.16) !important;
  border-radius: 12px;
  
  .ant-card-head {
    border-bottom-color: rgba(148, 163, 184, 0.16) !important;
    color: #e5e7eb;
  }
`;

const KnowledgeList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 300px;
  overflow-y: auto;
  
  &::-webkit-scrollbar {
    width: 6px;
  }
  
  &::-webkit-scrollbar-track {
    background: rgba(30, 41, 59, 0.3);
    border-radius: 3px;
  }
  
  &::-webkit-scrollbar-thumb {
    background: rgba(148, 163, 184, 0.3);
    border-radius: 3px;
  }
`;

const KnowledgeItem = styled.div`
  padding: 12px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.16);
`;

const KnowledgeHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
`;

const SourceBadge = styled(Tag)<{ $source: KnowledgeSource }>`
  background: ${({ $source }) =>
    $source === 'faq' ? '#3b82f6' : $source === 'rag' ? '#7c3aed' : '#16a34a'};
  border: none;
  color: white;
  font-size: 10px;
`;

const ScoreText = styled.span`
  font-size: 12px;
  color: #94a3b8;
  font-weight: 500;
`;

const KnowledgeTitle = styled.div`
  font-weight: 600;
  color: #f8fafc;
  margin-bottom: 6px;
  font-size: 13px;
`;

const KnowledgeContent = styled(Paragraph)`
  color: #cbd5e1 !important;
  font-size: 12px !important;
  margin-bottom: 8px !important;
  line-height: 1.4 !important;
`;

const KnowledgeActions = styled.div`
  display: flex;
  gap: 8px;
`;

const TimelineCard = styled(Card)`
  background: rgba(15, 23, 42, 0.88) !important;
  border: 1px solid rgba(148, 163, 184, 0.16) !important;
  border-radius: 12px;
  
  .ant-card-head {
    border-bottom-color: rgba(148, 163, 184, 0.16) !important;
    color: #e5e7eb;
  }
`;

const TimelineList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 280px;
  overflow-y: auto;
  
  &::-webkit-scrollbar {
    width: 6px;
  }
  
  &::-webkit-scrollbar-track {
    background: rgba(30, 41, 59, 0.3);
    border-radius: 3px;
  }
  
  &::-webkit-scrollbar-thumb {
    background: rgba(148, 163, 184, 0.3);
    border-radius: 3px;
  }
`;

const TimelineItem = styled.div<{ $type: TimelineEvent['type'] }>`
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(30, 41, 59, 0.6);
  border-left: 3px solid ${({ $type }) =>
    $type === 'incoming' ? '#3b82f6' :
    $type === 'auto_reply' ? '#8b5cf6' :
    $type === 'lookup' ? '#f59e0b' :
    $type === 'manual_reply' ? '#22c55e' :
    $type === 'session_switch' ? '#06b6d4' :
    $type === 'sla_warning' ? '#ef4444' :
    '#f97316'};
`;

const TimelineTime = styled.span`
  font-size: 10px;
  color: #64748b;
  margin-right: 8px;
`;

const TimelineLabel = styled.span`
  font-size: 12px;
  color: #e2e8f0;
`;

const EmptyState = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  color: #64748b;
`;

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

const formatTime = (ts: number): string => new Date(ts).toLocaleTimeString('en-US', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

const getAvatarColor = (name: string): string => {
  const colors = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#06b6d4', '#f43f5e'];
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
};

const getInitials = (name: string): string => {
  const parts = name.split(' ');
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
};

const getSLALevel = (seconds: number): 'green' | 'yellow' | 'red' => {
  if (seconds <= 30) return 'red';
  if (seconds <= 60) return 'yellow';
  return 'green';
};

const generateOrderId = (): string => {
  const num = Math.floor(Math.random() * 9000) + 1000;
  return `EC-${num}`;
};

const generateSessionId = (): string => {
  return `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
};

const generateMessageId = (sessionId: string, prefix: string): string => {
  return `${sessionId}-${prefix}-${Date.now()}`;
};

// ============================================================================
// INITIAL STATE BUILDERS
// ============================================================================

function buildInitialSessions(): SupportSession[] {
  return SEED_CUSTOMERS.slice(0, 8).map((customer, index) => ({
    id: `session-${index + 1}`,
    customer,
    status: (['urgent', 'urgent', 'active', 'active', 'active', 'waiting', 'waiting', 'resolved'] as SessionStatus[])[index],
    priority: (['high', 'high', 'medium', 'medium', 'medium', 'low', 'low', 'low'] as ('low' | 'medium' | 'high')[])[index],
    unreadCount: index % 3,
    waitingSeconds: 10 + index * 8,
    orderId: `EC-${1200 + index}`,
    lastMessage: customer.locale === 'zh'
      ? CHINESE_MESSAGES.shipping[index % CHINESE_MESSAGES.shipping.length]
      : ENGLISH_MESSAGES.shipping[index % ENGLISH_MESSAGES.shipping.length],
    lastMessageAt: Date.now() - index * 60000,
    intent: (['shipping', 'refund', 'product'] as Intent[])[index % 3],
    slaSeconds: 120 - index * 10,
  }));
}

function buildInitialMessages(sessions: SupportSession[]): Record<string, SupportMessage[]> {
  const messages: Record<string, SupportMessage[]> = {};

  sessions.forEach((session, index) => {
    const ts = session.lastMessageAt;
    messages[session.id] = [
      {
        id: `${session.id}-sys-1`,
        sessionId: session.id,
        sender: 'system',
        content: `Session created for ${session.customer.name} via ${session.customer.channel}`,
        timestamp: ts - 180000,
      },
      {
        id: `${session.id}-cust-1`,
        sessionId: session.id,
        sender: 'customer',
        content: session.lastMessage,
        timestamp: ts - 60000,
      },
    ];

    if (session.unreadCount > 0) {
      const secondMsg = session.customer.locale === 'zh'
        ? CHINESE_MESSAGES[session.intent][(index + 1) % CHINESE_MESSAGES[session.intent].length]
        : ENGLISH_MESSAGES[session.intent][(index + 1) % ENGLISH_MESSAGES[session.intent].length];
      messages[session.id].push({
        id: `${session.id}-cust-2`,
        sessionId: session.id,
        sender: 'customer',
        content: secondMsg,
        timestamp: ts,
      });
    }
  });

  return messages;
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

const App: React.FC = () => {
  // State
  const [scenario, setScenario] = React.useState<ScenarioMode>('normal');
  const [running, setRunning] = React.useState(true);
  const [autoReply, setAutoReply] = React.useState(true);
  const [maxConcurrent, setMaxConcurrent] = React.useState(8);
  const [activeTab, setActiveTab] = React.useState<SessionStatus>('active');
  const [sessions, setSessions] = React.useState<SupportSession[]>(() => buildInitialSessions());
  const [messagesBySession, setMessagesBySession] = React.useState<Record<string, SupportMessage[]>>(() =>
    buildInitialMessages(buildInitialSessions())
  );
  const [activeSessionId, setActiveSessionId] = React.useState<string>('');
  const [draftReply, setDraftReply] = React.useState('');
  const [timeline, setTimeline] = React.useState<TimelineEvent[]>([]);
  const [metrics, setMetrics] = React.useState<Metrics>({
    concurrentSessions: 0,
    autoRepliesSent: 0,
    knowledgeLookups: 0,
    avgReplyLatencyMs: 0,
  });
  const [replyLatencies, setReplyLatencies] = React.useState<number[]>([]);

  // Derived state
  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? sessions[0];
  const activeMessages = activeSession ? (messagesBySession[activeSession.id] ?? []) : [];
  const knowledgeHits = activeSession ? (KNOWLEDGE_LIBRARY[activeSession.intent] ?? KNOWLEDGE_LIBRARY.shipping) : KNOWLEDGE_LIBRARY.shipping;

  const sessionsByStatus = React.useMemo(() => {
    const filtered: SessionStatus[] = ['urgent', 'active', 'waiting', 'resolved'];
    return Object.fromEntries(
      filtered.map((status) => [status, sessions.filter((s) => s.status === status)])
    ) as Record<SessionStatus, SupportSession[]>;
  }, [sessions]);

  const activeCount = sessions.filter((s) => s.status === 'urgent' || s.status === 'active').length;

  // Initialize active session
  React.useEffect(() => {
    if (!activeSessionId && sessions.length > 0) {
      setActiveSessionId(sessions[0].id);
    }
  }, [sessions, activeSessionId]);

  // Update metrics when sessions change
  React.useEffect(() => {
    setMetrics((prev) => ({
      ...prev,
      concurrentSessions: activeCount,
    }));
  }, [activeCount]);

  // Calculate average latency
  const avgLatency = React.useMemo(() => {
    if (replyLatencies.length === 0) return 0;
    return Math.round(replyLatencies.reduce((a, b) => a + b, 0) / replyLatencies.length);
  }, [replyLatencies]);

  // Update avg latency metric
  React.useEffect(() => {
    if (avgLatency > 0) {
      setMetrics((prev) => ({
        ...prev,
        avgReplyLatencyMs: avgLatency,
      }));
    }
  }, [avgLatency]);

  // Get random message helper
  const getRandomIntent = React.useCallback((currentScenario: ScenarioMode): Intent => {
    if (currentScenario === 'refund_wave') return 'refund';
    const intents: Intent[] = ['shipping', 'refund', 'product'];
    return intents[Math.floor(Math.random() * intents.length)];
  }, []);

  const getRandomLocale = React.useCallback((currentScenario: ScenarioMode, defaultLocale: Locale): Locale => {
    if (currentScenario === 'multilingual') {
      return Math.random() > 0.5 ? 'zh' : 'en';
    }
    return defaultLocale;
  }, []);

  const getRandomMessage = React.useCallback((intent: Intent, locale: Locale): string => {
    const pool = locale === 'zh' ? CHINESE_MESSAGES : ENGLISH_MESSAGES;
    const messages = pool[intent];
    return messages[Math.floor(Math.random() * messages.length)];
  }, []);

  const getRandomAgentReply = React.useCallback((intent: Intent, locale: Locale): string => {
    const pool = locale === 'zh' ? AGENT_REPLIES_CHINESE : AGENT_REPLIES_ENGLISH;
    const replies = pool[intent];
    return replies[Math.floor(Math.random() * replies.length)];
  }, []);

  // Concurrent message injection engine
  React.useEffect(() => {
    if (!running) return;

    const getIntervalMs = () => {
      switch (scenario) {
        case 'burst': return 800;
        case 'normal': return 1500;
        case 'refund_wave': return 1500;
        case 'multilingual': return 1500;
        default: return 1500;
      }
    };

    const intervalMs = getIntervalMs();
    let timeoutId: ReturnType<typeof setTimeout>;

    const injectMessage = () => {
      if (sessions.length === 0) return;

      const eligibleSessions = sessions.filter(s => s.status !== 'resolved');
      if (eligibleSessions.length === 0) return;

      const targetIndex = Math.floor(Math.random() * Math.min(eligibleSessions.length, maxConcurrent));
      const targetSession = eligibleSessions[targetIndex];
      if (!targetSession) return;

      const intent = getRandomIntent(scenario);
      const locale = getRandomLocale(scenario, targetSession.customer.locale);
      const content = getRandomMessage(intent, locale);
      const ts = Date.now();

      // Update session
      setSessions((prev) =>
        prev.map((session) => {
          if (session.id !== targetSession.id) {
            return {
              ...session,
              waitingSeconds: session.waitingSeconds + 1,
            };
          }
          return {
            ...session,
            intent,
            lastMessage: content,
            lastMessageAt: ts,
            unreadCount: session.id === activeSessionId ? 0 : session.unreadCount + 1,
            waitingSeconds: 0,
            slaSeconds: 120,
            status: session.priority === 'high' || scenario === 'burst' ? 'urgent' :
              session.status === 'waiting' ? 'active' : session.status,
          };
        })
      );

      // Add message
      const newMessage: SupportMessage = {
        id: generateMessageId(targetSession.id, 'cust'),
        sessionId: targetSession.id,
        sender: 'customer',
        content,
        timestamp: ts,
      };

      setMessagesBySession((prev) => ({
        ...prev,
        [targetSession.id]: [...(prev[targetSession.id] ?? []), newMessage],
      }));

      // Add timeline event
      const newEvent: TimelineEvent = {
        id: `evt-${ts}`,
        sessionId: targetSession.id,
        label: `${targetSession.customer.name}: ${EVENT_LABELS.incoming} (${intent})`,
        timestamp: ts,
        type: 'incoming',
      };

      setTimeline((prev) => [newEvent, ...prev].slice(0, 20));
    };

    const runInjection = () => {
      injectMessage();
      const nextInterval = scenario === 'burst' && Math.random() > 0.5 ? 400 : intervalMs;
      timeoutId = setTimeout(runInjection, nextInterval);
    };

    timeoutId = setTimeout(runInjection, intervalMs);

    return () => clearTimeout(timeoutId);
  }, [running, scenario, sessions.length, maxConcurrent, activeSessionId, getRandomIntent, getRandomLocale, getRandomMessage]);

  // SLA countdown
  React.useEffect(() => {
    const timer = setInterval(() => {
      setSessions((prev) =>
        prev.map((session) => {
          if (session.status === 'resolved' || session.waitingSeconds === 0) return session;
          
          const newSla = Math.max(0, session.slaSeconds - 1);
          
          // Auto-escalate if waiting too long
          if (session.waitingSeconds > 120 && session.status !== 'urgent') {
            setTimeline((prev) => [{
              id: `escalate-${Date.now()}`,
              sessionId: session.id,
              label: `${session.customer.name}: ${EVENT_LABELS.escalation}`,
              timestamp: Date.now(),
              type: 'escalation',
            }, ...prev].slice(0, 20));
            
            return { ...session, slaSeconds: newSla, status: 'urgent' as SessionStatus };
          }
          
          // SLA warning
          if (newSla === 30 && session.status !== 'resolved') {
            setTimeline((prev) => [{
              id: `sla-${Date.now()}`,
              sessionId: session.id,
              label: `${session.customer.name}: ${EVENT_LABELS.sla_warning}`,
              timestamp: Date.now(),
              type: 'sla_warning',
            }, ...prev].slice(0, 20));
          }
          
          return { ...session, slaSeconds: newSla };
        })
      );
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  // Auto-reply engine
  React.useEffect(() => {
    if (!autoReply || !activeSession) return;

    const latestMessage = activeMessages[activeMessages.length - 1];
    if (!latestMessage || latestMessage.sender !== 'customer') return;

    const replyDelay = 800 + Math.random() * 400;
    const replyTimer = setTimeout(() => {
      const intent = activeSession.intent;
      const locale = activeSession.customer.locale;
      const content = getRandomAgentReply(intent, locale);
      const ts = Date.now();

      // Record latency
      const latency = ts - latestMessage.timestamp;
      setReplyLatencies((prev) => [...prev.slice(-19), latency]);

      // Add reply message
      const replyMessage: SupportMessage = {
        id: generateMessageId(activeSession.id, 'agent'),
        sessionId: activeSession.id,
        sender: 'agent',
        content,
        timestamp: ts,
      };

      setMessagesBySession((prev) => ({
        ...prev,
        [activeSession.id]: [...(prev[activeSession.id] ?? []), replyMessage],
      }));

      // Update metrics
      setMetrics((prev) => ({
        ...prev,
        autoRepliesSent: prev.autoRepliesSent + 1,
        knowledgeLookups: prev.knowledgeLookups + 1,
      }));

      // Update session
      setSessions((prev) =>
        prev.map((session) =>
          session.id === activeSession.id
            ? { ...session, status: 'active', unreadCount: 0, lastMessage: content, lastMessageAt: ts }
            : session
        )
      );

      // Add timeline events
      const lookupEvent: TimelineEvent = {
        id: `lookup-${ts}`,
        sessionId: activeSession.id,
        label: `${activeSession.customer.name}: ${EVENT_LABELS.lookup} hit`,
        timestamp: ts - 200,
        type: 'lookup',
      };

      const replyEvent: TimelineEvent = {
        id: `reply-${ts}`,
        sessionId: activeSession.id,
        label: `${activeSession.customer.name}: ${EVENT_LABELS.auto_reply}`,
        timestamp: ts,
        type: 'auto_reply',
      };

      setTimeline((prev) => [replyEvent, lookupEvent, ...prev].slice(0, 20));

    }, replyDelay);

    return () => clearTimeout(replyTimer);
  }, [activeMessages, autoReply, activeSession?.id, getRandomAgentReply]);

  // Handlers
  const handleSelectSession = (sessionId: string) => {
    if (sessionId === activeSessionId) return;
    setActiveSessionId(sessionId);
    setSessions((prev) =>
      prev.map((session) =>
        session.id === sessionId
          ? { ...session, unreadCount: 0, status: 'active' }
          : session
      )
    );
    const ts = Date.now();
    const session = sessions.find((s) => s.id === sessionId);
    if (session) {
      setTimeline((prev) => [
        {
          id: `switch-${ts}`,
          sessionId,
          label: `${session.customer.name}: ${EVENT_LABELS.session_switch}`,
          timestamp: ts,
          type: 'session_switch',
        },
        ...prev,
      ].slice(0, 20));
    }
  };

  const handleSendReply = () => {
    if (!activeSession || !draftReply.trim()) return;
    const ts = Date.now();

    const replyMessage: SupportMessage = {
      id: generateMessageId(activeSession.id, 'manual'),
      sessionId: activeSession.id,
      sender: 'agent',
      content: draftReply.trim(),
      timestamp: ts,
    };

    setMessagesBySession((prev) => ({
      ...prev,
      [activeSession.id]: [...(prev[activeSession.id] ?? []), replyMessage],
    }));

    setMetrics((prev) => ({
      ...prev,
      knowledgeLookups: prev.knowledgeLookups + 1,
    }));

    setSessions((prev) =>
      prev.map((session) =>
        session.id === activeSession.id
          ? { ...session, status: 'active', unreadCount: 0, lastMessage: draftReply.trim(), lastMessageAt: ts }
          : session
      )
    );

    setTimeline((prev) => [
      {
        id: `manual-${ts}`,
        sessionId: activeSession.id,
        label: `${activeSession.customer.name}: ${EVENT_LABELS.manual_reply}`,
        timestamp: ts,
        type: 'manual_reply',
      },
      ...prev,
    ].slice(0, 20));

    setDraftReply('');
  };

  const handleSuggestedReply = (reply: string) => {
    setDraftReply(reply);
  };

  const handleUseKnowledge = (knowledge: KnowledgeHit) => {
    setDraftReply((prev) => {
      if (prev.trim()) {
        return `${prev}\n\n${knowledge.content}`;
      }
      return knowledge.content;
    });
  };

  const handleCopyKnowledge = (content: string) => {
    navigator.clipboard.writeText(content);
  };

  const suggestedReplies = React.useMemo(() => {
    if (!activeSession) return [];
    return SUGGESTED_REPLIES[activeSession.customer.locale] ?? SUGGESTED_REPLIES.en;
  }, [activeSession?.id]);

  return (
    <Page data-testid="im-workbench-page">
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {/* Control Bar */}
        <ControlBar data-testid="control-bar">
          <ControlBarLeft>
            <Tag color="purple" style={{ fontSize: 12, padding: '4px 12px' }}>Test Target</Tag>
            <Title level={3} style={{ color: '#f8fafc', margin: '8px 0 4px 0' }}>
              IM Workbench Target
            </Title>
            <Paragraph style={{ color: '#94a3b8', margin: 0, fontSize: 13 }}>
              Hidden test-only target for browser automation skills. Not part of the main product chat flow.
            </Paragraph>
          </ControlBarLeft>

          <ControlBarRight>
            <Segmented<ScenarioMode>
              value={scenario}
              options={SCENARIO_OPTIONS.map((option) => ({
                label: <span data-testid={`scenario-option-${option.value}`}>{option.label}</span>,
                value: option.value,
              }))}
              onChange={(value) => setScenario(value)}
            />

            <SliderLabel>
              <Text style={{ color: '#cbd5e1', fontSize: 12 }}>Concurrent Sessions (1-50)</Text>
              <Slider
                min={1}
                max={50}
                value={maxConcurrent}
                onChange={setMaxConcurrent}
                style={{ width: 120, margin: '0 8px' }}
                data-testid="concurrent-slider"
              />
              <Text style={{ color: '#f8fafc', fontSize: 12, minWidth: 24 }}>{maxConcurrent}</Text>
            </SliderLabel>

            <SliderLabel>
              <Text style={{ color: '#cbd5e1', fontSize: 12 }}>Auto Reply</Text>
              <Switch checked={autoReply} onChange={setAutoReply} data-testid="auto-reply-switch" style={{ marginLeft: 8 }} />
            </SliderLabel>

            <Button
              type={running ? 'primary' : 'default'}
              icon={running ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
              onClick={() => setRunning((prev) => !prev)}
              data-testid="run-pause-button"
              danger={running}
            >
              {running ? 'Pause' : 'Run'}
            </Button>
          </ControlBarRight>
        </ControlBar>

        {/* Metrics Row */}
        <MetricsRow data-testid="metrics-row">
          <MetricCard>
            <Statistic
              title="Concurrent Sessions"
              value={metrics.concurrentSessions}
              prefix={<MessageOutlined />}
            />
          </MetricCard>
          <MetricCard>
            <Statistic
              title="Auto Replies"
              value={metrics.autoRepliesSent}
              prefix={<RobotOutlined />}
            />
          </MetricCard>
          <MetricCard>
            <Statistic
              title="Knowledge Lookups"
              value={metrics.knowledgeLookups}
              prefix={<ThunderboltOutlined />}
            />
          </MetricCard>
          <MetricCard>
            <Statistic
              title="Avg Reply Latency"
              value={metrics.avgReplyLatencyMs}
              suffix="ms"
              prefix={<ClockCircleOutlined />}
            />
          </MetricCard>
        </MetricsRow>

        {/* Main Content */}
        <MainContent>
          {/* Session Pool - Left Column */}
          <SessionPoolCard
            title="Session Pool"
            extra={<Text style={{ color: '#94a3b8', fontSize: 12 }}>{sessions.length} total</Text>}
            data-testid="session-pool"
          >
            <SessionTabs>
              {(['urgent', 'active', 'waiting', 'resolved'] as SessionStatus[]).map((status) => (
                <SessionTab
                  key={status}
                  $active={activeTab === status}
                  $status={status}
                  onClick={() => setActiveTab(status)}
                  data-testid={`session-tab-${status}`}
                >
                  {status.charAt(0).toUpperCase() + status.slice(1)}
                  <TabBadge $count={sessionsByStatus[status].length}>
                    {sessionsByStatus[status].length}
                  </TabBadge>
                </SessionTab>
              ))}
            </SessionTabs>

            <SessionList>
              {sessionsByStatus[activeTab].length === 0 ? (
                <EmptyState>
                  <Text style={{ color: '#64748b' }}>No {activeTab} sessions</Text>
                </EmptyState>
              ) : (
                sessionsByStatus[activeTab].map((session) => (
                  <SessionItem
                    key={session.id}
                    $active={session.id === activeSessionId}
                    onClick={() => handleSelectSession(session.id)}
                    data-testid={`session-item-${session.id}`}
                  >
                    <SessionHeader>
                      <CustomerInfo>
                        <CustomerAvatar $color={getAvatarColor(session.customer.name)}>
                          {getInitials(session.customer.name)}
                        </CustomerAvatar>
                        <CustomerName>{session.customer.name}</CustomerName>
                        <LocaleFlag>{LOCALE_FLAGS[session.customer.locale]}</LocaleFlag>
                      </CustomerInfo>
                      {session.unreadCount > 0 && (
                        <Badge count={session.unreadCount} size="small" />
                      )}
                    </SessionHeader>

                    <SessionMeta>
                      <ChannelBadge color={CHANNEL_COLORS[session.customer.channel]}>
                        {session.customer.channel}
                      </ChannelBadge>
                      <PriorityBadge $priority={session.priority}>
                        {session.priority.toUpperCase()}
                      </PriorityBadge>
                    </SessionMeta>

                    <SessionPreview>
                      {session.lastMessage.length > 40 
                        ? session.lastMessage.substring(0, 40) + '...' 
                        : session.lastMessage}
                    </SessionPreview>

                    <SessionFooter>
                      <span>#{session.orderId}</span>
                      <SLATimer
                        $level={getSLALevel(session.slaSeconds)}
                        data-testid={`sla-timer-${session.id}`}
                      >
                        {session.waitingSeconds}s
                      </SLATimer>
                    </SessionFooter>
                  </SessionItem>
                ))
              )}
            </SessionList>
          </SessionPoolCard>

          {/* Conversation Thread - Center Column */}
          <ConversationCard
            title={activeSession ? (
              <div data-testid="active-session">
                {activeSession.customer.name} · {activeSession.customer.channel}
              </div>
            ) : 'No Active Session'}
            data-testid="message-column"
          >
            {activeSession ? (
              <>
                <ConversationHeader>
                  <Space wrap>
                    <Tag color="blue">{activeSession.orderId}</Tag>
                    <Tag color="purple">{INTENT_TAGS[activeSession.intent]}</Tag>
                    <Tag color={activeSession.customer.locale === 'zh' ? 'green' : 'cyan'}>
                      {LOCALE_FLAGS[activeSession.customer.locale]} {activeSession.customer.locale.toUpperCase()}
                    </Tag>
                  </Space>
                </ConversationHeader>

                {/* Customer Profile */}
                <CustomerProfile data-testid="customer-profile">
                  <ProfileItem>
                    <UserOutlined />
                    <ProfileValue>{activeSession.customer.name}</ProfileValue>
                  </ProfileItem>
                  <ProfileItem>
                    <MailOutlined />
                    <ProfileValue style={{ fontSize: 10 }}>{activeSession.customer.email}</ProfileValue>
                  </ProfileItem>
                  <ProfileItem>
                    <ShopOutlined />
                    <ProfileValue>{activeSession.customer.channel}</ProfileValue>
                  </ProfileItem>
                  <ProfileItem>
                    <GlobalOutlined />
                    <ProfileValue>{activeSession.customer.locale === 'zh' ? 'Chinese' : 'English'}</ProfileValue>
                  </ProfileItem>
                  <ProfileItem>
                    <ProfileLabel>Priority:</ProfileLabel>
                    <PriorityBadge $priority={activeSession.priority}>
                      {activeSession.priority.toUpperCase()}
                    </PriorityBadge>
                  </ProfileItem>
                  <ProfileItem>
                    <CrownOutlined />
                    <TierBadge $tier={activeSession.customer.accountTier}>
                      {activeSession.customer.accountTier}
                    </TierBadge>
                  </ProfileItem>
                  <ProfileItem>
                    <HistoryOutlined />
                    <ProfileLabel>Prev Tickets:</ProfileLabel>
                    <ProfileValue>{activeSession.customer.previousTickets}</ProfileValue>
                  </ProfileItem>
                  <ProfileItem>
                    <FireOutlined />
                    <ProfileLabel>SLA:</ProfileLabel>
                    <SLATimer $level={getSLALevel(activeSession.slaSeconds)}>
                      {activeSession.slaSeconds}s
                    </SLATimer>
                  </ProfileItem>
                </CustomerProfile>

                <MessageColumn>
                  {activeMessages.map((message) => (
                    <MessageBubble
                      key={message.id}
                      $sender={message.sender}
                      data-testid={`message-bubble-${message.sender}-${message.id}`}
                    >
                      <MessageHeader>
                        <MessageSender>
                          {message.sender === 'customer'
                            ? activeSession.customer.name
                            : message.sender === 'agent'
                              ? 'Agent'
                              : 'System'}
                        </MessageSender>
                        <MessageTime>{formatTime(message.timestamp)}</MessageTime>
                      </MessageHeader>
                      <MessageContent>{message.content}</MessageContent>
                    </MessageBubble>
                  ))}
                </MessageColumn>

                <ReplyArea>
                  <ReplyHeader>
                    <Text style={{ color: '#94a3b8', fontSize: 12 }}>
                      Reply to {activeSession.customer.name}
                    </Text>
                    <CharCount $exceeded={draftReply.length > 500} data-testid="reply-char-count">
                      {draftReply.length} / 500
                    </CharCount>
                  </ReplyHeader>

                  <TextArea
                    rows={3}
                    value={draftReply}
                    onChange={(e) => setDraftReply(e.target.value)}
                    placeholder="Type your reply..."
                    maxLength={500}
                    data-testid="reply-input"
                  />

                  <SuggestedReplies data-testid="suggested-replies">
                    {suggestedReplies.map((reply, index) => (
                      <SuggestedReplyButton
                        key={index}
                        onClick={() => handleSuggestedReply(reply)}
                        data-testid={`suggested-reply-${index}`}
                      >
                        {reply.length > 30 ? reply.substring(0, 30) + '...' : reply}
                      </SuggestedReplyButton>
                    ))}
                  </SuggestedReplies>

                  <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <Button
                      type="primary"
                      icon={<SendOutlined />}
                      onClick={handleSendReply}
                      disabled={!draftReply.trim()}
                      data-testid="send-button"
                    >
                      Send Reply
                    </Button>
                  </div>
                </ReplyArea>
              </>
            ) : (
              <EmptyState>
                <MessageOutlined style={{ fontSize: 48, marginBottom: 16 }} />
                <Text style={{ color: '#64748b' }}>Select a session to view conversation</Text>
              </EmptyState>
            )}
          </ConversationCard>

          {/* Right Panel - Knowledge & Timeline */}
          <RightPanel>
            {/* Knowledge Assist */}
            <KnowledgeCard
              title="Knowledge Assist"
              extra={<ThunderboltOutlined style={{ color: '#f59e0b' }} />}
              data-testid="knowledge-card"
            >
              <KnowledgeList>
                {knowledgeHits.map((hit) => (
                  <KnowledgeItem key={hit.id} data-testid={`knowledge-hit-${hit.source}-${hit.id}`}>
                    <KnowledgeHeader>
                      <SourceBadge $source={hit.source}>{hit.source.toUpperCase()}</SourceBadge>
                      <ScoreText>{Math.round(hit.score * 100)}%</ScoreText>
                    </KnowledgeHeader>
                    <KnowledgeTitle>{hit.title}</KnowledgeTitle>
                    <KnowledgeContent ellipsis={{ rows: 2 }}>{hit.content}</KnowledgeContent>
                    <Progress percent={Math.round(hit.score * 100)} size="small" showInfo={false} />
                    <KnowledgeActions style={{ marginTop: 8 }}>
                      <Button
                        size="small"
                        type="primary"
                        onClick={() => handleUseKnowledge(hit)}
                        data-testid={`knowledge-use-${hit.id}`}
                      >
                        Use
                      </Button>
                      <Button
                        size="small"
                        icon={<CopyOutlined />}
                        onClick={() => handleCopyKnowledge(hit.content)}
                        data-testid={`knowledge-copy-${hit.id}`}
                      >
                        Copy
                      </Button>
                    </KnowledgeActions>
                  </KnowledgeItem>
                ))}
              </KnowledgeList>
            </KnowledgeCard>

            {/* Event Timeline */}
            <TimelineCard
              title="Event Timeline"
              extra={<ClockCircleOutlined style={{ color: '#64748b' }} />}
            >
              <TimelineList data-testid="timeline">
                {timeline.length === 0 ? (
                  <EmptyState>
                    <Text style={{ color: '#64748b', fontSize: 12 }}>No events yet</Text>
                  </EmptyState>
                ) : (
                  timeline.slice(0, 20).map((event) => (
                    <TimelineItem
                      key={event.id}
                      $type={event.type}
                      data-testid={`timeline-event-${event.id}`}
                    >
                      <TimelineTime>{formatTime(event.timestamp)}</TimelineTime>
                      <TimelineLabel>{event.label}</TimelineLabel>
                    </TimelineItem>
                  ))
                )}
              </TimelineList>
            </TimelineCard>
          </RightPanel>
        </MainContent>
      </Space>
    </Page>
  );
};

export default App;
