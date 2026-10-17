FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY checks.json server.py ./
COPY monitor ./monitor
COPY toolbox ./toolbox
COPY dashboard ./dashboard

RUN mkdir -p /app/data && useradd --create-home --uid 10001 dashboard \
    && chown -R dashboard:dashboard /app
USER dashboard

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=2)"

CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8080"]

