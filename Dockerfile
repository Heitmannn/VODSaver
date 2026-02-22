FROM python:3.12-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
  && pip install --no-cache-dir yt-dlp==2024.08.06

COPY vodsaver.py /app/vodsaver.py

ENTRYPOINT ["python", "/app/vodsaver.py"]
