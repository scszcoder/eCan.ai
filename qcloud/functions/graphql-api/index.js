/**
 * 腾讯云 SCF GraphQL API 入口
 *
 * 功能：
 * 1. SCF 云函数入口
 * 2. 接收 TCB Token 并验证
 * 3. 运行 Apollo Server 处理 GraphQL 请求
 *
 * 对应 AWS: Lambda + AppSync
 */

const { ApolloServer } = require('apollo-server-cloudfunctions');
const mysql = require('mysql2/promise');
const COS = require('cos-nodejs-sdk-v5');

const resolvers = require('./resolvers');
const typeDefs = require('./schema');

const CONFIG = {
  TDSQL_HOST: process.env.TDSQL_HOST,
  TDSQL_PORT: parseInt(process.env.TDSQL_PORT || '3306'),
  TDSQL_USER: process.env.TDSQL_USER,
  TDSQL_PASSWORD: process.env.TDSQL_PASSWORD,
  TDSQL_DATABASE: process.env.TDSQL_DATABASE,
  COS_BUCKET: process.env.COS_BUCKET,
  COS_REGION: process.env.COS_REGION || 'ap-guangzhou',
  COS_SECRET_ID: process.env.TENCENT_SECRET_ID,
  COS_SECRET_KEY: process.env.TENCENT_SECRET_KEY,
  TCB_ENV_ID: process.env.TCB_ENV_ID,
};

let mysqlPool = null;

async function getMySQLPool() {
  if (!mysqlPool) {
    mysqlPool = mysql.createPool({
      host: CONFIG.TDSQL_HOST,
      port: CONFIG.TDSQL_PORT,
      user: CONFIG.TDSQL_USER,
      password: CONFIG.TDSQL_PASSWORD,
      database: CONFIG.TDSQL_DATABASE,
      waitForConnections: true,
      connectionLimit: 20,
    });
  }
  return mysqlPool;
}

let cosClient = null;

function getCOSClient() {
  if (!cosClient) {
    cosClient = new COS({
      SecretId: CONFIG.COS_SECRET_ID,
      SecretKey: CONFIG.COS_SECRET_KEY,
      Region: CONFIG.COS_REGION,
    });
  }
  return cosClient;
}

async function verifyTCBToken(token) {
  if (!token) return { uid: 'anonymous', nickname: 'Anonymous' };

  try {
    const response = await fetch(
      `https://${CONFIG.TCB_ENV_ID}.service.tcloudbase.com/auth/v1/token/verify`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
      }
    );

    if (response.ok) {
      const data = await response.json();
      return { uid: data.uid, email: data.email, nickname: data.nickname || data.email };
    }
    return { uid: 'anonymous', nickname: 'Anonymous' };
  } catch (error) {
    console.error('Token verification failed:', error);
    return { uid: 'anonymous', nickname: 'Anonymous' };
  }
}

exports.main_handler = async (event, context) => {
  if (!global.apolloServer) {
    global.apolloServer = new ApolloServer({
      typeDefs,
      resolvers,
      dataSources: () => ({
        mysql: {
          pool: getMySQLPool,
          execute: async (sql, params = []) => {
            const pool = await getMySQLPool();
            const [rows] = await pool.execute(sql, params);
            return { records: rows };
          },
        },
        cos: {
          client: getCOSClient,
          bucket: CONFIG.COS_BUCKET,
        },
      }),
      context: async ({ event, context }) => {
        const headers = event.headers || {};
        const authHeader = headers['Authorization'] || headers['authorization'] || '';
        const token = authHeader.replace(/^Bearer\s+/i, '');
        const user = await verifyTCBToken(token);
        return {
          identity: { sub: user.uid, email: user.email, username: user.nickname },
          requestId: context.request_id,
        };
      },
      formatError: (error) => ({
        message: error.message,
        path: error.path,
        extensions: { code: error.extensions?.code || 'INTERNAL_ERROR' },
      }),
      introspection: process.env.NODE_ENV !== 'production',
      playground: process.env.NODE_ENV !== 'production',
    });
  }

  return global.apolloServer.handler(event, context);
};
