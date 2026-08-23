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
RUN pnpm run build


FROM nginx:1.27-alpine AS runtime

COPY --from=builder /srv/frontend/dist /usr/share/nginx/html

RUN printf '%s\n' \
    'server {' \
    '    listen 80;' \
    '    server_name _;' \
    '    root /usr/share/nginx/html;' \
    '    index index.html;' \
    '    gzip on;' \
    '    gzip_types text/plain text/css application/javascript application/json image/svg+xml;' \
    '    location /assets/ {' \
    '        expires 30d;' \
    '        add_header Cache-Control "public, max-age=2592000, immutable";' \
    '        try_files $uri =404;' \
    '    }' \
    '    location = /index.html {' \
    '        add_header Cache-Control "no-store";' \
    '    }' \
    '    location / {' \
    '        try_files $uri $uri/ /index.html;' \
    '    }' \
    '}' > /etc/nginx/conf.d/default.conf

EXPOSE 80