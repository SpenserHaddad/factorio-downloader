FROM python:3.15.0a1-slim-trixie
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt update
RUN apt install -y cron git

RUN git clone --depth 1 --branch v0.0.1 https://github.com/SpenserHaddad/factorio-downloader.git

#RUN mkdir /downloaded 
WORKDIR /factorio-downloader

RUN uv sync

#RUN echo "*/5 * * * * echo boop >> /downloaded/heartbeat.txt 2>&1" >> /etc/cron.d/factorio-dl
RUN echo "30 20 * * 1,3,5 git -C /factorio-downloader pull" >> /etc/cron.d/factorio-dl
RUN echo "45 20 * * 1,3,5 uv run /factorio-downloader/main.py --version=latest --build=expansion --outdir=/downloaded >> /downloaded/factorio-dl.log 2>&1" >> /etc/cron.d/factorio-dl
RUN chmod 0644 /etc/cron.d/factorio-dl
RUN crontab -n /etc/cron.d/factorio-dl
RUN crontab /etc/cron.d/factorio-dl
RUN touch /downloaded/factorio-dl.log

CMD ["cron", "&&", "tail", "-f", "/downloaded/factorio-dl.log"]
#CMD ["uv", "run", "/factorio-downloader/main.py", "--version=latest", "--build=expansion", "--outdir=/downloaded"]


