/**
 * Unit tests for SequentialIPCClient.
 */
import { SequentialIPCClient } from './sequentialClient';
import { IPCClient } from './client';
import { logger } from '../../utils/logger';

// 1. Mock the dependencies
jest.mock('./client', () => {
    // This is a manual mock of the IPCClient class
    const mockSendRequest = jest.fn();
    return {
        IPCClient: {
            getInstance: jest.fn().mockReturnValue({
                sendRequest: mockSendRequest,
            }),
        },
    };
});

// Mock the logger to prevent console output during tests
jest.mock('../../utils/logger', () => ({
    logger: {
        info: jest.fn(),
        debug: jest.fn(),
        warn: jest.fn(),
        error: jest.fn(),
    },
}));


// Type assertion for the mocked client
const MockedIPCClient = IPCClient as jest.Mocked<typeof IPCClient>;
// Get the underlying mock function to control its behavior in tests
const mockSendRequest = (MockedIPCClient.getInstance() as any).sendRequest as jest.Mock;

describe('SequentialIPCClient', () => {

    beforeEach(() => {
        // Clear any previous mock implementations and call history before each test
        mockSendRequest.mockClear();
    });

    it('should process a single request correctly', async () => {
        const sequentialClient = new SequentialIPCClient();
        const mockResult = { data: 'single_request_ok' };
        mockSendRequest.mockResolvedValue(mockResult);

        const result = await sequentialClient.sendRequest('get_user');
        
        expect(result).toEqual(mockResult);
        expect(mockSendRequest).toHaveBeenCalledWith('get_user', undefined, undefined);
        expect(mockSendRequest).toHaveBeenCalledTimes(1);
    });

    it('should process multiple requests in the correct sequence', async () => {
        const sequentialClient = new SequentialIPCClient();
        const processingOrder: string[] = [];

        // Mock sendRequest to return results based on method
        mockSendRequest.mockImplementation(async (method: string) => {
            if (method === 'taskA') return 'Result A';
            if (method === 'taskB') return 'Result B';
        });

        const promiseA = sequentialClient.sendRequest('taskA').then((res: any) => {
            processingOrder.push(res);
            return res;
        });

        const promiseB = sequentialClient.sendRequest('taskB').then((res: any) => {
            processingOrder.push(res);
            return res;
        });

        await Promise.all([promiseA, promiseB]);

        expect(processingOrder).toEqual(['Result A', 'Result B']);
        expect(mockSendRequest).toHaveBeenCalledTimes(2);
    });

    it('should maintain processing order even if responses arrive out of order', async () => {
        const sequentialClient = new SequentialIPCClient();
        const processingOrder: string[] = [];
        
        // This object will hold the resolve functions for our manual promises
        const resolvers: Record<string, (value: string) => void> = {};

        // Manually control promise resolution
        mockSendRequest.mockImplementation((method: string) => {
            return new Promise(resolve => {
                resolvers[method] = resolve;
            });
        });

        // Act: Send two requests. The promises are now stored.
        const promiseA = sequentialClient.sendRequest('taskA').then((res: any) => {
            logger.info('Task A processed');
            processingOrder.push(res);
        });
        
        const promiseB = sequentialClient.sendRequest('taskB').then((res: any) => {
            logger.info('Task B processed');
            processingOrder.push(res);
        });

        // Assert: At this point, nothing should have been processed
        expect(processingOrder).toEqual([]);

        // Manually resolve B FIRST
        resolvers['taskB']('Result B');
        // Give a tick for promise to potentially resolve (it shouldn't)
        await new Promise(r => setImmediate(r)); 
        
        // Assert: Still, nothing should have been processed because A is not done
        expect(processingOrder).toEqual([]);
        
        // Manually resolve A
        resolvers['taskA']('Result A');
        
        // Wait for both promises in the chain to complete
        await Promise.all([promiseA, promiseB]);

        // Assert: Now, the processing order must be correct
        expect(processingOrder).toEqual(['Result A', 'Result B']);
    });

    it('should continue the chain even if a request fails', async () => {
        const sequentialClient = new SequentialIPCClient();
        const processingOrder: string[] = [];
        const errors: Error[] = [];

        mockSendRequest.mockImplementation(async (method: string) => {
            if (method === 'failingTask') {
                throw new Error('Task Failed');
            }
            if (method === 'succeedingTask') {
                return 'Result C';
            }
        });

        const promiseFail = sequentialClient.sendRequest('failingTask').catch((err: any) => {
            errors.push(err);
        });

        const promiseSucceed = sequentialClient.sendRequest('succeedingTask').then((res: any) => {
            processingOrder.push(res);
        });
        
        await Promise.all([promiseFail, promiseSucceed]);
        
        expect(errors).toHaveLength(1);
        expect(errors[0].message).toBe('Task Failed');
        expect(processingOrder).toEqual(['Result C']);
    });
}); 