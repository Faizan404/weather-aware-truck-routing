FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Run as an unprivileged user.
RUN groupadd --system app && useradd --system --gid app --home-dir /app --no-create-home app
WORKDIR /app
RUN chown app:app /app

COPY --chown=app:app requirements.txt .
RUN pip install -r requirements.txt
COPY --chown=app:app . .

USER app
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput

EXPOSE 8000
# One process with threads: the 1 request/second throttle for the public
# routing server, the weather budget and the trip locks (core/http.py,
# weather/open_meteo.py, routing/service.py) are per process, so one worker
# keeps them exact. --timeout stays above PLAN_DEADLINE_SECONDS (60), which
# ends slow requests with a 503 first.
CMD gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 1 --threads 8 \
    --timeout 90 --graceful-timeout 30 --keep-alive 5 \
    --access-logfile -
