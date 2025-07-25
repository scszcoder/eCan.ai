import React, { useRef } from 'react';
import styled from '@emotion/styled';

const IFRAME_URL = 'http://127.0.0.1:9621';

const IframeContainer = styled.div`
  height: 100%;
  width: 100%;
`;

const KnowledgePlatform: React.FC = () => {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // 判断是否为开发环境
  const isDev = process.env.NODE_ENV === 'development';

  // 需要注入的脚本内容
  const injectedScript = `
    (function() {
      try {
        // 隐藏 <span class="font-bold md:inline-block">LightRAG</span>
        var spans = document.querySelectorAll('span.font-bold.md\\:inline-block');
        spans.forEach(function(span) {
          if (span.textContent && span.textContent.trim() === 'LightRAG') {
            span.style.display = 'none';
          }
        });
        // 仅非开发环境隐藏 class 包含 'font-medium' 且文本为 'API' 的 button
        if ('${!isDev}') {
          var buttons = document.querySelectorAll('button.font-medium');
          buttons.forEach(function(btn) {
            if (btn.textContent && btn.textContent.trim() === 'API') {
              btn.style.display = 'none';
            }
          });
        }
        // 隐藏 href 包含 'github.com/HKUDS/LightRAG' 的 <a> 元素
        var links = document.querySelectorAll('a[href*="github.com/HKUDS/LightRAG"]');
        links.forEach(function(link) {
          link.style.display = 'none';
        });
      } catch (e) { console.error('注入脚本错误', e); }
    })();
  `;

  const handleIframeLoad = () => {
    const iframe = iframeRef.current;
    if (iframe && iframe.contentWindow) {
      iframe.contentWindow.postMessage(
        {
          type: 'INJECT_SCRIPT',
          script: injectedScript,
        },
        IFRAME_URL
      );
    }
  };

  return (
    <IframeContainer>
      <style>
        {`
          .ant-layout-content {
              padding: 2px !important;
              margin: 2px !important;
          }
        `}
      </style>
      <iframe
            ref={iframeRef}
            src={IFRAME_URL}
            title="eCan.ai Graph KB"
            style={{ width: '100%', height: '100%', border: 'none' }}
            allowFullScreen
            onLoad={handleIframeLoad}
          />
    </IframeContainer>
  );
};

export default KnowledgePlatform; 