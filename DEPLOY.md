# Deploying & Pushing to GitHub

## If Cursor Can't Connect to GitHub

Use **VS Code** or **GitHub Desktop** for git operations. Both work with the same local repo.

### Workflow

1. **Edit in Cursor** – Make changes, use AI, etc.
2. **Commit & push in VS Code or GitHub Desktop** – Use the Source Control panel or GitHub Desktop UI.

### First-Time Cleanup (remove store/ and db files from repo)

Your [GitHub repo](https://github.com/Warlord437/Context-Based-File-Search) currently has `store/` and `.DS_Store` committed. To remove them:

**Option A: Run the script (VS Code terminal)**

```bash
chmod +x scripts/clean-git-for-push.sh
./scripts/clean-git-for-push.sh
```

Then push from VS Code or GitHub Desktop.

**Option B: Manual commands**

```bash
git rm -r --cached store/
git rm --cached .DS_Store 2>/dev/null || true
git commit -m "Stop tracking store and local files"
```

Then push.

### .gitignore

`store/`, `*.db`, `.DS_Store`, and `*.egg-info/` are in `.gitignore`. After the cleanup above, they won't be committed again.
