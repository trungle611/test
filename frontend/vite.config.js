import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), ''), ...process.env };
  if (env.VERCEL === '1' && !/^https:\/\/[^/]+(?:\/.*)?$/.test(env.VITE_API_URL || '')) {
    throw new Error('Đặt VITE_API_URL bằng URL HTTPS của backend trước khi build trên Vercel.');
  }
  return {
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      allowedHosts: (env.DEV_ALLOWED_HOSTS || '')
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      proxy: {
        '/api': {
          target: env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  };
});
