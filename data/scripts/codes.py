"""Code tables from the PLUTO data dictionary (26v2, August 2026), for the lot card.

Transcribed from data/original/nyc_mappluto_26v2_fgdb/pluto_datadictionary.pdf:
LandUse p. 20, OwnerType p. 21, Ext/ProxCode/IrrLotCode p. 30-31, LotType p. 31-32,
BsmtCode p. 32, building classes Appendix C p. 51-54.
"""

LAND_USE = {
    "01": "One & Two Family Buildings", "02": "Multi-Family Walk-Up Buildings",
    "03": "Multi-Family Elevator Buildings", "04": "Mixed Residential & Commercial Buildings",
    "05": "Commercial & Office Buildings", "06": "Industrial & Manufacturing",
    "07": "Transportation & Utility", "08": "Public Facilities & Institutions",
    "09": "Open Space & Outdoor Recreation", "10": "Parking Facilities", "11": "Vacant Land",
}

OWNER_TYPE = {
    "C": "City ownership", "M": "Mixed city & private ownership",
    "O": "Other – owned by either a public authority or the state or federal government",
    "P": "Private ownership",
    "X": "Fully tax-exempt property that may be owned by the city, state, or federal government; "
         "a public authority; or a private institution",
    "": "Unknown (usually private ownership)",
}

EXT = {"E": "Extension", "G": "Garage", "EG": "Extension and garage", "N": "None", "": "Unknown"}
PROX = {"0": "Not available", "1": "Detached", "2": "Semi-attached", "3": "Attached"}
IRR = {"Y": "Yes, an irregularly shaped lot", "N": "No, not an irregularly shaped lot", "": "Unknown"}
LOT_TYPE = {
    "0": "Unknown", "1": "Block assemblage", "2": "Waterfront", "3": "Corner", "4": "Through",
    "5": "Inside", "6": "Interior lot", "7": "Island lot", "8": "Alley lot", "9": "Submerged land lot",
}
BSMT = {
    "0": "None/No Basement", "1": "Above grade full basement", "2": "Below grade full basement",
    "3": "Above grade partial basement", "4": "Below grade partial basement", "5": "Unknown",
}

BLDG_CLASS_GROUP = {
    "A": "One Family Dwellings", "B": "Two Family Dwellings", "C": "Walk Up Apartments",
    "D": "Elevator Apartments", "E": "Warehouses", "F": "Factory and Industrial Buildings",
    "G": "Garages and Gasoline Stations", "H": "Hotels", "I": "Hospitals and Health",
    "J": "Theatres", "K": "Store Buildings (Taxpayers Included)", "L": "Loft Buildings",
    "M": "Churches, Synagogues, etc.", "N": "Asylums and Homes", "O": "Office Buildings",
    "P": "Places of Public Assembly (Indoor) and Cultural", "Q": "Outdoor Recreation Facilities",
    "R": "Condominiums", "S": "Residence - Multiple Use", "T": "Transportation Facilities (Assessed in ORE)",
    "U": "Utility Bureau Properties", "V": "Vacant Land", "W": "Educational Structures",
    "Y": "Selected Government Installations", "Z": "Miscellaneous",
}

_BC = {
    "A": {"0": "Cape Cod", "1": "Two Stories Detached (Small or Moderate Size, With or Without Attic)",
          "2": "One Story (Permanent Living Quarters)", "3": "Large Suburban Residence", "4": "City Residence",
          "5": "Attached or Semi-Detached", "6": "Summer Cottages", "7": "Mansion Type or Town House",
          "8": "Bungalow Colony/Land Coop Owned", "9": "Miscellaneous"},
    "B": {"1": "Brick", "2": "Frame", "3": "Converted from One Family", "9": "Miscellaneous"},
    "C": {"0": "Three Families", "1": "Over Six Families Without Stores", "2": "Five to Six Families",
          "3": "Four Families", "4": "Old Law Tenements", "5": "Converted Dwelling or Rooming House",
          "6": "Cooperative", "7": "Over Six Families with Stores", "8": "Co-Op Conversion from Loft/Warehouse",
          "9": "Garden Apartments", "M": "Mobile Homes/Trailer Parks"},
    "D": {"0": "Co-op Conversion from Loft/Warehouse", "1": "Semi-fireproof (Without Stores)",
          "2": "Artists in Residence", "3": "Fireproof (Without Stores)",
          "4": "Cooperatives (Other Than Condominiums)", "5": "Converted", "6": "Fireproof with Stores",
          "7": "Semi-Fireproof with Stores", "8": "Luxury Type", "9": "Miscellaneous"},
    "E": {"1": "Fireproof", "2": "Contractor’s Warehouse", "3": "Semi-Fireproof", "4": "Frame, Metal",
          "7": "Warehouse, Self Storage", "9": "Miscellaneous"},
    "F": {"1": "Heavy Manufacturing - Fireproof", "2": "Special Construction - Fireproof", "4": "Semi-Fireproof",
          "5": "Light Manufacturing", "8": "Tank Farms", "9": "Miscellaneous"},
    "G": {"0": "Residential Tax Class 1 Garage", "1": "All Parking Garages", "2": "Auto Body/Collision or Auto Repair",
          "3": "Gas Station with Retail Store", "4": "Gas Station with Service/Auto Repair",
          "5": "Gas Station only with/without Small Kiosk", "6": "Licensed Parking Lot", "7": "Unlicensed Parking Lot",
          "8": "Car Sales/Rental with Showroom", "9": "Miscellaneous Garage or Gas Station",
          "U": "Car Sales/Rental without Showroom", "W": "Car Wash or Lubritorium Facility"},
    "H": {"1": "Luxury Type", "2": "Full Service Hotel", "3": "Limited Service – Many Affiliated with National Chain",
          "4": "Motels", "5": "Private Club, Luxury Type", "6": "Apartment Hotels", "7": "Apartment Hotels-Co-op Owned",
          "8": "Dormitories", "9": "Miscellaneous",
          "B": "Boutique 10-100 Rooms, with Luxury Facilities, Themed, Stylish, with Full Service Accommodations",
          "H": "Hostel-Bed Rental in Dorm Like Setting with Shared Rooms & Bathrooms",
          "R": "SRO- 1 or 2 People Housed in Individual Rooms in Multiple Dwelling Affordable Housing",
          "S": "Extended Stay/Suite Amenities Similar to Apt., Typically Charge Weekly Rates & Less Expensive than Full Service Hotel"},
    "I": {"1": "Hospitals, Sanitariums, Mental Institutions", "2": "Infirmary", "3": "Dispensary",
          "4": "Staff Facilities", "5": "Health Center, Child Center, Clinic", "6": "Nursing Home",
          "7": "Adult Care Facility", "9": "Miscellaneous"},
    "J": {"1": "Art Type (Seating Capacity under 400 Seats)", "2": "Art Type (Seating Capacity Over 400 Seats)",
          "3": "Motion Picture Theatre with Balcony", "4": "Legitimate Theatres (Theatre Sole Use of Building)",
          "5": "Theatre in Mixed Use Building", "6": "T.V. Studios", "7": "Off-Broadway Type",
          "8": "Multiplex Picture Theatre", "9": "Miscellaneous"},
    "K": {"1": "One Story Retail Building", "2": "Multi-Story Retail Building", "3": "Multi-Story Department Store",
          "4": "Predominant Retail with Other Uses", "5": "Stand Alone Food Establishment",
          "6": "Shopping Centers with or without Parking", "7": "Banking Facilities with or without Parking",
          "8": "Big Box Retail Not Affixed & Standing on Own Lot with Parking", "9": "Miscellaneous"},
    "L": {"1": "Over Eight Stores (Mid-Manhattan Type)", "2": "Fireproof and Storage Type (Without Stores)",
          "3": "Semi-Fireproof", "8": "With Retail Stores Other Than Type 1", "9": "Miscellaneous"},
    "M": {"1": "Church, Synagogue, Chapel", "2": "Mission House (Non-Residential)", "3": "Parsonage, Rectory",
          "4": "Convents", "9": "Miscellaneous"},
    "N": {"1": "Asylums", "2": "Homes for Indigent Children, Aged, Homeless", "3": "Orphanages",
          "4": "Detention House For Wayward Girls", "9": "Miscellaneous"},
    "O": {"1": "Office Only – 1 Story", "2": "Office Only – 2-6 Stories", "3": "Office Only – 7-19 Stories",
          "4": "Office Only or Office with Comm – 20 Stories or More", "5": "Office with Comm – 1 to 6 Stories",
          "6": "Office with Comm – 7 to 19 Stories", "7": "Professional Buildings/Stand Alone Funeral Homes",
          "8": "Office with Apartments Only (No Comm)", "9": "Miscellaneous and Old Style Bank Bldgs"},
    "P": {"1": "Concert Halls", "2": "Lodge Rooms", "3": "YWCA, YMCA, YWHA, YMHA, PAL", "4": "Beach Club",
          "5": "Community Center", "6": "Amusement Place, Bathhouse, Boat House", "7": "Museum", "8": "Library",
          "9": "Miscellaneous"},
    "Q": {"0": "Open Space", "1": "Parks/Recreation Facilities", "2": "Playground", "3": "Outdoor Pool",
          "4": "Beach", "5": "Golf Course", "6": "Stadium, Race Track, Baseball Field", "7": "Tennis Court",
          "8": "Marina, Yacht Club", "9": "Miscellaneous", "G": "Community Gardens"},
    "R": {"0": "Condo Billing Lot", "1": "Residential Unit in 2-10 Unit Bldg", "2": "Residential Unit in Walk-Up Bldg",
          "3": "Residential Unit in 1-3 Story Bldg", "4": "Residential Unit in Elevator Bldg",
          "5": "Miscellaneous Commercial", "6": "Residential Unit of 1-3 Unit Bldg-Orig Class 1",
          "7": "Commercial Unit of 1-3 Unit Bldg-Orig Class 1", "8": "Commercial Unit of 2-10 Unit Bldg",
          "9": "Co-op within a Condominium", "A": "Cultural, Medical, Educational, etc.", "B": "Office Space",
          "C": "Commercial Building (Mixed Commercial Condo Building Classification Codes)",
          "D": "Residential Building (Mixed Residential Condo Building Classification Codes)",
          "G": "Indoor Parking", "H": "Hotel/Boatel", "I": "Mixed Warehouse/Factory/Industrial & Commercial",
          "K": "Retail Space", "M": "Mixed Residential & Commercial Building (Mixed Residential & Commercial)",
          "P": "Outdoor Parking", "R": "Condominium Rentals", "S": "Non-Business Storage Space",
          "T": "Terraces/Gardens/Cabanas", "W": "Warehouse/Factory/Industrial",
          "X": "Mixed Residential, Commercial & Industrial", "Z": "Mixed Residential & Warehouse"},
    "S": {"0": "Primarily One Family with Two Stores or Offices", "1": "Primarily One Family with One Store or Office",
          "2": "Primarily Two Family with One Store or Office", "3": "Primarily Three Family with One Store or Office",
          "4": "Primarily Four Family with One Store or Office",
          "5": "Primarily Five to Six Family with One Store or Office",
          "9": "Single or Multiple Dwelling with Stores or Offices"},
    "T": {"1": "Airport, Air Field, Terminal", "2": "Pier, Dock, Bulkhead", "9": "Miscellaneous"},
    "U": {"0": "Utility Company Land and Building", "1": "Bridge, Tunnel, Highway", "2": "Gas or Electric Utility",
          "3": "Ceiling Railroad", "4": "Telephone Utility", "5": "Communications Facilities Other Than Telephone",
          "6": "Railroad - Private Ownership", "7": "Transportation - Public Ownership", "8": "Revocable Consent",
          "9": "Miscellaneous"},
    "V": {"0": "Zoned Residential; Not Manhattan", "1": "Zoned Commercial or Manhattan Residential",
          "2": "Zoned Commercial Adjacent to Class 1 Dwelling; Not Manhattan",
          "3": "Zoned Primarily Residential; Not Manhattan", "4": "Police or Fire Department",
          "5": "School Site or Yard", "6": "Library, Hospital or Museum", "7": "Port Authority of NY and NJ",
          "8": "New York State & U.S. Government", "9": "Miscellaneous"},
    "W": {"1": "Public Elementary, Junior or Senior High", "2": "Parochial School, Yeshiva", "3": "School or Academy",
          "4": "Training School", "5": "City University", "6": "Other College and University",
          "7": "Theological Seminary", "8": "Other Private School", "9": "Miscellaneous"},
    "Y": {"1": "Fire Department", "2": "Police Department", "3": "Prison, Jail, House of Detention",
          "4": "Military and Naval Installation", "5": "Department of Real Estate", "6": "Department of Sanitation",
          "7": "Department of Ports and Terminals", "8": "Department of Public Works",
          "9": "Department of Environmental Protection"},
    "Z": {"0": "Tennis Court, Pool, Shed, etc.", "1": "Court House", "2": "Public Parking Area", "3": "Post Office",
          "4": "Foreign Government", "5": "United Nations", "7": "Easement", "8": "Cemetery", "9": "Other"},
}
BLDG_CLASS = {g + k: v for g, d in _BC.items() for k, v in d.items()}


def all_codes():
    return {"LandUse": LAND_USE, "OwnerType": OWNER_TYPE, "Ext": EXT, "ProxCode": PROX, "IrrLotCode": IRR,
            "LotType": LOT_TYPE, "BsmtCode": BSMT, "BldgClassGroup": BLDG_CLASS_GROUP, "BldgClass": BLDG_CLASS}
