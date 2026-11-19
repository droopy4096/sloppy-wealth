#!/usr/bin/env bash
# Add the published container image to the GitHub Release of a tag (called by
# .github/workflows/container.yml after the image is pushed).
#   release-container-notes.sh TAG IMAGE DIGEST "TAGS (newline-separated)" PLATFORMS
# A release already made for the tag (on the web page or with gh) keeps its notes and
# gets a "Container image" section; on a re-run that section is replaced. Without a
# release, one is created with GitHub's generated notes. A tag with a "-" (1.2.3-rc.1)
# is marked as a pre-release.
set -euo pipefail
tag=$1 image=$2 digest=$3 tags=$4 platforms=$5
marker="<!-- container-image -->"

section="$marker
## Container image

\`\`\`
docker pull $image:$tag
docker run --rm -p 5000:5000 $image:$tag
\`\`\`

Then open http://127.0.0.1:5000. (\`podman\` works the same way.)

- Tags: $(printf '%s\n' "$tags" | sed 's/.*:/`/; s/$/`/' | paste -sd ' ' | sed 's/ /, /g')
- Digest: \`$digest\` (pin it with \`$image@$digest\`)
- Platforms: ${platforms//,/, }
- Package: https://github.com/${GITHUB_REPOSITORY}/pkgs/container/${image##*/}"

if ! gh release view "$tag" >/dev/null 2>&1; then
  pre=(); [[ $tag == *-* ]] && pre=(--prerelease)
  gh release create "$tag" --verify-tag --title "$tag" --generate-notes "${pre[@]}"
fi
# The section always goes last, so an earlier run's section is everything after it.
body=$(gh release view "$tag" --json body --jq .body)
body=${body%%"$marker"*}
body=${body%"${body##*[![:space:]]}"}               # trim trailing blank lines
printf '%s\n\n%s\n' "$body" "$section" > notes.md
gh release edit "$tag" --notes-file notes.md
