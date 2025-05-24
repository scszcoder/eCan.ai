/**
 * 登录相关类型定义
 */

/**
 * 登录响应类型
 */
export interface LoginResponse {
    /** 用户令牌 */
    token: string;
    /** 响应消息 */
    message: string;
}

/**
 * 登录请求参数
 */
export interface LoginParams {
    /** 用户名 */
    username: string;
    /** 密码 */
    password: string;
}

/**
 * 登录表单值类型
 */
export interface LoginFormValues {
    /** 用户名 */
    username: string;
    /** 密码 */
    password: string;
}

/**
 * 登录组件属性类型
 */
export interface LoginProps {
    /** 登录成功后的回调 */
    onLoginSuccess?: (token: string) => void;
} 