from sqlalchemy import Column, Integer, String, Text, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class SalesInfo(Base):
    __tablename__ = "sales_info"

    id = Column(Integer, primary_key=True)  # Matches 'id' from properties
    iznos_najvise_ponude = Column(Float)   # Represents the highest bid amount
    status_nadmetanja = Column(String)      # Auction status
    broj_uplatitelja = Column(Integer)     # Number of participants
    data_hash = Column(Text)               # Hash of the JSON data
    json_data = Column(Text)               # JSON data as a string
