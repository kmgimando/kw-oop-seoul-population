FROM python:3.12-slim

# .pyc를 만들지 않고, 로그를 버퍼링 없이 바로 출력
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 라이브러리 목록만 먼저 복사해서, 코드만 바뀌면 설치 단계는 캐시를 재사용
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8767

# 자동 갱신 모드에서는 한 worker가 갱신과 조회를 모두 맡으며, fork 전에 갱신 스레드를 시작하지 않는다.
CMD ["sh", "-c", "if [ -n \"$SEOUL_OPEN_API_KEY\" ]; then set -- --workers 1 --threads 4; else set -- --workers \"${WEB_CONCURRENCY:-2}\" --preload; fi; exec gunicorn --bind \"0.0.0.0:${PORT:-8767}\" \"$@\" 'dashboard_app:create_dashboard_app()'"]
