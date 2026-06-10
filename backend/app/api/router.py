"""Aggregate API routers.

``api_router`` is mounted with the global ``current_auth`` gate. ``public_router`` is mounted
without it (register / login / Google OAuth — and, in PR2, the public gallery).
"""

from fastapi import APIRouter

from app.api import (
    auth,
    cast,
    director,
    gallery,
    generation,
    images,
    memory,
    pipeline,
    projects,
    roughcut,
    storyboard,
    usage,
)

api_router = APIRouter()
api_router.include_router(projects.router)
api_router.include_router(pipeline.router)
api_router.include_router(storyboard.router)
api_router.include_router(images.router)
api_router.include_router(generation.router)
api_router.include_router(roughcut.router)
api_router.include_router(memory.router)
api_router.include_router(cast.router)
api_router.include_router(director.router)
api_router.include_router(usage.router)
api_router.include_router(auth.router)  # gated: /me, /rotate-token, /logout
api_router.include_router(gallery.router)  # gated: publish / unpublish a rough cut

public_router = APIRouter()
public_router.include_router(auth.public_router)  # /register, /login, /google/*
public_router.include_router(gallery.public_router)  # /gallery (list + video redirect)
