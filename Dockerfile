FROM python:3.14.1-alpine
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /factorio-downloader
COPY pyproject.toml uv.lock README.md /factorio-downloader
COPY src/ /factorio-downloader/src

RUN ls -l /factorio-downloader/src/factorio_downloader && uv sync

RUN mkdir -p /etc/cron.d
RUN mkdir /downloaded && touch /downloaded/factorio-dl.log

COPY docker-start.sh /docker-start.sh
RUN chmod +x /docker-start.sh

CMD ["/docker-start.sh"]
