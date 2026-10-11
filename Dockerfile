FROM caddy:2 AS proxy
FROM python:3.11-slim
COPY --from=proxy /usr/bin/caddy /usr/bin/caddy
RUN cp /usr/bin/caddy /tmp/caddy-unprivileged && mv /tmp/caddy-unprivileged /usr/bin/caddy
WORKDIR /app
COPY download_build.py /tmp/download_build.py
RUN python /tmp/download_build.py
RUN pip install --no-cache-dir -r LocalServer/requirements.txt
COPY player_service.py LocalServer/player_service.py
COPY economy.py community.py LocalServer/
ENV CF_UNLIMITED_COINS_USERNAME=jesusinmuha
ENV PORT=10000 CF_ENABLE_QA=0 CF_DATA_DIR=/tmp/counterflame-data PYTHONUNBUFFERED=1
EXPOSE 10000
CMD ["python", "LocalServer/Deploy/Render/start.py"]

