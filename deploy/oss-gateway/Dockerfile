# دروازهٔ ذخیره‌سازی مستقل روی MinIO (سازگار با قرارداد ObjectStorage پروژه)
# سازگار با سرورهای دارای شبکهٔ فیلترشده: pip از آینهٔ در دسترس runflare استفاده
# می‌کند و به curl/apt نیازی نیست (healthcheck با پایتون انجام می‌شود).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -i https://mirror-pypi.runflare.com/simple -r /srv/requirements.txt

COPY app.py /srv/app.py

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9000/healthz', timeout=5).status==200 else 1)"]

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
