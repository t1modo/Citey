#!/usr/bin/env bash
# Prints, as Markdown, the SQL that this branch's new Alembic migrations
# would run, and the SQL that would undo them. CI adds it to the job
# summary so a reviewer reads the actual statements, not only the Python.
#
# Run from backend/ with any DATABASE_URL set (no connection is made):
#   ../.github/scripts/migration-draft.sh origin/main
set -euo pipefail

base_ref="${1:?usage: migration-draft.sh <base-ref>}"

head_rev="$(uv run --frozen alembic heads | awk '{print $1}')"

# The newest migration the base branch has, if it has any.
base_rev=""
if git cat-file -e "${base_ref}:backend/migrations/versions" 2>/dev/null; then
  tmp="$(mktemp -d)"
  git worktree add --quiet --detach "$tmp" "$base_ref"
  # `heads` only reads the scripts; it never runs env.py or connects.
  base_rev="$(uv run --frozen alembic -c "$tmp/backend/alembic.ini" heads | awk '{print $1}')"
  git worktree remove --force "$tmp"
fi

echo "## Migration SQL draft"
echo
if [ "$base_rev" = "$head_rev" ]; then
  echo "No new migrations on this branch (head is \`${head_rev:-none}\`)."
  exit 0
fi

if [ -n "$base_rev" ]; then
  up_range="${base_rev}:head"
  down_range="head:${base_rev}"
  echo "From \`${base_rev}\` (\`${base_ref}\`) to \`${head_rev}\`. Review it before merging."
else
  up_range="head"
  down_range="head:base"
  echo "\`${base_ref}\` has no migrations yet; this is the whole schema, up to \`${head_rev}\`."
fi

echo
echo "### Upgrade"
echo
echo '```sql'
uv run --frozen alembic upgrade "$up_range" --sql 2>/dev/null
echo '```'
echo
echo "<details><summary>Downgrade (undo)</summary>"
echo
echo '```sql'
uv run --frozen alembic downgrade "$down_range" --sql 2>/dev/null
echo '```'
echo
echo "</details>"
