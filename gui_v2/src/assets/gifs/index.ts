// 自动导入 src/assets/gifs 下所有 gif/mp4 文件
const modules = import.meta.glob('./*.{gif,mp4}', { eager: true, as: 'url' });

const agentGifs: string[] = Object.values(modules) as string[];

export default agentGifs; 