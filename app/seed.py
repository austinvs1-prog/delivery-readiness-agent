import time
from pathlib import Path
from datetime import datetime
import pandas as pd
from app.db import Base, engine, session_scope
from app.models import InspectionRecord

CSV_PATH = Path("data/delivery_readiness_inspections.csv")


def seed() -> None:
    # DB may still be starting when the container boots.
    for _ in range(30):
        try:
            Base.metadata.create_all(bind=engine)
            break
        except Exception:
            time.sleep(2)
    df = pd.read_csv(CSV_PATH)

    with session_scope() as session:
        existing = session.query(InspectionRecord).count()
        if existing:
            return
        for row in df.to_dict(orient="records"):
            session.add(
                InspectionRecord(
                    inspection_id=row["Inspection ID"],
                    inspector_name=row["Inspector Name"],
                    pass_fail=row["Pass/Fail"],
                    free_text=row["Free Text"],
                    gate_captured=row["Gate Captured"],
                    gate_missed=None if pd.isna(row["Gate Missed"]) else row["Gate Missed"],
                    part_cost=float(row["Part Cost"]),
                    labor_time=float(row["Labor Time"]),
                    labor_cost=float(row["Labor Cost"]),
                    plant=row["Plant"],
                    part_sn=str(row["Part SN"]),
                    vin=row["VIN"],
                    customer=row["Customer"],
                    dangerous_issue_flag=row["Dangerous Issue Flag"],
                    inspection_date=datetime.strptime(row["Inspection Date"], "%Y-%m-%d").date(),
                    rework_date=None if pd.isna(row["Rework Date"]) else datetime.strptime(row["Rework Date"], "%Y-%m-%d").date(),
                )
            )


if __name__ == "__main__":
    seed()
