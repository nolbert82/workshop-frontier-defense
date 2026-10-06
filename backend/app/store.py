"""Transactions bloquantes : toutes les méthodes sont appelées via to_thread."""
from datetime import datetime, timezone
from sqlalchemy import JSON, BigInteger, Column, Integer, MetaData, String, Table, UniqueConstraint, create_engine, select, text
from sqlalchemy.exc import IntegrityError


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, url):
        self.engine = create_engine(url, pool_pre_ping=True, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
        meta = MetaData()
        self.measurements = Table("measurements", meta,
            Column("id", Integer, primary_key=True), Column("device_id", String(40), index=True),
            Column("boot_id", String(64)), Column("sequence", BigInteger),
            Column("received_at", String(40), index=True), Column("data", JSON),
            UniqueConstraint("device_id", "boot_id", "sequence"))
        self.alerts = Table("alerts", meta, Column("id", String(80), primary_key=True), Column("created_at", String(40), index=True), Column("data", JSON))
        self.commands = Table("commands", meta, Column("id", String(64), primary_key=True), Column("created_at", String(40), index=True), Column("data", JSON))
        self.devices = Table("device_status", meta, Column("id", String(40), primary_key=True), Column("data", JSON))
        self.meta = meta

    def initialize(self):
        self.meta.create_all(self.engine)
        # After restart, an unconfirmed command remains execution-unknown.
        for row in self.list_rows("commands", 10000):
            if row["status"] == "pending":
                row.update(status="timeout", reason="Redémarrage serveur : exécution inconnue")
                self.put("commands", row["command_id"], row)

    def ping(self):
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True

    def insert_measurement(self, data):
        values = {key: data[key] for key in ("device_id", "boot_id", "sequence", "received_at")}
        try:
            with self.engine.begin() as conn:
                conn.execute(self.measurements.insert().values(**values, data=data))
            return True
        except IntegrityError:
            # The receipt may now be sent: a matching identity was already committed.
            with self.engine.connect() as conn:
                match = conn.execute(select(self.measurements.c.id).where(
                    self.measurements.c.device_id == data["device_id"], self.measurements.c.boot_id == data["boot_id"], self.measurements.c.sequence == data["sequence"])).first()
            if not match:
                raise
            return False

    def put(self, table, id_, data):
        tab = getattr(self, table)
        with self.engine.begin() as conn:
            existing = conn.execute(select(tab.c.id).where(tab.c.id == id_)).first()
            if existing:
                conn.execute(tab.update().where(tab.c.id == id_).values(data=data))
            else:
                values = {"id": id_, "data": data}
                if table != "devices":
                    values["created_at"] = data["created_at"]
                conn.execute(tab.insert().values(**values))

    def update_measurement(self, data):
        tab = self.measurements
        with self.engine.begin() as conn:
            conn.execute(tab.update().where(tab.c.device_id == data["device_id"], tab.c.boot_id == data["boot_id"], tab.c.sequence == data["sequence"]).values(data=data))

    def get(self, table, id_):
        tab = getattr(self, table)
        with self.engine.connect() as conn:
            return conn.execute(select(tab.c.data).where(tab.c.id == id_)).scalar_one_or_none()

    def list_rows(self, table, limit=100, offset=0, device=None, since=None, until=None):
        tab = getattr(self, table)
        date = tab.c.received_at if table == "measurements" else tab.c.created_at
        query = select(tab.c.data).order_by(date.desc(), tab.c.id.desc()).limit(limit).offset(offset)
        if device and table == "measurements":
            query = query.where(tab.c.device_id == device)
        if since:
            query = query.where(date >= since)
        if until:
            query = query.where(date <= until)
        with self.engine.connect() as conn:
            return list(conn.execute(query).scalars())
