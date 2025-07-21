#!/bin/bash

echo "🔍 Checking for upstream updates..."

# Fetch upstream changes
git fetch upstream

# Check if there are new commits
BEHIND=$(git rev-list --count HEAD..upstream/main)

if [ "$BEHIND" -eq 0 ]; then
    echo "✅ Your fork is up to date with upstream!"
    exit 0
fi

echo "📦 Found $BEHIND new commits in upstream"
echo ""

echo "📋 New commits:"
git log HEAD..upstream/main --oneline --graph

echo ""
echo "📁 Modified files:"
git diff --name-only HEAD..upstream/main

echo ""
echo "🔍 Do you want to see the detailed changes? (y/n)"
read -r response

if [[ "$response" =~ ^[Yy]$ ]]; then
    echo ""
    echo "📝 Detailed changes:"
    git diff HEAD..upstream/main
fi

echo ""
echo "🤔 Do you want to merge these changes? (y/n)"
read -r merge_response

if [[ "$merge_response" =~ ^[Yy]$ ]]; then
    echo "🔄 Merging upstream changes..."
    git merge upstream/main
    echo "✅ Merge completed!"
else
    echo "⏸️  Merge skipped. Changes are fetched but not applied."
    echo "   Run 'git merge upstream/main' when you're ready."
fi
