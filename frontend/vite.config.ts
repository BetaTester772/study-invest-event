/// <reference types="vitest/config" />
import { defineConfig, loadEnv, type HtmlTagDescriptor, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';

const imagePath = '/images/study-invest-preview.jpg';

/** Social crawlers read the initial HTML without running React. */
function socialPreview(siteUrl?: string): Plugin {
  let origin: string | undefined;
  if (siteUrl?.trim()) {
    const url = new URL(siteUrl.trim());
    if (
      !['http:', 'https:'].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.pathname !== '/' ||
      url.search ||
      url.hash
    ) {
      throw new Error('VITE_SITE_URL에는 경로 없이 공개 웹 주소만 설정하세요 (예: https://study.example.com).');
    }
    origin = url.origin;
  }

  return {
    name: 'study-invest-social-preview',
    configResolved(config) {
      if (config.command === 'build' && !origin) {
        config.logger.warn(
          'VITE_SITE_URL이 비어 있어 미리보기 이미지에 상대 경로를 사용합니다. 공개 배포 시 웹 주소를 설정하세요.',
        );
      }
    },
    transformIndexHtml() {
      const imageUrl = origin ? new URL(imagePath, origin).href : imagePath;
      const tags: HtmlTagDescriptor[] = [
        { tag: 'meta', attrs: { property: 'og:image', content: imageUrl }, injectTo: 'head' },
        { tag: 'meta', attrs: { name: 'twitter:image', content: imageUrl }, injectTo: 'head' },
      ];
      if (origin) {
        tags.push({ tag: 'meta', attrs: { property: 'og:url', content: `${origin}/` }, injectTo: 'head' });
      }
      return tags;
    },
  };
}

export default defineConfig(({ mode }) => ({
  plugins: [react(), socialPreview(loadEnv(mode, '.', 'VITE_').VITE_SITE_URL)],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: { modules: { classNameStrategy: 'non-scoped' } },
  },
}));
