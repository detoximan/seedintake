# Seeds

Machine-readable Seed markdown files will be created here by Seed Pipeline v0.1.

Expected path pattern:

```text
/Inbox/YYYY/YYYY-MM-DD-NNN.md
```

Seed files are raw source artifacts. After creation, their original content must not be edited manually. If a created Seed is wrong, fix it through the synchronization and error-handling rules in:

- `/architecture/system_contracts.md`
- `/architecture/error_contract.md`
- `/architecture/seed_pipeline_scaffold.md`

Dry-run and sandbox checks must not write final Seed files here.

Minimal Seed markdown format:

```markdown
status: new

[2026-04-27-001](https://docs.google.com/document/d/...)

# Комментарий Павла

...

# Источник для обработки

...
```

Full dossier, processing details and technical runtime data belong in Google Doc, Google Sheet, Seed plan or runtime logs, not in the final markdown file.
