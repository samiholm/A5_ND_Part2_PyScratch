# ============================================================
# WL Auto Part 2 - NORTH DAKOTA COUNTY LOOP (SIMPLE + TEACHABLE)
# - Wraps YOUR click-by-click steps in a basic for-loop
# - Writes county outputs + a per-county summary table
# - Merges all summaries into ONE final table at the end
# - look for the following to change for a new state: 
#                ---> ****NEEDS TO BE CHANGED FOR NEW STATE****
# ============================================================

import arcpy
import os

arcpy.env.overwriteOutput = True

# ------------------------------------------------------------
# 0) USER PATHS (YOU PROVIDED THESE)
# ------------------------------------------------------------
GDB = r"C:\GIS\Adv_GIS\A5_ND_Part2_PyScratch\A5_ND_Part2PyScratch\A5_ND_Part2PyScratch.gdb"
DATA_FOLDER = r"C:\GIS\Adv_GIS\A5_ND_Part2_PyScratch\A5_ND_Part2PyScratch"

arcpy.env.workspace = GDB
arcpy.env.scratchWorkspace = GDB

# set state fips for the state you are interested in
STATE_FIPS = "38"  # North Dakota   ---> ****NEEDS TO BE CHANGED FOR NEW STATE****

# ------------------------------------------------------------
# 1) INPUT DATASETS (SET THESE TO YOUR 4 SOURCE DATASETS)
#    (Keep them simple + explicit for students.)
# ------------------------------------------------------------
# A) ND counties polygon feature class (must include STATEFP, GEOID, NAME, etc.)
COUNTIES_FC = os.path.join(DATA_FOLDER, "USA_Counties.gdb", "cb_2018_us_county_500k")   # <-- change if yours is in a GDB

# B) ND wetlands feature class  ---> ****NEEDS TO BE CHANGED FOR NEW STATE****
WETLANDS_FC = os.path.join(DATA_FOLDER, "ND_geodatabase_wetlands.gdb", "ND_Wetlands")  # <-- change to your actual path

# C) NLCD land cover raster (2024)
NLCD_LC = os.path.join(DATA_FOLDER, "Annual_NLCD_LndCov_2024_CU_C1V1.tif")

# D) NLCD impervious raster (2024)
NLCD_IMP = os.path.join(DATA_FOLDER, "Annual_NLCD_FctImp_2024_CU_C1V1.tif")

# ------------------------------------------------------------
# 2) OUTPUTS (FINAL MERGED SUMMARY)  ---> ****NEEDS TO BE CHANGED FOR NEW STATE****
# ------------------------------------------------------------
FINAL_MERGED_SUMMARY = os.path.join(GDB, "ND_Risk_Summary_ALL")

# ------------------------------------------------------------
# 3) BASIC HELPERS (NOT CLEVER - JUST TO REDUCE REPEATED TYPING)
# ------------------------------------------------------------
import time
import arcpy

def safe_delete(path, tries=5, wait=1.0):
    if not arcpy.Exists(path):
        return

    for t in range(tries):
        try:
            arcpy.ClearWorkspaceCache_management()
            arcpy.management.Delete(path)
            return
        except Exception:
            time.sleep(wait)

    # If it still can't delete, raise the last error
    arcpy.management.Delete(path)

def ensure_text_field(fc_or_table, field_name, length=50):
    fields = [f.name for f in arcpy.ListFields(fc_or_table)]
    if field_name not in fields:
        arcpy.management.AddField(fc_or_table, field_name, "TEXT", field_length=length)

###Start Main Function

def run_one_county(county_name, geoid, statefp):
    arcpy.ClearWorkspaceCache_management()
    """
    Runs your steps for ONE county.
    Writes:
      - AOI_<County>
      - Wetlands_<County>
      - DevPress_<County>
      - DevPressPoly_<County>
      - MultiRing_<County>
      - RiskUnion_<County>
      - WetlandRiskFinal_<County>
      - <County>_Risk_Summary
    Returns:
      - path to the summary table for merge
    """

    # Clean tags for dataset names (avoid spaces/special chars)
    ctag = "".join([ch for ch in county_name if ch.isalnum() or ch in ["_", "-"]]).replace("-", "_")
    if len(ctag) == 0:
        ctag = "County"

    aoi_fc = os.path.join(GDB, f"AOI_{ctag}")
    wetlands_out = os.path.join(GDB, f"Wetlands_{ctag}")
    devpress_ras = os.path.join(GDB, f"DevPress_{ctag}")
    devpress_poly = os.path.join(GDB, f"DevPressPoly_{ctag}")
    multiring_fc = os.path.join(GDB, f"MultiRing_{ctag}")
    union_fc = os.path.join(GDB, f"RiskUnion_{ctag}")
    final_fc = os.path.join(GDB, f"WetlandRiskFinal_{ctag}")
    summary_tbl = os.path.join(GDB, f"{ctag}_Risk_Summary")

    # If re-running, remove old outputs
    for p in [aoi_fc, wetlands_out, devpress_ras, devpress_poly, multiring_fc, union_fc, final_fc, summary_tbl]:
        safe_delete(p)

    # --------------------------------------------------------
    # 2B. export county (YOUR STEP, now with a WHERE CLAUSE)
    # --------------------------------------------------------
    # NOTE: cb_2018_us_county_500k typically uses STATEFP + COUNTYFP + GEOID, etc.
    # We'll select the county by GEOID + STATEFP to be safe.
    where_county = f"STATEFP = '{statefp}' AND GEOID = '{geoid}'"

    arcpy.conversion.ExportFeatures(
        in_features=COUNTIES_FC,
        out_features=aoi_fc,
        where_clause=where_county
    )

    # --------------------------------------------------------
    # 3 + 3B + 3C. select wetlands in county, deselect lakes/rivers, export
    # (Do it without relying on map layers: use MakeFeatureLayer)
    # --------------------------------------------------------
    wetlands_lyr = "wetlands_lyr_tmp"
    safe_delete(wetlands_lyr)  # harmless if it doesn't exist
    arcpy.management.MakeFeatureLayer(WETLANDS_FC, wetlands_lyr)

    arcpy.management.SelectLayerByLocation(
        in_layer=wetlands_lyr,
        overlap_type="INTERSECT",
        select_features=aoi_fc,
        selection_type="NEW_SELECTION"
    )

    arcpy.management.SelectLayerByAttribute(
        in_layer_or_view=wetlands_lyr,
        selection_type="SUBSET_SELECTION",
        where_clause="WETLAND_TYPE <> 'Lake' And WETLAND_TYPE <> 'Riverine'"
    )

    arcpy.conversion.ExportFeatures(
        in_features=wetlands_lyr,
        out_features=wetlands_out
    )

    # --------------------------------------------------------
    # 4. Create Development Pressure Raster (YOUR STEP, but dynamic extent/mask)
    # --------------------------------------------------------
    from arcpy.sa import Raster, Con

    arcpy.CheckOutExtension("Spatial")
    
    with arcpy.EnvManager(
        snapRaster=NLCD_LC,
        extent=aoi_fc,
        cellSize=NLCD_LC,
        mask=aoi_fc,
        scratchWorkspace=GDB
    ):
        lc = Raster(NLCD_LC)
        imp = Raster(NLCD_IMP)
    
        # Dev pressure = 1 where developed classes OR impervious >= 20, else 0
        dev = Con(((lc == 21) | (lc == 22) | (lc == 23) | (lc == 24) | (imp >= 20)), 1, )
    
        dev.save(devpress_ras)

    # --------------------------------------------------------
    # 5. Convert dev raster to polygon
    # --------------------------------------------------------
    arcpy.conversion.RasterToPolygon(
        in_raster=devpress_ras,
        out_polygon_features=devpress_poly,
        simplify="SIMPLIFY",
        raster_field="Value",
        create_multipart_features="MULTIPLE_OUTER_PART"
    )

    # --------------------------------------------------------
    # 6. Build multi ring risk buffers
    # --------------------------------------------------------
    arcpy.analysis.MultipleRingBuffer(
        Input_Features=devpress_poly,
        Output_Feature_class=multiring_fc,
        Distances=[100, 250, 500],
        Buffer_Unit="Meters",
        Field_Name="distance",
        Dissolve_Option="ALL",
        Outside_Polygons_Only="FULL",
        Method="GEODESIC"
    )

    # --------------------------------------------------------
    # 7. Union wetlands and risk rings
    # --------------------------------------------------------
    arcpy.analysis.Union(
        in_features=f"{multiring_fc} #;{wetlands_out} #",
        out_feature_class=union_fc,
        join_attributes="ALL",
        gaps="GAPS"
    )

    # --------------------------------------------------------
    # 8. Select only the union with wetlands (get rid of roads only)
    # 8b. Export the risk wetland only
    # --------------------------------------------------------
    union_lyr = "union_lyr_tmp"
    safe_delete(union_lyr)
    arcpy.management.MakeFeatureLayer(union_fc, union_lyr)

    arcpy.management.SelectLayerByAttribute(
        in_layer_or_view=union_lyr,
        selection_type="NEW_SELECTION",
        where_clause="WETLAND_TYPE <> ''"
    )

    arcpy.conversion.ExportFeatures(
        in_features=union_lyr,
        out_features=final_fc
    )

    # --------------------------------------------------------
    # 9. Add RiskClass field
    # 9b. Calculate RiskClass from distance
    # --------------------------------------------------------
    ensure_text_field(final_fc, "RiskClass", length=30)

    arcpy.management.CalculateField(
        in_table=final_fc,
        field="RiskClass",
        expression="risk(!distance!)",
        expression_type="PYTHON3",
        code_block="""def risk(d):
    if d == 100:
        return "High (0-100m)"
    elif d == 250:
        return "Moderate (100-250m)"
    elif d == 500:
        return "Low (250-500m)"
    else:
        return "Minimal (>500m)"
"""
    )

    # --------------------------------------------------------
    # 10. Update Acres field (write to ACRES)
    # --------------------------------------------------------
    # Ensure ACRES exists, then calculate geometry into it
    ensure_text_field(final_fc, "ACRES", length=50)  # if ACRES already numeric, this won't run; see note below
    # If ACRES already exists and is Double, the AddField above will not happen.
    arcpy.management.CalculateGeometryAttributes(
        in_features=final_fc,
        geometry_property=[["ACRES", "AREA_GEODESIC"]],
        area_unit="ACRES_US"
    )

    # --------------------------------------------------------
    # 11. Summarize wetland acres by risk class
    # --------------------------------------------------------
    arcpy.analysis.Statistics(
        in_table=final_fc,
        out_table=summary_tbl,
        statistics_fields=[["ACRES", "SUM"]],
        case_field=["RiskClass"]
    )

    # Add County field to each summary so we can merge later
    ensure_text_field(summary_tbl, "County", length=100)
    arcpy.management.CalculateField(
        in_table=summary_tbl,
        field="County",
        expression=f"'{county_name}'",
        expression_type="PYTHON3"
    )

    return summary_tbl


# ------------------------------------------------------------
# 4) MAIN LOOP: ALL North Dakota COUNTIES
# ------------------------------------------------------------
# Make a layer for counties, select MN only, then loop rows.
counties_lyr = "counties_lyr_tmp"
safe_delete(counties_lyr)
arcpy.management.MakeFeatureLayer(COUNTIES_FC, counties_lyr)

# Processing state fips from the top
arcpy.management.SelectLayerByAttribute(
    counties_lyr,
    "NEW_SELECTION",
    f"STATEFP = '{STATE_FIPS}'"   #reads input from top of script
)

summary_tables = []

# Get NAME + GEOID + STATEFP from the selected counties
#   ---> ****NEEDS TO BE CHANGED TO RUN WHOLE STATE****
MAX_COUNTIES = 999   # <-- change to 999 after testing to run whole state

i = 0

with arcpy.da.SearchCursor(counties_lyr, ["NAME", "GEOID", "STATEFP"]) as cur:
    for name, geoid, statefp in cur:

        i += 1
        if i > MAX_COUNTIES:
            print("Stopping early for debugging.")
            break

        print(f"Running county: {name} (GEOID {geoid})")

        try:
            tbl = run_one_county(name, geoid, statefp)
            summary_tables.append(tbl)
            print(f"  OK -> {tbl}")
        except Exception as e:
            print(f"  FAILED -> {name}: {e}")

# ------------------------------------------------------------
# 5) COMBINE ALL SUMMARY TABLES INTO ONE TABLE
# ------------------------------------------------------------
safe_delete(FINAL_MERGED_SUMMARY)

if len(summary_tables) == 0:
    raise RuntimeError("No county summaries were created. Nothing to merge.")

arcpy.management.Merge(summary_tables, FINAL_MERGED_SUMMARY)

print("DONE.")
print("Final merged summary table:")
print(FINAL_MERGED_SUMMARY)

0

# ------------------------------------------------------------
# IMPORTANT NOTE (ACRES FIELD)
# If your wetlands already have a numeric ACRES field, great.
# If not, CalculateGeometryAttributes writes area into ACRES.
# If ACRES already exists but is NOT numeric, fix that once, then re-run.
# ------------------------------------------------------------

