# backend/main.py

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path

from .data.routes_with_coords import ROUTES, COORDINATES, haversine

# =========================================================
# APP
# =========================================================
app = FastAPI(title="Railway CO₂ Calculator API")

# =========================================================
# CORS
# =========================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# КОЭФФИЦИЕНТЫ ВЫБРОСОВ (кг CO₂ / т·км)
# =========================================================
EMISSION_FACTORS = {
    "rail": {
        "dfe": 0.018,
        "sfe": 0.015
    },
    # "ship_plus" — условный альтернативный путь с морской перегрузкой
    "ship_plus": {
        "dfe": 0.045,   # ≈ в 2.5 раза выше ж/д
        "sfe": 0.038
    }
}

# =========================================================
# МОДЕЛЬ ЗАПРОСА
# =========================================================
class EmissionRequest(BaseModel):
    route_id: str          # "1", "2", "3", "4"
    weight_tons: float     # масса груза, т
    container: str         # "dfe" | "sfe"

# =========================================================
# API: ВСЕ МАРШРУТЫ + КООРДИНАТЫ (для фронта)
# =========================================================
@app.get("/api/routes/full")
def get_full_routes():
    coords_serializable = {k: list(v) for k, v in COORDINATES.items()}
    return {
        "routes": ROUTES,
        "coordinates": coords_serializable
    }

# =========================================================
# API: СПИСОК МАРШРУТОВ
# =========================================================
@app.get("/api/routes")
def list_routes():
    return {
        "routes": [
            {"id": k, "name": v["name"]}
            for k, v in ROUTES.items()
        ]
    }

# =========================================================
# API: РАСЧЁТ ВЫБРОСОВ ПО ВСЕМУ МАРШРУТУ
# =========================================================
@app.post("/api/calculate")
def calculate_emissions(req: EmissionRequest):
    if req.route_id not in ROUTES:
        raise HTTPException(400, "Неверный ID маршрута")
    if req.container not in ("dfe", "sfe"):
        raise HTTPException(400, "container должен быть 'dfe' или 'sfe'")
    if req.weight_tons <= 0:
        raise HTTPException(400, "Масса должна быть больше 0")

    route = ROUTES[req.route_id]
    stations = route["stations"]

    # --- расчёт расстояния по координатам ---
    distance_km = 0.0
    coords = []

    for i, station in enumerate(stations):
        if station not in COORDINATES:
            raise HTTPException(500, f"Нет координат для станции: {station}")
        lat, lon = COORDINATES[station]
        coords.append([lat, lon])
        if i > 0:
            lat1, lon1 = coords[i - 1]
            distance_km += haversine(lat1, lon1, lat, lon)

    # --- выбросы ---
    rail_factor = EMISSION_FACTORS["rail"][req.container]
    ship_factor = EMISSION_FACTORS["ship_plus"][req.container]

    rail_emission = req.weight_tons * distance_km * rail_factor
    ship_emission = req.weight_tons * distance_km * ship_factor
    saved = ship_emission - rail_emission

    # 1 дерево поглощает ~22 кг CO₂ в год → используем для метафоры
    trees = max(0, round(saved / 22))

    return {
        "route_name": route["name"],
        "from": stations[0],
        "to": stations[-1],
        "distance_km": round(distance_km, 1),
        "rail_kg": round(rail_emission, 1),
        "ship_kg": round(ship_emission, 1),
        "saved_kg": round(saved, 1),
        "trees": trees,
        "coords": coords
    }

# =========================================================
# FRONTEND (STATIC FILES)
# =========================================================
BASE_DIR = Path(__file__).resolve().parent.parent

app.mount(
    "/",
    StaticFiles(directory=BASE_DIR / "frontend", html=True),
    name="frontend"
)
