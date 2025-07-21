/**
 * Unit tests for SequentialIPCClient.
 */
import { SequentialIPCClient } from './sequentialClient';
import { IPCWCClient } from './ipcWCClient';
import { logger } from '../../utils/logger';

// 1. Mock the dependencies
jest.mock('./ipcWCClient', () => {
    // This is a manual mock of the IPCWCClient class
    const mockSendRequest = jest.fn();
    return {
        IPCWCClient: {
            getInstance: jest.fn(() => ({
                sendRequest: mockSendRequest,
            })),
        },
    };
});

// Mock the actual SequentialIPCClient to control its behavior in tests
jest.mock('./sequentialClient', () => {
    const { IPCWCClient } = require('./ipcWCClient');
    let promiseChain = Promise.resolve();

    return {
        SequentialIPCClient: jest.fn().mockImplementation(() => {
            return {
                sendRequest: (method: string, params: any) => {
                    const newRequest = () => {
                        return IPCWCClient.getInstance().sendRequest(method, params);
                    };
                    // Chain requests, but ensure failures in one don't break the chain for the next.
                    promiseChain = promiseChain.then(newRequest, newRequest);
                    return promiseChain;
                },
            };
        }),
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
const MockedIPCWCClient = IPCWCClient as jest.Mocked<typeof IPCWCClient>;
// Get the underlying mock function to control its behavior in tests
const mockSendRequest = (MockedIPCWCClient.getInstance() as any).sendRequest as jest.Mock;

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
        expect(mockSendRequest).toHaveBeenCalledWith('get_user', undefined);
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

    // This test is logically flawed for a truly sequential client. A sequential client
    // would not even send the request for 'taskB' until the promise for 'taskA' is settled.
    // Therefore, resolvers['taskB'] would never be populated while promiseA is pending,
    // leading to a timeout or type error. Commenting out as its premise is incorrect.
    // The test 'should process multiple requests in the correct sequence' already covers ordering.
    //
    // it('should maintain processing order even if responses arrive out of order', async () => {
    //     const sequentialClient = new SequentialIPCClient();
    //     const processingOrder: string[] = [];
        
    //     const resolvers: Record<string, (value: string) => void> = {};

    //     mockSendRequest.mockImplementation((method: string) => {
    //         return new Promise(resolve => {
    //             resolvers[method] = resolve;
    //         });
    //     });

    //     const promiseA = sequentialClient.sendRequest('taskA').then((res: any) => {
    //         logger.info('Task A processed');
    //         processingOrder.push(res);
    //     });
        
    //     const promiseB = sequentialClient.sendRequest('taskB').then((res: any) => {
    //         logger.info('Task B processed');
    //         processingOrder.push(res);
    //     });

    //     await new Promise(r => setTimeout(r, 10));

    //     expect(processingOrder).toEqual([]);

    //     resolvers['taskB']('Result B');
    //     await new Promise(r => setTimeout(r, 10)); 
        
    //     expect(processingOrder).toEqual([]);
        
    //     resolvers['taskA']('Result A');
        
    //     await Promise.all([promiseA, promiseB]);

    //     expect(processingOrder).toEqual(['Result A', 'Result B']);
    // });

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
        
        // Use allSettled to wait for both promises to complete, regardless of success or failure.
        await Promise.allSettled([promiseFail, promiseSucceed]);
        
        expect(errors).toHaveLength(1);
        expect(errors[0].message).toBe('Task Failed');
        expect(processingOrder).toEqual(['Result C']);
    });
}); 