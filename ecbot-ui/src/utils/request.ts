import axios, {AxiosInstance, AxiosError, AxiosRequestConfig, AxiosResponse} from 'axios';
import {MessagePlugin} from 'tdesign-vue-next'; // 假设Message是一个可以导入的组件

// 定义请求响应参数
interface ResponseData<T = any> {
    code: number;
    message: string;
    data?: T;
}

// 配置类
class AppConfig {
    private static instance: AppConfig;
    public baseURL: string;
    public timeout: number;

    private constructor() {
        this.baseURL = 'http://localhost:8888'; // 使用环境变量
        this.timeout = parseInt('20000', 10);
    }

    public static getInstance(): AppConfig {
        if (!AppConfig.instance) {
            AppConfig.instance = new AppConfig();
        }
        return AppConfig.instance;
    }

    // 将配置转换为 AxiosRequestConfig 格式
    toAxiosConfig(): AxiosRequestConfig {
        return {
            baseURL: this.baseURL,
            timeout: this.timeout
        };
    }
}

// 请求类
class RequestHttp {
    private service: AxiosInstance;

    constructor(private config: AxiosRequestConfig) {
        this.service = axios.create(this.config);
        this.initInterceptors();
    }

    private initInterceptors() {
        this.service.interceptors.request.use(
            (config) => {
                // const token = localStorage.getItem('token') || '';
                // if (token) {
                //     config.headers = {
                //         ...config.headers,
                //         Authorization: `Bearer ${token}`
                //     };
                // }
                return config;
            },
            (error) => Promise.reject(error)
        );

        this.service.interceptors.response.use(
            (response) => {
                const {data} = response;
                if (!data) {
                    MessagePlugin.error('请求失败');
                    return Promise.reject(data);
                }
                return data;
            },
            (error: AxiosError) => {
                if (error.response) {
                    const {status} = error.response;
                    this.handleStatusCode(status);
                }
                MessagePlugin.error('请求失败');
                return Promise.reject(error);
            }
        );
    }

    private handleStatusCode(status: number) {
        switch (status) {
            case 401:
                MessagePlugin.error('登录失败，请重新登录');
                break;
            default:
                MessagePlugin.error('请求失败');
                break;
        }
    }

    get<T>(url: string, params?: object): Promise<ResponseData<T>> {
        return this.service.get(url, {params});
    }

    getFile(url: string, params?: object): Promise<any> {
        return this.service.get(url, {params, responseType: 'blob'});
    }
}

// 创建实例
const apiClient = new RequestHttp(AppConfig.getInstance().toAxiosConfig());

// 导出实例
export default apiClient;
