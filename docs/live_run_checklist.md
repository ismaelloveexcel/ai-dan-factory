# Live Run Pre-Flight Checklist

Use this checklist right before the first real execution of `factory-build`.

- [ ] GitHub repo secret `FACTORY_GITHUB_TOKEN` exists and is valid.
- [ ] GitHub repo secret `VERCEL_DEPLOY_HOOK_URL` exists and points to the correct Vercel project.
- [ ] Workflow input `dry_run` is set to `false` for the live run.
- [ ] Workflow input `project_id` is a valid slug (example: `test-001`).
- [ ] Workflow input `build_brief_json` is valid JSON (or copied from `test_data/live_test_brief.json`).
- [ ] Confirm this expected output sequence after run:
  - [ ] repo created (or safely marked as already existing)
  - [ ] `PRODUCT_BRIEF.md` and `product.config.json` injection step succeeded
  - [ ] deployment trigger step succeeded
  - [ ] structured factory response JSON produced in final step

## Quick go/no-go

- **GO** when all checklist items are checked.
- **NO-GO** if any secret is missing, hook is incorrect, or payload fails validation.
