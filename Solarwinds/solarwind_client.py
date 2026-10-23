"""SolarWinds Orion SWIS API Client & Telemetry Extraction Engine.
 
This module provides enterprise-grade read-only access to SolarWinds Orion
Information Service (SWIS) v3 REST API, extracting node metrics, computing health
classifications, vendor distributions, and fleet telemetry aggregations matching
MRD FR-003 & FR-004 specifications.
"""
 
from http import client
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
# from App.core.config import Settings, settings
# from src.sync.source_transport import proxy_request_options, proxy_diagnostics

import os
from dotenv import load_dotenv

load_dotenv()


class SolarWindsSecurityError(Exception):
    pass


ALLOWED_METHODS = {"GET"}


def validate_swql_read_only(query: str):
    query = query.strip().upper()

    if not query.startswith("SELECT"):
        raise SolarWindsSecurityError(
            "Only SELECT queries are allowed."
        )

def proxy_request_options(*args, **kwargs):
    return {}

def proxy_diagnostics(*args, **kwargs):
    return "Proxy Disabled"
 
# from app.core.security import (
#     ALLOWED_METHODS,
#     FORBIDDEN_SWQL_KEYWORDS,
#     SolarWindsSecurityError,
#     validate_swql_read_only,
# )
 
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
 
 
def atomic_json_dump(data: Any, filepath: str, indent: Optional[int] = None) -> None:
    """Safely write JSON data to file using an atomic replace to prevent race conditions.
 
    Args:
        data: Serializable Python object.
        filepath: Target destination filepath.
        indent: Optional indentation level (default: None for compact production).
    """
    target_dir = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(target_dir, exist_ok=True)
   
    fd, temp_path = tempfile.mkstemp(dir=target_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent)
        os.replace(temp_path, filepath)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
 
 
class SolarWindsApiError(Exception):
    """Exception raised for SWIS API query or response errors."""
    pass
 
 
class SolarWindsAuthError(Exception):
    """Exception raised for SWIS API authentication or permission errors."""
    pass
 
 
def normalize_solarwinds_vendor(vendor_str: Optional[str]) -> str:
    """Normalize raw vendor string into standard 5 categories: Windows, Cisco, Linux, SolarWinds, Other.
 
    Args:
        vendor_str: Raw vendor name from Orion.Nodes.
 
    Returns:
        Standard vendor category name.
    """
    if not vendor_str or not isinstance(vendor_str, str):
        return "Other"
 
    v_lower = vendor_str.strip().lower()
    if "windows" in v_lower or "microsoft" in v_lower:
        return "Windows"
    if "cisco" in v_lower:
        return "Cisco"
    if any(k in v_lower for k in ("linux", "ubuntu", "redhat", "red hat", "centos", "debian", "suse", "net-snmp", "rocky", "oracle", "canonical")):
        return "Linux"
    if "solarwinds" in v_lower or "orion" in v_lower:
        return "SolarWinds"
    return "Other"
 
 
def _parse_sw_status(raw_status: Any) -> Optional[int]:
    """Safely parse node status from int, float, or numeric string, guarding against bool."""
    if raw_status is None or isinstance(raw_status, bool):
        return None
    if isinstance(raw_status, int):
        return raw_status
    if isinstance(raw_status, float) and raw_status.is_integer():
        return int(raw_status)
    if isinstance(raw_status, str):
        s = raw_status.strip()
        try:
            val = float(s)
            if val.is_integer():
                return int(val)
        except (ValueError, OverflowError):
            return None
    return None
 
 
def _parse_sw_metric(raw_val: Any) -> Optional[float]:
    """Safely parse resource metric (CPU, RAM, latency) from int, float, or numeric string, guarding against bool and negatives."""
    if raw_val is None or isinstance(raw_val, bool):
        return None
    if isinstance(raw_val, (int, float)):
        return float(raw_val) if raw_val >= 0 else None
    if isinstance(raw_val, str):
        s = raw_val.strip()
        try:
            val = float(s)
            return val if val >= 0 else None
        except (ValueError, OverflowError):
            return None
    return None
 
 
def classify_node_health(node: Dict[str, Any]) -> str:
    """Compute server health classification based on Status, CPU, and RAM thresholds.
 
    Rules:
        - Low/Critical: Status in [2 (Down), 14 (Critical), 0 (Unknown/Unmanaged)] OR CPULoad > 90 OR PercentMemoryUsed > 90
        - Medium: Status in [1, 3] AND (75 <= CPULoad <= 90 OR 80 <= PercentMemoryUsed <= 90 OR Status == 3 (Warning))
        - High: Status == 1 (Up) AND (CPULoad < 75 or CPULoad is None) AND (PercentMemoryUsed < 80 or PercentMemoryUsed is None)
 
    Args:
        node: Node dictionary containing Status, CPULoad, PercentMemoryUsed.
 
    Returns:
        'High', 'Medium', or 'Low' (Critical/Degraded).
    """
    if not isinstance(node, dict):
        return "Low"
 
    raw_status = node.get("Status")
    raw_cpu = node.get("CPULoad")
    raw_ram = node.get("PercentMemoryUsed")
 
    status = _parse_sw_status(raw_status)
    valid_cpu = _parse_sw_metric(raw_cpu)
    valid_ram = _parse_sw_metric(raw_ram)
 
    # Check Critical / Low Health conditions
    is_status_crit = status in [2, 14, 0] or status is None
    is_cpu_crit = valid_cpu is not None and valid_cpu > 90
    is_ram_crit = valid_ram is not None and valid_ram > 90
 
    if is_status_crit or is_cpu_crit or is_ram_crit:
        return "Low"
 
    # Check Warning / Medium Health conditions
    is_status_warn = (status == 3)
    is_cpu_warn = valid_cpu is not None and (75 <= valid_cpu <= 90)
    is_ram_warn = valid_ram is not None and (80 <= valid_ram <= 90)
 
    if is_status_warn or (status in [1, 3] and (is_cpu_warn or is_ram_warn)):
        return "Medium"
 
    # Default to High if Status == 1 (Up) with healthy resource metrics
    if status == 1:
        return "High"
 
    return "Medium"
 
 
class SolarWindsClient:
    """Enterprise read-only client for SolarWinds Orion SWIS API v3."""
 
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 30,
        config=None,
    ) -> None:
        """Initialize SolarWinds SWIS Client with runtime credentials.
 
        Args:
            host: SolarWinds server hostname or IP (defaults to SOLARWINDS_HOST env).
            port: SWIS API port (defaults to SOLARWINDS_PORT env or 17774).
            username: SWIS API username (defaults to SOLARWINDS_USERNAME env).
            password: SWIS API password (defaults to SOLARWINDS_PASSWORD env).
            timeout: HTTP request timeout in seconds.
        """
        # self.host = host or config.SOLARWINDS_HOST or ""
        # self.port = port or config.SOLARWINDS_PORT
        # self.username = username if username is not None else (config.SOLARWINDS_USERNAME or "")
        # self.password = password if password is not None else (config.SOLARWINDS_PASSWORD or "")
        # self.timeout = timeout
        # self.verify_ssl = bool(config.SOLARWINDS_VERIFY_SSL)
        # self.config = config
        self.host = host or os.getenv("SOLARWINDS_HOST", "")
        self.port = int(os.getenv("SOLARWINDS_PORT", "17774"))

        self.username = (
            username
            if username is not None
            else os.getenv("SOLARWINDS_USERNAME", "")
        )

        self.password = (
            password
            if password is not None
            else os.getenv("SOLARWINDS_PASSWORD", "")
        )

        self.timeout = timeout

        self.verify_ssl = False 



        # client.timeout = 30
        # client.verify_ssl = False

        # self.verify_ssl = (
        #     os.getenv("SOLARWINDS_VERIFY_SSL", "false")
        #     .lower() == "true"
        # )
 
        self.base_url = f"https://{self.host}:{self.port}/SolarWinds/InformationService/v3/Json/Query"
        self._session = self._create_resilient_session()
 
    # def _create_resilient_session(self) -> requests.Session:
    #     """Create requests session with retry adapters and connection pooling."""
    #     session = requests.Session()
    #     session.trust_env = bool(self.config.SOURCE_PROXY_INHERIT and self.config.SOURCE_PROXY_MODE == "inherit")
    #     proxies = {}
    #     if self.config.SOURCE_HTTP_PROXY:
    #         proxies["http"] = self.config.SOURCE_HTTP_PROXY
    #     if self.config.SOURCE_HTTPS_PROXY:
    #         proxies["https"] = self.config.SOURCE_HTTPS_PROXY
    #     if proxies:
    #         session.proxies.update(proxies)
    #     logger.info("SolarWinds transport: %s", proxy_diagnostics(self.base_url, self.config))
    #     session.auth = (self.username, self.password)
    #     retries = Retry(
    #         total=3,
    #         backoff_factor=0.5,
    #         status_forcelist=[500, 502, 503, 504],
    #         raise_on_status=False
    #     )
    #     adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    #     session.mount("https://", adapter)
    #     session.mount("http://", adapter)
    #     return session

    def _create_resilient_session(self) -> requests.Session:
        """Create requests session with retry adapters and connection pooling."""

        session = requests.Session()

        # Use system proxy settings if available
        session.trust_env = True

        logger.info("SolarWinds transport: Proxy Disabled")

        session.auth = (self.username, self.password)

        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False
        )

        adapter = HTTPAdapter(
            max_retries=retries,
            pool_connections=10,
            pool_maxsize=10
        )

        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session
 
    def query(self, swql_query: str, params: Optional[Dict[str, Any]] = None, method: str = "GET") -> List[Dict[str, Any]]:
        """Execute a strictly read-only SWQL query against the SWIS REST API.
 
        Args:
            swql_query: Valid SWQL query string (must start with SELECT).
            params: Optional parameter dictionary for parameterized queries.
            method: HTTP method (strictly restricted to GET).
 
        Returns:
            List of result row dictionaries.
 
        Raises:
            SolarWindsSecurityError: If write method or mutating query is attempted.
            SolarWindsAuthError: If authentication/authorization fails (401/403).
            SolarWindsApiError: If query execution fails or returns non-200.
        """
        # Hard Security Guard: Strictly block any non-GET methods
        if method.upper() not in ALLOWED_METHODS:
            raise SolarWindsSecurityError(
                f"SolarWinds integration is strictly READ-ONLY. Method '{method}' is forbidden. Allowed: {ALLOWED_METHODS}"
            )
 
        # Hard Security Guard: Verify SWQL query is strictly SELECT
        validate_swql_read_only(swql_query)
 
        query_params = {"query": swql_query}
        if params:
            if any(str(key).lower() == "query" for key in params):
                raise SolarWindsSecurityError("Parameters cannot override the validated SELECT query")
            query_params.update(params)
 
        logger.info("Executing read-only SWQL query against SWIS API (%s:%s)...", self.host, self.port)
 
        try:
            response = self._session.get(
                self.base_url,
                params=query_params,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
 
            if response.status_code == 200:
                data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                    raise SolarWindsApiError("SWIS response must contain a results list")
                results = data["results"]
                logger.info("SWIS query succeeded. %d rows returned.", len(results))
                return results
 
            if response.status_code in (401, 403):
                raise SolarWindsAuthError(
                    f"Authentication failed (HTTP {response.status_code})"
                )
 
            raise SolarWindsApiError(
                f"SWIS API error HTTP {response.status_code}"
            )
 
        except requests.exceptions.Timeout as exc:
            raise SolarWindsApiError(f"SWIS API connection timed out ({self.timeout}s): {exc}") from exc
        except requests.exceptions.ConnectionError as exc:
            raise SolarWindsApiError(f"Failed to connect to SWIS API at {self.host}:{self.port}: {exc}") from exc
 
    def _fetch_complete_pages(self, fields: str, entity: str, order_fields: List[str], page_size: int = 500,
                              order_by: Optional[str] = None) -> List[Dict[str, Any]]:
        """Bound each SELECT and reject truncation, unstable order or changing counts."""
        def count():
            rows = self.query(f"SELECT COUNT(*) AS Total FROM {entity}")
            if len(rows) != 1 or not isinstance(rows[0], dict):
                raise SolarWindsApiError('Invalid SWIS snapshot count')
            total = rows[0].get('Total')
            if isinstance(total, bool) or not isinstance(total, int) or total < 0:
                raise SolarWindsApiError('Invalid SWIS snapshot count')
            return total
 
        expected = count()
        result = []
        previous = None
        for start in range(1, expected + 1, page_size):
            end = min(start + page_size - 1, expected)
            rows = self.query(f"SELECT {fields} FROM {entity} ORDER BY {order_by or ', '.join(order_fields)} WITH ROWS {start} TO {end}")
            if len(rows) != end - start + 1:
                raise SolarWindsApiError('Incomplete SWIS snapshot page')
            for row in rows:
                try:
                    key = tuple(row[field] for field in order_fields)
                    if any(value is None for value in key) or (previous is not None and key <= previous):
                        raise ValueError('Unstable page order')
                    previous = key
                except (KeyError, TypeError, ValueError) as exc:
                    raise SolarWindsApiError('Invalid SWIS snapshot order') from exc
            result.extend(rows)
        if count() != expected:
            raise SolarWindsApiError('SWIS snapshot changed during extraction')
        return result
 
    def fetch_groups(self) -> List[Dict[str, Any]]:
        return self._fetch_complete_pages(
            'ContainerID, Name, Owner, IsDeleted, Status, StatusDescription',
            'Orion.Container', ['ContainerID'])
 
    def fetch_group_members(self) -> List[Dict[str, Any]]:
        return self._fetch_complete_pages(
            'ContainerID, MemberPrimaryID, MemberEntityType', 'Orion.ContainerMembers',
            ['ContainerID', 'MemberEntityType', 'MemberPrimaryID'])
 
    def fetch_nodes(self) -> List[Dict[str, Any]]:
        """Query server nodes and required fields from Orion.Nodes.
 
        Returns:
            List of node telemetry dictionaries.
        """
        fields = """
                n.NodeID,
                n.Caption,
                n.IPAddress,
                n.Status,
                n.StatusDescription,
                n.CPULoad,
                n.PercentMemoryUsed,
                n.ResponseTime,
                n.AvgResponseTime,
                n.Vendor,
                n.MachineType,
                n.LastSync,
                n.SystemUpTime,
                n.NodeDescription,
                cp.City AS City,
                cp.ITSM_Location AS ITSM_Location,
                cp.NodeCategory AS NodeCategory,
                cp.NodeType AS NodeType,
                n.Contact
        """
        return self._fetch_complete_pages(fields,
            'Orion.Nodes n LEFT JOIN Orion.NodesCustomProperties cp ON n.NodeID = cp.NodeID',
            ['NodeID'], order_by='n.NodeID')
 
    def process_telemetry(self, raw_nodes: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Process, clean, enrich with health classifications, and compute dashboard summary.
 
        Args:
            raw_nodes: Raw node records extracted from Orion.Nodes.
 
        Returns:
            Tuple of (enriched_nodes, dashboard_summary).
        """
        valid_raw_nodes = [n for n in raw_nodes if isinstance(n, dict)]
        total_nodes = len(valid_raw_nodes)
        enriched_nodes: List[Dict[str, Any]] = []
 
        high_health_count = 0
        medium_health_count = 0
        low_health_count = 0
 
        up_count = 0
        down_count = 0
        warning_count = 0
        critical_count = 0
        unmanaged_count = 0
 
        vendor_breakdown = {
            "Windows": 0,
            "Cisco": 0,
            "Linux": 0,
            "SolarWinds": 0,
            "Other": 0,
        }
        raw_vendor_counts: Dict[str, int] = {}
 
        valid_cpu_sum = 0.0
        valid_cpu_count = 0
 
        valid_ram_sum = 0.0
        valid_ram_count = 0
 
        valid_latency_sum = 0.0
        valid_latency_count = 0
 
        degraded_candidates: List[Dict[str, Any]] = []
 
        for node in valid_raw_nodes:
            # Clean and sanitize fields
            node_id = node.get("NodeID")
            caption = node.get("Caption") or "Unknown"
            ip_address = node.get("IPAddress") or "N/A"
            status = node.get("Status")
            status_desc = node.get("StatusDescription") or ""
            cpu_load = node.get("CPULoad")
            ram_used = node.get("PercentMemoryUsed")
            resp_time = node.get("ResponseTime")
            avg_resp_time = node.get("AvgResponseTime")
            raw_vendor = node.get("Vendor") or "Unknown"
            machine_type = node.get("MachineType") or "Unknown"
            last_sync = node.get("LastSync")
            sys_uptime = node.get("SystemUpTime")
            node_desc = node.get("NodeDescription") or ""
            city = node.get("City") or ""
            contact = node.get("Contact") or ""
 
            # Health classification
            health = classify_node_health(node)
            if health == "High":
                high_health_count += 1
            elif health == "Medium":
                medium_health_count += 1
            else:
                low_health_count += 1
 
            # Status tracking
            if status == 1:
                up_count += 1
            elif status == 2:
                down_count += 1
            elif status == 3:
                warning_count += 1
            elif status == 14:
                critical_count += 1
            else:
                unmanaged_count += 1
 
            # Vendor aggregation
            norm_vendor = normalize_solarwinds_vendor(raw_vendor)
            vendor_breakdown[norm_vendor] = vendor_breakdown.get(norm_vendor, 0) + 1
            raw_vendor_counts[raw_vendor] = raw_vendor_counts.get(raw_vendor, 0) + 1
 
            # CPU metrics aggregation
            cpu_metric = _parse_sw_metric(cpu_load)
            if cpu_metric is not None:
                valid_cpu_sum += cpu_metric
                valid_cpu_count += 1
 
            # RAM metrics aggregation
            ram_metric = _parse_sw_metric(ram_used)
            if ram_metric is not None:
                valid_ram_sum += ram_metric
                valid_ram_count += 1
 
            # Latency metrics aggregation
            raw_latency = avg_resp_time if avg_resp_time is not None else resp_time
            latency_metric = _parse_sw_metric(raw_latency)
            if latency_metric is not None:
                valid_latency_sum += latency_metric
                valid_latency_count += 1
 
            enriched_record = {
                "NodeID": node_id,
                "Caption": caption,
                "IPAddress": ip_address,
                "Status": status,
                "StatusDescription": status_desc,
                "CPULoad": cpu_load,
                "PercentMemoryUsed": ram_used,
                "ResponseTime": resp_time,
                "AvgResponseTime": avg_resp_time,
                "Vendor": raw_vendor,
                "NormalizedVendor": norm_vendor,
                "MachineType": machine_type,
                "LastSync": last_sync,
                "SystemUpTime": sys_uptime,
                "NodeDescription": node_desc,
                "City": city,
                "Contact": contact,
                "HealthClassification": health,
            }
            enriched_nodes.append(enriched_record)
 
            # Check if degraded / resource pressure candidate
            is_degraded = (
                health in ("Medium", "Low") or
                status in (2, 3, 14, 0) or
                (cpu_metric is not None and cpu_metric >= 75) or
                (ram_metric is not None and ram_metric >= 80)
            )
            if is_degraded:
                degraded_candidates.append(enriched_record)
 
        # Sort degraded candidates by severity (Low health first, then CPU desc, then RAM desc)
        def degraded_sort_key(item: Dict[str, Any]) -> Tuple[int, float, float]:
            h_rank = 0 if item["HealthClassification"] == "Low" else (1 if item["HealthClassification"] == "Medium" else 2)
            c_val = _parse_sw_metric(item.get("CPULoad")) or 0.0
            r_val = _parse_sw_metric(item.get("PercentMemoryUsed")) or 0.0
            return (h_rank, -c_val, -r_val)
 
        degraded_candidates.sort(key=degraded_sort_key)
        top_degraded = degraded_candidates[:25]
 
        # Calculate averages
        avg_cpu = round(valid_cpu_sum / valid_cpu_count, 1) if valid_cpu_count > 0 else 0.0
        avg_ram = round(valid_ram_sum / valid_ram_count, 1) if valid_ram_count > 0 else 0.0
        avg_latency = round(valid_latency_sum / valid_latency_count, 1) if valid_latency_count > 0 else 0.0
 
        high_pct = round((high_health_count / total_nodes) * 100, 2) if total_nodes > 0 else 0.0
        med_pct = round((medium_health_count / total_nodes) * 100, 2) if total_nodes > 0 else 0.0
        low_pct = round((low_health_count / total_nodes) * 100, 2) if total_nodes > 0 else 0.0
 
        active_monitored = up_count + down_count + warning_count + critical_count
 
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "total_server_nodes": total_nodes,
                "active_monitored_nodes": active_monitored,
                "unmanaged_nodes": unmanaged_count,
                "high_health_nodes": high_health_count,
                "medium_health_nodes": medium_health_count,
                "low_critical_nodes": low_health_count,
                "high_health_pct": high_pct,
                "medium_health_pct": med_pct,
                "low_critical_pct": low_pct,
                "status_counts": {
                    "up": up_count,
                    "down": down_count,
                    "warning": warning_count,
                    "critical": critical_count,
                    "unmanaged_unknown": unmanaged_count,
                },
                "avg_fleet_cpu_load_pct": avg_cpu,
                "avg_fleet_ram_used_pct": avg_ram,
                "avg_fleet_latency_ms": avg_latency,
            },
            "vendor_breakdown": vendor_breakdown,
            "raw_vendor_distribution": raw_vendor_counts,
            "health_breakdown": {
                "High": high_health_count,
                "Medium": medium_health_count,
                "Low": low_health_count,
            },
            "top_degraded_servers": top_degraded,
            "sample_nodes": enriched_nodes[:50],
        }
 
        return enriched_nodes, summary
 
    def fetch_and_save(
        self,
        nodes_output_path: Optional[str] = None,
        summary_output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute full extraction, enrichment, and write output files.
 
        Args:
            nodes_output_path: Destination path for raw enriched nodes JSON.
            summary_output_path: Destination path for summary payload JSON.
 
        Returns:
            The summary payload dictionary.
        """
        raw_nodes = self.fetch_nodes()
        enriched_nodes, summary = self.process_telemetry(raw_nodes)
 
        # Save enriched nodes dataset
        if nodes_output_path:
            atomic_json_dump({
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "total_nodes": len(enriched_nodes),
                "nodes": enriched_nodes,
            }, nodes_output_path, indent=2)
            logger.info("Saved %d SolarWinds node records to: %s", len(enriched_nodes), nodes_output_path)
 
        # Save summary payload
        if summary_output_path:
            # Preserve full node registry for in-browser pagination
            summary["sample_nodes"] = enriched_nodes
            atomic_json_dump(summary, summary_output_path, indent=2)
            logger.info("Saved SolarWinds summary payload to: %s", summary_output_path)
 
        return summary
 
    def reconcile_from_file(
        self,
        nodes_input_path: str,
        summary_output_path: Optional[str] = None,
        nodes_output_path: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Reconcile summary metrics and enrich raw node records from a local JSON file.
 
        Args:
            nodes_input_path: Path to existing raw nodes JSON file.
            summary_output_path: Optional path to write reconciled summary payload.
            nodes_output_path: Optional path to write enriched raw nodes (defaults to nodes_input_path).
 
        Returns:
            Tuple of (enriched_nodes, summary).
        """
        if not os.path.exists(nodes_input_path):
            raise FileNotFoundError(f"SolarWinds nodes file not found: {nodes_input_path}")
 
        try:
            with open(nodes_input_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except json.JSONDecodeError as err:
            raise SolarWindsApiError(
                f"Corrupt or invalid JSON in SolarWinds nodes file '{nodes_input_path}': {err}. "
                "Please regenerate the file via 'python scripts/fetch_solarwinds_data.py'."
            ) from err
 
        if not isinstance(raw_data, (dict, list)):
            raise SolarWindsApiError(
                f"Unexpected JSON structure in '{nodes_input_path}'. Expected dict or list of nodes, "
                f"got {type(raw_data).__name__}."
            )
 
        if isinstance(raw_data, dict):
            raw_nodes_val = raw_data.get("nodes")
            if raw_nodes_val is not None and not isinstance(raw_nodes_val, list):
                raise SolarWindsApiError(
                    f"Unexpected JSON structure in '{nodes_input_path}': 'nodes' field must be a list, "
                    f"got {type(raw_nodes_val).__name__}."
                )
            raw_nodes = raw_nodes_val if isinstance(raw_nodes_val, list) else []
            extracted_at = raw_data.get("extracted_at", datetime.now(timezone.utc).isoformat())
        else:
            raw_nodes = raw_data
            extracted_at = datetime.now(timezone.utc).isoformat()
 
        enriched_nodes, summary = self.process_telemetry(raw_nodes)
 
        target_nodes_path = nodes_output_path or nodes_input_path
        atomic_json_dump({
            "extracted_at": extracted_at,
            "total_nodes": len(enriched_nodes),
            "nodes": enriched_nodes,
        }, target_nodes_path, indent=2)
 
        summary["sample_nodes"] = enriched_nodes
        if summary_output_path:
            atomic_json_dump(summary, summary_output_path, indent=2)
 
        return enriched_nodes, summary
 
