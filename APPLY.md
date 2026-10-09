# Apply from the root of YOUR local clone, in the terminal (NOT with Finder: it replaces whole folders and hides dot-folders)

    unzip -o ~/Downloads/stockmind-overlay-2.zip -d .
    rm -f APPLY.md
    ls .github/workflows/market-data.yml apps/web/vercel.json tests/integration/test_repo_policy.py
    git status --short | grep -c '^ D'      # must print 0
    git status --short | wc -l              # about 10
    git add -A && git commit -m "Public-repo data policy: build and deploy market data from Actions" && git push

Then follow docs/operations/real-market-data.md (steps 1-7).
