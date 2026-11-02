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

# 전체 CSV를 시작 시 로딩하고 worker에 공유한다. 샘플은 로컬 별도 진입점으로 유지한다.
# 0.0.0.0: 컨테이너 밖(브라우저)의 접속도 받음 / PORT가 없으면 8767 사용
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8767} --workers ${WEB_CONCURRENCY:-2} --preload 'dashboard_app:create_dashboard_app()'"]
