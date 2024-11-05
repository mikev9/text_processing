FROM python:3.12.2-bullseye AS builder

ARG SERVICE_NAME
ARG POETRY_HOME
ARG POETRY_CACHE_DIR

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=${POETRY_CACHE_DIR}

RUN python -m venv $POETRY_HOME && $POETRY_HOME/bin/pip install poetry==1.8.4

WORKDIR /app

COPY pyproject.toml poetry.lock .
COPY shared /app/shared

RUN --mount=type=cache,target=$POETRY_CACHE_DIR $POETRY_HOME/bin/poetry install --no-root
RUN --mount=type=cache,target=$POETRY_CACHE_DIR $POETRY_HOME/bin/poetry install --no-root --with ${SERVICE_NAME}


FROM python:3.12.2-slim-bullseye AS runtime

ARG SERVICE_NAME

ENV VIRTUAL_ENV=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY shared /app/shared

COPY text_processing/${SERVICE_NAME}/ /app

ENTRYPOINT ["python", "/app/main.py"]
