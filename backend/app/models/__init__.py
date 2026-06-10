"""Importing this package registers every SQLModel table on SQLModel.metadata."""

from app.models.asset import ImageAsset
from app.models.concept import LookFrame, VisualConceptSet
from app.models.director import DirectorTurn
from app.models.gallery import PublishedVideo
from app.models.generation import GenerationJob, ShotVersion
from app.models.memory import CharacterProfile, StylePack
from app.models.project import Brief, Project
from app.models.scene import Scene
from app.models.shot import Shot
from app.models.timeline import TimelineSequence
from app.models.user import User

__all__ = [
    "User",
    "Project",
    "Brief",
    "Scene",
    "Shot",
    "VisualConceptSet",
    "LookFrame",
    "ImageAsset",
    "ShotVersion",
    "GenerationJob",
    "CharacterProfile",
    "StylePack",
    "TimelineSequence",
    "PublishedVideo",
    "DirectorTurn",
]
