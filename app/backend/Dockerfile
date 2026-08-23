# ایمیج تولیدی بک‌اند «ویدارا - نسخه جلسات»
# سازگار با سرورهای دارای شبکهٔ فیلترشده:
#   * pip از آینهٔ در دسترس (mirror-pypi.runflare.com) استفاده می‌کند.
#   * ffmpeg/ffprobe به‌صورت باینری استاتیک و فونت‌ها از پیش در bundle/ آماده‌اند
#     (بدون نیاز به apt / deb.debian.org).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Tehran

WORKDIR /srv/backend

# ابزارهای صوت (استاتیک — بدون apt) و فونت‌ها برای خروجی اسناد فارسی
COPY bundle/bin/ffmpeg bundle/bin/ffprobe /usr/local/bin/
COPY bundle/fonts/ /usr/share/fonts/truetype/
RUN chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe

COPY requirements.txt requirements.default ./
RUN pip install --no-cache-dir -i https://mirror-pypi.runflare.com/simple -r requirements.txt \
    && pip install --no-cache-dir -i https://mirror-pypi.runflare.com/simple -r requirements.default

COPY . /srv/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=6 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status==200 else 1)"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
