import {createApp} from 'vue'
import App from './App.vue'
import router from './router'
import 'tdesign-vue-next/es/style/index.css';
import TDesign from 'tdesign-vue-next';
import i18n from './i18n/index'

createApp(App)
    .use(i18n)
    .use(TDesign)
    .use(router)
    .mount('#app')
