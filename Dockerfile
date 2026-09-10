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
# Versione CookieRadar da installare
ARG COOKIERADAR_VERSION=2026.9.1
# Installa cookieradar da PyPI
RUN pip install --no-cache-dir --root-user-action=ignore \
    "cookieradar==${COOKIERADAR_VERSION}"
# Installa Playwright e Chromium
RUN playwright install chromium && \
    playwright install-deps chromium
# Crea utente non-root
RUN useradd -m -u 1000 cookieradar && \
    mkdir -p /home/cookieradar/.cookieradar && \
    chown -R cookieradar:cookieradar /home/cookieradar
USER cookieradar
WORKDIR /home/cookieradar
VOLUME ["/home/cookieradar/.cookieradar"]
ENTRYPOINT ["cookieradar"]
CMD ["--help"]
