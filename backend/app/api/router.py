"""Aggregate all API routers under one router mounted at /api."""

from fastapi import APIRouter

from app.api import generation, images, memory, pipeline, projects, roughcut, storyboard, usage

api_router = APIRouter()
api_router.include_router(projects.router)
api_router.include_router(pipeline.router)
api_router.include_router(storyboard.router)
api_router.include_router(images.router)
api_router.include_router(generation.router)
api_router.include_router(roughcut.router)
api_router.include_router(memory.router)
api_router.include_router(usage.router)
