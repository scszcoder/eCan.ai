// 任务相关的类型定义
export interface Task {
  id: string;
  sessionId: string;
  skill: string;
  metadata: {
    state: {
      top: string;
    };
  };
  state: {
    top: string;
  };
  resume_from: string;
  trigger: string;
  schedule: {
    repeat_type: string;
    repeat_number: number;
    repeat_unit: string;
    start_date_time: string;
    end_date_time: string;
    time_out: number;
  };
  checkpoint_nodes: any[];
  priority: string;
  last_run_datetime: string | null;
  already_run_flag: boolean;
} 