from fastapi import FastAPI
from contextlib import asynccontextmanager
from routes.packages import router, start_kafka_producer, stop_kafka_producer

@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_kafka_producer()
    yield
    await stop_kafka_producer()

app = FastAPI(lifespan=lifespan)

app.include_router(router)
