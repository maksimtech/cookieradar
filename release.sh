#!/bin/bash
set -e

if [ -z "$1" ]; then
    echo "❌ Uso: ./release.sh <versione>"
    echo "   Esempio: ./release.sh 2026.09.3"
    exit 1
fi

VERSION="$1"
TAG="v${VERSION}"

echo "🚀 Releasing CookieRadar ${TAG}"

if [ -n "$(git status --porcelain)" ]; then
    echo "❌ Working tree non pulito — committa prima le modifiche"
    exit 1
fi

if git tag | grep -q "^${TAG}$"; then
    echo "❌ Tag ${TAG} già esistente"
    exit 1
fi

OLD_VERSION=$(python3 -c "import re; content=open('cookieradar/__init__.py').read(); print(re.search(r'__version__ = \"(.+?)\"', content).group(1))")
echo "📝 Bump versione: ${OLD_VERSION} → ${VERSION}"
sed -i "s/__version__ = \"${OLD_VERSION}\"/__version__ = \"${VERSION}\"/" cookieradar/__init__.py

git add cookieradar/__init__.py
git commit -m "chore: bump version to ${VERSION}"

echo "📤 Push main..."
git push origin main

echo "🏷️  Tag ${TAG}..."
git tag ${TAG}
git push origin ${TAG}

echo "✅ Done! GitHub Actions si occupa del resto"
echo "   → Release: github.com/maksimtech/cookieradar/releases"
echo "   → PyPI:    pypi.org/project/cookieradar"
echo "   → Docker:  hub.docker.com/r/maksimtech/cookieradar"
