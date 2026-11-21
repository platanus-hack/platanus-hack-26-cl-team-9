"""HTTP driving adapter (FastAPI). Read-only API over the unified grid snapshot.

Run: cascadasen-api  (or: uvicorn cascadasen.api.app:app --reload)
Map: http://localhost:8000/map     Docs: http://localhost:8000/docs
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from cascadasen.api.schemas import EdgePage, Health, IslandsRequest, IslandsResponse, NodePage, Page
from cascadasen.api.simulation_routes import router as simulation_router
from cascadasen.application.grid_queries import GridQueryService, NotFoundError
from cascadasen.application.simulation_service import SimulationService
from cascadasen.infrastructure.container import repository
from cascadasen.infrastructure.settings import Settings, get_settings

STATIC = Path(__file__).parent / "static"
LAYERS = ("substations", "taps", "lines", "plants", "storage", "comunas")


def get_service(request: Request) -> GridQueryService:
    s = request.app.state.service
    if s is None:
        raise HTTPException(503, "No hay snapshot de la red. Ejecuta `cascadasen-build` primero.")
    return s


Svc = Annotated[GridQueryService, Depends(get_service)]


def create_app(
    service: GridQueryService | None = None,
    settings: Settings | None = None,
    simulation: SimulationService | None = None,
) -> FastAPI:
    app = FastAPI(
        title="CascadaSEN · Red eléctrica de Chile",
        version="0.1.0",
        description=(
            "Red de transmisión del Sistema Eléctrico Nacional unificada desde fuentes públicas: IDE Energía "
            "(Ministerio de Energía), Infotecnica (CEN), modelo PyPSA-CL (Ministerio de Energía) y Censo 2024 (INE). "
            "Cada registro trae su procedencia; los valores inferidos llevan `is_assumption`."
        ),
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"]
    )
    app.add_middleware(GZipMiddleware, minimum_size=2048)

    if service is None:
        snap = repository(settings or get_settings()).load()
        service = GridQueryService(snap) if snap else None
    app.state.service = service
    app.state.simulation = simulation  # built lazily from the snapshot on the first /sim request
    app.include_router(simulation_router)

    def found(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except NotFoundError as exc:
            raise HTTPException(404, f"No existe: {exc.args[0]}") from exc

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/map")

    @app.get("/map", include_in_schema=False)
    def map_page() -> FileResponse:
        return FileResponse(STATIC / "map.html")

    @app.get("/api/v1/health", response_model=Health, tags=["general"])
    def health(request: Request) -> dict[str, Any]:
        s: GridQueryService | None = request.app.state.service
        return {
            "status": "ok" if s else "sin snapshot",
            "snapshot_built_at": s.s.built_at if s else None,
            "nodes": len(s.nodes) if s else 0,
            "edges": len(s.edges) if s else 0,
        }

    @app.post(
        "/api/v1/admin/reload",
        response_model=Health,
        tags=["general"],
        summary="Relee el snapshot del disco (tras correr cascadasen-build)",
    )
    def reload(request: Request) -> dict[str, Any]:
        snap = repository(settings or get_settings()).load()
        request.app.state.service = GridQueryService(snap) if snap else None
        request.app.state.simulation = None
        return health(request)

    @app.get(
        "/api/v1/stats",
        tags=["general"],
        summary="Conteos, tasas de cruce entre fuentes y resumen de validación",
    )
    def stats(s: Svc) -> dict[str, Any]:
        return s.stats()

    @app.get("/api/v1/sources", tags=["general"], summary="Fuentes de datos usadas y qué aporta cada una")
    def sources(s: Svc) -> list[dict[str, Any]]:
        return s.sources()

    @app.get(
        "/api/v1/validation", tags=["general"], summary="Chequeos de cobertura, conectividad y consistencia"
    )
    def validation(s: Svc) -> dict[str, Any]:
        return s.validation()

    @app.get("/api/v1/assumptions", tags=["general"], summary="Supuestos declarados del modelo")
    def assumptions(s: Svc) -> list[str]:
        return s.s.assumptions

    @app.get(
        "/api/v1/nodes", response_model=NodePage, tags=["red"], summary="Subestaciones y nodos (filtrables)"
    )
    def nodes(
        s: Svc,
        q: str | None = None,
        kind: str | None = Query(None, description="substation | tap | junction | dangling"),
        kv_min: float | None = None,
        kv_max: float | None = None,
        segment: str | None = None,
        region: str | None = Query(None, description="código de región INE, ej. 13"),
        macro_zone: str | None = Query(None, description="NG, NC, CE, CS, SU, AY, MA"),
        system: str | None = None,
        delivers: bool | None = None,
        located: bool | None = None,
        main_grid: bool | None = None,
        limit: int = Query(100, ge=1, le=5000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        total, items = s.list_nodes(
            q,
            kind,
            kv_min,
            kv_max,
            segment,
            region,
            macro_zone,
            system,
            delivers,
            located,
            main_grid,
            limit,
            offset,
        )
        return {"total": total, "items": items}

    @app.get(
        "/api/v1/nodes/{node_id}",
        tags=["red"],
        summary="Detalle: conexiones, centrales, baterías, comunas abastecidas",
    )
    def node(s: Svc, node_id: str) -> dict[str, Any]:
        return found(s.node_detail, node_id)

    @app.get("/api/v1/nodes/{node_id}/neighbors", tags=["grafo"])
    def neighbors(s: Svc, node_id: str, depth: int = Query(1, ge=1, le=5)) -> dict[str, Any]:
        return found(s.neighbors, node_id, depth)

    @app.get("/api/v1/edges", response_model=EdgePage, tags=["red"], summary="Líneas y acoples (filtrables)")
    def edges(
        s: Svc,
        q: str | None = None,
        kind: str | None = Query(None, description="line | colocated"),
        kv_min: float | None = None,
        kv_max: float | None = None,
        segment: str | None = None,
        topology_source: str | None = Query(None, description="'inferida' o 'CEN'"),
        with_electrical: bool | None = None,
        node: str | None = None,
        limit: int = Query(100, ge=1, le=5000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        total, items = s.list_edges(
            kind, kv_min, kv_max, segment, topology_source, with_electrical, node, q, limit, offset
        )
        return {"total": total, "items": items}

    @app.get(
        "/api/v1/edges/{edge_id}", tags=["red"], summary="Detalle de una línea con geometría y parámetros"
    )
    def edge(s: Svc, edge_id: str) -> dict[str, Any]:
        return found(s.edge_detail, edge_id)

    @app.get("/api/v1/plants", response_model=Page, tags=["activos"])
    def plants(
        s: Svc,
        tech: str | None = Query(None, description="solar, eolica, hidro, termica, bioenergia, geotermica"),
        min_mw: float | None = None,
        operating: bool | None = None,
        system: str | None = None,
        node: str | None = None,
        limit: int = Query(2000, ge=1, le=5000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        total, items = s.list_plants(tech, min_mw, operating, system, node, limit, offset)
        return {"total": total, "items": items}

    @app.get("/api/v1/storage", response_model=Page, tags=["activos"])
    def storage(s: Svc, source: str | None = None, existing_only: bool = False) -> dict[str, Any]:
        total, items = s.list_storage(source, existing_only)
        return {"total": total, "items": items}

    @app.get(
        "/api/v1/comunas",
        tags=["territorio"],
        summary="Comunas con población y subestaciones que las abastecen",
    )
    def comunas(s: Svc, region: str | None = None, macro_zone: str | None = None) -> list[dict[str, Any]]:
        return s.list_comunas(region, macro_zone)

    @app.get("/api/v1/comunas/{cut}", tags=["territorio"])
    def comuna(s: Svc, cut: str) -> dict[str, Any]:
        return found(s.comuna_detail, str(int(cut)) if cut.isdigit() else cut)

    @app.get(
        "/api/v1/zones",
        tags=["territorio"],
        summary="Zonas eléctricas y enlaces entre ellas (capacidad conocida)",
    )
    def zones(s: Svc) -> dict[str, Any]:
        return s.macro_zones()

    @app.get("/api/v1/graph/path", tags=["grafo"], summary="Camino más corto (km) entre dos nodos")
    def path(s: Svc, source: str, target: str) -> dict[str, Any]:
        return found(s.path, source, target)

    @app.post(
        "/api/v1/graph/islands",
        response_model=IslandsResponse,
        tags=["grafo"],
        summary="Islas que quedan al sacar líneas o nodos (conectividad)",
    )
    def islands(s: Svc, body: IslandsRequest) -> dict[str, Any]:
        return found(s.islands, body.remove)

    @app.get("/api/v1/model/buses", tags=["modelo eléctrico"], summary="Barras PyPSA-CL y su subestación")
    def model_buses(s: Svc) -> list[dict[str, Any]]:
        return s.model_buses()

    @app.get(
        "/api/v1/model/branches",
        tags=["modelo eléctrico"],
        summary="Líneas PyPSA-CL (r, x, s_nom) y sus tramos",
    )
    def model_branches(s: Svc) -> list[dict[str, Any]]:
        return s.model_branches()

    @app.get("/api/v1/geo/{layer}.geojson", tags=["mapa"], summary=f"Capas GeoJSON: {', '.join(LAYERS)}")
    def geo(s: Svc, layer: str, kv_min: float | None = None) -> dict[str, Any]:
        if layer not in LAYERS:
            raise HTTPException(404, f"Capa desconocida. Opciones: {', '.join(LAYERS)}")
        return s.geojson(layer, kv_min)

    return app


def __getattr__(name: str):  # lazy module-level app for `uvicorn cascadasen.api.app:app`
    if name == "app":
        return create_app()
    raise AttributeError(name)


def run() -> None:
    import uvicorn

    uvicorn.run("cascadasen.api.app:create_app", factory=True, host="0.0.0.0", port=8000)
