# Single stage: this app has no frontend build step and no compiled
# extension that genuinely needs a separate build image (rapidfuzz ships
# prebuilt wheels for this platform) -- a multi-stage build would add
# complexity this project has nothing to trim.
FROM python:3.12-slim

WORKDIR /app

# Without this, Python block-buffers stdout when it is not a terminal (as
# under Docker), so the "[startup] analysis ran/skipped" line only appears
# after uvicorn's own log lines -- or not at all until the buffer fills.
ENV PYTHONUNBUFFERED=1

# Dependencies first, so editing application code doesn't invalidate the
# (much slower) dependency-install layer on a rebuild.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# No RUN step analyzes the corpus at build time: the pipeline runs once at
# container STARTUP instead (app/main.py's lifespan), the one point where
# the data volume -- where its results are stored -- is actually mounted.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
