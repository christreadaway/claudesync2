## PII Prevention Rules

1. Never commit local file paths (like /Users/username/ or C:\Users\username\) to any repo. Use ~/ instead.
2. Never commit real institution names, addresses, phone numbers, emails, or staff/clergy names to repos. Use bracketed placeholders like [Parish Name], [Parish Address], [Parish Phone], [Staff Name].
3. Never commit API keys, tokens, passwords, or credentials to any repo.
4. Before any git commit, scan the staged files for PII. If found, replace it before committing.
5. The venmo-tip repo is excluded from all automated operations. Never touch it.
6. When creating product specs or status files that reference real institutions, always use placeholders in the repo copy. Real names can exist in Claude.ai conversations and Google Drive but NOT in GitHub.
