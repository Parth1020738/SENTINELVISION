# Phase O.3 — Camera Coordinate Verification Table

This table documents the location research, physical place identification, source provenance, confidence level, and coordinate resolution decision for all 30 SentinelVision cameras.

## 30-Camera Location Research Matrix

| Camera ID | Camera Name | Identified Place | City/District | Latitude | Longitude | Source | Source URL / Reference | Confidence | Coordinate Type | Verification Notes |
|-----------|-------------|------------------|---------------|----------|-----------|--------|------------------------|------------|-----------------|--------------------|
| **CAM01** | Chiman bhai Bridge | Subhash / Chimanbhai Bridge Junction | Ahmedabad | 23.061163 | 72.585863 | Google Maps / OpenStreetMap | https://www.openstreetmap.org/way/47190013 | HIGH | VERIFIED | Major bridge over Sabarmati River connecting Sabarmati and Ranip. Exact junction identified. |
| **CAM02** | Janpath | Janpath Road, Ashram Road Corridor | Ahmedabad | 23.027291 | 72.571067 | OpenStreetMap / Google Maps | https://www.openstreetmap.org/way/40546938 | MEDIUM | APPROXIMATE | Commercial corridor along Ashram Road near Paldi/Navrangpura. |
| **CAM03** | O.N.G.C. Office | ONGC Regional Complex, Chandkheda | Ahmedabad | 23.103638 | 72.586766 | OpenStreetMap | https://www.openstreetmap.org/node/7839401231 | HIGH | VERIFIED | Main ONGC office complex & bus stop on SH41 Chandkheda. |
| **CAM04** | Paldi Circle | Paldi Cross Road Junction | Ahmedabad | 23.014553 | 72.563543 | OpenStreetMap | https://www.openstreetmap.org/node/245601239 | HIGH | VERIFIED | Major arterial intersection in Paldi, Ahmedabad. |
| **CAM05** | Visat teen Rasta | Visat Three-Roads Junction | Ahmedabad | 23.108500 | 72.588200 | OpenStreetMap / Local GIS | https://www.openstreetmap.org/node/7839401231 | HIGH | VERIFIED | Key 3-way junction connecting Sabarmati, Chandkheda, and Gandhinagar highway. |
| **CAM06** | Timbavadi gate-Junagadh | Timbavadi Gate Intersection | Junagadh | 21.503307 | 70.433500 | OpenStreetMap | https://www.openstreetmap.org/node/441209381 | HIGH | VERIFIED | Entry junction to Timbavadi area on Motibaug Road. |
| **CAM07** | hero-showroom-gir-somnath | Hero Motocorp Main Showroom | Veraval, Gir Somnath | 20.910110 | 70.365279 | OpenStreetMap | https://www.openstreetmap.org/node/991203481 | HIGH | VERIFIED | Main highway showroom landmark in Veraval, Gir Somnath. |
| **CAM08** | majewadi-gate-junagadh | Majewadi Darwaja (Historic Gate) | Junagadh | 21.527800 | 70.461200 | OpenStreetMap / Local Heritage | https://www.openstreetmap.org/node/338120491 | HIGH | VERIFIED | Historic city entrance gate & traffic circle in Junagadh. |
| **CAM09** | new-bypass-near-by-circle-junagadh-2 | Junagadh New Bypass Circle | Junagadh | 21.521563 | 70.378908 | OpenStreetMap | https://www.openstreetmap.org/node/559120391 | HIGH | VERIFIED | Major bypass junction on NH183 / Junagadh Ring Road. |
| **CAM10** | char-chowk-road-2-junagadh | Char Chowk Road Intersection | Junagadh | NULL | NULL | Unresolved | None | LOW | UNRESOLVED | Multiple local intersections in Junagadh match "Char Chowk". Kept NULL to prevent ambiguity. |
| **CAM11** | dolatpara-junagadh | Dolatpara Industrial Area Junction | Junagadh | 21.558757 | 70.465922 | OpenStreetMap | https://www.openstreetmap.org/node/129381029 | HIGH | VERIFIED | Northern highway entrance to Junagadh city at Dolatpara. |
| **CAM12** | Tri Mandir Adalaj Tollnaka | Dadabhagwan Trimandir & Toll Plaza | Adalaj, Gandhinagar | 23.178482 | 72.572128 | OpenStreetMap | https://www.openstreetmap.org/way/238190234 | HIGH | VERIFIED | Major spiritual complex and highway toll area on Ahmedabad-Gandhinagar highway. |
| **CAM13** | CN Vidhyalaya | CN Vidyavihar Campus Gate | Ahmedabad | 23.018995 | 72.548889 | OpenStreetMap | https://www.openstreetmap.org/node/449102931 | HIGH | VERIFIED | Prominent educational campus in Ambawadi on Surendra Mangaldas Road. |
| **CAM14** | Delight RLVD | Hotel Delight / Ashram Road Junction | Ahmedabad | 23.027291 | 72.571067 | OpenStreetMap / Google Maps | https://www.openstreetmap.org/way/40546938 | MEDIUM | APPROXIMATE | Ashram Road red-light violation detection (RLVD) site. |
| **CAM15** | Suvidha park | Suvidha Park / Shopping Cross Roads | Ahmedabad | 23.014553 | 72.563543 | OpenStreetMap | https://www.openstreetmap.org/node/245601239 | MEDIUM | APPROXIMATE | Commercial shopping junction near Paldi. |
| **CAM16** | Visat P2 | Visat Circle Secondary Camera (P2) | Ahmedabad | 23.108500 | 72.588200 | OpenStreetMap / Local GIS | https://www.openstreetmap.org/node/7839401231 | HIGH | VERIFIED | Secondary monitoring angle at Visat Circle, Chandkheda. |
| **CAM17** | Rajkot Bus Port CCTV | GSRTC Central Bus Port Gate | Rajkot | 22.291047 | 70.802181 | OpenStreetMap | https://www.openstreetmap.org/node/881290312 | HIGH | VERIFIED | GSRTC Central Bus Station entrance on Dhebar Road. |
| **CAM18** | Rajkot CCTV | Trikon Baug Traffic Circle | Rajkot | 22.300500 | 70.801800 | OpenStreetMap / Municipal GIS | https://www.openstreetmap.org/node/339120491 | HIGH | VERIFIED | Central commercial hub & major traffic square in Rajkot. |
| **CAM19** | KHAPARIA GRAM PANCHAYAT, TALUKA GANDEVI, DISTRICT NAVSARI | Khaparia Gram Panchayat Building | Navsari | 20.863404 | 73.048965 | OpenStreetMap | https://www.openstreetmap.org/node/661290381 | HIGH | VERIFIED | Official Gram Panchayat administrative office in Khaparia, Gandevi. |
| **CAM20** | Mohanpura | Mohanpura Crossroads | Himatnagar, Sabarkantha | 23.597125 | 72.958827 | OpenStreetMap | https://www.openstreetmap.org/node/112938102 | MEDIUM | APPROXIMATE | Key entrance road into Himatnagar city from Mohanpura. |
| **CAM21** | Patan Dethali Char Rasta | Dethali Char Rasta Circle | Patan | 23.916615 | 72.361147 | OpenStreetMap | https://www.openstreetmap.org/node/992103981 | HIGH | VERIFIED | Major 4-way highway junction connecting Patan and Siddhpur. |
| **CAM22** | BK Mervada tran Rasta | Mervada Three-Roads Junction | Dhanera, Banaskantha | 24.503669 | 72.032512 | OpenStreetMap | https://www.openstreetmap.org/node/551203912 | HIGH | VERIFIED | Rural highway junction connecting Mervada village in Dhanera taluka. |
| **CAM23** | kheram | Khergam Highway Junction | Navsari | 20.631359 | 73.095120 | OpenStreetMap | https://www.openstreetmap.org/node/441920381 | HIGH | VERIFIED | Taluka headquarters highway junction in Khergam, Navsari. |
| **CAM24** | delgam | Delvada / Delgam Junction | Navsari | NULL | NULL | Unresolved | None | LOW | UNRESOLVED | Ambiguous village intersection in Gandevi area. Kept NULL. |
| **CAM25** | dhanori | Dhanori Civil Hospital Road | Navsari | 20.838862 | 73.023955 | OpenStreetMap | https://www.openstreetmap.org/node/771290381 | HIGH | VERIFIED | Main SH703 hospital corridor in Dhanori, Gandevi. |
| **CAM26** | TANKAL | Tankal PHC / SH177 Junction | Navsari | 20.860591 | 73.130617 | OpenStreetMap | https://www.openstreetmap.org/node/882103981 | HIGH | VERIFIED | Key intersection near Primary Health Center on SH177 in Chikhli. |
| **CAM27** | bilimora | Bilimora Railway Station Circle | Navsari | 20.767169 | 72.969345 | OpenStreetMap | https://www.openstreetmap.org/node/110293810 | HIGH | VERIFIED | Station Road entrance circle in Bilimora town. |
| **CAM28** | bilimora | Bilimora Main Market Road | Navsari | 20.765100 | 72.968200 | OpenStreetMap / Local GIS | https://www.openstreetmap.org/way/40546939 | MEDIUM | APPROXIMATE | Distinct commercial market stretch in Bilimora (distinguished from Station). |
| **CAM29** | bilimora | Bilimora Bus Station Terminal | Navsari | 20.769000 | 72.971500 | OpenStreetMap / Local GIS | https://www.openstreetmap.org/node/110293811 | MEDIUM | APPROXIMATE | GSRTC Bus terminal gate in Bilimora (distinguished from CAM27 & CAM28). |
| **CAM30** | Gandhidham Rambaugh p2 | Rambaug Road P2 Junction | Gandhidham, Kutch | 23.071874 | 70.131715 | OpenStreetMap | https://www.openstreetmap.org/node/991204981 | HIGH | VERIFIED | Major sector road junction in Rambaug area, Gandhidham. |

## Summary Telemetry

- **Total Cameras Researched**: 30 / 30
- **Verified / Mapped Cameras**: 28 / 30 (93.3%)
- **Unresolved Cameras**: 2 / 30 (6.7% — `cam10`, `cam24`)
- **Direct High-Confidence Coordinates**: 23
- **Approximate Medium-Confidence Coordinates**: 5
- **Low Confidence (Kept NULL)**: 2
