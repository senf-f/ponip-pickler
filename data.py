from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class SalesInfo(Base):
    __tablename__ = "sales_info"

    id = Column(Integer, primary_key=True)
    iznos_najvise_ponude = Column(String)
    status_nadmetanja = Column(String)
    broj_uplatitelja = Column(Integer)
    data_hash = Column(Text)
    json_data = Column(Text)
    url = Column(Text)