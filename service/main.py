from fastapi import FastAPI, HTTPException
import httpx
import json


r = httpx.get("https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs")
# app = FastAPI()

# @app.get("/")
# async def root():
#     return {"message": "hello world"}

