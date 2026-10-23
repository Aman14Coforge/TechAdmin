"""
SolarWinds DataFrame Loader

Uses the existing SolarWindsClient to:
1. Fetch node telemetry from SolarWinds
2. Process and enrich the data
3. Convert to Pandas DataFrame
4. Save to CSV (optional)
5. Return DataFrame for downstream analytics/database loading
"""

import pandas as pd

from app.services.solarwind_client import SolarWindsClient


def fetch_solarwinds_dataframe() -> pd.DataFrame:
    """
    Fetch SolarWinds node data and return as DataFrame.

    Returns:
        pd.DataFrame
    """
    client = SolarWindsClient()

    # Fetch raw node data
    raw_nodes = client.fetch_nodes()

    # Process telemetry and enrich data
    enriched_nodes, summary = client.process_telemetry(raw_nodes)

    # Convert to DataFrame
    df = pd.DataFrame(enriched_nodes)

    print(f"Successfully loaded {len(df)} nodes")
    print(f"Columns: {list(df.columns)}")

    return df


def save_dataframe_to_csv(
    output_file: str = "solarwinds_nodes.csv"
) -> pd.DataFrame:
    """
    Fetch SolarWinds data and save to CSV.

    Args:
        output_file: Output CSV filename

    Returns:
        pd.DataFrame
    """
    df = fetch_solarwinds_dataframe()

    df.to_csv(output_file, index=False)

    print(f"CSV saved: {output_file}")

    return df


if __name__ == "__main__":
    df = save_dataframe_to_csv()

    print("\nDataFrame Shape:")
    print(df.shape)

    print("\nSample Records:")
    print(df.head())
