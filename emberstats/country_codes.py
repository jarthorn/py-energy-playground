"""
Country code constants for the Ember API.
"""

from enum import StrEnum


class CountryCode(StrEnum):
    """
    ISO 3166-1 alpha-3 country codes supported by the Ember API.

    StrEnum automatically inherits from both str and Enum, providing:
    - Type safety and validation
    - Direct string behavior (no need for .value)
    - IDE autocomplete support

    Usage:
        >>> code = CountryCode.CAN
        >>> print(code)  # "CAN" (works as string directly)
        >>> CountryCode("CAN")  # CountryCode.CAN
        >>> str(code)  # "CAN"
    """

    # All supported country codes
    ARG = "ARG"  # Argentina
    ARM = "ARM"  # Armenia
    AUS = "AUS"  # Australia
    AUT = "AUT"  # Austria
    AZE = "AZE"  # Azerbaijan
    BEL = "BEL"  # Belgium
    BGD = "BGD"  # Bangladesh
    BGR = "BGR"  # Bulgaria
    BIH = "BIH"  # Bosnia and Herzegovina
    BLR = "BLR"  # Belarus
    BOL = "BOL"  # Bolivia
    BRA = "BRA"  # Brazil
    CAN = "CAN"  # Canada
    CHE = "CHE"  # Switzerland
    CHL = "CHL"  # Chile
    CHN = "CHN"  # China
    COL = "COL"  # Colombia
    CRI = "CRI"  # Costa Rica
    CYP = "CYP"  # Cyprus
    CZE = "CZE"  # Czech Republic
    DEU = "DEU"  # Germany
    DNK = "DNK"  # Denmark
    DOM = "DOM"  # Dominican Republic
    ECU = "ECU"  # Ecuador
    EGY = "EGY"  # Egypt
    ESP = "ESP"  # Spain
    EST = "EST"  # Estonia
    FIN = "FIN"  # Finland
    FRA = "FRA"  # France
    GBR = "GBR"  # United Kingdom
    GEO = "GEO"  # Georgia
    GRC = "GRC"  # Greece
    HRV = "HRV"  # Croatia
    HUN = "HUN"  # Hungary
    IND = "IND"  # India
    IRL = "IRL"  # Ireland
    IRN = "IRN"  # Iran
    ITA = "ITA"  # Italy
    JPN = "JPN"  # Japan
    KAZ = "KAZ"  # Kazakhstan
    KEN = "KEN"  # Kenya
    KGZ = "KGZ"  # Kyrgyzstan
    KOR = "KOR"  # South Korea
    KWT = "KWT"  # Kuwait
    LKA = "LKA"  # Sri Lanka
    LTU = "LTU"  # Lithuania
    LUX = "LUX"  # Luxembourg
    LVA = "LVA"  # Latvia
    MAR = "MAR"  # Morocco
    MDA = "MDA"  # Moldova
    MEX = "MEX"  # Mexico
    MKD = "MKD"  # North Macedonia
    MLT = "MLT"  # Malta
    MMR = "MMR"  # Myanmar
    MNE = "MNE"  # Montenegro
    MNG = "MNG"  # Mongolia
    MYS = "MYS"  # Malaysia
    NGA = "NGA"  # Nigeria
    NLD = "NLD"  # Netherlands
    NOR = "NOR"  # Norway
    NZL = "NZL"  # New Zealand
    OMN = "OMN"  # Oman
    PAK = "PAK"  # Pakistan
    PER = "PER"  # Peru
    PHL = "PHL"  # Philippines
    POL = "POL"  # Poland
    PRI = "PRI"  # Puerto Rico
    PRT = "PRT"  # Portugal
    QAT = "QAT"  # Qatar
    ROU = "ROU"  # Romania
    RUS = "RUS"  # Russia
    SGP = "SGP"  # Singapore
    SLV = "SLV"  # El Salvador
    SRB = "SRB"  # Serbia
    SVK = "SVK"  # Slovakia
    SVN = "SVN"  # Slovenia
    SWE = "SWE"  # Sweden
    THA = "THA"  # Thailand
    TJK = "TJK"  # Tajikistan
    TUN = "TUN"  # Tunisia
    TUR = "TUR"  # Turkey
    TWN = "TWN"  # Taiwan
    UKR = "UKR"  # Ukraine
    URY = "URY"  # Uruguay
    USA = "USA"  # United States
    VNM = "VNM"  # Vietnam
    XKX = "XKX"  # Kosovo
    ZAF = "ZAF"  # South Africa
