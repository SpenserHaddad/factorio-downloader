FROM python:3.14.1-alpine
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /factorio-downloader
COPY pyproject.toml uv.lock README.md /factorio-downloader
COPY src/ /factorio-downloader/src

RUN ls -l /factorio-downloader/src/factorio_downloader && uv sync

RUN mkdir -p /etc/cron.d
RUN echo "* 18 * * 1 uv run --directory /factorio-downloader python -m factorio_downloader --version=latest --build=expansion --outdir=/downloaded >> /downloaded/factorio-dl.log 2>&1" >> /etc/cron.d/factorio-dl
RUN chmod 0644 /etc/cron.d/factorio-dl && crontab /etc/cron.d/factorio-dl
RUN mkdir /downloaded && touch /downloaded/factorio-dl.log

CMD ["crond", "&&", "tail", "-f", "/var/log/cron.log"]
