#!/bin/bash
set -euo pipefail

INIT_FILE="cookieradar/__init__.py"

fail() {
    echo "❌ $*" >&2
    exit 1
}

if [ $# -lt 1 ] || [ -z "$1" ]; then
    echo "❌ Uso: ./release.sh <versione>" >&2
    echo "   Esempio: ./release.sh 2026.09.3" >&2
    exit 1
fi

VERSION="$1"
TAG="v${VERSION}"

# Versione calendario: YYYY.MM.N (il tag v<VERSION> deve coincidere con __init__.py,
# publish.yml lo verifica)
if ! [[ "$VERSION" =~ ^[0-9]{4}\.(0[1-9]|1[0-2])\.[0-9]+$ ]]; then
    fail "Versione non valida: ${VERSION} (formato atteso YYYY.MM.N, es. 2026.09.3)"
fi

echo "🚀 Releasing CookieRadar ${TAG}"

BRANCH=$(git rev-parse --abbrev-ref HEAD)
[ "$BRANCH" = "main" ] || fail "Non sei su main (branch corrente: ${BRANCH})"

[ -z "$(git status --porcelain)" ] || fail "Working tree non pulito — committa prima le modifiche"

git fetch --quiet --tags origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] \
    || fail "main locale non è allineato con origin/main — fai pull/push prima della release"

if git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null \
    || [ -n "$(git ls-remote --tags origin "refs/tags/${TAG}")" ]; then
    fail "Tag ${TAG} già esistente"
fi

OLD_VERSION=$(python3 - "$INIT_FILE" <<'EOF'
import re, sys
print(re.search(r'__version__ = "(.+?)"', open(sys.argv[1]).read()).group(1))
EOF
)
[ "$OLD_VERSION" != "$VERSION" ] || fail "${VERSION} è già la versione corrente"

echo "📝 Bump versione: ${OLD_VERSION} → ${VERSION}"
python3 - "$INIT_FILE" "$VERSION" <<'EOF'
import re, sys
path, version = sys.argv[1], sys.argv[2]
text = open(path).read()
new, count = re.subn(r'__version__ = ".+?"', f'__version__ = "{version}"', text, count=1)
assert count == 1, "__version__ not found"
open(path, "w").write(new)
EOF

git add "$INIT_FILE"
git commit -m "chore: bump version to ${VERSION}"
git tag -a "$TAG" -m "CookieRadar ${VERSION}"

echo "📤 Push main + tag ${TAG}..."
# Atomico: o arrivano entrambi o nessuno dei due
git push --atomic origin main "$TAG"

echo "✅ Done! GitHub Actions si occupa del resto"
echo "   → Release: github.com/maksimtech/cookieradar/releases"
echo "   → PyPI:    pypi.org/project/cookieradar"
echo "   → Docker:  hub.docker.com/r/maksimtech/cookieradar"
