// 只导出 public/assets/gifs 下的 webm 文件路径
// 使用相对路径以支持 file:// 协议
const agentGifs = [
  './assets/gifs/agent0.webm',
  './assets/gifs/agent1.webm',
  './assets/gifs/agent2.webm',
  './assets/gifs/agent3.webm',
  './assets/gifs/agent4.webm',
  './assets/gifs/agent5.webm',
];

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