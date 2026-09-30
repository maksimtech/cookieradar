FROM python:3.12-slim-trixie
# OCI metadata
LABEL maintainer="maksimtech <github@maksimtech.com>"
LABEL org.opencontainers.image.title="CookieRadar"
LABEL org.opencontainers.image.description="Cookie compliance auditor — GDPR art.5/6/7 — pre-consent, post-reject, GTM analysis"
LABEL org.opencontainers.image.source="https://github.com/maksimtech/cookieradar"
LABEL org.opencontainers.image.licenses="MIT"
# Security patches for the base system. Chromium's own dependencies arrive
# through `playwright install-deps` further down.
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
# Python environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
# Playwright before the source, so the layers holding Chromium stay cached
# when only cookieradar's own code has changed.
RUN pip install --no-cache-dir --root-user-action=ignore "playwright>=1.40.0"
# Chromium's system dependencies, which need root
RUN playwright install-deps chromium
# A non-root user to run as
RUN useradd -m -u 1000 cookieradar
# Chromium installed as cookieradar, into ~/.cache/ms-playwright
USER cookieradar
RUN playwright install chromium
USER root
# Where cookieradar comes from:
#   local (default, CI) → the code in this repository
#   pypi (release)      → cookieradar==COOKIERADAR_VERSION from PyPI
ARG COOKIERADAR_SOURCE=local
ARG COOKIERADAR_VERSION=
COPY pyproject.toml README.md LICENSE /app/src/
COPY cookieradar/ /app/src/cookieradar/
RUN case "${COOKIERADAR_SOURCE}" in \
        local) pip install --no-cache-dir --root-user-action=ignore /app/src ;; \
        pypi) test -n "${COOKIERADAR_VERSION}" || { echo "COOKIERADAR_VERSION is required with COOKIERADAR_SOURCE=pypi" >&2; exit 1; } && \
              pip install --no-cache-dir --root-user-action=ignore "cookieradar==${COOKIERADAR_VERSION}" ;; \
        *) echo "COOKIERADAR_SOURCE must be 'local' or 'pypi'" >&2; exit 1 ;; \
    esac && \
    rm -rf /app/src
USER cookieradar
WORKDIR /home/cookieradar
ENTRYPOINT ["cookieradar"]
CMD ["--help"]
