# TenderTrace Web UI

P4 provides a static operations workbench served by FastAPI from `web/dist`.

Current UI surfaces:

- Natural-language query input
- Immediate run trigger through `POST /api/runs`
- Scheduled subscription creation through `POST /api/subscriptions`
- Manual subscription trigger through `POST /api/subscriptions/{id}/run`
- Latest run summary
- TenderGraph pipeline checkpoints
- Trace event timeline
- Subscription table
- Outbox Word report table and downloads

Run it with:

```powershell
python -m tendertrace serve
```

Then open `http://127.0.0.1:8000/`.
