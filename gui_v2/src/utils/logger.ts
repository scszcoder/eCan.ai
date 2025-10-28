/**
 * LogTool
 * 提供统一的Log记录功能，SupportLog等级控制
 */

// Log等级枚举
enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3,
  NONE = 4
}

// LogConfigurationInterface
interface LoggerConfig {
  level: LogLevel;
  enableConsole: boolean;
  enableFile: boolean;
  filePath?: string;
  format?: (level: string, message: string, ...args: unknown[]) => string;
}

// DefaultConfiguration
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
    // Print初始Configuration
    console.log('Logger initialized with config:', {
      level: LogLevel[this.config.level],
      enableConsole: this.config.enableConsole
    });
  }

  /**
   * GetLog实例
   */
  public static getInstance(config?: Partial<LoggerConfig>): Logger {
    if (!Logger.instance) {
      Logger.instance = new Logger(config);
    }
    return Logger.instance;
  }

  /**
   * UpdateLogConfiguration
   */
  public updateConfig(config: Partial<LoggerConfig>): void {
    this.config = { ...this.config, ...config };
    console.log('Logger config updated:', {
      level: LogLevel[this.config.level],
      enableConsole: this.config.enableConsole
    });
  }

  /**
   * GetWhen前Log等级
   */
  public getLevel(): LogLevel {
    return this.config.level;
  }

  /**
   * SettingsLog等级
   */
  public setLevel(level: LogLevel): void {
    this.config.level = level;
    console.log('Logger level set to:', LogLevel[level]);
  }

  /**
   * 写入Log
   */
  private log(level: LogLevel, levelName: string, message: string, ...args: unknown[]): void {
    // CheckLog等级：只有WhenWhen前Log等级小于等于Configuration的等级时才Display
    if (this.config.level > level) {
      return;
    }

    const formattedMessage = this.config.format?.(levelName, message, ...args) ?? 
      `[${levelName}] ${message} ${args.join(' ')}`;

    if (this.config.enableConsole) {
      // 使用 console.log 替代 console.debug，因为某些Browser可能不Support console.debug
      switch (level) {
        case LogLevel.DEBUG:
          console.log(`%c${formattedMessage}`, 'color: #6c757d'); // 使用灰色Display debug Log
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
      // TODO: Implementation文件Log写入
      // 这里CanAdd将Log写入文件的逻辑
    }
  }

  /**
   * 记录DebugLevelLog
   */
  public debug(message: string, ...args: unknown[]): void {
    this.log(LogLevel.DEBUG, 'DEBUG', message, ...args);
  }

  /**
   * 记录InformationLevelLog
   */
  public info(message: string, ...args: unknown[]): void {
    this.log(LogLevel.INFO, 'INFO', message, ...args);
  }

  /**
   * 记录WarningLevelLog
   */
  public warn(message: string, ...args: unknown[]): void {
    this.log(LogLevel.WARN, 'WARN', message, ...args);
  }

  /**
   * 记录ErrorLevelLog
   */
  public error(message: string, ...args: unknown[]): void {
    this.log(LogLevel.ERROR, 'ERROR', message, ...args);
  }
}

// Export单例实例
export const logger = Logger.getInstance();

// ExportLog等级枚举
export { LogLevel }; 