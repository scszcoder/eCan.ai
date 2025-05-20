"""
JavaScript 注入模块，处理脚本注入和初始化
"""

class JavaScriptInjector:
    """JavaScript 注入器类，用于注入和管理 JavaScript 代码"""
    
    @staticmethod
    def get_web_channel_script():
        """获取 WebChannel 初始化脚本"""
        return """
        // 全局状态管理
        window.webChannelState = {
            isInitialized: false,
            isInitializing: false,
            lastError: null,
            retryCount: 0,
            maxRetries: 5
        };

        // 确保 Qt WebChannel 脚本加载完成
        function loadQtWebChannel() {
            return new Promise((resolve, reject) => {
                if (window.QWebChannel) {
                    console.log('QWebChannel already loaded');
                    resolve();
                    return;
                }

                if (window.webChannelState.retryCount >= window.webChannelState.maxRetries) {
                    const error = new Error('Maximum retry attempts reached');
                    window.webChannelState.lastError = error;
                    reject(error);
                    return;
                }

                console.log('Loading QWebChannel script...');
                const script = document.createElement('script');
                script.src = 'qrc:///qtwebchannel/qwebchannel.js';
                
                const timeout = setTimeout(() => {
                    window.webChannelState.retryCount++;
                    reject(new Error('Script load timeout'));
                }, 5000);

                script.onload = () => {
                    clearTimeout(timeout);
                    console.log('QWebChannel script loaded successfully');
                    resolve();
                };
                
                script.onerror = (error) => {
                    clearTimeout(timeout);
                    window.webChannelState.retryCount++;
                    console.error('Failed to load QWebChannel script:', error);
                    reject(error);
                };
                
                document.head.appendChild(script);
            });
        }

        // 初始化 WebChannel
        async function initializeWebChannel() {
            if (window.webChannelState.isInitialized) {
                console.log('WebChannel already initialized');
                return;
            }

            if (window.webChannelState.isInitializing) {
                console.log('WebChannel initialization in progress');
                return;
            }

            window.webChannelState.isInitializing = true;
            window.webChannelState.lastError = null;

            try {
                await loadQtWebChannel();
                
                console.log('Creating QWebChannel...');
                new QWebChannel(qt.webChannelTransport, function(channel) {
                    console.log('QWebChannel created successfully');
                    
                    const bridge = channel.objects.bridge;
                    console.log('Bridge object:', bridge);
                    
                    if (bridge) {
                        window.bridge = bridge;
                        window.webChannelState.isInitialized = true;
                        window.webChannelState.isInitializing = false;

                        // 设置消息处理
                        if (bridge.dataReceived) {
                            bridge.dataReceived.connect(function(message) {
                                try {
                                    const data = JSON.parse(message);
                                    console.log('Received from Python:', data);
                                    
                                    if (data.type === 'response') {
                                        const event = new CustomEvent('python-response', {
                                            detail: data
                                        });
                                        window.dispatchEvent(event);
                                    }
                                } catch (e) {
                                    console.error('Error parsing message from Python:', e);
                                    window.webChannelState.lastError = e;
                                }
                            });
                            console.log('Message handler set up successfully');
                        } else {
                            throw new Error('dataReceived not available on bridge');
                        }

                        // 设置发送消息的函数
                        window.sendToPython = function(message) {
                            if (!window.bridge) {
                                throw new Error('Bridge not initialized');
                            }
                            try {
                                if (typeof message === 'object') {
                                    message = JSON.stringify(message);
                                }
                                window.bridge.sendToPython(message);
                                console.log('Message sent to Python:', message);
                            } catch (e) {
                                console.error('Error sending message to Python:', e);
                                window.webChannelState.lastError = e;
                                throw e;
                            }
                        };

                        // 触发自定义事件通知初始化完成
                        const event = new CustomEvent('webchannel-ready');
                        console.log('Dispatching webchannel-ready event');
                        window.dispatchEvent(event);

                        // 发送测试消息
                        window.sendToPython({
                            type: 'command',
                            command: 'test_command',
                            data: { test: 'Initial connection test' }
                        });
                    } else {
                        throw new Error('Bridge object not available');
                    }
                });
            } catch (e) {
                console.error('Error initializing WebChannel:', e);
                window.webChannelState.lastError = e;
                window.webChannelState.isInitializing = false;
                
                // 如果还有重试次数，延迟后重试
                if (window.webChannelState.retryCount < window.webChannelState.maxRetries) {
                    setTimeout(initializeWebChannel, 1000 * Math.pow(2, window.webChannelState.retryCount));
                }
            }
        }

        // 全局错误处理
        window.addEventListener('error', function(event) {
            console.error('Global error:', event.error);
            window.webChannelState.lastError = event.error;
        });

        // 等待页面完全加载
        if (document.readyState === 'complete') {
            console.log('Document already loaded, initializing WebChannel');
            initializeWebChannel();
        } else {
            console.log('Waiting for document load...');
            window.addEventListener('load', function() {
                console.log('Document loaded, initializing WebChannel');
                initializeWebChannel();
            });
        }
        """
    
    @staticmethod
    def get_dev_tools_script():
        """获取开发者工具相关的脚本"""
        return """
        (function() {
            // 控制台日志拦截
            const originalConsole = {
                log: console.log,
                info: console.info,
                warn: console.warn,
                error: console.error,
                debug: console.debug
            };
            
            function sendToPython(type, message) {
                try {
                    const event = new CustomEvent('python-command', {
                        detail: {
                            command: type,
                            data: message
                        }
                    });
                    window.dispatchEvent(event);
                } catch (e) {
                    originalConsole.error('Error sending to Python:', e);
                }
            }
            
            // 重写控制台方法
            console.log = function() {
                originalConsole.log.apply(console, arguments);
                sendToPython('console_log', {
                    type: 'log',
                    message: Array.from(arguments).join(' '),
                    timestamp: new Date().toISOString()
                });
            };
            
            console.info = function() {
                originalConsole.info.apply(console, arguments);
                sendToPython('console_log', {
                    type: 'info',
                    message: Array.from(arguments).join(' '),
                    timestamp: new Date().toISOString()
                });
            };
            
            console.warn = function() {
                originalConsole.warn.apply(console, arguments);
                sendToPython('console_log', {
                    type: 'warning',
                    message: Array.from(arguments).join(' '),
                    timestamp: new Date().toISOString()
                });
            };
            
            console.error = function() {
                originalConsole.error.apply(console, arguments);
                sendToPython('console_log', {
                    type: 'error',
                    message: Array.from(arguments).join(' '),
                    timestamp: new Date().toISOString()
                });
            };
            
            console.debug = function() {
                originalConsole.debug.apply(console, arguments);
                sendToPython('console_log', {
                    type: 'debug',
                    message: Array.from(arguments).join(' '),
                    timestamp: new Date().toISOString()
                });
            };
            
            // 网络请求监控
            const originalFetch = window.fetch;
            window.fetch = async function() {
                const startTime = performance.now();
                try {
                    const response = await originalFetch.apply(this, arguments);
                    const endTime = performance.now();
                    
                    sendToPython('network_request', {
                        url: arguments[0],
                        method: arguments[1]?.method || 'GET',
                        status: response.status,
                        duration: endTime - startTime,
                        timestamp: new Date().toISOString()
                    });
                    
                    return response;
                } catch (error) {
                    const endTime = performance.now();
                    sendToPython('network_request', {
                        url: arguments[0],
                        method: arguments[1]?.method || 'GET',
                        status: 0,
                        error: error.message,
                        duration: endTime - startTime,
                        timestamp: new Date().toISOString()
                    });
                    throw error;
                }
            };
            
            // 元素检查模式
            let inspectMode = false;
            let hoveredElement = null;
            
            function handleMouseOver(e) {
                if (!inspectMode) return;
                e.preventDefault();
                e.stopPropagation();
                
                if (hoveredElement) {
                    hoveredElement.style.outline = '';
                }
                
                hoveredElement = e.target;
                hoveredElement.style.outline = '2px solid #007bff';
            }
            
            function handleMouseOut(e) {
                if (!inspectMode) return;
                e.preventDefault();
                e.stopPropagation();
                
                if (hoveredElement) {
                    hoveredElement.style.outline = '';
                    hoveredElement = null;
                }
            }
            
            function handleClick(e) {
                if (!inspectMode) return;
                e.preventDefault();
                e.stopPropagation();
                
                const element = e.target;
                const elementInfo = {
                    tagName: element.tagName,
                    id: element.id,
                    className: element.className,
                    attributes: Array.from(element.attributes).map(attr => ({
                        name: attr.name,
                        value: attr.value
                    })),
                    innerHTML: element.innerHTML,
                    outerHTML: element.outerHTML,
                    computedStyle: window.getComputedStyle(element)
                };
                
                sendToPython('inspect_element', elementInfo);
            }
            
            // 监听 Python 命令
            window.addEventListener('python-command', function(e) {
                const { command, data } = e.detail;
                
                switch (command) {
                    case 'toggle_inspect_mode':
                        inspectMode = !inspectMode;
                        if (inspectMode) {
                            document.addEventListener('mouseover', handleMouseOver);
                            document.addEventListener('mouseout', handleMouseOut);
                            document.addEventListener('click', handleClick);
                        } else {
                            document.removeEventListener('mouseover', handleMouseOver);
                            document.removeEventListener('mouseout', handleMouseOut);
                            document.removeEventListener('click', handleClick);
                            if (hoveredElement) {
                                hoveredElement.style.outline = '';
                                hoveredElement = null;
                            }
                        }
                        break;
                }
            });
            
            // 性能监控
            const performanceObserver = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                sendToPython('performance_metrics', {
                    entries: entries.map(entry => ({
                        name: entry.name,
                        type: entry.entryType,
                        duration: entry.duration,
                        startTime: entry.startTime,
                        timestamp: new Date().toISOString()
                    }))
                });
            });
            
            performanceObserver.observe({ entryTypes: ['resource', 'navigation', 'paint'] });
        })();
        """ 