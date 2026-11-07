from fastapi import APIRouter
from app.api.v1.endpoints import (
    analyses,
    comparisons,
    datasets,
    eda,
    feature_engineering,
    health,
    jobs,
    preprocessing,
    quality,
    readiness,
    reports,
    thumbnails,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(datasets.router, prefix="/datasets", tags=["Datasets"])
api_router.include_router(analyses.router, prefix="/analyses", tags=["Analyses"])
api_router.include_router(quality.router, prefix="/quality-assessments", tags=["Quality"])
api_router.include_router(eda.router, prefix="/eda-reports", tags=["EDA"])
api_router.include_router(comparisons.router, prefix="/comparisons", tags=["Comparisons"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
api_router.include_router(preprocessing.router, prefix="/datasets", tags=["Preprocessing"])
api_router.include_router(feature_engineering.router, prefix="/datasets", tags=["FeatureEngineering"])
api_router.include_router(readiness.router, prefix="/datasets", tags=["Readiness"])
api_router.include_router(reports.router, prefix="/datasets", tags=["Reports"])
api_router.include_router(thumbnails.router, prefix="", tags=["Thumbnails"])
