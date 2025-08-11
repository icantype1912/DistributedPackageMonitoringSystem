from fastapi import FastAPI
from contextlib import asynccontextmanager
from routes.packages import router, start_rabbitmq_producer, stop_rabbitmq_producer

@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_rabbitmq_producer()
    yield
    await stop_rabbitmq_producer()

app = FastAPI(lifespan=lifespan)

app.include_router(router)
