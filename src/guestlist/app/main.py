"""Roster review: the page where a human turns proposals into people.

One project directory = one event: roster.json plus the crops it points to. Every action rewrites
roster.json and re-renders the roster fragment (HTMX), so the page never holds state of its own.

    python -m guestlist.app --project projects/dev --port 7788
"""

from __future__ import annotations

import argparse
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..roster import Roster

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
REVIEW_ORDER = {"conflict": 0, "suggested": 1, "pending": 2}


def view(r: Roster) -> dict:
    people = r.people()
    label_of = {ref: p["label"] for p in people for ref in p["tracks"]}
    open_props = sorted((p for p in r.proposals if p.status in REVIEW_ORDER),
                        key=lambda p: (REVIEW_ORDER[p.status], -(p.spark or {}).get("confidence", 0)))
    decided = [p for p in r.proposals if p.status in ("accepted", "rejected")]
    return {
        "people": people, "guests": [p for p in people if p["kind"] == "guest"],
        "crowd": [p for p in people if p["kind"] == "crowd"], "tracks": r.tracks, "label_of": label_of,
        "open": open_props, "decided": decided, "clips": r.clips,
        "suggested": sum(p.status == "suggested" for p in open_props),
    }


def create_app(project: str | Path) -> FastAPI:
    project = Path(project).resolve()
    app = FastAPI(title="Guestlist roster")
    app.mount("/media", StaticFiles(directory=project), name="media")

    def roster() -> Roster:
        return Roster(project / "roster.json")

    def render(request: Request, r: Roster, fragment: bool, error: str = "") -> HTMLResponse:
        return TEMPLATES.TemplateResponse(request, "roster.html", {**view(r), "fragment": fragment, "error": error})

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return render(request, roster(), fragment=False)

    @app.post("/proposals/decide", response_class=HTMLResponse)
    def decide(request: Request, pid: str = Form(...), accept: bool = Form(...)):
        r = roster()
        try:
            r.decide(pid, accept)
        except ValueError as e:  # the roster refuses a merge its own rules rule out; say why, change nothing
            return render(request, roster(), fragment=True, error=str(e))
        r.save()
        return render(request, r, fragment=True)

    @app.post("/proposals/accept-suggested", response_class=HTMLResponse)
    def accept_suggested(request: Request):
        r = roster()
        r.accept_suggested()
        r.save()
        return render(request, r, fragment=True)

    @app.post("/people/name", response_class=HTMLResponse)
    def name(request: Request, pid: str = Form(...), name: str = Form("")):
        r = roster()
        r.set_name(pid, name)
        r.save()
        return render(request, r, fragment=True)

    @app.post("/people/confirm", response_class=HTMLResponse)
    def confirm(request: Request, pid: str = Form(...)):
        r = roster()
        r.confirm(pid)
        r.save()
        return render(request, r, fragment=True)

    return app


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="projects/dev")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7788)
    args = ap.parse_args()
    uvicorn.run(create_app(args.project), host=args.host, port=args.port)
