# ایمیج تولیدی فرانت: ساخت با Node و سرو استاتیک با nginx
FROM node:20-bookworm-slim AS builder

WORKDIR /srv/frontend

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    CI=true

# نسخهٔ pnpm از فیلد packageManager در package.json خوانده و همان دانلود می‌شود.
RUN corepack enable

COPY package.json pnpm-lock.yaml* ./
# بدون fallback: اگر lockfile با package.json ناسازگار باشد، بیلد باید بلند
# شکست بخورد نه اینکه بی‌صدا وابستگی دیگری نصب کند.
RUN pnpm install --frozen-lockfile

COPY . .

# در استقرار مستقل، فرانت و API روی همان دامنه هستند؛ پس آدرس پایه نسبی می‌ماند.
ENV VITE_API_BASE_URL=""
# دامنهٔ عمومی این استقرار برای sitemap.xml و robots.txt. هر استقرار (نسخهٔ
# جلسات، نسخهٔ HR، …) این مقدار را در زمان بیلد خودش تعیین می‌کند تا هیچ
# دامنه‌ای در کد ثابت نماند.
ARG VITE_SITE_URL="https://vidara-meeting.ir"
ENV VITE_SITE_URL=$VITE_SITE_URL
RUN pnpm run build

# پیش‌فشرده‌سازی فایل‌های استاتیک: nginx با gzip_static نسخهٔ .gz را بدون مصرف
# CPU سرو می‌کند و نسبت فشرده‌سازی بهتری هم می‌دهد (سطح ۹ در زمان ساخت).
# فایل اصلی دست‌نخورده می‌ماند تا درخواست‌های بدون Accept-Encoding هم پاسخ بگیرند.
RUN if ! command -v gzip >/dev/null 2>&1; then \
      apt-get update && apt-get install -y --no-install-recommends gzip \
      && rm -rf /var/lib/apt/lists/*; \
    fi \
 && find dist -type f \( -name '*.js' -o -name '*.css' -o -name '*.html' \
      -o -name '*.svg' -o -name '*.json' -o -name '*.txt' \) \
      -size +1k -exec gzip -9 -k {} + \
 && echo "precompressed files: $(find dist -name '*.gz' | wc -l)"


FROM nginx:1.27-alpine AS runtime

COPY --from=builder /srv/frontend/dist /usr/share/nginx/html

RUN printf '%s\n' \
    'server {' \
    '    listen 80;' \
    '    server_name _;' \
    '    root /usr/share/nginx/html;' \
    '    index index.html;' \
    '    gzip on;' \
    '    gzip_vary on;' \
    '    gzip_static on;' \
    '    gzip_comp_level 6;' \
    '    gzip_min_length 1024;' \
    '    gzip_proxied any;' \
    '    gzip_types text/plain text/css application/javascript application/json application/manifest+json image/svg+xml application/wasm;' \
    '    location /assets/ {' \
    '        add_header Cache-Control "public, max-age=2592000, immutable" always;' \
    '        add_header Vary "Accept-Encoding" always;' \
    '        try_files $uri =404;' \
    '    }' \
    '    location = /index.html {' \
    '        add_header Cache-Control "no-store" always;' \
    '    }' \
    '    location / {' \
    '        try_files $uri $uri/ /index.html;' \
    '    }' \
    '}' > /etc/nginx/conf.d/default.conf

EXPOSE 80