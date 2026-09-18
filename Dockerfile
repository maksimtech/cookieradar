FROM python:3.12-slim-bookworm
# Metadata OCI
LABEL maintainer="maksimtech <github@maksimtech.com>"
LABEL org.opencontainers.image.title="CookieRadar"
LABEL org.opencontainers.image.description="Cookie compliance auditor — GDPR art.5/6/7 — pre-consent, post-reject, GTM analysis"
LABEL org.opencontainers.image.source="https://github.com/maksimtech/cookieradar"
LABEL org.opencontainers.image.license="MIT"
# Dipendenze di sistema + Playwright
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends gnupg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
# Ambiente Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
# Playwright prima del sorgente: gli strati con Chromium restano in cache
# quando cambia solo il codice di cookieradar
RUN pip install --no-cache-dir --root-user-action=ignore "playwright>=1.40.0"
# Dipendenze di sistema di Chromium (richiedono root)
RUN playwright install-deps chromium
# Crea utente non-root
RUN useradd -m -u 1000 cookieradar && \
    mkdir -p /home/cookieradar/.cookieradar && \
    chown -R cookieradar:cookieradar /home/cookieradar
# Chromium installato come cookieradar, in ~/.cache/ms-playwright
USER cookieradar
RUN playwright install chromium
USER root
# Sorgente di cookieradar:
#   local (default, CI) → il codice di questo repository
#   pypi (release)      → cookieradar==COOKIERADAR_VERSION da PyPI
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
VOLUME ["/home/cookieradar/.cookieradar"]
ENTRYPOINT ["cookieradar"]
CMD ["--help"]
