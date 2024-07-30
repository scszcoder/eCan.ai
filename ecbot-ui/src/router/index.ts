import { createRouter, createWebHashHistory } from 'vue-router'
import { routes } from './routes'

const router = createRouter({
    history: createWebHashHistory(),
    routes
})

// // 重定向匹配404页面
// router.resolve({
//     name: 'NotFound',
//     params: { pathMatch: ['not', 'found'] },
// }).href

export default router
