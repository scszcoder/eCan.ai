import { logger } from '../../utils/logger';

// EventServiceInterface
interface EventService {
    initialize(): void;
    cleanup(): void;
    getStatus(): { isInitialized: boolean; eventCount: number };
}

// Event管理器类
export class EventManager {
    private static instance: EventManager;
    private services: Map<string, EventService> = new Map();
    private isInitialized = false;

    private constructor() {}

    // 单例模式
    public static getInstance(): EventManager {
        if (!EventManager.instance) {
            EventManager.instance = new EventManager();
        }
        return EventManager.instance;
    }

    // RegisterEventService
    public registerService(name: string, service: EventService): void {
        if (this.services.has(name)) {
            logger.warn(`EventService ${name} 已经存在，将被覆盖`);
        }
        this.services.set(name, service);
        logger.info(`RegisterEventService: ${name}`);
    }

    // GetEventService
    public getService<T extends EventService>(name: string): T | undefined {
        return this.services.get(name) as T | undefined;
    }

    // InitializeAllService
    public initialize(): void {
        if (this.isInitialized) {
            logger.warn('EventManager 已经Initialize过了');
            return;
        }

        logger.info('Initialize EventManager...');
        
        // RegisterDefaultService
        this.registerDefaultServices();
        
        // InitializeAllService
        this.services.forEach((service, name) => {
            try {
                service.initialize();
                logger.info(`EventService ${name} InitializeSuccess`);
            } catch (error) {
                logger.error(`EventService ${name} InitializeFailed:`, error);
            }
        });

        this.isInitialized = true;
        logger.info('EventManager InitializeCompleted');
    }

    // CleanupAllService
    public cleanup(): void {
        if (!this.isInitialized) {
            return;
        }

        logger.info('Cleanup EventManager...');
        
        this.services.forEach((service, name) => {
            try {
                service.cleanup();
                logger.info(`EventService ${name} CleanupSuccess`);
            } catch (error) {
                logger.error(`EventService ${name} CleanupFailed:`, error);
            }
        });

        this.isInitialized = false;
        logger.info('EventManager CleanupCompleted');
    }

    // GetAllServiceStatus
    public getAllServicesStatus(): Record<string, { isInitialized: boolean; eventCount: number }> {
        const status: Record<string, { isInitialized: boolean; eventCount: number }> = {};
        
        this.services.forEach((service, name) => {
            status[name] = service.getStatus();
        });

        return status;
    }

    // Get管理器Status
    public getStatus(): { isInitialized: boolean; serviceCount: number } {
        return {
            isInitialized: this.isInitialized,
            serviceCount: this.services.size
        };
    }

    // RegisterDefaultService
    private registerDefaultServices(): void {
        // 这里CanRegister其他EventService
        // this.registerService('otherEvent', otherEventService);
    }

    // GetServiceList
    public getServiceNames(): string[] {
        return Array.from(this.services.keys());
    }

    // CheckService是否存在
    public hasService(name: string): boolean {
        return this.services.has(name);
    }

    // RemoveService
    public removeService(name: string): boolean {
        const service = this.services.get(name);
        if (service) {
            try {
                service.cleanup();
                this.services.delete(name);
                logger.info(`RemoveEventService: ${name}`);
                return true;
            } catch (error) {
                logger.error(`RemoveEventService ${name} Failed:`, error);
                return false;
            }
        }
        return false;
    }
}

// Export单例实例
export const eventManager = EventManager.getInstance(); 