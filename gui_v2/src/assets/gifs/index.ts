// 通过打包器导入资源，确保开发/构建环境下都能得到正确的 URL
// 这些文件应位于本目录（src/assets/gifs）下
import a0 from './agent0.webm';
import a1 from './agent1.webm';
import a2 from './agent2.webm';
import a3 from './agent3.webm';
import a4 from './agent4.webm';
import a5 from './agent5.webm';

const agentGifs = [a0, a1, a2, a3, a4, a5];

export default agentGifs;

// 导出视频支持检测函数，供需要时调用
export function logVideoSupport() {
  const video = document.createElement('video');
  const formats = [
    { type: 'video/mp4; codecs=\"avc1.42E01E, mp4a.40.2\"', label: 'MP4 (H.264/AAC)' },
    { type: 'video/webm; codecs=\"vp8, vorbis\"', label: 'WebM (VP8/Vorbis)' },
    { type: 'video/webm; codecs=\"vp9\"', label: 'WebM (VP9)' },
    { type: 'video/ogg; codecs=\"theora\"', label: 'Ogg (Theora)' }
  ];
  formats.forEach(f => {
    const canPlay = video.canPlayType(f.type);
    console.log(`${f.label}: ${canPlay}`);
  });
}