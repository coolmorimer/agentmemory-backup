# Security model

AutoDev assumes repository text, issue text, web pages, model output, and memory snippets can be
hostile. Context marks untrusted material, normalizes repository-relative paths, caps size, and
redacts common credential forms. Commands are argv arrays and policy checked; adapters avoid shell
execution. Git commits are scoped to the task and refused if unrelated staged changes exist.

The secret scanner blocks `.env` files and common token/private-key patterns before commit. Private
projects can route only to local or explicitly private-code-capable providers; `LOCAL_ONLY` never
routes source to cloud. Paid models require both an enable flag and non-zero budget.

Production and destructive operations are approval-gated. Logs carry correlation IDs but omit query
strings, headers, secrets, and raw provider credentials. Run an independent repository secret scan
before publishing any remote.
