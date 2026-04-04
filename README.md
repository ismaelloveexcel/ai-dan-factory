# GitHub Factory (Minimal Production Structure)

This repository is a minimal factory that:
1. Creates a GitHub project repository from a template
2. Injects a BuildBrief into placeholder product files
3. Triggers deployment through Vercel API

## Folder Structure

```text
.
├── .github/
│   └── workflows/
│       └── factory-build.yml
├── scripts/
│   ├── create_project.py
│   ├── inject_brief.py
│   └── deploy.py
└── templates/
    └── saas-template/
        ├── .gitignore
        ├── PRODUCT_BRIEF.md
        ├── app/
        │   ├── api/
        │   │   └── lead/
        │   │       └── route.ts
        │   ├── globals.css
        │   ├── layout.tsx
        │   └── page.tsx
        ├── next-env.d.ts
        ├── next.config.js
        ├── package.json
        ├── product.config.json
        └── tsconfig.json
```

## Template Behavior (`templates/saas-template`)

- Next.js 14 app (App Router)
- Single landing page with one CTA button
- Hero section that reads `PRODUCT_BRIEF.md` and displays:
  - Product name
  - Problem
  - Solution
  - CTA
- API route: `POST /api/lead`

## Scripts

### `scripts/create_project.py`
Creates a GitHub repo from a template repo using GitHub API.

Example:
```bash
python scripts/create_project.py \
  --project-id acme-saas \
  --org your-org
```

Environment:
- `GITHUB_TOKEN` (required unless `--dry-run`)
- `TEMPLATE_OWNER` / `TEMPLATE_REPO` (optional if `GITHUB_REPOSITORY` is available)

### `scripts/inject_brief.py`
Takes BuildBrief JSON and generates:
- `PRODUCT_BRIEF.md`
- `product.config.json`

Example:
```bash
python scripts/inject_brief.py \
  --project-dir templates/saas-template \
  --brief-json '{"project_id":"acme-saas","product_name":"Acme","problem":"Ops chaos","solution":"Automated workflow","cta":"Join Waitlist"}'
```

### `scripts/deploy.py`
Triggers deployment via Vercel Deploy Hook API.

Example:
```bash
python scripts/deploy.py --project-id acme-saas
```

Environment:
- `VERCEL_DEPLOY_HOOK_URL` (required unless `--dry-run`)

## GitHub Workflow

Workflow file: `.github/workflows/factory-build.yml`

Manual trigger inputs:
- `project_id` (string, required)
- `build_brief_json` (string, required)
- `dry_run` (`true`/`false`)

Execution order:
1. Checkout
2. Setup Python
3. Run `create_project.py`
4. Run `inject_brief.py`
5. Run `deploy.py`

## Required GitHub Secrets

- `FACTORY_GITHUB_TOKEN`
- `VERCEL_DEPLOY_HOOK_URL`
