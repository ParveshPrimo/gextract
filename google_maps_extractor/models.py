from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

@dataclass
class BusinessInfo:
    name: str
    category: Optional[str] = None
    rating: Optional[float] = None
    reviews: Optional[int] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    maps_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    opening_hours: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert dataclass instance to dictionary."""
        return asdict(self)
