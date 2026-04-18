# syntax=docker/dockerfile:1.7

FROM python:3.12-alpine AS runtime

RUN apk add --no-cache build-base postgresql-dev postgresql-client

WORKDIR /host

# Install the Escalated package from the repo root as an editable install.
COPY pyproject.toml setup.cfg MANIFEST.in ./package-src/
COPY escalated ./package-src/escalated
RUN pip install --no-cache-dir ./package-src \
    && pip install --no-cache-dir django dj-database-url psycopg2-binary

COPY docker/host-app/ ./
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

ENTRYPOINT ["entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
