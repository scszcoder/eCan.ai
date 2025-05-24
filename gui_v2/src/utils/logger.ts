/**
 * 日志工具
 * 提供统一的日志记录功能，支持日志等级控制
 */

// 日志等级枚举
enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3,
  NONE = 4
}

// 日志配置接口
interface LoggerConfig {
  level: LogLevel;
  enableConsole: boolean;
  enableFile: boolean;
  filePath?: string;
  format?: (level: string, message: string, ...args: unknown[]) => string;
}

// 默认配置
const defaultConfig: LoggerConfig = {
  level: LogLevel.INFO,
  enableConsole: true,
  enableFile: false,
  format: (level: string, message: string, ...args: unknown[]) => {
    const timestamp = new Date().toISOString();
    const formattedArgs = args.map(arg => 
      typeof arg === 'object' ? JSON.stringify(arg, null, 2) : String(arg)
    ).join(' ');
    
    return `[${timestamp}] [${level}] ${message} ${formattedArgs}`.trim();
  }
};

class Logger {
  private config: LoggerConfig;
  private static instance: Logger;

  private constructor(config: Partial<LoggerConfig> = {}) {
    this.config = { ...defaultConfig, ...config };
    // 打印初始配置
    console.log('Logger initialized with config:', {
      level: LogLevel[this.config.level],
      enableConsole: this.config.enableConsole
    });
  }

  /**
   * 获取日志实例
   */
  public static getInstance(config?: Partial<LoggerConfig>): Logger {
    if (!Logger.instance) {
      Logger.instance = new Logger(config);
    }
    return Logger.instance;
  }

  /**
   * 更新日志配置
   */
  public updateConfig(config: Partial<LoggerConfig>): void {
    this.config = { ...this.config, ...config };
    console.log('Logger config updated:', {
      level: LogLevel[this.config.level],
      enableConsole: this.config.enableConsole
    });
  }

  /**
   * 获取当前日志等级
   */
  public getLevel(): LogLevel {
    return this.config.level;
  }

  /**
   * 设置日志等级
   */
  public setLevel(level: LogLevel): void {
    this.config.level = level;
    console.log('Logger level set to:', LogLevel[level]);
  }

  /**
   * 写入日志
   */
  private log(level: LogLevel, levelName: string, message: string, ...args: unknown[]): void {
    // 检查日志等级：只有当当前日志等级小于等于配置的等级时才显示
    if (this.config.level > level) {
      return;
    }

    const formattedMessage = this.config.format?.(levelName, message, ...args) ?? 
      `[${levelName}] ${message} ${args.join(' ')}`;

    if (this.config.enableConsole) {
      // 使用 console.log 替代 console.debug，因为某些浏览器可能不支持 console.debug
      switch (level) {
        case LogLevel.DEBUG:
          console.log(`%c${formattedMessage}`, 'color: #6c757d'); // 使用灰色显示 debug 日志
          break;
        case LogLevel.INFO:
          console.info(formattedMessage);
          break;
        case LogLevel.WARN:
          console.warn(formattedMessage);
          break;
        case LogLevel.ERROR:
          console.error(formattedMessage);
          break;
      }
    }

    if (this.config.enableFile && this.config.filePath) {
      // TODO: 实现文件日志写入
      // 这里可以添加将日志写入文件的逻辑
    }
  }

  /**
   * 记录调试级别日志
   */
  public debug(message: string, ...args: unknown[]): void {
    this.log(LogLevel.DEBUG, 'DEBUG', message, ...args);
  }

  /**
   * 记录信息级别日志
   */
  public info(message: string, ...args: unknown[]): void {
    this.log(LogLevel.INFO, 'INFO', message, ...args);
  }

  /**
   * 记录警告级别日志
   */
  public warn(message: string, ...args: unknown[]): void {
    this.log(LogLevel.WARN, 'WARN', message, ...args);
  }

  /**
   * 记录错误级别日志
   */
  public error(message: string, ...args: unknown[]): void {
    this.log(LogLevel.ERROR, 'ERROR', message, ...args);
  }
}

// 导出单例实例
export const logger = Logger.getInstance();

// 导出日志等级枚举
export { LogLevel }; 