from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from .. import schemas, crud
from ..database import get_db

router = APIRouter(prefix="/api/dividends", tags=["dividends"])


@router.get("/", response_model=List[schemas.DividendResponse])
def list_dividends(
    security_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return crud.get_dividends(db, security_id=security_id, skip=skip, limit=limit)


@router.post("/", response_model=schemas.DividendResponse, status_code=201)
def create_dividend(data: schemas.DividendCreate, db: Session = Depends(get_db)):
    security = crud.get_security(db, data.security_id)
    if not security:
        raise HTTPException(status_code=404, detail="Security not found")
    return crud.create_dividend(db, data)


@router.get("/dohod")
async def dividends_from_dohod(
    portfolio_id: int = Query(..., description="ID портфеля"),
    force_refresh: bool = Query(False, description="Принудительно обновить данные"),
    db: Session = Depends(get_db),
):
    """
    Возвращает предстоящие дивиденды из dohod.ru, сопоставленные с бумагами портфеля.
    Сопоставление идёт по полю Security.dohod_name (либо name/short_name).
    """
    from ..services.dohod_service import get_dohod_dividends_for_portfolio
    return await get_dohod_dividends_for_portfolio(db, portfolio_id, force_refresh)
