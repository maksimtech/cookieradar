#!/bin/bash
set -e

# Leggi versione da __init__.py
VERSION=$(python3 -c "import re; content=open('cookieradar/__init__.py').read(); print(re.search(r'__version__ = \"(.+?)\"', content).group(1))")
TAG="v${VERSION}"

echo "🚀 Releasing CookieRadar ${TAG}"

# Verifica working tree pulito
if [ -n "$(git status --porcelain)" ]; then
    echo "❌ Working tree non pulito — committa prima le modifiche"
    exit 1
fi

# Verifica che il tag non esista già
if git tag | grep -q "^${TAG}$"; then
    echo "❌ Tag ${TAG} già esistente"
    exit 1
fi

# Push main
echo "📤 Push main..."
git push origin main

# Crea e pusha tag
echo "🏷️  Tag ${TAG}..."
git tag ${TAG}
git push origin ${TAG}

echo "✅ Tag ${TAG} pushato — GitHub Actions si occupa del resto"
echo "   → Release: github.com/maksimtech/cookieradar/releases"
echo "   → PyPI:    pypi.org/project/cookieradar"
echo "   → Docker:  hub.docker.com/r/maksimtech/cookieradar"
