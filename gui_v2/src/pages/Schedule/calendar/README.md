# Calendar View for Schedule Management
# 日程管理日历视图

这是一个功能完整的日历UI组件库，用于管理和展示任务日程。

## ✨ 功能特性

### 📅 三种视图模式
- **月视图 (Month View)**: 以月为单位展示所有任务，快速了解整月安排
- **周视图 (Week View)**: 以周为单位展示任务，更详细的时间轴视图
- **日视图 (Day View)**: 以天为单位展示任务，精确到分钟的时间规划

### 🎯 核心功能
- ✅ 任务状态可视化（待处理、进行中、已完成、失败、已取消）
- 🔄 重复任务支持（按秒/分钟/小时/天/周/月/年）
- 📊 优先级标识（低、中、高、紧急）
- 🎨 状态颜色编码
- 📌 今日指示器（实时显示当前时间）
- 🔍 任务详情查看
- ✏️ 创建和编辑日程
- 🗑️ 删除日程
- ▶️ 运行任务

### 🎨 视觉特性
- 深色主题设计
- 流畅的动画过渡
- 响应式布局
- 悬停效果
- 拖拽式交互（计划中）

## 📦 组件结构

```
calendar/
├── types.ts                    # 类型定义
├── utils.ts                    # 工具函数
├── MonthView.tsx              # 月视图组件
├── WeekView.tsx               # 周视图组件
├── DayView.tsx                # 日视图组件
├── CalendarView.tsx           # 主日历组件（集成所有视图）
├── EventDetailDrawer.tsx      # 事件详情抽屉
├── ScheduleFormModal.tsx      # 日程表单弹窗
└── README.md                  # 文档
```

## 🚀 使用方法

### 基础用法

```tsx
import { CalendarView } from './calendar';

function SchedulePage() {
  const [schedules, setSchedules] = useState<TaskSchedule[]>([]);
  
  return (
    <CalendarView
      schedules={schedules}
      onRefresh={() => loadSchedules()}
      onCreateSchedule={(data) => createSchedule(data)}
      onUpdateSchedule={(schedule) => updateSchedule(schedule)}
      onDeleteSchedule={(schedule) => deleteSchedule(schedule)}
      onRunTask={(event) => runTask(event)}
    />
  );
}
```

### 自定义配置

```tsx
const config: Partial<CalendarConfig> = {
  weekStartsOn: 1,           // 0=Sunday, 1=Monday
  timeSlotDuration: 30,       // 时间槽间隔（分钟）
  dayStartHour: 0,            // 每天开始时间
  dayEndHour: 24,             // 每天结束时间
  showWeekNumbers: true,      // 显示周数
  showWeekends: true,         // 显示周末
  locale: 'zh-CN',            // 语言环境
};

<CalendarView schedules={schedules} config={config} />
```

## 📋 数据结构

### TaskSchedule (输入数据)
```typescript
interface TaskSchedule {
  taskId?: string;
  taskName?: string;
  repeat_type: 'none' | 'by seconds' | 'by minutes' | 'by hours' | 
                'by days' | 'by weeks' | 'by months' | 'by years';
  repeat_number: number;
  repeat_unit: 'second' | 'minute' | 'hour' | 'day' | 'week' | 'month' | 'year';
  start_date_time: string;  // "YYYY-MM-DD HH:mm:ss:SSS"
  end_date_time: string;    // "YYYY-MM-DD HH:mm:ss:SSS"
  time_out: number;
  week_days?: Array<'M' | 'Tu' | 'W' | 'Th' | 'F' | 'SA' | 'SU'>;
  months?: Array<'Jan' | 'Feb' | 'Mar' | 'Apr' | 'May' | 'Jun' | 
                 'Jul' | 'Aug' | 'Sep' | 'Oct' | 'Nov' | 'Dec'>;
}
```

### CalendarEvent (内部使用)
```typescript
interface CalendarEvent {
  id: string;
  title: string;
  start: Date;
  end: Date;
  taskId?: string;
  schedule: TaskSchedule;
  isRecurring: boolean;
  isOneTime: boolean;
  status?: string;
  priority?: string;
  color?: string;
  backgroundColor?: string;
  borderColor?: string;
}
```

## 🎨 状态颜色

| 状态 | 颜色 | 说明 |
|------|------|------|
| pending | 🟡 黄色 | 待处理 |
| running / in_progress | 🔵 蓝色 | 进行中 |
| completed | 🟢 绿色 | 已完成 |
| failed | 🔴 红色 | 失败 |
| cancelled | ⚪ 灰色 | 已取消 |

## 🔧 工具函数

### schedulesToEvents
将 `TaskSchedule[]` 转换为 `CalendarEvent[]`

### generateRecurringEvents
生成重复事件的所有实例（在指定日期范围内）

### getEventsInRange
获取日期范围内的所有事件（包括重复事件的实例）

### generateMonthView
生成月视图数据结构

### generateWeekView
生成周视图数据结构

### generateTimeSlots
生成日视图的时间槽

### detectEventConflicts
检测事件时间冲突

### navigateNext / navigatePrevious
日历导航函数

### formatViewTitle
格式化视图标题

## 🌟 特色功能

### 1. 重复任务智能展开
系统会自动根据重复规则生成所有任务实例，支持：
- 星期过滤（只在特定星期重复）
- 月份过滤（只在特定月份重复）
- 复杂的组合规则

### 2. 时间冲突检测
自动检测和高亮显示时间冲突的任务

### 3. 实时时间指示器
在周视图和日视图中显示当前时间线

### 4. 智能事件布局
自动处理重叠事件的显示，避免视觉混乱

### 5. 响应式设计
适配不同屏幕尺寸，提供最佳的用户体验

## 🔮 未来计划

- [ ] 拖拽调整任务时间
- [ ] 批量操作任务
- [ ] 任务过滤和搜索
- [ ] 导出日历
- [ ] 打印功能
- [ ] 任务模板
- [ ] 团队协作视图
- [ ] 移动端适配
- [ ] 离线支持

## 📝 注意事项

1. **日期格式**: 输入的日期字符串必须是 `YYYY-MM-DD HH:mm:ss:SSS` 格式
2. **重复任务**: 为避免性能问题，重复事件生成最多1000个实例
3. **时区**: 所有时间默认使用本地时区
4. **性能**: 建议一次加载不超过1000个任务

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可

MIT License

