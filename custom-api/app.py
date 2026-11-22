import os

from fastapi import FastAPI
import time

import microtek

app = FastAPI()

MICROTEK_PASSWORD = os.getenv("MICROTEK_PASSWORD")

@app.on_event("startup")
async def startup_event():
    print("STARTUP EVENT", flush=True)
    print(f"MICROTEK_PASSWORD={MICROTEK_PASSWORD}")
    microtek.start_listener(MICROTEK_PASSWORD)
    print("LISTENER START CALLED", flush=True)
    
@app.get("/")
async def root():
    return {"status": "ok"}

@app.get("/inverter")
def inverter():
    if microtek.latest_state:
        microtek.latest_state["_age"] = (
            time.time() - microtek.latest_state["_received_at"]
        )

    response = microtek.latest_state.copy()
    # microtek.latest_state.clear()

    return response