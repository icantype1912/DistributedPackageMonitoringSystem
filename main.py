from fastapi import FastAPI
from routes.packages import router as package_router

app = FastAPI()
app.include_router(package_router)

