# Recorded provider responses

These files keep the **shape** of each job board's public API so provider tests never touch the network.
They were captured once from the endpoints below, then the job text, titles, companies and URLs were replaced
with synthetic content — the postings belong to those employers, not to this project.

- `greenhouse_job.json` — `https://boards-api.greenhouse.io/v1/boards/<board>/jobs/<id>`
- `lever_job.json` — `https://api.lever.co/v0/postings/<org>/<id>?mode=json`
- `ashby_board.json` — `https://api.ashbyhq.com/posting-api/job-board/<org>?includeCompensation=true`

`pytest -m live_http` checks the real endpoints on purpose, so shape drift is still caught.
