from fastapi import FastAPI


app = FastAPI(title="motion-sense-mock-backend")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/ingest/batch")
async def ingest_batch(payload: dict) -> dict[str, int]:
    items = payload.get("items", [])
    return {"accepted": len(items)}
