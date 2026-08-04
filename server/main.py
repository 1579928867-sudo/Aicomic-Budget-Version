"""FastAPI application entry point."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AI漫剧", version="0.1.0")

# CORS — 允许前端 dev server (Vite :5173) 跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


def main():
    import uvicorn

    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()

