import {defineConfig} from 'vite';
import {resolve} from 'path'
import svgLoader from 'vite-svg-loader';
import vue from "@vitejs/plugin-vue";

export default defineConfig({
    plugins: [vue(), svgLoader(),],
    server: {
        open: true,
        proxy: {
            '/api': {
                target: 'http://localhost:3000',
                changeOrigin: true,
                rewrite: (path) => path.replace(/^\/api/, '')
            }
        },
        host: '0.0.0.0',
        port: 3000
    },
    resolve: {
        alias: {
            "@": resolve(__dirname, 'src'), // 设置 '@' 指向'src' 目录，'src' 为实际存放代码的目录
            "#": resolve(__dirname, "types")
        },
        extensions: ['.js', '.json', '.ts'] // 使用路径别名时想要省略的后缀名，可以根据需要自行增减
    }, build: {
        terserOptions: {
            compress: {
                drop_debugger: true,
                drop_console: true
            }
        },
        rollupOptions: {

            output: {
                manualChunks: {
                    // 将 Vue 相关的库打包到一个名为 'vue-chunk' 的 chunk 中
                    'vue-chunk': ['vue', 'vue-router'],
                    'fabric-chunk': ['fabric'],
                    'tdesign-icon-chunk': ['tdesign-icons-vue-next'],
                    'tdesign-chunk': ['tdesign-vue-next'],
                },
            },
        },
    },
})
