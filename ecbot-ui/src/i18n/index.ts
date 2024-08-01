import {createI18n} from 'vue-i18n'
// 语言包
import zhCn from './lang/zh-cn'
import en from './lang/en'

const i18n = createI18n({
    legacy: false, // 设置为 false，启用 composition API 模式
    locale: sessionStorage.getItem('localeLang') || 'zhCn',
    messages: {
        zhCn,
        en,
    },
})
export default i18n
